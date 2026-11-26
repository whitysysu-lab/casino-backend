import os
import asyncpg

_raw_db_url = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
# Убираем channel_binding=require, так как asyncpg его не поддерживает
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
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance DOUBLE PRECISION DEFAULT 0.0,
                total_wagered DOUBLE PRECISION DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                game TEXT,
                bet DOUBLE PRECISION,
                payout DOUBLE PRECISION,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount DOUBLE PRECISION,
                method TEXT,
                wallet TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_mines (
                game_id TEXT PRIMARY KEY,
                user_id BIGINT,
                bet DOUBLE PRECISION,
                mines_count INTEGER,
                mines_json TEXT,
                revealed_json TEXT
            );
        """)


async def close_db():
    if pool:
        await pool.close()
