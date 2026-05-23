# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bot

```bash
# Local development (requires DATABASE_URL pointing at a running Postgres)
python bot.py

# Full local stack (bot + postgres + postgres-exporter)
docker compose up -d --build
```

There is no test suite. Verify behavior by running the bot directly.

## Configuration

The bot loads config from `config/config-local.json` if it exists, otherwise falls back to `config/config.json`. The local file is gitignored and is the right place for real tokens.

```json
{
  "discord": { "token": "<your-token>" },
  "debug": true
}
```

Setting `debug: true` disables OpenTelemetry tracing **and Pyroscope profiling**, and skips starting the background tasks (`check_for_new_anime` and `_run_new_episode_check_logic`).

`DATABASE_URL` (env var, not in config file) must be set to a Postgres DSN — `bot.py` raises on startup if it's missing. In compose, this is set automatically; locally, point it at your own Postgres.

## Deployment

`Jenkinsfile` runs `docker compose build && docker compose up -d`. All container runtime config (image name, env, volumes, network, restart policy) lives in the root `docker-compose.yml` — Jenkins doesn't pass `-v` / `-e` flags directly anymore.

The bot container attaches to the external `monitoring_monitoring` network so it can reach `tempo:4317`, `pyroscope:4040`, etc. If you rename that network or change the OTel endpoint in `bot.py`, update `docker-compose.yml` in the same commit (`chore(docker): ...`).

A separate `Deploy Monitoring` stage handles the observability stack; it only runs when `monitoring/**` changes. See `monitoring/CLAUDE.md` for that flow.

### Root `docker-compose.yml`

Three services:

- **`db`** — `postgres:16-alpine`, named volume `postgres_data`, healthcheck via `pg_isready`.
- **`bot`** — built from `Dockerfile`, `container_name: mydiscordbot`, `depends_on: db (service_healthy)`. `DATABASE_URL` is wired here. Mounts use `${DISCORD_DATA_PATH:-./data}` so Jenkins can point at `/home/izilov/Desktop/discord-files` while local dev uses `./data`.
- **`postgres-exporter`** — `prometheuscommunity/postgres-exporter`, scraped by the monitoring stack's Prometheus over the shared network.

`bot` and `postgres-exporter` join `default` (for db reachability) and `monitoring` (the external `monitoring_monitoring` network). `db` stays on `default` only — it's not exposed to the monitoring network directly.

## Architecture

`bot.py` is the entry point. It registers all slash commands, sets up OTel + Pyroscope (when `debug: false`), and in `on_ready` initialises the asyncpg pool (`init_pool()` + `ensure_schema()`). Command implementations do not live in `bot.py` — they are thin wrappers that delegate to handlers in `functions/`.

```
bot.py               ← slash command registration, OTel/Pyroscope setup, DB bootstrap
config/
  consts.py          ← enums, file paths, channel IDs, Discord limits
  config.json        ← default config template
utils/
  config.py          ← AppConfig loader (prefers config-local.json)
  db.py              ← asyncpg pool + per-domain query helpers
  logger.py          ← botLogger (file + console)
  tracing.py         ← @trace_function decorator (sync + async)
  utils.py           ← shared helpers: dropdown UI, RSS parsing,
                       MAL scraping (Selenium), roulette logic, chart generation,
                       make_embed
functions/
  feed.py            ← /rss command: add/view/remove/sub/unsub
  mal.py             ← /mal and /anime_list commands
  nyaa.py            ← /nyaa torrent search (aiohttp + BeautifulSoup)
  roulettes.py       ← /roulette and /auto_roulette commands
  tasks.py           ← background loops: hourly RSS check, daily MAL refresh
  voice.py           ← /play and /leave (yt-dlp + ffmpeg)
data/                ← runtime artifacts only (gitignored): logs, downloaded files.
                       NOT persistent state — that lives in Postgres.
monitoring/          ← observability stack — see monitoring/CLAUDE.md
```

## Key patterns

**`@trace_function`** — every function (sync and async) is decorated with this. It wraps the function in an OpenTelemetry span. When `debug: true`, the tracer provider is never set up, so spans are no-ops. Do not add new functions without this decorator.

**Data persistence (Postgres)** — all state lives in PostgreSQL, accessed through `utils/db.py`. It exposes:

- `init_pool()` / `close_pool()` / `get_pool()` — asyncpg pool lifecycle.
- `ensure_schema()` — idempotent `CREATE TABLE IF NOT EXISTS` for `roulette_options`, `rss_feeds`, `rss_subscriptions`, `mal_profiles`, `anime_list`. Called once from `on_ready`.
- Per-domain helpers: `roulette_*`, `rss_*`, `mal_*`, `anime_list_*`. All decorated with `@trace_function`.

When adding a new persistent feature, add a table to `ensure_schema()` and a new group of `<domain>_*` helpers — don't reach into the pool directly from `functions/`.

**Dropdown interactions** — `dropdown_interactions()` in `utils/utils.py` is the standard way to show a Discord select menu and await the user's choice. It uses an `asyncio.Future` internally. Discord limits select menus to 25 items; `create_select_menus()` handles chunking automatically.

**Embed responses** — `make_embed()` in `utils/utils.py` is the standard response wrapper. Use it for every command reply instead of building `discord.Embed` by hand, so titles/colors/footers stay consistent.

**Background tasks** — `tasks.py` uses `discord.ext.tasks`. `_run_new_episode_check_logic` loops hourly to check for new RSS episodes (reading from `rss_feeds` / `rss_subscriptions`) and announce them to `OTAKU_CHANNEL_ID`. `check_for_new_anime` loops daily, scrapes MAL for currently-watching airing anime, and auto-adds matching RSS entries. Both tasks are only started when `debug: false`.

**New episode announcements** — `announce_new_episode()` in `tasks.py` posts to `tormag.ezpz.work` to convert a magnet link into a shareable URL, then mentions all subscribed user IDs in `OTAKU_CHANNEL_ID`.

**MAL scraping** — `scrape_mal()` in `utils/utils.py` uses Selenium with headless Chromium. Chrome must be installed (handled in `Dockerfile` via `chromium` + `chromium-driver`).

**Pyroscope profiling** — when `debug: false`, `bot.py` also starts continuous profiling against `http://pyroscope:4040` with `oncpu=False` (captures blocking I/O like Discord WS, HTTP, Selenium) and `gil_only=False` (includes native threads — ffmpeg, chromium driver).

## Channel IDs

Hardcoded in `config/consts.py`:
- `BOT_CHANNEL_ID` — general bot announcements
- `OTAKU_CHANNEL_ID` — new episode announcements and RSS notifications

## Git guidelines

### Commit message format

```
<type>(<scope>): <short summary in imperative mood>

[optional body — wrap at 72 chars]
[optional footer — Breaking change: ..., Closes #issue]
```

**Types**

| Type | When to use |
|---|---|
| `feat` | New user-visible feature or slash command |
| `fix` | Bug fix |
| `refactor` | Code change with no behavior change |
| `chore` | Deps, config, Docker, CI — no production code |
| `docs` | CLAUDE.md, README, inline comments only |
| `style` | Formatting, linting — no logic change |

**Scopes** — match the file/module being changed: `bot`, `feed`, `mal`, `nyaa`, `roulette`, `voice`, `tasks`, `utils`, `db`, `config`, `docker`, `monitoring`

**Examples**

```
# Good
feat(feed): add /rss remove command with dropdown confirmation
fix(tasks): prevent duplicate episode announcements on restart
chore(docker): pin chromium to 120.x for stable Selenium compat

# Bad
fix stuff
update bot.py
WIP changes
```

### Commit discipline

- **One logical change per commit.** Don't bundle a feature with an unrelated bugfix.
- If a change touches `bot.py` and a `functions/` file for the same feature, that's one commit. If it touches `feed.py` and `mal.py` for unrelated reasons, split it.
- Keep commits small enough that `git revert` is safe to use on each one.
- Never commit: `config/config-local.json`, `data/`, `.env`, `monitoring/.env`, `monitoring/alertmanager/discord-webhook-url`, tokens, or secrets — these are gitignored for a reason.

### Branches and pushing

- Always work on a branch: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`
- Open a PR — never push directly to `main` or force-push it
- Squash trivial fixup commits before pushing (`git rebase -i`)
- After merging a stable state, tag it: `git tag v1.x.x`
