import asyncio
import html
import os
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

import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
_raw_url = os.getenv("WEBAPP_URL", "https://casino-backend-gu9d.onrender.com").strip()
WEBAPP_URL = _raw_url.split("](")[0].lstrip("[")
STARS_TO_CENTS = 1  # 100 Telegram Stars = 100 cents ($1.00)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎰 Играть в T Casino", web_app=WebAppInfo(url=WEBAPP_URL))],
            [InlineKeyboardButton(text="⭐ Пополнить баланс", callback_data="topup_menu")],
        ]
    )


def topup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="100 ⭐ (+$1)", callback_data="buy:100"),
                InlineKeyboardButton(text="500 ⭐ (+$5)", callback_data="buy:500"),
            ],
            [
                InlineKeyboardButton(text="1000 ⭐ (+$10)", callback_data="buy:1000"),
                InlineKeyboardButton(text="5000 ⭐ (+$50)", callback_data="buy:5000"),
            ],
        ]
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = html.escape(message.from_user.first_name or "Игрок")
    text = (
        f"👑 <b>Добро пожаловать в T CASINO, {name}!</b>\n\n"
        f"<blockquote>"
        f"🎰 <b>20 топовых игр</b> — Краш, Плинко, Мины, Башня, Блэкджек 21, Европейская рулетка, Кейсы и др.\n"
        f"🎁 <b>Демо-счёт на $10 000</b> — тестируй стратегии бесплатно.\n"
        f"⭐ <b>Курс пополнения:</b> 100 Stars = $1.00 (мгновенно).\n"
        f"💸 <b>Быстрый вывод</b> — от $1.00 на карту, TON или USDT."
        f"</blockquote>\n\n"
        f"👇 Жми кнопку ниже, чтобы открыть лобби:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())


@dp.message(Command("users"))
async def cmd_users(message: Message):
    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        return
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, username, balance_cents, games_played FROM users ORDER BY balance_cents DESC LIMIT 40"
        )
        total = await conn.fetchrow("SELECT COUNT(*) AS cnt, COALESCE(SUM(balance_cents), 0) AS bal FROM users")

    lines = [
        f"👥 <b>Игроков в базе:</b> {total['cnt']}",
        f"🏦 <b>Общий банк:</b> ${total['bal'] / 100:.2f}\n",
    ]
    for i, r in enumerate(rows, 1):
        uname = html.escape(r["username"] or "Игрок")
        lines.append(f"{i}. <b>{uname}</b> (<code>{r['user_id']}</code>) — <b>${r['balance_cents'] / 100:.2f}</b> ({r['games_played']} игр)")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("paysupport"))
async def cmd_paysupport(message: Message):
    await message.answer(
        "💬 <b>Поддержка по платежам Telegram Stars</b>\n"
        "Если возникла проблема с оплатой или зачислением, опишите ситуацию и укажите свой Telegram ID: "
        f"<code>{message.from_user.id}</code>.",
        parse_mode="HTML",
    )


@dp.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


@dp.message(Command("topup"))
async def cmd_topup(message: Message):
    await message.answer(
        "⭐ Выберите пакет пополнения через Telegram Stars (<b>100 ⭐ = $1</b>):",
        parse_mode="HTML",
        reply_markup=topup_kb(),
    )


@dp.callback_query(F.data == "topup_menu")
async def cb_topup_menu(callback: CallbackQuery):
    if callback.message:
        await callback.message.answer(
            "⭐ Выберите пакет пополнения через Telegram Stars (<b>100 ⭐ = $1</b>):",
            parse_mode="HTML",
            reply_markup=topup_kb(),
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy_stars(callback: CallbackQuery):
    stars = int(callback.data.split(":")[1])
    usd = round((stars * STARS_TO_CENTS) / 100.0, 2)

    if callback.message:
        await callback.message.answer_invoice(
            title=f"Пополнение T Casino: ${usd:.2f}",
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

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            wd = await conn.fetchrow("SELECT * FROM withdrawals WHERE id = $1 FOR UPDATE", wd_id)
            if not wd:
                await callback.answer("Заявка не найдена", show_alert=True)
                return
            if wd["status"] != "pending":
                await callback.answer("Заявка уже обработана", show_alert=True)
                return

            await conn.execute("UPDATE withdrawals SET status = $1 WHERE id = $2", new_status, wd_id)

            usd = round(wd["amount_cents"] / 100.0, 2)
            if action == "wd_ok":
                status_text = "✅ ОДОБРЕНО (выплачено)"
                user_msg = f"✅ Ваша заявка на вывод #{wd_id} (${usd:.2f}) одобрена и выплачена!"
            else:
                await conn.execute(
                    "UPDATE users SET balance_cents = balance_cents + $1 WHERE user_id = $2",
                    wd["amount_cents"], wd["user_id"],
                )
                status_text = "❌ ОТКЛОНЕНО (средства возвращены)"
                user_msg = f"❌ Ваша заявка на вывод #{wd_id} (${usd:.2f}) отклонена. Средства возвращены на баланс."

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

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            inserted = await conn.fetchval(
                """
                INSERT INTO payments (charge_id, user_id, stars, amount_cents)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (charge_id) DO NOTHING
                RETURNING id
                """,
                charge_id, user_id, stars, amount_cents,
            )
            if not inserted:
                return

            await conn.execute(
                """
                INSERT INTO users (user_id, username, balance_cents, games_played, total_wagered_cents, total_won_cents)
                VALUES ($1, $2, $3, 0, 0, 0)
                ON CONFLICT (user_id) DO UPDATE
                SET balance_cents = users.balance_cents + EXCLUDED.balance_cents
                """,
                user_id, username, amount_cents,
            )

    await message.answer(
        f"✅ Оплата <b>{stars} ⭐</b> прошла успешно!\nНа ваш баланс зачислено <b>+${usd:.2f}</b>.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


async def main():
    await db.init_db()
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
