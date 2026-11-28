import logging
import os
import asyncpg

logger = logging.getLogger("tcasino.db")

_raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
if "channel_binding=" in _raw_db_url:
    base, _, query = _raw_db_url.partition("?")
    params = [p for p in query.split("&") if p and not p.startswith("channel_binding=")]
    DATABASE_URL = f"{base}?{'&'.join(params)}" if params else base
else:
    DATABASE_URL = _raw_db_url

pool: asyncpg.Pool | None = None


async def init_db():
    global pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан в переменных окружения!")

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=8,
        command_timeout=15,
        max_inactive_connection_lifetime=240,
    )
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance_cents BIGINT NOT NULL DEFAULT 0 CHECK (balance_cents >= 0),
                games_played INTEGER NOT NULL DEFAULT 0,
                total_wagered_cents BIGINT NOT NULL DEFAULT 0,
                total_won_cents BIGINT NOT NULL DEFAULT 0,
                hilo_card INTEGER NOT NULL DEFAULT 7
            );
        """)
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS total_wagered_cents BIGINT NOT NULL DEFAULT 0;
        """)
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS hilo_card INTEGER NOT NULL DEFAULT 7;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mines_games (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                bet_cents BIGINT NOT NULL CHECK (bet_cents > 0),
                mines_count INTEGER NOT NULL CHECK (mines_count BETWEEN 1 AND 24),
                mines_positions TEXT NOT NULL,
                revealed TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crash_games (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                bet_cents BIGINT NOT NULL CHECK (bet_cents > 0),
                crash_point DOUBLE PRECISION NOT NULL,
                auto_cashout DOUBLE PRECISION NOT NULL DEFAULT 0,
                started_at DOUBLE PRECISION NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tower_games (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                bet_cents BIGINT NOT NULL CHECK (bet_cents > 0),
                difficulty TEXT NOT NULL,
                traps TEXT NOT NULL,
                floor INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blackjack_games (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                bet_cents BIGINT NOT NULL CHECK (bet_cents > 0),
                deck TEXT NOT NULL,
                player_hand TEXT NOT NULL,
                dealer_hand TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                charge_id TEXT UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                stars INTEGER NOT NULL CHECK (stars > 0),
                amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                kind TEXT NOT NULL,
                amount_cents BIGINT NOT NULL,
                balance_after_cents BIGINT NOT NULL,
                meta TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Безопасное добавление CHECK-ограничений для уже существующих баз
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'users_balance_non_negative'
                ) THEN
                    ALTER TABLE users
                    ADD CONSTRAINT users_balance_non_negative CHECK (balance_cents >= 0) NOT VALID;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'withdrawals_amount_positive'
                ) THEN
                    ALTER TABLE withdrawals
                    ADD CONSTRAINT withdrawals_amount_positive CHECK (amount_cents > 0) NOT VALID;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'payments_amount_positive'
                ) THEN
                    ALTER TABLE payments
                    ADD CONSTRAINT payments_amount_positive CHECK (amount_cents > 0 AND stars > 0) NOT VALID;
                END IF;
            END $$;
        """)

        # Индексы для быстрых запросов
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_user_status ON withdrawals (user_id, status);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_status_id ON withdrawals (status, id DESC);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments (user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions (user_id, id DESC);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_leaderboard ON users (total_won_cents DESC, balance_cents DESC);")

    logger.info("PostgreSQL pool initialized and schema verified")


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("PostgreSQL pool closed")


async def log_transaction(
    conn: asyncpg.Connection,
    user_id: int,
    kind: str,
    amount_cents: int,
    balance_after_cents: int,
    meta: str | None = None,
):
    await conn.execute(
        """
        INSERT INTO transactions (user_id, kind, amount_cents, balance_after_cents, meta)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_id,
        kind,
        amount_cents,
        balance_after_cents,
        meta,
    )


async def handle_withdrawal_decision(wd_id: int, action: str) -> dict:
    """
    Единая атомарная обработка заявки на вывод для main.py и bot.py.
    action: 'approve' | 'reject'
    """
    if action not in ("approve", "reject"):
        return {"ok": False, "code": 400, "error": "Некорректное действие"}

    new_status = "approved" if action == "approve" else "rejected"
    async with pool.acquire() as conn:
        async with conn.transaction():
            wd = await conn.fetchrow("SELECT * FROM withdrawals WHERE id = $1 FOR UPDATE", wd_id)
            if not wd:
                return {"ok": False, "code": 404, "error": "Заявка не найдена"}
            if wd["status"] != "pending":
                return {"ok": False, "code": 400, "error": "Заявка уже обработана"}

            await conn.execute("UPDATE withdrawals SET status = $1 WHERE id = $2", new_status, wd_id)

            amount_cents = int(wd["amount_cents"])
            user_id = int(wd["user_id"])
            usd = round(amount_cents / 100.0, 2)

            if action == "approve":
                status_text = "✅ ОДОБРЕНО (выплачено)"
                user_msg = f"✅ Ваша заявка на вывод #{wd_id} (${usd:.2f}) одобрена и выплачена!"
            else:
                u_row = await conn.fetchrow(
                    """
                    UPDATE users
                    SET balance_cents = balance_cents + $1
                    WHERE user_id = $2
                    RETURNING balance_cents
                    """,
                    amount_cents,
                    user_id,
                )
                if u_row:
                    await log_transaction(
                        conn,
                        user_id,
                        "withdraw_refund",
                        amount_cents,
                        int(u_row["balance_cents"]),
                        f"wd:{wd_id}",
                    )
                status_text = "❌ ОТКЛОНЕНО (средства возвращены)"
                user_msg = f"❌ Ваша заявка на вывод #{wd_id} (${usd:.2f}) отклонена. Средства возвращены на баланс."

    return {
        "ok": True,
        "wd_id": wd_id,
        "user_id": user_id,
        "amount_cents": amount_cents,
        "usd": usd,
        "action": action,
        "status_text": status_text,
        "user_msg": user_msg,
    }
