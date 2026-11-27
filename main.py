import hashlib
import hmac
import json
import math
import os
import secrets
import time
import urllib.request
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
STARS_TO_CENTS = 1  # 100 Stars = 100 cents ($1.00)
CRASH_SPEED = 0.12  # mult(t) = exp(0.12 * t)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


app = FastAPI(title="T Casino Mini App v2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


def to_cents(dollars: float) -> int:
    return int(round(dollars * 100))


def to_dollars(cents: int) -> float:
    return round(cents / 100.0, 2)


def send_tg_message(chat_id: int, text: str, reply_markup: dict | None = None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = {"chat_id": chat_id, "text": text}
    if reply_markup:
        body["reply_markup"] = reply_markup
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception:
        pass


def notify_admin_withdrawal(wd_id: int, user_id: int, username: str, amount_cents: int, details: str):
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
    send_tg_message(ADMIN_ID, text, reply_markup=markup)


# --- Авторизация Telegram WebApp ---
def verify_telegram_init_data(init_data: str) -> dict:
    parsed = dict(parse_qsl(init_data, strict_parsing=True))
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

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Missing user data")
    return json.loads(user_raw)


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
            await conn.execute(
                """
                INSERT INTO users (user_id, username, balance_cents, games_played, total_wagered_cents, total_won_cents)
                VALUES ($1, $2, 0, 0, 0, 0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id, username,
            )
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        elif row["username"] != username:
            await conn.execute("UPDATE users SET username = $1 WHERE user_id = $2", username, user_id)
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row)


async def settle_instant_game(user_id: int, bet_cents: int, win_cents: int) -> int:
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET balance_cents = balance_cents - $1 + $2,
                games_played = games_played + 1,
                total_wagered_cents = total_wagered_cents + $1,
                total_won_cents = total_won_cents + $2
            WHERE user_id = $3 AND balance_cents >= $1
            RETURNING balance_cents
            """,
            bet_cents, win_cents, user_id,
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Кассе!")
        return int(row["balance_cents"])


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


# --- Модели запросов ---
class BetRequest(BaseModel):
    bet: float = Field(gt=0, le=100000)


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
    current_card: int = Field(ge=2, le=14)
    guess: str = Field(pattern="^(high|low)$")


class PlinkoRequest(BetRequest):
    risk: str = Field(default="medium", pattern="^(low|medium|high)$")


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
@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/api/me")
async def api_me(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    async with db.pool.acquire() as conn:
        mines_row = await conn.fetchrow("SELECT * FROM mines_games WHERE user_id = $1 AND active = 1", uid)
        crash_row = await conn.fetchrow("SELECT * FROM crash_games WHERE user_id = $1 AND active = 1", uid)
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
        active_mines = {
            "bet": to_dollars(mines_row["bet_cents"]),
            "mines_count": mines_row["mines_count"],
            "revealed": revealed,
            "multiplier": mult,
            "potential_win": to_dollars(int(round(mines_row["bet_cents"] * mult))),
        }

    active_crash = None
    if crash_row:
        now_mult = crash_current_mult(crash_row["started_at"])
        if now_mult < crash_row["crash_point"]:
            active_crash = {
                "bet": to_dollars(crash_row["bet_cents"]),
                "auto_cashout": crash_row["auto_cashout"],
                "started_at": crash_row["started_at"],
                "multiplier": now_mult,
            }
        else:
            async with db.pool.acquire() as conn:
                await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", uid)

    active_tower = None
    if tower_row:
        mult = tower_multiplier(tower_row["difficulty"], tower_row["floor"])
        active_tower = {
            "bet": to_dollars(tower_row["bet_cents"]),
            "difficulty": tower_row["difficulty"],
            "floor": tower_row["floor"],
            "multiplier": mult,
            "potential_win": to_dollars(int(round(tower_row["bet_cents"] * mult))),
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

    return {
        "user_id": uid,
        "username": user["username"],
        "balance": to_dollars(user["balance_cents"]),
        "games_played": user["games_played"],
        "total_won": to_dollars(user["total_won_cents"]),
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
async def api_leaderboard():
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT username, total_won_cents, games_played, balance_cents
            FROM users
            WHERE games_played > 0 OR total_won_cents > 0
            ORDER BY total_won_cents DESC, balance_cents DESC
            LIMIT 15
            """
        )
    return {
        "leaders": [
            {
                "username": r["username"] or "Игрок",
                "total_won": to_dollars(r["total_won_cents"]),
                "games_played": r["games_played"],
                "balance": to_dollars(r["balance_cents"]),
            }
            for r in rows
        ]
    }


@app.post("/api/withdraw")
async def api_withdraw(req: WithdrawRequest, user: dict = Depends(get_current_user)):
    amount_cents = to_cents(req.amount)
    details = req.details.strip()
    if amount_cents < 100:
        raise HTTPException(status_code=400, detail="Минимальная сумма вывода — $1.00")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents - $1 WHERE user_id = $2 AND balance_cents >= $1 RETURNING balance_cents",
                amount_cents, user["user_id"],
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств на балансе")

            wd_row = await conn.fetchrow(
                "INSERT INTO withdrawals (user_id, username, amount_cents, details, status) VALUES ($1, $2, $3, $4, 'pending') RETURNING id",
                user["user_id"], user["username"], amount_cents, details,
            )
            wd_id = wd_row["id"]
            new_bal_cents = row["balance_cents"]

    notify_admin_withdrawal(wd_id, user["user_id"], user["username"], amount_cents, details)
    return {"id": wd_id, "balance": to_dollars(new_bal_cents), "status": "pending"}


@app.post("/api/stars/invoice")
def create_stars_invoice(req: StarsInvoiceRequest, user: dict = Depends(get_current_user)):
    amount_cents = req.stars * STARS_TO_CENTS
    usd = to_dollars(amount_cents)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink"
    payload = json.dumps({
        "title": f"Пополнение T Casino: ${usd:.2f}",
        "description": f"Зачисление ${usd:.2f} на баланс за {req.stars} Telegram Stars",
        "payload": f"topup:{user['user_id']}:{req.stars}",
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": f"${usd:.2f}", "amount": req.stars}],
    }).encode("utf-8")

    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                raise HTTPException(status_code=500, detail=data.get("description", "Telegram API error"))
            return {"invoice_url": data["result"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания счёта: {e}")


# =========================================================
# 1. СЛОТЫ (RTP ~90.5%)
# =========================================================
SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]


@app.post("/api/play/slots")
async def play_slots(req: BetRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    reels = [secrets.choice(SLOT_SYMBOLS) for _ in range(3)]
    mult = 0.0
    if reels[0] == reels[1] == reels[2]:
        mult = 20.0 if reels[0] == "7️⃣" else (12.0 if reels[0] == "💎" else 6.0)
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        mult = 1.55

    win_cents = int(round(bet_cents * mult))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {"reels": reels, "multiplier": mult, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# =========================================================
# 2. МИНЫ (RTP 94%, авто-клетка, показ бомб после победы)
# =========================================================
@app.post("/api/play/mines/start")
async def mines_start(req: MinesStartRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT active FROM mines_games WHERE user_id = $1 AND active = 1", user["user_id"]
            )
            if existing:
                raise HTTPException(status_code=400, detail="Завершите текущую игру в Мины")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2 AND balance_cents >= $1
                RETURNING balance_cents
                """,
                bet_cents, user["user_id"],
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Кассе!")
            new_bal_cents = int(row["balance_cents"])

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
                user["user_id"], bet_cents, req.mines_count, json.dumps(mines), json.dumps([]),
            )
    return {"balance": to_dollars(new_bal_cents), "bet": to_dollars(bet_cents), "mines_count": req.mines_count}


@app.post("/api/play/mines/reveal")
async def mines_reveal(req: MinesRevealRequest, user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM mines_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
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
                await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", user["user_id"])
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", user["user_id"])
                return {
                    "status": "boom",
                    "cell": cell,
                    "mines": mines,
                    "revealed": revealed,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            revealed.append(cell)
            mult = mines_multiplier(game["mines_count"], len(revealed))
            potential_cents = int(round(game["bet_cents"] * mult))

            if len(revealed) == 25 - game["mines_count"]:
                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    potential_cents, user["user_id"],
                )
                await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", user["user_id"])
                return {
                    "status": "win_all",
                    "cell": cell,
                    "multiplier": mult,
                    "win": to_dollars(potential_cents),
                    "mines": mines,
                    "revealed": revealed,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            await conn.execute("UPDATE mines_games SET revealed = $1 WHERE user_id = $2", json.dumps(revealed), user["user_id"])
            return {
                "status": "safe",
                "cell": cell,
                "multiplier": mult,
                "potential_win": to_dollars(potential_cents),
                "revealed": revealed,
            }


@app.post("/api/play/mines/cashout")
async def mines_cashout(user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM mines_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры")

            revealed = json.loads(game["revealed"])
            if len(revealed) == 0:
                raise HTTPException(status_code=400, detail="Откройте хотя бы одну клетку")

            mines = json.loads(game["mines_positions"])
            mult = mines_multiplier(game["mines_count"], len(revealed))
            win_cents = int(round(game["bet_cents"] * mult))

            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, user["user_id"],
            )
            await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", user["user_id"])
            new_bal_cents = int(u_row["balance_cents"])

    return {
        "win": to_dollars(win_cents),
        "multiplier": mult,
        "mines": mines,
        "revealed": revealed,
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 3. КОСТИ (нерф до 93% RTP, шанс 5–90%)
# =========================================================
@app.post("/api/play/dice")
async def play_dice(req: DiceRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    chance = (req.target - 1) if req.direction == "under" else (100 - req.target)
    if chance < 5 or chance > 90:
        raise HTTPException(status_code=400, detail="Допустимый шанс победы — от 5% до 90%")

    roll = secrets.randbelow(100) + 1
    is_win = (roll < req.target) if req.direction == "under" else (roll > req.target)
    multiplier = round(93.0 / chance, 2)
    win_cents = int(round(bet_cents * multiplier)) if is_win else 0

    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
    result = secrets.choice(["heads", "tails"])
    win_cents = int(round(bet_cents * 1.90)) if result == req.choice else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {"result": result, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# =========================================================
# 5. ЖИВОЙ КРАШ (RTP 94%, ручной и авто-вывод)
# =========================================================
@app.post("/api/play/crash/start")
async def crash_start(req: CrashStartRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if req.auto_cashout != 0.0 and req.auto_cashout < 1.05:
        raise HTTPException(status_code=400, detail="Авто-вывод должен быть от 1.05x (или 0 для отключения)")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
            )
            if existing:
                if crash_current_mult(existing["started_at"]) < existing["crash_point"]:
                    raise HTTPException(status_code=400, detail="Ракета уже в полёте!")
                await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", user["user_id"])

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2 AND balance_cents >= $1
                RETURNING balance_cents
                """,
                bet_cents, user["user_id"],
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств")
            new_bal_cents = int(row["balance_cents"])

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
                    user["user_id"], bet_cents, req.auto_cashout, now,
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
                user["user_id"], bet_cents, cp, req.auto_cashout, now,
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
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
            )
            if not game:
                return {"status": "idle"}

            now_mult = crash_current_mult(game["started_at"])
            auto_c = float(game["auto_cashout"] or 0.0)
            cp = float(game["crash_point"])

            if auto_c >= 1.05 and now_mult >= auto_c and auto_c <= cp:
                win_cents = int(round(game["bet_cents"] * auto_c))
                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    win_cents, user["user_id"],
                )
                await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", user["user_id"])
                return {
                    "status": "cashed_out",
                    "multiplier": auto_c,
                    "crash_point": cp,
                    "win": to_dollars(win_cents),
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            if now_mult >= cp:
                await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", user["user_id"])
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", user["user_id"])
                return {
                    "status": "crashed",
                    "multiplier": cp,
                    "crash_point": cp,
                    "win": 0.0,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            return {"status": "flying", "multiplier": now_mult}


@app.post("/api/play/crash/cashout")
async def crash_cashout(user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM crash_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активного полёта")

            now_mult = crash_current_mult(game["started_at"])
            auto_c = float(game["auto_cashout"] or 0.0)
            cp = float(game["crash_point"])

            if auto_c >= 1.05 and now_mult >= auto_c and auto_c <= cp:
                cash_mult = auto_c
            elif now_mult >= cp:
                await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", user["user_id"])
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", user["user_id"])
                return {
                    "status": "crashed",
                    "multiplier": cp,
                    "crash_point": cp,
                    "win": 0.0,
                    "balance": to_dollars(u_row["balance_cents"]),
                }
            else:
                cash_mult = max(1.01, now_mult)
                if cash_mult > cp:
                    cash_mult = cp

            win_cents = int(round(game["bet_cents"] * cash_mult))
            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, user["user_id"],
            )
            await conn.execute("UPDATE crash_games SET active = 0 WHERE user_id = $1", user["user_id"])
            return {
                "status": "cashed_out",
                "multiplier": cash_mult,
                "crash_point": cp,
                "win": to_dollars(win_cents),
                "balance": to_dollars(u_row["balance_cents"]),
            }


# =========================================================
# 6. ЕВРОПЕЙСКАЯ РУЛЕТКА (0–36, RTP 91.9%–94.9%)
# =========================================================
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


@app.post("/api/play/roulette")
async def play_roulette(req: RouletteRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
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

    win_cents = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
    sector_index = secrets.randbelow(len(WHEEL_SECTORS))
    mult = WHEEL_SECTORS[sector_index]
    win_cents = int(round(bet_cents * mult))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {
        "sector_index": sector_index,
        "multiplier": mult,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 8. КАРТЫ HI-LO (нерф до ~90% RTP)
# =========================================================
@app.post("/api/play/hilo")
async def play_hilo(req: HiloRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    count = (14 - req.current_card) if req.guess == "high" else (req.current_card - 2)
    if count <= 0:
        raise HTTPException(status_code=400, detail="Невозможный выбор для этой карты")

    mult = max(1.03, round(11.7 / count, 2))
    next_card = secrets.randbelow(13) + 2
    is_win = (next_card > req.current_card) if req.guess == "high" else (next_card < req.current_card)
    win_cents = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {
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
    bet_cents = to_cents(req.bet)
    path = [secrets.randbelow(2) for _ in range(8)]  # 0 = лево, 1 = право
    bucket = sum(path)
    mult = PLINKO_BUCKETS[req.risk][bucket]
    win_cents = int(round(bet_cents * mult))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {
        "path": path,
        "bucket": bucket,
        "multiplier": mult,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 10. БАШНЯ / TOWER (8 этажей, RTP 94%)
# =========================================================
@app.post("/api/play/tower/start")
async def tower_start(req: TowerStartRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    cols, traps_per_floor = TOWER_CFG[req.difficulty]

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT active FROM tower_games WHERE user_id = $1 AND active = 1", user["user_id"]
            )
            if existing:
                raise HTTPException(status_code=400, detail="Завершите текущую игру в Башне")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2 AND balance_cents >= $1
                RETURNING balance_cents
                """,
                bet_cents, user["user_id"],
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств")
            new_bal_cents = int(row["balance_cents"])

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
                user["user_id"], bet_cents, req.difficulty, json.dumps(traps),
            )
    return {
        "balance": to_dollars(new_bal_cents),
        "bet": to_dollars(bet_cents),
        "difficulty": req.difficulty,
        "cols": cols,
    }


@app.post("/api/play/tower/climb")
async def tower_climb(req: TowerClimbRequest, user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM tower_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
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
                await conn.execute("UPDATE tower_games SET active = 0 WHERE user_id = $1", user["user_id"])
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", user["user_id"])
                return {
                    "status": "boom",
                    "floor": floor,
                    "col": col,
                    "traps": traps,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            next_floor = floor + 1
            mult = tower_multiplier(game["difficulty"], next_floor)
            pot_cents = int(round(game["bet_cents"] * mult))

            if next_floor >= TOWER_FLOORS:
                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    pot_cents, user["user_id"],
                )
                await conn.execute("UPDATE tower_games SET active = 0, floor = $1 WHERE user_id = $2", next_floor, user["user_id"])
                return {
                    "status": "win_all",
                    "floor": next_floor,
                    "col": col,
                    "multiplier": mult,
                    "win": to_dollars(pot_cents),
                    "traps": traps,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            await conn.execute("UPDATE tower_games SET floor = $1 WHERE user_id = $2", next_floor, user["user_id"])
            return {
                "status": "safe",
                "floor": next_floor,
                "col": col,
                "multiplier": mult,
                "potential_win": to_dollars(pot_cents),
            }


@app.post("/api/play/tower/cashout")
async def tower_cashout(user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM tower_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры")
            floor = int(game["floor"])
            if floor <= 0:
                raise HTTPException(status_code=400, detail="Пройдите хотя бы первый этаж")

            traps = json.loads(game["traps"])
            mult = tower_multiplier(game["difficulty"], floor)
            win_cents = int(round(game["bet_cents"] * mult))
            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, user["user_id"],
            )
            await conn.execute("UPDATE tower_games SET active = 0 WHERE user_id = $1", user["user_id"])
            return {
                "win": to_dollars(win_cents),
                "multiplier": mult,
                "traps": traps,
                "balance": to_dollars(u_row["balance_cents"]),
            }


# =========================================================
# 11. ЛИМБО (RTP 94%)
# =========================================================
@app.post("/api/play/limbo")
async def play_limbo(req: LimboRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    result = draw_crash_point()
    is_win = result >= req.target
    win_cents = int(round(bet_cents * req.target)) if is_win else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {
        "result": result,
        "is_win": is_win,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 12. КЕНО (5x5, выбор 1–8 чисел, RTP ~92%)
# =========================================================
KENO_PAYOUTS = {
    1: {1: 2.85},
    2: {1: 0.5, 2: 7.5},
    3: {2: 2.5, 3: 16.0},
    4: {2: 1.5, 3: 4.5, 4: 25.0},
    5: {2: 0.7, 3: 2.8, 4: 12.0, 5: 50.0},
    6: {2: 0.3, 3: 2.0, 4: 6.5, 5: 25.0, 6: 100.0},
    7: {3: 1.4, 4: 4.0, 5: 15.0, 6: 60.0, 7: 200.0},
    8: {3: 1.0, 4: 2.8, 5: 8.5, 6: 30.0, 7: 100.0, 8: 300.0},
}


@app.post("/api/play/keno")
async def play_keno(req: KenoRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    picks = sorted(set(req.picks))
    if len(picks) != len(req.picks) or any(p < 1 or p > 25 for p in picks):
        raise HTTPException(status_code=400, detail="Выберите от 1 до 8 уникальных чисел (1–25)")

    pool_nums = list(range(1, 26))
    drawn = sorted([pool_nums.pop(secrets.randbelow(len(pool_nums))) for _ in range(8)])
    hits = sorted(set(picks) & set(drawn))
    mult = KENO_PAYOUTS[len(picks)].get(len(hits), 0.0)
    win_cents = int(round(bet_cents * mult))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
    return {
        "drawn": drawn,
        "hits": hits,
        "multiplier": mult,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# =========================================================
# 13. КЕЙСЫ (RTP ~90.8%)
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
    bet_cents = CASE_PRICES[req.tier]
    roll = secrets.randbelow(1000)
    acc = 0
    picked = CASE_ITEMS[0]
    for item in CASE_ITEMS:
        acc += item["weight"]
        if roll < acc:
            picked = item
            break

    win_cents = int(round(bet_cents * picked["mult"]))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
        rank = c[:-2] if len(c) > 2 else c[0]
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
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT active FROM blackjack_games WHERE user_id = $1 AND active = 1", user["user_id"]
            )
            if existing:
                raise HTTPException(status_code=400, detail="Завершите текущую раздачу Блэкджека")

            row = await conn.fetchrow(
                """
                UPDATE users
                SET balance_cents = balance_cents - $1,
                    games_played = games_played + 1,
                    total_wagered_cents = total_wagered_cents + $1
                WHERE user_id = $2 AND balance_cents >= $1
                RETURNING balance_cents
                """,
                bet_cents, user["user_id"],
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств")
            bal_cents = int(row["balance_cents"])

            deck = make_bj_deck()
            p_hand = [deck.pop(), deck.pop()]
            d_hand = [deck.pop(), deck.pop()]
            p_sc = bj_score(p_hand)
            d_sc = bj_score(d_hand)

            if p_sc == 21:
                if d_sc == 21:
                    win_cents = bet_cents
                    outcome = "push"
                else:
                    win_cents = int(round(bet_cents * 2.4))
                    outcome = "blackjack"
                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    win_cents, user["user_id"],
                )
                return {
                    "status": "finished",
                    "outcome": outcome,
                    "player_hand": p_hand,
                    "player_score": p_sc,
                    "dealer_hand": d_hand,
                    "dealer_score": d_sc,
                    "win": to_dollars(win_cents),
                    "balance": to_dollars(u_row["balance_cents"]),
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
                user["user_id"], bet_cents, json.dumps(deck), json.dumps(p_hand), json.dumps(d_hand),
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
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM blackjack_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
            )
            if not game:
                raise HTTPException(status_code=400, detail="Нет активной игры в Блэкджек")

            deck = json.loads(game["deck"])
            p_hand = json.loads(game["player_hand"])
            d_hand = json.loads(game["dealer_hand"])
            p_hand.append(deck.pop())
            p_sc = bj_score(p_hand)

            if p_sc > 21:
                await conn.execute("UPDATE blackjack_games SET active = 0 WHERE user_id = $1", user["user_id"])
                u_row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", user["user_id"])
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
                if d_sc > 21 or p_sc > d_sc:
                    win_cents, outcome = int(round(game["bet_cents"] * 1.95)), "win"
                elif p_sc == d_sc:
                    win_cents, outcome = int(game["bet_cents"]), "push"
                else:
                    win_cents, outcome = 0, "lose"

                u_row = await conn.fetchrow(
                    "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                    win_cents, user["user_id"],
                )
                await conn.execute("UPDATE blackjack_games SET active = 0 WHERE user_id = $1", user["user_id"])
                return {
                    "status": "finished",
                    "outcome": outcome,
                    "player_hand": p_hand,
                    "player_score": p_sc,
                    "dealer_hand": d_hand,
                    "dealer_score": d_sc,
                    "win": to_dollars(win_cents),
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            await conn.execute(
                "UPDATE blackjack_games SET deck = $1, player_hand = $2 WHERE user_id = $3",
                json.dumps(deck), json.dumps(p_hand), user["user_id"],
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
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow(
                "SELECT * FROM blackjack_games WHERE user_id = $1 AND active = 1 FOR UPDATE", user["user_id"]
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
            if d_sc > 21 or p_sc > d_sc:
                win_cents, outcome = int(round(game["bet_cents"] * 1.95)), "win"
            elif p_sc == d_sc:
                win_cents, outcome = int(game["bet_cents"]), "push"
            else:
                win_cents, outcome = 0, "lose"

            u_row = await conn.fetchrow(
                "UPDATE users SET balance_cents = balance_cents + $1, total_won_cents = total_won_cents + $1 WHERE user_id = $2 RETURNING balance_cents",
                win_cents, user["user_id"],
            )
            await conn.execute("UPDATE blackjack_games SET active = 0 WHERE user_id = $1", user["user_id"])
            return {
                "status": "finished",
                "outcome": outcome,
                "player_hand": p_hand,
                "player_score": p_sc,
                "dealer_hand": d_hand,
                "dealer_score": d_sc,
                "win": to_dollars(win_cents),
                "balance": to_dollars(u_row["balance_cents"]),
            }


# =========================================================
# 15. БАККАРА
# =========================================================
def bac_val(card: str) -> int:
    rank = card[:-2] if len(card) > 2 else card[0]
    if rank in ("10", "J", "Q", "K"):
        return 0
    return 1 if rank == "A" else int(rank)


@app.post("/api/play/baccarat")
async def play_baccarat(req: BaccaratRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
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
    win_cents = int(round(bet_cents * mults[winner])) if req.choice == winner else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
    cups = [0, 1, 2]
    ball_positions = [cups.pop(secrets.randbelow(len(cups))) for _ in range(req.balls)]
    is_win = req.cup in ball_positions
    mult = 2.80 if req.balls == 1 else 1.40
    win_cents = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
    bot_choice = secrets.choice(["rock", "paper", "scissors"])
    wins = {("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")}
    if req.choice == bot_choice:
        outcome, mult = "draw", 1.0
    elif (req.choice, bot_choice) in wins:
        outcome, mult = "win", 1.85
    else:
        outcome, mult = "lose", 0.0

    win_cents = int(round(bet_cents * mult))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
    zones = [0, 1, 2, 3, 4]
    blocks = 2 if req.difficulty == "normal" else 3
    keeper_zones = [zones.pop(secrets.randbelow(len(zones))) for _ in range(blocks)]
    is_goal = req.zone not in keeper_zones
    mult = 1.55 if req.difficulty == "normal" else 2.30
    win_cents = int(round(bet_cents * mult)) if is_goal else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
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

    win_cents = int(round(bet_cents * mult))
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
    bet_cents = to_cents(req.bet)
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

    win_cents = int(round(bet_cents * mult)) if is_win else 0
    new_bal_cents = await settle_instant_game(user["user_id"], bet_cents, win_cents)
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
# АДМИН-ПАНЕЛЬ (расширенная статистика)
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
        row = await conn.fetchrow("SELECT balance_cents FROM users WHERE user_id = $1", req.target_user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Игрок с таким ID не найден в базе")

        cur = int(row["balance_cents"])
        if req.mode == "add":
            new_bal_cents = cur + amount_cents
        elif req.mode == "sub":
            new_bal_cents = max(0, cur - amount_cents)
        else:
            new_bal_cents = amount_cents

        await conn.execute("UPDATE users SET balance_cents = $1 WHERE user_id = $2", new_bal_cents, req.target_user_id)

    return {"user_id": req.target_user_id, "balance": to_dollars(new_bal_cents)}


@app.post("/api/admin/withdraw/handle")
async def admin_handle_withdraw(req: AdminWithdrawHandleRequest, admin: dict = Depends(require_admin)):
    new_status = "approved" if req.action == "approve" else "rejected"
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            wd = await conn.fetchrow("SELECT * FROM withdrawals WHERE id = $1 FOR UPDATE", req.wd_id)
            if not wd:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            if wd["status"] != "pending":
                raise HTTPException(status_code=400, detail="Заявка уже обработана")

            await conn.execute("UPDATE withdrawals SET status = $1 WHERE id = $2", new_status, req.wd_id)

            usd = to_dollars(wd["amount_cents"])
            if req.action == "approve":
                user_msg = f"✅ Ваша заявка на вывод #{req.wd_id} (${usd:.2f}) одобрена и выплачена!"
            else:
                await conn.execute(
                    "UPDATE users SET balance_cents = balance_cents + $1 WHERE user_id = $2",
                    wd["amount_cents"], wd["user_id"],
                )
                user_msg = f"❌ Ваша заявка на вывод #{req.wd_id} (${usd:.2f}) отклонена. Средства возвращены на баланс."

    send_tg_message(wd["user_id"], user_msg)
    return {"ok": True, "wd_id": req.wd_id, "action": req.action}
