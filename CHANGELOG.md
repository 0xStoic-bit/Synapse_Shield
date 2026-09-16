# Changelog

All notable changes to the Synapse Shield project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
