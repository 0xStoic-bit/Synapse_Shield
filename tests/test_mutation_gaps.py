"""
Boundary and invariant tests written from real mutation-testing survivors (mutmut, 2026-11-06).

Every test here pins a behaviour that a one-token change in the source used to leave undetected:
`>` vs `>=`, a constant off by one, a swapped `and`/`or`, a missing call, a default argument.
Time-dependent code is tested with a frozen clock so that "exactly on the boundary" is reproducible.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import itertools
import json
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from synapse_shield import core, metrics, tokens
from synapse_shield import storage as storage_mod
from synapse_shield.storage import RedisStorageBackend, SQLiteStorageBackend

NOW_S = 1_800_000_000.0
NOW_MS = int(NOW_S * 1000)


@pytest.fixture
def frozen(monkeypatch):
    """Freeze time.time() (module-global, so tokens.py and storage.py both see it)."""
    state = {"t": NOW_S}
    monkeypatch.setattr(time, "time", lambda: state["t"])
    return state


@pytest.fixture
def no_rust(monkeypatch):
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", False)


@pytest.fixture
def sq(tmp_path, no_rust):
    b = SQLiteStorageBackend(db_path=str(tmp_path / "gap.db"))
    yield b
    b.close()


@pytest.fixture
def sq_nodb(tmp_path, no_rust):
    """SQLite backend whose database is unusable, so only the in-memory L1 structures answer."""
    b = SQLiteStorageBackend(db_path=str(tmp_path))
    yield b
    b.close()


# --------------------------------------------------------------------------------------------
# tokens.py — time boundaries
# --------------------------------------------------------------------------------------------


def _b64(obj) -> str:
    raw = obj if isinstance(obj, str) else json.dumps(obj)
    return base64.b64encode(raw.encode()).decode()


def _challenge(ts_ms: int) -> str:
    nonce = secrets.token_hex(16)
    sig = hmac.HMAC(tokens.SECRET_KEY, f"{nonce}:{ts_ms}".encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{ts_ms}.{sig}"


def _verify(ts_ms: int, telemetry=None):
    return tokens.verify_and_consume_token(_b64({"challenge": _challenge(ts_ms), "telemetry": telemetry or {}}))


def _events(min_t: float, max_t: float) -> dict:
    return {"mouse_movements": [{"x": 0, "y": 0, "t": min_t}, {"x": 1, "y": 1, "t": max_t}]}


def test_future_timestamp_boundary(frozen, monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "0")
    ok, reason, _ = _verify(NOW_MS + 5000)
    assert not ok and "Humanly Impossible" in reason, "exactly +5 s is not yet 'future'"
    ok, reason, _ = _verify(NOW_MS + 5001)
    assert not ok and "Gelecek" in reason


def test_default_min_elapsed_is_1500_ms(frozen, monkeypatch):
    monkeypatch.delenv("SYNAPSE_MIN_ELAPSED_MS", raising=False)
    assert _verify(NOW_MS - 1500)[0] is True
    ok, reason, _ = _verify(NOW_MS - 1499)
    assert ok is False and "Humanly Impossible" in reason


def test_token_expiry_boundary(frozen, monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "0")
    assert _verify(NOW_MS - 59_990)[0] is True
    ok, reason, _ = _verify(NOW_MS - 60_040)
    assert ok is False and reason == "TOKEN_EXPIRED", "elapsed is measured in seconds (ms / 1000)"


def test_epoch_telemetry_window_boundaries(frozen, monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "0")
    ts = NOW_MS - 3000
    # lower edge: telemetry may start exactly 5 s before the challenge, not 1 ms earlier
    assert _verify(ts, _events(ts - 5000, ts - 4990))[0] is True
    ok, reason, _ = _verify(ts, _events(ts - 5001, ts - 4990))
    assert ok is False and "Stale" in reason
    # upper edge: telemetry may end exactly 2 s in the future, not 1 ms later
    assert _verify(ts, _events(NOW_MS + 1900, NOW_MS + 2000))[0] is True
    ok, reason, _ = _verify(ts, _events(NOW_MS + 1900, NOW_MS + 2001))
    assert ok is False and "Stale" in reason


def test_epoch_vs_relative_timestamp_switch_at_1e10(frozen, monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "0")
    ts = NOW_MS - 3000
    # exactly 1e10 is still "relative" (no epoch staleness check) ...
    assert _verify(ts, _events(10_000_000_000, 10_000_000_100))[0] is True
    # ... one above is "epoch" and is far older than the challenge
    ok, reason, _ = _verify(ts, _events(10_000_000_001, 10_000_000_100))
    assert ok is False and "Stale" in reason


def test_relative_telemetry_boundaries(frozen, monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "1")
    ts = NOW_MS - 2000  # elapsed = 2000 ms
    assert _verify(ts, _events(2400, 2500))[0] is True, "max_t == elapsed + 500 is allowed"
    assert _verify(ts, _events(1900, 2000))[0] is True, "max_t below elapsed must never be rejected"
    ok, reason, _ = _verify(ts, _events(2401, 2501))
    assert ok is False and "Relative" in reason
    # the check is active as soon as MIN_ELAPSED_MS > 0 (here: 1)
    ok, reason, _ = _verify(ts, _events(2600, 2700))
    assert ok is False and "Relative" in reason


def test_time_travel_duration_boundaries(frozen, monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "1")
    ts = NOW_MS - 2000  # token is 2.0 s old
    assert _verify(ts, _events(0, 2500))[0] is True, "duration == elapsed + 0.5 s is allowed"
    assert _verify(ts, _events(0, 1800))[0] is True, "shorter telemetry is fine"
    ok, reason, _ = _verify(ts, _events(0, 2500.9))
    assert ok is False and "Time Travel" in reason, "duration is measured in seconds (ms / 1000)"


def test_token_size_limit_is_exactly_64kib():
    ok, reason, _ = tokens.verify_and_consume_token("A" * 65536)
    assert not ok and "boyutu" not in reason
    ok, reason, _ = tokens.verify_and_consume_token("A" * 65537)
    assert not ok and "boyutu" in reason


@pytest.mark.parametrize(
    "challenge",
    ["a.b", "n.notanint.sig", f"n.{NOW_MS}.deadbeef"],
)
def test_structurally_invalid_challenges_never_validate(challenge):
    ok, _, tel = tokens.verify_and_consume_token(_b64({"challenge": challenge, "telemetry": {}}))
    assert ok is False and tel == {}


def test_binding_hash_needs_only_one_client_attribute():
    assert tokens.compute_client_binding_hash("1.2.3.4", None) != ""
    assert tokens.compute_client_binding_hash(None, "ua") != ""
    assert tokens.compute_client_binding_hash(None, None) == ""
    assert len(tokens.compute_client_binding_hash("1.2.3.4", "ua")) == 16


def test_challenge_shape_and_defaults():
    ch = tokens.generate_challenge()
    assert ch["expires_in"] == 60
    assert re.fullmatch(r"[0-9a-f]{32}", ch["challenge"].split(".")[0]), "128-bit nonce"
    assert re.fullmatch(r"[0-9a-f]{16}", tokens.generate_pow_salt().split(".")[0]), "64-bit salt"


def test_nonce_and_pow_ttl_is_120_seconds(monkeypatch):
    calls = []

    class Spy:
        def consume_nonce(self, nonce, ttl_sec=None):
            calls.append(ttl_sec)
            return True

    monkeypatch.setattr(tokens, "get_storage", lambda: Spy())
    _verify(NOW_MS - 3000)  # the nonce is consumed (with ttl 120) before any time check
    assert calls == [120]
    calls.clear()
    salt = tokens.generate_pow_salt("9.9.9.9", difficulty=1)
    nonce = next(str(n) for n in itertools.count() if hashlib.sha256(f"{salt}{n}".encode()).hexdigest()[0] == "0")
    assert tokens.verify_and_consume_pow(salt, nonce, client_ip="9.9.9.9", difficulty=1)
    assert calls and set(calls) == {120}


def _pow_salt_at(elapsed_ms: int, difficulty: int = 4) -> str:
    ts = NOW_MS - elapsed_ms
    sig = hmac.HMAC(tokens.SECRET_KEY, f"abcd:{ts}:{difficulty}".encode(), hashlib.sha256).hexdigest()
    return f"abcd.{ts}.{difficulty}.{sig}"


@pytest.mark.parametrize(
    "elapsed_ms,valid",
    [(60_000, True), (60_040, False), (60_500, False), (-5_000, True), (-5_500, False), (30_000, True)],
)
def test_pow_salt_age_window(frozen, elapsed_ms, valid):
    assert tokens.verify_pow_salt(_pow_salt_at(elapsed_ms)) is valid


def test_pow_difficulty_one_needs_a_single_zero_nonce():
    salt = tokens.generate_pow_salt("8.8.8.8", difficulty=1)
    nonce = next(
        str(n)
        for n in itertools.count()
        if (h := hashlib.sha256(f"{salt}{n}".encode()).hexdigest()).startswith("0") and not h.startswith("00")
    )
    assert tokens.verify_and_consume_pow(salt, nonce, client_ip="8.8.8.8", difficulty=1) is True


def test_secret_key_creates_missing_parent_directories(monkeypatch, tmp_path):
    monkeypatch.delenv("SYNAPSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tokens.Path, "home", classmethod(lambda cls: tmp_path / "no" / "such" / "home"))
    with pytest.warns(UserWarning):
        key = tokens._load_or_generate_secret_key()
    assert (tmp_path / "no" / "such" / "home" / ".synapse_shield" / "secret.key").read_bytes() == key


def test_python_nonce_cleanup_boundaries(frozen, monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", False)
    monkeypatch.setattr(tokens, "DB_FILE", str(tmp_path / "n.db"))
    seen = []
    real = sqlite3.connect
    monkeypatch.setattr(tokens.sqlite3, "connect", lambda *a, **k: seen.append(k) or real(*a, **k))
    for last, should_run in [(NOW_S - 30.0, True), (NOW_S - 29.9, False), (NOW_S - 31.0, True), (NOW_S, False)]:
        seen.clear()
        monkeypatch.setattr(tokens, "_last_cleanup_ts", last)
        tokens._cleanup_expired_nonces()
        assert bool(seen) is should_run, last
        if should_run:
            assert seen[0]["timeout"] == 5.0
            assert tokens._last_cleanup_ts == NOW_S


def test_cleanup_timestamp_starts_at_zero():
    import os
    import subprocess
    import sys

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env = {**os.environ, "PYTHONPATH": src, "SYNAPSE_SECRET_KEY": "00" * 32}
    out = subprocess.run(
        [sys.executable, "-c", "import synapse_shield.tokens as t; print(repr(t._last_cleanup_ts))"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.stdout.strip() == "0.0", out.stderr


# --------------------------------------------------------------------------------------------
# core.py — decisions, defaults, metrics
# --------------------------------------------------------------------------------------------


def _token(telemetry=None) -> str:
    return _b64({"challenge": tokens.generate_challenge()["challenge"], "telemetry": telemetry or {}})


def _fake(score, classification="Human", reasons=None, **features):
    def analyze(telemetry, *a, **k):
        return score, classification, list(reasons or ["fake"]), {"features": dict(features), "threat_type": None}

    return analyze


def test_module_constants_and_signature_defaults():
    assert core.MAX_PAYLOAD_SIZE == 262_144
    for fn in (core.evaluate_synapse_request_sync, core.evaluate_synapse_request):
        p = inspect.signature(fn).parameters
        assert p["max_risk_score"].default == 50.0
        assert p["accessibility_mode"].default is False
        assert p["mode"].default == "enforce"
    d = core.SynapseDecision(allowed=True)
    assert (d.status_code, d.error_message, d.classification, d.bot_score) == (200, None, "Human", 0.0)
    assert (d.action, d.challenge_data, d.headers, d.reasons) == ("allow", None, {}, [])
    assert core.SynapseDecision(allowed=True).headers is not d.headers, "mutable defaults must not be shared"


def test_shadow_decision_serialisation():
    d = core.SynapseDecision(allowed=True, shadow_mode=True, action="shadow_block", reasons=["r1"])
    body = d.to_dict()
    assert body["shadow_mode"] is True and body["simulated_action"] == "block" and body["reasons"] == ["r1"]
    assert core.SynapseDecision(allowed=True, shadow_mode=True, action="allow").to_dict()["simulated_action"] == "allow"


@pytest.mark.parametrize("shadow", [False, True])
def test_hard_rejections_report_full_risk_and_correct_status(shadow):
    mode = "shadow" if shadow else "enforce"
    ip = f"198.19.0.{1 + shadow}"
    cases = {
        "missing": dict(token=None),
        "bad_token": dict(token=_b64("[]")),
    }
    for name, kw in cases.items():
        d = core.evaluate_synapse_request_sync(client_ip=ip + "0", user_agent="ua", mode=mode, **kw)
        assert d.bot_score == 100.0 and d.classification == "Bot", name
        assert d.status_code == (200 if shadow else 403), name
        assert d.shadow_mode is shadow and d.allowed is shadow, name
        assert d.headers["X-Synapse-Risk-Score"] == "100.0%"
    storage_mod.get_storage().ban_ip(ip, duration_sec=30)
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token="x", mode=mode)
    assert d.bot_score == 100.0 and d.status_code == (200 if shadow else 403)
    assert d.shadow_mode is shadow
    storage_mod.get_storage().unban_ip(ip)


def test_request_flood_ban_reports_full_risk(monkeypatch):
    monkeypatch.setenv("SYNAPSE_MAX_REQ_10S", "1")
    monkeypatch.setattr(core, "analyze_behavior", _fake(0.0, total_interactive_events=5, mouse_points=5))
    ip = "198.19.1.1"
    core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token())
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token())
    assert d.status_code == 403 and d.bot_score == 100.0 and d.classification == "Bot"
    storage_mod.get_storage().unban_ip(ip)


def test_session_and_telemetry_plumbing(monkeypatch):
    seen = {}
    st = storage_mod.get_storage()

    class Spy:
        def __getattr__(self, name):
            return getattr(st, name)

        def get_session_telemetries(self, session_id, window_sec=None):
            seen["session"] = (session_id, window_sec)
            return []

        def record_and_get_request_count(self, ip, window_sec=None):
            seen["count_window"] = window_sec
            return 1

        def record_session_telemetry(self, session_id, metrics_, max_history=None, window_sec=None):
            seen["record"] = (metrics_, max_history, window_sec)

    def analyze(telemetry, recent, penalized, accessibility, history):
        seen["analyze"] = (penalized, accessibility, history)
        return 0.0, "Human", [], {"features": {"total_interactive_events": 3, "mouse_points": 3, "total_distance": 10.0}}

    monkeypatch.setattr(core, "get_storage", lambda: Spy())
    monkeypatch.setattr(core, "analyze_behavior", analyze)
    d = core.evaluate_synapse_request_sync(client_ip="198.19.2.1", user_agent="ua-x", token=_token())
    assert d.allowed
    assert re.fullmatch(r"ip_198\.19\.2\.1_[0-9a-f]{16}", seen["session"][0])
    assert seen["session"][1] == 300 and seen["count_window"] == 10
    assert seen["analyze"] == (False, False, [])
    metrics_, max_history, window = seen["record"]
    assert (max_history, window) == (10, 300)
    assert metrics_ == {"avg_jerk": 0.0, "straightness": 1.0, "total_distance": 10.0, "submovement_count": 0,
                        "spectral_purity": 0.0}


@pytest.mark.parametrize(
    "features,reasons,challenged",
    [
        ({"key_count": 5, "mouse_points": 5}, None, True),  # total = mouse + keys
        ({"mouse_points": 5, "click_count": 5}, None, True),  # total = mouse + clicks
        ({"touch_event_count": 4}, None, True),
        ({"key_count": 5}, None, True),  # missing mouse_points means 0, not 1
        ({"mouse_points": 3}, None, True),  # 3 desktop mouse points is not the 1..2 bot signature
        ({"mouse_points": 2}, None, False),  # 1..2 desktop mouse points IS
        ({}, None, False),  # no interaction at all
        ({"mouse_points": 9}, ["Session Behavioral Invariance: zero variance"], False),
        ({"mouse_points": 9, "is_stealth_automation": True}, None, False),
        ({"mouse_points": 9}, None, True),
    ],
)
def test_gray_area_challenge_decision_matrix(monkeypatch, features, reasons, challenged):
    monkeypatch.setattr(core, "analyze_behavior", _fake(40.0, reasons=reasons, **features))
    d = core.evaluate_synapse_request_sync(client_ip="198.19.3.1", user_agent="ua", token=_token(), enable_pow=True)
    assert (d.status_code == 429) is challenged


def test_gray_area_upper_edge_and_risk_threshold(monkeypatch):
    base = dict(total_interactive_events=9, mouse_points=9)
    monkeypatch.setattr(core, "analyze_behavior", _fake(55.0, **base))
    d = core.evaluate_synapse_request_sync(client_ip="198.19.3.2", user_agent="ua", token=_token(), enable_pow=True)
    assert d.status_code == 403, "55.0 is outside the 35..<55 gray band: block, don't challenge"
    monkeypatch.setattr(core, "analyze_behavior", _fake(50.0, **base))
    d = core.evaluate_synapse_request_sync(client_ip="198.19.3.3", user_agent="ua", token=_token(), max_risk_score=50.0)
    assert d.status_code == 403, "a score equal to max_risk_score is blocked"
    d = core.evaluate_synapse_request_sync(client_ip="198.19.3.4", user_agent="ua", token=_token())
    assert d.status_code == 403, "default max_risk_score is 50"
    monkeypatch.setattr(core, "analyze_behavior", _fake(49.9, **base))
    d = core.evaluate_synapse_request_sync(client_ip="198.19.3.5", user_agent="ua", token=_token())
    assert d.allowed


@pytest.fixture
def prom(monkeypatch):
    pytest.importorskip("prometheus_client")
    monkeypatch.setattr(core, "METRICS_ENABLED", True)
    for name in ("synapse_requests_total", "synapse_shadow_requests_total", "synapse_replays_detected_total",
                 "synapse_pow_solved_total", "synapse_inference_latency_seconds"):
        monkeypatch.setattr(core, name, getattr(metrics, name))
    return metrics


def _count(counter, **labels):
    return counter.labels(**labels)._value.get() if labels else counter._value.get()


def test_every_decision_path_increments_its_counter(prom, monkeypatch):
    sh = prom.synapse_shadow_requests_total
    rq = prom.synapse_requests_total
    ev = core.evaluate_synapse_request_sync

    def delta(counter, labels, fn):
        before = _count(counter, **labels)
        fn()
        return _count(counter, **labels) - before

    bot = dict(action="block", classification="Bot")
    storage_mod.get_storage().ban_ip("198.19.4.1", duration_sec=30)
    assert delta(sh, bot, lambda: ev(client_ip="198.19.4.1", user_agent="u", token="x", mode="shadow")) == 1
    storage_mod.get_storage().unban_ip("198.19.4.1")
    assert delta(sh, bot, lambda: ev(client_ip="198.19.4.2", user_agent="u", token=None, mode="shadow")) == 1
    assert delta(sh, bot, lambda: ev(client_ip="198.19.4.3", user_agent="u", token=_b64("[]"), mode="shadow")) == 1

    monkeypatch.setattr(core, "analyze_behavior", _fake(90.0, "Bot", total_interactive_events=9, mouse_points=9))
    labels = dict(action="block", classification="Bot")
    assert delta(sh, labels, lambda: ev(client_ip="198.19.4.4", user_agent="u", token=_token(), mode="shadow")) == 1
    assert delta(rq, dict(status="block", classification="Bot"),
                 lambda: ev(client_ip="198.19.4.5", user_agent="u", token=_token())) == 1

    monkeypatch.setattr(core, "analyze_behavior", _fake(5.0, total_interactive_events=9, mouse_points=9))
    assert delta(rq, dict(status="allow", classification="Human"),
                 lambda: ev(client_ip="198.19.4.6", user_agent="u", token=_token())) == 1
    assert delta(sh, dict(action="allow", classification="Human"),
                 lambda: ev(client_ip="198.19.4.7", user_agent="u", token=_token(), mode="shadow")) == 1


def test_replay_counter_counts_replays_only(prom):
    c = prom.synapse_replays_detected_total
    before = _count(c)
    core.evaluate_synapse_request_sync(client_ip="198.19.5.1", user_agent="u", token=_b64("[]"))
    assert _count(c) == before, "a malformed token is not a replay"
    tok = _token()
    core.evaluate_synapse_request_sync(client_ip="198.19.5.2", user_agent="u", token=tok)
    core.evaluate_synapse_request_sync(client_ip="198.19.5.2", user_agent="u", token=tok)
    assert _count(c) == before + 1


def test_nothing_is_counted_when_metrics_are_disabled(prom, monkeypatch):
    monkeypatch.setattr(core, "METRICS_ENABLED", False)
    snapshot = lambda: (  # noqa: E731
        _count(prom.synapse_shadow_requests_total, action="block", classification="Bot"),
        _count(prom.synapse_requests_total, status="allow", classification="Human"),
        _count(prom.synapse_replays_detected_total),
    )
    before = snapshot()
    ev = core.evaluate_synapse_request_sync
    ev(client_ip="198.19.6.1", user_agent="u", token=None, mode="shadow")
    storage_mod.get_storage().ban_ip("198.19.6.2", duration_sec=30)
    ev(client_ip="198.19.6.2", user_agent="u", token="x", mode="shadow")
    storage_mod.get_storage().unban_ip("198.19.6.2")
    tok = _token()
    ev(client_ip="198.19.6.3", user_agent="u", token=tok)
    ev(client_ip="198.19.6.3", user_agent="u", token=tok, mode="shadow")
    monkeypatch.setattr(core, "analyze_behavior", _fake(5.0, total_interactive_events=9, mouse_points=9))
    ev(client_ip="198.19.6.4", user_agent="u", token=_token())
    monkeypatch.setattr(core, "analyze_behavior", _fake(90.0, "Bot", total_interactive_events=9, mouse_points=9))
    ev(client_ip="198.19.6.5", user_agent="u", token=_token(), mode="shadow")
    assert snapshot() == before


# --------------------------------------------------------------------------------------------
# storage.py — SQLite
# --------------------------------------------------------------------------------------------


def test_nonce_expiry_is_in_the_future_so_replays_stay_blocked(sq, frozen):
    assert sq.consume_nonce("n-1") is True
    with sqlite3.connect(sq.db_path) as conn:
        assert conn.execute("SELECT expires_at FROM used_nonces WHERE nonce='n-1'").fetchone()[0] == int(NOW_S) + 120
    sq._last_nonce_cleanup = 0.0
    assert sq.consume_nonce("n-1") is False, "cleanup must not delete a live nonce (replay window)"
    assert sq.consume_nonce("n-2", ttl_sec=7) is True
    with sqlite3.connect(sq.db_path) as conn:
        assert conn.execute("SELECT expires_at FROM used_nonces WHERE nonce='n-2'").fetchone()[0] == int(NOW_S) + 7


@pytest.mark.parametrize("last,runs", [(NOW_S - 30, False), (NOW_S - 59.9, False), (NOW_S - 60, True), (NOW_S - 60.5, True)])
def test_nonce_cleanup_throttle_is_60_seconds(sq, frozen, last, runs):
    with sqlite3.connect(sq.db_path) as conn:
        conn.execute("INSERT INTO used_nonces VALUES ('stale', ?)", (int(NOW_S) - 10,))
    sq._last_nonce_cleanup = last
    sq._cleanup_expired_nonces()
    with sqlite3.connect(sq.db_path) as conn:
        left = conn.execute("SELECT COUNT(*) FROM used_nonces WHERE nonce='stale'").fetchone()[0]
    assert (left == 0) is runs


def test_connection_options(tmp_path, no_rust, monkeypatch):
    seen = []
    real = sqlite3.connect
    monkeypatch.setattr(storage_mod.sqlite3, "connect", lambda *a, **k: seen.append(k) or real(*a, **k))
    b = SQLiteStorageBackend(db_path=str(tmp_path / "c.db"))
    assert seen[0]["timeout"] == 10.0 and seen[0]["check_same_thread"] is False
    conn = b._get_connection()
    box = []
    t = threading.Thread(target=lambda: box.append(conn.execute("SELECT 1").fetchone()))
    t.start()
    t.join()
    assert box == [(1,)], "connections may be closed/used from another thread (GC)"
    b.close()


def test_ip_ban_cache_lifetimes(sq):
    # Each expiry is compared with a clock reading taken right before the action, and the upper
    # tolerance is 0.6 s, so the test stays stable on a loaded machine while still telling
    # 2 s from 3 s and 5 s from 6 s.
    def lifetime(ip, action):
        t0 = time.time()
        action()
        return sq._ip_ban_cache[ip][1] - t0

    life = lifetime("7.0.0.1", lambda: sq.is_ip_banned("7.0.0.1"))
    assert sq._ip_ban_cache["7.0.0.1"][0] is False and 1.5 < life <= 2.6, "negative cache lives 2 s"
    # a ban written by another worker stays invisible until the negative entry expires
    with sqlite3.connect(sq.db_path) as conn:
        conn.execute("INSERT INTO banned_ips VALUES ('7.0.0.1', ?, 't')",
                     ((datetime.now(timezone.utc) + timedelta(seconds=100)).isoformat(),))
    assert sq.is_ip_banned("7.0.0.1") is False
    sq._ip_ban_cache.clear()
    life = lifetime("7.0.0.1", lambda: sq.is_ip_banned("7.0.0.1"))
    assert sq._ip_ban_cache["7.0.0.1"][0] is True and 90 < life <= 101, "positive cache lives for the remaining ban"

    life = lifetime("7.0.0.2", lambda: sq.ban_ip("7.0.0.2", duration_sec=30))
    assert 28 < life <= 31
    with sqlite3.connect(sq.db_path) as conn:
        conn.execute("DELETE FROM banned_ips WHERE ip='7.0.0.2'")
    assert sq.is_ip_banned("7.0.0.2") is True, "served from the positive cache"

    life = lifetime("7.0.0.2", lambda: sq.unban_ip("7.0.0.2"))
    assert sq._ip_ban_cache["7.0.0.2"][0] is False and 4.5 < life <= 5.6

    with sqlite3.connect(sq.db_path) as conn:
        conn.execute("INSERT INTO banned_ips VALUES ('7.0.0.3', ?, 't')",
                     ((datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),))
    life = lifetime("7.0.0.3", lambda: sq.is_ip_banned("7.0.0.3"))
    assert sq._ip_ban_cache["7.0.0.3"][0] is False and 4.5 < life <= 5.6, "expired bans: purged, cached negative 5 s"


def test_ban_ip_default_duration_is_60_seconds(sq):
    sq.ban_ip("7.0.1.1")
    with sqlite3.connect(sq.db_path) as conn:
        until = datetime.fromisoformat(conn.execute("SELECT banned_until FROM banned_ips WHERE ip='7.0.1.1'").fetchone()[0])
    assert 58.5 <= (until - datetime.now(timezone.utc)).total_seconds() <= 60.1


def test_default_windows_are_60_10_and_300_seconds(sq, frozen):
    ip = "7.0.2.1"
    for _ in range(3):
        sq.record_bot_strike(ip, threshold=99)
        sq.record_and_get_request_count(ip)
        sq.record_session_telemetry(ip, {"k": 1})
    frozen["t"] = NOW_S + 60.5
    assert sq.get_bot_strike_count(ip) == 0, "default strike window is 60 s"
    assert sq.record_bot_strike("7.0.2.2") is False
    for _ in range(3):
        sq.record_bot_strike("7.0.2.2")
    frozen["t"] = NOW_S + 121.0
    assert sq.record_bot_strike("7.0.2.2") is False, "old strikes fell out of the default window"
    frozen["t"] = NOW_S + 10.5
    assert sq.record_and_get_request_count(ip) == 1, "default request window is 10 s"
    frozen["t"] = NOW_S + 300.5
    assert sq.get_session_telemetries(ip) == [], "default telemetry window is 300 s"


def test_session_telemetry_keeps_ten_by_default(sq):
    for i in range(14):
        sq.record_session_telemetry("s-def", {"i": i})
    assert [m["i"] for m in sq.get_session_telemetries("s-def")] == list(range(4, 14))
    sq._session_telemetry_l1.clear()
    assert len(sq.get_session_telemetries("s-def")) == 14  # cold read returns all disk rows ...
    assert len(sq._session_telemetry_l1["s-def"]) == 10  # ... but the warmed cache is capped at 10


def test_window_edges_are_inclusive_in_l1(sq_nodb, frozen):
    b = sq_nodb
    b.record_bot_strike("e1", threshold=99, window_sec=60)
    frozen["t"] = NOW_S + 60
    assert b.get_bot_strike_count("e1", window_sec=60) == 1, "a strike exactly window_sec old still counts"
    frozen["t"] = NOW_S
    b.record_bot_strike("e2", threshold=2, window_sec=60)
    frozen["t"] = NOW_S + 60
    assert b.record_bot_strike("e2", threshold=2, window_sec=60) is True

    frozen["t"] = NOW_S
    b.record_and_get_request_count("e3", window_sec=10)
    frozen["t"] = NOW_S + 10
    assert b.record_and_get_request_count("e3", window_sec=10) == 2

    frozen["t"] = NOW_S
    b.record_session_telemetry("e4", {"v": 1}, window_sec=300)
    frozen["t"] = NOW_S + 300
    assert b.get_session_telemetries("e4", window_sec=300) == [{"v": 1}]
    b.record_session_telemetry("e4", {"v": 2}, window_sec=300)
    assert len(b._session_telemetry_l1["e4"]) == 2


def _fill(b, kind, n, ts):
    if kind == "strikes":
        for i in range(n):
            b._ip_strikes_l1[f"old{i}"] = deque([ts])
    elif kind == "history":
        for i in range(n):
            b._ip_history[f"old{i}"] = deque([ts])
    else:
        for i in range(n):
            b._session_telemetry_l1[f"old{i}"] = deque([(ts, {})])


def _touch(b, kind):
    if kind == "strikes":
        b.record_bot_strike("new", threshold=99, window_sec=60)
        return b._ip_strikes_l1
    if kind == "history":
        b.record_and_get_request_count("new", window_sec=10)
        return b._ip_history
    b.record_session_telemetry("new", {}, window_sec=300)
    return b._session_telemetry_l1


WINDOW = {"strikes": 60, "history": 10, "telemetry": 300}


@pytest.mark.parametrize("kind", ["strikes", "history", "telemetry"])
def test_l1_maps_are_purged_only_above_5000_entries(sq, frozen, kind):
    _fill(sq, kind, 5000, NOW_S - WINDOW[kind] - 100)
    m = _touch(sq, kind)
    assert len(m) == 5001, "exactly 5000 entries: no purge yet"


@pytest.mark.parametrize("kind", ["strikes", "history", "telemetry"])
def test_l1_purge_keeps_fresh_and_edge_entries(sq, frozen, kind):
    w = WINDOW[kind]
    _fill(sq, kind, 5001, NOW_S - w - 100)
    empty = deque()
    fresh = deque([NOW_S]) if kind != "telemetry" else deque([(NOW_S, {})])
    edge = deque([NOW_S - w]) if kind != "telemetry" else deque([(NOW_S - w, {})])
    target = {"strikes": sq._ip_strikes_l1, "history": sq._ip_history, "telemetry": sq._session_telemetry_l1}[kind]
    target.update({"empty": empty, "fresh": fresh, "edge": edge})
    m = _touch(sq, kind)
    assert set(m) == {"fresh", "edge", "new"}, sorted(m)[:5]


# --------------------------------------------------------------------------------------------
# storage.py — Rust L1 integration (stubbed native module)
# --------------------------------------------------------------------------------------------


class RustRecorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, a))
            return {"consume_nonce_rs": True, "is_ip_banned_rs": False}.get(name)

        return call


def _exercise(b):
    b.consume_nonce("rec-1")
    b.is_ip_banned("rec-ip")
    b.ban_ip("rec-ip", duration_sec=5)
    b.unban_ip("rec-ip")
    b.clear_all()


def test_rust_l1_is_used_when_active(tmp_path, monkeypatch):
    rec = RustRecorder()
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", True)
    monkeypatch.setattr(storage_mod, "synapse_core_rs", rec)
    b = SQLiteStorageBackend(db_path=str(tmp_path / "r1.db"))
    assert [c[0] for c in rec.calls] == [], "no bans on disk: nothing to hydrate"
    _exercise(b)
    names = [c[0] for c in rec.calls]
    for expected in ("consume_nonce_rs", "is_ip_banned_rs", "ban_ip_rs", "unban_ip_rs", "clear_state_engine_rs"):
        assert expected in names, names
    b.close()


def test_rust_l1_is_not_touched_when_inactive(tmp_path, monkeypatch):
    rec = RustRecorder()
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", False)
    monkeypatch.setattr(storage_mod, "synapse_core_rs", rec)
    b = SQLiteStorageBackend(db_path=str(tmp_path / "r2.db"))
    _exercise(b)
    b.close()
    assert rec.calls == []


def test_disk_ban_is_promoted_to_rust_only_with_whole_seconds_left(tmp_path, monkeypatch):
    rec = RustRecorder()
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", True)
    monkeypatch.setattr(storage_mod, "synapse_core_rs", rec)
    b = SQLiteStorageBackend(db_path=str(tmp_path / "r3.db"))

    def insert(ip, seconds):
        with sqlite3.connect(b.db_path) as conn:
            conn.execute("INSERT INTO banned_ips VALUES (?, ?, 't')",
                         (ip, (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()))

    insert("p1", 1.6)
    assert b.is_ip_banned("p1") is True
    assert ("ban_ip_rs", ("p1", 1)) in rec.calls, "1 whole second left is promoted"
    insert("p2", 0.6)
    assert b.is_ip_banned("p2") is True
    assert not any(c[0] == "ban_ip_rs" and c[1][0] == "p2" for c in rec.calls), "0 whole seconds: nothing to promote"
    b.close()


# --------------------------------------------------------------------------------------------
# storage.py — Redis
# --------------------------------------------------------------------------------------------

fakeredis = pytest.importorskip("fakeredis")


@pytest.fixture
def rb(tmp_path, no_rust):
    fb = SQLiteStorageBackend(db_path=str(tmp_path / "rfb.db"))
    b = RedisStorageBackend("redis://fake", client=fakeredis.FakeRedis(decode_responses=True), fallback=fb)
    yield b
    fb.close()


def test_redis_backend_construction(tmp_path, monkeypatch, no_rust):
    redis = pytest.importorskip("redis")
    captured = {}
    fake = fakeredis.FakeRedis(decode_responses=True)

    def from_url(cls, url, **kw):
        captured.update(url=url, **kw)
        return fake

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(from_url))
    given = SQLiteStorageBackend(db_path=str(tmp_path / "g.db"))
    b = RedisStorageBackend("redis://h:1/0", fallback=given)
    assert b.fallback is given and b.redis_url == "redis://h:1/0" and b.client is fake
    assert captured == {"url": "redis://h:1/0", "decode_responses": True, "socket_timeout": 1.5,
                        "socket_connect_timeout": 1.5, "retry_on_timeout": False}
    default = RedisStorageBackend("redis://x", client=fake)
    assert isinstance(default.fallback, SQLiteStorageBackend)
    given.close()
    default.fallback.close()


def test_redis_unique_member_shape():
    a, b = storage_mod._unique_member(12.5), storage_mod._unique_member(12.5)
    assert a != b and re.fullmatch(r"12\.5:\d+:[0-9a-f]{12}", a)


def test_redis_sliding_windows_use_real_expiry_and_scores(rb, frozen):
    key = "synapse:strikes:r-ip"
    rb.client.zadd(key, {"zero-score": 0})
    assert rb.record_bot_strike("r-ip", threshold=99, window_sec=60) is False
    assert rb.client.zcard(key) == 1, "an entry with score 0 is older than any window and must be removed"
    assert 115 <= rb.client.ttl(key) <= 120, "key TTL is twice the window"

    key = "synapse:req_count:r-ip"
    rb.client.zadd(key, {"zero-score": 0})
    assert rb.record_and_get_request_count("r-ip", window_sec=10) == 1
    assert 15 <= rb.client.ttl(key) <= 20

    rb.client.zadd("synapse:strikes:r2", {"zero-score": 0})
    assert rb.get_bot_strike_count("r2") == 0


def test_redis_defaults_match_sqlite(rb, frozen):
    assert [rb.record_bot_strike("d-ip") for _ in range(4)] == [False, False, False, True]
    assert 55 <= rb.client.ttl("synapse:ban:d-ip") <= 60, "default ban is 60 s"
    assert rb.consume_nonce("n-d") is True
    assert 115 <= rb.client.ttl("synapse:nonce:n-d") <= 120, "default nonce TTL is 120 s"
    rb.record_bot_strike("w-ip", threshold=99)
    frozen["t"] = NOW_S + 60.5
    assert rb.get_bot_strike_count("w-ip") == 0, "default strike window is 60 s"
    rb.record_and_get_request_count("w-ip")
    frozen["t"] = NOW_S + 71.0
    assert rb.record_and_get_request_count("w-ip") == 1, "default request window is 10 s"
    for i in range(12):
        rb.record_session_telemetry("s-d", {"i": i})
    assert len(rb.get_session_telemetries("s-d")) == 10, "default history is 10"
    assert 295 <= rb.client.ttl("synapse:session:s-d") <= 300, "default session TTL is 300 s"


def test_redis_telemetry_window_edge_is_inclusive(rb, frozen):
    rb.client.rpush("synapse:session:edge", json.dumps({"v": 1, "_ts": NOW_S - 300}))
    assert rb.get_session_telemetries("edge", window_sec=300) == [{"v": 1, "_ts": NOW_S - 300}]


def test_get_storage_returns_a_sqlite_singleton_without_redis(monkeypatch):
    monkeypatch.delenv("SYNAPSE_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    storage_mod.set_storage(None)
    try:
        first = storage_mod.get_storage()
        assert isinstance(first, SQLiteStorageBackend) and storage_mod.get_storage() is first
    finally:
        storage_mod.set_storage(None)
