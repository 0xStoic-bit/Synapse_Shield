"""p3g: IP+UA session history poisoning. Every final decision is recorded with ``ok`` (allowed); the history-only
invariance window uses only ``ok`` entries, so bot requests blocked on a shared CGNAT IP + common User-Agent cannot
make the victim's next clean request trip session invariance. Contract tests only (synthetic inputs)."""

from __future__ import annotations

import random

import pytest

from synapse_shield import adversarial as adv
from synapse_shield import core
from synapse_shield.engine import analyze_behavior
from synapse_shield.storage import SQLiteStorageBackend, get_storage
from test_p2bc_invariance_short_trace import _gray_human_like, _hist, _tel, _template, _token, _variant
from test_p3f_pow_cost_ip_shape import _score, app  # noqa: F401  (fixture)

INV = "Session Behavioral Invariance"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("SYNAPSE_ENABLE_POW", "SYNAPSE_KEYBOARD_ONLY_CHALLENGE", "SYNAPSE_SHORT_TRACE_CHALLENGE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SYNAPSE_TRAJECTORY_REPLAY", "0")


def _bot_entry():
    bot = adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)
    return _hist(bot)


def test_engine_history_only_window_ignores_blocked_entries():
    victim = _tel(_gray_human_like())
    poisoned = [dict(_bot_entry(), ok=True) for _ in range(3)]
    # The attack the fix closes: three identical stored entries trip invariance on an unrelated request.
    _, cls, reasons, _ = analyze_behavior(victim, session_history=poisoned)
    assert cls == "Bot" and any(INV in r for r in reasons)
    blocked = [dict(e, ok=False) for e in poisoned]
    score, _, reasons, _ = analyze_behavior(victim, session_history=blocked)
    assert not any(INV in r for r in reasons)
    # Blocked entries must not change the verdict at all: same score as with no history. (The victim sits near
    # the 50 threshold, so asserting "Human" would depend on numeric details of the installed numpy/Rust build.)
    clean_score, _, _, _ = analyze_behavior(victim, session_history=[])
    assert score == pytest.approx(clean_score)


def test_engine_blocked_entries_still_count_when_the_current_request_matches():
    base, rnd = _template(), random.Random(2)
    tels = [_tel(_variant(base, rnd, scale=rnd.uniform(0.8, 1.25))) for _ in range(3)]
    hist = [dict(_hist(tels[0]), ok=False), dict(_hist(tels[1]), ok=False)]
    _, cls, reasons, _ = analyze_behavior(tels[2], session_history=hist)
    assert cls == "Bot" and any(INV in r for r in reasons)


def test_core_poisoned_session_does_not_block_victim():
    ip, ua = "198.18.63.1", "Mozilla/5.0 common"
    sid = f"ip_{ip}_{core.hashlib.sha256(ua.encode()).hexdigest()[:16]}"
    st = get_storage()
    for _ in range(3):  # attacker requests from the same IP+UA, recorded as blocked
        core.record_session_history(st, sid, {"features": {"mouse_points": 50, **_bot_entry()}}, allowed=False)
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent=ua, token=_token(_tel(_gray_human_like())))
    assert d.action == "allow" and not any(INV in r for r in d.reasons)
    assert [h["ok"] for h in st.get_session_telemetries(sid, 300)][-1] is True


def test_core_records_blocked_decisions_as_not_ok():
    ip, ua = "198.18.63.2", "ua-bot"
    bot = adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent=ua, token=_token(bot))
    assert d.action == "block"
    sid = f"ip_{ip}_{core.hashlib.sha256(ua.encode()).hexdigest()[:16]}"
    assert [h["ok"] for h in get_storage().get_session_telemetries(sid, 300)] == [False]


def test_core_repeating_template_bot_still_blocked_on_third_request():
    base, rnd = _gray_human_like(), random.Random(4)
    ip, ua = "198.18.63.3", "ua-repeat"
    actions = []
    for _ in range(4):
        tel = _tel(_variant(base, rnd, scale=rnd.uniform(0.85, 1.2), noise=0.0))
        actions.append(core.evaluate_synapse_request_sync(client_ip=ip, user_agent=ua, token=_token(tel)))
    assert [a.action for a in actions] == ["allow", "allow", "block", "block"]
    assert any(INV in r for r in actions[2].reasons)


def test_main_records_blocked_decision_as_not_ok(app):  # noqa: F811
    client, backend = app
    assert isinstance(backend, SQLiteStorageBackend)
    bot = adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)
    assert _score(client, "ua-bot", bot)["decision"] == "block"
    sid = f"ip_100.64.9.9_{core.hashlib.sha256(b'ua-bot').hexdigest()[:16]}"
    assert [h["ok"] for h in backend.get_session_telemetries(sid, 300)] == [False]
