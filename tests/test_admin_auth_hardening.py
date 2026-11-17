"""Acik #15 / #16: admin authentication must never 500 and must tell the operator (not the caller) why it failed.

#15  hmac.compare_digest(str, str) raises TypeError when either str has non-ASCII characters. Starlette decodes
     header values as latin-1, so a header byte >= 0x80 used to turn into HTTP 500 on every admin endpoint.
#16  Every failure returns the same generic 401 body; the server log carries the cause
     ("SYNAPSE_ADMIN_SECRET not configured" vs "invalid admin secret").
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from synapse_shield import main as main_mod

SECRET = "s3cret-admin-value"
GENERIC = {"detail": "Unauthorized: Invalid admin secret"}
ADMIN_GETS = ["/metrics", "/metrics/prometheus"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("SYNAPSE_DEV_MODE", raising=False)
    monkeypatch.setattr(main_mod, "_admin_not_configured_logged", False)
    return TestClient(main_mod.app, client=("203.0.113.9", 50000), raise_server_exceptions=False)


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Admin-Secret": "s3cret-ädmin"},
        {"Authorization": "Bearer s3cret-ädmin"},
        {"X-Admin-Secret": "ünïcödé"},
    ],
)
def test_non_ascii_admin_header_is_401_not_500(client, monkeypatch, headers):
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", SECRET)
    encoded = {k: v.encode("utf-8") for k, v in headers.items()}  # raw bytes on the wire, >= 0x80
    r = client.post("/api/clear", headers=encoded)
    assert r.status_code == 401 and r.json() == GENERIC
    for path in ADMIN_GETS:
        assert client.get(path, headers=encoded).status_code == 401


def test_non_ascii_configured_secret_still_works(client, monkeypatch):
    """Both sides are compared as UTF-8 bytes, so a non-ASCII secret is usable when sent as UTF-8."""
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", "geheim-ß")
    assert main_mod._admin_secret_matches("geheim-ß", "geheim-ß") is True
    assert main_mod._admin_secret_matches("geheim-ss", "geheim-ß") is False
    assert main_mod._admin_secret_matches(None, "geheim-ß") is False
    assert main_mod._admin_secret_matches("x", None) is False


def test_bearer_prefix_is_checked_not_stripped_anywhere(client, monkeypatch):
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", SECRET)
    assert client.post("/api/clear", headers={"Authorization": f"Bearer {SECRET}"}).status_code == 200
    assert client.post("/api/clear", headers={"X-Admin-Secret": SECRET}).status_code == 200
    # .replace("Bearer ", "") accepted these; a prefix check does not.
    assert client.post("/api/clear", headers={"Authorization": SECRET}).status_code == 401
    assert client.post("/api/clear", headers={"Authorization": f"Basic Bearer {SECRET}"}).status_code == 401
    assert client.post("/api/clear", headers={"Authorization": f"Bearer Bearer {SECRET}"}).status_code == 401


def test_not_configured_is_logged_but_response_is_identical(client, monkeypatch, caplog):
    monkeypatch.delenv("SYNAPSE_ADMIN_SECRET", raising=False)
    with caplog.at_level(logging.DEBUG, logger="synapse_shield.main"):
        unset = client.post("/api/clear", headers={"X-Admin-Secret": "anything"})
        client.post("/api/clear", headers={"X-Admin-Secret": "anything"})
    assert unset.status_code == 401 and unset.json() == GENERIC
    msgs = [r for r in caplog.records if "SYNAPSE_ADMIN_SECRET not configured" in r.getMessage()]
    assert len(msgs) == 2
    assert msgs[0].levelno == logging.WARNING and msgs[1].levelno == logging.DEBUG, "loud once, then quiet"
    assert "203.0.113.9" not in msgs[0].getMessage(), "client IP is anonymised in the log"

    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", SECRET)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="synapse_shield.main"):
        wrong = client.post("/api/clear", headers={"X-Admin-Secret": "wrong"})
        missing = client.post("/api/clear")
    assert wrong.json() == unset.json() == missing.json() == GENERIC
    assert wrong.headers.get("content-length") == unset.headers.get("content-length")
    text = " | ".join(r.getMessage() for r in caplog.records)
    assert "invalid admin secret" in text and "missing admin secret" in text
    assert "wrong" not in text and SECRET not in text, "the provided or real secret never reaches the log"


def test_websocket_terminal_non_ascii_token_is_rejected_cleanly(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", SECRET)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/terminal?token=%C3%BCn%C3%AFc", headers={"origin": "http://testserver", "host": "testserver"}
        ) as ws:
            ws.receive_text()
