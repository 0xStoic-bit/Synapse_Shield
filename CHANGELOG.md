# Changelog

All notable changes to the Synapse Shield project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
