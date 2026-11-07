"""
Regression tests for the external review of v0.10.5 (findings 1, 2, 3, 4, 5, 7, 8, 10).

Each test reproduces the reported failure first (these all passed against the unfixed code only by accident
of fixtures that were too synthetic) and pins the fixed behaviour.
"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib

import pytest

from synapse_shield import core, privacy, tokens
from synapse_shield.engine import analyze_behavior
from synapse_shield import storage as storage_mod

from test_mutation_gaps import NOW_MS, _events, _fake, _token, _verify, frozen  # noqa: F401

ROOT = pathlib.Path(__file__).resolve().parent.parent
BROWSER = {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080}


def _analyze(telemetry, history=None, accessibility=False):
    score, cls, reasons, details = analyze_behavior(telemetry, 1, False, accessibility, history or [])
    return score, cls, reasons, details


# --- Finding 1: a lone scroll event must not count as interaction ----------------------------------------------
def test_scroll_only_desktop_submission_is_a_bot():
    tel = {"browser": BROWSER, "mouse_movements": [], "keystrokes": [], "clicks": [],
           "scrolls": [{"t": 1000, "y": 10}]}
    score, cls, reasons, details = _analyze(tel)
    assert score >= 50 and cls == "Bot"
    assert any("DESKTOP_SCROLL_ONLY_SUBMISSION" in r for r in reasons)
    assert details["features"]["total_interactive_events"] == 0


def test_scroll_only_is_tolerated_in_accessibility_mode():
    tel = {"browser": BROWSER, "mouse_movements": [], "keystrokes": [], "clicks": [],
           "scrolls": [{"t": 1000, "y": 10}]}
    score, cls, reasons, _ = _analyze(tel, accessibility=True)
    assert not any("DESKTOP_SCROLL_ONLY_SUBMISSION" in r for r in reasons)
    assert score < 50


def test_scroll_plus_click_still_counts_as_interaction():
    tel = {"browser": BROWSER, "mouse_movements": [], "keystrokes": [], "scrolls": [{"t": 1000, "y": 10}],
           "clicks": [{"x": 5, "y": 5, "t": 1100}]}
    _, _, reasons, details = _analyze(tel)
    assert details["features"]["total_interactive_events"] >= 2
    assert not any("DESKTOP_SCROLL_ONLY_SUBMISSION" in r for r in reasons)


def test_core_treats_scroll_only_as_hard_violation_for_pow(monkeypatch):
    """A scroll-only request in the PoW gray band must be blocked, not offered a proof-of-work escape."""
    tel = {"browser": BROWSER, "mouse_movements": [], "keystrokes": [], "clicks": [],
           "scrolls": [{"t": 1000, "y": 10}]}
    d = core.evaluate_synapse_request_sync(client_ip="198.19.7.1", user_agent="ua", token=_token(tel),
                                           enable_pow=True)
    assert d.status_code == 403 and d.classification == "Bot"
    storage_mod.get_storage().unban_ip("198.19.7.1")


# --- Finding 2: repeated single taps (mobile / keyboard users) must never become "session invariance" ----------
def _tap(t0):
    return {"mouse_movements": [{"x": 300, "y": 520, "t": t0, "source": "touch", "r": 9.4, "f": 0.4}],
            "keystrokes": [], "scrolls": [],
            "clicks": [{"x": 300, "y": 520, "t": t0 + 90, "r": 9.4, "tap_duration_ms": 96, "source": "touch"}],
            "browser": {**BROWSER, "touch_supported": True, "max_touch_points": 5, "screen_width": 390}}


PLACEHOLDER = {"avg_jerk": 0.0, "straightness": 1.0, "total_distance": 0.0, "submovement_count": 0,
               "spectral_purity": 0.0}


def test_fourth_single_tap_is_not_blocked_by_session_invariance():
    score, cls, reasons, _ = _analyze(_tap(5000), history=[dict(PLACEHOLDER)] * 3)
    assert cls == "Human" and score < 50, reasons
    assert not any("Session Behavioral Invariance" in r for r in reasons)


def test_real_trajectory_history_still_triggers_invariance():
    """The filter must only drop placeholder entries, not real replayed trajectories."""
    real = {"avg_jerk": 0.00015, "straightness": 0.9450, "total_distance": 310.0, "submovement_count": 3}
    tel = {"browser": BROWSER, "keystrokes": [], "scrolls": [], "clicks": [{"x": 1, "y": 1, "t": 1200}],
           "mouse_movements": [{"x": 100 + i * 7, "y": 100 + i * 3 + (i % 4), "t": 1000 + i * 17 + (i * 3) % 7}
                               for i in range(30)]}
    _, _, reasons, _ = _analyze(tel, history=[dict(real)] * 3)
    assert any("Session Behavioral Invariance" in r for r in reasons)


@pytest.mark.parametrize("features,recorded", [
    ({"mouse_points": 1, "total_distance": 0.0}, False),   # single tap
    ({"mouse_points": 2, "total_distance": 40.0}, False),  # too short to be a trajectory
    ({"mouse_points": 5, "total_distance": 0.0}, False),   # no movement
    ({"mouse_points": 3, "total_distance": 0.5}, True),
    ({"mouse_points": 40, "total_distance": 300.0}, True),
])
def test_only_real_trajectories_are_stored_in_session_history(monkeypatch, features, recorded):
    calls = []

    class Spy(storage_mod.SQLiteStorageBackend):
        def record_session_telemetry(self, session_id, metrics_, max_history=10, window_sec=300):
            calls.append(metrics_)

    monkeypatch.setattr(core, "get_storage", lambda: Spy(db_path=":memory:"))
    monkeypatch.setattr(core, "analyze_behavior", _fake(1.0, total_interactive_events=5, **features))
    core.evaluate_synapse_request_sync(client_ip="198.19.7.20", user_agent="ua", token=_token())
    assert bool(calls) is recorded


# --- Finding 3: short zero-entropy lines -------------------------------------------------------------------------
def _line(n, step, dt_fn):
    return {"browser": BROWSER, "keystrokes": [], "scrolls": [], "clicks": [{"x": 125, "y": 100, "t": 1500}],
            "mouse_movements": [{"x": 100 + i * step, "y": 100, "t": dt_fn(i)} for i in range(n)]}


def test_25px_perfect_line_is_flagged():
    score, cls, reasons, _ = _analyze(_line(6, 5, lambda i: 1000 + i * 16))
    assert score >= 50 and cls == "Bot"
    assert any("Zero-entropy micro-trajectory" in r for r in reasons)


def test_micro_rule_needs_all_three_zero_entropy_signals():
    """Timing jitter alone (a real, slightly irregular 25px move) must not trigger the rule."""
    jitter = [0, 16, 33, 49, 67, 83]
    _, _, reasons, _ = _analyze(_line(6, 5, lambda i: 1000 + jitter[i]))
    assert not any("Zero-entropy micro-trajectory" in r for r in reasons)


def test_micro_rule_ignores_sub_5px_and_over_30px_ranges():
    _, _, reasons, _ = _analyze(_line(6, 0.5, lambda i: 1000 + i * 16))
    assert not any("Zero-entropy micro-trajectory" in r for r in reasons), "<= 5px is a click wobble"
    _, _, reasons, _ = _analyze(_line(6, 8, lambda i: 1000 + i * 16))
    assert not any("Zero-entropy micro-trajectory" in r for r in reasons), "> 30px has its own rules"


def test_micro_rule_is_softened_in_accessibility_mode():
    base, _, _, _ = _analyze(_line(6, 5, lambda i: 1000 + i * 16))
    soft, _, _, _ = _analyze(_line(6, 5, lambda i: 1000 + i * 16), accessibility=True)
    assert soft < base


# --- Finding 4: closed allow-list instead of a regex guess ---------------------------------------------------
@pytest.mark.parametrize("word", ["Mustafa", "Sifre123", "Ankara", "password", "ab", "Ab1", "F25", "ArrowLeftt"])
def test_multi_character_words_are_masked(word):
    assert privacy.safe_key_name(word) == "masked"


@pytest.mark.parametrize("key", ["Enter", "enter", "BACKSPACE", "ArrowLeft", "arrowdown", "Unidentified", "process",
                                 "Dead", "F1", "f12", "F24", "Shift", "Control", "Alt", "AltGraph", "Meta", "Tab",
                                 "Escape", "Delete", "PageUp", "Home", "End"])
def test_allow_listed_control_keys_pass_through(key):
    assert privacy.safe_key_name(key) == key


def test_sanitizer_masks_words_but_keeps_control_keys():
    out = privacy.sanitize_keystrokes([{"key": "Mustafa", "t": 1}, {"key": "Sifre123", "t": 2},
                                       {"key": "a", "t": 3}, {"key": "Enter", "t": 4}])
    assert [e["key"] for e in out] == ["masked", "masked", "masked", "Enter"]


def test_named_keys_cover_function_keys_and_basics():
    assert {f"f{i}" for i in range(1, 25)} <= privacy.NAMED_KEYS
    assert {"enter", "backspace", "unidentified", "process", "dead"} <= privacy.NAMED_KEYS


def test_sdk_allow_lists_match_the_server():
    """The server and all three SDKs must share one list, otherwise masking differs by client."""
    import re
    expected = set(privacy.NAMED_KEYS)
    for rel in ("src/synapse_shield/static/synapse-sdk.js", "synapse-shield-react/src/useSynapseShield.ts",
                "synapse-shield-vue/src/useSynapseShield.ts"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        start = text.index("NAMED_KEYS")
        block = text[start:text.index("]);", start)]
        assert set(re.findall(r'"([a-z0-9]+)"', block)) == expected, rel
        assert "NAMED_KEY_RE" not in text, rel


# --- Finding 5: PyO3 extension-module must be a feature, not a hard dependency ------------------------------------
def test_pyo3_extension_module_is_an_optional_feature_enabled_by_maturin():
    cargo = (ROOT / "crates/synapse_core_rs/Cargo.toml").read_text(encoding="utf-8")
    assert 'extension-module = ["pyo3/extension-module"]' in cargo
    dep_line = next(line for line in cargo.splitlines() if line.startswith("pyo3 ="))
    assert "extension-module" not in dep_line, "a hard extension-module feature breaks `cargo test` on Linux"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'features = ["pyo3/extension-module"]' in pyproject, "wheels would link libpython without this"


# --- Finding 7: Litestar guard parity + enable_pow on every adapter -------------------------------------------------
@pytest.mark.parametrize("module", ["flask", "django", "sanic", "litestar", "middleware", "asgi"])
def test_every_adapter_exposes_enable_pow(module):
    src = (ROOT / f"src/synapse_shield/{module}.py").read_text(encoding="utf-8")
    assert "enable_pow" in src


def test_litestar_guard_and_middleware_accept_enable_pow():
    from synapse_shield import litestar as ls
    assert inspect.signature(ls.synapse_guard).parameters["enable_pow"].default is False
    assert inspect.signature(ls.LitestarSynapseMiddleware.__init__).parameters["enable_pow"].default is False


def test_flask_and_sanic_signatures_expose_enable_pow():
    from synapse_shield import flask as fl
    assert inspect.signature(fl.shield_protect_flask).parameters["enable_pow"].default is False
    assert inspect.signature(fl.SynapseFlaskMiddleware.__init__).parameters["enable_pow"].default is False
    if importlib.util.find_spec("sanic"):
        from synapse_shield import sanic as sn
        assert inspect.signature(sn.shield_protect_sanic).parameters["enable_pow"].default is False
        assert inspect.signature(sn.SynapseSanicMiddleware.__init__).parameters["enable_pow"].default is False


def test_litestar_middleware_builds_its_asgi_handler_once():
    ls = pytest.importorskip("litestar")  # noqa: F841
    from synapse_shield.litestar import LitestarSynapseMiddleware

    async def app(scope, receive, send):
        return None

    mw = LitestarSynapseMiddleware(app, enable_pow=True)
    assert mw._asgi_handler.enable_pow is True
    handler = mw._asgi_handler
    assert mw._asgi_handler is handler


def _litestar_app(guard):
    from litestar import Litestar, post
    from litestar.testing import TestClient

    @post("/g", guards=[guard], sync_to_thread=False)
    def handler(data: dict) -> dict:
        return {"ok": True}

    return TestClient(Litestar([handler]))


def test_litestar_guard_enforces_the_256kb_limit():
    pytest.importorskip("litestar")
    from synapse_shield.litestar import synapse_guard

    with _litestar_app(synapse_guard()) as client:
        big = {"token": "x", "pad": "a" * (core.MAX_PAYLOAD_SIZE + 10)}
        assert client.post("/g", json=big).status_code == 413


def test_litestar_guard_returns_429_challenge_not_403(monkeypatch):
    pytest.importorskip("litestar")
    from synapse_shield.litestar import synapse_guard

    monkeypatch.setattr(core, "analyze_behavior", _fake(40.0, total_interactive_events=9, mouse_points=9))
    with _litestar_app(synapse_guard(enable_pow=True)) as client:
        r = client.post("/g", json={"token": _token()}, headers={"user-agent": "ua"})
        assert r.status_code == 429
        body = r.json()
        detail = body.get("detail", body)
        assert detail["status"] == "challenge_required" and detail["pow_salt"]


# --- Finding 8: every event timestamp field is validated ---------------------------------------------------------
@pytest.mark.usefixtures("frozen")
def test_down_up_and_time_fields_are_checked_for_staleness(monkeypatch):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "0")
    ts = NOW_MS - 3000
    stale = ts - 60_000
    for field in ("down", "up", "time"):
        tel = {"keystrokes": [{"key": "enter", field: stale}, {"key": "enter", field: stale + 10}]}
        ok, reason, _ = _verify(ts, tel)
        assert ok is False and "Stale" in reason, field
        fresh = {"keystrokes": [{"key": "enter", field: ts + 100}, {"key": "enter", field: ts + 200}]}
        assert _verify(ts, fresh)[0] is True, field


@pytest.mark.parametrize("field", ["t", "down", "up", "time"])
@pytest.mark.parametrize("bad", [True, False, "12", [1], float("nan"), float("inf")])
@pytest.mark.usefixtures("frozen")
def test_non_numeric_or_bool_timestamps_are_rejected(monkeypatch, field, bad):
    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "0")
    ok, reason, _ = _verify(NOW_MS - 3000, {"keystrokes": [{"key": "a", field: bad}]})
    assert ok is False and "TypeError" in reason


def test_event_time_fields_constant():
    assert tokens._EVENT_TIME_FIELDS == ("t", "down", "up", "time")


# --- Finding 10: shared digraph set, optional Sanic -------------------------------------------------------------
def test_digraph_sets_are_identical_in_every_layer():
    import re
    def digraphs(rel, anchor):
        text = (ROOT / rel).read_text(encoding="utf-8")
        start = text.index(anchor)
        end = text.index("];", start) if rel.endswith(".rs") else (text.index("]", start) if rel.endswith((".js", ".ts")) else text.index("})", start))
        return set(re.findall(r'"([a-z]{2})"', text[start:end]))
    py = set(privacy.FREQUENT_DIGRAPHS)
    assert digraphs("src/synapse_shield/static/synapse-sdk.js", "FREQUENT_DIGRAPHS") == py
    assert digraphs("synapse-shield-react/src/useSynapseShield.ts", "FREQUENT_DIGRAPHS") == py
    assert digraphs("synapse-shield-vue/src/useSynapseShield.ts", "FREQUENT_DIGRAPHS") == py
    assert digraphs("crates/synapse_core_rs/src/keystrokes.rs", "FREQUENT_DIGRAPHS") == py
    assert "da" not in py and "te" not in py
