"""v0.10.6 review fixes: human false positives in engine.py and the version bump script."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from synapse_shield.engine import analyze_behavior

ROOT = Path(__file__).resolve().parents[1]


def _mobile_login() -> dict:
    """A phone user taps username, password and the login button, seconds apart (SDK touch format)."""
    moves, clicks = [], []
    t = 1000
    for i, (x, y) in enumerate([(180, 300), (180, 380), (190, 470)]):
        for j in range(3):  # touchstart + small finger drift
            moves.append({"x": x + j, "y": y + (j % 2), "t": t + j * 16, "r": 11.0 + 0.6 * i + 0.3 * j,
                          "f": 0.4 + 0.05 * j, "source": "touch"})
        clicks.append({"x": x + 2, "y": y + 1, "t": t + 95, "r": 11.5 + 0.5 * i, "tap_duration_ms": 80 + 17 * i,
                       "source": "touch"})
        t += 2600 + 700 * i
    return {
        "mouse_movements": moves,
        "clicks": clicks,
        "keystrokes": [],
        "scrolls": [],
        "browser": {"webdriver": False, "screen_width": 390, "screen_height": 844, "device_pixel_ratio": 3,
                    "touch_supported": True, "max_touch_points": 5, "motion_variance": 0.02,
                    "plugins_length": 0, "orientation": "portrait-primary"},
    }


def test_mobile_taps_seconds_apart_are_not_polynomial_acceleration():
    # Rule 4.C ran on touch input: taps ~3 s apart give acceleration_var ~1e-10 and +65 (non-bypassable).
    score, decision, reasons, _ = analyze_behavior(_mobile_login())
    assert not any("polynomial acceleration" in r for r in reasons), reasons
    assert decision == "Human", (score, reasons)


def _keys_with_rollover() -> list[dict]:
    """Typing with Shift held and rollover: the next key goes down before the previous one is released,
    so the up->down flight time is negative on average."""
    ks = []
    t = 1000.0
    for i in range(8):
        down = t
        up = down + 104.0 + (i * 7) % 23  # organic, varying hold (95-130 ms)
        ks.append({"type": "down", "key": "masked", "t": down})
        ks.append({"type": "up", "key": "masked", "t": up, "down": down, "up": up, "duration_ms": up - down})
        t += 85.0 + (i % 3) * 9.0  # next key pressed 85-103 ms later, before this one is released
    return ks


def test_negative_flight_time_is_not_superhuman_typing():
    moves = [{"x": 200 + 9 * i + (i % 3), "y": 300 + 4 * i + (i % 2) * 3, "t": 1000 + 33 * i} for i in range(25)]
    tel = {"mouse_movements": moves, "clicks": [{"x": 420, "y": 400, "t": 1900}], "keystrokes": _keys_with_rollover(),
           "scrolls": [], "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080,
                                      "plugins_length": 5, "touch_supported": False}}
    _, _, reasons, details = analyze_behavior(tel)
    assert not any("Superhuman input frequency" in r for r in reasons), reasons


def test_superhuman_key_interval_requires_positive_interval():
    from synapse_shield.engine import _superhuman_key_interval

    assert _superhuman_key_interval({"key_interval_avg": 10.0})
    assert not _superhuman_key_interval({"key_interval_avg": -20.8})  # Shift held / rollover
    assert not _superhuman_key_interval({"key_interval_avg": 0.0})  # interval not measurable
    assert not _superhuman_key_interval({"key_interval_avg": 25.0})
    assert not _superhuman_key_interval({})


def test_brave_cap_survives_rollover_typing():
    # The Brave privacy cap used `key_interval_avg < 25` without the lower bound, so a real Brave user typing
    # with rollover (negative up->down interval) lost the 34.0 cap. Same organic mouse as test_security_patches.
    import math
    import random

    rnd = random.Random(42)
    moves, t = [], 1000
    for i in range(35):
        t += rnd.randint(18, 32)
        moves.append({"x": round(50 + i * 12 + rnd.gauss(0, 1.8)), "y": round(100 + math.sin(i / 3.0) * 18.0
                                                                              + rnd.gauss(0, 1.8)), "t": t})
    tel = {"browser": {"is_canvas_hooked": True, "webdriver": False, "screen_width": 1920, "screen_height": 1080},
           "mouse_movements": moves, "clicks": [{"x": moves[-1]["x"], "y": moves[-1]["y"], "t": t}],
           "keystrokes": _keys_with_rollover(), "scrolls": []}
    _, _, reasons, details = analyze_behavior(tel)
    assert details["features"]["key_interval_avg"] < 0, details["features"]["key_interval_avg"]
    assert any("capped at 34.0" in r for r in reasons), reasons


def test_rollover_typing_is_not_labelled_robotic_keystroke():
    from synapse_shield.engine import classify_threat

    # Keyboard-only features (no pointer data); touch_supported skips the pointer-based labels before step 5.
    feats = {"key_count": 8, "key_interval_var": 30.0, "key_interval_avg": -20.8, "touch_supported": True}
    assert classify_threat(feats, {}, 0, 0.0, 0.0, "Bot", []) != "ROBOTIC_KEYSTROKE"
    feats["key_interval_avg"] = 12.0
    assert classify_threat(feats, {}, 0, 0.0, 0.0, "Bot", []) == "ROBOTIC_KEYSTROKE"


def test_bump_version_updates_version_module(tmp_path):
    (tmp_path / "src" / "synapse_shield").mkdir(parents=True)
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    (tmp_path / "src" / "synapse_shield" / "_version.py").write_text('__version__ = "0.0.1"\n', encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "bump_version.py"), "9.9.9"], cwd=tmp_path, check=True,
                   capture_output=True, env=env)
    assert (tmp_path / "src" / "synapse_shield" / "_version.py").read_text(encoding="utf-8") == '__version__ = "9.9.9"\n'
    assert 'version = "9.9.9"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_bump_version_fails_loudly_without_version_module(tmp_path):
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "bump_version.py"), "9.9.9"], cwd=tmp_path,
                         capture_output=True, env=env)
    assert res.returncode != 0
