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

[Key Features](#-key-features--hardening-v050) • [Architecture](#-architecture--sequence-diagram) • [Quickstart](#-30-second-quickstart) • [Developer Guide](#-developer-integration) • [Benchmarks](#-attack-simulation-benchmarks) • [Math](#-kinematic--mathematical-foundations)

</div>

---

## ⚡ Overview

**Synapse Shield** replaces intrusive legacy CAPTCHAs and expensive proprietary cloud WAFs with **sub-millisecond behavioral biomechanics**.

By evaluating natural human neuromuscular micro-tremors (**Jerk: $\frac{da}{dt}$**), Fitts's Law terminal deceleration profiles, cursor curvature, and millisecond keystroke dynamics, Synapse Shield autonomously classifies and mitigates bots, scrapers, and credential stuffers **before they touch your backend logic**.

---

## ✨ Key Features & Security Architecture (v0.6.4)

| Feature | Description |
| :--- | :--- |
| 🕵️ **Anti-Stealth & Tamper Proofing** | Dynamically detects headless browser fingerprints (`navigator.webdriver`), fake plugin arrays, and native `toString` overwrites in WebGL/Canvas APIs. |
| 🗄️ **Continuous Learning Collector** | Integrated drop-in `store.html` telemetry collector endpoint (`/api/collect_dataset`) for future 1D-CNN Fine-Tuning with raw human datasets. |
| 🤖 **Pure-NumPy 1D-CNN Micro-Brain** | The Sequence Tokenizer fuses kinematics and keystroke stats into an 8D and 5D tensor architecture, fully processed by a 15KB NumPy-based 1D-CNN (Zero-PyTorch). |
| 🛡️ **Max Gating (Fusion Engine)** | Dynamically unifies Heuristic/Mathematical rules with the 1D-CNN AI confidence score. If either engine flags the telemetry as a Bot, the request is unconditionally blocked. |
| 🔗 **Zero-Dependency Multimodal Tokenizer** | Fuses 5D Mouse Sequence `[dx, dy, dt, velocity, jerk]` with 8D Static Keystroke/Scroll Vector via Late Fusion. |
| 🧩 **100% Invisible UX** | Zero annoying puzzles, image selections, or audio challenges. Legitimate humans pass friction-free. |
| ⚡ **Async Non-Blocking SLA (<0.5 ms)** | Heavy CPU-bound kinematics processed via `asyncio.to_thread`, guaranteeing zero event-loop blocking under high concurrency. |
| 🔐 **Cryptographic Replay Defense** | Every session is bound to a single-use **HMAC-SHA256** signed nonce. Intercepted tokens cannot be replayed. |
| 🧠 **Fitts's Law Deceleration Kinematics** | Distinguishes advanced Bézier curve bots (`ghost-cursor`) from organic human hands by analyzing terminal velocity drops before click actions. |
| ⚛️ **React & Next.js Drop-in Support** | Native `"use client"` compatible `<SynapseProtect />` component and `useSynapseShield` hook with event throttling. |
| 🐍 **Multi-Framework Adapters** | Native middlewares and decorators for **Django** (`SynapseShieldMiddleware`) and **Flask** (`@shield_protect_flask`). |
| ♿ **Accessibility Mode** | Graceful risk scaling (`accessibility_mode=True`) prevents false positives for motor-impaired and assistive device users. |
| 📈 **Enterprise Prometheus Metrics** | Built-in `/metrics` endpoint supporting multi-process Gunicorn/Uvicorn aggregation via `PROMETHEUS_MULTIPROC_DIR`. |
| 🔒 **100% Zero-PII & Privacy-First** | No keystroke characters or form values collected — strictly relative millisecond timing deltas processed (GDPR & KVKK compliant). |
| 📊 **Poisson Flooder Defense** | Statistical Poisson anomaly detection identifies high-frequency headless API flooders and applies dynamic IP rate penalties. |
| 💾 **SQLite WAL with Auto-Pruning** | In-memory TTL nonce management + Write-Ahead Logging (WAL) with 10s timeouts prevents database locks during async BackgroundTasks. |

---

## 🏛️ Architecture & Sequence Diagram

```text
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

Visit [http://127.0.0.1:8000](http://127.0.0.1:8000/) in your browser to launch the **Live Security Cockpit**.

---

## 💻 Developer Integration

### 1. FastAPI Integration

Protect any API endpoint using the `@shield_protect` decorator or global middleware:

```python
from fastapi import FastAPI, Request
from synapse_shield import shield_protect, SynapseShieldMiddleware

app = FastAPI()
app.add_middleware(SynapseShieldMiddleware, protected_paths=["/api/auth"])

@app.post("/api/login")
@shield_protect(max_risk_score=50.0, accessibility_mode=False)
async def login(request: Request):
    return {"status": "authenticated"}
```

### 2. Django & Flask Integration

Native support for Django and Flask environments.

**Django (`settings.py`)**:

```python
MIDDLEWARE = [
    # ...
    'synapse_shield.django.SynapseShieldMiddleware',
]
SYNAPSE_SHIELD_PROTECTED_PATHS = ['/api/login']
SYNAPSE_SHIELD_MAX_RISK = 50.0
SYNAPSE_SHIELD_ACCESSIBILITY = False
```

**Flask**:

```python
from flask import Flask
from synapse_shield.flask import shield_protect_flask

app = Flask(__name__)

@app.route("/login", methods=["POST"])
@shield_protect_flask(max_risk_score=50.0)
def login():
    return {"status": "authenticated"}
```

### 3. React / Next.js Integration

We provide a drop-in `"use client"` compatible React package.

```tsx
import { useSynapseShield, SynapseProtect } from 'synapse-shield-react';

export default function LoginForm() {
  const { getProtectedPayload } = useSynapseShield();

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = getProtectedPayload();
    // Send payload.token to your backend
  };

  return (
    <form onSubmit={handleSubmit}>
      <SynapseProtect />
      <button type="submit">Login</button>
    </form>
  );
}
```

### 4. Prometheus Metrics

Enterprise observability out of the box. Automatically exposes latency and block rates.
To enable multi-process support (e.g., Gunicorn workers), set the environment variable:

```bash
export PROMETHEUS_MULTIPROC_DIR=/tmp/synapse_metrics
```

### 5. Vanilla JS / HTML SDK

Add the lightweight SDK (`<5 KB`) to your vanilla project:

```html
<script src="http://localhost:8000/static/synapse-sdk.js"></script>
<script>
  SynapseShield.init();
  async function handleLogin() {
    const payload = SynapseShield.getPayload();
    // Submit payload
  }
</script>
```

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

Human muscle tremors produce continuous high-frequency Jerk. Mathematical bot curves (Bézier/Linear) produce near-zero or static Jerk.

### 2. Fitts's Law Terminal Deceleration Index

$$\text{Terminal Decel Ratio} = \frac{\bar{v}_{\text{terminal (last 25\%)}}}{v_{\text{peak}}}$$

Humans naturally decelerate ($< 0.40$) as they approach the target click point.

### 3. Cumulative Poisson Anomaly Distribution

$$P(X < k) = \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

---

## 📁 Repository Structure

```text
Synapse_Shield/
├── .github/
│   └── workflows/
│       └── ci.yml             # Automated CI matrix (Python 3.10, 3.11, 3.12)
├── src/
│   └── synapse_shield/
│       ├── __init__.py        # Public API exports
│       ├── cli.py             # CLI Controller (run / test commands)
│       ├── engine.py          # Real-time Decision & Poisson Engine
│       ├── features.py        # 19D Kinematics, Fitts's Law & Multimodal Tokenizer
│       ├── models.py          # Zero-Dependency NumPy 1D-CNN Inference Engine
│       ├── weights.npz        # 4KB Serialized Neural Network Weights
│       ├── main.py            # Async FastAPI Gateway & SQLite Logger
│       ├── middleware.py      # @shield_protect & Middleware classes
│       ├── django.py          # Django Middleware Adapter
│       ├── flask.py           # Flask Route Decorator
│       ├── metrics.py         # Prometheus Multi-Process Exporter
│       ├── tokens.py          # HMAC-SHA256 Challenge & Replay Defense
│       ├── live_attacker.py   # 7-Vector Red Team Simulation Suite
│       └── static/            # Embedded 3D Cockpit & Client SDK
│           ├── index.html
│           └── synapse-sdk.js
├── synapse-shield-react/      # React / Next.js SDK Package
│   ├── src/
│   │   ├── SynapseProtect.tsx # "use client" Drop-in Component
│   │   ├── useSynapseShield.ts# React Hook with event throttling
│   │   └── index.ts
│   ├── package.json
│   └── tsconfig.json
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

Distributed under the [MIT License](https://opensource.org/licenses/MIT). Free for commercial and personal use.
