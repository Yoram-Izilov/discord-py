# discord-py

> An anime-focused Discord bot - MyAnimeList integration, torrent RSS, voice/music, and games - instrumented end-to-end with distributed tracing and continuous profiling.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.7.1-5865F2?style=flat&logo=discord&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat&logo=docker&logoColor=white)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-traces-425CC7?style=flat&logo=opentelemetry&logoColor=white)
![Pyroscope](https://img.shields.io/badge/Pyroscope-profiling-F46800?style=flat)

`mydiscordbot` is a feature-rich bot for an anime community: it tracks MyAnimeList profiles, watches SubsPlease torrent RSS feeds for new episodes, plays YouTube audio in voice channels, and runs games like a synopsis-guessing quiz. Every handler is wrapped in an OpenTelemetry span and the whole process is continuously profiled, so its behavior is observable from the same Grafana stack that watches the rest of the box.

> The authoritative deep-dive lives in [`CLAUDE.md`](CLAUDE.md). This README is the operator's overview.

## Architecture

`bot.py` is the entry point: it registers the slash commands, sets up tracing/profiling (unless `debug: true`), and bootstraps the asyncpg pool in `on_ready`. Commands are thin wrappers that delegate to handlers in `functions/`; all state lives in PostgreSQL behind `utils/db.py`. The observability stack itself is **not** here - it lives in [`home-server`](https://github.com/Yoram-Izilov/home-server); the bot just attaches to the `monitoring_monitoring` network it creates.

```mermaid
flowchart TB
    discord(["Discord"])

    subgraph botc["mydiscordbot container"]
        entry["bot.py<br/>slash-command registry · OTel/Pyroscope init · DB bootstrap"]
        fns["functions/<br/>feed · mal · voice · queue · nyaa · season · quiz · roulettes"]
        utils["utils/<br/>db.py · tracing.py · utils.py"]
        tasks["background tasks<br/>hourly RSS · daily MAL · weekly leaderboard"]
    end

    pg[("PostgreSQL 16")]
    exporter["postgres-exporter :9187"]

    subgraph mon["monitoring_monitoring (external - home-server)"]
        tempo["tempo :4317"]
        pyro["pyroscope :4040"]
        prom["prometheus"]
    end

    discord <-->|slash commands · events| entry
    entry --> fns --> utils
    tasks --> utils
    utils -->|asyncpg pool| pg
    exporter --- pg
    entry -->|traces| tempo
    entry -->|wall-clock profiles| pyro
    prom -->|scrape| exporter
```

## Features

All commands are Discord slash commands. Multi-action commands (`/rss`, `/mal`, `/anime_list`, `/auto_roulette`) present a choice picker.

**MyAnimeList**

| Command | What it does |
|---|---|
| `/mal` | Add / view / remove tracked MAL users. |
| `/mal_link` · `/mal_unlink` | Bind (or unbind) your Discord account to a MAL username. |
| `/anime_list` | Update or view your *watching* / *plan-to-watch* lists. |
| `/mal_compare` | Compare your list against another linked member. |
| `/mal_stats` | Your MAL activity charts (episodes/month, score distribution). |
| `/anime_recommend` · `/next_anime` | Random pick from your plan-to-watch list. |
| `/who_is_watching` | Which linked members are currently watching a given anime. |

**Episodes & torrents**

| Command | What it does |
|---|---|
| `/rss` | Add / view / subscribe / unsubscribe / remove SubsPlease RSS feeds. |
| `/next_episode` | Next airing episode for your subscriptions (or look up one anime). |
| `/season_anime` | Browse this season's airing anime; subscribe with the 🔔 button. |
| `/nyaa` | Search torrents on Nyaa. |

**Voice & music**

| Command | What it does |
|---|---|
| `/play` · `/queue_play` | Play / queue YouTube audio (URL or search term). |
| `/skip` · `/queue` · `/now_playing` | Control and inspect the queue. |
| `/op` | Queue an anime opening. · `/leave` disconnects. |

**Games & utility**

| Command | What it does |
|---|---|
| `/anime_quiz` | 60-second guess-the-anime-from-its-synopsis game. |
| `/roulette` · `/auto_roulette` | Weighted random picker with a pie chart; save reusable option sets. |
| `/help` | Every command, grouped by feature. |

**Background automation** (only when `debug: false`): hourly RSS check → announces new episodes to the otaku channel; daily MAL scrape that auto-adds RSS feeds for currently-watching airing anime; daily MAL list snapshots (powering `/mal_stats`); a weekly watch leaderboard. React 🔔 on an announcement to auto-subscribe to that series.

## Tech stack

- **Runtime** - Python 3.12, [discord.py](https://discordpy.readthedocs.io/) 2.7.1, asyncio throughout.
- **Data** - PostgreSQL 16 via `asyncpg`; metrics exposed by `prometheuscommunity/postgres-exporter`.
- **Media** - `yt-dlp` + `ffmpeg` (+ `deno` as yt-dlp's JS runtime) for voice; `PyNaCl` for voice encryption.
- **Scraping / matching** - Selenium + headless Chromium (MAL), `aiohttp` + BeautifulSoup (Nyaa), `scikit-learn` + `fuzzywuzzy` for the quiz and season↔RSS matching; `matplotlib` for charts.
- **Observability** - OpenTelemetry SDK + OTLP exporter, `pyroscope-io`.

## Repo layout

```
discord-py/
├── bot.py                  # entry point: command registry, OTel/Pyroscope, DB bootstrap
├── config/
│   ├── consts.py           # enums, file paths, channel IDs, Discord limits
│   ├── config.json         # default template (debug + token placeholder)
│   └── config-local.json   # gitignored - real token lives here
├── utils/
│   ├── db.py               # asyncpg pool + ensure_schema() + per-domain helpers
│   ├── tracing.py          # @trace_function decorator (sync + async spans)
│   ├── utils.py            # dropdowns, RSS/MAL parsing, charts, make_embed
│   └── config.py, logger.py
├── functions/              # one module per feature area (feed, mal, voice, …)
├── Dockerfile              # python:3.12.7-slim + ffmpeg + chromium + deno, non-root
├── docker-compose.yml      # db + bot + postgres-exporter
├── Jenkinsfile             # build → up -d → verify
└── CLAUDE.md
```

## Quick start

```bash
# 1. Configure the token (gitignored - never commit it)
cp config/config.json config/config-local.json
#   edit config-local.json → set discord.token, and "debug": true for local runs

# 2a. Full local stack (bot + Postgres + exporter)
docker compose up -d --build

# 2b. …or run the bot alone against your own Postgres
export DATABASE_URL="postgresql://botuser:botpassword@localhost:5432/discordbot"
python bot.py
```

There is no test suite - verify behavior by running the bot and exercising commands in Discord. Running with `debug: true` is the recommended local mode: it turns OpenTelemetry, Pyroscope, and the background tasks **off**, so you don't need the monitoring stack running.

## Configuration

| Setting | Where | Notes |
|---|---|---|
| Discord token | `config/config-local.json` → `discord.token` | Gitignored. Falls back to `config/config.json` if absent. |
| `debug` | same file | `true` disables tracing, profiling, **and** background tasks. |
| `DATABASE_URL` | environment | Postgres DSN; `bot.py` raises on startup if missing. Set automatically in compose. |
| `DISCORD_DATA_PATH` | environment (deploy) | Host mount for `data/` + config. Defaults to `./data` locally. |

`db.py` owns the schema (`ensure_schema()`, idempotent) and all queries: roulette option sets, RSS feeds & subscriptions, MAL profiles & cached lists, daily MAL snapshots (for `/mal_stats`), and episode-announcement records (for 🔔 subscriptions). Add new persistent state as a table in `ensure_schema()` plus a group of `<domain>_*` helpers - never reach into the pool from `functions/`.

## Observability

When `debug: false`, `bot.py` wires up:

- **Tracing** - service `mydiscordbot`, OTLP/gRPC → `tempo:4317`; asyncio + discord.py auto-instrumented, and every handler carries a `@trace_function` span.
- **Profiling** - continuous wall-clock profiles → `http://pyroscope:4040` with `oncpu=False` (captures blocking I/O: Discord WS, HTTP, Selenium) and `gil_only=False` (includes native threads: ffmpeg, the Chromium driver).
- **Database metrics** - `postgres-exporter` is scraped by the `home-server` Prometheus at `postgres-exporter:9187` over the shared network.

These endpoints (`tempo`, `pyroscope`, `postgres-exporter`) resolve only because the bot joins the external `monitoring_monitoring` network. Rename that network and tracing/profiling silently stop.

## Deployment

[`Jenkinsfile`](Jenkinsfile) runs `docker compose build && docker compose up -d` on merge to `main`, prunes dangling images, then verifies the `mydiscordbot` container is running. All runtime config (image name, env, volumes, network, restart policy) lives in [`docker-compose.yml`](docker-compose.yml) - Jenkins passes no `-v`/`-e` flags. The deploy host mounts data at `DISCORD_DATA_PATH` (default `/home/izilov/Desktop/discord-files`).

**Compose services:** `db` (`postgres:16-alpine`, `default` net only), `bot` (`mydiscordbot`, on `default` + `monitoring`), and `postgres-exporter` (`v0.17.1`, on `default` + `monitoring`). The dev-only credentials in compose (`botuser` / `botpassword`) are for the local Postgres container.

## Conventions

- **Branch + PR, never push to `main`.** Branches: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`. One logical change per commit.
- **Commit format** `<type>(<scope>): <summary>`, enforced by the `verify-commit-message` hook. Types: `feat · fix · refactor · chore · docs · style`. Scopes: `bot · feed · mal · nyaa · roulette · voice · tasks · utils · db · config · docker`.
- **Every handler gets `@trace_function`** and replies via `make_embed` - the `warn-missing-trace` hook flags omissions.
- **`.claude/` skills** - `/add-slash-command` scaffolds a new command (handler + registration); `/sync-docker-jenkins` audits Dockerfile/Jenkinsfile/compose for drift.
- Secrets (`config/config-local.json`, `.env`, `data/`) are gitignored and blocked from `git add` by the `block-sensitive-files` hook.

## Part of the yoram-izilov.com stack

| Repo | Role |
|---|---|
| [home-server](https://github.com/Yoram-Izilov/home-server) | Monitoring stack + Jenkins; creates the `monitoring_monitoring` network and scrapes this bot's exporter. |
| **discord-py** (this repo) | The bot; emits traces/profiles and exposes `postgres-exporter`. |
| [portfolio](https://github.com/Yoram-Izilov/portfolio) | SvelteKit site whose [Discord-bot case study](https://www.yoram-izilov.com/work/discord-bot) features this project. |
