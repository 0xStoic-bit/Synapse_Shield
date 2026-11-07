"""
Second mutation pass (mutmut v2 run, 2026-11-07): response contract, headers, thresholds, abstract base.

Each test pins behaviour that a one-token mutation used to leave undetected.
"""

from __future__ import annotations

import inspect

import pytest

from synapse_shield import core, tokens
from synapse_shield import storage as storage_mod
from synapse_shield.storage import RedisStorageBackend

from test_mutation_gaps import _b64, _fake, _token  # noqa: F401  (shared helpers)


def test_decision_to_dict_wire_contract():
    ch = core.SynapseDecision(
        allowed=False, action="challenge", classification="Human", bot_score=42.0, reasons=["r"],
        challenge_data={"pow_difficulty": 5, "pow_salt": "salt"},
    ).to_dict()
    assert ch == {"status": "challenge_required", "action": "challenge", "classification": "Human",
                  "bot_score": "42.0%", "reasons": ["r"], "pow_difficulty": 5, "pow_salt": "salt"}
    for cd in ({}, None):
        bare = core.SynapseDecision(allowed=False, action="challenge", challenge_data=cd).to_dict()
        assert (bare["pow_difficulty"], bare["pow_salt"]) == (4, "")
    assert core.SynapseDecision(allowed=True, classification="Human", bot_score=3.0).to_dict() == {
        "status": "allowed", "classification": "Human", "bot_score": "3.0%"}
    assert core.SynapseDecision(allowed=False, error_message="no", classification="Bot", bot_score=100.0,
                                reasons=["x"]).to_dict() == {
        "error": "no", "classification": "Bot", "bot_score": "100.0%", "reasons": ["x"]}
    assert core.SynapseDecision(allowed=False).to_dict()["error"] == "Access Denied by Synapse Shield"
    assert core.SynapseDecision(allowed=True).telemetry is None


@pytest.mark.parametrize("shadow", [False, True])
def test_hard_rejection_messages_reasons_and_headers(shadow):
    mode = "shadow" if shadow else "enforce"
    decision = "shadow-block" if shadow else "block"
    ip = f"198.19.6.{1 + shadow}"
    ev = core.evaluate_synapse_request_sync
    miss = ev(client_ip=ip + "0", user_agent="ua", token=None, mode=mode)
    assert miss.reasons == ["MISSING_TOKEN"] and miss.headers["X-Synapse-Decision"] == decision
    if not shadow:
        assert miss.error_message == "[Synapse Shield] Missing token."
    bad = ev(client_ip=ip + "1", user_agent="ua", token=_b64("[]"), mode=mode)
    assert bad.reasons[0].startswith("TOKEN_")
    assert bad.headers == {"X-Synapse-Decision": decision, "X-Synapse-Risk-Score": "100.0%"}
    if not shadow:
        assert bad.error_message.startswith("[Synapse Shield] Token Error: ")
    storage_mod.get_storage().ban_ip(ip, duration_sec=30)
    banned = ev(client_ip=ip, user_agent="ua", token="x", mode=mode)
    storage_mod.get_storage().unban_ip(ip)
    assert banned.reasons == ["IP_BANNED"]
    assert banned.headers == {"X-Synapse-Decision": decision, "X-Synapse-Risk-Score": "100.0%"}
    if not shadow:
        assert banned.error_message == "IP address is banned by Synapse Shield."


def test_flood_block_reason_and_headers(monkeypatch):
    monkeypatch.setenv("SYNAPSE_MAX_REQ_10S", "1")
    monkeypatch.setattr(core, "analyze_behavior", _fake(0.0, total_interactive_events=5, mouse_points=5))
    ip = "198.19.6.50"
    core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token())
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token())
    storage_mod.get_storage().unban_ip(ip)
    assert d.reasons == ["Extreme request frequency (>1 req/10s)"]
    assert d.headers == {"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "100.0%"}


def test_final_decisions_headers_status_and_messages(monkeypatch):
    base = dict(total_interactive_events=9, mouse_points=9)
    ev = core.evaluate_synapse_request_sync
    monkeypatch.setattr(core, "analyze_behavior", _fake(10.0, **base))
    ok = ev(client_ip="198.19.6.60", user_agent="ua", token=_token())
    assert ok.status_code == 200
    assert ok.headers == {"X-Synapse-Decision": "allow", "X-Synapse-Risk-Score": "10.0%"}
    monkeypatch.setattr(core, "analyze_behavior", _fake(80.0, **base))
    blk = ev(client_ip="198.19.6.61", user_agent="ua", token=_token())
    assert blk.error_message == "Access Denied by Synapse Shield"
    assert blk.headers == {"X-Synapse-Decision": "block", "X-Synapse-Risk-Score": "80.0%"}
    sh = ev(client_ip="198.19.6.62", user_agent="ua", token=_token(), mode="shadow")
    assert sh.status_code == 200
    assert sh.headers == {"X-Synapse-Decision": "shadow-block", "X-Synapse-Risk-Score": "80.0%"}


@pytest.mark.parametrize("score,diff", [(35.0, 4), (44.9, 4), (45.0, 5), (54.9, 5)])
def test_pow_difficulty_steps_at_45(monkeypatch, score, diff):
    monkeypatch.setattr(core, "analyze_behavior", _fake(score, total_interactive_events=9, mouse_points=9))
    d = core.evaluate_synapse_request_sync(client_ip="198.19.6.70", user_agent="ua", token=_token(), enable_pow=True)
    assert d.status_code == 429 and d.challenge_data["pow_difficulty"] == diff
    assert d.headers["X-Synapse-Action"] == "challenge" and d.headers["Retry-After"] == "2"
    assert d.headers["X-Synapse-Risk-Score"] == f"{score:.1f}%"


@pytest.mark.parametrize("threat", [None, "STEALTH_AUTOMATION", "SESSION_INVARIANCE_BOT"])
def test_hard_violations_skip_the_pow_challenge(monkeypatch, threat):
    feats = {"mouse_points": 9, "total_interactive_events": 9}
    if threat is None:
        feats = {"mouse_points": 1, "total_interactive_events": 1}

    def analyze(telemetry, *a, **k):
        return 40.0, "Human", ["x"], {"features": feats, "threat_type": threat}

    monkeypatch.setattr(core, "analyze_behavior", analyze)
    d = core.evaluate_synapse_request_sync(client_ip="198.19.6.80", user_agent="ua", token=_token(), enable_pow=True)
    assert d.status_code != 429


def test_session_features_are_forwarded_to_storage(monkeypatch):
    seen = {}

    class Spy(storage_mod.SQLiteStorageBackend):
        def record_session_telemetry(self, session_id, metrics_, max_history=10, window_sec=300):
            seen["m"] = metrics_

    feats = {"avg_jerk": 1.5, "straightness": 0.4, "total_distance": 77.0, "submovement_count": 3,
             "spectral_purity": 0.2, "total_interactive_events": 5, "mouse_points": 5}
    monkeypatch.setattr(core, "get_storage", lambda: Spy(db_path=":memory:"))
    monkeypatch.setattr(core, "analyze_behavior", _fake(1.0, **feats))
    core.evaluate_synapse_request_sync(client_ip="198.19.6.90", user_agent="ua", token=_token())
    assert seen["m"] == {k: feats[k] for k in ("avg_jerk", "straightness", "total_distance",
                                               "submovement_count", "spectral_purity")}


def test_storage_base_class_is_abstract_and_keeps_its_defaults():
    P = storage_mod.StorageBackend
    with pytest.raises(TypeError):
        P()
    for name in ("consume_nonce", "is_ip_banned", "ban_ip", "unban_ip", "record_bot_strike",
                 "record_session_telemetry", "record_and_get_request_count", "get_session_telemetries",
                 "clear_all"):
        assert getattr(P, name).__isabstractmethod__, name
    sig = inspect.signature
    assert sig(P.consume_nonce).parameters["ttl_sec"].default == 120
    assert sig(P.ban_ip).parameters["duration_sec"].default == 60
    assert sig(P.ban_ip).parameters["reason"].default == "4 ardışık bot kararı"
    rs = sig(P.record_bot_strike).parameters
    assert (rs["threshold"].default, rs["window_sec"].default, rs["ban_duration_sec"].default) == (4, 60, 60)
    assert rs["reason"].default == "4 ardışık bot kararı"
    assert sig(P.record_session_telemetry).parameters["max_history"].default == 10
    assert sig(P.record_and_get_request_count).parameters["window_sec"].default == 10
    assert sig(P.get_session_telemetries).parameters["window_sec"].default == 300
    assert sig(RedisStorageBackend.ban_ip).parameters["reason"].default == "4 ardışık bot kararı"


def test_binding_hash_normalisation():
    h = tokens.compute_client_binding_hash("203.0.113.9", "Mozilla/5.0")
    assert h == tokens.compute_client_binding_hash("203.0.113.77", " mozilla/5.0 ")
    assert h != tokens.compute_client_binding_hash("203.0.113.9", "other")
    assert tokens.compute_client_binding_hash("203.0.113.9", None) == tokens.compute_client_binding_hash(
        "203.0.113.9", "")
