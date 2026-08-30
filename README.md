<div align="center">

# 🛡️ SYNAPSE SHIELD

### Next-Gen Open-Source Behavioral Biometrics & Bot Mitigation Engine

**A privacy-first, zero-friction, self-hosted alternative to Cloudflare Turnstile.**

[![PyPI](https://img.shields.io/pypi/v/synapse-shield?color=00F0FF&label=pypi)](https://pypi.org/project/synapse-shield/)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](https://opensource.org/licenses/MIT)
[![CI/CD](https://github.com/0xStoic-bit/Synapse_Shield/actions/workflows/ci.yml/badge.svg)](https://github.com/0xStoic-bit/Synapse_Shield/actions)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![Inference SLA](https://img.shields.io/badge/Latency-%3C0.5ms-10B981.svg)]()
[![Zero-PII](https://img.shields.io/badge/Privacy-100%25%20Zero--PII-success.svg)]()

<br/>

[Key Features](#-key-features--hardening-v040) • [Architecture](#-architecture--sequence-diagram) • [Quickstart](#-30-second-quickstart) • [Developer Guide](#-developer-integration) • [Benchmarks](#-attack-simulation-benchmarks) • [Math](#-kinematic--mathematical-foundations)

</div>

---

## ⚡ Overview

**Synapse Shield** replaces intrusive legacy CAPTCHAs and expensive proprietary cloud WAFs with **sub-millisecond behavioral biomechanics**.

By evaluating natural human neuromuscular micro-tremors (**Jerk: $\frac{da}{dt}$**), Fitts's Law terminal deceleration profiles, cursor curvature, and millisecond keystroke dynamics, Synapse Shield autonomously classifies and mitigates bots, scrapers, and credential stuffers **before they touch your backend logic**.

---

## ✨ Key Features & Hardening (v0.4.0)

| Feature                                    | Description                                                                                                                                   |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 🧩 **100% Invisible UX**                   | Zero annoying puzzles, image selections, or audio challenges. Legitimate humans pass friction-free.                                           |
| ⚡ **Async Non-Blocking SLA (<0.5 ms)**    | Heavy CPU-bound kinematics processed via `asyncio.to_thread`, guaranteeing zero event-loop blocking under high concurrency.                   |
| 🔐 **Cryptographic Replay Defense**        | Every session is bound to a single-use **HMAC-SHA256** signed nonce. Intercepted tokens cannot be replayed.                                   |
| 🧠 **Fitts's Law Deceleration Kinematics** | Distinguishes advanced Bézier curve bots (`ghost-cursor`) from organic human hands by analyzing terminal velocity drops before click actions. |
| 🔒 **100% Zero-PII & Privacy-First**       | No keystroke characters or form values collected — strictly relative millisecond timing deltas processed (GDPR & KVKK compliant).             |
| 📊 **Poisson Flooder Defense**             | Statistical Poisson anomaly detection identifies high-frequency headless API flooders and applies dynamic IP rate penalties.                  |
| 💾 **SQLite WAL with Auto-Pruning**        | In-memory TTL nonce management + Write-Ahead Logging with automatic log pruning prevents memory leaks and disk bloat.                         |

---

## 🏛️ Architecture & Sequence Diagram

```
┌─────────────────┐             ┌─────────────────────┐             ┌─────────────────────────┐
│  Client Browser │             │  FastAPI Gateway    │             │  Kinematic Decision     │
│  (synapse-sdk)  │             │  (Synapse Shield)   │             │  Engine (<0.5ms SLA)    │
└────────┬────────┘             └──────────┬──────────┘             └────────────┬────────────┘
         │                                 │                                     │
         │── 1. GET /api/challenge ───────►│                                     │
         │◄── 2. { nonce, ts, hmac_sig } ──│  (Generates single-use signed nonce)│
         │                                 │                                     │
   [User moves cursor / types]             │                                     │
   [SDK bundles 50Hz telemetry]            │                                     │
         │                                 │                                     │
         │── 3. POST /api/score {token} ──►│  (1. Validates HMAC signature)      │
         │                                 │  (2. Checks 60s TTL freshness)      │
         │                                 │  (3. Checks Replay Attack nonce)    │
         │                                 │                                     │
         │                                 │── 4. asyncio.to_thread ────────────►│ (19D Kinematics)
         │                                 │                                     │ (Jerk & Fitts's Law)
         │                                 │                                     │ (Poisson Anomaly)
         │                                 │◄── 5. (bot_score, ALLOW/BLOCK) ─────│
         │                                 │                                     │
         │                                 │── 6. Save Log to SQLite (WAL)       │
         │◄── 7. HTTP 200 {ALLOW/BLOCK} ───│                                     │
```

---

## 🚀 30-Second Quickstart

### Option 1: Install via PyPI

```bash
pip install synapse-shield
```

Run the server and live cockpit directly from your terminal:

```bash
synapse-shield run --port 8000
```

Run the automated 7-vector adversarial security test suite:

```bash
synapse-shield test
```

### Option 2: Clone & Local Development

```bash
git clone https://github.com/0xStoic-bit/Synapse_Shield.git
cd Synapse_Shield
pip install -e .
python test_suite.py
```

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser to launch the **Live Security Cockpit**.

---

## 💻 Developer Integration

### Method 1: FastAPI Route Decorator (3 Lines)

Protect any API endpoint or login route using the `@shield_protect` decorator:

```python
from fastapi import FastAPI, Request
from synapse_shield import shield_protect

app = FastAPI()

@app.post("/api/login")
@shield_protect(max_risk_score=50.0)
async def login(request: Request):
    # Only executes if Synapse Shield verifies the request as genuine human
    return {"status": "authenticated", "user": "verified_human"}
```

### Method 2: Global Middleware

Protect entire route prefixes across your application:

```python
from fastapi import FastAPI
from synapse_shield import SynapseShieldMiddleware

app = FastAPI()
app.add_middleware(SynapseShieldMiddleware, protected_paths=["/api/auth", "/checkout"])
```

### Method 3: Frontend Client SDK

Add the lightweight SDK (**<5 KB**) to your HTML or React project:

```html
<!-- Include SDK -->
<script src="http://localhost:8000/static/synapse-sdk.js"></script>

<script>
  // Initialize biometric listener
  SynapseShield.init();

  async function handleLogin() {
    // Automatically signs and packages 50 Hz telemetry
    const response = await SynapseShield.submit("/api/score");
    console.log("Evaluation Result:", response);
  }
</script>
```

### Environment Variables & Security Configuration

| Environment Variable | Default | Description |
| -------------------- | ------- | ----------- |
| `SYNAPSE_SECRET_KEY` | `~/.synapse_shield/secret.key` | Cryptographic key for HMAC challenge signing. **Must be set in production.** |
| `SYNAPSE_CORS_ORIGINS` | Disabled (`[]`) | Comma-separated list of allowed CORS origins (e.g., `https://myapp.com,https://api.myapp.com`). |
| `SYNAPSE_DEV_MODE` | `0` | Set to `1` to automatically allow common local dev origins (`localhost:3000`, `localhost:5173`, etc.). |
| `SYNAPSE_DB_PATH` | System Temp Path | Path to SQLite database file. |

---

## 🤖 Attack Simulation Benchmarks

Run the full adversarial suite anytime:

```bash
synapse-shield test
```

| Attack Vector          | Simulated Signature              | Detection Mechanism               | Decision | Risk Score | Latency |
| ---------------------- | -------------------------------- | --------------------------------- | -------- | ---------- | ------- |
| **Selenium Crawler**   | `navigator.webdriver = true`     | WebDriver API Detection           | 🔴 BLOCK | 100.0%     | 0.01 ms |
| **Linear Bot**         | Straightness = 1.000 & Zero Jerk | Straightness > 0.985 & Jerk ~ 0   | 🔴 BLOCK | 100.0%     | 0.18 ms |
| **Bézier Stealth Bot** | Mathematical curved trajectory   | Fitts's Law + Zero Accel Variance | 🔴 BLOCK | 65.0%      | 0.22 ms |
| **Robotic Auto-Typer** | Fixed-interval key injections    | Keystroke Variance < 1.0 ms²      | 🔴 BLOCK | 50.0%      | 0.15 ms |
| **Poisson Flooder**    | 8 rapid requests in <500 ms      | Poisson anomaly (P > 99%)         | 🔴 BLOCK | 60.0%      | 0.08 ms |
| **Replay Attack**      | Re-sending captured valid token  | Single-use HMAC Nonce reuse       | 🔴 BLOCK | 100.0%     | 0.05 ms |
| **Natural Human**      | Organic curves with tremors      | Biologic Jerk & Deceleration      | 🟢 ALLOW | 0.0%       | 0.24 ms |

---

## 🧠 Kinematic & Mathematical Foundations

### 1. Jerk — Neuromuscular Tremor Fingerprint

$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$

Human muscle tremors produce continuous high-frequency Jerk. Mathematical bot curves (Bézier/Linear) produce near-zero or static Jerk — this is the primary differentiation signal.

### 2. Fitts's Law Terminal Deceleration Index

$$\text{Terminal Decel Ratio} = \frac{\bar{v}_{\text{terminal (last 25\%)}}}{v_{\text{peak}}}$$

Humans naturally decelerate ($< 0.40$) as they approach the target click point. Bots maintain constant or linearly decreasing velocity.

### 3. Cumulative Poisson Anomaly Distribution

$$P(X < k) = \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

Request bursts that exceed the expected Poisson rate with $P > 99\%$ confidence are flagged and rate-penalized.

---

## 📁 Repository Structure

```
Synapse_Shield/
├── .github/
│   └── workflows/
│       └── ci.yml             # Automated CI matrix (Python 3.10, 3.11, 3.12)
├── src/
│   └── synapse_shield/
│       ├── __init__.py        # Public API exports
│       ├── cli.py             # CLI Controller (run / test commands)
│       ├── engine.py          # Real-time Decision & Poisson Engine
│       ├── features.py        # 19D Kinematics & Fitts's Law Extractor
│       ├── main.py            # Async FastAPI Gateway & SQLite Logger
│       ├── middleware.py      # @shield_protect & Middleware classes
│       ├── tokens.py          # HMAC-SHA256 Challenge & Replay Defense
│       ├── live_attacker.py   # 7-Vector Red Team Simulation Suite
│       └── static/            # Embedded 3D Cockpit & Client SDK
│           ├── index.html
│           └── synapse-sdk.js
├── tests/                     # Modular Pytest Suite
│   ├── test_features.py
│   ├── test_tokens.py
│   ├── test_engine.py
│   └── test_api.py
├── test_suite.py              # Standalone Zero-Dependency Test Runner
├── pyproject.toml             # PEP 517/621 Package Definition
├── requirements.txt           # Core Dependencies
├── LICENSE                    # MIT License
└── README.md
```

---

## 📜 License

Distributed under the [MIT License](LICENSE). Free for commercial and personal use.
