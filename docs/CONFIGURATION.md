# Configuration

Everything is configured with environment variables; the defaults are safe for a single server.
Back to the [documentation index](README.md).

- [Required in production](#required-in-production)
- [Detection policy](#detection-policy)
- [IP strikes and bans](#ip-strikes-and-bans)
- [1D-CNN model and retraining](#1d-cnn-model-and-retraining)
- [Storage, Redis and logs](#storage-redis-and-logs)
- [Network and server](#network-and-server)
- [Prometheus metrics](#prometheus-metrics)
- [Telegram and Discord alerts](#telegram-and-discord-alerts)

## Required in production

| Variable | Why |
| :--- | :--- |
| `SYNAPSE_SECRET_KEY` | Signs challenges and keys every HMAC (device penalty, trajectory fingerprint, shape hash). If unset, a key is generated and kept in a local file. **Every server/pod must share the same value**, otherwise tokens and replay checks only work on the pod that issued them. Rotating it forgets at most ~1 hour of replay fingerprints and 60 s of device penalties. |
| `SYNAPSE_ADMIN_SECRET` | Protects admin endpoints (`/api/clear`, metrics, log export, dashboard console). Admin endpoints return the same 401 for every failure; the reason (`not configured` / `invalid` / `missing`) is written to the `synapse_shield.main` logger. |
| `SYNAPSE_REDIS_URL` | Needed when you run more than one worker or server, so nonces, strikes and bans are shared (see [Storage](#storage-redis-and-logs)). |
| `SYNAPSE_TRUSTED_PROXIES` | Behind a load balancer or CDN, list its addresses so the real client IP is read from `CF-Connecting-IP` / `X-Forwarded-For`. Default `127.0.0.1,::1,localhost`; CIDR ranges are accepted. |

## Detection policy

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `SYNAPSE_ENABLE_POW` | `0` (adapters) | Gray-area (risk 35-55) proof-of-work challenge. The built-in server (`synapse-shield run`) always challenges the gray area; set `1` for the same behaviour in the framework adapters. |
| `SYNAPSE_KEYBOARD_ONLY_CHALLENGE` | `1` | Keyboard-only sessions (no mouse movement, at least 3 keystrokes) that would otherwise be allowed get a challenge even with proof-of-work off. |
| `SYNAPSE_SHORT_TRACE_CHALLENGE` | `1` | Same for short pointer traces (<40 samples) whose risk was capped. Short humanised bots pass more often without proof-of-work, so keep this on (or enable proof-of-work). |
| `SYNAPSE_TRAJECTORY_REPLAY` | `1` | Keyed 64-bit fingerprint of each allowed trajectory; a re-sent trace with a fresh token is blocked as `REPLAY_TRAJECTORY`. Consumed only on `allow`, so SDK retries after a challenge or an expired token are not replays. Adding 1 px of noise defeats the exact fingerprint; the in-session shape check still applies. |
| `SYNAPSE_TRAJECTORY_FP_TTL` | `3600` | How long a fingerprint is remembered (seconds, minimum 60). |
| `SYNAPSE_MIN_ELAPSED_MS` | `1500` | Minimum challenge age; faster submissions are treated as automated. |
| `SYNAPSE_TOKEN_BINDING` | (lenient) | Challenges are bound to the client's /24 (IPv4) or /64 (IPv6) subnet and User-Agent, and a mismatch is always rejected (token relay). `strict` additionally rejects tokens that carry no binding at all (challenges issued without client details). |
| `SYNAPSE_MAX_REQ_10S` | `100` | Requests per IP per 10 s before a 15-minute ban. Shared by the built-in server and the adapters. |

Per-route options on every adapter: `max_risk_score` (default 50, the block threshold), `accessibility_mode` (scales kinematic risk down for assistive-device users), `mode="shadow"` (see [Shadow mode](SHADOW_MODE.md)).

**Challenge cost.** Keyboard-only and short-trace challenges always use difficulty 5 (about a million SHA-256 hashes, a few seconds on a phone), and a solved proof-of-work lowers the risk by 10 points (20 elsewhere in the gray area). It raises the cost of automation; it does not prove that a visitor is human.

## IP strikes and bans

- **4 strikes in 60 s ban the IP for 60 s.** Strikes are token errors (replay, forged, malformed, stale, relay; expired tokens are not strikes) and hard violations (no interaction, scroll-only, webdriver / stealth, session invariance on the same IP + User-Agent, trajectory replay) or Bot verdicts with risk ≥ 85.
- **Borderline Bot verdicts** block the request and add a 60 s +50 penalty to that device only: the key is HMAC(IP + User-Agent), so one bot behind a shared NAT/CGNAT does not penalise everyone else.
- **Token errors** (double submit, network retry) never penalise the device, only the IP strike counter.
- A repeated trajectory shape seen only across User-Agents on the same IP blocks the request but is not an IP strike, so it cannot be used to ban a shared IP.
- Blocked requests are kept in the session history marked as blocked and are not used as the reference for history-only invariance checks, so an attacker sharing a CGNAT IP and a common User-Agent cannot poison a victim's session.

## 1D-CNN model and retraining

The 1D-CNN runs in **shadow mode by default**: it is computed (`details["ai_raw_score"]`) but does not affect the decision. The bundled weights were trained on synthetic noise only and blocked about 19% of real human windows in production, so they are not used to decide.

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `SYNAPSE_CNN_MODE` | `shadow` | `enforce` lets the CNN score count. Only enable it with weights you validated on your own traffic. |
| `SYNAPSE_WEIGHTS_PATH` | bundled weights | Weights to load. A `synapse_weights.npz` in the working directory is **not** loaded implicitly (a warning is logged). |

```bash
synapse-shield retrain --epochs 5 --output /data/synapse_weights.npz   # needs --output or SYNAPSE_WEIGHTS_PATH
export SYNAPSE_WEIGHTS_PATH=/data/synapse_weights.npz
export SYNAPSE_CNN_MODE=enforce
```

Retraining needs stored traces (`SYNAPSE_STORE_RAW_TELEMETRY=1`); without them use `retrain --bootstrap`. A saturated or non-finite model is refused and not written.

## Storage, Redis and logs

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `SYNAPSE_REDIS_URL` (or `REDIS_URL`) | unset → SQLite | Shared nonces, strikes, bans and fingerprints across workers/servers (`SET NX EX`). If Redis is down, each pod falls back to its local SQLite: bans stay enforced, but a token can be replayed once per pod during the outage (bounded by the 60 s token life and the client binding hash). Run Redis highly available and monitor it if that matters to you. |
| `SYNAPSE_DB_PATH` | `<tmp>/synapse_shield.db` | SQLite database (WAL). |
| `SYNAPSE_STORE_RAW_TELEMETRY` | `0` | `1` keeps full traces in the log (coordinates and timings; typed characters are always masked) so `retrain` can learn from your traffic. |
| `SYNAPSE_PRIVACY_MODE` | `strict` | Log rows keep a masked IP (/24, /64) and a coarse User-Agent family (`Chrome/131 Windows`); `hash` keeps HMACs; `off` keeps raw values. |
| `SYNAPSE_LOG_RETENTION_DAYS` | `14` | Log retention, enforced periodically while the server runs. |
| `SYNAPSE_LOG_PRUNE_INTERVAL_SEC` | `600` | How often the retention clean-up runs. |
| `SYNAPSE_DATASET_PATH` | `<tmp>/synapse_dataset.db` | Store for the admin-only `/api/collect_dataset` endpoint (raw traces, 14-day retention). |

What is processed, stored and for how long: [Privacy notes for operators](PRIVACY_OPERATOR_NOTES.md).

## Network and server

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `SYNAPSE_CORS_ORIGINS` | none | Comma-separated origins allowed to call the built-in server. |
| `SYNAPSE_DEV_MODE` | `0` | `1` adds common localhost origins to CORS and lets requests from localhost use admin endpoints and the dashboard console without the admin secret. Local development only. |

## Prometheus metrics

`pip install "synapse-shield[metrics]"`. The server exposes Prometheus text on `GET /metrics/prometheus` (and on `GET /metrics` when the scraper sends `Accept: text/plain` / OpenMetrics, which Prometheus does; a plain request returns the JSON Rust-state view). Both need `Authorization: Bearer $SYNAPSE_ADMIN_SECRET` (Prometheus `authorization:` scrape config). For multi-process servers (Gunicorn workers):

```bash
export PROMETHEUS_MULTIPROC_DIR=/tmp/synapse_metrics
```

Ready-made Grafana dashboard and alert rules: [`deploy/monitoring/`](../deploy/monitoring/README.md).

## Telegram and Discord alerts

Blocked threats (for example `STEALTH_AUTOMATION`, `POISSON_FLOOD`) and IP bans can be sent to Telegram or Discord from a background task.

**Telegram:** message [@BotFather](https://t.me/BotFather) with `/newbot` and copy the HTTP API token; send any message to your new bot; get your chat ID from [@userinfobot](https://t.me/userinfobot); then open the dashboard (`http://127.0.0.1:8000`), click **WEBHOOKS** and paste the token and chat ID.

**Discord:** Server settings → Integrations → Webhooks → New Webhook, copy the URL, and paste it under **WEBHOOKS** in the dashboard.

Only Telegram and Discord hosts are accepted (HTTPS, no look-alike domains).
