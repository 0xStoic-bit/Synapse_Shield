"""Strike policy (main.py and core.py):

1. Token-level failures (replay, forged, garbage) feed only the IP-level 4-strike ban counter; they never give
   the device (IP + User-Agent) the 60 s +50 penalty. A double submit / SDK retry of the same token is rejected
   as a replay, but the same device's next clean request is judged without a penalty.
2. A behavioural Bot verdict always gives the device the +50 penalty, but feeds the IP ban counter only when it
   is a hard violation or scores >= core.IP_STRIKE_MIN_SCORE (85), so borderline wrong verdicts on humans
   behind one CGNAT address cannot lock the whole address out.

Real engine and real SQLite storage. The only substitution is in the borderline test, where analyze_behavior
is wrapped to force a 70-point Bot verdict: no stable real telemetry sits in 50..85 across engine updates,
and the test is about the strike plumbing, not the score.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from synapse_shield import adversarial as adv
from synapse_shield import core, tokens
from synapse_shield import main as main_mod
from synapse_shield import storage as storage_mod
from synapse_shield.storage import SQLiteStorageBackend, client_strike_key, set_storage
from test_keyboard_only_access import _human_keyboard_only_session

IP = "100.64.9.21"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
PENALTY_REASON = "temporarily penalized"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("SYNAPSE_ENABLE_POW", raising=False)
    monkeypatch.delenv("SYNAPSE_KEYBOARD_ONLY_CHALLENGE", raising=False)
    previous = storage_mod._global_storage
    backend = SQLiteStorageBackend(db_path=str(tmp_path / "strike_policy.db"))
    set_storage(backend)
    main_mod._challenge_limiter.cache.clear()
    try:
        yield backend
    finally:
        set_storage(previous)
        main_mod._challenge_limiter.cache.clear()
        backend.close()


def _spy(monkeypatch, module):
    seen: list[bool] = []
    real = module.analyze_behavior

    def spy(telemetry, recent, penalized, accessibility, history, ip_history=None):
        seen.append(penalized)
        return real(telemetry, recent, penalized, accessibility, history, ip_history=ip_history)

    monkeypatch.setattr(module, "analyze_behavior", spy)
    return seen


def _core_token(telemetry):
    challenge = tokens.generate_challenge(client_ip=IP, user_agent=UA)["challenge"]
    return base64.b64encode(json.dumps({"challenge": challenge, "telemetry": telemetry}).encode()).decode()


def _linear_bot():
    return adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)


# ------------------------------------------------------------------------------------------------
# 1. Double submit / replay: rejected, IP strike, no device penalty
# ------------------------------------------------------------------------------------------------


def test_core_double_submit_is_rejected_but_next_clean_request_is_not_penalized(store, monkeypatch):
    seen = _spy(monkeypatch, core)
    key = client_strike_key(IP, UA)
    tok = _core_token(_human_keyboard_only_session(7))

    first = core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=tok)
    assert first.action == "challenge", (first.action, first.reasons)
    second = core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=tok)
    assert second.status_code == 403 and second.action == "block"
    assert any("TOKEN_" in r for r in second.reasons)
    assert store.get_bot_strike_count(IP, 60) == 1, "token failure still feeds the IP ban counter"
    assert store.get_client_strike_count(key, 60) == 0, "but never the device penalty"

    clean = core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=_core_token(_human_keyboard_only_session(8)))
    assert seen[-1] is False
    assert clean.action == "challenge" and clean.status_code == 429
    assert not any(PENALTY_REASON in r for r in clean.reasons)


def test_main_double_submit_is_rejected_but_next_clean_request_is_not_penalized(store, monkeypatch):
    seen = _spy(monkeypatch, main_mod)
    client = TestClient(main_mod.app, client=(IP, 50000))
    h = {"User-Agent": UA}

    def token(tel):
        challenge = client.get("/api/challenge", headers=h).json()["challenge"]
        env = {"challenge": challenge, "telemetry": tel, "created_at": int(time.time() * 1000)}
        return base64.b64encode(json.dumps(env).encode()).decode()

    tok = token(_human_keyboard_only_session(7))
    assert client.post("/api/score", json={"token": tok}, headers=h).json()["decision"] == "challenge"
    replay = client.post("/api/score", json={"token": tok}, headers=h).json()
    assert replay["decision"] == "block" and replay["threat_type"] == "REPLAY_ATTACK"
    assert store.get_bot_strike_count(IP, 60) == 1
    assert store.get_client_strike_count(client_strike_key(IP, UA), 60) == 0

    garbage = client.post("/api/score", json={"token": "garbage"}, headers=h).json()
    assert garbage["decision"] == "block"
    assert store.get_client_strike_count(client_strike_key(IP, UA), 60) == 0

    clean = client.post("/api/score", json={"token": token(_human_keyboard_only_session(8))}, headers=h).json()
    assert seen[-1] is False
    assert clean["decision"] == "challenge", clean


def test_repeated_token_failures_still_ban_the_ip(store):
    """Attacker side is unchanged: 4 forged tokens in 60 s from one IP -> IP ban."""
    forged = base64.b64encode(json.dumps({"challenge": "abc.1.deadbeef", "telemetry": {}}).encode()).decode()
    for _ in range(4):
        assert core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=forged).status_code == 403
    assert store.is_ip_banned(IP) is True
    d = core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=_core_token(_human_keyboard_only_session(3)))
    assert d.reasons == ["IP_BANNED"]


# ------------------------------------------------------------------------------------------------
# 2. Which behavioural verdicts feed the IP ban counter
# ------------------------------------------------------------------------------------------------


def test_counts_as_ip_strike_rule():
    assert core.IP_STRIKE_MIN_SCORE == 85.0
    assert core.counts_as_ip_strike(85.0, False) is True
    assert core.counts_as_ip_strike(84.9, False) is False
    assert core.counts_as_ip_strike(51.0, True) is True


def test_scripted_bot_verdict_feeds_ip_counter_and_device_penalty(store):
    d = core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=_core_token(_linear_bot()))
    assert d.action == "block" and d.bot_score >= core.IP_STRIKE_MIN_SCORE
    assert store.get_bot_strike_count(IP, 60) == 1
    assert store.get_client_strike_count(client_strike_key(IP, UA), 60) == 1


@pytest.mark.parametrize("path", ["core", "main"])
def test_borderline_bot_verdict_blocks_and_penalizes_device_but_no_ip_strike(store, monkeypatch, path):
    module = core if path == "core" else main_mod
    real = module.analyze_behavior

    def borderline(telemetry, recent, penalized, accessibility, history, ip_history=None):
        _s, _c, reasons, details = real(telemetry, recent, penalized, accessibility, history)
        return 70.0, "Bot", reasons, details

    monkeypatch.setattr(module, "analyze_behavior", borderline)
    tel = adv.generate_bezier_telemetry(start=(100.0, 120.0), end=(640.0, 480.0), steps=50, duration_ms=1300.0)
    if path == "core":
        d = core.evaluate_synapse_request_sync(client_ip=IP, user_agent=UA, token=_core_token(tel))
        assert d.action == "block" and d.status_code == 403
    else:
        client = TestClient(main_mod.app, client=(IP, 50000))
        h = {"User-Agent": UA}
        challenge = client.get("/api/challenge", headers=h).json()["challenge"]
        env = {"challenge": challenge, "telemetry": tel, "created_at": int(time.time() * 1000)}
        tok = base64.b64encode(json.dumps(env).encode()).decode()
        assert client.post("/api/score", json={"token": tok}, headers=h).json()["decision"] == "block"
    assert store.get_bot_strike_count(IP, 60) == 0, "borderline verdict must not feed the shared IP counter"
    assert store.get_client_strike_count(client_strike_key(IP, UA), 60) == 1, "but the device is penalized"
