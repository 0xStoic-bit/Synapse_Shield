"""
Server-side Zero-PII guard (privacy.py).

Legacy SDKs (< 0.10.5) and hand-rolled clients send typed characters in clear text. After token
verification no layer may see them: not the scoring engine, not the application handler
(request.state.synapse_telemetry), not the dataset store. The digraph signal must survive masking.
"""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest
from fastapi import Request as FastAPIRequest

from synapse_shield import privacy, tokens
from synapse_shield.features import extract_features

SECRET = "Ş1fre-Gizli_42!ğüİ😀"


def _legacy_keystrokes(text: str, typed: bool = True, start: float = 1000.0) -> list[dict]:
    """Keystrokes as pre-0.10.4 SDKs sent them: the lower-cased character itself."""
    out, t = [], start
    for i, ch in enumerate(text):
        key = ch.lower()
        if typed:
            out.append({"type": "down", "key": key, "t": t})
            out.append({"type": "up", "key": key, "t": t + 80 + i % 7, "duration_ms": 80 + i % 7})
        else:
            out.append({"key": key, "t": t, "up": t + 80 + i % 7})
        t += 120 + (i * 37) % 90
    return out


def _all_keys(keystrokes) -> set[str]:
    return {k["key"] for k in keystrokes}


@pytest.mark.parametrize("typed", [True, False])
def test_raw_characters_are_masked(typed):
    cleaned = privacy.sanitize_keystrokes(_legacy_keystrokes(SECRET, typed))
    assert _all_keys(cleaned) == {"masked"}
    blob = json.dumps(cleaned, ensure_ascii=False)
    for ch in set(SECRET.lower()):
        assert f'"{ch}"' not in blob


def test_named_keys_survive_and_input_is_not_mutated():
    ks = [{"type": "down", "key": k, "t": i * 100.0} for i, k in enumerate(["Enter", "arrowleft", "a", "Unidentified", "F1", "masked", "", None])]
    before = json.dumps(ks)
    cleaned = privacy.sanitize_keystrokes(ks)
    assert [k["key"] for k in cleaned] == ["Enter", "arrowleft", "masked", "Unidentified", "F1", "masked", "unknown", "unknown"]
    assert json.dumps(ks) == before, "caller's telemetry must not be modified"


def test_current_sdk_payload_is_returned_untouched():
    ks = [{"type": "down", "key": "masked", "t": 1.0, "is_freq_digraph": True}, {"type": "down", "key": "enter", "t": 2.0}]
    assert privacy.sanitize_keystrokes(ks) is ks
    assert privacy.sanitize_keystrokes("not-a-list") == "not-a-list"
    tel = {"keystrokes": ks}
    assert privacy.sanitize_telemetry(tel) is tel
    assert privacy.sanitize_telemetry([]) == []


def test_digraph_flag_is_derived_like_the_sdk():
    cleaned = privacy.sanitize_keystrokes(_legacy_keystrokes("then"))
    downs = [k for k in cleaned if k["type"] == "down"]
    ups = [k for k in cleaned if k["type"] == "up"]
    # t-h (th), h-e (he), e-n (en) are all frequent digraphs; the first key has no predecessor.
    assert [k["is_freq_digraph"] for k in downs] == [False, True, True, True]
    assert [k["is_freq_digraph"] for k in ups] == [False, True, True, True], "keyup inherits its keydown flag"
    cleaned = privacy.sanitize_keystrokes(_legacy_keystrokes("xq"))
    assert all(k["is_freq_digraph"] is False for k in cleaned)


def test_client_supplied_flag_is_kept():
    ks = [{"type": "down", "key": "t", "t": 0.0, "is_freq_digraph": True}, {"type": "down", "key": "h", "t": 100.0, "is_freq_digraph": False}]
    assert [k["is_freq_digraph"] for k in privacy.sanitize_keystrokes(ks)] == [True, False]


def test_masking_keeps_the_digraph_signal_for_scoring():
    """Raw 'th'/'he' faster than rare pairs: a human. The verdict must be the same after masking."""
    text = "thexqthezvthe"
    ks, t = [], 1000.0
    for i, ch in enumerate(text):
        ks.append({"type": "down", "key": ch, "t": t})
        ks.append({"type": "up", "key": ch, "t": t + 70 + (i % 4) * 11, "duration_ms": 70 + (i % 4) * 11})
        nxt = text[i + 1] if i + 1 < len(text) else ""
        t += 90 + (i % 3) * 7 if (ch + nxt) in privacy.FREQUENT_DIGRAPHS else 260 + (i % 3) * 23
    tel = {"mouse_movements": [], "clicks": [], "scrolls": [], "keystrokes": ks, "browser": {}}
    raw = extract_features(tel, force_python=True)["keystroke_score"]
    masked = extract_features(privacy.sanitize_telemetry(tel), force_python=True)["keystroke_score"]
    rust = extract_features(privacy.sanitize_telemetry(tel))["keystroke_score"]
    assert masked == pytest.approx(raw, abs=1e-6)
    assert rust == pytest.approx(masked, abs=1e-4)


def test_verified_token_telemetry_never_contains_raw_text():
    ch = tokens.generate_challenge()["challenge"]
    tel = {"keystrokes": _legacy_keystrokes(SECRET), "mouse_movements": []}
    tok = base64.b64encode(json.dumps({"challenge": ch, "telemetry": tel}).encode()).decode()
    ok, _, out = tokens.verify_and_consume_token(tok)
    assert ok
    assert _all_keys(out["keystrokes"]) == {"masked"}


def test_framework_handler_receives_masked_telemetry():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse_shield.middleware import SynapseShieldMiddleware

    app = FastAPI()
    seen = {}

    async def handler(request: FastAPIRequest):
        seen["tel"] = request.state.synapse_telemetry
        return {"ok": True}

    app.add_api_route("/api/login", handler, methods=["POST"])
    app.add_middleware(SynapseShieldMiddleware, protected_paths=["/api"], mode="shadow")
    tel = {
        "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
        "mouse_movements": [{"x": 100 + i, "y": 100 + i, "t": i * 20 + (i * 7) % 5} for i in range(20)],
        "keystrokes": [{"key": c, "t": 10 + i * 30, "up": 60 + i * 30} for i, c in enumerate("parola")],
    }
    tok = base64.b64encode(json.dumps({"challenge": tokens.generate_challenge()["challenge"], "telemetry": tel}).encode()).decode()
    assert TestClient(app).post("/api/login", json={"token": tok}).status_code == 200
    assert _all_keys(seen["tel"]["keystrokes"]) == {"masked"}


def test_dataset_store_never_persists_raw_text():
    from fastapi.testclient import TestClient

    from synapse_shield import main

    r = TestClient(main.app).post(
        "/api/collect_dataset",
        json={"keystrokes": _legacy_keystrokes(SECRET)},
        headers={"X-Admin-Secret": "pytest-secret"},
    )
    assert r.status_code == 200
    conn = main.get_dataset_connection()
    row = conn.execute("SELECT keystrokes FROM raw_telemetry ORDER BY id DESC LIMIT 1").fetchone()
    stored = json.loads(row[0])
    assert _all_keys(stored) == {"masked"}
    assert isinstance(conn, sqlite3.Connection)
