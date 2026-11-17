"""Acik #12: the SDK / middleware path (core.evaluate_synapse_request_sync) applies the same short per-device
"+50 penalized" signal as main.py.

Before: core.py passed ``storage.is_ip_banned(ip)`` as the penalty flag. A banned IP already returned 403 at
step 1, so the flag was always False there and a bot that had just been blocked came back with no penalty.
Now a bot verdict records a strike under the IP + User-Agent HMAC key and the next evaluation of that same
device gets +50, while other devices behind the same NAT address do not.

Real engine, real SQLite storage; analyze_behavior is only wrapped (not replaced) to observe the flag.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest

from synapse_shield import adversarial as adv
from synapse_shield import core, tokens
from synapse_shield import storage as storage_mod
from synapse_shield.storage import SQLiteStorageBackend, client_strike_key, set_storage
from test_keyboard_only_access import _human_keyboard_only_session

NAT_IP = "100.64.7.9"
BOT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/130.0.0.0 Safari/537.36"
HUMAN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
PENALTY_REASON = "temporarily penalized"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("SYNAPSE_ENABLE_POW", raising=False)
    monkeypatch.delenv("SYNAPSE_KEYBOARD_ONLY_CHALLENGE", raising=False)
    previous = storage_mod._global_storage
    backend = SQLiteStorageBackend(db_path=str(tmp_path / "core_nat.db"))
    set_storage(backend)
    try:
        yield backend
    finally:
        set_storage(previous)
        backend.close()


@pytest.fixture
def seen(monkeypatch):
    flags: list[bool] = []
    real = core.analyze_behavior

    def spy(telemetry, recent, penalized, accessibility, history, ip_history=None):
        flags.append(penalized)
        return real(telemetry, recent, penalized, accessibility, history, ip_history=ip_history)

    monkeypatch.setattr(core, "analyze_behavior", spy)
    return flags


def _token(telemetry, ip=NAT_IP, ua=None):
    challenge = tokens.generate_challenge(client_ip=ip, user_agent=ua)["challenge"]
    return base64.b64encode(json.dumps({"challenge": challenge, "telemetry": telemetry}).encode()).decode()


def _linear_bot():
    return adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)


def _eval(ua, telemetry, mode="enforce"):
    return core.evaluate_synapse_request_sync(client_ip=NAT_IP, user_agent=ua, token=_token(telemetry, ua=ua), mode=mode)


def test_other_device_behind_nat_is_not_penalized(store, seen):
    """(a) same IP, different UA: a keyboard-only human stays in the gray-area challenge, no +50."""
    assert _eval(BOT_UA, _linear_bot()).action == "block"
    assert store.get_client_strike_count(client_strike_key(NAT_IP, BOT_UA), 60) == 1
    assert store.get_bot_strike_count(NAT_IP, 60) == 1, "IP-level counter still counts per IP"

    d = _eval(HUMAN_UA, _human_keyboard_only_session(7))
    assert seen[-1] is False
    assert d.action == "challenge" and d.status_code == 429, (d.action, d.bot_score, d.reasons)
    assert not any(PENALTY_REASON in r for r in d.reasons)


def test_same_device_bot_repeat_is_penalized(store, seen):
    """(b) same IP + same UA after a bot verdict: +50 applies, the gray-area session becomes a block."""
    assert _eval(BOT_UA, _linear_bot()).action == "block"
    assert seen[-1] is False, "first request has no prior verdict"

    d = _eval(BOT_UA, _human_keyboard_only_session(8))
    assert seen[-1] is True
    assert d.action == "block" and d.status_code == 403
    assert any(PENALTY_REASON in r for r in d.reasons)


def test_invalid_token_records_an_ip_strike_but_no_device_penalty(store, seen):
    """Token failures feed the IP-level ban counter only; the +50 device penalty comes from behaviour alone."""
    key = client_strike_key(NAT_IP, BOT_UA)
    forged = base64.b64encode(json.dumps({"challenge": "abc.1.deadbeef", "telemetry": {}}).encode()).decode()
    d = core.evaluate_synapse_request_sync(client_ip=NAT_IP, user_agent=BOT_UA, token=forged)
    assert d.status_code == 403
    assert store.get_bot_strike_count(NAT_IP, 60) == 1
    assert store.get_client_strike_count(key, 60) == 0


def test_shadow_mode_records_strikes_like_the_ip_counter(store, seen):
    """Shadow mode never blocks, but it records verdicts exactly as the IP-level counter does (existing pattern),
    so switching to enforce does not start from an empty history."""
    d = _eval(BOT_UA, _linear_bot(), mode="shadow")
    assert d.allowed and d.action == "shadow_block"
    assert store.get_bot_strike_count(NAT_IP, 60) == 1
    assert store.get_client_strike_count(client_strike_key(NAT_IP, BOT_UA), 60) == 1
    _eval(BOT_UA, _human_keyboard_only_session(9), mode="shadow")
    assert seen[-1] is True


def test_flask_middleware_end_to_end(store, seen):
    """(c) Through the real Flask request pipeline: the bot's own retry is penalized, its NAT neighbour is not."""
    flask = pytest.importorskip("flask")
    from flask import jsonify

    from synapse_shield.flask import shield_protect_flask

    app = flask.Flask(f"nat_core_{uuid.uuid4().hex}")

    @app.route("/login", methods=["POST"])
    @shield_protect_flask()
    def login():
        return jsonify({"ok": True})

    client = app.test_client()

    def post(ua, telemetry):
        return client.post(
            "/login",
            json={"token": _token(telemetry, ua=ua)},
            headers={"User-Agent": ua},
            environ_base={"REMOTE_ADDR": NAT_IP},
        )

    assert post(BOT_UA, _linear_bot()).status_code == 403
    assert seen[-1] is False

    neighbour = post(HUMAN_UA, _human_keyboard_only_session(7))
    assert seen[-1] is False
    assert neighbour.status_code == 429, neighbour.get_json()

    retry = post(BOT_UA, _human_keyboard_only_session(8))
    assert seen[-1] is True
    assert retry.status_code == 403
