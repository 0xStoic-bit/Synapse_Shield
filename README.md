<div align="center">

# 🛡️ SYNAPSE SHIELD

### Open-Source Behavioral Biometrics & Bot Mitigation Engine

**A privacy-first, zero-friction, self-hosted alternative to Cloudflare Turnstile.**

[![PyPI](https://img.shields.io/pypi/v/synapse-shield.svg?color=00F0FF)](https://pypi.org/project/synapse-shield/)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python)](https://python.org)

Features • Architecture • Quickstart • Developer Guide • Benchmarks

</div>

---

## ⚡ Overview

Synapse Shield replaces intrusive CAPTCHAs and proprietary cloud WAFs with sub-millisecond behavioral biomechanics and cryptographic challenge-response.

By evaluating natural human neuromuscular micro-tremors (Jerk: $da/dt$), cursor trajectory straightness, Fitts's Law terminal deceleration profiles, and millisecond keystroke interval dynamics, Synapse Shield classifies bots before they touch your backend logic.

---

## ✨ Key Features

- **🧩 100% Invisible & Friction-Free UX:** No puzzles, image selection, or audio challenges. Legitimate users pass seamlessly.
- **🔑 Cryptographic Challenge-Response:** Native replay attack protection. Clients fetch a single-use HMAC-SHA256 token from `/api/challenge` and sign their telemetry payload before submission.
- **📈 Fitts's Law Deceleration Profiling:** Evaluates terminal deceleration ratio and velocity skewness to detect mechanical bot paths that don't slow down before clicks.
- **⚡ Sub-millisecond Local Inference:** Evaluated entirely in-memory using pure Python math — no external ML model required for the fast path.
- **🔒 No Keystroke Characters Collected:** Only event types (keydown/keyup) and millisecond timestamps are captured. No form content, no key values.
- **💸 Self-Hostable, $0 Cloud Cost:** No third-party lock-in. Run via Docker or `pip install synapse-shield`.
- **📊 Poisson Flooder Detection:** Catches high-frequency headless API scrapers using cumulative Poisson anomaly distributions.
- **📋 SQLite Audit Logging:** All decisions logged with WAL mode for concurrent read performance.

---

## 🏛️ Architecture

```
[ CLIENT BROWSER ]
       │
       ├── (1) GET /api/challenge ──► Single-use HMAC-SHA256 token
       │
       ├── (2) ~33 Hz Biometric Telemetry capture (Mouse, Keystroke timestamps)
       │
       ▼ [Signed Telemetry Payload]
[ FASTAPI INGRESS GATEWAY ]
       │
       ├── (3) Token verification & Replay Attack check (USED_NONCES cache)
       │
       ├── (4) Kinematic Feature Extraction (19D Physical Vector)
       │       [Jerk: da/dt, Terminal Decel Ratio, Velocity Skewness, Straightness]
       ▼
[ REAL-TIME DECISION ENGINE ]
       │
       ├──────────────────────────────┐
       ▼                              ▼
  [ RISK < max_risk_score ]    [ RISK ≥ max_risk_score ]
   Human                        Bot
       │                              │
       ▼                              ▼
  [ ALLOW 200 ]                 [ BLOCK 403 ]
```

The decision is binary against a single configurable threshold (`max_risk_score`,
default **50**). There is no separate mid-band "challenge" step.

---

## 🚀 Quickstart

### Option 1: pip install

```bash
pip install synapse-shield
synapse-shield run --host 0.0.0.0 --port 8000     # add --reload for development
```

Visit http://127.0.0.1:8000 to launch the Security Lab dashboard.

### Option 2: Docker Compose

```bash
SYNAPSE_SHIELD_SECRET_KEY=$(openssl rand -hex 32) docker compose up -d --build
```

### Run Red Team Simulation

```bash
synapse-shield test        # exits non-zero if any attack vector gets through
```

### Configuration (environment variables)

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `SYNAPSE_SHIELD_SECRET_KEY` | *(ephemeral random)* | HMAC signing key for challenge tokens. **Required in production** — without it tokens do not survive a restart or work across multiple workers. |
| `SYNAPSE_SHIELD_ADMIN_TOKEN` | *(unset → open)* | When set, `/api/logs` and `/api/clear` require `Authorization: Bearer <token>` (or `X-Admin-Token`). |
| `SYNAPSE_SHIELD_CORS_ORIGINS` | `*` | Comma-separated allowed origins. `*` disables credentialed CORS. |
| `SYNAPSE_SHIELD_DB` | `synapse_shield.db` | SQLite audit-log path. |

> **Multi-worker note:** replay protection uses a per-process nonce store. For
> `uvicorn --workers N` (N > 1) or multi-host deployments, inject a shared
> backend via `synapse_shield.set_nonce_store(...)`.

---

## 💻 Developer Integration

### Backend — FastAPI Decorator

```python
from fastapi import FastAPI, Request
from synapse_shield.middleware import shield_protect

app = FastAPI()

@app.post("/api/login")
@shield_protect(max_risk_score=50.0)
async def login(request: Request):
    return {"status": "success"}
```

### Frontend — Vanilla JS SDK

```html
<script src="http://your-server:8000/static/synapse-sdk.js"></script>

<script>
  await SynapseShield.init(); // Fetches challenge token automatically

  async function handleLogin() {
    const response = await SynapseShield.submit("/api/score");
    console.log(response);
  }
</script>
```

---

## 🤖 Benchmarks

7-vector adversarial test suite — run with `synapse-shield test`:

| Scenario               | Attack Signature                      | Detection Mechanism             | Decision  | Risk Score |
| :--------------------- | :------------------------------------ | :------------------------------ | :-------- | :--------- |
| **Natural Human**      | Organic curves with micro-tremors     | Jerk & deceleration verified    | **ALLOW** | <10%       |
| **Linear Bot**         | Straight-line cursor                  | Straightness = 1.000, zero jerk | **BLOCK** | 100%       |
| **Bézier / Spline Bot**| Smooth curved path, no tremor         | Sub-human jerk on a curved path | **BLOCK** | ~90%       |
| **Replay Attacker**    | Reused valid token                    | Nonce already consumed          | **BLOCK** | 100%       |
| **Fitts Violator**     | No terminal deceleration before click | terminal_decel_ratio > 0.85     | **BLOCK** | 80%        |
| **Poisson Flooder**    | 8 requests in <500ms                  | Poisson anomaly P > 95%         | **BLOCK** | 85%        |
| **Selenium Webdriver** | Headless crawler                      | navigator.webdriver = true      | **BLOCK** | 100%       |
| **Robotic Auto-Typer** | Fixed 50ms keystroke intervals        | Key variance < 1.0 ms²          | **BLOCK** | 92%        |

---

## 🧠 Mathematical Foundation

### Jerk (Neuromuscular Tremor)

$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$
Humans produce continuous high-frequency jerk. Mathematical bot curves (Bézier, linear) produce near-zero jerk.

### Fitts's Law — Terminal Deceleration

$$\text{Terminal Decel Ratio} = \frac{\bar{v}_{\text{terminal}}}{v_{\text{max}}}$$
Humans slow down when approaching a click target (ratio < 0.40). Click bots maintain monotonic speed (ratio > 0.85).

### Poisson Request Rate Anomaly

$$P(X \ge k) = 1 - \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

---

## 📁 Repository Structure

```
Synapse_Shield/
├── pyproject.toml
├── README.md
├── LICENSE
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── tests/
│   └── test_suite.py       # All-in-one test suite module
└── src/
    └── synapse_shield/
        ├── __init__.py       # Public API: shield_protect, SynapseEngine, analyze_behavior, set_nonce_store
        ├── engine.py         # Decision engine
        ├── features.py       # 19D kinematic feature extractor
        ├── middleware.py     # @shield_protect FastAPI decorator (verifies signed tokens)
        ├── cli.py            # CLI: synapse-shield run / test
        ├── tokens.py         # HMAC-SHA256 challenge & replay attack defense
        ├── live_attacker.py  # 7-vector red team simulator
        └── static/
            ├── index.html
            └── synapse-sdk.js
```

---

## 🔐 Security Model & Limitations

- **Telemetry is client-supplied.** Every kinematic signal originates in the
  browser. A determined adversary who reproduces the SDK can synthesize
  human-plausible jerk, deceleration and typing dynamics. Treat Synapse Shield
  as **defense-in-depth / friction reduction**, not a sole authentication gate.
- **Challenge tokens** provide signature, expiry and single-use replay
  protection — but only when `SYNAPSE_SHIELD_SECRET_KEY` is set and the nonce
  store is shared across all workers (see Configuration).
- `@shield_protect` requires a signed token by default (`require_token=True`).
- The bundled SQLite audit log and rate counter are single-node; use an
  external store for horizontally scaled deployments.

## ⚠️ Privacy & Data Notice

Synapse Shield collects and stores the following data in its local SQLite audit log: client IP address, user-agent string, derived kinematic feature vectors, and anonymized telemetry (mouse coordinates, scroll positions, keystroke timing). No keystroke characters or form content are ever captured. For production deployments, configure appropriate data retention policies per your jurisdiction's requirements.

---

## 📜 License

MIT License — free for commercial and personal use.
