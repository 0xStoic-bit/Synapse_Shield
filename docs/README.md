# Synapse Shield documentation

New here? Start with the [main README](../README.md): install, a 5-minute integration and what your users will see.

| Guide | What's in it |
| :--- | :--- |
| [Integrations](INTEGRATIONS.md) | FastAPI, Django, Flask, Litestar, Sanic, ASGI; React, Vue and plain JS SDKs; proof-of-work challenges; Subresource Integrity |
| [Configuration](CONFIGURATION.md) | Every environment variable, detection policy, IP strikes and bans, 1D-CNN and retraining, Redis, logs, Prometheus, Telegram / Discord alerts |
| [Shadow mode](SHADOW_MODE.md) | Measure what enforcing would do on real traffic, per cohort, before blocking anyone; offline replay of recordings |
| [Privacy notes for operators](PRIVACY_OPERATOR_NOTES.md) | What is processed and stored, for how long, and how to turn it off |
| [Architecture](ARCHITECTURE.md) | Request flow, defence layers, decision policy, the kinematic maths, repository layout |
| [Benchmarks](BENCHMARKS.md) | Real-human false positives, the attack simulation suite, known limits |
| [Feature history](FEATURES.md) | Every feature by release |

Per-folder guides:

| Folder | Guide |
| :--- | :--- |
| `src/synapse_shield/` | [Python package: module map](../src/synapse_shield/README.md) |
| `crates/synapse_core_rs/` | [Rust core: build and test](../crates/synapse_core_rs/README.md) |
| `tests/` | [Python tests, coverage and mutation testing](../tests/README.md) |
| `sdk-tests/` | [Browser SDK tests](../sdk-tests/README.md) |
| `synapse-shield-react/` | [React / Next.js SDK](../synapse-shield-react/README.md) |
| `synapse-shield-vue/` | [Vue 3 / Nuxt 3 SDK](../synapse-shield-vue/README.md) |
| `scripts/` | [Attack simulators, benchmarks and release helpers](../scripts/README.md) |
| `deploy/monitoring/` | [Grafana dashboard and Prometheus alerts](../deploy/monitoring/README.md) |

Security issues: see [SECURITY.md](../SECURITY.md).
