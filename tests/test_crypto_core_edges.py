"""
Cryptographic layer (tokens.py) and decision pipeline (core.py) edge cases.

Focus: every branch that decides BLOCK vs ALLOW, plus input-shape robustness. A malformed token
must produce a clean 403 *and* a bot strike — never an unhandled exception (HTTP 500), which
would also skip strike/ban accounting and let an attacker probe without ever being quarantined.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import os
import secrets
import time

import pytest

from synapse_shield import core, tokens
from synapse_shield.storage import get_storage


def _b64(obj) -> str:
    raw = obj if isinstance(obj, str) else json.dumps(obj)
    return base64.b64encode(raw.encode()).decode()


def _signed_challenge(ts_ms: int, bind_hash: str | None = None) -> str:
    nonce = secrets.token_hex(16)  # not time-based: Windows clock ticks are coarse
    if bind_hash:
        sig = hmac.HMAC(tokens.SECRET_KEY, f"{nonce}:{ts_ms}:{bind_hash}".encode(), hashlib.sha256).hexdigest()
        return f"{nonce}.{ts_ms}.{bind_hash}.{sig}"
    sig = hmac.HMAC(tokens.SECRET_KEY, f"{nonce}:{ts_ms}".encode(), hashlib.sha256).hexdigest()
    return f"{nonce}.{ts_ms}.{sig}"


def _token(telemetry=None, ts_ms: int | None = None, **gen) -> str:
    ch = _signed_challenge(ts_ms) if ts_ms is not None else tokens.generate_challenge(**gen)["challenge"]
    return _b64({"challenge": ch, "telemetry": telemetry if telemetry is not None else {}})


# --------------------------------------------------------------------------------------------
# Malformed envelopes: 403 + strike, never an exception
# --------------------------------------------------------------------------------------------


MALFORMED_ENVELOPES = ["[]", "null", '"x"', "42", '{"challenge": 123}', '{"challenge": ["a"]}']


@pytest.mark.parametrize("raw", MALFORMED_ENVELOPES)
def test_malformed_envelope_is_rejected_not_crashed(raw):
    ok, reason, tel = tokens.verify_and_consume_token(_b64(raw))
    assert ok is False and tel == {}


@pytest.mark.parametrize(
    "telemetry",
    [[], "x", None, {"mouse_movements": "abc"}, {"mouse_movements": {"a": 1}}, {"clicks": None}, {"keystrokes": 5}],
)
def test_wrong_typed_telemetry_is_rejected_after_burning_nonce(telemetry):
    ch = tokens.generate_challenge()["challenge"]
    tok = _b64({"challenge": ch, "telemetry": telemetry})
    ok, reason, _ = tokens.verify_and_consume_token(tok)
    assert ok is False and "Malformed Telemetry" in reason
    # The challenge is burned: fixing the body and retrying with the same challenge is a replay.
    fixed = _b64({"challenge": ch, "telemetry": {}})
    ok, reason, _ = tokens.verify_and_consume_token(fixed)
    assert ok is False and "Replay" in reason


@pytest.mark.parametrize("raw", MALFORMED_ENVELOPES)
def test_malformed_envelope_records_strike_and_eventually_bans(raw):
    ip = "198.18.0.77"
    for _ in range(4):
        d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_b64(raw))
        assert d.status_code == 403 and d.allowed is False
    assert get_storage().is_ip_banned(ip), "malformed-token probing must lead to quarantine"
    get_storage().unban_ip(ip)


def test_http_score_endpoint_blocks_malformed_tokens_without_500():
    """/api/score reports verdicts in the JSON body; before the fix these raised HTTP 500."""
    from fastapi.testclient import TestClient

    from synapse_shield.main import app

    c = TestClient(app, raise_server_exceptions=False)
    for raw in MALFORMED_ENVELOPES:
        r = c.post("/api/score", json={"token": _b64(raw)})
        assert r.status_code != 500, (raw, r.text)
        assert r.json()["classification"] == "Bot", (raw, r.text)
        c.post("/api/clear", headers={"X-Admin-Secret": "pytest-secret"})


# --------------------------------------------------------------------------------------------
# Token verification branches
# --------------------------------------------------------------------------------------------


def test_token_size_type_and_structure_guards():
    assert tokens.verify_and_consume_token("A" * 70000)[0] is False
    assert tokens.verify_and_consume_token(None)[0] is False  # type: ignore[arg-type]
    assert "Base64" in tokens.verify_and_consume_token("%%%not-base64%%%")[1]
    assert "challenge" in tokens.verify_and_consume_token(_b64({"challenge": "a.b"}))[1].lower()
    assert "zaman" in tokens.verify_and_consume_token(_b64({"challenge": "n.notint.sig"}))[1].lower()


def test_forged_signatures_rejected_for_both_challenge_formats():
    now = int(time.time() * 1000)
    assert "Forged" in tokens.verify_and_consume_token(_b64({"challenge": f"n.{now}.deadbeef"}))[1]
    assert "Forged" in tokens.verify_and_consume_token(_b64({"challenge": f"n.{now}.bind.deadbeef"}))[1]


def test_client_binding_relay_and_strict_mode(monkeypatch):
    ch = tokens.generate_challenge(client_ip="203.0.113.5", user_agent="UA-1")["challenge"]
    tok = _b64({"challenge": ch, "telemetry": {}})
    ok, reason, _ = tokens.verify_and_consume_token(tok, client_ip="198.51.100.9", user_agent="UA-1")
    assert not ok and "Relay" in reason
    # Same /24 subnet + same UA (case-insensitive) is the same client.
    ch = tokens.generate_challenge(client_ip="203.0.113.5", user_agent="UA-1")["challenge"]
    ok, _, _ = tokens.verify_and_consume_token(_b64({"challenge": ch, "telemetry": {}}), "203.0.113.200", "ua-1")
    assert ok
    # Binding present but caller provides no client info -> relay rejection.
    ch = tokens.generate_challenge(client_ip="203.0.113.5", user_agent="UA-1")["challenge"]
    assert not tokens.verify_and_consume_token(_b64({"challenge": ch}))[0]

    monkeypatch.setenv("SYNAPSE_TOKEN_BINDING", "strict")
    ok, reason, _ = tokens.verify_and_consume_token(_token())
    assert not ok and "Strict" in reason


def test_time_checks(monkeypatch):
    now = int(time.time() * 1000)
    assert tokens.verify_and_consume_token(_token(ts_ms=now - 61_000))[1] == "TOKEN_EXPIRED"
    assert "Gelecek" in tokens.verify_and_consume_token(_token(ts_ms=now + 60_000))[1]

    monkeypatch.setenv("SYNAPSE_MIN_ELAPSED_MS", "1500")
    assert "Humanly Impossible" in tokens.verify_and_consume_token(_token(ts_ms=now))[1]

    base = now - 2000
    # Telemetry spanning longer than the token has existed -> time travel.
    tel = {"mouse_movements": [{"x": 0, "y": 0, "t": base - 9000}, {"x": 1, "y": 1, "t": base}]}
    assert "Time Travel" in tokens.verify_and_consume_token(_token(tel, ts_ms=base))[1]
    # Epoch timestamps from before the challenge was issued -> stale replayed telemetry.
    tel = {"clicks": [{"x": 0, "y": 0, "t": base - 6000}, {"x": 0, "y": 0, "t": base - 5900}]}
    assert "Stale" in tokens.verify_and_consume_token(_token(tel, ts_ms=base))[1]
    # Relative timestamps beyond elapsed time, or negative -> anomaly.
    tel = {"scrolls": [{"t": -5}, {"t": 10}]}
    assert "Relative" in tokens.verify_and_consume_token(_token(tel, ts_ms=base))[1]
    tel = {"keystrokes": [{"t": 1}, {"t": 1.0}, "not-a-dict", {"no_t": 1}]}
    assert tokens.verify_and_consume_token(_token(tel, ts_ms=base))[0] is True


@pytest.mark.parametrize("bad_t", ["123", float("nan"), float("inf")])
def test_non_numeric_event_timestamp_rejected(bad_t):
    raw = json.dumps({"challenge": tokens.generate_challenge()["challenge"], "telemetry": {"mouse_movements": [{"t": 0}]}})
    raw = raw.replace('"t": 0', f'"t": {json.dumps(bad_t) if isinstance(bad_t, str) else ("NaN" if bad_t != bad_t else "Infinity")}')
    ok, reason, _ = tokens.verify_and_consume_token(base64.b64encode(raw.encode()).decode())
    assert not ok and "TypeError" in reason


def test_client_subnet_normalisation():
    assert tokens.get_client_subnet(None) == "unknown_subnet"
    assert tokens.get_client_subnet("10.1.2.3") == "10.1.2.0"
    assert tokens.get_client_subnet("::ffff:10.1.2.3") == "10.1.2.0"
    assert tokens.get_client_subnet("2001:db8:1:2:3:4:5:6") == "2001:db8:1:2::"
    assert tokens.get_client_subnet(" not-an-ip ") == "not-an-ip"
    assert tokens.compute_client_binding_hash(None, None) == ""


# --------------------------------------------------------------------------------------------
# Secret key loading & nonce cleanup
# --------------------------------------------------------------------------------------------


def test_secret_key_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("SYNAPSE_SECRET_KEY", "00ff")
    assert tokens._load_or_generate_secret_key() == b"\x00\xff"
    monkeypatch.setenv("SYNAPSE_SECRET_KEY", "not hex!")
    assert tokens._load_or_generate_secret_key() == b"not hex!"

    monkeypatch.delenv("SYNAPSE_SECRET_KEY")
    monkeypatch.setattr(tokens.Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.warns(UserWarning, match="SYNAPSE_SECRET_KEY"):
        generated = tokens._load_or_generate_secret_key()
    key_file = tmp_path / ".synapse_shield" / "secret.key"
    assert key_file.read_text().encode() == generated
    assert tokens._load_or_generate_secret_key() == generated, "persisted key must be reused"


def test_secret_key_persisted_when_config_dir_already_exists(monkeypatch, tmp_path):
    """Mutation-testing finding: with mkdir(exist_ok=False) an existing ~/.synapse_shield/ made the
    write fail silently, so a NEW key was generated on every restart and every outstanding challenge
    became invalid. The key must be written and reused even when the directory already exists."""
    monkeypatch.delenv("SYNAPSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tokens.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / ".synapse_shield").mkdir()
    with pytest.warns(UserWarning):
        first = tokens._load_or_generate_secret_key()
    assert (tmp_path / ".synapse_shield" / "secret.key").exists()
    assert tokens._load_or_generate_secret_key() == first


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_secret_key_file_is_owner_only(monkeypatch, tmp_path):
    """Mutation-testing finding: nothing asserted the HMAC key file's mode (0o600)."""
    monkeypatch.delenv("SYNAPSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tokens.Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.warns(UserWarning):
        tokens._load_or_generate_secret_key()
    mode = (tmp_path / ".synapse_shield" / "secret.key").stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_db_path_honours_environment_variable(monkeypatch, tmp_path):
    """Mutation-testing finding: the SYNAPSE_DB_PATH variable name was never exercised (conftest
    always sets it before import), so a typo would silently fall back to the temp directory."""
    # Fresh interpreter: reloading the modules in-process would replace class objects and the
    # storage singleton that other tests hold references to.
    import subprocess
    import sys

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    probe = "import synapse_shield.tokens as t, synapse_shield.storage as s; print(t.DB_FILE); print(s.DB_FILE)"
    target = str(tmp_path / "custom.db")

    def db_files(env_value):
        env = {k: v for k, v in os.environ.items() if k != "SYNAPSE_DB_PATH"}
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        env["SYNAPSE_SECRET_KEY"] = "00" * 32
        if env_value is not None:
            env["SYNAPSE_DB_PATH"] = env_value
        out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        return out.stdout.split()

    assert db_files(target) == [target, target]
    default = db_files(None)
    assert all(p.endswith("synapse_shield.db") and p != target for p in default)


def test_python_nonce_cleanup_is_throttled(monkeypatch, tmp_path):
    """Cleanup runs at most every 30 s; otherwise every challenge would hit the DB with a DELETE."""
    import sqlite3

    import synapse_shield.storage as storage_mod

    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", False)
    calls = []
    real_connect = sqlite3.connect
    monkeypatch.setattr(tokens.sqlite3, "connect", lambda *a, **k: calls.append(a) or real_connect(*a, **k))
    monkeypatch.setattr(tokens, "DB_FILE", str(tmp_path / "throttle.db"))
    monkeypatch.setattr(tokens, "_last_cleanup_ts", time.time() - 10)
    tokens._cleanup_expired_nonces()
    assert calls == [], "within 30 s of the last cleanup nothing must run"
    monkeypatch.setattr(tokens, "_last_cleanup_ts", time.time() - 31)
    tokens._cleanup_expired_nonces()
    assert len(calls) == 1


def test_secret_key_unwritable_home_falls_back_to_ephemeral(monkeypatch, tmp_path):
    monkeypatch.delenv("SYNAPSE_SECRET_KEY", raising=False)
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    monkeypatch.setattr(tokens.Path, "home", classmethod(lambda cls: blocker))
    with pytest.warns(UserWarning):
        key = tokens._load_or_generate_secret_key()
    assert len(key) == 64


def test_secret_key_chmod_failure_is_tolerated(monkeypatch, tmp_path):
    monkeypatch.delenv("SYNAPSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(tokens.Path, "home", classmethod(lambda cls: tmp_path))

    def no_chmod(self, mode):
        raise OSError("chmod unsupported")

    monkeypatch.setattr(tokens.Path, "chmod", no_chmod)
    with pytest.warns(UserWarning):
        assert len(tokens._load_or_generate_secret_key()) == 64


def test_python_nonce_cleanup_without_rust(monkeypatch, tmp_path):
    import synapse_shield.storage as storage_mod

    db = tmp_path / "tok.db"
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", False)
    monkeypatch.setattr(tokens, "DB_FILE", str(db))
    monkeypatch.setattr(tokens, "_last_cleanup_ts", 0.0)
    import sqlite3

    with sqlite3.connect(db) as conn:
        tokens._ensure_table(conn)
        conn.execute("INSERT INTO used_nonces VALUES ('old', 1)")
    tokens._cleanup_expired_nonces()
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM used_nonces").fetchone()[0] == 0
    tokens._cleanup_expired_nonces()  # rate-limited second call

    monkeypatch.setattr(tokens, "_last_cleanup_ts", 0.0)
    monkeypatch.setattr(tokens, "DB_FILE", str(tmp_path))  # a directory -> connect fails, logged
    tokens._cleanup_expired_nonces()


# --------------------------------------------------------------------------------------------
# Proof of Work
# --------------------------------------------------------------------------------------------


def _solve(salt: str, difficulty: int) -> str:
    prefix = "0" * difficulty
    for n in itertools.count():
        if hashlib.sha256(f"{salt}{n}".encode()).hexdigest().startswith(prefix):
            return str(n)
    raise AssertionError  # pragma: no cover


def test_pow_salt_formats_and_tamper():
    salt = tokens.generate_pow_salt("10.0.0.1", difficulty=3)
    assert tokens.extract_pow_difficulty(salt) == 3
    assert tokens.verify_pow_salt(salt, "10.0.0.1")
    assert not tokens.verify_pow_salt(salt, "10.0.0.2"), "salt is IP-bound"
    s, ts, d, sig = salt.split(".")
    assert not tokens.verify_pow_salt(f"{s}.{ts}.1.{sig}", "10.0.0.1"), "difficulty downgrade must break the HMAC"
    assert not tokens.verify_pow_salt(f"{s}.x.{d}.{sig}")
    assert not tokens.verify_pow_salt("a.b")
    assert tokens.extract_pow_difficulty("a.b.x.d") == 4
    assert tokens.extract_pow_difficulty("legacy") == 4

    # Legacy 3-part salt (no difficulty field).
    now = int(time.time() * 1000)
    legacy_sig = hmac.HMAC(tokens.SECRET_KEY, f"abcd:{now}".encode(), hashlib.sha256).hexdigest()
    assert tokens.verify_pow_salt(f"abcd.{now}.{legacy_sig}")
    assert not tokens.verify_pow_salt(f"abcd.{now}.{'0' * 64}")
    assert not tokens.verify_pow_salt(f"abcd.nope.{legacy_sig}")

    old = now - 120_000
    old_sig = hmac.HMAC(tokens.SECRET_KEY, f"abcd:{old}".encode(), hashlib.sha256).hexdigest()
    assert not tokens.verify_pow_salt(f"abcd.{old}.{old_sig}"), "expired salt"


def test_pow_consume_is_single_use():
    salt = tokens.generate_pow_salt("10.0.0.9", difficulty=3)
    nonce = _solve(salt, 3)
    assert not tokens.verify_and_consume_pow("", nonce)
    assert not tokens.verify_and_consume_pow(salt, "")
    assert not tokens.verify_and_consume_pow(salt, nonce, client_ip="10.0.0.8")
    wrong = next(str(n) for n in itertools.count() if not hashlib.sha256(f"{salt}{n}".encode()).hexdigest().startswith("000"))
    assert not tokens.verify_and_consume_pow(salt, wrong, client_ip="10.0.0.9")
    assert tokens.verify_and_consume_pow(salt, nonce, client_ip="10.0.0.9")
    assert not tokens.verify_and_consume_pow(salt, nonce, client_ip="10.0.0.9"), "solved PoW cannot be replayed"


# --------------------------------------------------------------------------------------------
# core.py decision pipeline
# --------------------------------------------------------------------------------------------


def _fake_analysis(score: float, classification: str = "Human", **features):
    feat = {"total_interactive_events": 20, "mouse_points": 20, **features}

    def analyze(telemetry, *a, **k):
        return score, classification, ["fake"], {"features": feat, "threat_type": None}

    return analyze


def test_banned_ip_in_shadow_mode_is_reported_not_blocked():
    ip = "198.18.1.1"
    get_storage().ban_ip(ip, duration_sec=60)
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token="x", mode="shadow")
    assert d.allowed and d.action == "shadow_block" and d.reasons == ["IP_BANNED"]
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token="x")
    assert not d.allowed and d.status_code == 403
    get_storage().unban_ip(ip)


def test_token_error_in_shadow_mode_and_expired_tokens_do_not_strike():
    ip = "198.18.1.2"
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_b64("[]"), mode="shadow")
    assert d.allowed and d.headers["X-Synapse-Decision"] == "shadow-block"
    for _ in range(5):
        expired = _token(ts_ms=int(time.time() * 1000) - 120_000)  # fresh token each time
        d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=expired)
        assert d.reasons == ["TOKEN_TOKEN_EXPIRED"]
    assert get_storage().get_bot_strike_count(ip) == 1, "expired tokens (slow humans) must not add strikes"


def test_extreme_request_frequency_bans_ip(monkeypatch):
    ip = "198.18.1.3"
    monkeypatch.setenv("SYNAPSE_MAX_REQ_10S", "2")
    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(0.0))
    decisions = [core.evaluate_synapse_request_sync(client_ip=ip, user_agent="ua", token=_token()) for _ in range(3)]
    assert [d.allowed for d in decisions] == [True, True, False]
    assert "Extreme request frequency" in decisions[-1].error_message
    assert get_storage().is_ip_banned(ip)
    get_storage().unban_ip(ip)


@pytest.mark.parametrize("score,difficulty", [(40.0, 4), (50.0, 5)])
def test_gray_area_issues_risk_adaptive_pow_challenge(monkeypatch, score, difficulty):
    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(score))
    d = core.evaluate_synapse_request_sync(client_ip="198.18.2.1", user_agent="ua", token=_token(), enable_pow=True)
    assert d.status_code == 429 and d.action == "challenge"
    body = d.to_dict()
    assert body["status"] == "challenge_required" and body["pow_difficulty"] == difficulty
    assert tokens.extract_pow_difficulty(body["pow_salt"]) == difficulty
    assert d.headers["Retry-After"] == "2"


def test_gray_area_solved_pow_reduces_risk(monkeypatch):
    ip = "198.18.2.2"
    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(40.0))
    salt = tokens.generate_pow_salt(client_ip=ip, difficulty=4)
    nonce = _solve(salt, 4)
    d = core.evaluate_synapse_request_sync(
        client_ip=ip, user_agent="ua", token=_token(), enable_pow=True, pow_nonce=nonce, pow_salt=salt
    )
    assert d.allowed and d.bot_score == 20.0
    assert any("PoW Challenge successfully solved" in r for r in d.reasons)
    # Re-using the same solution falls back to a fresh challenge.
    d = core.evaluate_synapse_request_sync(
        client_ip=ip, user_agent="ua", token=_token(), enable_pow=True, pow_nonce=nonce, pow_salt=salt
    )
    assert d.status_code == 429


@pytest.mark.parametrize(
    "features",
    [
        {"total_interactive_events": 0},
        {"mouse_points": 2, "total_interactive_events": 2},
        {"is_stealth_automation": True},
    ],
)
def test_hard_bot_signals_never_get_a_pow_escape_hatch(monkeypatch, features):
    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(40.0, **features))
    d = core.evaluate_synapse_request_sync(client_ip="198.18.2.3", user_agent="ua", token=_token(), enable_pow=True)
    assert d.status_code != 429, "hard bot violations must not be offered a solvable challenge"


def test_gray_area_in_shadow_mode_skips_challenge(monkeypatch):
    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(40.0))
    d = core.evaluate_synapse_request_sync(
        client_ip="198.18.2.4", user_agent="ua", token=_token(), enable_pow=True, mode="shadow", max_risk_score=30.0
    )
    assert d.allowed and d.action == "shadow_block" and d.to_dict()["simulated_action"] == "block"


def test_pow_enabled_via_environment(monkeypatch):
    monkeypatch.setenv("SYNAPSE_ENABLE_POW", "true")
    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(40.0))
    d = core.evaluate_synapse_request_sync(client_ip="198.18.2.5", user_agent="ua", token=_token())
    assert d.status_code == 429


def test_shadow_allow_and_metrics_counters(monkeypatch):
    pytest.importorskip("prometheus_client")
    from synapse_shield import metrics

    monkeypatch.setattr(core, "METRICS_ENABLED", True)
    for name in ("synapse_requests_total", "synapse_shadow_requests_total", "synapse_replays_detected_total",
                 "synapse_pow_solved_total", "synapse_inference_latency_seconds"):
        monkeypatch.setattr(core, name, getattr(metrics, name))

    def sample(counter, **labels):
        return counter.labels(**labels)._value.get() if labels else counter._value.get()

    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(5.0))
    before = sample(metrics.synapse_shadow_requests_total, action="allow", classification="Human")
    d = core.evaluate_synapse_request_sync(client_ip="198.18.3.1", user_agent="ua", token=_token(), mode="shadow")
    assert d.allowed and d.to_dict()["simulated_action"] == "allow"
    assert sample(metrics.synapse_shadow_requests_total, action="allow", classification="Human") == before + 1

    before = sample(metrics.synapse_replays_detected_total)
    tok = _token()
    core.evaluate_synapse_request_sync(client_ip="198.18.3.2", user_agent="ua", token=tok)
    core.evaluate_synapse_request_sync(client_ip="198.18.3.2", user_agent="ua", token=tok)
    assert sample(metrics.synapse_replays_detected_total) == before + 1

    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(90.0, "Bot"))
    before = sample(metrics.synapse_requests_total, status="block", classification="Bot")
    core.evaluate_synapse_request_sync(client_ip="198.18.3.3", user_agent="ua", token=_token())
    assert sample(metrics.synapse_requests_total, status="block", classification="Bot") == before + 1

    for mode, tok in (("shadow", None), ("shadow", _b64("[]"))):
        core.evaluate_synapse_request_sync(client_ip="198.18.3.4", user_agent="ua", token=tok, mode=mode)
    get_storage().ban_ip("198.18.3.5")
    core.evaluate_synapse_request_sync(client_ip="198.18.3.5", user_agent="ua", token="x", mode="shadow")
    core.evaluate_synapse_request_sync(client_ip="198.18.3.6", user_agent="ua", token=_token(), mode="shadow")

    monkeypatch.setattr(core, "analyze_behavior", _fake_analysis(40.0))
    salt = tokens.generate_pow_salt(client_ip="198.18.3.7", difficulty=4)
    before = sample(metrics.synapse_pow_solved_total)
    core.evaluate_synapse_request_sync(client_ip="198.18.3.7", user_agent="ua", token=_token(), enable_pow=True,
                                       pow_nonce=_solve(salt, 4), pow_salt=salt)
    assert sample(metrics.synapse_pow_solved_total) == before + 1
    get_storage().unban_ip("198.18.3.5")


def test_decision_serialisation_variants():
    d = core.SynapseDecision(allowed=False, action="challenge")
    assert d.to_dict()["pow_difficulty"] == 4 and d.to_dict()["pow_salt"] == ""
    d = core.SynapseDecision(allowed=True, shadow_mode=True, action="allow")
    assert "reasons" not in d.to_dict()


@pytest.mark.parametrize(
    "mode,ip,expected",
    [
        ("hash", "203.0.113.1", "anon_"),
        ("strict", "::ffff:203.0.113.1", "203.0.113.*"),
        ("strict", "2001:db8::1", "2001:0db8:0000:0000:*:*:*:*"),
    ],
)
def test_anonymize_ip_modes(monkeypatch, mode, ip, expected):
    monkeypatch.setenv("SYNAPSE_PRIVACY_MODE", mode)
    out = core.anonymize_ip(ip)
    assert out.startswith(expected) and "203.0.113.1" not in out


class _MappingHeaders:
    """Mapping-like header object (Starlette/Werkzeug/Django style): has .get but is not a dict."""

    def __init__(self, data):
        self._d = data

    def get(self, key, default=None):
        return self._d.get(key, default)


ATTACKER = "6.6.6.6"


@pytest.mark.parametrize(
    "peer,trusted,headers,expected",
    [
        # --- Anti-spoofing: an untrusted peer's forwarding headers are ignored --------------------
        # Loopback peer is NOT trusted unless loopback is in the trusted set (mutmut core #14).
        ("127.0.0.1", {"10.0.0.0/8"}, {"x-forwarded-for": ATTACKER}, "127.0.0.1"),
        ("::1", {"10.0.0.0/8"}, {"cf-connecting-ip": ATTACKER}, "::1"),
        ("192.0.2.11", {"192.0.2.10"}, {"x-real-ip": ATTACKER}, "192.0.2.11"),  # exact entry, other IP (#33)
        ("11.0.0.1", {"10.1.2.3/8"}, {"x-real-ip": ATTACKER}, "11.0.0.1"),
        # --- Trusted peers --------------------------------------------------------------------
        ("127.0.0.1", {"127.0.0.1"}, {"x-real-ip": "1.2.3.4"}, "1.2.3.4"),
        ("::1", {"::1"}, {"x-real-ip": "1.2.3.4"}, "1.2.3.4"),
        ("127.0.0.1", {"localhost"}, {"x-real-ip": "1.2.3.4"}, "1.2.3.4"),
        ("192.0.2.10", {"192.0.2.10"}, {"x-real-ip": "1.2.3.4"}, "1.2.3.4"),  # exact entry (#33)
        ("10.9.9.9", {"10.1.2.3/8"}, {"x-real-ip": "1.2.3.4"}, "1.2.3.4"),  # CIDR with host bits (#29)
        (None, {"127.0.0.1"}, {"x-real-ip": "1.2.3.4"}, "1.2.3.4"),  # missing peer = local (#42)
        # --- Header priority: CF-Connecting-IP > X-Real-IP > X-Forwarded-For -------------------
        ("10.0.0.1", {"10.0.0.0/8"}, {"cf-connecting-ip": "1.1.1.1", "x-real-ip": "2.2.2.2", "x-forwarded-for": "3.3.3.3"}, "1.1.1.1"),
        ("10.0.0.1", {"10.0.0.0/8"}, {"x-real-ip": "2.2.2.2", "x-forwarded-for": "3.3.3.3"}, "2.2.2.2"),
        ("10.0.0.1", {"10.0.0.0/8"}, {"cf-connecting-ip": "not-an-ip", "x-real-ip": "2.2.2.2"}, "2.2.2.2"),
        # --- Header spellings -----------------------------------------------------------------
        ("10.0.0.1", {"10.0.0.0/8"}, {"X_Forwarded_For": "3.3.3.3"}, "3.3.3.3"),  # WSGI-style key (#47)
        ("10.0.0.1", {"10.0.0.0/8"}, {"HTTP_X_FORWARDED_FOR": "3.3.3.3"}, "3.3.3.3"),  # Django META in dict
        ("10.0.0.1", {"10.0.0.0/8"}, _MappingHeaders({"cf-connecting-ip": "1.1.1.1"}), "1.1.1.1"),
        ("10.0.0.1", {"10.0.0.0/8"}, _MappingHeaders({"X-REAL-IP": "2.2.2.2"}), "2.2.2.2"),
        ("10.0.0.1", {"10.0.0.0/8"}, _MappingHeaders({"HTTP_X_FORWARDED_FOR": "3.3.3.3"}), "3.3.3.3"),
        ("10.0.0.1", {"10.0.0.0/8"}, _MappingHeaders({"x-real-ip": "", "x-forwarded-for": "3.3.3.3"}), "3.3.3.3"),
        ("10.0.0.1", {"10.0.0.0/8"}, [(b"cf-connecting-ip", b"1.1.1.1")], "1.1.1.1"),
        ("10.0.0.1", {"10.0.0.0/8"}, [("X-Real-IP", "2.2.2.2")], "2.2.2.2"),
        ("10.0.0.1", {"10.0.0.0/8"}, object(), "10.0.0.1"),  # unknown header container
    ],
)
def test_resolve_client_ip_matrix(peer, trusted, headers, expected):
    assert core.resolve_client_ip(peer, headers, trusted) == expected


def test_resolve_client_ip_proxy_rules():
    trusted = {"10.0.0.0/8", "localhost", "", "bogus/cidr", "proxy.internal"}
    # Untrusted peer: headers are ignored (anti-spoofing).
    assert core.resolve_client_ip("8.8.8.8", {"x-forwarded-for": "1.1.1.1"}, trusted) == "8.8.8.8"
    # Trusted peer: right-most untrusted XFF hop wins.
    assert core.resolve_client_ip("10.1.1.1", {"x-forwarded-for": "1.1.1.1, 2.2.2.2, 10.9.9.9"}, trusted) == "2.2.2.2"
    # All hops trusted -> right-most valid hop.
    assert core.resolve_client_ip("10.1.1.1", {"x-forwarded-for": "10.2.2.2, junk"}, trusted) == "10.2.2.2"
    # ASGI raw header list form and loopback via "localhost".
    hdrs = [(b"x-real-ip", b"5.5.5.5"), ("bad",)]
    assert core.resolve_client_ip("127.0.0.1", hdrs, trusted) == "5.5.5.5"
    # Hostname-style trusted entry; invalid IPs never trusted by CIDR.
    assert core._is_ip_in_trusted("proxy.internal", trusted)
    assert not core._is_ip_in_trusted("", trusted)
    assert not core._is_valid_ip("")
    assert core.get_trusted_proxies() >= {"127.0.0.1"}
