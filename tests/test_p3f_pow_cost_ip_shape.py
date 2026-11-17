"""p3f: insufficient-evidence PoW cost, IP-only shape history poisoning, IP-only invariance strike policy and the
hard cap of the process-local fallback stores. Contract tests only (synthetic inputs, no metric claims)."""

from __future__ import annotations

import base64
import json
import random
import time

import pytest
from fastapi.testclient import TestClient

from synapse_shield import core
from synapse_shield import main as main_mod
from synapse_shield import storage as storage_mod
from synapse_shield.storage import SQLiteStorageBackend, StorageBackend, set_storage
from test_keyboard_only_access import _human_keyboard_only_session, _solve_pow
from test_p2bc_invariance_short_trace import (
    SHAPE_REASON,
    _gray_human_like,
    _short_humanized_tel,
    _tel,
    _token,
    _variant,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("SYNAPSE_ENABLE_POW", "SYNAPSE_KEYBOARD_ONLY_CHALLENGE", "SYNAPSE_SHORT_TRACE_CHALLENGE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SYNAPSE_TRAJECTORY_REPLAY", "0")


# ---------------- 1. insufficient-evidence PoW: difficulty 5, discount 10 ----------------
def test_helpers():
    assert core.pow_challenge_difficulty(36.0, True) == 5
    assert core.pow_challenge_difficulty(36.0, False) == 4 and core.pow_challenge_difficulty(46.0, False) == 5
    assert core.pow_solved_discount(True) == 10.0 and core.pow_solved_discount(False) == 20.0


@pytest.mark.parametrize("tel,ip", [(_short_humanized_tel(), "198.18.60.1"),
                                    (_human_keyboard_only_session(3), "198.18.60.2")])
def test_forced_challenge_is_difficulty_5_and_solver_passes_with_reduced_discount(tel, ip):
    first = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token(tel), enable_pow=False)
    assert first.action == "challenge" and first.challenge_data["pow_difficulty"] == 5
    salt = first.challenge_data["pow_salt"]
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token(tel), enable_pow=False,
                                           pow_nonce=_solve_pow(salt, 5), pow_salt=salt)
    assert d.action == "allow" and d.allowed
    assert d.bot_score == pytest.approx(first.bot_score - 10.0)


def test_ordinary_gray_area_keeps_adaptive_difficulty_and_20_point_discount(monkeypatch):
    def analyze(telemetry, *a, **k):
        f = {"mouse_points": 60, "key_count": 0, "total_interactive_events": 61, "touch_supported": False}
        return 40.0, "Human", [], {"features": f, "short_trace_gated": False}

    monkeypatch.setattr(core, "analyze_behavior", analyze)
    tel = _tel(_gray_human_like())
    first = core.evaluate_synapse_request_sync(client_ip="198.18.60.3", user_agent="ua", token=_token(tel),
                                               enable_pow=True)
    assert first.action == "challenge" and first.challenge_data["pow_difficulty"] == 4
    salt = first.challenge_data["pow_salt"]
    d = core.evaluate_synapse_request_sync(client_ip="198.18.60.3", user_agent="ua", token=_token(tel),
                                           enable_pow=True, pow_nonce=_solve_pow(salt, 4), pow_salt=salt)
    assert d.action == "allow" and d.bot_score == pytest.approx(20.0)


# ---------------- main.py parity ----------------
@pytest.fixture
def app(tmp_path):
    backend = SQLiteStorageBackend(db_path=str(tmp_path / "p3f.db"))
    previous = storage_mod._global_storage
    set_storage(backend)
    main_mod._challenge_limiter.cache.clear()
    try:
        yield TestClient(main_mod.app, client=("100.64.9.9", 50000)), backend
    finally:
        set_storage(previous)
        main_mod._challenge_limiter.cache.clear()
        backend.close()


def _score(client, ua, telemetry, **extra):
    h = {"User-Agent": ua}
    challenge = client.get("/api/challenge", headers=h).json()["challenge"]
    env = {"challenge": challenge, "telemetry": telemetry, "created_at": int(time.time() * 1000)}
    token = base64.b64encode(json.dumps(env).encode()).decode()
    return client.post("/api/score", json={"token": token, **extra}, headers=h).json()


def test_main_short_trace_challenge_difficulty_5_and_discount_10(app):
    client, _ = app
    tel = _short_humanized_tel()
    first = _score(client, "ua-main", tel)
    assert first["decision"] == "challenge" and first["pow_difficulty"] == 5
    salt = first["pow_salt"]
    d = _score(client, "ua-main", tel, pow_nonce=_solve_pow(salt, 5), pow_salt=salt)
    assert d["decision"] == "allow"
    assert d["bot_score"] == pytest.approx(core.analyze_behavior(tel)[0] - 10.0)


# ---------------- 2. IP-only shape history is written only on allow ----------------
def test_core_does_not_record_ip_shape_history_for_blocked_or_challenged(monkeypatch):
    calls = []
    monkeypatch.setattr(core, "record_ip_shape_history", lambda st, sid, det: calls.append(sid))
    from synapse_shield import adversarial as adv

    bot = adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)
    d = core.evaluate_synapse_request_sync(client_ip="198.18.61.1", user_agent="ua", token=_token(bot))
    assert d.action == "block" and calls == []
    d = core.evaluate_synapse_request_sync(client_ip="198.18.61.2", user_agent="ua",
                                           token=_token(_short_humanized_tel()), enable_pow=False)
    assert d.action == "challenge" and calls == []
    d = core.evaluate_synapse_request_sync(client_ip="198.18.61.3", user_agent="ua",
                                           token=_token(_tel(_gray_human_like())))
    assert d.action == "allow" and calls == [core.ip_shape_session_id("198.18.61.3")]


def test_main_does_not_record_ip_shape_history_for_blocked(app):
    from synapse_shield import adversarial as adv

    client, backend = app
    bot = adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)
    assert _score(client, "ua-bot", bot)["decision"] == "block"
    assert backend.get_session_telemetries(core.ip_shape_session_id("100.64.9.9"), 300) == []


# ---------------- 3. IP-only invariance blocks but is not an IP strike ----------------
def test_invariance_scopes():
    ip_r = f"Session Behavioral Invariance: {core.IP_SHAPE_INVARIANCE_MARKER} (Hamming 1, 2 <= 6)."
    ses_r = "Session Behavioral Invariance: Same normalized trajectory shape repeated across session requests (x)."
    assert core.invariance_scopes([ip_r], "SESSION_INVARIANCE_BOT") == (False, True)
    assert core.invariance_scopes([ses_r]) == (True, False)
    assert core.invariance_scopes([ip_r, ses_r]) == (True, True)
    assert core.invariance_scopes([], "SESSION_INVARIANCE_BOT") == (True, False)


@pytest.mark.parametrize("scope,score,cls,strike", [
    ("IP", 75.0, "Bot", False),     # IP-only match: block, no IP strike
    ("IP", 40.0, "Human", False),   # IP-only match on a gray score: still blocked, never challenged
    ("session", 75.0, "Bot", True),  # IP+UA match stays a hard violation -> IP strike
])
def test_shape_match_scope_strike_policy(monkeypatch, scope, score, cls, strike):
    reason = (f"Session Behavioral Invariance: Same normalized trajectory shape repeated across {scope} requests "
              "(Hamming 1, 2 <= 6; scaled/translated/jittered template replay).")

    def analyze(telemetry, *a, **k):
        f = {"mouse_points": 60, "key_count": 0, "total_interactive_events": 61, "touch_supported": False}
        return score, cls, [reason], {"features": f, "threat_type": "SESSION_INVARIANCE_BOT"}

    monkeypatch.setattr(core, "analyze_behavior", analyze)
    strikes = []
    real = storage_mod.SQLiteStorageBackend.record_bot_strike
    monkeypatch.setattr(storage_mod.SQLiteStorageBackend, "record_bot_strike",
                        lambda self, ip, *a, **k: (strikes.append(ip), real(self, ip, *a, **k))[1])
    ip = f"198.18.62.{int(score)}"
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token(_tel(_gray_human_like())),
                                           enable_pow=True)
    assert d.action == "block" and d.classification == "Bot"
    assert (ip in strikes) is strike


def test_core_still_catches_ua_rotation_on_third_request():
    base, rnd = _gray_human_like(), random.Random(4)
    ip = "198.18.62.3"
    actions = []
    for i in range(3):
        tel = _tel(_variant(base, rnd, scale=rnd.uniform(0.85, 1.2), noise=0.0))
        actions.append(core.evaluate_synapse_request_sync(client_ip=ip, user_agent=f"ua-rot-{i}", token=_token(tel)))
    assert [a.action for a in actions] == ["allow", "allow", "block"]
    assert any(SHAPE_REASON in r and "IP requests" in r for r in actions[2].reasons)


# ---------------- 4. process-local store hard cap ----------------
def _mem():
    cls = type("_MemImpl", (StorageBackend,), {m: (lambda *a, **k: None) for m in StorageBackend.__abstractmethods__})
    return cls()


def test_trajectory_fp_store_is_capped_within_ttl(monkeypatch):
    monkeypatch.setattr(storage_mod, "MEMORY_STORE_MAX_KEYS", 50)
    s = _mem()
    for i in range(200):
        assert s.consume_trajectory_fp(f"fp{i}", ttl_sec=3600) is True
    store = s.__dict__["_trajectory_fps_default"][1]
    assert len(store) == 50 and "fp199" in store and "fp0" not in store
    assert s.consume_trajectory_fp("fp199", ttl_sec=3600) is False  # most recent still remembered


def test_client_strike_store_is_capped_within_window(monkeypatch):
    monkeypatch.setattr(storage_mod, "MEMORY_STORE_MAX_KEYS", 50)
    s = _mem()
    for i in range(200):
        s.record_client_strike(f"k{i}", window_sec=60)
    store = s.__dict__["_client_strikes_default"][1]
    assert len(store) == 50
    assert s.get_client_strike_count("k199") == 1 and s.get_client_strike_count("k0") == 0
