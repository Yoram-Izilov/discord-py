import asyncio
import time
from typing import Any

import aiohttp

from config.consts import Statuses
from utils.logger import botLogger
from utils.tracing import trace_function

JIKAN_BASE = "https://api.jikan.moe/v4"
MAL_LIST_LOAD = "https://myanimelist.net/animelist/{user}/load.json"
MAL_PAGE_SIZE = 300

_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()

_rate_sem = asyncio.Semaphore(2)
_rate_min_interval = 0.35
_last_request_at = 0.0
_rate_lock = asyncio.Lock()

_cache: dict[str, tuple[float, Any]] = {}

_TTL = {
    "/seasons/now":  3600,
    "/anime":        21600,
    "/anime_search": 1800,
    "mal_list":      1800,
}

# Mapping from our Statuses enum to MAL's numeric status param for load.json.
_MAL_STATUS_NUMERIC = {
    Statuses.CURRENTLY_WATCHING.value: 1,
    Statuses.COMPLETED.value:          2,
    Statuses.ON_HOLD.value:            3,
    Statuses.DROPPED.value:            4,
    Statuses.PLAN_TO_WATCH.value:      6,
}


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        async with _session_lock:
            if _session is None or _session.closed:
                _session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=15)
                )
    return _session


def _cache_key(path: str, params: dict | None) -> str:
    if not params:
        return path
    canonical = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{path}?{canonical}"


def _ttl_for(path: str, params: dict | None) -> int:
    if path == "/seasons/now":
        return _TTL["/seasons/now"]
    if path.startswith("/users/"):
        return _TTL["/users"]
    if path == "/anime" and params and "q" in params:
        return _TTL["/anime_search"]
    if path.startswith("/anime/"):
        return _TTL["/anime"]
    return 600


async def _throttled_get_url(
    url: str,
    params: dict | None = None,
    *,
    headers: dict | None = None,
    cache_key: str | None = None,
    ttl: int = 0,
) -> Any | None:
    """Generic throttled GET with retry. Caches when cache_key + ttl are provided."""
    now = time.monotonic()
    if cache_key:
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    global _last_request_at
    async with _rate_sem:
        async with _rate_lock:
            wait = _rate_min_interval - (time.monotonic() - _last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            _last_request_at = time.monotonic()

        session = await _get_session()
        for attempt in range(2):
            try:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status in (401, 403, 404):
                        return None
                    if resp.status == 429:
                        retry_after = float(resp.headers.get("Retry-After", "1"))
                        botLogger.warning("upstream 429 on %s, sleeping %ss", url, retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    if 500 <= resp.status < 600:
                        botLogger.warning("upstream %s on %s, retrying", resp.status, url)
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
            except aiohttp.ClientError as e:
                botLogger.warning("network error on %s: %s", url, e)
                if attempt == 1:
                    raise
                await asyncio.sleep(0.5)
                continue

            if cache_key and ttl > 0:
                _cache[cache_key] = (now + ttl, data)
            return data
    return None


@trace_function
async def _throttled_get(path: str, params: dict | None = None, *, use_cache: bool = True) -> dict | None:
    key = _cache_key(path, params) if use_cache else None
    ttl = _ttl_for(path, params) if use_cache else 0
    return await _throttled_get_url(f"{JIKAN_BASE}{path}", params, cache_key=key, ttl=ttl)


@trace_function
async def _mal_load_page(username: str, status_numeric: int, offset: int) -> list[dict] | None:
    """Fetch one page (up to MAL_PAGE_SIZE entries) of a user's list from MAL's
    internal load.json endpoint. Returns [] when the list is private/missing,
    None on hard network failure."""
    url = MAL_LIST_LOAD.format(user=username)
    params = {"status": status_numeric, "offset": offset}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; mydiscordbot/1.0)",
        "Accept": "application/json",
    }
    key = f"mal_list:{username}:{status_numeric}:{offset}"
    data = await _throttled_get_url(
        url, params, headers=headers, cache_key=key, ttl=_TTL["mal_list"]
    )
    if data is None:
        return []
    return data if isinstance(data, list) else []


@trace_function
async def get_current_season() -> list[dict]:
    results: list[dict] = []
    page = 1
    while True:
        data = await _throttled_get("/seasons/now", {"page": page})
        if not data:
            break
        results.extend(data.get("data", []))
        pagination = data.get("pagination") or {}
        if not pagination.get("has_next_page"):
            break
        page += 1
        if page > 10:
            break
    return results


@trace_function
async def get_anime(mal_id: int) -> dict | None:
    data = await _throttled_get(f"/anime/{mal_id}")
    return data.get("data") if data else None


@trace_function
async def get_anime_full(mal_id: int) -> dict | None:
    data = await _throttled_get(f"/anime/{mal_id}/full")
    return data.get("data") if data else None


@trace_function
async def search_anime(query: str, limit: int = 10) -> list[dict]:
    if not query:
        return []
    data = await _throttled_get("/anime", {"q": query, "limit": limit})
    return data.get("data", []) if data else []


@trace_function
async def get_user_list(username: str, status: int | None = None) -> list[dict]:
    """Fetch a user's MAL anime list via MAL's internal load.json endpoint.
    Jikan v4 does not expose user lists, so we hit MAL directly.

    Returns normalized entries with keys: mal_id, title, status, score,
    episodes_watched. Empty list if the user doesn't exist or has a private list."""
    if not username:
        return []

    if status is not None and status in _MAL_STATUS_NUMERIC:
        status_codes = [_MAL_STATUS_NUMERIC[status]]
    else:
        status_codes = list(_MAL_STATUS_NUMERIC.values())

    # Reverse map MAL numeric status -> our Statuses enum value.
    reverse = {v: k for k, v in _MAL_STATUS_NUMERIC.items()}

    results: list[dict] = []
    for status_numeric in status_codes:
        offset = 0
        while True:
            page = await _mal_load_page(username, status_numeric, offset)
            if not page:
                break
            for entry in page:
                mal_id = entry.get("anime_id")
                title = entry.get("anime_title")
                if not mal_id or not title:
                    continue
                raw_status = entry.get("status", status_numeric)
                normalized_status = reverse.get(int(raw_status), status)
                if normalized_status is None:
                    continue
                score = entry.get("score")
                results.append({
                    "mal_id":           int(mal_id),
                    # MAL serialises numeric-looking titles as JSON numbers
                    # (e.g. the anime "86"). Force a string here so downstream
                    # asyncpg INSERTs against a TEXT column don't blow up.
                    "title":            str(title),
                    "status":           int(normalized_status),
                    "score":            int(score) if score else None,
                    "episodes_watched": int(entry.get("num_watched_episodes") or 0),
                })
            if len(page) < MAL_PAGE_SIZE:
                break
            offset += MAL_PAGE_SIZE
            if offset >= 7500:
                botLogger.warning("get_user_list hit 7500-entry safety stop for %s", username)
                break
    return results


@trace_function
async def close() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None
