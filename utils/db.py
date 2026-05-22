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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_feeds (
                id         SERIAL      PRIMARY KEY,
                series     TEXT        NOT NULL UNIQUE,
                title      TEXT        NOT NULL,
                link       TEXT        NOT NULL,
                guid       TEXT,
                pub_date   TEXT        NOT NULL,
                size       TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_subscriptions (
                feed_id    INTEGER     NOT NULL REFERENCES rss_feeds(id) ON DELETE CASCADE,
                user_id    BIGINT      NOT NULL,
                PRIMARY KEY (feed_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mal_profiles (
                id         SERIAL      PRIMARY KEY,
                username   TEXT        NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS anime_list (
                id         SERIAL      PRIMARY KEY,
                status     INTEGER     NOT NULL,
                title      TEXT        NOT NULL,
                UNIQUE (status, title)
            )
        """)
    botLogger.info("schema ensured")


# ---------------------------------------------------------------------------
# Roulette helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# RSS helpers
# ---------------------------------------------------------------------------

@trace_function
async def rss_get_series_list() -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT series FROM rss_feeds ORDER BY created_at ASC"
        )
    return [row["series"] for row in rows]


@trace_function
async def rss_get_subscribed_series(user_id: int) -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT f.series FROM rss_feeds f
            JOIN rss_subscriptions s ON f.id = s.feed_id
            WHERE s.user_id = $1
            ORDER BY f.created_at ASC
            """,
            user_id,
        )
    return [row["series"] for row in rows]


@trace_function
async def rss_get_unsubscribed_series(user_id: int) -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT f.series FROM rss_feeds f
            WHERE NOT EXISTS (
                SELECT 1 FROM rss_subscriptions s
                WHERE s.feed_id = f.id AND s.user_id = $1
            )
            ORDER BY f.created_at ASC
            """,
            user_id,
        )
    return [row["series"] for row in rows]


@trace_function
async def rss_get_all_with_subs() -> list[dict]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT f.series,
                   COALESCE(array_agg(s.user_id) FILTER (WHERE s.user_id IS NOT NULL), '{}') AS subs
            FROM rss_feeds f
            LEFT JOIN rss_subscriptions s ON f.id = s.feed_id
            GROUP BY f.id, f.series
            ORDER BY f.created_at ASC
            """
        )
    return [{"series": row["series"], "subs": list(row["subs"])} for row in rows]


@trace_function
async def rss_get_all_episodes() -> list[dict]:
    """Return all feeds with subscriber lists for episode checking."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT f.series, f.title, f.link, f.pub_date, f.size,
                   COALESCE(array_agg(s.user_id) FILTER (WHERE s.user_id IS NOT NULL), '{}') AS subs
            FROM rss_feeds f
            LEFT JOIN rss_subscriptions s ON f.id = s.feed_id
            GROUP BY f.id
            ORDER BY f.created_at ASC
            """
        )
    return [
        {
            "series":  row["series"],
            "title":   row["title"],
            "link":    row["link"],
            "pubDate": row["pub_date"],
            "size":    row["size"],
            "subs":    [str(uid) for uid in row["subs"]],
        }
        for row in rows
    ]


@trace_function
async def rss_add_feed(entry: dict, user_id: int | None = None) -> None:
    """Insert a feed entry, optionally subscribing a user. No-op if series exists."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO rss_feeds (series, title, link, guid, pub_date, size)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (series) DO NOTHING
            RETURNING id
            """,
            entry["series"],
            entry["title"],
            entry["link"],
            entry.get("guid"),
            entry["pubDate"],
            entry.get("size"),
        )
        if row and user_id is not None:
            await conn.execute(
                """
                INSERT INTO rss_subscriptions (feed_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                row["id"],
                user_id,
            )


@trace_function
async def rss_delete_series(series: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM rss_feeds WHERE series = $1", series)


@trace_function
async def rss_subscribe(series: str, user_id: int) -> bool:
    """Returns True if newly subscribed, False if already subscribed."""
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO rss_subscriptions (feed_id, user_id)
            SELECT id, $2 FROM rss_feeds WHERE series = $1
            ON CONFLICT DO NOTHING
            """,
            series,
            user_id,
        )
    return result.endswith("1")


@trace_function
async def rss_unsubscribe(series: str, user_id: int) -> bool:
    """Returns True if unsubscribed, False if wasn't subscribed."""
    async with get_pool().acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM rss_subscriptions
            WHERE feed_id = (SELECT id FROM rss_feeds WHERE series = $1)
            AND user_id = $2
            """,
            series,
            user_id,
        )
    return result.endswith("1")


@trace_function
async def rss_update_episode(series: str, pub_date: str, title: str, link: str, size: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE rss_feeds SET pub_date = $1, title = $2, link = $3, size = $4
            WHERE series = $5
            """,
            pub_date, title, link, size, series,
        )


# ---------------------------------------------------------------------------
# MAL profile helpers
# ---------------------------------------------------------------------------

@trace_function
async def mal_get_users() -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT username FROM mal_profiles ORDER BY created_at ASC")
    return [row["username"] for row in rows]


@trace_function
async def mal_add_user(username: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO mal_profiles (username) VALUES ($1) ON CONFLICT (username) DO NOTHING",
            username,
        )


@trace_function
async def mal_remove_user(username: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM mal_profiles WHERE username = $1", username)


# ---------------------------------------------------------------------------
# Anime list helpers
# ---------------------------------------------------------------------------

@trace_function
async def anime_list_get(status: int) -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT title FROM anime_list WHERE status = $1 ORDER BY id ASC", status
        )
    return [row["title"] for row in rows]


@trace_function
async def anime_list_replace(status: int, titles: list[str]) -> None:
    """Atomically replace all titles for a given status."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM anime_list WHERE status = $1", status)
            if titles:
                await conn.executemany(
                    "INSERT INTO anime_list (status, title) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    [(status, t) for t in titles],
                )
