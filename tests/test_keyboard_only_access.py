"""Keyboard-only users (screen reader, switch device, Tab navigation) must not be hard-blocked just because
there is no mouse telemetry; they land in the existing gray-area PoW range (35-55) instead. Keyboard-only
automation must not slip through as a clean allow: auto-typers are still blocked by the keystroke rules and
jittered ones are at least challenged.

Human sessions follow the login-form flow of the human simulator (Tab to the form, type username, Tab, type
password, Enter) with per-person timing drawn from the CMU Keystroke Dynamics between-subject spread
(hold median ~86 ms, within-person CV 0.08-0.6, rollover ~11 %) and the Aalto free-text speed
(5.1 +- 2.1 keys/s). These are synthetic sessions, not recorded humans.
"""

import base64
import hashlib
import itertools
import json
import math
import random

import pytest

from synapse_shield import core, tokens
from synapse_shield.engine import analyze_behavior

BROWSER = {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
           "touch_supported": False, "max_touch_points": 0, "languages": "tr-TR,tr,en-US,en",
           "is_plugin_array_fake": False, "has_webdriver_own_prop": False, "is_webgl_hooked": False,
           "is_canvas_hooked": False}
NO_MOTION_REASON = "without mouse movement telemetry"
KEYBOARD_ONLY_REASON = "keyboard-only, routed to gray-area challenge"


def _press(ev, key, t, hold, is_freq=False):
    ev.append({"type": "down", "key": key, "t": round(t), "is_freq_digraph": is_freq})
    ev.append({"type": "up", "key": key, "t": round(t + hold), "down": round(t), "up": round(t + hold),
               "duration_ms": round(hold), "is_freq_digraph": is_freq})


def _human_keyboard_only_session(seed):
    rnd = random.Random(seed)
    hold_ms = min(250.0, max(30.0, rnd.gauss(87.6, 18.8)))
    hold_cv = rnd.uniform(0.08, 0.6)
    iki_ms = 1000.0 / max(1.2, rnd.gauss(5.1, 2.1))
    iki_cv = rnd.uniform(0.2, 0.9)
    rollover = rnd.uniform(0.0, 0.3)

    def hold():
        return hold_ms * math.exp(rnd.gauss(0.0, hold_cv))

    ev, t = [], rnd.uniform(800, 4000)
    for _ in range(rnd.randint(1, 3)):
        h = hold()
        _press(ev, "tab", t, h)
        t += h + rnd.uniform(150, 600)
    for field in ("user", "pass"):
        for _ in range(rnd.randint(6, 13)):
            h = hold()
            _press(ev, "masked", t, h)
            iki = iki_ms * math.exp(rnd.gauss(0.0, iki_cv))
            if rnd.random() < 0.06:
                iki += rnd.uniform(300, 1500)  # thinking / word pause
            if rnd.random() < rollover:
                iki = min(iki, h * rnd.uniform(0.5, 0.95))
            t += max(25.0, iki)
        h = hold()
        _press(ev, "tab" if field == "user" else "enter", t, h)
        t += h + rnd.uniform(150, 600)
    ev.sort(key=lambda e: e["t"])
    return {"mouse_movements": [], "clicks": [], "keystrokes": ev[-50:], "scrolls": [], "browser": dict(BROWSER)}


def _bot_keyboard_only_session(seed, flight, dwell):
    rnd = random.Random(seed)
    ev, t = [], rnd.uniform(800, 4000)
    for key in ["tab"] + ["masked"] * 10 + ["tab"] + ["masked"] * 10 + ["enter"]:
        d = dwell(rnd)
        _press(ev, key, t, d)
        t += d + flight(rnd)
    return {"mouse_movements": [], "clicks": [], "keystrokes": ev[-50:], "scrolls": [], "browser": dict(BROWSER)}


def _decide(telemetry, ip, enable_pow):
    env = {"challenge": tokens.generate_challenge()["challenge"], "telemetry": telemetry}
    token = base64.b64encode(json.dumps(env).encode()).decode()
    return core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=token, enable_pow=enable_pow)


def test_keyboard_only_humans_score_in_gray_area_not_block():
    results = [analyze_behavior(_human_keyboard_only_session(seed)) for seed in range(200)]
    gray = [s for s, c, reasons, _ in results if c == "Human" and any(KEYBOARD_ONLY_REASON in r for r in reasons)]
    # Before the fix every one of these sessions scored >= 50 from the missing-mouse rule alone.
    assert len(gray) / len(results) >= 0.90, len(gray)
    assert all(35.0 <= s < 50.0 for s in gray), sorted(set(gray))


def test_keyboard_only_human_gets_pow_challenge_not_403_when_pow_enabled():
    d = _decide(_human_keyboard_only_session(3), "198.19.7.1", enable_pow=True)
    assert d.status_code == 429 and d.action == "challenge", (d.status_code, d.bot_score, d.reasons)


@pytest.mark.parametrize(
    "name,flight,dwell",
    [
        ("constant_interval", lambda r: 100.0, lambda r: 50.0),
        ("superhuman", lambda r: 15.0, lambda r: 10.0),
        ("puppeteer_delay0", lambda r: r.uniform(0, 3), lambda r: r.uniform(0, 2)),
    ],
)
def test_keyboard_only_autotypers_are_still_bots(name, flight, dwell):
    for seed in range(20):
        score, classification, reasons, _ = analyze_behavior(_bot_keyboard_only_session(seed, flight, dwell))
        assert classification == "Bot" and score >= 55.0, (name, seed, score, reasons)


def test_jittered_keyboard_only_bot_is_not_a_clean_allow():
    """A uniform-jitter typer that evades the keystroke rules still has to pass the gray-area challenge."""
    tel = _bot_keyboard_only_session(1, lambda r: r.uniform(80, 200), lambda r: r.uniform(60, 120))
    score, _, _, _ = analyze_behavior(tel)
    assert score >= 35.0
    d = _decide(tel, "198.19.7.2", enable_pow=True)
    assert not d.allowed


def test_click_without_mouse_or_keyboard_evidence_is_still_penalized():
    """element.click() macro: a click with no pointer motion and no keystrokes keeps the +50."""
    tel = {"mouse_movements": [], "clicks": [{"x": 960, "y": 600, "t": 2400}], "keystrokes": [], "scrolls": [],
           "browser": dict(BROWSER)}
    score, classification, reasons, _ = analyze_behavior(tel)
    assert classification == "Bot" and score >= 50.0
    assert any(NO_MOTION_REASON in r and KEYBOARD_ONLY_REASON not in r for r in reasons)


def _token_for(telemetry):
    env = {"challenge": tokens.generate_challenge()["challenge"], "telemetry": telemetry}
    return base64.b64encode(json.dumps(env).encode()).decode()


def _solve_pow(salt, difficulty):
    prefix = "0" * difficulty
    for n in itertools.count():
        if hashlib.sha256(f"{salt}{n}".encode()).hexdigest().startswith(prefix):
            return str(n)
    raise AssertionError  # pragma: no cover


JITTER_BOT = (lambda r: r.uniform(80, 200), lambda r: r.uniform(60, 120))


@pytest.fixture
def default_keyboard_only_challenge(monkeypatch):
    monkeypatch.delenv("SYNAPSE_KEYBOARD_ONLY_CHALLENGE", raising=False)
    monkeypatch.delenv("SYNAPSE_ENABLE_POW", raising=False)


@pytest.mark.parametrize(
    "tel",
    [_human_keyboard_only_session(3), _bot_keyboard_only_session(1, *JITTER_BOT)],
    ids=["human", "jittered_bot"],
)
def test_keyboard_only_gray_area_is_challenged_even_with_pow_disabled(default_keyboard_only_challenge, tel):
    score, classification, _, _ = analyze_behavior(tel)
    assert classification == "Human" and 35.0 <= score < 50.0, (score, classification)
    d = _decide(tel, "198.19.8.1", enable_pow=False)
    assert d.action == "challenge" and d.status_code == 429 and not d.allowed, (d.action, d.bot_score)
    body = d.to_dict()
    assert body["status"] == "challenge_required" and body["pow_salt"]
    assert tokens.extract_pow_difficulty(body["pow_salt"]) == body["pow_difficulty"]


def test_keyboard_only_session_with_solved_pow_is_allowed(default_keyboard_only_challenge):
    ip, tel = "198.19.8.2", _human_keyboard_only_session(3)
    first = _decide(tel, ip, enable_pow=False)
    assert first.action == "challenge"
    salt = first.challenge_data["pow_salt"]
    nonce = _solve_pow(salt, first.challenge_data["pow_difficulty"])
    # The behaviour token is single-use, so the retry carries a fresh one (as the SDK does).
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token_for(tel), enable_pow=False,
                                           pow_nonce=nonce, pow_salt=salt)
    assert d.allowed and d.action == "allow" and d.status_code == 200
    assert any("PoW Challenge successfully solved" in r for r in d.reasons)


@pytest.mark.parametrize("how", ["argument", "environment"])
def test_keyboard_only_challenge_can_be_turned_off(monkeypatch, how):
    monkeypatch.delenv("SYNAPSE_ENABLE_POW", raising=False)
    kwargs = {}
    if how == "argument":
        kwargs["keyboard_only_challenge"] = False
    else:
        monkeypatch.setenv("SYNAPSE_KEYBOARD_ONLY_CHALLENGE", "0")
    tel = _human_keyboard_only_session(3)
    d = core.evaluate_synapse_request_sync(client_ip="198.19.8.3", user_agent="ua", token=_token_for(tel),
                                           enable_pow=False, **kwargs)
    assert d.allowed and d.action == "allow", (d.action, d.bot_score)


def _routed_analysis(score, classification="Human", **features):
    """Core routing only: the engine verdict is fixed so the gray-area branch is exercised at an exact score."""
    feat = {"total_interactive_events": 20, "mouse_points": 20, "key_count": 20, **features}

    def analyze(telemetry, *a, **k):
        return score, classification, ["routed"], {"features": feat, "threat_type": None}

    return analyze


def test_mouse_gray_area_without_pow_is_unchanged(default_keyboard_only_challenge, monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior", _routed_analysis(42.0))
    d = _decide(_human_keyboard_only_session(3), "198.19.8.4", enable_pow=False)
    assert d.allowed and d.action == "allow"


@pytest.mark.parametrize("score,classification", [(52.0, "Bot"), (45.0, "Bot")])
def test_keyboard_only_challenge_never_turns_a_block_into_a_challenge(default_keyboard_only_challenge, monkeypatch,
                                                                    score, classification):
    monkeypatch.setattr(core, "analyze_behavior", _routed_analysis(score, classification, mouse_points=0))
    d = _decide(_human_keyboard_only_session(3), "198.19.8.5", enable_pow=False)
    assert d.action == "block" and d.status_code == 403


def test_keyboard_only_challenge_is_not_issued_in_shadow_mode(default_keyboard_only_challenge):
    tel = _human_keyboard_only_session(3)
    d = core.evaluate_synapse_request_sync(client_ip="198.19.8.6", user_agent="ua", token=_token_for(tel),
                                           enable_pow=False, mode="shadow")
    assert d.allowed and d.action == "allow" and d.shadow_mode and d.status_code == 200
    assert d.cohort is not None and d.cohort["input"] == "keyboard"


def test_flask_adapter_challenges_keyboard_only_then_accepts_solved_pow(default_keyboard_only_challenge):
    from flask import Flask

    from synapse_shield.flask import shield_protect_flask

    app = Flask(__name__)

    @app.route("/api/login", methods=["POST"])
    @shield_protect_flask(max_risk_score=50.0)  # enable_pow defaults to False
    def login():
        return "OK"

    client = app.test_client()
    tel = _human_keyboard_only_session(5)
    res = client.post("/api/login", json={"token": _token_for(tel)})
    assert res.status_code == 429 and res.json["status"] == "challenge_required", res.json
    salt, diff = res.json["pow_salt"], res.json["pow_difficulty"]
    nonce = _solve_pow(salt, diff)
    res = client.post("/api/login", json={"token": _token_for(tel)},
                      headers={"X-Synapse-PoW-Nonce": nonce, "X-Synapse-PoW-Salt": salt})
    assert res.status_code == 200 and res.data == b"OK"


def test_click_with_too_few_keys_is_still_penalized():
    """1-2 keys are below the keystroke rules' minimum (key_count >= 3), so they are not keyboard evidence."""
    keys = []
    _press(keys, "enter", 2000, 80)
    tel = {"mouse_movements": [], "clicks": [{"x": 0, "y": 0, "t": 2100}], "keystrokes": keys, "scrolls": [],
           "browser": dict(BROWSER)}
    score, classification, reasons, _ = analyze_behavior(tel)
    assert classification == "Bot" and score >= 50.0
    assert not any(KEYBOARD_ONLY_REASON in r for r in reasons)
