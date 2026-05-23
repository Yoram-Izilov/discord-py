# monitoring/CLAUDE.md

Guidance for the monitoring stack. The root `CLAUDE.md` covers the bot itself; this file loads only when something under `monitoring/` is being edited.

## Stack

All services are defined in `docker-compose.yml` and joined to the `monitoring` network (which the bot's root compose attaches to as the external `monitoring_monitoring` network — see below).

| Service | Image | Purpose |
|---|---|---|
| `prometheus` | `prom/prometheus:v3.11.3` | Metrics. Rules in `prometheus/rules/`. Remote-write receiver enabled. |
| `node-exporter` | `prom/node-exporter:v1.11.1` | Host metrics. Uses `network_mode: host`. |
| `grafana` | `grafana/grafana:13.0.1` | UI. Provisioning + dashboards mounted from `grafana/`. |
| `loki` | `grafana/loki:3.7.2` | Logs. Rules in `loki/rules/fake/`. |
| `promtail` | `grafana/promtail:3.4.1` | Log shipper. Reads `/var/lib/docker/containers` and `/var/log`. |
| `tempo` | `grafana/tempo:2.10.5` | Traces. Receives OTel on `4317`. |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.111.0` | OTel gateway. Exposes `4317`/`4318`. |
| `alertmanager` | `prom/alertmanager:v0.28.1` | Alerts → Discord webhook. |
| `pyroscope` | `grafana/pyroscope:1.10.0` | Continuous profiling. Bot pushes to `http://pyroscope:4040`. |

`postgres-exporter` runs in the **root** `docker-compose.yml` (not here) and is scraped by this Prometheus over the shared network.

The bot exports traces to `tempo:4317` (hardcoded in `bot.py`) and profiles to `http://pyroscope:4040`.

## Deploy flow

`Jenkinsfile` at the repo root has a `Deploy Monitoring` stage that runs **only when `monitoring/**` changes** (`when { changeset 'monitoring/**' }`). The stage:

1. `rsync -a --delete monitoring/` → `/home/izilov/Desktop/discord-monitoring/`
2. Writes the Discord webhook secret to `alertmanager/discord-webhook-url` (gitignored)
3. `docker compose -p monitoring -f /home/izilov/Desktop/discord-monitoring/docker-compose.yml up -d`

The `-p monitoring` flag pins the project name so the network resolves to `monitoring_monitoring` — that's the name the bot's root compose expects to attach to as `external: true`. Do not remove `-p monitoring`.

## Credentials (Jenkins secret-text)

| Credential ID | Used as | Consumed by |
|---|---|---|
| `grafana-admin-password` | env `GRAFANA_ADMIN_PASSWORD` | Grafana via `GF_SECURITY_ADMIN_PASSWORD` |
| `discord-alertmanager-webhook-url` | written to `alertmanager/discord-webhook-url` | Alertmanager via `webhook_url_file:` |

For local dev: put `GRAFANA_ADMIN_PASSWORD=...` in `monitoring/.env` and the Discord webhook URL in `monitoring/alertmanager/discord-webhook-url`. Both are gitignored.

## Alertmanager Discord webhook

`alertmanager.yml` references the webhook via `webhook_url_file: /etc/alertmanager/discord-webhook-url` — never inline the URL into the YAML. The file is bind-mounted read-only into the container.

## Host-path gotcha (Jenkins)

Jenkins runs inside a container but talks to the **host** Docker daemon, so the bind-mount paths in `docker-compose.yml` (`./prometheus/prometheus.yml`, etc.) are resolved by the host, not by the Jenkins container. That's why the deploy rsyncs the whole `monitoring/` tree to `/home/izilov/Desktop/discord-monitoring/` on the host and runs compose from there.

For this to work, the Jenkins container itself must have `/home/izilov/Desktop/discord-monitoring` bind-mounted at the **same path** (so `docker compose -f /home/izilov/...` inside Jenkins points at the same file the host daemon will resolve mounts against). `rsync` must be installed in the Jenkins image.

## When editing files here

- Touching a Prometheus rule, Grafana dashboard, Tempo config, etc. only requires re-running the `Deploy Monitoring` stage — push the change, Jenkins handles it.
- Adding a new service: also confirm whether the bot or `postgres-exporter` needs to reach it; if so, no extra wiring needed (they're already on `monitoring_monitoring`), but document the port/endpoint in the bot's CLAUDE.md if it's user-visible.
- Changing the network name or removing `-p monitoring`: breaks the bot's `monitoring_monitoring` external attachment. Don't.
