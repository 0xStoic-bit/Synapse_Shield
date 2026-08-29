<div align="center">

# 🛡️ SYNAPSE SHIELD

### Next-Gen Open-Source Behavioral Biometrics & Bot Mitigation Engine

**A privacy-first, zero-friction, self-hosted alternative to Cloudflare Turnstile.**

[![PyPI](https://img.shields.io/pypi/v/synapse-shield.svg?color=00F0FF)](https://pypi.org/project/synapse-shield/)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](https://opensource.org/licenses/MIT)
[![CI/CD](https://github.com/0xStoic-bit/Synapse_Shield/actions/workflows/ci.yml/badge.svg)](https://github.com/0xStoic-bit/Synapse_Shield/actions)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![Inference SLA](https://img.shields.io/badge/Latency-%3C0.5ms-10B981.svg)]()
[![Zero-PII](https://img.shields.io/badge/Privacy-100%25%20Zero--PII-success.svg)]()

<br/>

[Key Features](#-key-features) • [Architecture & Flow](#-architecture--sequence-diagram) • [Quickstart](#-30-second-quickstart) • [Developer Guide](#-developer-integration) • [Benchmarks](#-attack-simulation-benchmarks) • [Math Foundations](#-kinematic--mathematical-foundations)

</div>

---

## ⚡ Overview

**Synapse Shield** replaces intrusive legacy CAPTCHAs and expensive proprietary cloud WAFs with **sub-millisecond behavioral biomechanics**.

By evaluating natural human neuromuscular micro-tremors (**Jerk: $da/dt$**), Fitts's Law terminal deceleration profiles, cursor curvature, and millisecond keystroke dynamics, Synapse Shield autonomously classifies and mitigates bots, scrapers, and credential stuffers before they touch your backend logic.

---

## ✨ Key Features & Hardening (v0.3.0)

- **🧩 100% Invisible UX:** Zero annoying puzzles, image selections, or audio challenges. Legitimate humans pass friction-free.
- **⚡ Async Non-Blocking SLA (<0.5 ms):** Heavy CPU-bound kinematics are processed asynchronously (`asyncio.to_thread`), guaranteeing zero event-loop blocking under high concurrent traffic.
- **🔐 Cryptographic Replay Defense (HMAC-SHA256):** Every session is bound to a single-use signed challenge nonce. Intercepted tokens cannot be replayed.
- **🧠 Fitts's Law Deceleration Kinematics:** Distinguishes advanced Bézier curve bots (`ghost-cursor`) from organic human hands by analyzing terminal velocity drops before click actions.
- **🔒 100% Zero-PII & Privacy-First:** No keystroke characters or form values are collected—strictly relative millisecond timing deltas ($t_{\text{hold}}$, $t_{\text{flight}}$) are processed (GDPR & KVKK compliant).
- **📊 Poisson Flooder Defense & Dynamic IP Throttling:** Statistical Poisson anomaly detection identifies high-frequency headless API flooders lacking mouse telemetry and applies temporary rate penalties.
- **💾 SQLite WAL with Auto-Pruning:** In-memory TTL nonce management and SQLite Write-Ahead Logging (WAL) with automatic log pruning prevent memory leaks and disk bloat.

---

## 🏛️ Architecture & Sequence Diagram

┌─────────────────┐ ┌─────────────────────┐ ┌─────────────────────────┐
│ Client Browser │ │ FastAPI Gateway │ │ Kinematic Decision │
│ (synapse-sdk) │ │ (Synapse Shield) │ │ Engine (<0.5ms SLA) │
└────────┬────────┘ └──────────┬──────────┘ └────────────┬────────────┘
│ │ │
│── 1. GET /api/challenge ───────►│ │
│◄── 2. { nonce.ts.hmac_sig } ───│ (Generates single-use signed nonce) │
│ │ │
[User moves cursor / types] │ │
[SDK bundles 50Hz telemetry] │ │
│ │ │
│── 3. POST /api/score {token} ──►│ (1. Validates HMAC signature) │
│ │ (2. Checks 60s TTL freshness) │
│ │ (3. Checks Replay Attack nonce) │
│ │ │
│ │── 4. asyncio.to_thread ────────────►│ (19D Kinematics)
│ │ │ (Jerk & Fitts's Law)
│ │ │ (Poisson Anomaly)
│ │◄── 5. (bot_score, ALLOW/BLOCK) ─────│
│ │ │
│ │── 6. Save Log to SQLite (WAL) │
│◄── 7. HTTP 200 {ALLOW/BLOCK} ───│ │
│ │ │

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

Visit `http://127.0.0.1:8000` in your browser to launch the Live Security Cockpit.

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

Add the lightweight SDK (<5 KB) to your HTML or React project:

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

---

## 🤖 Attack Simulation Benchmarks

Synapse Shield includes an automated adversarial test suite simulating 7 distinct attack vectors:

```bash
synapse-shield test
```

| Attack Vector          | Simulated Signature                                                         | Detection Mechanism                     | Decision  | Risk Score | Latency |
| :--------------------- | :-------------------------------------------------------------------------- | :-------------------------------------- | :-------- | :--------- | :------ |
| **Selenium Crawler**   | Headless browser automation `navigator.webdriver = true`                    | WebDriver API Algılaması                | **BLOCK** | 100.0%     | 0.01 ms |
| **Linear Bot**         | Programmatic straight-line cursor $\text{Straightness} = 1.000$ & Zero Jerk | `Straightness > 0.985` & `Jerk ~ 0`     | **BLOCK** | 100.0%     | 0.18 ms |
| **Bézier Stealth Bot** | Mathematical curved trajectory                                              | Fitts's Law + Zero Accel Variance       | **BLOCK** | 65.0%      | 0.22 ms |
| **Robotic Auto-Typer** | Fixed-interval key injections                                               | Keystroke Variance $< 1.0\text{ ms}^2$  | **BLOCK** | 50.0%      | 0.15 ms |
| **Poisson Flooder**    | 8 rapid API requests in $<500\text{ ms}$                                    | Poisson frequency anomaly ($P > 99\%$)  | **BLOCK** | 60.0%      | 0.08 ms |
| **Replay Attack**      | Re-sending captured valid token                                             | Single-use HMAC Nonce reuse             | **BLOCK** | 100.0%     | 0.05 ms |
| **Natural Human**      | Organic curves with tremors                                                 | Biological Jerk & Deceleration verified | **ALLOW** | 0.0%       | 0.24 ms |

---

## 🧠 Kinematic & Mathematical Foundations

### Jerk (Acceleration Derivative / Neuromuscular Tremors):

$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$

Human muscle tremors produce continuous high-frequency Jerk, whereas mathematical bot curves (Bézier/Linear) produce near-zero or static Jerk.

### Fitts's Law Terminal Deceleration Index:

$$\text{Terminal Decel Ratio} = \frac{\bar{v}_{\text{terminal (last 25\%)}}}{v_{\text{peak}}}$$

Humans naturally decelerate ($<0.40$) as they approach the target click point.

### Cumulative Poisson Anomaly Distribution:

$$P(X < k) = \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

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
└── README.md                  # Documentation & Showcase
```

---

## 📜 License

Distributed under the MIT License. Free for commercial and personal use.
