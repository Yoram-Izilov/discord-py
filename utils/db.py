import os

import asyncpg

from utils.logger import botLogger
from utils.tracing import trace_function

_pool: asyncpg.Pool | None = None


@trace_function
async def init_pool() -> None:
    global _pool
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise EnvironmentError(
            "DATABASE_URL is not set. Example: "
            "postgresql://user:password@localhost:5432/dbname"
        )
    _pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5)
    botLogger.info("asyncpg pool initialised")


@trace_function
async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        botLogger.info("asyncpg pool closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised. Call init_pool() first.")
    return _pool


@trace_function
async def ensure_schema() -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS roulette_options (
                id         SERIAL      PRIMARY KEY,
                line       TEXT        NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    botLogger.info("roulette_options table ensured")


@trace_function
async def roulette_load_all() -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT line FROM roulette_options ORDER BY created_at ASC"
        )
    return [row["line"] for row in rows]


@trace_function
async def roulette_add(line: str) -> bool:
    """Returns True if inserted, False if already exists."""
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            "INSERT INTO roulette_options (line) VALUES ($1) ON CONFLICT (line) DO NOTHING",
            line,
        )
    return result.endswith("1")


@trace_function
async def roulette_update(old_line: str, new_line: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE roulette_options SET line = $1 WHERE line = $2",
            new_line, old_line,
        )


@trace_function
async def roulette_remove(line: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "DELETE FROM roulette_options WHERE line = $1",
            line,
        )
