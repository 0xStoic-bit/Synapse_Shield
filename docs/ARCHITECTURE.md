# Architecture

How a request is checked, what the engine measures, and where the code lives.
Back to the [documentation index](README.md).

## Request flow

```text
┌─────────────────┐             ┌─────────────────────┐             ┌─────────────────────────┐
│  Client browser │             │  Your app + Synapse │             │  Decision engine        │
│  (SDK)          │             │  middleware         │             │  (engine.py / Rust)     │
└────────┬────────┘             └──────────┬──────────┘             └────────────┬────────────┘
         │── 1. GET /api/challenge ───────►│                                     │
         │◄── 2. { nonce.ts.bind.sig } ────│  single-use, HMAC-signed, bound to  │
         │                                 │  client subnet + User-Agent         │
   [visitor moves / taps / types]          │                                     │
   [SDK records timing, masks text]        │                                     │
         │── 3. request + X-Synapse-Token ►│  verify signature, age (1.5-60 s),  │
         │                                 │  binding, then burn the nonce       │
         │                                 │── 4. score (worker thread) ────────►│ kinematics, keystrokes,
         │                                 │                                     │ browser integrity,
         │                                 │                                     │ session history
         │                                 │◄── 5. risk 0-100 + reasons ─────────│
         │                                 │  6. policy: allow / challenge / block, strikes, replay fingerprint
         │◄── 7. 2xx (your handler) / 429 challenge / 403 block
```

## Defence layers

| Layer | What it checks | Main code |
| :--- | :--- | :--- |
| 1. Cryptographic tokens | HMAC-SHA256 single-use challenges, minimum human time (1.5 s), 60 s maximum age, client binding, atomic nonce burn (SQLite or Redis `SET NX`) | `tokens.py`, `storage.py` |
| 2. Behavioural kinematics | Cursor and touch physics: jerk, curvature, straightness, Fitts's-law deceleration, sub-movements, tremor spectrum; keystroke dwell / flight timing | `features.py`, `engine.py`, Rust `crates/synapse_core_rs` |
| 3. 1D-CNN sequence model | 60-step movement model. **Shadow mode by default** (computed, not used to decide) | `models.py`, `train.py` |
| 4. Client integrity | Headless and stealth signs: `navigator.webdriver`, fake plugin arrays, hooked WebGL / Canvas, mobile GPU mismatch | SDKs, `engine.py` |
| 5. Network and replay | Request rate (Poisson anomaly, extreme-rate ban), IP strikes, per-device penalty, trajectory replay fingerprint, session shape invariance | `core.py`, `main.py`, `fingerprint.py`, `storage.py` |

A single weak signal is not enough to block a person: for example a privacy browser's canvas noise (Brave farbling) on its own never blocks, and keyboard-only typing (no mouse movement, at least 3 keystrokes) leads to a background proof-of-work, not a block.

### Decision policy

- **Risk < 35:** allow. **35-55:** gray area, challenged when proof-of-work applies. **≥ 50** (`max_risk_score`): block, unless a challenge applies.
- Keyboard-only sessions and short pointer traces (<40 samples) that would otherwise be allowed always get a challenge.
- Hard violations (no interaction, webdriver / stealth, session invariance, replay) are never offered a challenge.
- See [Configuration](CONFIGURATION.md) for the strike and ban rules.

## Kinematic foundations

**Jerk (neuromuscular tremor).** Human muscle produces continuous high-frequency jerk; mathematical curves (linear, Bézier) produce near-zero or constant jerk.

$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$

**Fitts's-law terminal deceleration.** People slow down as they approach the click target (ratio below about 0.40).

$$\text{Terminal decel ratio} = \frac{\bar{v}_{\text{last 25\%}}}{v_{\text{peak}}}$$

**Differential curvature.** Computed only where the cursor actually moves (both neighbouring steps ≥ 5 px), so a person stopping on a target is not mistaken for chaotic motion.

$$\kappa(t) = \frac{|\dot{x}\ddot{y} - \dot{y}\ddot{x}|}{(\dot{x}^2 + \dot{y}^2 + \epsilon)^{3/2}}$$

**Poisson request anomaly.** Bursts that are unlikely under normal arrival rates raise risk (λ = 2.0).

$$P(X < k) = \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

**Evidence limits.** Short traces (<40 samples) carry little information: the straightness, FFT and sub-movement rules together add at most 45 risk there. The tremor spectrum (`spectral_entropy`) is computed but not used as a rule, because on real data it only separated bots that other rules already catch.

## Repository layout

```text
Synapse_Shield/
├── src/synapse_shield/        Python package (engine, adapters, server, CLI)    → src/synapse_shield/README.md
├── crates/synapse_core_rs/    Rust core (PyO3 abi3, SIMD kinematics, nonce cache) → crates/synapse_core_rs/README.md
├── synapse-shield-react/      React / Next.js SDK
├── synapse-shield-vue/        Vue 3 / Nuxt 3 SDK
├── tests/                     Python test suite                                  → tests/README.md
├── sdk-tests/                 Vitest suite for the three browser SDKs           → sdk-tests/README.md
├── scripts/                   Attack simulators, benchmarks, release helpers     → scripts/README.md
├── deploy/monitoring/         Grafana dashboard and Prometheus alerts            → deploy/monitoring/README.md
├── docs/                      This documentation
├── .github/workflows/         ci.yml (tests), wheels.yml (Linux/macOS/Windows wheels), mutation.yml
├── Dockerfile, docker-compose.yml
└── pyproject.toml             Package definition (built with maturin)
```
