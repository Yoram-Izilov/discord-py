---
name: sync-docker-jenkins
description: Audit Dockerfile, Jenkinsfile, and docker-compose.yml for drift in the values CLAUDE.md says must stay in sync (image name, network, OTel endpoint, mount paths, restart policy). Use when the user asks to verify Docker/Jenkins sync, or after editing any of those three files.
---

# Sync Docker / Jenkins / docker-compose

CLAUDE.md ("Deployment" section) lists values that must agree across `Dockerfile`, `Jenkinsfile`, and `docker-compose.yml`. This skill reads all three and flags drift. It is read-only -- it does not modify files.

## What to check

| Value | Where to look | Expected |
|---|---|---|
| Image / container name | `Jenkinsfile` (`IMAGE_NAME`), `docker-compose.yml` (`container_name:`) | `mydiscordbot` |
| External network | `docker-compose.yml` (`networks:` block) | `monitoring_monitoring` |
| OTel endpoint | `bot.py` (`OTLPSpanExporter(endpoint=...)`); env override in compose if present | `tempo:4317` |
| Data mount | `Dockerfile` (`WORKDIR` / `mkdir`), `docker-compose.yml` (`volumes:`) | host data dir -> `/app/data` |
| Config mount | `docker-compose.yml` (`volumes:`) | host config.json -> `/app/config/config.json` |
| Restart policy | `docker-compose.yml` (`restart:`) | `unless-stopped` |

## How to run

1. Read `Dockerfile`, `Jenkinsfile`, `docker-compose.yml`, and the OTel setup section of `bot.py`.
2. Build a markdown table showing the actual value found in each file (or `-` if not present).
3. Call out every row where values disagree, or where a value is missing in a file that should set it. Give the specific fix.
4. Verify these common drift cases explicitly:
   - `Jenkinsfile`'s `IMAGE_NAME` env var matches `docker-compose.yml`'s `container_name`.
   - `docker-compose.yml` references the `monitoring_monitoring` external network.
   - `bot.py`'s OTel endpoint is `tempo:4317` (not `localhost` or a different name).
   - All data mount destinations resolve to `/app/data`.
5. If everything is consistent, say so plainly: "all values are in sync, no drift detected".

## Output format

A markdown table plus a short prose section listing any drift with suggested fixes. Don't modify files -- this is an audit only. If the user wants the drift fixed afterward, they'll ask.

## Why this matters

The Jenkins pipeline (`docker compose build && docker compose up -d`) depends on the compose file being correct. If `bot.py` exports to `tempo:4317` but the container isn't on the `monitoring_monitoring` network, traces are silently dropped. If the data mount destination doesn't match `/app/data` (where the code reads/writes state), the bot starts with empty `data/` on every deploy, losing RSS subscriptions, roulette options, and the MAL anime list cache.
