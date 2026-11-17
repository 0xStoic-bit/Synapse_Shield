"""Spoofed ``touch_supported`` flag on sessions without pointer motion.

A desktop keyboard / click bot that sends ``mouse_points == 0`` and ``browser.touch_supported = True`` used to skip
both the spoofed-touch check (which required >= 3 mouse points) and the whole ``not is_touch`` block (+50 / +40 /
+60), so it scored 0. Without any capacitive evidence (touch events, taps, contact radius or tap duration) the flag
is now rejected on desktop-width screens: the session is reclassified as non-touch and goes through the desktop
rules (+40 keyboard-only / +50 / +60), so the flag gives a bot no advantage over not sending it. There is no extra
spoofing penalty: touch-screen laptops and iPads with a hardware keyboard really report touch_supported=true
without touch events, and a +65 penalty blocked 71-100% of them (synthetic measurement).

With >= 3 pointer points and no touch evidence the same principle applies: the flag is rejected (desktop kinematic
rules run) and the former +75 spoofing penalty is gone. It blocked every touch-screen laptop / Surface user moving a
mouse or touchpad, while no known mouse-bot class (Bezier, linear, sine, minimum-jerk, jitter, replay) scored lower
with the flag after reclassification than without it (synthetic measurement).

Keyboard timing comes from the synthetic CMU / Aalto keyboard-only generator in test_keyboard_only_access.py.
These are synthetic sessions, not recorded humans.
"""

import copy
import random

import pytest

from synapse_shield import adversarial
from synapse_shield.engine import analyze_behavior
from test_keyboard_only_access import BROWSER, _bot_keyboard_only_session, _decide, _human_keyboard_only_session

SPOOF_REASON = "Spoofed touch_supported flag without capacitive touch telemetry."
NO_MOTION_REASON = "without mouse movement telemetry"


def _with_touch_flag(tel, **browser):
    tel["browser"].update({"touch_supported": True, "max_touch_points": 10, **browser})
    return tel


def _touch_browser():
    return dict(BROWSER, touch_supported=True, max_touch_points=10)


def _keys(n, start=1000.0, hold=90.0, flight=140.0):
    ev, t = [], start
    for _ in range(n):
        ev.append({"type": "down", "key": "masked", "t": round(t)})
        ev.append({"type": "up", "key": "masked", "t": round(t + hold), "duration_ms": round(hold)})
        t += hold + flight
    return ev


@pytest.fixture
def no_env_pow(monkeypatch):
    monkeypatch.delenv("SYNAPSE_KEYBOARD_ONLY_CHALLENGE", raising=False)
    monkeypatch.delenv("SYNAPSE_ENABLE_POW", raising=False)


def test_keyboard_bot_with_spoofed_touch_flag_is_caught(no_env_pow):
    tel = {"mouse_movements": [], "clicks": [], "keystrokes": _keys(5), "scrolls": [],
           "browser": _touch_browser()}
    score, classification, reasons, details = analyze_behavior(tel)
    features = details["features"]
    assert features["key_count"] == 5 and features["mouse_points"] == 0
    assert SPOOF_REASON in reasons
    assert any(NO_MOTION_REASON in r for r in reasons)  # the not-is_touch block runs again
    assert features["touch_supported"] is False
    # Same verdict as the identical session without the flag: the flag buys nothing.
    no_flag = dict(tel, browser=dict(BROWSER))
    assert score == analyze_behavior(no_flag)[0] and classification == "Bot", (score, reasons)
    for i, enable_pow in enumerate((False, True)):
        d = _decide(tel, f"198.19.9.{i + 1}", enable_pow=enable_pow)
        assert not d.allowed, (enable_pow, d.action, d.bot_score)


@pytest.mark.parametrize("seed", range(10))
def test_jittered_keyboard_bot_with_spoofed_touch_flag_is_not_a_clean_allow(seed, no_env_pow):
    tel = _with_touch_flag(_bot_keyboard_only_session(seed, lambda r: r.uniform(80, 200), lambda r: r.uniform(60, 120)))
    score, _, reasons, _ = analyze_behavior(tel)
    assert SPOOF_REASON in reasons and score >= 35.0, (score, reasons)  # gray area at least, never a clean 0
    for i, enable_pow in enumerate((False, True)):  # challenged or blocked, never allowed without PoW
        assert not _decide(tel, f"198.19.{10 + i}.{seed + 1}", enable_pow=enable_pow).allowed


@pytest.mark.parametrize("points", [0, 1, 2])
def test_click_macro_with_spoofed_touch_flag_is_penalized(points):
    tel = {"mouse_movements": [{"x": 900 + i, "y": 600, "t": 2000 + 16 * i} for i in range(points)],
           "clicks": [{"x": 960, "y": 600, "t": 2400}], "keystrokes": [], "scrolls": [],
           "browser": _touch_browser()}
    score, classification, reasons, _ = analyze_behavior(tel)
    assert SPOOF_REASON in reasons and classification == "Bot" and score >= 50.0, (score, reasons)


def _phone_session(seed):
    """Real phone login: finger swipe/taps with varying contact radius, organic tap hold times, soft keyboard."""
    rnd = random.Random(seed)
    moves, t, x, y = [], 500.0, rnd.uniform(80, 300), rnd.uniform(300, 600)
    for _ in range(rnd.randint(6, 12)):
        x += rnd.gauss(0, 6)
        y += rnd.gauss(-12, 5)
        t += rnd.uniform(12, 20)
        moves.append({"x": x, "y": y, "t": t, "r": rnd.uniform(9.0, 14.0), "source": "touch"})
    clicks = []
    for _ in range(2):  # each tap lands where the finger was last recorded
        t += rnd.uniform(400, 900)
        x, y = rnd.uniform(60, 330), rnd.uniform(200, 700)
        for _ in range(2):
            t += rnd.uniform(12, 20)
            moves.append({"x": x + rnd.gauss(0, 1), "y": y + rnd.gauss(0, 1), "t": t, "r": rnd.uniform(9.0, 14.0),
                          "source": "touch"})
        clicks.append({"x": x, "y": y, "t": t + 5, "source": "touch", "r": rnd.uniform(9.0, 14.0),
                       "tap_duration_ms": rnd.uniform(70, 160)})
    keys = _human_keyboard_only_session(seed)["keystrokes"]
    shift = t + 2500 - min(e["t"] for e in keys)
    keys = [dict(e, t=e["t"] + shift) for e in keys]
    return {"mouse_movements": moves, "clicks": clicks, "keystrokes": keys, "scrolls": [], "browser": dict(BROWSER, screen_width=390, screen_height=844, touch_supported=True,
                                           max_touch_points=5, webgl_renderer="Apple GPU")}


@pytest.mark.parametrize("seed", range(10))
def test_real_phone_session_is_not_penalized(seed):
    score, classification, reasons, details = analyze_behavior(_phone_session(seed))
    features = details["features"]
    assert features["touch_event_count"] > 0 and features["tap_count"] > 0
    assert not any("Spoofed touch_supported" in r for r in reasons)
    assert not any(NO_MOTION_REASON in r for r in reasons)
    assert classification == "Human" and score < 35.0, (score, reasons)


@pytest.mark.parametrize("seed", range(20))
def test_tablet_keyboard_session_with_a_real_tap_is_not_penalized(seed):
    """iPad + hardware keyboard that tapped the field once (iOS reports r=0, but a real tap hold time)."""
    tel = _with_touch_flag(_human_keyboard_only_session(seed), screen_width=1180, screen_height=820,
                           max_touch_points=5, webgl_renderer="Apple GPU")
    tel["clicks"] = [{"x": 400, "y": 300, "t": 300, "source": "touch", "r": 0, "tap_duration_ms": 95}]
    score, _, reasons, _ = analyze_behavior(tel)
    assert SPOOF_REASON not in reasons and score < 35.0, (score, reasons)


TRAJECTORY_SPOOF_REASON = "Spoofed touch_supported flag on non-capacitive desktop pointer trajectory."


def _without_touch_flag(tel):
    tel = copy.deepcopy(tel)
    tel["browser"].update(touch_supported=False, max_touch_points=0)
    return tel


def test_touch_flag_with_mouse_trajectory_is_reclassified_without_penalty():
    """>= 3 pointer points without touch evidence: the flag is rejected (desktop rules run), but no extra penalty.

    The former +75 blocked every touch-screen laptop user moving a mouse or touchpad and added no detection over
    the desktop kinematic rules for any known mouse-bot class (synthetic measurement).
    """
    tel = {"mouse_movements": [{"x": 100 + 7 * i, "y": 200 + 3 * i, "t": 1000 + 16 * i} for i in range(12)],
           "clicks": [], "keystrokes": _keys(5, start=1500), "scrolls": [], "browser": _touch_browser()}
    score, classification, reasons, details = analyze_behavior(copy.deepcopy(tel))
    assert TRAJECTORY_SPOOF_REASON in reasons
    assert SPOOF_REASON not in reasons
    assert details["features"]["touch_supported"] is False
    assert any("straight-line trajectory" in r for r in reasons)  # desktop kinematic filters ran
    assert (score, classification) == analyze_behavior(_without_touch_flag(tel))[:2]


def _bezier(rnd):
    return adversarial.generate_bezier_telemetry(start=(rnd.uniform(50, 300), rnd.uniform(50, 300)),
                                                 end=(rnd.uniform(400, 900), rnd.uniform(400, 800)),
                                                 steps=rnd.randint(35, 65), duration_ms=rnd.uniform(800, 1800))


def _linear(rnd):
    return adversarial.generate_linear_telemetry(start=(rnd.uniform(50, 300), rnd.uniform(50, 300)),
                                                 end=(rnd.uniform(400, 900), rnd.uniform(400, 800)),
                                                 steps=rnd.randint(35, 65), duration_ms=rnd.uniform(800, 1800))


def _min_jerk(rnd):
    return adversarial.generate_minimum_jerk_telemetry(start=(rnd.uniform(50, 300), rnd.uniform(50, 300)),
                                                       end=(rnd.uniform(400, 900), rnd.uniform(400, 800)),
                                                       steps=rnd.randint(35, 65), duration_ms=rnd.uniform(800, 1800))


def _jitter(rnd):
    """Straight path plus point-independent uniform noise, integer pixels like a browser."""
    amp, step, dt = rnd.uniform(1, 6), rnd.uniform(2, 12), rnd.choice([8, 16, 30])
    moves = [{"x": round(100 + i * step + rnd.uniform(-amp, amp)), "y": round(300 + rnd.uniform(-amp, amp)),
              "t": 1000 + i * dt} for i in range(80)]
    return {"mouse_movements": moves, "clicks": [{"x": moves[-1]["x"], "y": moves[-1]["y"], "t": moves[-1]["t"] + 80}],
            "keystrokes": [], "scrolls": [], "browser": dict(BROWSER)}


@pytest.mark.parametrize("make_bot", [_bezier, _linear, _min_jerk, _jitter])
@pytest.mark.parametrize("seed", range(5))
def test_touch_flag_gives_mouse_bot_no_advantage(make_bot, seed):
    """Bot trajectory + spoofed flag scores exactly like the same bot without the flag, and is still a Bot."""
    rnd = random.Random(seed)
    random.seed(seed)  # adversarial generators draw from the global RNG
    bot = make_bot(rnd)
    flagged = _with_touch_flag(copy.deepcopy(bot))
    score, classification, reasons, _ = analyze_behavior(copy.deepcopy(flagged))
    assert TRAJECTORY_SPOOF_REASON in reasons
    assert (score, classification) == analyze_behavior(_without_touch_flag(bot))[:2]
    assert classification == "Bot", (score, reasons)


@pytest.mark.parametrize("seed", range(20))
def test_touch_laptop_mouse_user_scores_no_worse_than_without_flag(seed, no_env_pow):
    """Touch-screen laptop / Surface user moving a mouse: touch_supported=true, maxTouchPoints=10, no touch events."""
    random.seed(seed)
    w, h = TOUCH_LAPTOPS[seed % len(TOUCH_LAPTOPS)]
    human = adversarial.generate_synthetic_human_telemetry()
    human["browser"].update(screen_width=w, screen_height=h)
    flagged = _with_touch_flag(copy.deepcopy(human))
    score, classification, _, _ = analyze_behavior(copy.deepcopy(flagged))
    base_score, base_classification = analyze_behavior(_without_touch_flag(human))[:2]
    assert score <= base_score
    assert base_classification == "Human" and classification == "Human", (score, base_score)
    d = _decide(flagged, f"198.19.30.{seed + 1}", enable_pow=False)
    assert d.allowed, (d.action, d.bot_score)


# Legitimate devices that really report touch_supported=true but produce no touch events. With the earlier +65
# spoofing penalty core.py blocked 100% of touch-laptop and 71% of iPad keyboard users; reclassification alone
# sends them to the keyboard-only gray-area challenge instead.
TOUCH_LAPTOPS = [(1920, 1080), (1536, 864), (1368, 912), (1280, 800), (1440, 960), (2256, 1504)]
IPAD_LANDSCAPE = [(1024, 1366), (1366, 1024), (1180, 820), (1194, 834), (1032, 1376)]


def _block_rate(sessions):
    return sum(analyze_behavior(t)[1] == "Bot" for t in sessions) / len(sessions)


def test_touch_laptop_keyboard_only_user_is_not_blocked():
    sessions = []
    for seed in range(200):
        w, h = TOUCH_LAPTOPS[seed % len(TOUCH_LAPTOPS)]
        sessions.append(_with_touch_flag(_human_keyboard_only_session(seed), screen_width=w, screen_height=h))
    assert _block_rate(sessions) <= 0.05


def test_ipad_hardware_keyboard_user_is_not_blocked():
    sessions = []
    for seed in range(200):
        w, h = IPAD_LANDSCAPE[seed % len(IPAD_LANDSCAPE)]
        sessions.append(_with_touch_flag(_human_keyboard_only_session(seed), screen_width=w, screen_height=h,
                                         max_touch_points=5, webgl_renderer="Apple GPU"))
    assert _block_rate(sessions) <= 0.05


def test_ipad_portrait_below_desktop_width_is_unaffected():
    for seed in range(20):
        tel = _with_touch_flag(_human_keyboard_only_session(seed), screen_width=820, screen_height=1180,
                               max_touch_points=5, webgl_renderer="Apple GPU")
        _, _, reasons, _ = analyze_behavior(tel)
        assert SPOOF_REASON not in reasons
