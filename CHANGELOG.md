# Changelog

All notable changes to the Synapse Shield project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.8] - 2026-10-20
### Security & Performance Overhaul
- **[P0] Comprehensive Cryptographic & Biometric Vulnerability Patches:**
  - **Brave Farbling Camouflage Bypass Prevention:** Expanded `has_critical_bot_anomaly` to enforce DSP spectral purity, differential curvature ($\kappa(t) \ge 0.75$), 1D-CNN AI confidence ($\ge 50\%$), high heuristic risk ($\ge 70\%$), and session invariance checks. Prevents spoofed `is_webgl_hooked: true` signals from forcing scores down to 34.0.
  - **Telemetry Timestamp Drift & Stale Replay Defense:** Enforced cryptographic timestamp validation rejecting future-dated packets ($t > \text{server\_time} + 15\text{s}$) and stale payloads ($t < \text{server\_time} - 120\text{s}$) even with valid HMAC signatures.
  - **Ruler Straight Line & Instantaneous Teleportation Macro Bot Defense:** Lowered kinematic analysis threshold to `mouse_points >= 3` to detect 3-5 point linear bots (`straightness > 0.985`). Flagged 1-2 point desktop click events as instantaneous cursor teleportation (`LINEAR_MACRO`, +60 Risk).
  - **Zero-Event Telemetry Enforcement:** Flagged empty telemetry payloads (`total_interactive_events == 0`) with +60 Risk, terminating headless spoofing.
  - **Keystroke Dwell Time Pairing:** Refactored dwell time calculation to key-code-specific tracking queues (`pending_downs[code]`), fixing cross-key interleaving inaccuracies in typing biometrics.
  - **DoS & Token Size Limiter:** Enforced a strict 64 KB token payload cap, neutralizing memory exhaustion attempts before Base64 decoding.
  - **Robust Secret Key File Access:** Wrapped `secret.key` filesystem reads in `try ... except OSError:`, resolving `PermissionError: [WinError 5]` in Windows sandbox and read-only container environments.
- **[P0] Sub-Millisecond Latency & AI Vectorization (23.84 ms $\rightarrow$ 0.84 ms):**
  - **Vectorized 1D-CNN Inference:** Eliminated sequential 60-step loops via NumPy `sliding_window_view` and BLAS matrix multiplication, slashing AI inference time from $0.481\text{ ms}$ to **$0.092\text{ ms}$** (**5.2x speedup**).
  - **Thread-Local Persistent SQLite & WAL Mode:** Replaced per-request connection creation with thread-local pooling and enabled `PRAGMA journal_mode=WAL` with `synchronous=NORMAL`.
  - **L1 In-Memory Sliding Window Caches:** Implemented in-memory sliding window deques for IP bans, bot strikes, and session telemetry, reducing reads from disk queries to **~20 nanoseconds**.
  - **Throttled Nonce Maintenance:** Throttled expired nonce sweeps to once every 60 seconds, eliminating frequent database write-lock contention.
- **[P1] Alpine Linux (musllinux) Native Rust Wheels:**
  - Added automated GitHub Actions matrix jobs building `musllinux_1_2` wheels (`x86_64` and `aarch64`) for Alpine Docker deployments, tested via `test-alpine`.

## [0.9.7] - 2026-10-16
### Security & Architectural Hardening
- **[P0] Cryptographic Parity Across All Frameworks (Django & Flask Hardening):**
  - Integrated `evaluate_synapse_request_sync` across both Django (`synapse_shield.django`) and Flask (`synapse_shield.flask`).
  - Patched critical cryptographic bypass by enforcing HMAC token verification (`verify_and_consume_token`), Replay attack defense, IP ban checks, 256 KB memory DoS caps, and session behavioral history.
- **[P0] Reverse Proxy & Load Balancer IP Resolution:**
  - Implemented `resolve_client_ip` supporting `SYNAPSE_TRUSTED_PROXIES` environment configuration.
  - Traverses `X-Forwarded-For` chains and validates `CF-Connecting-IP` / `X-Real-IP`, preventing proxy IP quarantine and ensuring legitimate users are never blocked behind Cloudflare, Nginx, or AWS ALB.
- **[P0] First-Class `X-Synapse-Token` HTTP Header Support:**
  - Added primary support for `X-Synapse-Token`, `X-Synapse-PoW-Nonce`, and `X-Synapse-PoW-Salt` headers across ASGI, FastAPI, Litestar, Sanic, Flask, and Django.
  - Eliminates JSON body schema collisions (e.g. strict Pydantic `extra="forbid"`) and enables seamless protection for `multipart/form-data` file uploads.
- **[P1] Enterprise Shadow Mode (`mode="shadow"` / `dry_run=True`):**
  - Added non-blocking dry-run evaluation mode across all middlewares and guards.
  - Silently evaluates incoming sessions, emits `X-Synapse-Decision: shadow-block` response headers and Prometheus telemetry without blocking users.
- **[P1] Proof-of-Work (PoW) Gray Area Flow in Middleware:**
  - Extended core evaluation engine to support Smart Challenge (PoW) on gray area classifications (`35 <= bot_score <= 65`), returning HTTP 429 Challenge Required and validating solved PoW nonces.
- **[P1] Zero-PII Compliance & Automatic Data Retention TTL:**
  - Added `SYNAPSE_PRIVACY_MODE=hash` (daily salt-rotated HMAC-SHA256) and `strict` (/24 truncate) IP anonymization.
  - Added automatic database TTL pruning job (`prune_old_records`) purging records older than `SYNAPSE_LOG_RETENTION_DAYS` (default 14 days) to prevent disk inflation.
- **[P2] Packaging, PEP 561 Typing & SDK Improvements:**
  - Added `src/synapse_shield/py.typed` and comprehensive `synapse_core_rs.pyi` type stubs for native Rust functions.
  - Decoupled `fastapi`, `uvicorn`, and `websockets` from core dependencies into optional `[server]` extra.
  - Added `SynapseShield.protectFetch()` and `SynapseShield.protectAxios()` auto-interceptors in `synapse-sdk.js`.
  - Upgraded React (`synapse-shield-react`) and Vue (`synapse-shield-vue`) SDKs to v0.9.7 with SSR-safe (`typeof window`) guards.

## [0.9.6] - 2026-10-14
### Added & Multi-Framework Support
- **[P0] Universal ASGI 3.0 Middleware (`synapse_shield.asgi`):**
  - High-performance, zero-framework-dependency ASGI 3.0 middleware (`SynapseShieldASGIMiddleware`).
  - Implements stream replay safety via a closure-wrapped `replayable_receive` callable, allowing downstream handlers to parse request bodies without stream exhaustion or hanging.
  - Enforces strict 256 KB memory DoS protection (`MAX_PAYLOAD_SIZE = 262_144` $\rightarrow$ HTTP 413 Payload Too Large) at stream-read time.
  - Injects verified telemetry and decision context directly into `scope['state']['synapse_telemetry']`.
- **[P0] Idiomatic Litestar Integration (`synapse_shield.litestar`):**
  - Native Litestar route guard `synapse_guard` (`guards=[synapse_guard(max_risk_score=40.0)]`).
  - Native Litestar application middleware `LitestarSynapseMiddleware`.
- **[P0] Dual-Mode Sanic Integration (`synapse_shield.sanic`):**
  - Native route decorator `@shield_protect_sanic(max_risk_score=50.0)`.
  - Native Sanic request middleware `SynapseSanicMiddleware`.
  - Works natively with both Sanic's custom HTTP engine and ASGI servers.
- **[P1] Centralized Security Engine (`synapse_shield.core`):**
  - Extracted framework-agnostic `evaluate_synapse_request` and `SynapseDecision` to provide a single, non-duplicative security source of truth.

## [0.8.0] - 2026-09-23
### Added & Performance Optimization (Native Rust Core & Distributed Defense)
- **[P0] Native Rust Two-Bucket In-Memory Nonce Cache (`crates/synapse_core_rs`):**
  - Implemented rotating $O(1)$ `TwoBucketNonceStore` in native Rust with PyO3 bindings, replacing disk-based SQLite replay lookups.
  - Slashed cryptographic nonce verification latency from $984\,\mu s$ to **$0.8\,\mu s$** (**1,200x speedup** / ~794,000 ops/sec).
- **[P0] Sub-Microsecond L1 IP Ban In-Memory Cache:**
  - Implemented thread-safe `RwLock<HashMap<String, u64>>` in Rust delivering ~15 ns IP quarantine checks.
  - Added cold-start SQLite hydration and dual-write persistence to guarantee zero ban loss across restarts.
- **[P0] Multi-Platform Binary Wheel Matrix (`.github/workflows/wheels.yml`):**
  - Added automated GitHub Actions matrix using `PyO3/maturin-action` to build and publish pre-compiled binary wheels across Linux (`manylinux_2_28_x86_64`, `aarch64`), Windows (`x64`), and macOS (`x86_64`, `arm64`).
- **[P1] Distributed Botnet DDoS & Load Testing Suite:**
  - Implemented `scripts/flood_10k_stress.py` verifying system resilience under a 10,000-request distributed attack across 250 zombie IPs with zero crashes, zero dropped connections, and zero `database is locked` errors.
  - Added Locust simulation suite (`tests/locustfile.py`) with 4 concurrent personas (`LegitimateHumanUser`, `ReplayAttackBot`, `SyntheticLinearBot`, `RapidFloodBot`).
  - Added interactive live-streaming ANSI attack visualizer (`scripts/attack_sim.py`).
- **[P1] Graceful Storage Fallback & Clean Token Pipeline:**
  - `SQLiteStorageBackend` transparently degrades to optimized disk queries if the native extension is absent.
  - Bypassed periodic disk cleanup scans during high-throughput token verification when the Two-Bucket engine is active.
- **[P1] Unit Test Suite Expansion:**
  - Added `tests/test_rust_core.py` covering Two-Bucket deduplication, L1 ban lifecycles, and SQLite fallback (all 84 pytest tests passing).

## [0.7.9] - 2026-09-22
### Added & Performance Benchmarking
- **[P0] Microsecond Latency & Throughput Benchmark Suite (`synapse_shield.benchmark`):**
  - Integrated high-precision microsecond ($\mu s$) timing harness profiling 19D Kinematics ($73.7\,\mu s$), 1D-CNN NumPy inference ($451.2\,\mu s$), HMAC crypto verification ($961.8\,\mu s$), and end-to-end evaluation pipeline ($828.1\,\mu s$).
  - Produces formatted ASCII/Markdown console reports with Mean, P50, P95, P99, and single-core throughput (~$1,200$ req/sec).
  - Added CLI command: `synapse-shield benchmark [--iterations N] [--export FILE]`.
- **[P0] Biological Human Telemetry Generator (`synapse_shield.adversarial`):**
  - Implemented `generate_synthetic_human_telemetry()` utilizing multi-bell submovement decomposition (ballistic primary burst + 2 corrective homing pulses with velocity valleys), wrist/elbow biomechanical curvature, and inertia-filtered low-pass neuromuscular pink-noise micro-tremor (100% human classification accuracy).
- **[P0] Isolated Weights Architecture & Active Learning Bootstrap (`synapse_shield.train`):**
  - Added `--bootstrap` training flag to synthesize balanced human and adversarial bot telemetry batches, enabling safe active learning calibration even in empty or newly deployed databases without class collapse.
  - Implemented non-invasive weight saving: fine-tuning writes to local `./synapse_weights.npz` (or `SYNAPSE_WEIGHTS_PATH`) by default, completely isolating package distribution weights from test and retraining pollution.
  - Upgraded `SynapseHybridModel` weight loading hierarchy: `SYNAPSE_WEIGHTS_PATH` $\rightarrow$ `./synapse_weights.npz` $\rightarrow$ default bundled `weights.npz`.

## [0.7.8] - 2026-09-21
### Security & Architectural Hardening
- **[P0] FFT Tremor Spectral Analysis (DSP):** Integrated Fast Fourier Transform (`numpy.fft.rfft`) into kinematic feature extraction. Calculates Power Spectral Density (PSD), `spectral_purity`, and normalized `spectral_entropy` to distinguish biological stochastic tremor from artificial harmonic oscillators ($\sin(2\pi ft)$).
- **[P0] Sub-Movement Kinematic Decomposition:** Decomposed mouse trajectories into discrete corrective velocity pulses based on Fitts's Law and Flash & Hogan kinematic theory. Trajectories lacking physiological sub-movements (`submovement_count <= 1` across >60px) or showing superhuman stutter (>18 peaks) are unconditionally mitigated.
- **[P1] Session-Level Behavioral Invariance Detection:** Introduced stateful sliding-window session telemetry tracking in SQLite (`session_telemetry` table) and Redis (`synapse:session:{key}`). Detects bots repeating deterministic kinetic templates (zero jerk or straightness variance across consecutive requests).
- **[P1] Adversarial Training Pipeline:** Added modular synthetic telemetry generators (`synapse_shield.adversarial`) producing Bézier, sinusoidal oscillator, and minimum-jerk curves. Integrated synthetic bot injection into `train.py` active learning to eliminate 1D-CNN out-of-distribution blindspots.

### Added & Improved
- **Zero-Dependency Guarantee:** Maintained zero external runtime dependencies by leveraging NumPy's native FFT engine.
- **Package Synchronization:** Synchronized Python core, JavaScript SDK (`synapse-sdk.js`), React SDK (`synapse-shield-react`), and Vue SDK (`synapse-shield-vue`) packages to `v0.7.8`.

## [0.7.7] - 2026-09-20
### Security
- **[P0] Stored XSS Mitigation:** Enforced HTML entity sanitization (`escapeHtml`) across all client-rendered fields in the cockpit (`index.html`), preventing script injection via spoofed telemetry and User-Agent headers.
- **[P0] WebSocket Terminal Authentication:** Enforced `SYNAPSE_ADMIN_SECRET` query-token validation on `/ws/terminal`, immediately terminating unauthorized handshakes with `WS_1008_POLICY_VIOLATION`.
- **[P0] Webhook SSRF & DNS Rebinding Defense:** Protected webhook settings with admin verification, HTTPS scheme enforcement, and domain allowlisting (`ALLOWED_WEBHOOK_DOMAINS = {"discord.com", "discordapp.com", "api.telegram.org"}`).
- **[P0] Gated Brave Farbling Exemption:** Gated the 34.0% risk cap to require zero critical bot anomalies (`has_critical_bot_anomaly`), preventing automated scrapers from evading mitigation under farbling noise.
- **[P1] Single-Use PoW Nonce Consumption:** Bound solved Proof-of-Work puzzles to single-use storage keys (`pow:{salt}:{nonce}`) with 120s TTL to prevent challenge reuse.
- **[P1] Early Challenge Nonce Invalidation:** Consumed challenge nonces immediately after signature verification to prevent probe-and-retry exploits against velocity and timing thresholds.
- **[P1] AI Training Data Sanitization:** Filtered `/api/collect_dataset` and `load_training_data` to ensure only verified, organic human sessions without farbling exemptions are admitted into model retraining pipelines.

### Added & Improved
- **[P2] Multi-Worker SQLite Composite Index:** Added `idx_ip_strikes_ip_ts` composite index on the `ip_strikes` table, replacing linear scans with sub-millisecond query execution during attack floods.
- **[P2] Granular Token Expiration:** Separated expired tokens (`HTTP 400 EXPIRED`) from replay strikes, allowing the JavaScript SDK to transparently refresh challenges without incurring IP penalties.
- **[P2] Keystroke DoS Protection:** Capped input array sizes (150 items max) and refactored hold-time computation to $O(N)$ with queued key tracking.
- **[P2] Middleware Quarantine Synchronization:** Integrated atomic IP ban status checks and bot strike tracking directly into `@shield_protect` and `SynapseShieldMiddleware`.
- **Package Synchronization:** Synchronized Python core, JavaScript SDK, React SDK (`synapse-shield-react`), and Vue SDK (`synapse-shield-vue`) packages to `v0.7.7`.

## [0.7.6] - 2026-09-16
### Added
- Real-time Webhook Notification Engine: Non-blocking background alerting for critical threats (`BLOCK` / Dynamic IP Bans) dispatched to configured Discord and Telegram webhooks.
- Webhook management endpoints (`GET /api/settings/webhooks`, `POST /api/settings/webhooks`) for dynamic runtime configuration.
- Interactive Webhook modal in the Synapse Shield Cockpit (`index.html`) with live feedback and state persistence in SQLite.
- Fully synchronized SDK, Vue, and React package versions to v0.7.6.

### Fixed
- Fixed mock targeting in `tests/test_sdk.py` to correctly reference `engine._ai_model.predict`.

## [0.7.5] - 2026-09-14
### Added
- PyPI health score optimizations (`classifiers` and full `urls` in `pyproject.toml`).
- GitHub community issue templates (`bug_report.md` and `feature_request.md`).

## [0.7.3] - 2026-09-13
### Added
- Enterprise distributed state & cluster management architecture via `StorageBackend` interface in `storage.py`.
- Atomic multi-server Replay Attack protection powered by Redis `SET key 1 EX 120 NX`, eliminating race conditions across load-balanced instances.
- Cluster-wide IP quarantine and sliding-window bot strike synchronization across distributed worker nodes.
- Resilient zero-downtime runtime fallback: seamlessly degrades to local SQLite storage with `socket_timeout=1.5s` if Redis disconnects or crashes mid-flight.
- Optional dependency `redis>=5.0.0` in `pyproject.toml` (`pip install synapse-shield[redis]`).
- Comprehensive multi-worker stress test suite `tests/test_storage.py` and `scripts/stress_test_distributed.py` validating 4-worker concurrency and self-healing failover.

## [0.7.2] - 2026-09-12
### Added
- Native mobile & touchscreen biometrics in `synapse-sdk.js` via passive `touchstart`, `touchmove`, and `touchend` listeners to prevent false-positive penalties on mobile devices.
- Dynamic Proof-of-Work (PoW) difficulty validator supporting arbitrary hex zero lengths with event loop yielding to eliminate UI freezing.
- Robust UTF-8 Base64 encoding fallback (`safeBtoa`) in the SDK to prevent DOMException errors on international locales and Unicode characters.
- Anti-stealth prototype defense extracting unpolluted native `Function.prototype.toString` via hidden iframe to detect sophisticated browser hooks.
- Immutability safeguards locking `window.SynapseShield` via `Object.freeze` and non-writable property descriptors against runtime tampering.
- Comprehensive test suite `tests/test_sdk.py` validating SDK static serving, UTF-8 token decodes, PoW retry verification, and mobile touch kinematics.

### Fixed
- Fixed critical PoW retry replay-attack bug where `challenge_required` retried with the already-consumed challenge token instead of proactively acquiring a fresh challenge.
- Fixed telemetry time-travel detection violation on PoW retries by re-windowing event timestamps to match the active challenge lifecycle.

## [0.7.1] - 2026-09-09
### Added
- Admin authentication enforcement for the `/api/clear` endpoint using `SYNAPSE_ADMIN_SECRET`.
- Native `SynapseHybridModel` unit tests and end-to-end framework test coverage for Flask and Django middleware.
- Configurable environment variable `SYNAPSE_MIN_ELAPSED_MS` to accelerate local test suites without triggering time manipulation blocks.
- Extensive GitHub Actions CI workflow with Pytest coverage tracking and Ruff linting.
- Community guidelines including `SECURITY.md`, `CHANGELOG.md`, and `CONTRIBUTING.md`.

### Changed
- Refactored token handling to automatically ensure the `used_nonces` table is created, fixing an `OperationalError` when used as middleware.
- Updated `is_plugin_array_fake` detection from `Array.isArray` to `Object.prototype.toString.call` to patch a V8 prototype logic flaw.
- Improved sliding window IP quarantine mechanism to utilize TTL and LRU-based eviction rather than clearing the whole dictionary at the 10,000 threshold.
- Optimized engine concurrency by moving blocking operations (`get_recent_request_count`, `is_ip_banned`) into `asyncio.to_thread`.
- Removed dead code (`velocity_skewness` calculation) from the features extraction pipeline.
- Improved Red Team test coverage in `live_attacker.py` to correctly evaluate Replay Attacks.

### Fixed
- Fixed an issue in `train.py` where saving weights could cause file corruption during concurrent access by utilizing temporary files and atomic `os.replace`.
- Addressed `Timezone` comparison bug in `is_ip_banned` for compatibility with Python 3.11+.

### Security
- Introduced a hard limit of 256 KB on `/api/score` payloads, enforcing it during read to prevent `Transfer-Encoding: chunked` memory inflation attacks.

## [0.6.2] - 2026-09-02
### Added
- 1D-CNN AI Engine (The Micro-Brain) with zero PyTorch/Tensorflow dependencies.
- Cryptographic Proof of Work (Smart Challenge) fallback mechanisms.
- Late fusion architecture for kinematics and static environmental variables.

### Changed
- Overhauled Red Team test scripts, integrating advanced Stealth Evasion, Bezier Ghost Cursor, and Headless detection tests.

## [0.1.0] - 2026-08-25
### Added
- Initial release of Synapse Shield Behavioral Biometrics framework.
- Basic HMAC-SHA256 Challenge/Response integration.
- Sliding Window IP Quarantine mechanism.
