import collections
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlparse

import aiohttp
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database as db

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tcasino.api")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
STARS_TO_CENTS = 1  # 100 Stars = 100 cents ($1.00)
CRASH_SPEED = 0.12  # mult(t) = exp(0.12 * t)
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "100.0"))
MAX_WIN_USD = float(os.getenv("MAX_WIN_USD", "1000.0"))
MAX_BET_CENTS = int(round(MAX_BET_USD * 100))
MAX_WIN_CENTS = int(round(MAX_WIN_USD * 100))
INIT_DATA_MAX_AGE = int(os.getenv("INIT_DATA_MAX_AGE", "86400"))  # 24 часа
MAX_PENDING_WITHDRAWALS = int(os.getenv("MAX_PENDING_WITHDRAWALS", "2"))

http_session: aiohttp.ClientSession | None = None


def _build_allowed_origins() -> list[str]:
    origins: list[str] = []
    raw_list = [os.getenv("WEBAPP_URL", "")] + os.getenv("ALLOWED_ORIGINS", "").split(",")
    for item in raw_list:
        val = item.strip().strip('"').strip("'")
        if not val:
            continue
        parsed = urlparse(val)
        if parsed.scheme and parsed.netloc:
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in origins:
                origins.append(origin)
    return origins


ALLOWED_ORIGINS = _build_allowed_origins()
if not ALLOWED_ORIGINS:
    logger.warning("WEBAPP_URL / ALLOWED_ORIGINS not set — CORS falls back to wildcard '*'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_session
    await db.init_db()
    http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    try:
        yield
    finally:
        if http_session:
            await http_session.close()
            http_session = None
        await db.close_db()


app = FastAPI(title="T Casino Mini App v2.2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Лёгкий per-user rate limiter (sliding window) ---
_rate_buckets: dict[tuple[str, int], collections.deque[float]] = collections.defaultdict(collections.deque)


_rl_last_prune = 0.0


def check_rate_limit(scope: str, user_id: int, limit: int, window_sec: float):
    global _rl_last_prune
    now = time.monotonic()
    if len(_rate_buckets) > 500 and now - _rl_last_prune > 60.0:
        _rl_last_prune = now
        stale_keys = [k for k, dq in _rate_buckets.items() if not dq or now - dq[-1] > 120.0]
        for k in stale_keys:
            _rate_buckets.pop(k, None)

    q = _rate_buckets[(scope, user_id)]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail="Слишком много запросов. Подождите пару секунд.")
    q.append(now)


def to_cents(dollars: float) -> int:
    return int(round(dollars * 100))


def to_dollars(cents: int) -> float:
    return round(cents / 100.0, 2)


def validate_bet_cents(dollars: float) -> int:
    bet_cents = to_cents(dollars)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")
    if bet_cents > MAX_BET_CENTS:
        raise HTTPException(status_code=400, detail=f"Максимальная ставка — ${MAX_BET_USD:.2f}")
    return bet_cents


def cap_win(win_cents: int) -> int:
    return min(max(0, int(win_cents)), MAX_WIN_CENTS)


CARD_RANK_RE = re.compile(r"^(10|[2-9JQKA])")


def parse_card_rank(card: str) -> str:
    m = CARD_RANK_RE.match(str(card or ""))
    return m.group(1) if m else "0"


async def send_tg_message(chat_id: int, text: str, reply_markup: dict | None = None) -> bool:
    if not http_session:
        logger.warning("HTTP session is not initialized; skipping Telegram message")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        body["reply_markup"] = reply_markup
    try:
        async with http_session.post(url, json=body) as resp:
            if resp.status != 200:
                err_body = await resp.text()
                logger.warning("Telegram sendMessage failed (%s): %s", resp.status, err_body[:200])
                return False
            return True
    except Exception as exc:
        logger.warning("Telegram sendMessage network error: %s", type(exc).__name__)
        return False


async def notify_admin_withdrawal(wd_id: int, user_id: int, username: str, amount_cents: int, details: str):
    if not ADMIN_ID:
        return
    text = (
        f"💸 Новая заявка на вывод #{wd_id}\n\n"
        f"👤 Игрок: {username} (ID: {user_id})\n"
        f"💰 Сумма: ${to_dollars(amount_cents):.2f}\n"
        f"💳 Реквизиты: {details}"
    )
    markup = {
        "inline_keyboard": [[
            {"text": "✅ Одобрить", "callback_data": f"wd_ok:{wd_id}"},
            {"text": "❌ Отклонить", "callback_data": f"wd_no:{wd_id}"},
        ]]
    }
    await send_tg_message(ADMIN_ID, text, reply_markup=markup)


# --- Авторизация Telegram WebApp (HMAC-SHA256 + auth_date) ---
def verify_telegram_init_data(init_data: str) -> dict:
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed initData")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")

    raw_auth_date = parsed.get("auth_date")
    if not raw_auth_date or not raw_auth_date.isdigit():
        raise HTTPException(status_code=401, detail="Missing auth_date")
    auth_date = int(raw_auth_date)
    now = time.time()
    if now - auth_date > INIT_DATA_MAX_AGE or auth_date - now > 300:
        raise HTTPException(status_code=401, detail="Сессия Telegram устарела. Переоткройте приложение.")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Missing user data")
    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=401, detail="Invalid user payload")


async def get_current_user(x_telegram_init_data: str | None = Header(default=None)) -> dict:
    if x_telegram_init_data:
        tg_user = verify_telegram_init_data(x_telegram_init_data)
        user_id = int(tg_user["id"])
        username = tg_user.get("first_name") or tg_user.get("username") or "Игрок"
    elif DEV_MODE:
        user_id = 123456789
        username = "DevPlayer"
    else:
        raise HTTPException(status_code=401, detail="Telegram auth required")

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not row:
            initial_card = secrets.randbelow(11) + 3
            await conn.execute(
                """
                INSERT INTO users (user_id, username, balance_cents, games_played, total_wagered_cents, total_won_cents, hilo_card)
                VALUES ($1, $2, 0, 0, 0, 0, $3)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id, username, initial_card,
            )
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        elif row["username"] != username:
            await conn.execute("UPDATE users SET username = $1 WHERE user_id = $2", username, user_id)
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row)


async def settle_instant_game(
    user_id: int,
    bet_cents: int,
    win_cents: int,
    game_name: str,
    games_inc: int = 1,
) -> tuple[int, int]:
    """Атомарно списывает ставку, начисляет выигрыш и пишет запись в ledger за 1 SQL round-trip."""
    check_rate_limit("play", user_id, limit=45, window_sec=10.0)
    capped_win = cap_win(win_cents)
    net_cents = capped_win - bet_cents
    meta = f"{game_name}:bet={bet_cents}:win={capped_win}:n={games_inc}"

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH updated AS (
                UPDATE users
                SET balance_cents = balance_cents - $1 + $2,
                    games_played = games_played + $7,
                    total_wagered_cents = total_wagered_cents + $1,
                    total_won_cents = total_won_cents + $2
                WHERE user_id = $3 AND balance_cents >= $1
                RETURNING balance_cents
            )
            INSERT INTO transactions (user_id, kind, amount_cents, balance_after_cents, meta)
            SELECT $3, $4, $5, balance_cents, $6 FROM updated
            RETURNING balance_after_cents
            """,
            bet_cents,
            capped_win,
            user_id,
            f"play_{game_name}",
            net_cents,
            meta,
            max(1, int(games_inc)),
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Кассе!")
        return int(row["balance_after_cents"]), capped_win


def mines_multiplier(mines_count: int, revealed_count: int) -> float:
    if revealed_count == 0:
        return 1.0
    prob = 1.0
    for i in range(revealed_count):
        prob *= (25 - mines_count - i) / (25 - i)
    return max(1.02, round(0.94 / prob, 2))


TOWER_CFG = {
    "easy": (4, 1),    # 4 колонки, 1 ловушка
    "medium": (3, 1),  # 3 колонки, 1 ловушка
    "hard": (3, 2),    # 3 колонки, 2 ловушки
}
TOWER_FLOORS = 8


def tower_multiplier(difficulty: str, floor: int) -> float:
    if floor <= 0:
        return 1.0
    cols, traps = TOWER_CFG[difficulty]
    safe_prob = (cols - traps) / cols
    return round(0.94 / (safe_prob ** floor), 2)


def crash_current_mult(started_at: float) -> float:
    elapsed = max(0.0, time.time() - started_at)
    return round(math.exp(CRASH_SPEED * elapsed), 2)


def draw_crash_point() -> float:
    r = (secrets.randbelow(999999) + 1) / 1000000.0
    val = 0.94 / r
    return 1.0 if val < 1.01 else round(min(val, 1000.0), 2)


async def settle_crash_if_ended(conn, game) -> dict | None:
    """
    Единая проверка завершения активного полёта Краша (вызывается внутри транзакции с FOR UPDATE).
    Гарантирует выплату сработавшего auto_cashout даже если игрок свернул Telegram или пропала сеть.
    Возвращает словарь результата, если полёт завершён, или None, если ракета ещё летит.
    """
    uid = int(game["user_id"])
    now_mult = crash_current_mult(game["started_at"])
    auto_c = float(game["auto_cashout"] or 0.0)
    cp = float(game["crash_point"])

    if auto_c >= 1.05 and now_mult >= auto_c and auto_c <= cp:
        win_cents = cap_win(int(round(game["bet_cents"] * auto_c)))
        u_row = await conn.fetchrow(
            """
            UPDATE users
            SET balance_cents = balance_cents + $1,
                total_won_cents = total_won_cents + $1
            WHERE user_id = $2
            RETURNING balance_cents
            """,
            win_cents,
            uid,
        )
        new_bal = int(u_row["balance_cents"])
        await db.log_transaction(conn, uid, "crash_auto_win", win_cents, new_bal, f"mult={auto_c}")
        await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", uid)
        return {
            "status": "cashed_out",
            "multiplier": auto_c,
            "crash_point": cp,
            "win": to_dollars(win_cents),
            "balance": to_dollars(new_bal),
        }

    if now_mult >= cp:
        await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", uid)
        u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", uid)
        return {
            "status": "crashed",
            "multiplier": cp,
            "crash_point": cp,
            "win": 0.0,
            "balance": to_dollars(int(u_row["balance_cents"])),
        }

    return None


# --- Модели запросов ---
class BetRequest(BaseModel):
    bet: float = Field(gt=0, le=MAX_BET_USD)


class CoinflipRequest(BetRequest):
    choice: str = Field(pattern="^(heads|tails)$")


class DiceRequest(BetRequest):
    target: int = Field(ge=6, le=95)
    direction: str = Field(pattern="^(under|over)$")


class MinesStartRequest(BetRequest):
    mines_count: int = Field(ge=1, le=24)


class MinesRevealRequest(BaseModel):
    cell: int = Field(ge=-1, le=24)  # -1 = случайная клетка (Авто-мины)


class CrashStartRequest(BetRequest):
    auto_cashout: float = Field(default=0.0, ge=0.0, le=1000.0)


class RouletteRequest(BetRequest):
    bet_type: str = Field(pattern="^(red|black|green|even|odd|low|high|dozen1|dozen2|dozen3|number)$")
    number: int | None = Field(default=None, ge=0, le=36)


class HiloRequest(BetRequest):
    guess: str = Field(pattern="^(high|low)$")


class PlinkoRequest(BetRequest):
    risk: str = Field(default="medium", pattern="^(low|medium|high)$")
    balls: int = Field(default=1, ge=1, le=50)


class TowerStartRequest(BetRequest):
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")


class TowerClimbRequest(BaseModel):
    col: int = Field(ge=-1, le=3)  # -1 = случайный выбор


class LimboRequest(BetRequest):
    target: float = Field(ge=1.05, le=1000.0)


class KenoRequest(BetRequest):
    picks: list[int] = Field(min_length=1, max_length=8)


class CasesRequest(BaseModel):
    tier: str = Field(pattern="^(bronze|silver|gold|royal)$")


class BaccaratRequest(BetRequest):
    choice: str = Field(pattern="^(player|banker|tie)$")


class ThimblesRequest(BetRequest):
    cup: int = Field(ge=0, le=2)
    balls: int = Field(default=1, ge=1, le=2)


class RpsRequest(BetRequest):
    choice: str = Field(pattern="^(rock|paper|scissors)$")


class PenaltyRequest(BetRequest):
    zone: int = Field(ge=0, le=4)
    difficulty: str = Field(default="normal", pattern="^(normal|hard)$")


class Dice7Request(BetRequest):
    choice: str = Field(pattern="^(under|over|exact7|double)$")


class StarsInvoiceRequest(BaseModel):
    stars: int = Field(ge=1, le=10000)


class WithdrawRequest(BaseModel):
    amount: float = Field(ge=1.0, le=100000)
    details: str = Field(min_length=3, max_length=200)


# --- Основные маршруты ---
@app.api_route("/", methods=["GET", "HEAD"])
def serve_index():
    return FileResponse("static/index.html")


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    try:
        async with db.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Health check DB failure: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/api/me")
async def api_me(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    active_crash = None

    async with db.pool.acquire() as conn:
        # Сначала корректно закрываем завершённый Краш (с выплатой auto_cashout!)
        async with conn.transaction():
            crash_row = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if crash_row:
                settled = await settle_crash_if_ended(conn, crash_row)
                if not settled:
                    active_crash = {
                        "bet": to_dollars(crash_row["bet_cents"]),
                        "auto_cashout": crash_row["auto_cashout"],
                        "started_at": crash_row["started_at"],
                        "multiplier": crash_current_mult(crash_row["started_at"]),
                    }

        fresh_user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", uid)
        mines_row = await conn.fetchrow("SELECT * FROM mines_games WHERE user_id = $1 AND active = 1", uid)
        tower_row = await conn.fetchrow("SELECT * FROM tower_games WHERE user_id = $1 AND active = 1", uid)
        bj_row = await conn.fetchrow("SELECT * FROM blackjack_games WHERE user_id = $1 AND active = 1", uid)
        wd_rows = await conn.fetch(
            "SELECT id, amount_cents, status FROM withdrawals WHERE user_id = $1 ORDER BY id DESC LIMIT 10",
            uid,
        )

    active_mines = None
    if mines_row:
        revealed = json.loads(mines_row["revealed"])
        mult = mines_multiplier(mines_row["mines_count"], len(revealed))
        potential_cents = cap_win(int(round(mines_row["bet_cents"] * mult)))
        active_mines = {
            "bet": to_dollars(mines_row["bet_cents"]),
            "mines_count": mines_row["mines_count"],
            "revealed": revealed,
            "multiplier": mult,
            "potential_win": to_dollars(potential_cents),
        }

    active_tower = None
    if tower_row:
        mult = tower_multiplier(tower_row["difficulty"], tower_row["floor"])
        potential_cents = cap_win(int(round(tower_row["bet_cents"] * mult)))
        active_tower = {
            "bet": to_dollars(tower_row["bet_cents"]),
            "difficulty": tower_row["difficulty"],
            "floor": tower_row["floor"],
            "multiplier": mult,
            "potential_win": to_dollars(potential_cents),
        }

    active_blackjack = None
    if bj_row:
        p_hand = json.loads(bj_row["player_hand"])
        d_hand = json.loads(bj_row["dealer_hand"])
        active_blackjack = {
            "bet": to_dollars(bj_row["bet_cents"]),
            "player_hand": p_hand,
            "player_score": bj_score(p_hand),
            "dealer_visible": [d_hand[0], "🂠"],
            "dealer_visible_score": bj_score([d_hand[0]]),
        }

    hilo_card = int(fresh_user["hilo_card"] or 7)
    if hilo_card < 2 or hilo_card > 14:
        hilo_card = 7

    return {
        "user_id": uid,
        "username": fresh_user["username"],
        "balance": to_dollars(fresh_user["balance_cents"]),
        "games_played": fresh_user["games_played"],
        "total_won": to_dollars(fresh_user["total_won_cents"]),
        "hilo_card": hilo_card,
        "limits": {"max_bet": MAX_BET_USD, "max_win": MAX_WIN_USD},
        "active_mines": active_mines,
        "active_crash": active_crash,
        "active_tower": active_tower,
        "active_blackjack": active_blackjack,
        "withdrawals": [
            {"id": r["id"], "amount": to_dollars(r["amount_cents"]), "status": r["status"]}
            for r in wd_rows
        ],
        "is_admin": bool(ADMIN_ID and uid == ADMIN_ID),
    }


@app.get("/api/leaderboard")
async def api_leaderboard(user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT username, total_won_cents, games_played
            FROM users
            WHERE games_played > 0 OR total_won_cents > 0
            ORDER BY total_won_cents DESC, games_played DESC
            LIMIT 15
            """
        )
    return {
        "leaders": [
            {
                "username": r["username"] or "Игрок",
                "total_won": to_dollars(r["total_won_cents"]),
                "games_played": r["games_played"],
            }
            for r in rows
        ]
    }


@app.post("/api/withdraw")
async def api_withdraw(req: WithdrawRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("withdraw", uid, limit=5, window_sec=60.0)

    amount_cents = to_cents(req.amount)
    details = req.details.strip()
    if amount_cents < 100:
        raise HTTPException(status_code=400, detail="Минимальная сумма вывода — $1.00")
    if len(details) < 3:
        raise HTTPException(status_code=400, detail="Укажите корректные реквизиты")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            u_lock = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1 FOR UPDATE", uid)
            if not u_lock or int(u_lock["balance_cents"]) < amount_cents:
                raise HTTPException(status_code=400, detail="Недостаточно средств на балансе")

            pending_cnt = await conn.fetchval(
                "SELECT COUNT(*) FROM withdrawals WHERE user_id = $1 AND status = 'pending'",
                uid,
            )
            if pending_cnt >= MAX_PENDING_WITHDRAWALS:
                raise HTTPException(
                    status_code=400,
                    detail=f"У вас уже есть {pending_cnt} активные заявки на вывод. Дождитесь их обработки.",
                )

            row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents - $1 WHERE user_id = $2 RETURNING balance_cents",
                amount_cents,
                uid,
            )
            wd_row = await conn.fetchrow(
                "INSERT INTO withdrawals (user_id, username, amount_cents, details, status) VALUES ($1, $2, $3, $4, 'pending') RETURNING id",
                uid,
                user["username"],
                amount_cents,
                details,
            )
            wd_id = int(wd_row["id"])
            new_bal_cents = int(row["balance_cents"])
            await db.log_transaction(conn, uid, "withdraw_request", -amount_cents, new_bal_cents, f"wd:{wd_id}")

    await notify_admin_withdrawal(wd_id, uid, user["username"], amount_cents, details)
    return {"id": wd_id, "balance": to_dollars(new_bal_cents), "status": "pending"}


@app.post("/api/stars/invoice")
async def create_stars_invoice(req: StarsInvoiceRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("invoice", uid, limit=10, window_sec=60.0)

    if not http_session:
        raise HTTPException(status_code=503, detail="Сервис временно недоступен")

    amount_cents = req.stars * STARS_TO_CENTS
    usd = to_dollars(amount_cents)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink"
    payload = {
        "title": f"Пополнение T Casino: ${usd:.2f}",
        "description": f"Зачисление ${usd:.2f} на баланс за {req.stars} Telegram Stars",
        "payload": f"topup:{uid}:{req.stars}",
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": f"${usd:.2f}", "amount": req.stars}],
    }

    try:
        async with http_session.post(url, json=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.error("createInvoiceLink Telegram error: %s", data.get("description"))
                raise HTTPException(status_code=502, detail="Не удалось создать счёт Telegram Stars")
            return {"invoice_url": data["result"]}
    except HTTPException:
        raise
    except Exception as exc:
        # Никогда не пробрасываем текст исключения наружу — там может оказаться BOT_TOKEN из URL
        logger.error("createInvoiceLink failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Ошибка соединения с Telegram. Попробуйте позже.")


# =========================================================
# 1. СЛОТЫ (RTP ~90.5%)
# =========================================================
SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]


@app.post("/api/play/slots")
async def play_slots(req: BetRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    reels = [secrets.choice(SLOT_SYMBOLS) for _ in range(3)]
    mult = 0.0
    if reels[0] == reels[1] == reels[2]:
        mult = 20.0 if reels[0] == "7️⃣" else (12.0 if reels[0] == "💎" else 6.0)
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        mult = 1.55

    raw_win = int(round(bet_cents * mult))
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "slots")
    return {"reels": reels, "multiplier": mult, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# =========================================================
# 2. МИНЫ (RTP 94%, авто-клетка, показ бомб после победы)
# =========================================================
@app.post("/api/play/mines/start")
async def mines_start(req: MinesStartRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=45, window_sec=10.0)
    bet_cents = validate_bet_cents(req.bet)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Блокируем строку пользователя первой — полностью исключаем race condition
            u_lock = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1 FOR UPDATE", uid)
            if not u_lock or int(u_lock["balance_cents"]) < bet_cents:
                raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Кассе!")

            existing = await conn.fetchrow(
                "SELECT active FROM mines_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if existing:
                raise HTTPException(status_code=400, detail="Завершите текущую игру в Мины")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2
                RETURNING balance_cents
                """,
                bet_cents,
                uid,
            )
            new_bal_cents = int(row["balance_cents"])
            await db.log_transaction(conn, uid, "mines_bet", -bet_cents, new_bal_cents, f"mines={req.mines_count}")

            cells = list(range(25))
            mines = [cells.pop(secrets.randbelow(len(cells))) for _ in range(req.mines_count)]

            await conn.execute(
                """
                INSERT INTO mines_games (user_id, bet_cents, mines_count, mines_positions, revealed, active)
                VALUES ($1, $2, $3, $4, $5, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    bet_cents = EXCLUDED.bet_cents,
                    mines_count = EXCLUDED.mines_count,
                    mines_positions = EXCLUDED.mines_positions,
                    revealed = EXCLUDED.revealed,
                    active = 1
                """,
                uid, bet_cents, req.mines_count, json.dumps(mines), json.dumps([]),
            )
    return {"balance": to_dollars(new_bal_cents), "bet": to_dollars(bet_cents), "mines_count": req.mines_count}


@app.post("/api/play/mines/reveal")
async def mines_reveal(req: MinesRevealRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=60, window_sec=10.0)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM mines_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры")

            mines = json.loads(game["mines_positions"])
            revealed = json.loads(game["revealed"])

            cell = req.cell
            if cell == -1:
                unopened = [i for i in range(25) if i not in revealed]
                if not unopened:
                    raise HTTPException(status_code=400, detail="Нет закрытых клеток")
                cell = secrets.choice(unopened)
            elif cell in revealed:
                raise HTTPException(status_code=400, detail="Клетка уже открыта")

            if cell in mines:
                await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", uid)
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", uid)
                return {
                    "status": "boom",
                    "cell": cell,
                    "mines": mines,
                    "revealed": revealed,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            revealed.append(cell)
            mult = mines_multiplier(game["mines_count"], len(revealed))
            potential_cents = cap_win(int(round(game["bet_cents"] * mult)))

            if len(revealed) == 25 - game["mines_count"] or potential_cents >= MAX_WIN_CENTS:
                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    potential_cents, uid,
                )
                new_bal = int(u_row["balance_cents"])
                await db.log_transaction(conn, uid, "mines_win", potential_cents, new_bal, f"mult={mult}")
                await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", uid)
                return {
                    "status": "win_all",
                    "cell": cell,
                    "multiplier": mult,
                    "win": to_dollars(potential_cents),
                    "mines": mines,
                    "revealed": revealed,
                    "balance": to_dollars(new_bal),
                }

            await conn.execute("UPDATE mines_games SET revealed = $1 WHERE user_id = $2", json.dumps(revealed), uid)
            return {
                "status": "safe",
                "cell": cell,
                "multiplier": mult,
                "potential_win": to_dollars(potential_cents),
                "revealed": revealed,
            }


@app.post("/api/play/mines/cashout")
async def mines_cashout(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM mines_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры")

            revealed = json.loads(game["revealed"])
            if len(revealed) == 0:
                raise HTTPException(status_code=400, detail="Откройте хотя бы одну клетку")

            mines = json.loads(game["mines_positions"])
            mult = mines_multiplier(game["mines_count"], len(revealed))
            win_cents = cap_win(int(round(game["bet_cents"] * mult)))

            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, uid,
            )
            new_bal_cents = int(u_row["balance_cents"])
            await db.log_transaction(conn, uid, "mines_win", win_cents, new_bal_cents, f"mult={mult}")
            await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", uid)

    return {
        "win": to_dollars(win_cents),
        "multiplier": mult,
        "mines": mines,
        "revealed": revealed,
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 3. КОСТИ (93% RTP, шанс 5–90%)
# =========================================================
@app.post("/api/play/dice")
async def play_dice(req: DiceRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    chance = (req.target - 1) if req.direction == "under" else (100 - req.target)
    if chance < 5 or chance > 90:
        raise HTTPException(status_code=400, detail="Допустимый шанс победы — от 5% до 90%")

    roll = secrets.randbelow(100) + 1
    is_win = (roll < req.target) if req.direction == "under" else (roll > req.target)
    multiplier = round(93.0 / chance, 2)
    raw_win = int(round(bet_cents * multiplier)) if is_win else 0

    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "dice")
    return {
        "roll": roll,
        "is_win": is_win,
        "multiplier": multiplier,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 4. МОНЕТКА (1.90x, RTP 95%)
# =========================================================
@app.post("/api/play/coinflip")
async def play_coinflip(req: CoinflipRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    result = secrets.choice(["heads", "tails"])
    raw_win = int(round(bet_cents * 1.90)) if result == req.choice else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "coinflip")
    return {"result": result, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# =========================================================
# 5. ЖИВОЙ КРАШ (RTP 94%, ручной и авто-вывод)
# =========================================================
@app.post("/api/play/crash/start")
async def crash_start(req: CrashStartRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=45, window_sec=10.0)
    bet_cents = validate_bet_cents(req.bet)
    if req.auto_cashout != 0.0 and req.auto_cashout < 1.05:
        raise HTTPException(status_code=400, detail="Авто-вывод должен быть от 1.05x (или 0 для отключения)")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Блокируем пользователя первым
            await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1 FOR UPDATE", uid)

            existing = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if existing:
                settled = await settle_crash_if_ended(conn, existing)
                if not settled:
                    raise HTTPException(status_code=400, detail="Ракета уже в полёте!")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2 AND balance_cents >= $1
                RETURNING balance_cents
                """,
                bet_cents,
                uid,
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств")
            new_bal_cents = int(row["balance_cents"])
            await db.log_transaction(conn, uid, "crash_bet", -bet_cents, new_bal_cents, f"auto={req.auto_cashout}")

            cp = draw_crash_point()
            now = time.time()

            if cp <= 1.00:
                await conn.execute(
                    """
                    INSERT INTO crash_games (user_id, bet_cents, crash_point, auto_cashout, started_at, active)
                    VALUES ($1, $2, 1.0, $3, $4, 0)
                    ON CONFLICT (user_id) DO UPDATE SET
                        bet_cents = EXCLUDED.bet_cents,
                        crash_point = 1.0,
                        auto_cashout = EXCLUDED.auto_cashout,
                        started_at = EXCLUDED.started_at,
                        active = 0
                    """,
                    uid, bet_cents, req.auto_cashout, now,
                )
                return {
                    "status": "crashed",
                    "crash_point": 1.0,
                    "balance": to_dollars(new_bal_cents),
                    "started_at": now,
                    "speed": CRASH_SPEED,
                }

            await conn.execute(
                """
                INSERT INTO crash_games (user_id, bet_cents, crash_point, auto_cashout, started_at, active)
                VALUES ($1, $2, $3, $4, $5, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    bet_cents = EXCLUDED.bet_cents,
                    crash_point = EXCLUDED.crash_point,
                    auto_cashout = EXCLUDED.auto_cashout,
                    started_at = EXCLUDED.started_at,
                    active = 1
                """,
                uid, bet_cents, cp, req.auto_cashout, now,
            )

    return {
        "status": "flying",
        "balance": to_dollars(new_bal_cents),
        "started_at": now,
        "speed": CRASH_SPEED,
        "auto_cashout": req.auto_cashout,
    }


@app.get("/api/play/crash/state")
async def crash_state(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                return {"status": "idle"}

            settled = await settle_crash_if_ended(conn, game)
            if settled:
                return settled

            return {"status": "flying", "multiplier": crash_current_mult(game["started_at"])}


@app.post("/api/play/crash/cashout")
async def crash_cashout(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активного полёта")

            settled = await settle_crash_if_ended(conn, game)
            if settled:
                return settled

            now_mult = crash_current_mult(game["started_at"])
            cp = float(game["crash_point"])
            if now_mult < 1.01:
                raise HTTPException(status_code=400, detail="Подождите долю секунды (минимум 1.01x)")

            cash_mult = min(now_mult, cp)
            win_cents = cap_win(int(round(game["bet_cents"] * cash_mult)))
            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, uid,
            )
            new_bal = int(u_row["balance_cents"])
            await db.log_transaction(conn, uid, "crash_win", win_cents, new_bal, f"mult={cash_mult}")
            await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", uid)
            return {
                "status": "cashed_out",
                "multiplier": cash_mult,
                "crash_point": cp,
                "win": to_dollars(win_cents),
                "balance": to_dollars(new_bal),
            }


# =========================================================
# 6. ЕВРОПЕЙСКАЯ РУЛЕТКА (0–36, RTP 91.9%–94.9%)
# =========================================================
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


@app.post("/api/play/roulette")
async def play_roulette(req: RouletteRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    if req.bet_type == "number" and req.number is None:
        raise HTTPException(status_code=400, detail="Укажите число от 0 до 36")

    number = secrets.randbelow(37)
    color = "green" if number == 0 else ("red" if number in RED_NUMBERS else "black")

    is_win = False
    mult = 0.0
    if req.bet_type == "green":
        is_win, mult = (number == 0), 34.0
    elif req.bet_type == "number":
        is_win, mult = (number == req.number), 34.0
    elif req.bet_type == "red":
        is_win, mult = (color == "red"), 1.95
    elif req.bet_type == "black":
        is_win, mult = (color == "black"), 1.95
    elif req.bet_type == "even":
        is_win, mult = (number != 0 and number % 2 == 0), 1.95
    elif req.bet_type == "odd":
        is_win, mult = (number % 2 == 1), 1.95
    elif req.bet_type == "low":
        is_win, mult = (1 <= number <= 18), 1.95
    elif req.bet_type == "high":
        is_win, mult = (19 <= number <= 36), 1.95
    elif req.bet_type == "dozen1":
        is_win, mult = (1 <= number <= 12), 2.85
    elif req.bet_type == "dozen2":
        is_win, mult = (13 <= number <= 24), 2.85
    elif req.bet_type == "dozen3":
        is_win, mult = (25 <= number <= 36), 2.85

    raw_win = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "roulette")
    return {
        "number": number,
        "color": color,
        "is_win": is_win,
        "multiplier": mult if is_win else 0.0,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 7. КОЛЕСО ФОРТУНЫ (12 секторов, RTP 93.3%)
# =========================================================
WHEEL_SECTORS = [0.0, 1.5, 0.0, 2.0, 0.5, 0.0, 1.2, 0.0, 2.5, 0.0, 0.5, 3.0]


@app.post("/api/play/wheel")
async def play_wheel(req: BetRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    sector_index = secrets.randbelow(len(WHEEL_SECTORS))
    mult = WHEEL_SECTORS[sector_index]
    raw_win = int(round(bet_cents * mult))
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "wheel")
    return {
        "sector_index": sector_index,
        "multiplier": mult,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 8. КАРТЫ HI-LO (серверная карта в БД, RTP ~90%)
# =========================================================
@app.post("/api/play/hilo")
async def play_hilo(req: HiloRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=45, window_sec=10.0)
    bet_cents = validate_bet_cents(req.bet)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            u_row = await conn.fetchrow(
                "SELECT balance_cents, hilo_card FROM users WHERE user_id = $1 FOR UPDATE",
                uid,
            )
            if not u_row or int(u_row["balance_cents"]) < bet_cents:
                raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Кассе!")

            current_card = int(u_row["hilo_card"] or 7)
            if current_card < 2 or current_card > 14:
                current_card = 7

            count = (14 - current_card) if req.guess == "high" else (current_card - 2)
            if count <= 0:
                raise HTTPException(status_code=400, detail="Невозможный выбор для этой карты")

            mult = max(1.03, round(11.7 / count, 2))
            next_card = secrets.randbelow(13) + 2
            is_win = (next_card > current_card) if req.guess == "high" else (next_card < current_card)
            win_cents = cap_win(int(round(bet_cents * mult))) if is_win else 0

            updated = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1 + $2,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1,
                    total_won_cents = total_won_cents + $2,
                    hilo_card = $3
                WHERE user_id = $4
                RETURNING balance_cents
                """,
                bet_cents, win_cents, next_card, uid,
            )
            new_bal_cents = int(updated["balance_cents"])
            await db.log_transaction(
                conn,
                uid,
                "play_hilo",
                win_cents - bet_cents,
                new_bal_cents,
                f"cur={current_card}:next={next_card}:bet={bet_cents}:win={win_cents}",
            )

    return {
        "previous_card": current_card,
        "next_card": next_card,
        "is_win": is_win,
        "win": to_dollars(win_cents),
        "multiplier": mult,
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 9. ПЛИНКО (8 рядов, 3 уровня риска, RTP 92–93%)
# =========================================================
PLINKO_BUCKETS = {
    "low": [4.0, 1.8, 1.1, 0.85, 0.6, 0.85, 1.1, 1.8, 4.0],
    "medium": [10.0, 3.0, 1.4, 0.6, 0.35, 0.6, 1.4, 3.0, 10.0],
    "high": [22.0, 4.5, 1.3, 0.3, 0.2, 0.3, 1.3, 4.5, 22.0],
}


@app.post("/api/play/plinko")
async def play_plinko(req: PlinkoRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    balls = req.balls
    total_bet_cents = bet_cents * balls
    if total_bet_cents > MAX_BET_CENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Сумма ({balls} × ${to_dollars(bet_cents):.2f} = ${to_dollars(total_bet_cents):.2f}) превышает лимит ${MAX_BET_USD:.2f}",
        )

    buckets_cfg = PLINKO_BUCKETS[req.risk]
    drops = []
    remaining_cap = MAX_WIN_CENTS
    total_win_cents = 0

    for _ in range(balls):
        path = [secrets.randbelow(2) for _ in range(8)]  # 0 = лево, 1 = право
        bucket = sum(path)
        mult = buckets_cfg[bucket]
        raw_win = int(round(bet_cents * mult))
        drop_win_cents = min(raw_win, remaining_cap)
        remaining_cap = max(0, remaining_cap - drop_win_cents)
        total_win_cents += drop_win_cents
        drops.append({
            "path": path,
            "bucket": bucket,
            "multiplier": mult,
            "win": to_dollars(drop_win_cents),
        })

    new_bal_cents, settled_win_cents = await settle_instant_game(
        user["user_id"], total_bet_cents, total_win_cents, "plinko", games_inc=balls
    )
    first = drops[0]
    return {
        "balls": balls,
        "risk": req.risk,
        "bet_per_ball": to_dollars(bet_cents),
        "total_bet": to_dollars(total_bet_cents),
        "total_win": to_dollars(settled_win_cents),
        "drops": drops,
        # Обратная совместимость для одиночного броска
        "path": first["path"],
        "bucket": first["bucket"],
        "multiplier": first["multiplier"],
        "win": to_dollars(settled_win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 10. БАШНЯ / TOWER (8 этажей, RTP 94%)
# =========================================================
@app.post("/api/play/tower/start")
async def tower_start(req: TowerStartRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=45, window_sec=10.0)
    bet_cents = validate_bet_cents(req.bet)
    cols, traps_per_floor = TOWER_CFG[req.difficulty]

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            u_lock = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1 FOR UPDATE", uid)
            if not u_lock or int(u_lock["balance_cents"]) < bet_cents:
                raise HTTPException(status_code=400, detail="Недостаточно средств")

            existing = await conn.fetchrow(
                "SELECT active FROM tower_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if existing:
                raise HTTPException(status_code=400, detail="Завершите текущую игру в Башне")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2
                RETURNING balance_cents
                """,
                bet_cents,
                uid,
            )
            new_bal_cents = int(row["balance_cents"])
            await db.log_transaction(conn, uid, "tower_bet", -bet_cents, new_bal_cents, f"diff={req.difficulty}")

            traps = []
            for _ in range(TOWER_FLOORS):
                c_list = list(range(cols))
                floor_traps = [c_list.pop(secrets.randbelow(len(c_list))) for _ in range(traps_per_floor)]
                traps.append(floor_traps)

            await conn.execute(
                """
                INSERT INTO tower_games (user_id, bet_cents, difficulty, traps, floor, active)
                VALUES ($1, $2, $3, $4, 0, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    bet_cents = EXCLUDED.bet_cents,
                    difficulty = EXCLUDED.difficulty,
                    traps = EXCLUDED.traps,
                    floor = 0,
                    active = 1
                """,
                uid, bet_cents, req.difficulty, json.dumps(traps),
            )
    return {
        "balance": to_dollars(new_bal_cents),
        "bet": to_dollars(bet_cents),
        "difficulty": req.difficulty,
        "cols": cols,
    }


@app.post("/api/play/tower/climb")
async def tower_climb(req: TowerClimbRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=60, window_sec=10.0)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM tower_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры в Башне")

            cols, _ = TOWER_CFG[game["difficulty"]]
            col = secrets.randbelow(cols) if req.col == -1 else req.col
            if col < 0 or col >= cols:
                raise HTTPException(status_code=400, detail="Некорректная ячейка")

            traps = json.loads(game["traps"])
            floor = int(game["floor"])

            if col in traps[floor]:
                await conn.execute("UPDATE tower_games SET active = 0 WHERE user_id = $1", uid)
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", uid)
                return {
                    "status": "boom",
                    "floor": floor,
                    "col": col,
                    "traps": traps,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            next_floor = floor + 1
            mult = tower_multiplier(game["difficulty"], next_floor)
            pot_cents = cap_win(int(round(game["bet_cents"] * mult)))

            if next_floor >= TOWER_FLOORS or pot_cents >= MAX_WIN_CENTS:
                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    pot_cents, uid,
                )
                new_bal = int(u_row["balance_cents"])
                await db.log_transaction(conn, uid, "tower_win", pot_cents, new_bal, f"floor={next_floor}:mult={mult}")
                await conn.execute("UPDATE tower_games SET active = 0, floor = $1 WHERE user_id = $2", next_floor, uid)
                return {
                    "status": "win_all",
                    "floor": next_floor,
                    "col": col,
                    "multiplier": mult,
                    "win": to_dollars(pot_cents),
                    "traps": traps,
                    "balance": to_dollars(new_bal),
                }

            await conn.execute("UPDATE tower_games SET floor = $1 WHERE user_id = $2", next_floor, uid)
            return {
                "status": "safe",
                "floor": next_floor,
                "col": col,
                "multiplier": mult,
                "potential_win": to_dollars(pot_cents),
            }


@app.post("/api/play/tower/cashout")
async def tower_cashout(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM tower_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры")
            floor = int(game["floor"])
            if floor <= 0:
                raise HTTPException(status_code=400, detail="Пройдите хотя бы первый этаж")

            traps = json.loads(game["traps"])
            mult = tower_multiplier(game["difficulty"], floor)
            win_cents = cap_win(int(round(game["bet_cents"] * mult)))
            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, uid,
            )
            new_bal = int(u_row["balance_cents"])
            await db.log_transaction(conn, uid, "tower_win", win_cents, new_bal, f"floor={floor}:mult={mult}")
            await conn.execute("UPDATE tower_games SET active = 0 WHERE user_id = $1", uid)
            return {
                "win": to_dollars(win_cents),
                "multiplier": mult,
                "traps": traps,
                "balance": to_dollars(new_bal),
            }


# =========================================================
# 11. ЛИМБО (RTP 94%)
# =========================================================
@app.post("/api/play/limbo")
async def play_limbo(req: LimboRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    result = draw_crash_point()
    is_win = result >= req.target
    raw_win = int(round(bet_cents * req.target)) if is_win else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "limbo")
    return {
        "result": result,
        "is_win": is_win,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 12. КЕНО (5x5, выбор 1–8 чисел, исправленный RTP 91.2%–93.5%)
# =========================================================
KENO_PAYOUTS = {
    1: {1: 2.85},
    2: {1: 0.5, 2: 7.4},
    3: {2: 2.5, 3: 16.5},
    4: {2: 1.5, 3: 4.5, 4: 25.0},
    5: {2: 0.65, 3: 2.6, 4: 11.5, 5: 48.0},
    6: {2: 0.25, 3: 1.75, 4: 5.8, 5: 23.0, 6: 90.0},
    7: {3: 1.2, 4: 3.4, 5: 12.5, 6: 50.0, 7: 160.0},
    8: {3: 0.85, 4: 2.2, 5: 6.5, 6: 24.0, 7: 80.0, 8: 250.0},
}


@app.post("/api/play/keno")
async def play_keno(req: KenoRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    picks = sorted(set(req.picks))
    if len(picks) != len(req.picks) or any(p < 1 or p > 25 for p in picks):
        raise HTTPException(status_code=400, detail="Выберите от 1 до 8 уникальных чисел (1–25)")

    pool_nums = list(range(1, 26))
    drawn = sorted([pool_nums.pop(secrets.randbelow(len(pool_nums))) for _ in range(8)])
    hits = sorted(set(picks) & set(drawn))
    mult = KENO_PAYOUTS[len(picks)].get(len(hits), 0.0)
    raw_win = int(round(bet_cents * mult))
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "keno")
    return {
        "drawn": drawn,
        "hits": hits,
        "multiplier": mult,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 13. КЕЙСЫ (RTP ~90.8%, с проверкой MAX_BET_USD)
# =========================================================
CASE_PRICES = {"bronze": 100, "silver": 500, "gold": 2000, "royal": 5000}
CASE_ITEMS = [
    {"label": "0.2x", "mult": 0.2, "weight": 400, "rarity": "common", "icon": "🪙"},
    {"label": "0.5x", "mult": 0.5, "weight": 260, "rarity": "common", "icon": "💵"},
    {"label": "1.0x", "mult": 1.0, "weight": 150, "rarity": "uncommon", "icon": "💰"},
    {"label": "1.5x", "mult": 1.5, "weight": 90, "rarity": "rare", "icon": "💍"},
    {"label": "2.5x", "mult": 2.5, "weight": 55, "rarity": "epic", "icon": "💎"},
    {"label": "5.0x", "mult": 5.0, "weight": 35, "rarity": "legendary", "icon": "👑"},
    {"label": "10.0x", "mult": 10.0, "weight": 10, "rarity": "mythic", "icon": "🏆"},
]


@app.post("/api/play/cases")
async def play_cases(req: CasesRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(to_dollars(CASE_PRICES[req.tier]))
    roll = secrets.randbelow(1000)
    acc = 0
    picked = CASE_ITEMS[0]
    for item in CASE_ITEMS:
        acc += item["weight"]
        if roll < acc:
            picked = item
            break

    raw_win = int(round(bet_cents * picked["mult"]))
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "cases")
    return {
        "tier": req.tier,
        "cost": to_dollars(bet_cents),
        "item": picked,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 14. БЛЭКДЖЕК 21
# =========================================================
BJ_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
BJ_SUITS = ["♠️", "♥️", "♦️", "♣️"]


def make_bj_deck() -> list[str]:
    deck = [f"{r}{s}" for r in BJ_RANKS for s in BJ_SUITS]
    for i in range(len(deck) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        deck[i], deck[j] = deck[j], deck[i]
    return deck


def bj_score(hand: list[str]) -> int:
    total = 0
    aces = 0
    for c in hand:
        rank = parse_card_rank(c)
        if rank in ("J", "Q", "K", "10"):
            total += 10
        elif rank == "A":
            total += 11
            aces += 1
        else:
            total += int(rank)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


@app.post("/api/play/blackjack/start")
async def blackjack_start(req: BetRequest, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=45, window_sec=10.0)
    bet_cents = validate_bet_cents(req.bet)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            u_lock = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1 FOR UPDATE", uid)
            if not u_lock or int(u_lock["balance_cents"]) < bet_cents:
                raise HTTPException(status_code=400, detail="Недостаточно средств")

            existing = await conn.fetchrow(
                "SELECT active FROM blackjack_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if existing:
                raise HTTPException(status_code=400, detail="Завершите текущую раздачу Блэкджека")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2
                RETURNING balance_cents
                """,
                bet_cents,
                uid,
            )
            bal_cents = int(row["balance_cents"])
            await db.log_transaction(conn, uid, "bj_bet", -bet_cents, bal_cents)

            deck = make_bj_deck()
            p_hand = [deck.pop(), deck.pop()]
            d_hand = [deck.pop(), deck.pop()]
            p_sc = bj_score(p_hand)
            d_sc = bj_score(d_hand)

            if p_sc == 21 or d_sc == 21:
                if p_sc == 21 and d_sc == 21:
                    win_cents = bet_cents
                    outcome = "push"
                elif p_sc == 21:
                    win_cents = cap_win(int(round(bet_cents * 2.4)))
                    outcome = "blackjack"
                else:
                    win_cents = 0
                    outcome = "lose"

                if win_cents > 0:
                    u_row = await conn.fetchrow(
                        "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                        win_cents, uid,
                    )
                    new_bal = int(u_row["balance_cents"])
                    await db.log_transaction(conn, uid, f"bj_{outcome}", win_cents, new_bal)
                else:
                    new_bal = bal_cents
                return {
                    "status": "finished",
                    "outcome": outcome,
                    "player_hand": p_hand,
                    "player_score": p_sc,
                    "dealer_hand": d_hand,
                    "dealer_score": d_sc,
                    "win": to_dollars(win_cents),
                    "balance": to_dollars(new_bal),
                }

            await conn.execute(
                """
                INSERT INTO blackjack_games (user_id, bet_cents, deck, player_hand, dealer_hand, active)
                VALUES ($1, $2, $3, $4, $5, 1)
                ON CONFLICT (user_id) DO UPDATE SET
                    bet_cents = EXCLUDED.bet_cents,
                    deck = EXCLUDED.deck,
                    player_hand = EXCLUDED.player_hand,
                    dealer_hand = EXCLUDED.dealer_hand,
                    active = 1
                """,
                uid, bet_cents, json.dumps(deck), json.dumps(p_hand), json.dumps(d_hand),
            )
    return {
        "status": "playing",
        "player_hand": p_hand,
        "player_score": p_sc,
        "dealer_visible": [d_hand[0], "🂠"],
        "dealer_visible_score": bj_score([d_hand[0]]),
        "balance": to_dollars(bal_cents),
    }


@app.post("/api/play/blackjack/hit")
async def blackjack_hit(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    check_rate_limit("play", uid, limit=60, window_sec=10.0)

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM blackjack_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры в Блэкджек")

            deck = json.loads(game["deck"])
            p_hand = json.loads(game["player_hand"])
            d_hand = json.loads(game["dealer_hand"])
            p_hand.append(deck.pop())
            p_sc = bj_score(p_hand)

            if p_sc > 21:
                await conn.execute("UPDATE blackjack_games SET active = 0 WHERE user_id = $1", uid)
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", uid)
                return {
                    "status": "finished",
                    "outcome": "bust",
                    "player_hand": p_hand,
                    "player_score": p_sc,
                    "dealer_hand": d_hand,
                    "dealer_score": bj_score(d_hand),
                    "win": 0.0,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            if p_sc == 21:
                while bj_score(d_hand) < 17:
                    d_hand.append(deck.pop())
                d_sc = bj_score(d_hand)
                dealer_natural = (len(d_hand) == 2 and d_sc == 21)
                if dealer_natural:
                    win_cents, outcome = 0, "lose"
                elif d_sc > 21 or p_sc > d_sc:
                    win_cents, outcome = cap_win(int(round(game["bet_cents"] * 1.95))), "win"
                elif p_sc == d_sc:
                    win_cents, outcome = int(game["bet_cents"]), "push"
                else:
                    win_cents, outcome = 0, "lose"

                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    win_cents, uid,
                )
                new_bal = int(u_row["balance_cents"])
                if win_cents > 0:
                    await db.log_transaction(conn, uid, f"bj_{outcome}", win_cents, new_bal)
                await conn.execute("UPDATE blackjack_games SET active = 0 WHERE user_id = $1", uid)
                return {
                    "status": "finished",
                    "outcome": outcome,
                    "player_hand": p_hand,
                    "player_score": p_sc,
                    "dealer_hand": d_hand,
                    "dealer_score": d_sc,
                    "win": to_dollars(win_cents),
                    "balance": to_dollars(new_bal),
                }

            await conn.execute(
                "UPDATE blackjack_games SET deck = $1, player_hand = $2 WHERE user_id = $3",
                json.dumps(deck), json.dumps(p_hand), uid,
            )
            return {
                "status": "playing",
                "player_hand": p_hand,
                "player_score": p_sc,
                "dealer_visible": [d_hand[0], "🂠"],
                "dealer_visible_score": bj_score([d_hand[0]]),
            }


@app.post("/api/play/blackjack/stand")
async def blackjack_stand(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM blackjack_games WHERE user_id = $1 AND active = 1 FOR UPDATE", uid
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры в Блэкджек")

            deck = json.loads(game["deck"])
            p_hand = json.loads(game["player_hand"])
            d_hand = json.loads(game["dealer_hand"])
            while bj_score(d_hand) < 17:
                d_hand.append(deck.pop())

            p_sc = bj_score(p_hand)
            d_sc = bj_score(d_hand)
            dealer_natural = (len(d_hand) == 2 and d_sc == 21)
            if dealer_natural and not (len(p_hand) == 2 and p_sc == 21):
                win_cents, outcome = 0, "lose"
            elif d_sc > 21 or p_sc > d_sc:
                win_cents, outcome = cap_win(int(round(game["bet_cents"] * 1.95))), "win"
            elif p_sc == d_sc:
                win_cents, outcome = int(game["bet_cents"]), "push"
            else:
                win_cents, outcome = 0, "lose"

            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, uid,
            )
            new_bal = int(u_row["balance_cents"])
            if win_cents > 0:
                await db.log_transaction(conn, uid, f"bj_{outcome}", win_cents, new_bal)
            await conn.execute("UPDATE blackjack_games SET active = 0 WHERE user_id = $1", uid)
            return {
                "status": "finished",
                "outcome": outcome,
                "player_hand": p_hand,
                "player_score": p_sc,
                "dealer_hand": d_hand,
                "dealer_score": d_sc,
                "win": to_dollars(win_cents),
                "balance": to_dollars(new_bal),
            }


# =========================================================
# 15. БАККАРА
# =========================================================
def bac_val(card: str) -> int:
    rank = parse_card_rank(card)
    if rank in ("10", "J", "Q", "K"):
        return 0
    return 1 if rank == "A" else int(rank)


@app.post("/api/play/baccarat")
async def play_baccarat(req: BaccaratRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    deck = make_bj_deck()
    p_cards = [deck.pop(), deck.pop()]
    b_cards = [deck.pop(), deck.pop()]
    p_sc = sum(bac_val(c) for c in p_cards) % 10
    b_sc = sum(bac_val(c) for c in b_cards) % 10

    if p_sc < 8 and b_sc < 8:
        p_third = None
        if p_sc <= 5:
            p_third = deck.pop()
            p_cards.append(p_third)
            p_sc = sum(bac_val(c) for c in p_cards) % 10
        if p_third is None:
            if b_sc <= 5:
                b_cards.append(deck.pop())
        else:
            tv = bac_val(p_third)
            draw_b = (
                b_sc <= 2
                or (b_sc == 3 and tv != 8)
                or (b_sc == 4 and tv in (2, 3, 4, 5, 6, 7))
                or (b_sc == 5 and tv in (4, 5, 6, 7))
                or (b_sc == 6 and tv in (6, 7))
            )
            if draw_b:
                b_cards.append(deck.pop())
        b_sc = sum(bac_val(c) for c in b_cards) % 10

    winner = "player" if p_sc > b_sc else ("banker" if b_sc > p_sc else "tie")
    mults = {"player": 1.95, "banker": 1.90, "tie": 8.0}
    raw_win = int(round(bet_cents * mults[winner])) if req.choice == winner else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "baccarat")
    return {
        "player_cards": p_cards,
        "banker_cards": b_cards,
        "player_score": p_sc,
        "banker_score": b_sc,
        "winner": winner,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 16. НАПЁРСТКИ (RTP 93.3%)
# =========================================================
@app.post("/api/play/thimbles")
async def play_thimbles(req: ThimblesRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    cups = [0, 1, 2]
    ball_positions = [cups.pop(secrets.randbelow(len(cups))) for _ in range(req.balls)]
    is_win = req.cup in ball_positions
    mult = 2.80 if req.balls == 1 else 1.40
    raw_win = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "thimbles")
    return {
        "ball_positions": ball_positions,
        "is_win": is_win,
        "multiplier": mult if is_win else 0.0,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 17. КАМЕНЬ-НОЖНИЦЫ-БУМАГА (RTP 95%)
# =========================================================
@app.post("/api/play/rps")
async def play_rps(req: RpsRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    bot_choice = secrets.choice(["rock", "paper", "scissors"])
    wins = {("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")}
    if req.choice == bot_choice:
        outcome, mult = "draw", 1.0
    elif (req.choice, bot_choice) in wins:
        outcome, mult = "win", 1.85
    else:
        outcome, mult = "lose", 0.0

    raw_win = int(round(bet_cents * mult))
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "rps")
    return {
        "bot_choice": bot_choice,
        "outcome": outcome,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 18. ПЕНАЛЬТИ (RTP 92–93%)
# =========================================================
@app.post("/api/play/penalty")
async def play_penalty(req: PenaltyRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    zones = [0, 1, 2, 3, 4]
    blocks = 2 if req.difficulty == "normal" else 3
    keeper_zones = [zones.pop(secrets.randbelow(len(zones))) for _ in range(blocks)]
    is_goal = req.zone not in keeper_zones
    mult = 1.55 if req.difficulty == "normal" else 2.30
    raw_win = int(round(bet_cents * mult)) if is_goal else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "penalty")
    return {
        "keeper_zones": keeper_zones,
        "is_goal": is_goal,
        "multiplier": mult if is_goal else 0.0,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 19. СКРЕТЧ-КАРТА (3x3, RTP 91.7%)
# =========================================================
SCRATCH_OUTCOMES = [
    (620, None, 0.0),
    (160, "🍋", 1.2),
    (110, "🍒", 2.0),
    (60, "🔔", 3.0),
    (35, "💎", 5.0),
    (15, "👑", 10.0),
]
SCRATCH_FILLERS = ["🍋", "🍒", "🔔", "💎", "👑", "🍀"]


@app.post("/api/play/scratch")
async def play_scratch(req: BetRequest, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    roll = secrets.randbelow(1000)
    acc = 0
    win_sym, mult = None, 0.0
    for w, sym, m in SCRATCH_OUTCOMES:
        acc += w
        if roll < acc:
            win_sym, mult = sym, m
            break

    grid = []
    if win_sym:
        grid.extend([win_sym] * 3)
        others = [s for s in SCRATCH_FILLERS if s != win_sym]
        pool = []
        for s in others:
            pool.extend([s, s])
        for _ in range(6):
            grid.append(pool.pop(secrets.randbelow(len(pool))))
    else:
        pool = []
        for s in SCRATCH_FILLERS:
            pool.extend([s, s])
        for _ in range(9):
            grid.append(pool.pop(secrets.randbelow(len(pool))))

    for i in range(len(grid) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        grid[i], grid[j] = grid[j], grid[i]

    raw_win = int(round(bet_cents * mult))
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "scratch")
    return {
        "grid": grid,
        "win_symbol": win_sym,
        "multiplier": mult,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 20. 2 КУБИКА / БОЛЬШЕ-МЕНЬШЕ 7 (RTP 91.7%)
# =========================================================
@app.post("/api/play/dice7")
async def play_dice7(req: Dice7Request, user: dict = Depends(get_current_user)):
    bet_cents = validate_bet_cents(req.bet)
    d1 = secrets.randbelow(6) + 1
    d2 = secrets.randbelow(6) + 1
    total = d1 + d2

    if req.choice == "under":
        is_win, mult = (total < 7), 2.20
    elif req.choice == "over":
        is_win, mult = (total > 7), 2.20
    elif req.choice == "exact7":
        is_win, mult = (total == 7), 5.50
    else:
        is_win, mult = (d1 == d2), 5.50

    raw_win = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents, win_cents = await settle_instant_game(user["user_id"], bet_cents, raw_win, "dice7")
    return {
        "d1": d1,
        "d2": d2,
        "total": total,
        "is_win": is_win,
        "multiplier": mult if is_win else 0.0,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# АДМИН-ПАНЕЛЬ (расширенная статистика + атомарные правки)
# =========================================================
def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not ADMIN_ID or user["user_id"] != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Доступ только для администратора")
    return user


class AdminBalanceRequest(BaseModel):
    target_user_id: int = Field(gt=0)
    amount: float = Field(ge=0, le=1000000)
    mode: str = Field(pattern="^(add|sub|set)$")


class AdminWithdrawHandleRequest(BaseModel):
    wd_id: int = Field(gt=0)
    action: str = Field(pattern="^(approve|reject)$")


@app.get("/api/admin/overview")
async def admin_overview(admin: dict = Depends(require_admin)):
    async with db.pool.acquire() as conn:
        st = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS users_count,
                COALESCE(SUM(balance_cents), 0) AS total_balance_cents,
                COALESCE(SUM(games_played), 0) AS total_games,
                COALESCE(SUM(total_wagered_cents), 0) AS total_wagered_cents,
                COALESCE(SUM(total_won_cents), 0) AS total_won_cents
            FROM users
            """
        )
        pay = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(stars), 0) AS total_stars,
                COALESCE(SUM(amount_cents), 0) AS total_dep_cents
            FROM payments
            """
        )
        wd_st = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status = 'approved' THEN amount_cents ELSE 0 END), 0) AS approved_cents,
                COALESCE(SUM(CASE WHEN status = 'pending' THEN amount_cents ELSE 0 END), 0) AS pending_cents
            FROM withdrawals
            """
        )
        pending = await conn.fetch(
            "SELECT id, user_id, username, amount_cents, details, status FROM withdrawals WHERE status = 'pending' ORDER BY id DESC LIMIT 30"
        )
        users = await conn.fetch(
            "SELECT user_id, username, balance_cents, games_played, total_won_cents FROM users ORDER BY balance_cents DESC LIMIT 50"
        )

    wagered = int(st["total_wagered_cents"])
    won = int(st["total_won_cents"])
    return {
        "stats": {
            "users_count": st["users_count"],
            "total_balance": to_dollars(st["total_balance_cents"]),
            "total_games": st["total_games"],
            "total_wagered": to_dollars(wagered),
            "total_won": to_dollars(won),
            "house_profit": to_dollars(wagered - won),
            "total_stars": int(pay["total_stars"]),
            "total_deposited": to_dollars(pay["total_dep_cents"]),
            "total_withdrawn": to_dollars(wd_st["approved_cents"]),
            "pending_withdraw_sum": to_dollars(wd_st["pending_cents"]),
        },
        "pending_withdrawals": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "username": r["username"],
                "amount": to_dollars(r["amount_cents"]),
                "details": r["details"],
                "status": r["status"],
            }
            for r in pending
        ],
        "users": [
            {
                "user_id": r["user_id"],
                "username": r["username"],
                "balance": to_dollars(r["balance_cents"]),
                "games_played": r["games_played"],
                "total_won": to_dollars(r["total_won_cents"]),
            }
            for r in users
        ],
    }


@app.post("/api/admin/balance")
async def admin_change_balance(req: AdminBalanceRequest, admin: dict = Depends(require_admin)):
    amount_cents = to_cents(req.amount)
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT balance_cents FROM users WHERE user_id = $1 FOR UPDATE",
                req.target_user_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Игрок с таким ID не найден в базе")

            cur = int(row["balance_cents"])
            if req.mode == "add":
                new_bal_cents = cur + amount_cents
            elif req.mode == "sub":
                new_bal_cents = max(0, cur - amount_cents)
            else:
                new_bal_cents = amount_cents

            delta = new_bal_cents - cur
            await conn.execute(
                "UPDATE users SET balance_cents = $1 WHERE user_id = $2",
                new_bal_cents,
                req.target_user_id,
            )
            await db.log_transaction(
                conn,
                req.target_user_id,
                f"admin_{req.mode}",
                delta,
                new_bal_cents,
                f"by_admin:{admin['user_id']}",
            )

    return {"user_id": req.target_user_id, "balance": to_dollars(new_bal_cents)}


@app.post("/api/admin/withdraw/handle")
async def admin_handle_withdraw(req: AdminWithdrawHandleRequest, admin: dict = Depends(require_admin)):
    res = await db.handle_withdrawal_decision(req.wd_id, req.action)
    if not res["ok"]:
        raise HTTPException(status_code=res["code"], detail=res["error"])

    await send_tg_message(res["user_id"], res["user_msg"])
    return {"ok": True, "wd_id": req.wd_id, "action": req.action}
