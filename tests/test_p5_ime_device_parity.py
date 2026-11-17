"""#5 mobil IME muafiyeti (dokunma kanıtı / ekran genişliği) ve istemci digraph bayrağı: davranış + Rust-Python paritesi.

Parite toleransı Demir Kural 3: |y_rust - y_py| < 1e-5.
"""

import random

import pytest

from synapse_shield import features as F
from synapse_shield.features import extract_features

HAS_RUST = bool(F.HAS_RUST_CORE)
needs_rust = pytest.mark.skipif(not HAS_RUST, reason="Rust core (synapse_core_rs) required for parity test")


def _tel(moves, keys=None, browser=None, clicks=None):
    return {
        "mouse_movements": moves,
        "clicks": clicks if clicks is not None else [],
        "keystrokes": keys or [],
        "scrolls": [],
        "browser": browser if browser is not None else {"screen_width": 1920, "screen_height": 1080},
    }


# --- #5 davranış + parite ----------------------------------------------------------------------------------

def _ime_keys(n=8, dwell=50.0):
    ks, t = [], 1000.0
    for i in range(n):
        ks.append({"type": "down", "key": "Unidentified", "t": t})
        ks.append({"type": "up", "key": "Unidentified", "t": t + dwell})
        t += dwell + [80.0, 160.0, 240.0, 120.0, 300.0, 200.0, 90.0][i % 7]
    return ks


@pytest.mark.parametrize("force_python", [True, False])
def test_spoofed_ime_on_desktop_without_touch_is_not_exempt(force_python):
    if not force_python and not HAS_RUST:
        pytest.skip("Rust core required")
    desktop = extract_features(_tel([], _ime_keys()), force_python=force_python)["keystroke_score"]
    phone = extract_features(
        _tel([], _ime_keys(), browser={"screen_width": 412, "screen_height": 915, "touch_supported": True}),
        force_python=force_python,
    )["keystroke_score"]
    tapped = extract_features(
        _tel([], _ime_keys(), clicks=[{"x": 10, "y": 10, "t": 900, "source": "touch", "tap_duration_ms": 90}]),
        force_python=force_python,
    )["keystroke_score"]
    assert desktop >= 0.70  # sabit 50 ms dwell (+0.80) artık atlanmıyor
    assert phone < 0.70 and tapped < 0.70


@pytest.mark.parametrize("force_python", [True, False])
def test_client_digraph_flag_cannot_lower_score(force_python):
    if not force_python and not HAS_RUST:
        pytest.skip("Rust core required")
    ks, t = [], 1000.0
    for i in range(12):
        is_freq = i % 2 == 1
        down = {"type": "down", "key": "masked", "t": t}
        if i:
            down["is_freq_digraph"] = is_freq
        ks += [down, {"type": "up", "key": "masked", "t": t + 50.0}]  # sabit dwell: +0.80
        t += (220.0 if is_freq else 90.0) + (i % 3) * 17.0  # sonraki (zıt sınıf) tuşun uçuşu
    with_flag = extract_features(_tel([], ks), force_python=force_python)["keystroke_score"]
    no_flag_ks = [{k: v for k, v in e.items() if k != "is_freq_digraph"} for e in ks]
    without = extract_features(_tel([], no_flag_ks), force_python=force_python)["keystroke_score"]
    assert with_flag == pytest.approx(without, abs=1e-9)


@needs_rust
def test_ime_device_context_differential_fuzz():
    rng = random.Random(5005)
    for _ in range(300):
        n = rng.randint(3, 20)
        ks, t = [], 1000.0
        for _i in range(n):
            t += rng.uniform(20.0, 400.0)
            dwell = rng.choice([50.0, rng.uniform(5.0, 200.0)])
            key = rng.choice(["Unidentified", "Process", "masked", "a"])
            down = {"type": "down", "key": key, "t": t}
            if rng.random() < 0.5:
                down["is_freq_digraph"] = rng.random() < 0.5
            ks += [down, {"type": "up", "key": key, "t": t + dwell}]
        browser = {"screen_width": rng.choice([0, 412, 1023, 1024, 1920]), "screen_height": 900,
                   "touch_supported": rng.random() < 0.5}
        clicks = rng.choice([[], [{"x": 5, "y": 5, "t": 900, "source": "touch"}],
                             [{"x": 5, "y": 5, "t": 900, "tap_duration_ms": 80}], [{"x": 5, "y": 5, "t": 900}]])
        moves = rng.choice([[], [{"x": 1, "y": 1, "t": 1, "r": 12.0}], [{"x": 1, "y": 1, "t": 1, "source": "touch"}]])
        tel = _tel(moves, ks, browser=browser, clicks=clicks)
        rust = F.synapse_core_rs.extract_features_rs(tel)
        py = extract_features(tel, force_python=True)
        assert abs(rust["keystroke_score"] - py["keystroke_score"]) < 1e-5, tel
