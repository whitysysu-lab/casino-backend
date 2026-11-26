import hashlib
import hmac
import json
import os
import secrets
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
STARS_TO_CENTS = 1  # 1 Star = 2 cents -> 500 Stars = 1000 cents ($10.00)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield
    await db.close_db()


app = FastAPI(title="T Casino Mini App", lifespan=lifespan)

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
                "INSERT INTO users (user_id, username, balance_cents, games_played, total_won_cents) VALUES ($1, $2, 0, 0, 0) ON CONFLICT (user_id) DO NOTHING",
                user_id, username,
            )
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row)


def mines_multiplier(mines_count: int, revealed_count: int) -> float:
    if revealed_count == 0:
        return 1.0
    prob = 1.0
    for i in range(revealed_count):
        prob *= (25 - mines_count - i) / (25 - i)
    return round(0.98 / prob, 2)


# --- Модели ---
class BetRequest(BaseModel):
    bet: float = Field(gt=0, le=100000)


class CoinflipRequest(BetRequest):
    choice: str = Field(pattern="^(heads|tails)$")


class DiceRequest(BetRequest):
    target: int = Field(ge=2, le=98)
    direction: str = Field(pattern="^(under|over)$")


class MinesStartRequest(BetRequest):
    mines_count: int = Field(ge=1, le=24)


class MinesRevealRequest(BaseModel):
    cell: int = Field(ge=0, le=24)


class CrashRequest(BetRequest):
    target: float = Field(ge=1.1, le=100.0)


class RouletteRequest(BetRequest):
    color: str = Field(pattern="^(red|black|green)$")


class HiloRequest(BetRequest):
    current_card: int = Field(ge=2, le=14)
    guess: str = Field(pattern="^(high|low)$")


class StarsInvoiceRequest(BaseModel):
    stars: int = Field(ge=1, le=10000)


class WithdrawRequest(BaseModel):
    amount: float = Field(ge=1.0, le=100000)
    details: str = Field(min_length=3, max_length=200)


# --- Маршруты ---
@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/api/me")
async def api_me(user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        game = await conn.fetchrow(
            "SELECT * FROM mines_games WHERE user_id = $1 AND active = 1",
            user["user_id"],
        )
        wd_rows = await conn.fetch(
            "SELECT id, amount_cents, status FROM withdrawals WHERE user_id = $1 ORDER BY id DESC LIMIT 5",
            user["user_id"],
        )

    active_mines = None
    if game:
        revealed = json.loads(game["revealed"])
        mult = mines_multiplier(game["mines_count"], len(revealed))
        potential_cents = int(round(game["bet_cents"] * mult))
        active_mines = {
            "bet": to_dollars(game["bet_cents"]),
            "mines_count": game["mines_count"],
            "revealed": revealed,
            "multiplier": mult,
            "potential_win": to_dollars(potential_cents),
        }

    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "balance": to_dollars(user["balance_cents"]),
        "games_played": user["games_played"],
        "total_won": to_dollars(user["total_won_cents"]),
        "active_mines": active_mines,
        "withdrawals": [
            {"id": r["id"], "amount": to_dollars(r["amount_cents"]), "status": r["status"]}
            for r in wd_rows
        ],
        "is_admin": bool(ADMIN_ID and user["user_id"] == ADMIN_ID),
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
        "title": f"Пополнение: ${usd:.2f}",
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


# --- 1. Слоты ---
SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]


@app.post("/api/play/slots")
async def play_slots(req: BetRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    reels = [secrets.choice(SLOT_SYMBOLS) for _ in range(3)]
    win_cents = 0
    if reels[0] == reels[1] == reels[2]:
        mult = 15.0 if reels[0] == "7️⃣" else (10.0 if reels[0] == "💎" else 5.0)
        win_cents = int(round(bet_cents * mult))
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        win_cents = int(round(bet_cents * 1.5))

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Профиле!")
        new_bal_cents = row["balance_cents"]

    return {"reels": reels, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# --- 2. Мины ---
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
                "UPDATE users SET balance_cents = balance_cents - $1, games_played = games_played + 1 WHERE user_id = $2 AND balance_cents >= $1 RETURNING balance_cents",
                bet_cents, user["user_id"],
            )
            if not row:
                raise HTTPException(status_code=400, detail="Недостаточно средств. Пополните баланс в Профиле!")
            new_bal_cents = row["balance_cents"]

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
            if req.cell in revealed:
                raise HTTPException(status_code=400, detail="Клетка уже открыта")

            if req.cell in mines:
                await conn.execute("UPDATE mines_games SET active = 0 WHERE user_id = $1", user["user_id"])
                return {
                    "status": "boom",
                    "cell": req.cell,
                    "mines": mines,
                    "revealed": revealed,
                    "balance": to_dollars(user["balance_cents"]),
                }

            revealed.append(req.cell)
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
                    "cell": req.cell,
                    "multiplier": mult,
                    "win": to_dollars(potential_cents),
                    "mines": mines,
                    "revealed": revealed,
                    "balance": to_dollars(u_row["balance_cents"]),
                }

            await conn.execute("UPDATE mines_games SET revealed = $1 WHERE user_id = $2", json.dumps(revealed), user["user_id"])
            return {"status": "safe", "cell": req.cell, "multiplier": mult, "potential_win": to_dollars(potential_cents)}


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
            new_bal_cents = u_row["balance_cents"]

    return {
        "win": to_dollars(win_cents),
        "multiplier": mult,
        "mines": mines,
        "revealed": revealed,
        "balance": to_dollars(new_bal_cents),
    }


# --- 3. Кости ---
@app.post("/api/play/dice")
async def play_dice(req: DiceRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    roll = secrets.randbelow(100) + 1
    if req.direction == "under":
        chance = req.target - 1
        is_win = roll < req.target
    else:
        chance = 100 - req.target
        is_win = roll > req.target

    if chance <= 0:
        raise HTTPException(status_code=400, detail="Некорректная цель")

    multiplier = round(98.0 / chance, 2)
    win_cents = int(round(bet_cents * multiplier)) if is_win else 0

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
        new_bal_cents = row["balance_cents"]

    return {
        "roll": roll,
        "is_win": is_win,
        "multiplier": multiplier,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# --- 4. Монетка ---
@app.post("/api/play/coinflip")
async def play_coinflip(req: CoinflipRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    result = secrets.choice(["heads", "tails"])
    win_cents = int(round(bet_cents * 1.95)) if result == req.choice else 0

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
        new_bal_cents = row["balance_cents"]

    return {"result": result, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# --- 5. Краш ---
@app.post("/api/play/crash")
async def play_crash(req: CrashRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    r = (secrets.randbelow(999999) + 1) / 1000000.0
    crash_point = max(1.0, round(0.97 / r, 2))
    is_win = crash_point >= req.target
    win_cents = int(round(bet_cents * req.target)) if is_win else 0

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
        new_bal_cents = row["balance_cents"]

    return {
        "crash_point": crash_point,
        "is_win": is_win,
        "win": to_dollars(win_cents),
        "balance": to_dollars(new_bal_cents),
    }


# --- 6. Рулетка ---
@app.post("/api/play/roulette")
async def play_roulette(req: RouletteRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    number = secrets.randbelow(15)
    color = "green" if number == 0 else ("red" if number <= 7 else "black")
    mult = 14.0 if color == "green" else 2.0
    win_cents = int(round(bet_cents * mult)) if color == req.color else 0

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
        new_bal_cents = row["balance_cents"]

    return {"number": number, "color": color, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# --- 7. Колесо Фортуны ---
@app.post("/api/play/wheel")
async def play_wheel(req: BetRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    sectors = [0.0, 1.5, 0.0, 2.0, 0.5, 0.0, 1.0, 0.0, 1.5, 3.0]
    mult = secrets.choice(sectors)
    win_cents = int(round(bet_cents * mult))

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
        new_bal_cents = row["balance_cents"]

    return {"multiplier": mult, "win": to_dollars(win_cents), "balance": to_dollars(new_bal_cents)}


# --- 8. Карты Hi-Lo ---
@app.post("/api/play/hilo")
async def play_hilo(req: HiloRequest, user: dict = Depends(get_current_user)):
    bet_cents = to_cents(req.bet)
    if bet_cents <= 0:
        raise HTTPException(status_code=400, detail="Некорректная ставка")

    count = (14 - req.current_card) if req.guess == "high" else (req.current_card - 2)
    if count <= 0:
        raise HTTPException(status_code=400, detail="Невозможный выбор для этой карты")

    mult = round(12.5 / count, 2)
    next_card = secrets.randbelow(13) + 2
    is_win = (next_card > req.current_card) if req.guess == "high" else (next_card < req.current_card)
    win_cents = int(round(bet_cents * mult)) if is_win else 0

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET balance_cents = balance_cents - $1 + $2, games_played = games_played + 1, total_won_cents = total_won_cents + $2 WHERE user_id = $3 AND balance_cents >= $1 RETURNING balance_cents",
            bet_cents, win_cents, user["user_id"],
        )
        if not row:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
        new_bal_cents = row["balance_cents"]

    return {
        "next_card": next_card,
        "win": to_dollars(win_cents),
        "multiplier": mult,
        "balance": to_dollars(new_bal_cents),
    }


# --- Админ-панель ---
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
            "SELECT COUNT(*) AS users_count, COALESCE(SUM(balance_cents), 0) AS total_balance_cents, COALESCE(SUM(games_played), 0) AS total_games FROM users"
        )
        pending = await conn.fetch(
            "SELECT id, user_id, username, amount_cents, details, status FROM withdrawals WHERE status = 'pending' ORDER BY id DESC LIMIT 20"
        )
        users = await conn.fetch(
            "SELECT user_id, username, balance_cents, games_played FROM users ORDER BY balance_cents DESC LIMIT 20"
        )

    return {
        "stats": {
            "users_count": st["users_count"],
            "total_balance": to_dollars(st["total_balance_cents"]),
            "total_games": st["total_games"],
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

            await conn.execute(
                "UPDATE withdrawals SET status = $1 WHERE id = $2",
                new_status, req.wd_id,
            )

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
