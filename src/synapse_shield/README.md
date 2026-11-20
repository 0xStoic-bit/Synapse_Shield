# `synapse_shield` Python package

Module map for contributors. Users should start with the [main README](../../README.md) and the [docs](../../docs/README.md).

## Request path

| Module | Role |
| :--- | :--- |
| `tokens.py` | Signed single-use challenges (`generate_challenge`), token verification (signature, age, client binding, nonce burn), proof-of-work salts and verification |
| `core.py` | `evaluate_synapse_request[_sync]`: the shared decision function behind every adapter (IP ban, rate limit, token, scoring, challenge policy, strikes, replay fingerprint, shadow mode). Returns a `SynapseDecision` |
| `features.py` | Feature extraction from telemetry (kinematics, keystrokes, browser fields). Uses the Rust core when it is loaded, the pure-Python path otherwise; both must agree to 1e-5 |
| `engine.py` | `analyze_behavior`: turns features into a 0-100 risk score with reasons (rules, session invariance, short-trace limits, CNN in shadow) |
| `models.py` | NumPy 1D-CNN; weight resolution (`SYNAPSE_WEIGHTS_PATH` or bundled) and `SYNAPSE_CNN_MODE` |
| `fingerprint.py` | Keyed trajectory fingerprint for replay detection |
| `storage.py` | Nonces, strikes, bans, device penalties, session history, fingerprints; SQLite (default) and Redis backends |
| `privacy.py` | Server-side Zero-PII guard: masks any typed character that still reaches the server |
| `rules.py`, `cohort.py` | Stable rule codes and shadow-mode cohorts |
| `metrics.py` | Prometheus counters |

## Framework adapters

`middleware.py` (FastAPI middleware and `@shield_protect`), `asgi.py`, `django.py`, `flask.py`, `litestar.py`, `sanic.py`. Each one only extracts the token, IP and User-Agent and calls `core.py`.

## Server, CLI and tooling

| Module | Role |
| :--- | :--- |
| `main.py` | The built-in FastAPI server: `/api/challenge`, `/api/score`, admin endpoints, dashboard, logging |
| `static/` | Dashboard (`index.html`), demo store page and the browser SDK (`synapse-sdk.js`) |
| `cli.py` | `synapse-shield run / test / redteam / benchmark / retrain / replay / telemetry / doctor` |
| `doctor.py` | Environment and installation checks (native core version, weights, secrets) |
| `replay.py` | Offline replay of recorded telemetry |
| `train.py` | CNN fine-tuning (`retrain`) |
| `adversarial.py`, `live_attacker.py`, `redteam_plugin.py` | Synthetic attack generators and the red-team suites |
| `benchmark.py` | Micro-benchmarks |
| `weights.npz` | Bundled CNN weights (trained on synthetic data; used in shadow mode only by default) |
| `synapse_core_rs*.pyd` / `.so` | Compiled Rust core (gitignored, built by maturin); see [crates/synapse_core_rs](../../crates/synapse_core_rs/README.md) |
