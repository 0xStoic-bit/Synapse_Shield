# Changelog

All notable changes to the Synapse Shield project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.5] - 2026-11-07
### Test Infrastructure & Zero-PII Leak Fix
- **[Critical] Zero-PII keystroke leak closed in all three SDKs (Vanilla JS, React, Vue):**
  - The v0.10.4 mask only covered keys whose value was exactly one UTF-16 unit (`rawKey.length === 1`). Single key presses longer than one unit were sent **in clear text**: emoji (`😀`), astral-plane letters (`𝒜`), ligature keys such as Arabic lam-alef (`لا`), combining sequences (`e` + U+0301) and **Turkish capital `İ`** (`"İ".toLowerCase()` is two code units).
  - New `telemetryKeyName()` rule: only standard named keys matching `/^[A-Z][A-Za-z0-9]+$/` (`Enter`, `Backspace`, `ArrowLeft`, `Unidentified`, `Process`, `F1`, …) are sent by name (lower-cased); everything else is `"masked"`. Sensitive fields still mask everything. Server-side feature extraction is unchanged.
- **[High] New JS SDK test suite (`sdk-tests/`, Vitest + jsdom):** one Zero-PII contract runs against Vanilla JS, React and Vue (56 tests: 18 Vanilla + 19 React + 19 Vue, the hook SDKs add an unmount case) plus 6 Vanilla token-lifecycle tests. Before the fix 18 of them failed (6 per SDK, the leak above); now 62/62 pass.
- **[High] Rust core unit tests:** 37 new tests across `keystrokes.rs` (dwell/flight statistics, IME majority/minority rule from v0.10.3, entropy bounds), `curvature.rs` (geometric curvature `1/R` recovery, AVX2 ↔ scalar parity for every remainder length, raw-pointer entry) and `kinematics.rs` (300-point cap, Fitts deceleration, mobile GPU mismatch, touch & tap statistics). Total Rust tests: 3 → 40.
- **[High] CI hardening (`.github/workflows/ci.yml`):** new `rust` job (`cargo test --all-targets`), new `sdk` job (Vitest + `tsc --noEmit` for React and Vue), and the Python job now fails if the native Rust core is not loaded, so Rust ↔ Python parity tests can no longer be silently skipped.
- **Known gaps documented as tests:**
  - ~~`test_masked_sdk_digraph_flag_rust_python_parity`: Rust ignored the client-side `is_freq_digraph` flag (0.40 in Python vs 0.00 in Rust).~~ **Fixed later in this release**; see "Production-Readiness Fixes" below.
  - `curvature::tests::independent_gaussian_like_jitter_is_flagged` (`#[ignore]`): curvature variance thresholds are absolute and scale-dependent; per-point jitter was flagged in only 1 of 10 probed amplitude/speed configurations.
- **Docs:** README / README_ZH gained a "Testing" section; masking description updated; repository tree lists `sdk-tests/`.
- **Repo hygiene:** `.gitignore` keeps `sdk-tests/package-lock.json` (reproducible `npm ci`) and ignores `sdk-tests/coverage/`, `CLAUDE.md`, `.claude/`.

### Coverage to 85%+, Mutation Testing & Bugs Found Along the Way
- **[High] Malformed token crashed the verifier (HTTP 500) and bypassed strike/ban accounting (`tokens.py`):** a token that decodes to valid JSON of the wrong shape (`[]`, `null`, `"x"`, `{"challenge": 123}`), or a validly signed token whose `telemetry` / event lists have the wrong type, raised `AttributeError` / `TypeError`. Every integration (FastAPI, Flask, Sanic, Litestar, Django, ASGI) answered with HTTP 500. Because the exception fired before the decision, the request was never recorded as a bot strike, so an attacker could probe indefinitely without being quarantined. Now these requests are rejected with a normal token error, which records a strike, and 4 such requests ban the IP. Telemetry type checks run *after* the nonce is consumed, so a malformed request still burns its challenge (no Probe & Retry).
- **[High] Redis sliding-window counters merged same-tick events (`storage.py`):** sorted-set members were `f"{time}:{time_ns}"`. On coarse clocks (Windows ticks are about 0.5–15 ms) or across concurrent workers, two events got the same member and `ZADD` collapsed them. The result undercounted both bot strikes and the request-flood counter: a burst of N requests could count as 1. Members now carry a random suffix (`_unique_member()`). A frozen-clock regression test fails on the old code and passes on the new.
- **[Medium] Red-team suite measured the wrong layer (`live_attacker.py`, `redteam_plugin.py`):** `get_challenge()` fetched challenges without the attack's IP and User-Agent, so since the v0.10.1 client binding *every* vector was rejected as `TOKEN_RELAY_ATTACK` before reaching the biometric engine. The replay vector used different names (and so different UAs) for its two sends, so it measured relay, not replay. Gateway rejections (`{"detail": ...}`) carried no verdict and were reported as "❌ BAŞARISIZ". Fixed: the challenge and the attack share IP + UA; HTTP 4xx/5xx counts as a block. The mobile-human control now uses the real SDK touch schema (`source: "touch"`, `r`, `f`, `tap_duration_ms`). The desktop-human control no longer uses a fixed 25 ms timer (itself a bot signature) and decelerates before the click.
- **[High] New test suites (Python 174 → 432; all layers 276 → 536, final counts after the readiness fixes below):**
  - `test_framework_contract.py`: one security contract (no token, valid human, replay, header token, webdriver bot, shadow mode, 256 KB limit, path and method pass-through) run through the *real* FastAPI, Flask, Sanic (`sanic-testing`) and Litestar request pipelines. It replaces MagicMock request objects.
  - `test_storage_backends.py`: Redis on `fakeredis` (real SET NX / ZSET / LIST semantics); Redis → SQLite failover for every operation; SQLite multi-worker disk paths; L1 map bounds; unusable-DB behaviour (nonces fail closed); Rust L1 hydration.
  - `test_crypto_core_edges.py`: every BLOCK/ALLOW branch of `tokens.py` and `core.py`, including the gray-area PoW flow (risk-adaptive difficulty 4/5, solved PoW lowers risk and cannot be replayed, hard bot signals never get a PoW escape hatch), extreme-frequency ban, shadow mode, secret-key loading, proxy IP resolution and Prometheus counters.
  - `test_admin_surface.py`: webhook alerts reach only the configured Discord/Telegram hosts; SSRF guard (non-HTTPS, look-alike domains); log export never contains raw IPs; WebSocket console Origin check and every command; dataset limits; challenge rate limiter.
  - `test_redteam_tooling.py`: the 9-vector `synapse-shield test` suite runs end-to-end in-process (urllib routed to TestClient, no network) and each verdict is asserted, including that no vector is short-circuited by relay binding. Also covers the plugin orchestrator and every CLI sub-command.
- **Coverage:** Python line coverage 67.4% → **~90%**, line + branch 65.5% → **87.8%**. `tokens.py` 77 → 99%, `storage.py` 61 → 95%, `core.py` 73 → 93%, `main.py` 64 → 93%, `flask.py` 46 → 91%, `sanic.py` 41 → 91%, `cli.py` / `live_attacker.py` / `redteam_plugin.py` 0 → 85–93%.
- **CI:** the Python job installs `sanic-testing redis fakeredis prometheus-client` and enforces `--cov-branch --cov-fail-under=85`. New `.github/workflows/mutation.yml` runs mutmut on the security core weekly (Mon 03:00 UTC) and on demand; config in `[tool.mutmut]` (`pyproject.toml`). `mutants/` is ignored.
- **Mutation testing (local, mutmut 2.5.1 on Windows; mutmut 3 needs Linux/WSL and Docker Desktop failed to start):** 1,189 mutants over `tokens.py`, `core.py`, `storage.py`, full test selection per module, source restored from a pristine copy before every mutant. Measured score **~88%** (1,008 killed / 137 survived of 1,145 evaluated; tokens 90.5%, core 88.0%, storage 86.2%; killed ÷ (killed + survived)). 44 mutants were not evaluated and a watchdog killed ~86 hung test processes (counted as killed), so treat the figure as approximate; CI's weekly mutmut 3 run gives the authoritative number. An earlier run reported 92.1% but was inflated: mutmut left mutated source in the shards, so that figure was discarded. About half of the survivors are log/message-string mutations that do not change behaviour. Survivors drove new tests (`tests/test_mutation_gaps.py`, `tests/test_mutation_gaps2.py`): secret-key file mode `0600`, key persistence, `SYNAPSE_DB_PATH`, cleanup throttling, an IP-spoofing matrix for `resolve_client_ip`, corrupt ban rows not stopping Rust hydration, SQLite PRAGMAs, the decision wire contract (JSON keys, `X-Synapse-*` headers), the PoW difficulty step at 45, and the abstract storage base class.
- **Known gaps documented as tests (not fixed):**
  - ~~Redis outage fail-open~~ **Fixed below.**
  - ~~Inconsistent `protected_paths=[]` semantics~~ **Fixed below (breaking, fail-safe).**

### Production-Readiness Fixes
- **[High] Rust core now reads the SDK's `is_freq_digraph` flag (`keystrokes.rs`, `lib.rs`):** `DetailedKeystroke` gained `is_freq_digraph: Option<bool>`, propagated with the same down/up pairing rules as `features.py`. When the flag is present, the "direct flights" comparison is used, as in Python. Rust previously ignored it, so the v0.10.4 client-side digraph feature never ran in production, where the Rust core is active. Also, Rust counted key length in UTF-8 bytes (`"ş"` = 2) while Python counted characters; it now uses `chars().count()`. Removed the `xfail` from `test_masked_sdk_digraph_flag_rust_python_parity`. A new 200-sample differential fuzz test (`test_masked_sdk_keystrokes_differential_fuzz`) shows Rust and Python agree on all samples; before the fix 25 of 60 disagreed. Three new Rust unit tests; Rust total 40 → 43.
- **[High] Server-side Zero-PII guard (`privacy.py`, new):** SDKs up to 0.10.4 and hand-rolled clients could still send typed characters. After token verification, every key that is not a named key (`/^[A-Za-z][A-Za-z0-9]+$/`) becomes `"masked"`, so raw text no longer reaches the scoring engine, `request.state.synapse_telemetry`, logs or `/api/collect_dataset`, which previously wrote raw keystrokes to disk. Before masking, `is_freq_digraph` is derived from the raw sequence exactly like the SDK, so scoring is unchanged (the test asserts identical scores before and after masking). Payloads from current SDKs are returned untouched. 10 tests in `test_server_pii_guard.py`. *Behaviour note:* legacy clients now go through the same digraph scoring path as current SDKs.
- **[High] Redis ban mirroring (`storage.py`):** `RedisStorageBackend.ban_ip` / `unban_ip` also write to the SQLite fallback, so bans stay enforced during a Redis outage (previously fail-open). A failing mirror never breaks banning.
- **[Medium] README benchmark table re-measured:** new `scripts/measure_readme_benchmarks.py` (in-process, no network). Selenium, Linear, Bézier, Auto-Typer and Replay are all BLOCK 100%. Natural human is ALLOW in 50 of 50 seeds. **The "Poisson Flooder → BLOCK 60%" claim does not hold:** 8 human-looking requests in ~315 ms are only flagged (risk 25%, 0 of 8 blocked), because the Poisson signal is suppressed for organic kinematics. Hard blocking starts at `SYNAPSE_MAX_REQ_10S` (100 requests per 10 s) or after 4 bot verdicts in 60 s. README and README_ZH now carry the measured table and this note; detection logic is unchanged.
- **Docs:** `SECURITY.md` supported versions are now 0.10.x stable, 0.9.x critical patches only, < 0.9 EOL, plus a note about legacy-SDK keystroke leaks and the new server-side guard.
- **[Breaking, security] Unified `protected_paths` semantics:** an empty or missing list now protects **every** `POST`/`PUT`/`PATCH` route in all six adapters (fail-safe). Previously Flask (`SynapseFlaskMiddleware`), FastAPI (`SynapseShieldMiddleware`) and Django (`SYNAPSE_SHIELD_PROTECTED_PATHS` unset) protected **nothing**, while Sanic, Litestar and raw ASGI protected everything, so adding the middleware without paths silently disabled protection on half of the integrations. *Migration:* apps that relied on an empty list being a no-op must list their paths explicitly. Covered by `test_empty_protected_paths_protect_every_mutating_route_in_all_adapters` (6 adapters × `None` / `[]`). README / README_ZH document the rule.
- **Test isolation fix:** `tests/test_frameworks.py::test_sanic_integration_mock` replaced `synapse_shield.sanic.sanic_json` with a stub and never restored it, so every Sanic test that ran after it returned HTTP 500. The bug was hidden only by alphabetical file order.
- **Still open:** curvature jitter thresholds are scale-dependent; the real-user false-positive rate is unmeasured (needs a shadow-mode pilot); burst flooding with organic-looking traces is flagged but not blocked (design decision).

### External Review Fixes (all 10 findings verified and fixed)
An independent review of the readiness work was verified against the code with live probes. Eight findings were reproduced and fixed here; each has a regression test in `tests/test_review_findings.py` or `sdk-tests/`.
- **[Critical] Scroll-only requests were allowed (`engine.py`, `core.py`):** a request with no mouse, click, key or touch events and a single scroll event scored 0% (ALLOW) because scroll counted as interaction. Scroll alone no longer counts as deliberate interaction (the zero-event rule fires, `DESKTOP_SCROLL_ONLY_SUBMISSION` reason) and `core.py` treats it as a hard bot signal, so the gray-area PoW escape hatch is closed. Accessibility mode keeps the old behaviour.
- **[Critical] Real mobile users were blocked on the 4th single tap (`engine.py`, `core.py`, `main.py`):** a single tap has no trajectory, so the extractor left placeholder values (jerk 0, straightness 1, distance 0). These were stored in session history and the 4th tap tripped both "zero straightness variance" (+50) and "fuzzy similarity" (+70): 100% Bot, HTTP 403, no PoW rescue. Session history now stores only real trajectories (>= 3 points and distance > 0), and the engine also ignores placeholder entries that are already stored (`total_distance == 0`). Keyboard-only (Enter) users were affected the same way.
- **[High] Short zero-entropy line bypass (`engine.py`):** every desktop kinematic rule was gated on `total_distance > 30/50/60`, so a 25px, 6-point, constant-speed, fixed-interval line scored 0%. New rule D2: 4+ points, 5px < distance <= 30px, straightness >= 0.99999, velocity variance < 1e-6 and dt variance < 0.01 together are flagged (+60, softened in accessibility mode). Timing jitter alone does not trigger it.
- **[High] Zero-PII allow-list (`privacy.py` + Vanilla/React/Vue SDKs):** the regex guesses (`^[A-Za-z][A-Za-z0-9]+$` on the server, `^[A-Z][A-Za-z0-9]+$` in the SDKs) let any whole word through unmasked (`Mustafa`, `Sifre123`). Replaced by one closed allow-list (`NAMED_KEYS`: Enter, Backspace, Tab, Shift, Control, Alt, AltGraph, Meta, CapsLock, Escape, arrows, Home/End/PageUp/PageDown, Insert, Delete, Dead, Process, Unidentified, NumLock, ScrollLock, ContextMenu, Pause, PrintScreen, Clear, Compose, F1-F24), case-insensitive. Everything else is `"masked"`. A test asserts the four lists are identical.
- **[High] CI Rust job could not link on Linux (`Cargo.toml`, `pyproject.toml`, `ci.yml`):** `pyo3` was pinned with the `extension-module` feature, which suppresses libpython linking and breaks `cargo test` on Linux. It is now an optional feature (`extension-module = ["pyo3/extension-module"]`) enabled for wheels through `[tool.maturin] features`. Verified locally that `maturin develop` passes `--features pyo3/extension-module` and that `cargo test` passes without it; **the Linux link itself could not be run here and is the first thing the PR's CI must confirm.** The CI step also sets `LD_LIBRARY_PATH` for libpython.
- **[High] Vue PoW and single-use challenge (`synapse-shield-vue`, `synapse-shield-react`):** Vue's `solvePow` generated a random client salt and hashed `challenge + salt + nonce`, which the server can never accept; it now takes the signed `pow_salt`, hashes `salt + nonce` and is bounded at 20M attempts (**signature change:** `solvePow(powSalt, difficulty = 4)`). React and Vue `getProtectedPayload()` now consume the single-use challenge and fetch the next one in the background, so a second submission in the same SPA session no longer replays it.
- **[High] Litestar guard parity (`litestar.py`):** the guard had no 256 KB limit (now 413 via `Content-Length` and body size), answered a PoW challenge with 403 instead of 429 + challenge body, and `LitestarSynapseMiddleware` rebuilt its ASGI handler on every request (now built once). `enable_pow` is now a parameter of the Litestar guard and middleware, `shield_protect_flask`, `SynapseFlaskMiddleware`, `shield_protect_sanic`, `SynapseSanicMiddleware` and `SYNAPSE_SHIELD_ENABLE_POW` (Django), matching the ASGI and FastAPI adapters.
- **[Medium] Timestamp window ignored fields (`tokens.py`):** the 65 s freshness check read only `"t"`, while the feature extractors read `"t"`, `"down"`, `"up"` and `"time"`. Events carrying only `down`/`up` skipped the check. All four fields are validated now, and booleans (an `int` subclass in Python) are rejected as timestamps.
- **[Low] Test hygiene and digraph set:** the Sanic contract tests skip cleanly when Sanic is not installed; React and Vue had two extra digraphs (`da`, `te`) that the Vanilla SDK, `privacy.py` and Rust did not, now identical in all five places (a test enforces it).
- **Test fixtures:** about a dozen "human" fixtures were a perfectly straight, 20 ms-constant diagonal line. The new micro-trajectory rule correctly flags that, so they now carry realistic timing jitter. Python 432 -> 536 tests (+1 skipped), JS 62 -> 78; coverage 88.1%.
- **[High, breaking] HTTP `DELETE` bypassed every adapter (`core.py` + 6 adapters):** all six adapters returned early for anything but `POST`/`PUT`/`PATCH`, so a token-less `DELETE /api/account/123` on a protected path reached the handler (HTTP 200), even from a banned IP. A shared `core.PROTECTED_METHODS = ("POST", "PUT", "PATCH", "DELETE")` is now used by `middleware.py`, `asgi.py`, `flask.py`, `django.py`, `sanic.py` and `litestar.py`. **Upgrade note:** clients that issue `DELETE` to a protected path without a Synapse token now get 403. A body-less `DELETE` carries its token in the `X-Synapse-Token` header (all adapters already read it). Unprotected paths are unaffected.
- **[High] `main.py` gateway parity and exposure (`main.py`):**
  - `session_id` is now `ip_<ip>_<ua_hash>` like `core.py`, so users behind one CGNAT / Eduroam address no longer share and poison each other's behavioural history.
  - The PoW challenge difficulty is risk-adaptive (5 from risk 45, else 4) and the signed salt carries the same value; it was fixed at 4.
  - `GET /metrics` (live nonce and ban counters, L1 rotation timing) now requires the admin secret (`X-Admin-Secret` or `Authorization: Bearer`). **Upgrade note:** Prometheus-style scrapers must send it.
  - `/api/score` accepts the token and PoW values from the `X-Synapse-Token`, `X-Synapse-Pow-Nonce` and `X-Synapse-Pow-Salt` headers like every adapter, and a non-object JSON body now returns 400 instead of crashing.
  - `SYNAPSE_PRIVACY_MODE` is honoured everywhere: the `logs` table, the WebSocket console broadcast and the Discord/Telegram webhooks previously carried the raw client IP; they now carry the masked or hashed value.
- **Mutation score:** the ~88% figure was measured before these changes; the new code has not been mutation-tested.

## [0.10.4] - 2026-11-04
### Zero-PII Keystroke Privacy & Multi-Framework SDK Hardening
- **[Critical] True Zero-PII In-Transit Keystroke Masking (GDPR Art. 5(1)(c) & KVKK Art. 4 Compliance):**
  - **Universal Single-Character Masking:** Extended client-side keystroke masking across Vanilla JS (`synapse-sdk.js`), React (`useSynapseShield.ts`), and Vue 3 (`useSynapseShield.ts`) to immediately mask all single-character inputs (`rawKey.length === 1 -> key: "masked"`).
  - **Zero Raw Text in Transit:** No raw typed character (whether from password fields, usernames, or search boxes) is ever transmitted over the network in token envelopes.
  - **Client-Side Digraph Parity:** Linguistic digraph frequency (`is_freq_digraph`) is pre-computed in client memory prior to masking, preserving full kinematic and muscle-memory bot detection fidelity.
  - **Functional Key Preservation:** Preserved virtual IME indicators (`"unidentified"`, `"process"`) and navigation control events (`"enter"`, `"backspace"`) to ensure 100% Android/iOS soft-keyboard and typing flight-time entropy detection.
- **[High] React & Vue SDK Hardening:**
  - Added `FREQUENT_DIGRAPHS` set and `isSensitiveInput` regex detection to React and Vue hooks.
  - Resolved `lookupId` collision in concurrent keystroke down/up tracking via `e.code || rawKey`.
  - Added SSR-safe `declare const Buffer` definitions for headless and Node.js environments.

## [0.10.3] - 2026-11-04
### Adversarial Red-Team Hardening & Dual-Model Security Audit
- **[Critical] IME Virtual Keyboard Bypass Remediation:**
  - **Strict Majority Enforcement:** Removed the single-touch heuristic in Python feature extractor (`features.py`) to align 100% with Rust SIMD core (`keystrokes.rs`). Dwell-time evaluation is only bypassed when >= 50% of keys are genuine IME virtual inputs (`unidentified` / `process`), terminating the adversarial exploit where bots injected `touch_supported=True` to zero out dwell analysis.
- **[High] Client-Side Infinite Expiry Retry Guard:**
  - **Bounded Recursion (`_retried = true`):** Capped transparent token expiration retries in `synapse-sdk.js` to exactly 1 attempt, preventing client-side CPU exhaustion and infinite network loops during server clock-skew or upstream reverse-proxy misconfigurations.
- **[High] Enforced Token Client-Binding on Bound Challenges:**
  - **Context-Bound Token Validation:** Patched `verify_and_consume_token` in `tokens.py` to strictly reject client-bound challenges whenever `client_ip` and `user_agent` are omitted by callers, preventing token relay exploitation through unauthenticated verification paths.
- **[High] 64-bit CGNAT & Campus Network Session Collision Shield:**
  - **Doubled UA Hash Entropy:** Expanded `ua_hash` in `session_id` from 8 hex chars (32 bits) to 16 hex chars (64 bits), moving the birthday bound collision threshold from ~65k to > 4 billion distinct client sessions on shared NAT and Eduroam networks.
- **[Medium] Risk-Adaptive Proof-of-Work (PoW) Difficulty:**
  - **Dynamic Scaling:** Dynamically scales PoW challenge difficulty based on the calculated risk score (diff=5 for risk >= 45%, diff=4 for risk between 35% and 44%).
- **[Low] Secret Key Hex Decoding Support:**
  - **Entropy Density Maximization:** Added automatic `bytes.fromhex()` decoding for 64-character hex keys configured via `SYNAPSE_SECRET_KEY`, ensuring full 32-byte binary entropy density.

## [0.10.2] - 2026-11-04
### Privacy, SPA Lifecycle, Proxy CIDR & Infrastructure Resilience
- **[P0] Keystroke Zero-PII Shield (GDPR / HIPAA / PCI-DSS Level 1 Compliance):**
  - **Client-Side Masking (`key: "masked"`):** Automatically identifies sensitive inputs (password, credit card, CVV, PIN, token, security code) and strips raw character data in ephemeral client memory before telemetry construction.
  - **Client-Side Linguistic Scoring (`is_freq_digraph`):** Evaluates frequent digraph correlations in ephemeral memory without recording or transmitting character pairs, maintaining high anti-bot discriminative power while transmitting zero Personally Identifiable Information across the wire.
- **[P0] SPA Token Lifecycle & Refresh Mutex:**
  - **Single-Use Token Invalidation:** Automatically invalidates `currentChallenge` upon payload consumption, eliminating false-positive 403 Replay Attack rejections in Single-Page Applications (React, Vue, Next.js).
  - **Token Staleness & Coalescing Mutex:** Transparently auto-refreshes challenge tokens older than 45 seconds and coalesces concurrent `/api/challenge` requests via inflight promise deduplication.
- **[P0] Proof-of-Work (PoW) Hardening & Telemetry Window Shift:**
  - **Dynamic Signed Difficulty (`salt.ts.diff.sig`):** Cryptographically signs adaptive difficulty into the PoW challenge envelope, preventing malicious downgrade attacks.
  - **Telemetry Retention on PoW Retry:** Shifts historical telemetry timestamps forward to align with the fresh challenge creation window instead of purging them, eliminating false-positive 403 blocks (`total_interactive_events == 0`) for legitimate humans solving PoW.
  - **Middleware End-to-End Enablement:** Ensured `enable_pow=True` propagates reliably across all ASGI, WSGI, Litestar, Django, Sanic, and Flask integration middleware layers.
- **[P0] Trusted Reverse Proxy CIDR & Header Sanitization:**
  - **CIDR Subnet Resolution:** Added native CIDR parsing (`ipaddress.ip_network`) for `SYNAPSE_TRUSTED_PROXIES` (e.g. `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `173.245.48.0/20`), enabling seamless enterprise deployment behind Cloudflare, AWS ALB, and Kubernetes Ingress controllers.
  - **IP Header Syntax Validation:** Validates `X-Forwarded-For`, `CF-Connecting-IP`, and `X-Real-IP` strings against strict RFC IP syntax before trusting proxy hops, preventing header injection and malformed IP attacks.
- **[P1] CGNAT & Campus NAT Collision Mitigation:**
  - **User-Agent Session Partitioning:** Incorporated User-Agent SHA-256 hash into session identifiers (`ip_{client_ip}_{ua_hash}`), preventing multi-user collisions on carrier-grade NAT and university networks (e.g. Eduroam).
  - **Configurable DoS Threshold:** Added `SYNAPSE_MAX_REQ_10S` environment variable (default: 100 req/10s) for flexible rate limit tuning.
- **[P1] IME Dwell-Time Bypass Patch:**
  - Enforced touch capability or majority requirement for mobile IME keys (`unidentified` / `process`), preventing desktop bots from claiming virtual IME status to bypass mechanical switch dwell checks in both Rust SIMD and Python feature extractors.

## [0.10.1] - 2026-11-01
### Cryptographic Hardening, Token Relay Defense & Diagnostics
- **[P0] Cryptographic Client Network Binding (`nonce.ts.bind_hash.sig`):**
  - **Token Relay & Harvesting Farm Mitigation:** Bound challenges directly to the client's network subnet (`/24` IPv4, `/64` IPv6) and case-normalized User-Agent via a deterministic 16-character HMAC digest (`compute_client_binding_hash`). Tokens acquired by clean solver IPs or real browsers cannot be transferred to headless scrapers or distributed bot networks (`TOKEN_RELAY_ATTACK`, +100 Risk).
  - **Roaming Subnet Tolerance:** Allows legitimate dynamic IP shifts within the client's ISP carrier subnet block (`/24` or `/64`) while terminating unauthorized cross-network token transfers.
  - **Backward Compatibility:** Seamlessly verifies legacy unbound challenges unless `SYNAPSE_TOKEN_BINDING=strict` is configured.
- **[P1] Leak-Free SQLite Connection Lifecycle Management:**
  - Implemented thread-safe `_open_connections` registry with mutex protection (`_connections_lock`), guaranteeing clean teardown of all worker connections in multi-threaded Uvicorn/ASGI environments.
- **[P1] Synapse Shield Doctor CLI (`synapse-shield doctor`):**
  - Added built-in diagnostic health audit tool verifying Python runtime (>= 3.10), Native Rust SIMD Core status, 1D-CNN neural weights integrity, HMAC secret key entropy, SQLite WAL health, and reverse proxy IP resolution.

## [0.10.0] - 2026-10-27
### Security, Mobile SDK v2.0 & Kinematic Hardening
- **[P0] Mobile SDK v2.0 & Handheld Biometric Engine:**
  - **Tap Hold Time Biometrics (`tap_duration_ms`):** Captures physical finger press-to-release duration (`touchend - touchstart`) across Vanilla JS (`synapse-sdk.js`), React (`synapse-shield-react`), and Vue (`synapse-shield-vue`). Flags superhuman instantaneous taps (`<8ms` $\rightarrow$ +55 Risk) and deterministic constant-duration multi-taps (`tap_duration_var < 0.5` $\rightarrow$ +50 Risk), while granting organic human hold verification (`15ms–800ms` $\rightarrow$ -10 Risk).
  - **Mobile GPU & Emulator Cross-Validation (`is_mobile_gpu_mismatch`):** Extracts WebGL renderer (`WEBGL_debug_renderer_info`) and `devicePixelRatio` to detect headless/desktop GPU renderers (`SwiftShader`, `llvmpipe`, `Mesa`, `NVIDIA GeForce`, `Radeon`) spoofing mobile touch viewports (+85 Risk, `STEALTH_AUTOMATION`).
  - **Passive Gyroscope/Accelerometer Micro-Tremor (`motion_variance`):** Computes 3-axis handheld acceleration variance via zero-permission passive `devicemotion` listeners, verifying physical handheld device movement (-10 Risk bonus).
  - **Android Gboard / Virtual IME Soft-Keyboard Support:** Exempts mobile virtual keyboard events (`key == "Unidentified"` / `"Process"`, keyCode 229) from mechanical switch dwell-time penalties (`avg_dwell_time < 15ms` and `dwell_time_var < 2.0`) in both Rust SIMD (`keystrokes.rs`) and Python (`features.py`), while preserving flight-time and Shannon entropy checks.
  - **Single-Tap & Flick-Scroll False-Positive Elimination:** Gated the 60-step desktop 1D-CNN model on short touch trajectories (`mouse_points < 12`), exempted `touch_supported` sessions from desktop Fitts's Law and 1–2 point macro-teleportation penalties, and upgraded Click-to-Cursor spatial alignment on touch devices to match against the nearest recorded touch point.

## [0.9.9] - 2026-10-21
### Security & Kinematic Hardening
- **[P0] Mobile Capacitive Touch & Swipe Kinematic Defense:**
  - **Effective Capacitive Proof Validation (`effective_is_touch`):** Patched bypass where desktop bots claimed `"touch_supported": true` to skip all 6 desktop kinematic filters. Enforced strict proof-of-touch requirement: if `mouse_points >= 3` but no capacitive contact data (`touch_event_count == 0`) exists, flagged with +75 Risk (`"Spoofed touch_supported flag on non-capacitive desktop pointer trajectory"`) and forced all desktop kinematic filters to execute.
  - **Synthetic Constant Touch Radius Trap:** Enforced multi-point contact deformation physics. Flagged artificial touch trajectories with zero radius variance (`touch_radius_variance == 0.0` over $\ge 4$ points) with +55 Risk (`"Synthetic touch profile: zero radius variance"`), neutralizing headless mobile emulators.
  - **Mobile Thumb Swipe Curvature & Velocity Dynamics:** Constrained swipe straightness and velocity variance to enforce natural physiological biomechanics during touch interactions.
- **[P0] Proof-of-Work (PoW) Hardening & Challenge Farm Veto:**
  - **Hard Bot Violation Veto:** Strictly denied PoW challenges and immediate bypass to requests triggering critical bot anomalies (zero interaction, instantaneous teleportation, stealth tampering, macro straight lines, and deterministic replay templates). Critical bots receive immediate HTTP 403 blocks with zero PoW escape route.
  - **Narrowed Gray Area Window:** Narrowed PoW challenge issuance strictly to borderline ambiguous scores (`35.0 <= score < 55.0`), eliminating bot exploitation of the previously wider challenge margin.
  - **Cryptographic Client-IP Binding:** Bound PoW challenge HMAC salt directly to the client's resolved IP address, preventing distributed challenge relays, cross-IP replay, and proxy solver farm exploitation.
- **[P0] Golden Trajectory Replay & Spatial Alignment Defense:**
  - **Multi-Dimensional Fuzzy Trajectory Similarity:** Implemented sliding-window trajectory hash and fuzzy kinematic delta matching ($\delta < 0.015$), detecting sophisticated replay attacks using minor perturbation or timestamp shifts across sessions.
  - **Click-to-Cursor Spatial Misalignment Detection:** Enforced coordinate consistency between click events and the final recorded pointer trajectory point ($\Delta d > 50\text{ px}$ flags detached synthetic click injection with +50 Risk).
  - **Monotonic Relative Timestamp & Jitter Validation:** Enforced strict relative timestamp progression to neutralize synthetic batch-injected points.
- **[P0] Secret-Keyed Dynamic Threshold Jitter:**
  - **White-Box Boundary Jitter ($\pm 5\%$):** Implemented deterministic dynamic threshold modulation derived from HMAC-SHA256 of the server's `SECRET_KEY` and epoch window, preventing attackers from probing static decision boundaries (e.g. riding exactly at 34.9 / 49.9).
- **[P0] Storage & Active Learning Anti-Poisoning Architecture:**
  - **Atomic SQLite Sliding-Window Accounting:** Enhanced SQLite storage with atomic transaction boundaries and sliding window queries for request tracking and persistent bot strike accumulation.
  - **Active Learning Training Quota (`train.py`):** Added strict per-IP sample capping ($\le 3$ samples per IP) in the model fine-tuning pipeline, neutralizing adversarial data poisoning attacks designed to distort the 1D-CNN decision manifold.

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
