# Privacy and Operator Notes

This document describes what Synapse Shield actually does with data, as read from the code. It is **not legal advice**. Whether a deployment is lawful depends on the operator's context, jurisdiction and configuration; that assessment is the operator's responsibility. File references point to `src/synapse_shield/` unless noted. Defaults can change between releases; re-check against the version you deploy.

## 1. What is processed

| Data | Notes | Where |
|---|---|---|
| Pointer / touch coordinates and timestamps | Used to compute kinematic features (jerk, curvature, straightness, ...) | `features.py`, `engine.py` |
| Key timings (down/up times) | Key *identity* is masked: anything not on a closed list of control keys (`Enter`, `ArrowLeft`, `F1`-`F24`, ...) becomes `"masked"` on the server after token verification, regardless of SDK version | `privacy.py` |
| Clicks, scrolls, browser signals | Browser signals are used for headless/automation checks | `engine.py` |
| `input_events` counters | `{t, kind}` only (autofill / paste / IME / insert), no content. Observation only; not used in the decision | `engine.py` |
| IP address | Used for ban/strike logic and token binding. Under GDPR an IP address is generally treated as personal data | `core.py` (`resolve_client_ip`) |
| User-Agent | Used for token binding, the device penalty key, and (see section 2) written to the log table in reduced form | `main.py` |

## 2. What is stored, for how long, how to reduce it

| Store | Contents | Retention | Control |
|---|---|---|---|
| Raw telemetry (`logs.telemetry`) | Full coordinates/timings **only if** opted in; otherwise `{}` | Same as `logs` | Off by default. `SYNAPSE_STORE_RAW_TELEMETRY=1` enables (`main.py` `store_raw_telemetry_enabled`, `save_log`) |
| `logs` table | `timestamp, ip, user_agent, bot_score, classification, threat_type, reasons, features, telemetry` (`main.py` `init_db`) | Rows older than `SYNAPSE_LOG_RETENTION_DAYS` (default 14) are deleted by `prune_old_records`, which runs at process start and then at most every `SYNAPSE_LOG_PRUNE_INTERVAL_SEC` (default 600) on the log-write path (`maybe_prune_old_records`); also capped to the newest 5000 rows on every insert (`save_log`) | Retention env var; admin clear endpoints |
| `logs.ip` | Anonymized before insert per `SYNAPSE_PRIVACY_MODE`: default `strict` = /24 (IPv4) or /64 (IPv6) truncation; `hash` = daily-rotating HMAC digest (`core.py` `anonymize_ip`; `main.py` `save_log`) | as above | `SYNAPSE_PRIVACY_MODE` |
| `logs.user_agent` | Follows `SYNAPSE_PRIVACY_MODE` (`main.py` `privacy_user_agent`): `strict` (default) stores a coarse family such as `Chrome/131 Windows`; `hash` stores `ua_` + HMAC-SHA256(SECRET_KEY, UA) truncated to 16 hex; `off` stores the raw string capped at 512 chars. Rows written before v0.10.9 are not migrated | as above | `SYNAPSE_PRIVACY_MODE`; shorten retention or scrub old rows yourself |
| IP bans / strikes (`banned_ips`, `ip_strikes`; Redis `synapse:ban:*`) | Raw IP (the keys must match incoming IPs) | Strike window 60 s; ban 60 s (`main.py` `record_ip_decision`) | Durations are hard-coded; admin unban/clear |
| Request-rate counter (Poisson anomaly, >100 req/10 s ban) | Raw IP as key, timestamps only; SQLite backend keeps it in process memory, Redis in `synapse:req_count:<ip>` ZSETs | 10 s window (Redis key TTL 20 s) | Inherent; the `logs` table is not used for counting (`storage.py` `record_and_get_request_count`) |
| Per-device penalty (`client_strikes`) | `HMAC-SHA256(SECRET_KEY, IP + UA)` truncated; no raw IP/UA | 60 s window | Inherent (`storage.py` `client_strike_key`) |
| Trajectory fingerprint (`trajectory_fps`) | Keyed delta fingerprint of the pointer path; raw trace not kept | 1 h default (`SYNAPSE_TRAJECTORY_FP_TTL`, minimum 60 s) | `SYNAPSE_TRAJECTORY_REPLAY=0` disables (`core.py`, `fingerprint.py`) |
| Nonces (`used_nonces`) | Opaque random values with an expiry | Challenge/token lifetime (60 s, `tokens.py`) | Inherent |
| Session history (`session_telemetry`) | Per session id: `avg_jerk`, `straightness`, `total_distance` only, and only for trajectories with at least 3 points | Last 10 entries within a 300 s window (`main.py`, `core.py`, `storage.py` `record_session_telemetry`) | Inherent |
| `/api/collect_dataset` | Writes mouse / keystroke (sanitized) / click / scroll / browser payload to `raw_telemetry` in the dataset DB (`main.py`) | Pruned with `SYNAPSE_LOG_RETENTION_DAYS` | **Not automatic.** Requires admin auth (`verify_admin`) and an explicit POST; the middleware never calls it. Do not wire it to end users without a legal basis |
| Log export (`/api/logs/export`) | Admin-only; IP is re-masked on output (`tests/test_admin_surface.py::test_log_export_masks_ips_and_requires_admin`) | n/a | Do not expose admin endpoints publicly |
| Webhooks | Outbound IP is masked (`main.py` `send_webhook_notification`) | n/a | Leave webhook URLs empty |

**Flags for operators**
- The export masks the IP and prints `logs.user_agent` as stored, i.e. already reduced per `SYNAPSE_PRIVACY_MODE` (older rows may still hold raw UAs).
- Ban/strike tables hold raw IPs (short-lived), while `logs.ip` holds the anonymized form.
- In-memory caches (session history, L1 caches) are not governed by the retention setting.
- Without a shared backend override, the process-local fallback stores for trajectory fingerprints and per-device penalties are hard-capped at 100,000 keys each (`storage.py` `MEMORY_STORE_MAX_KEYS`); when full, the oldest keys are dropped even inside their TTL.
- The IP-only shape history (`ipshape_<ip>`, a 64-bit shape SimHash per entry) is written only for allowed requests, so a blocked or challenged client cannot seed it.

**Multiple pods and key rotation.** Every pod must run with the same `SYNAPSE_SECRET_KEY`: it keys the per-device penalty key (`client_strike_key`), the trajectory fingerprint (`fingerprint.py`) and the hyperplanes of the shape SimHash (#39-C). Pods with different keys produce different values for the same device or trajectory, so penalties, replay detection and shape invariance silently stop matching across pods. When the key is rotated, entries written under the old key lose their meaning until they expire: at most about 1 hour for trajectory fingerprints (`SYNAPSE_TRAJECTORY_FP_TTL`), 300 s for shape histories and 60 s for device penalties. Replays and template rotations during that window are not caught by these checks; rotate during low traffic, or accept the gap.

## 3. Automated decisions and appeals

Decisions are made by rules and a heuristic score, with no human in the loop (`engine.py`, `main.py`, `core.py`).

| Situation | Outcome | Reference |
|---|---|---|
| IP currently banned (4 hard bot verdicts in 60 s) | 403 block | `core.py` |
| Missing / invalid / replayed token, hard rule violation, score at or above the block threshold | Block | `core.py`, `main.py` |
| Gray area (35 <= score < 55, no hard violation), reference server | Always a PoW challenge (429) | `main.py` |
| Middleware, `SYNAPSE_ENABLE_POW` unset | Score below `max_risk_score` (50): allow; otherwise block | `core.py` |
| Middleware, `SYNAPSE_ENABLE_POW=1` | Gray area gets a PoW challenge | `core.py` |
| Keyboard-only sessions (3+ keys) and very short traces | Challenge instead of a plain allow; never turns a block into a challenge. `SYNAPSE_KEYBOARD_ONLY_CHALLENGE=0` disables | `core.py`, `engine.py` |
| Shadow mode | Decision is computed and reported (`shadow_block`) but the request passes | `core.py` |

The library provides **no appeal or human-review mechanism**. Operators whose blocks affect people should provide their own route (contact form, alternate verification) and may want to start in shadow mode. Whether Art. 22 GDPR or similar rules apply to a given use is for the operator and their counsel to assess.

## 4. Redis outage: nonce fail-open

When Redis is unreachable, `consume_nonce` falls back to the local store (`storage.py`; deliberate fail-open, availability over strict cross-pod replay protection). Consequences:
- Each pod then tracks nonces only locally, so a token may be replayed once per pod during the outage. Nonces consumed locally are not copied back to Redis on recovery.
- Bounds: tokens are valid for about 60 s (`tokens.py`) and are bound to a client IP/UA hash (`compute_client_binding_hash`), so replay from a different client still fails.
- Bans are mirrored to the local fallback and keep applying during an outage (`storage.py` `ban_ip`).
- Recommendation: run a highly available Redis and alert on the `Redis ... failed` warnings. All pods must share the same `SYNAPSE_SECRET_KEY`, otherwise tokens and per-device keys do not match across pods.

## 5. 1D-CNN

`SYNAPSE_CNN_MODE` defaults to `shadow`: the probability is computed but does not influence the decision (`models.py`, `engine.py`). Reason: the bundled weights were trained on synthetic data and showed roughly 19% false-positive rate on real human data. `enforce` exists for weights you have validated yourself, loaded via `SYNAPSE_WEIGHTS_PATH` (`models.py`; `train.py` for retraining).

## 6. Accessibility

| User | Behavior |
|---|---|
| Keyboard-only, screen reader | Not blocked on that basis alone; receive a PoW challenge (`engine.py`, `core.py`) |
| Touch laptops, iPad + keyboard | Scored on whatever signals are present; single taps do not enter session history (`core.py`) |
| Clients that cannot solve PoW (integrations without the SDK) | Receive 429 and cannot proceed (`core.py`) |

Operators should test their real assistive-technology flows; the library has not been validated against a population of assistive-technology users.

## 7. Regulatory context (operator responsibility)

- **GDPR**: IP addresses and User-Agent strings may be personal data. Legal basis (for example legitimate interests and the balancing test), notices, retention and processor terms are for the operator to decide.
- **ePrivacy**: reading device/browser signals may fall under local rules on access to terminal equipment. Ask local counsel.
- **EU AI Act**: the system does not identify individuals; scope and risk classification of a deployment is the operator's assessment.
- **PCI-DSS 6.4.3**: `scripts/sri_hash.py` produces Subresource Integrity hashes for the served SDK script. It supports, but does not by itself satisfy, the requirement.

## 8. Note on detection figures

Human-side measurements come from the public SapiMouse dataset and a simulator; bot-side figures come from synthetic and red-team generated traffic. The system has **not** been validated against real-world bot traffic, so reported rates should not be read as production accuracy. Determined adversaries (human click farms, analog replay rigs, adaptive generators) can evade behavioral detection.
