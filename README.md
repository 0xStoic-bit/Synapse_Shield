<div align="center">
 
# 🛡️ SYNAPSE SHIELD
 
### Next-Gen Open-Source Behavioral Biometrics & Bot Mitigation Engine
 
**A privacy-first, zero-friction, self-hosted alternative to Cloudflare Turnstile.**
 
[![PyPI](https://img.shields.io/pypi/v/synapse-shield.svg?color=00F0FF)](https://pypi.org/project/synapse-shield/)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python)](https://python.org)
[![Inference SLA](https://img.shields.io/badge/Latency-%3C0.5ms-10B981.svg)]()
[![Zero-PII](https://img.shields.io/badge/Privacy-100%25%20Zero--PII-success.svg)]()
 
[Features](#-key-features) • [Architecture](#-architecture) • [Quickstart](#-30-second-quickstart) • [Developer Guide](#-developer-integration) • [Benchmarks](#-attack-simulation-benchmarks)
 
</div>
 
---
 
## ⚡ Overview
 
**Synapse Shield** replaces intrusive legacy CAPTCHAs and proprietary cloud WAFs with **sub-millisecond behavioral biomechanics & cryptographic challenges**.
 
By evaluating natural human neuromuscular micro-tremors (**Jerk: $da/dt$**), cursor trajectory curvature, Fitts's Law validation (terminal deceleration profiles), and millisecond keystroke intervals, Synapse Shield autonomously classifies and mitigates bots, scrapers, and credential stuffers before they touch your backend logic.
 
---
 
## ✨ Key Features
 
- **🧩 100% Invisible & Friction-Free UX:** Zero annoying puzzle solving, image selecting, or audio challenges. Genuine human users pass instantly.
- **🔑 Cryptographic Challenge-Response:** Native protection against telemetry replay attacks. Clients fetch a single-use token from `/api/challenge` and sign their telemetry payload.
- **📈 Fitts's Law Deceleration Profiling:** Evaluates mouse deceleration as it approaches targets/clicks (`terminal_decel_ratio`) and checks velocity asymmetry (`velocity_skewness`) to detect mechanical bot paths.
- **⚡ Ultra-Low Latency (<0.5 ms):** Evaluated locally in-memory using lightweight NumPy & mathematical kinematic scoring.
- **🔒 100% Zero-PII & Privacy-First:** No keystroke characters, form inputs, or personally identifiable information are captured. Only relative millisecond delta timestamps are processed (GDPR / KVKK compliant).
- **💸 $0 Cloud Costs (Self-Hostable):** Zero third-party cloud lock-in. Run anywhere with a single packages command.
- **📊 Poisson Flooder Detection:** Catches high-frequency headless API scrapers lacking mouse telemetry using cumulative Poisson anomaly distributions.
- **🎮 Interactive 3D Security Lab:** Built-in Three.js & WebGL visual dashboard with real-time SQLite audit trails and live telemetry gauges.
 
---
 
## 🏛️ Architecture
 
```
[ CLIENT BROWSER ]
       │
       ├── (1) GET /api/challenge ──► (Generates single-use Cryptographic Token)
       │
       ├── (2) Capture 50 Hz Biometric Telemetry (Mouse, Touch, Key Timestamps)
       │
       ▼ [Signed Telemetry Payload (Telemetry + Token)]
[ FASTAPI INGRESS GATEWAY ]
       │
       ├── (3) Token verification & Replay Attack check
       │
       ├── (4) Kinematic Feature Extraction (19D Physical Vector)
       │       [Jerk: da/dt, Deceleration Ratio, Velocity Skewness, Straightness]
       ▼
[ REAL-TIME DECISION ENGINE (<0.5 ms) ]
       │
       ├────────────────────────┬────────────────────────┐
       ▼                        ▼                        ▼
[ RISK < 50% ]          [ 50% ≤ RISK < 70% ]      [ RISK ≥ 70% ]
  Clean Human             Suspicious Traffic      Automated Bot
       │                        │                        │
       ▼                        ▼                        ▼
[ ALLOW 200 ]            [ CHALLENGE / POW ]      [ BLOCK 403 ]
(Seamless Pass)           (Dynamic Challenge)     (Access Denied)
```
 
---
 
## 🚀 30-Second Quickstart
 
### Installing the Command Line Tool
 
Since Synapse Shield is built as a pyproject.toml package, you can run CLI commands directly:
 
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the Synapse Shield server (with Hot-Reload dynamic auto-reload enabled)

synapse-shield run --host 0.0.0.0 --port 8000

````

Visit http://127.0.0.1:8000 in your browser to launch the Security Lab Cockpit dashboard.

### Running the Simulation Suite

To run the automated adversarial Red Team simulation suite showing Fitts's Law violations and Replay Attack mitigations:

```bash
synapse-shield test
````

---

## 💻 Developer Integration

### 1. Backend Protection (FastAPI Decorator)

Protect any API endpoint or login route using the `@shield_protect` decorator:

```python
from fastapi import FastAPI, Request
from synapse_shield.middleware import shield_protect

app = FastAPI()

@app.post("/api/login")
@shield_protect(max_risk_score=50.0)
async def login(request: Request):
    # This code only executes if Synapse Shield verifies the request as Human
    return {"status": "success", "message": "Authenticated successfully"}
```

### 2. Frontend Integration (Vanilla JS Sync)

Include the SDK (<5 KB) and wrap your sensitive form submission:

```html
<!-- Include SDK -->
<script src="http://your-server:8000/static/synapse-sdk.js"></script>

<script>
  // Initialize biometric listener
  SynapseShield.init();

  async function handleLogin() {
    // Automatically retrieves challenge, packages telemetry, and submits to verification endpoint
    const response = await SynapseShield.submit("/api/score");
    console.log("Evaluation Result:", response);
  }
</script>
```

---

## 🤖 Attack Simulation Benchmarks

Synapse Shield includes an automated adversarial test suite simulating 7 distinct attack vectors:

| Test Scenario          | Attack Signature                          | Detection Mechanism                       | Decision  | Risk Score |
| :--------------------- | :---------------------------------------- | :---------------------------------------- | :-------- | :--------- |
| **Natural Human**      | Organic curves with tremors               | Biological Jerk & Deceleration verified   | **ALLOW** | <10.0%     |
| **Linear Bot**         | Selenium straight-line cursor             | $\text{Straightness} = 1.000$ & Zero Jerk | **BLOCK** | 98.5%      |
| **Replay Attacker**    | Reuse of valid telemetry signature        | Cryptographic Token Reused / Stale        | **BLOCK** | 100.0%     |
| **Fitts Violator Bot** | Direct speed click - no terminal slowdown | `terminal_decel_ratio > 0.85`             | **BLOCK** | 80.0%      |
| **Poisson Flooder**    | 8 rapid requests in $<500\text{ ms}$      | Poisson frequency anomaly ($P > 95\%$)    | **BLOCK** | 85.0%      |
| **Selenium Webdriver** | Automated headless crawler                | `navigator.webdriver = true`              | **BLOCK** | 100.0%     |
| **Robotic Auto-Typer** | Constant 50ms keystrokes                  | $\text{Key Variance} < 1.0\text{ ms}^2$   | **BLOCK** | 92.0%      |

---

## 🧠 Kinematic & Mathematical Foundation

Synapse Shield extracts physical motion vectors derived from classical biomechanics:

**1. Jerk (Acceleration Derivative):**
$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$
Human neuromuscular micro-tremors produce continuous high-frequency Jerk, whereas mathematical bot curves (Bézier/Linear) produce near-zero or static Jerk.

**2. Fitts's Target Deceleration Profile:**
$$\text{Terminal Decel Ratio} = \frac{\bar{v}_{\text{terminal}}}{v_{\text{max}}}$$
Humans reflexively slow down when approaching a target click button ($\text{Terminal Decel Ratio} < 0.40$), whereas simple click bots maintain monotonic high speeds during clicks.

**3. Poisson Request Rate Anomaly:**
$$P(X \ge k) = 1 - \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

---

## 📁 Repository Structure

```
Synapse_Shield/
├── pyproject.toml              # PyPI Paket Tanımı & Yapılandırması
├── README.md                   # Proje dokümantasyonu
├── LICENSE                     # MIT Lisans dosyası
├── requirements.txt            # Gerekli kütüphaneler listesi
└── src/
    └── synapse_shield/         # Asıl Kütüphane Paketi
        ├── __init__.py         # Dışa aktarılan API (shield_protect, SynapseEngine)
        ├── engine.py           # Karar motoru
        ├── features.py         # Kinematik matematik modülü
        ├── middleware.py       # FastAPI dekoratörü
        ├── cli.py              # Terminal komutu (synapse-shield run / test)
        ├── tokens.py           # Kriptografik Challenge-Response token üretimi & doğrulaması
        ├── live_attacker.py    # Saldırı simülatörü
        └── static/             # Gömülü arayüz ve JS SDK
            ├── index.html
            └── synapse-sdk.js
```

---

## 📜 License

Distributed under the MIT License. Free for both commercial and personal use.
