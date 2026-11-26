import asyncio
import os
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://whitysysu-lab.github.io/casino/")
DB_PATH = os.getenv("DB_PATH", "casino.db")
STARS_TO_CENTS = 2  # 500 Telegram Stars = 1000 cents ($10.00)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def ensure_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance_cents INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                total_won_cents INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount_cents INTEGER,
                details TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                charge_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                stars INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎰 Открыть казино", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="⭐ Пополнить баланс", callback_data="topup_menu")],
        ]
    )


def topup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="50 ⭐ (+$1)", callback_data="buy:50"),
                InlineKeyboardButton(text="250 ⭐ (+$5)", callback_data="buy:250"),
            ],
            [
                InlineKeyboardButton(text="500 ⭐ (+$10)", callback_data="buy:500"),
                InlineKeyboardButton(text="2500 ⭐ (+$50)", callback_data="buy:2500"),
            ],
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👑 Добро пожаловать в ROYAL CASINO!\n\n"
        "• Валюта: $ (курс 500 ⭐ = $10)\n"
        "• Доступен демо-режим на $10 000\n\n"
        "Выберите действие:",
        reply_markup=main_menu_kb(),
    )


@dp.message(Command("paysupport"))
async def cmd_paysupport(message: Message):
    await message.answer(
        "💬 Поддержка по платежам Telegram Stars:\n"
        "Если возникла проблема с оплатой или зачислением, опишите ситуацию и укажите свой Telegram ID "
        f"(`{message.from_user.id}`). Администратор проверит платёж по ID транзакции.",
        parse_mode="Markdown",
    )


@dp.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Ваш Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")


@dp.message(Command("topup"))
async def cmd_topup(message: Message):
    await message.answer(
        "Выберите пакет пополнения через Telegram Stars (500 ⭐ = $10):",
        reply_markup=topup_kb(),
    )


@dp.callback_query(F.data == "topup_menu")
async def cb_topup_menu(callback: CallbackQuery):
    if callback.message:
        await callback.message.answer(
            "Выберите пакет пополнения через Telegram Stars (500 ⭐ = $10):",
            reply_markup=topup_kb(),
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy_stars(callback: CallbackQuery):
    stars = int(callback.data.split(":")[1])
    usd = round((stars * STARS_TO_CENTS) / 100.0, 2)

    if callback.message:
        await callback.message.answer_invoice(
            title=f"Пополнение: ${usd:.2f}",
            description=f"Зачисление ${usd:.2f} на игровой баланс за {stars} Telegram Stars",
            payload=f"topup:{callback.from_user.id}:{stars}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"${usd:.2f}", amount=stars)],
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("wd_ok:") | F.data.startswith("wd_no:"))
async def cb_handle_withdrawal(callback: CallbackQuery):
    if not ADMIN_ID or callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    action, raw_id = callback.data.split(":")
    wd_id = int(raw_id)
    new_status = "approved" if action == "wd_ok" else "rejected"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE id = ?", (wd_id,)) as cur:
            wd = await cur.fetchone()

        if not wd:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        # Атомарное обновление статуса
        upd = await db.execute(
            "UPDATE withdrawals SET status = ? WHERE id = ? AND status = 'pending'",
            (new_status, wd_id),
        )
        if upd.rowcount != 1:
            await callback.answer("Заявка уже обработана", show_alert=True)
            return

        usd = round(wd["amount_cents"] / 100.0, 2)
        if action == "wd_ok":
            status_text = "✅ ОДОБРЕНО (выплачено)"
            user_msg = f"✅ Ваша заявка на вывод #{wd_id} (${usd:.2f}) одобрена и выплачена!"
        else:
            await db.execute(
                "UPDATE users SET balance_cents = balance_cents + ? WHERE user_id = ?",
                (wd["amount_cents"], wd["user_id"]),
            )
            status_text = "❌ ОТКЛОНЕНО (средства возвращены)"
            user_msg = f"❌ Ваша заявка на вывод #{wd_id} (${usd:.2f}) отклонена. Средства возвращены на баланс."

        await db.commit()

    if callback.message and callback.message.text:
        await callback.message.edit_text(f"{callback.message.text}\n\nСтатус: {status_text}")

    try:
        await bot.send_message(wd["user_id"], user_msg)
    except Exception:
        pass
    await callback.answer("Готово")


@dp.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payment = message.successful_payment
    if not payment or payment.currency != "XTR":
        return

    user_id = message.from_user.id
    stars = payment.total_amount
    expected_payload = f"topup:{user_id}:{stars}"
    if payment.invoice_payload != expected_payload:
        await message.answer("⚠️ Ошибка проверки платежа. Обратитесь в /paysupport.")
        return

    charge_id = payment.telegram_payment_charge_id
    amount_cents = stars * STARS_TO_CENTS
    usd = round(amount_cents / 100.0, 2)
    username = message.from_user.first_name or message.from_user.username or "Игрок"

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO payments (charge_id, user_id, stars, amount_cents) VALUES (?, ?, ?, ?)",
            (charge_id, user_id, stars, amount_cents),
        )
        if cur.rowcount != 1:
            # Защита от двойного зачисления
            return

        async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as ucur:
            exists = await ucur.fetchone()

        if exists:
            await db.execute(
                "UPDATE users SET balance_cents = balance_cents + ? WHERE user_id = ?",
                (amount_cents, user_id),
            )
        else:
            await db.execute(
                "INSERT INTO users (user_id, username, balance_cents, games_played, total_won_cents) VALUES (?, ?, ?, 0, 0)",
                (user_id, username, amount_cents),
            )
        await db.commit()

    await message.answer(
        f"✅ Оплата {stars} ⭐ прошла успешно!\nНа ваш баланс зачислено +${usd:.2f}.",
        reply_markup=main_menu_kb(),
    )


async def main():
    await ensure_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
