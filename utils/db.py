import os
from datetime import datetime

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
        await conn.execute("""
            ALTER TABLE mal_profiles
            ADD COLUMN IF NOT EXISTS discord_user_id BIGINT UNIQUE
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mal_list_snapshots (
                username         TEXT        NOT NULL REFERENCES mal_profiles(username) ON DELETE CASCADE,
                mal_id           INTEGER     NOT NULL,
                title            TEXT        NOT NULL,
                status           INTEGER     NOT NULL,
                score            INTEGER,
                episodes_watched INTEGER     NOT NULL DEFAULT 0,
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (username, mal_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS mal_list_snapshots_status_mal_id_idx
            ON mal_list_snapshots(status, mal_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mal_activity (
                id             BIGSERIAL   PRIMARY KEY,
                username       TEXT        NOT NULL,
                mal_id         INTEGER     NOT NULL,
                delta_episodes INTEGER     NOT NULL,
                new_status     INTEGER,
                score          INTEGER,
                recorded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS mal_activity_username_recorded_idx
            ON mal_activity(username, recorded_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS mal_activity_recorded_idx
            ON mal_activity(recorded_at)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episode_announcements (
                message_id   BIGINT      PRIMARY KEY,
                series       TEXT        NOT NULL,
                announced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
                await conn.execute(
                    """
                    INSERT INTO anime_list (status, title)
                    SELECT $1, t FROM unnest($2::text[]) AS t
                    ON CONFLICT DO NOTHING
                    """,
                    status,
                    titles,
                )


# ---------------------------------------------------------------------------
# MAL link / snapshots / activity
# ---------------------------------------------------------------------------

@trace_function
async def mal_link_discord(username: str, discord_user_id: int) -> bool:
    """Bind a Discord user id to a MAL username. Returns False if discord_user_id
    is already bound to a different username, or if `username` doesn't exist in
    mal_profiles. Caller should ensure the row exists via mal_add_user first."""
    async with get_pool().acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT username FROM mal_profiles WHERE discord_user_id = $1",
            discord_user_id,
        )
        if existing and existing["username"] != username:
            return False
        result = await conn.execute(
            "UPDATE mal_profiles SET discord_user_id = $1 WHERE username = $2",
            discord_user_id, username,
        )
    return result.endswith("1")


@trace_function
async def mal_get_username_for_discord(discord_user_id: int) -> str | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM mal_profiles WHERE discord_user_id = $1",
            discord_user_id,
        )
    return row["username"] if row else None


@trace_function
async def mal_get_discord_for_username(username: str) -> int | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT discord_user_id FROM mal_profiles WHERE username = $1",
            username,
        )
    return row["discord_user_id"] if row and row["discord_user_id"] else None


@trace_function
async def mal_snapshot_replace(username: str, entries: list[dict]) -> list[dict]:
    """Atomically replace the snapshot for `username`. Each entry: mal_id, title,
    status, score, episodes_watched. Returns diff rows the caller can persist to
    mal_activity (only rows where episodes grew or status changed)."""
    diff: list[dict] = []
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            old_rows = await conn.fetch(
                "SELECT mal_id, status, episodes_watched FROM mal_list_snapshots WHERE username = $1",
                username,
            )
            old = {r["mal_id"]: r for r in old_rows}

            for e in entries:
                mal_id = int(e["mal_id"])
                new_status = int(e["status"])
                new_eps = int(e.get("episodes_watched") or 0)
                score = e.get("score")
                score = int(score) if score else None

                if mal_id in old:
                    delta = new_eps - int(old[mal_id]["episodes_watched"])
                    status_changed = int(old[mal_id]["status"]) != new_status
                else:
                    delta = new_eps
                    status_changed = True

                if delta > 0 or status_changed:
                    diff.append({
                        "mal_id":         mal_id,
                        "title":          e["title"],
                        "delta_episodes": max(delta, 0),
                        "new_status":     new_status if status_changed else None,
                        "score":          score,
                    })

            await conn.execute(
                "DELETE FROM mal_list_snapshots WHERE username = $1",
                username,
            )
            if entries:
                await conn.executemany(
                    """
                    INSERT INTO mal_list_snapshots
                        (username, mal_id, title, status, score, episodes_watched, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    """,
                    [
                        (
                            username,
                            int(e["mal_id"]),
                            str(e["title"]),
                            int(e["status"]),
                            int(e["score"]) if e.get("score") else None,
                            int(e.get("episodes_watched") or 0),
                        )
                        for e in entries
                    ],
                )
    return diff


@trace_function
async def mal_snapshot_get(username: str, status: int | None = None) -> list[dict]:
    async with get_pool().acquire() as conn:
        if status is None:
            rows = await conn.fetch(
                """
                SELECT mal_id, title, status, score, episodes_watched, updated_at
                FROM mal_list_snapshots WHERE username = $1
                ORDER BY title ASC
                """,
                username,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT mal_id, title, status, score, episodes_watched, updated_at
                FROM mal_list_snapshots WHERE username = $1 AND status = $2
                ORDER BY title ASC
                """,
                username, status,
            )
    return [dict(r) for r in rows]


@trace_function
async def mal_snapshot_updated_at(username: str) -> datetime | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT MAX(updated_at) AS ts FROM mal_list_snapshots WHERE username = $1",
            username,
        )
    return row["ts"] if row else None


@trace_function
async def mal_who_has(mal_id: int, statuses: list[int]) -> list[str]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT username FROM mal_list_snapshots
            WHERE mal_id = $1 AND status = ANY($2::int[])
            ORDER BY username ASC
            """,
            mal_id, statuses,
        )
    return [r["username"] for r in rows]


@trace_function
async def mal_activity_record(rows: list[dict]) -> None:
    if not rows:
        return
    async with get_pool().acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO mal_activity (username, mal_id, delta_episodes, new_status, score)
            VALUES ($1, $2, $3, $4, $5)
            """,
            [
                (
                    r["username"],
                    int(r["mal_id"]),
                    int(r["delta_episodes"]),
                    int(r["new_status"]) if r.get("new_status") is not None else None,
                    int(r["score"]) if r.get("score") is not None else None,
                )
                for r in rows
            ],
        )


@trace_function
async def mal_activity_episodes_by_month(username: str, months: int = 12) -> list[tuple[str, int]]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT to_char(date_trunc('month', recorded_at), 'YYYY-MM') AS month,
                   COALESCE(SUM(delta_episodes), 0)::int AS total
            FROM mal_activity
            WHERE username = $1
              AND recorded_at >= NOW() - ($2 || ' months')::interval
            GROUP BY 1
            ORDER BY 1 ASC
            """,
            username, str(months),
        )
    return [(r["month"], r["total"]) for r in rows]


@trace_function
async def mal_score_distribution(username: str) -> dict[int, int]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT score, COUNT(*)::int AS n
            FROM mal_list_snapshots
            WHERE username = $1 AND score IS NOT NULL AND score > 0
            GROUP BY score
            ORDER BY score ASC
            """,
            username,
        )
    return {int(r["score"]): int(r["n"]) for r in rows}


@trace_function
async def mal_activity_leaderboard(since: datetime) -> list[tuple[str, int]]:
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT username, COALESCE(SUM(delta_episodes), 0)::int AS total
            FROM mal_activity
            WHERE recorded_at >= $1
            GROUP BY username
            HAVING SUM(delta_episodes) > 0
            ORDER BY total DESC
            """,
            since,
        )
    return [(r["username"], r["total"]) for r in rows]


@trace_function
async def mal_alltime_leader() -> tuple[str, int] | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT username, COALESCE(SUM(episodes_watched), 0)::int AS total
            FROM mal_list_snapshots
            GROUP BY username
            ORDER BY total DESC
            LIMIT 1
            """
        )
    if not row or row["total"] <= 0:
        return None
    return (row["username"], row["total"])


# ---------------------------------------------------------------------------
# Episode announcements (for reaction-subscribe)
# ---------------------------------------------------------------------------

@trace_function
async def episode_announcement_record(message_id: int, series: str) -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO episode_announcements (message_id, series)
            VALUES ($1, $2)
            ON CONFLICT (message_id) DO NOTHING
            """,
            message_id, series,
        )


@trace_function
async def episode_announcement_get_series(message_id: int) -> str | None:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT series FROM episode_announcements WHERE message_id = $1",
            message_id,
        )
    return row["series"] if row else None
