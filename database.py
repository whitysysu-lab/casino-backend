import os
import asyncpg

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
        raise RuntimeError("DATABASE_URL не задан в переменных окружения Render!")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=8)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance_cents BIGINT DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                total_wagered_cents BIGINT DEFAULT 0,
                total_won_cents BIGINT DEFAULT 0
            );
        """)
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS total_wagered_cents BIGINT DEFAULT 0;
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mines_games (
                user_id BIGINT PRIMARY KEY,
                bet_cents BIGINT,
                mines_count INTEGER,
                mines_positions TEXT,
                revealed TEXT,
                active INTEGER
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crash_games (
                user_id BIGINT PRIMARY KEY,
                bet_cents BIGINT,
                crash_point DOUBLE PRECISION,
                auto_cashout DOUBLE PRECISION DEFAULT 0,
                started_at DOUBLE PRECISION,
                active INTEGER DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tower_games (
                user_id BIGINT PRIMARY KEY,
                bet_cents BIGINT,
                difficulty TEXT,
                traps TEXT,
                floor INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blackjack_games (
                user_id BIGINT PRIMARY KEY,
                bet_cents BIGINT,
                deck TEXT,
                player_hand TEXT,
                dealer_hand TEXT,
                active INTEGER DEFAULT 1
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                amount_cents BIGINT,
                details TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                charge_id TEXT UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                stars INTEGER NOT NULL,
                amount_cents BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


async def close_db():
    if pool:
        await pool.close()
