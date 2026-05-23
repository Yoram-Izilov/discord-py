# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bot

```bash
# Local development
python bot.py

# Docker
docker build -t mydiscordbot .
docker run mydiscordbot
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

Setting `debug: true` disables OpenTelemetry tracing and skips starting the background tasks (`check_for_new_anime` and `_run_new_episode_check_logic`).

## Deployment

Production deploys go through `Jenkinsfile` at the repo root. The pipeline builds the `mydiscordbot` image, stops + removes any running `discordbot` container, prunes dangling images, then runs a fresh container and verifies it's up.

Runtime container settings (from the pipeline — keep these in sync if you change them):

- Image / container name: `mydiscordbot`
- Network: `monitoring_monitoring` (external Docker network — the bot expects Tempo to be reachable at `tempo:4317` for OTel export)
- Env: `OTEL_EXPORTER_OTLP_ENDPOINT=tempo:4317`
- Volumes (host → container):
  - `/home/izilov/Desktop/discord-files/` → `/app/data/`
  - `/home/izilov/Desktop/discord-files/config.json` → `/app/config/config.json`
- Restart policy: `unless-stopped`

If you change the image name, mount paths, network, or OTel endpoint in code or the Dockerfile, update the `Jenkinsfile` in the same commit (`chore(docker): ...`).

The monitoring stack lives in `monitoring/docker-compose.yml` (Prometheus, Grafana, Loki, Promtail, Tempo, OTel Collector, Alertmanager, Pyroscope, node-exporter). It is deployed by a separate `Deploy Monitoring` stage in `Jenkinsfile` that runs only when files under `monitoring/**` change. Grafana's admin password is read from `GRAFANA_ADMIN_PASSWORD`, injected by Jenkins from a **Secret text** credential with ID `grafana-admin-password` (Manage Jenkins → Credentials). For local dev, put `GRAFANA_ADMIN_PASSWORD=...` in `monitoring/.env` (gitignored; see `monitoring/.env.example`).

## Architecture

`bot.py` is the entry point. It registers all slash commands and wires them to handler functions in `functions/`. The command implementations do not live in `bot.py` — they are thin wrappers that delegate immediately.

```
bot.py               ← slash command registration + OTel setup
config/
  consts.py          ← enums, file paths, channel IDs, Discord limits
  config.json        ← default config template
utils/
  config.py          ← AppConfig loader (prefers config-local.json)
  logger.py          ← botLogger (file + console)
  tracing.py         ← @trace_function decorator (sync + async)
  utils.py           ← shared helpers: JSON/text I/O, dropdown UI, RSS parsing,
                       MAL scraping (Selenium), roulette logic, chart generation
functions/
  feed.py            ← /rss command: add/view/remove/sub/unsub
  mal.py             ← /mal and /anime_list commands
  nyaa.py            ← /nyaa torrent search (aiohttp + BeautifulSoup)
  roulettes.py       ← /roulette and /auto_roulette commands
  tasks.py           ← background loops: hourly RSS check, daily MAL refresh
  voice.py           ← /play and /leave (yt-dlp + ffmpeg)
data/                ← runtime state (gitignored)
  rss_data.json      ← RSS subscriptions {series, title, link, pubDate, subs:[user_ids]}
  mal_profile.txt    ← MAL usernames (one per line)
  anime_list/{n}.txt ← cached anime lists keyed by MAL status int
  roulette_options.txt ← saved auto-roulette option sets
```

## Key patterns

**`@trace_function`** — every function (sync and async) is decorated with this. It wraps the function in an OpenTelemetry span. When `debug: true`, the tracer provider is never set up, so spans are no-ops. Do not add new functions without this decorator.

**Dropdown interactions** — `dropdown_interactions()` in `utils/utils.py` is the standard way to show a Discord select menu and await the user's choice. It uses an `asyncio.Future` internally. Discord limits select menus to 25 items; `create_select_menus()` handles chunking automatically.

**Data persistence** — all state is flat files in `data/`. JSON files use `load_json_data`/`save_json_data`; plain text files use `load_text_data`/`save_text_data` (one item per line). Both helpers in `utils/utils.py` handle missing files gracefully.

**Background tasks** — `tasks.py` uses `discord.ext.tasks`. `_run_new_episode_check_logic` loops hourly to check for new RSS episodes and announce them to `OTAKU_CHANNEL_ID`. `check_for_new_anime` loops daily, scrapes MAL for currently-watching airing anime, and auto-adds matching RSS entries. Both tasks are only started when `debug: false`.

**New episode announcements** — `announce_new_episode()` in `tasks.py` posts to `tormag.ezpz.work` to convert a magnet link into a shareable URL, then mentions all subscribed user IDs in `OTAKU_CHANNEL_ID`.

**MAL scraping** — `scrape_mal()` in `utils/utils.py` uses Selenium with headless Chromium. Chrome must be installed (handled in Dockerfile via `chromium` + `chromium-driver`).

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
 
**Scopes** — match the file/module being changed: `bot`, `feed`, `mal`, `nyaa`, `roulette`, `voice`, `tasks`, `utils`, `config`, `docker`
 
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
- Never commit: `config/config-local.json`, `data/`, `.env`, tokens, or secrets — these are gitignored for a reason.
### Branches and pushing
 
- Always work on a branch: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`
- Open a PR — never push directly to `main` or force-push it
- Squash trivial fixup commits before pushing (`git rebase -i`)
- After merging a stable state, tag it: `git tag v1.x.x`