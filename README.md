<div align="center">

# 🛡️ SYNAPSE SHIELD

### Next-Gen Open-Source Behavioral Biometrics & Bot Mitigation Engine

**A privacy-first, zero-friction, self-hosted alternative to Cloudflare Turnstile.**

[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python)](https://python.org)
[![Inference SLA](https://img.shields.io/badge/Latency-%3C0.5ms-10B981.svg)]()
[![Zero-PII](https://img.shields.io/badge/Privacy-100%25%20Zero--PII-success.svg)]()

[Features](#-key-features) • [Architecture](#-architecture) • [Quickstart](#-30-second-quickstart) • [Developer Guide](#-developer-integration) • [Benchmarks](#-attack-simulation-benchmarks)

</div>

---

## ⚡ Overview

**Synapse Shield** replaces intrusive legacy CAPTCHAs and proprietary cloud WAFs with **sub-millisecond behavioral biomechanics**.

By evaluating natural human neuromuscular micro-tremors (**Jerk: $da/dt$**), cursor trajectory curvature, and millisecond keystroke intervals, Synapse Shield autonomously classifies and mitigates bots, scrapers, and credential stuffers before they touch your backend logic.

---

## ✨ Key Features

- **🧩 100% Invisible & Friction-Free UX:** Zero annoying puzzle solving, image selecting, or audio challenges. Genuine human users pass instantly.
- **⚡ Ultra-Low Latency (<0.5 ms):** Evaluated locally in-memory using lightweight NumPy and native kinematics algorithms.
- **🔒 100% Zero-PII & Privacy-First:** No keystroke characters, form inputs, or personally identifiable information are captured. Only relative millisecond delta timestamps ($t_{\text{hold}}$, $t_{\text{flight}}$) are processed (GDPR / KVKK compliant).
- **💸 $0 Cloud Costs (Self-Hostable):** Zero third-party cloud lock-in. Run anywhere with a single Python script or lightweight Docker container.
- **📊 Poisson Flooder Detection:** Catches high-frequency headless API scrapers lacking mouse telemetry using cumulative Poisson anomaly distributions.
- **🎮 Interactive 3D Security Lab:** Built-in Three.js & WebGL visual dashboard with real-time SQLite audit trails and live telemetry gauges.

---

## 🏛️ Architecture

```
[ CLIENT BROWSER ]
       │
       ├── (1) 50 Hz Vanilla JS SDK (Mouse, Touch, Key Timestamps)
       │
       ▼ [Zero-PII Telemetry Payload]
[ FASTAPI INGRESS GATEWAY ]
       │
       ├── (2) Kinematic Feature Extraction (19D Physical Vector)
       │       [Jerk: da/dt, Velocity Variance, Straightness, Timing CV]
       ▼
[ REAL-TIME DECISION ENGINE (<0.5 ms) ]
       │
       ├────────────────────────┬────────────────────────┐
       ▼                        ▼                        ▼
[ RISK < 35% ]          [ 35% ≤ RISK < 70% ]      [ RISK ≥ 70% ]
Clean Human               Borderline Traffic      Automated Bot
       │                        │                        │
       ▼                        ▼                        ▼
[ ALLOW 200 ]          [ RATE LIMIT / PoW ]      [ BLOCK 403 ]
(Seamless Pass)           (Dynamic Challenge)     (Access Denied)
```

---

## 🚀 30-Second Quickstart

### Option 1: Local Python Environment

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/synapse-shield.git
cd synapse-shield

# 2. Install dependencies
pip install fastapi uvicorn numpy

# 3. Start the server
python main.py
```

Visit http://127.0.0.1:8000 in your browser to launch the Security Lab Cockpit.

### Option 2: Docker Compose

```bash
docker compose up -d
```

---

## 💻 Developer Integration

### 1. Backend Protection (FastAPI Decorator)

Protect any API endpoint or login route using the `@shield_protect` decorator:

```python
from fastapi import FastAPI, Request
from middleware import shield_protect

app = FastAPI()

@app.post("/api/login")
@shield_protect(max_risk_score=50.0)
async def login(request: Request):
    # This code only executes if Synapse Shield verifies the request as Human
    return {"status": "success", "message": "Authenticated successfully"}
```

### 2. Frontend Integration (Vanilla JS / React)

Add the lightweight SDK (<5 KB) to your web application:

```html
<!-- Include SDK -->
<script src="http://your-server:8000/static/synapse-sdk.js"></script>

<script>
  // Initialize biometric listener
  SynapseShield.init();

  async function handleLogin() {
    // Automatically packages 50 Hz telemetry
    const response = await SynapseShield.submit("/api/score");
    console.log("Evaluation Result:", response);
  }
</script>
```

---

## 🤖 Attack Simulation Benchmarks

Synapse Shield includes an automated adversarial test suite simulating 5 distinct attack vectors:

```bash
python test_bot.py
```

### Benchmark Results:

| Test Scenario          | Attack Signature                     | Detection Mechanism                       | Decision  | Risk Score | Latency |
| :--------------------- | :----------------------------------- | :---------------------------------------- | :-------- | :--------- | :------ |
| **Natural Human**      | Organic curves with tremors          | Biological Jerk verified                  | **ALLOW** | 0.0%       | 0.22 ms |
| **Linear Bot**         | Selenium straight-line cursor        | $\text{Straightness} = 1.000$ & Zero Jerk | **BLOCK** | 98.5%      | 0.14 ms |
| **Poisson Flooder**    | 8 rapid requests in $<500\text{ ms}$ | Poisson frequency anomaly ($P > 95\%$)    | **BLOCK** | 85.0%      | 0.08 ms |
| **Selenium Webdriver** | Automated headless crawler           | `navigator.webdriver = true`              | **BLOCK** | 100.0%     | 0.01 ms |
| **Robotic Auto-Typer** | Constant 50ms keystrokes             | $\text{Key Variance} < 1.0\text{ ms}^2$   | **BLOCK** | 92.0%      | 0.18 ms |

---

## 🧠 Kinematic & Mathematical Foundation

Synapse Shield extracts physical motion vectors derived from classical biomechanics:

**Jerk (Acceleration Derivative):**
$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$
Human neuromuscular micro-tremors produce continuous high-frequency Jerk, whereas mathematical bot curves (Bézier/Linear) produce near-zero or static Jerk.

**Trajectory Straightness Index:**
$$\text{Straightness} = \frac{\text{Euclidean Distance}(P_{\text{start}}, P_{\text{end}})}{\sum_{i=1}^{N} \Delta s_i}$$

**Poisson Request Rate Anomaly:**
$$P(X \ge k) = 1 - \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

---

## 📁 Repository Structure

```
synapse-shield/
├── static/
│   ├── index.html          # Interactive 3D Security Lab & HUD
│   └── synapse-sdk.js      # 50 Hz Client-side Telemetry SDK (<5 KB)
├── features.py             # 19-Dimensional Kinematic Feature Extractor
├── engine.py               # Real-time Behavioral & Poisson Classifier
├── main.py                 # FastAPI Application & SQLite Audit Logger
├── middleware.py           # Drop-in @shield_protect Decorator for Developers
├── train.py                # Synthetic Data Generator & ML Training Pipeline
├── test_bot.py             # 5-Vector Adversarial Attack Benchmark Suite
├── Dockerfile              # Production Container Definition
├── docker-compose.yml      # 1-Click Deployment Configuration
└── README.md               # Documentation & Showcase
```

---

## 📜 License

Distributed under the MIT License. Free for both commercial and personal use.
