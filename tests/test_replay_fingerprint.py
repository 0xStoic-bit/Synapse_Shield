"""#39-A single-request trajectory replay: keyed delta fingerprint, consumed only on the allow path.

Real engine, real SQLite storage, fakeredis for Redis semantics. No mocked verdicts.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import random
import sqlite3
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from synapse_shield import adversarial as adv
from synapse_shield import core, fingerprint, tokens
from synapse_shield import storage as storage_mod
from synapse_shield.storage import RedisStorageBackend, SQLiteStorageBackend, StorageBackend, client_strike_key, set_storage

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _human(seed: int = 7) -> dict:
    random.seed(seed)
    np.random.seed(seed)
    return adv.generate_synthetic_human_telemetry()


def _shift_time(tel: dict, ms: int) -> dict:
    tel = copy.deepcopy(tel)
    for key in ("mouse_movements", "clicks", "scrolls"):
        for e in tel.get(key, []):
            if "t" in e:
                e["t"] += ms
    return tel


def _translate(tel: dict, dx: int, dy: int) -> dict:
    tel = copy.deepcopy(tel)
    for e in tel["mouse_movements"]:
        e["x"] += dx
        e["y"] += dy
    return tel


def _token(telemetry, ip, ua=UA):
    challenge = tokens.generate_challenge(client_ip=ip, user_agent=ua)["challenge"]
    return base64.b64encode(json.dumps({"challenge": challenge, "telemetry": telemetry}).encode()).decode()


def _solve(salt: str, difficulty: int) -> str:
    target = "0" * difficulty
    n = 0
    while not hashlib.sha256((salt + str(n)).encode()).hexdigest().startswith(target):
        n += 1
    return str(n)


# ---------------------------------------------------------------- pure functions
def test_fingerprint_is_deterministic_keyed_and_opaque():
    tel = _human()
    a = fingerprint.trajectory_fingerprint(tel, secret_key=b"k1")
    assert a == fingerprint.trajectory_fingerprint(copy.deepcopy(tel), secret_key=b"k1")
    assert a.startswith("t_") and len(a) == 18
    int(a[2:], 16)
    assert fingerprint.trajectory_fingerprint(tel, secret_key=b"k2") != a


def test_time_shift_and_translation_keep_the_fingerprint():
    tel = _human()
    fp = fingerprint.trajectory_fingerprint(tel, secret_key=b"k")
    assert fingerprint.trajectory_fingerprint(_shift_time(tel, 1_700_000_000_000), secret_key=b"k") == fp
    assert fingerprint.trajectory_fingerprint(_translate(tel, 300, -120), secret_key=b"k") == fp


def test_one_pixel_change_changes_the_fingerprint():
    # Known limit of an exact hash (documented): 1 px noise defeats it.
    tel = _human()
    tel2 = copy.deepcopy(tel)
    tel2["mouse_movements"][10]["x"] += 1
    assert fingerprint.trajectory_fingerprint(tel, secret_key=b"k") != fingerprint.trajectory_fingerprint(tel2, secret_key=b"k")


def test_different_humans_differ():
    fps = {fingerprint.trajectory_fingerprint(_human(s), secret_key=b"k") for s in range(30)}
    assert len(fps) == 30


@pytest.mark.parametrize(
    "tel",
    [
        None,
        {},
        {"mouse_movements": "x"},
        {"mouse_movements": [{"x": i, "y": i, "t": i * 16} for i in range(19)]},  # < 20 points
        {"mouse_movements": [{"x": 100 + (i % 2), "y": 100, "t": i * 16} for i in range(40)]},  # tiny path
        {"mouse_movements": [{"x": i * 10, "y": 0, "t": i * 16} for i in range(40)]},  # 1 distinct delta
        {"mouse_movements": [{"x": "a", "y": 0, "t": 0}] * 30},
        {"mouse_movements": [{"x": float("nan"), "y": 0, "t": 0}] * 30},
        {"mouse_movements": [{"x": True, "y": 0, "t": 0}] * 30},
    ],
)
def test_entropy_gate_and_malformed_input_return_none(tel):
    assert fingerprint.trajectory_fingerprint(tel, secret_key=b"k") is None


def test_default_key_is_the_token_secret():
    tel = _human()
    assert fingerprint.trajectory_fingerprint(tel) == fingerprint.trajectory_fingerprint(tel, secret_key=tokens.SECRET_KEY)


# ---------------------------------------------------------------- storage
fakeredis = pytest.importorskip("fakeredis")


class _BrokenRedis:
    def __getattr__(self, name):
        def boom(*a, **k):
            raise ConnectionError("redis down")

        return boom


@pytest.fixture
def sqlite_backend(tmp_path):
    b = SQLiteStorageBackend(db_path=str(tmp_path / "fp.db"))
    yield b
    b.close()


@pytest.fixture
def redis_backend(tmp_path):
    fb = SQLiteStorageBackend(db_path=str(tmp_path / "fp_fb.db"))
    yield RedisStorageBackend("redis://fake:6379/0", client=fakeredis.FakeRedis(decode_responses=True), fallback=fb)
    fb.close()


@pytest.fixture(params=["sqlite", "redis"])
def backend(request, sqlite_backend, redis_backend):
    return sqlite_backend if request.param == "sqlite" else redis_backend


def test_consume_first_true_then_false(backend):
    assert backend.consume_trajectory_fp("t_aaaa", 3600) is True
    assert backend.consume_trajectory_fp("t_aaaa", 3600) is False
    assert backend.consume_trajectory_fp("t_bbbb", 3600) is True


def test_clear_all_forgets_fingerprints(backend):
    backend.consume_trajectory_fp("t_cccc", 3600)
    backend.clear_all()
    assert backend.consume_trajectory_fp("t_cccc", 3600) is True


def test_sqlite_expired_fingerprint_is_new_again_and_purged(sqlite_backend):
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        conn.execute("INSERT INTO trajectory_fps (fp, expires_at) VALUES (?, ?)", ("t_old", time.time() - 5))
        conn.execute("INSERT INTO trajectory_fps (fp, expires_at) VALUES (?, ?)", ("t_other_old", time.time() - 5))
    sqlite_backend._last_trajectory_fp_purge = 0.0
    assert sqlite_backend.consume_trajectory_fp("t_old", 3600) is True
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        rows = {r[0] for r in conn.execute("SELECT fp FROM trajectory_fps")}
    assert rows == {"t_old"}  # periodic purge removed the other expired row


def test_redis_key_has_ttl(redis_backend):
    redis_backend.consume_trajectory_fp("t_ttl", 3600)
    ttl = redis_backend.client.ttl("synapse:trajfp:t_ttl")
    assert 3500 < ttl <= 3600


def test_redis_outage_falls_back_to_sqlite_same_key(tmp_path):
    fb = SQLiteStorageBackend(db_path=str(tmp_path / "out.db"))
    try:
        b = RedisStorageBackend("redis://down", client=_BrokenRedis(), fallback=fb)
        assert b.consume_trajectory_fp("t_dd", 3600) is True
        assert b.consume_trajectory_fp("t_dd", 3600) is False
        assert fb.consume_trajectory_fp("t_dd", 3600) is False
    finally:
        fb.close()


def test_third_party_backend_gets_process_local_default():
    class Minimal(StorageBackend):
        def consume_nonce(self, nonce, ttl_sec=120): return True
        def is_ip_banned(self, ip): return False
        def ban_ip(self, ip, duration_sec=900, reason=""): pass
        def unban_ip(self, ip): pass
        def record_and_get_request_count(self, ip, window_sec=10): return 1
        def record_bot_strike(self, ip, threshold=4, window_sec=60, ban_duration_sec=60, reason=""): pass
        def get_bot_strike_count(self, ip, window_sec=60): return 0
        def clear_all(self): pass
        def record_session_telemetry(self, *a, **k): pass
        def get_session_telemetries(self, *a, **k): return []

    try:
        m = Minimal()
    except TypeError as e:  # interface grew another abstract method; this test only covers the fp default
        pytest.skip(str(e))
    assert m.consume_trajectory_fp("t_x", 3600) is True
    assert m.consume_trajectory_fp("t_x", 3600) is False


def test_sqlite_stores_no_raw_trajectory(sqlite_backend):
    tel = _human()
    fp = fingerprint.trajectory_fingerprint(tel)
    sqlite_backend.consume_trajectory_fp(fp, 3600)
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        rows = conn.execute("SELECT * FROM trajectory_fps").fetchall()
    assert rows and all(len(r) == 2 for r in rows)
    assert rows[0][0] == fp


# ---------------------------------------------------------------- core end to end
@pytest.fixture
def store(tmp_path, monkeypatch):
    for k in ("SYNAPSE_ENABLE_POW", "SYNAPSE_KEYBOARD_ONLY_CHALLENGE", "SYNAPSE_TRAJECTORY_REPLAY"):
        monkeypatch.delenv(k, raising=False)
    previous = storage_mod._global_storage
    backend = SQLiteStorageBackend(db_path=str(tmp_path / "core_fp.db"))
    set_storage(backend)
    try:
        yield backend
    finally:
        set_storage(previous)
        backend.close()


def _eval(tel, ip, ua=UA, **kw):
    return core.evaluate_synapse_request_sync(client_ip=ip, user_agent=ua, token=_token(tel, ip, ua), **kw)


def test_core_replay_from_new_ip_and_new_ua_is_blocked(store):
    tel = _human()
    first = _eval(tel, "198.51.100.1")
    assert first.action == "allow"
    again = _eval(_translate(_shift_time(tel, 777), 40, 25), "203.0.113.9", ua=UA.replace("131", "132"))
    assert again.action == "block" and again.status_code == 403
    assert core.TRAJECTORY_REPLAY_REASON in again.reasons
    # IP strike only, no per-device penalty (same policy as token replay)
    assert store.get_bot_strike_count("203.0.113.9", 60) == 1
    assert store.get_client_strike_count(client_strike_key("203.0.113.9", UA.replace("131", "132")), 60) == 0


def test_core_blocked_request_does_not_consume(store):
    tel = _human()
    # a penalized device (+50) without PoW is blocked -> fingerprint not consumed
    store.record_client_strike(client_strike_key("198.51.100.2", UA), 60)
    blocked = _eval(tel, "198.51.100.2", max_risk_score=50.0)
    assert blocked.action == "block"
    assert core.TRAJECTORY_REPLAY_REASON not in blocked.reasons
    assert _eval(tel, "198.51.100.3").action == "allow"


def test_core_shadow_mode_reports_but_does_not_block(store):
    tel = _human()
    assert _eval(tel, "198.51.100.4", mode="shadow").action == "allow"
    d = _eval(tel, "198.51.100.5", mode="shadow")
    assert d.allowed and d.action == "shadow_block"
    assert core.TRAJECTORY_REPLAY_REASON in d.reasons


def test_core_kill_switch(store, monkeypatch):
    monkeypatch.setenv("SYNAPSE_TRAJECTORY_REPLAY", "0")
    tel = _human()
    assert _eval(tel, "198.51.100.6").action == "allow"
    assert _eval(tel, "198.51.100.7").action == "allow"


def test_core_low_entropy_input_is_not_fingerprinted(store, monkeypatch):
    calls = []
    real = store.consume_trajectory_fp
    monkeypatch.setattr(store, "consume_trajectory_fp", lambda fp, ttl_sec=3600: calls.append(fp) or real(fp, ttl_sec))
    tel = _human()
    tel["mouse_movements"] = tel["mouse_movements"][:15]
    _eval(tel, "198.51.100.8")
    assert calls == []


def test_core_sdk_pow_retry_is_not_a_replay(store):
    """SDK flow: 429 challenge -> same events, time-shifted, new token + PoW -> ALLOW; then a re-send -> REPLAY."""
    ip = "198.51.100.10"
    store.record_client_strike(client_strike_key(ip, UA), 60)  # +50 -> gray area 50
    tel = _human()
    first = _eval(tel, ip, enable_pow=True)
    assert first.action == "challenge" and first.status_code == 429
    salt = first.challenge_data["pow_salt"]
    nonce = _solve(salt, first.challenge_data["pow_difficulty"])
    retry = _eval(_shift_time(tel, 2100), ip, enable_pow=True, pow_salt=salt, pow_nonce=nonce)
    assert retry.action == "allow", retry.reasons
    replay = _eval(_shift_time(tel, 9000), "203.0.113.20", enable_pow=True)
    assert replay.action == "block" and core.TRAJECTORY_REPLAY_REASON in replay.reasons


def test_core_expired_token_retry_is_not_a_replay(store, monkeypatch):
    ip = "198.51.100.11"
    tel = _human()
    real_time = time.time
    # build an old challenge (> 60 s) by generating it under a past clock
    monkeypatch.setattr(time, "time", lambda: real_time() - 120)
    old_challenge = tokens.generate_challenge(client_ip=ip, user_agent=UA)["challenge"]
    monkeypatch.setattr(time, "time", real_time)
    expired_tok = base64.b64encode(json.dumps({"challenge": old_challenge, "telemetry": tel}).encode()).decode()
    d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent=UA, token=expired_tok)
    assert d.action == "block" and "EXPIRED" in " ".join(d.reasons).upper()
    assert _eval(_shift_time(tel, 1500), ip).action == "allow"


# ---------------------------------------------------------------- main.py parity
def test_main_server_parity(tmp_path):
    from synapse_shield.main import app

    client = TestClient(app, client=("127.0.0.1", 50002))
    tel = _human(11)

    def post(ip, telemetry, extra=None):
        h = {"x-forwarded-for": ip, "User-Agent": UA}
        ch = client.get("/api/challenge", headers=h).json()["challenge"]
        tok = base64.b64encode(json.dumps({"challenge": ch, "telemetry": telemetry}).encode()).decode()
        body = {"token": tok, **(extra or {})}
        return client.post("/api/score", json=body, headers=h).json()

    first = post("10.39.0.1", tel)
    assert first["decision"] == "allow"
    again = post("10.39.0.2", _shift_time(tel, 5000))
    assert again["decision"] == "block"
    assert again["threat_type"] == core.TRAJECTORY_REPLAY_THREAT
    assert core.TRAJECTORY_REPLAY_REASON in again["reasons"]


def test_main_pow_retry_is_not_a_replay():
    from synapse_shield.main import app
    from synapse_shield.storage import get_storage

    client = TestClient(app, client=("127.0.0.1", 50003))
    ip = "10.39.0.3"
    get_storage().record_client_strike(client_strike_key(ip, UA), 60)
    tel = _human(12)
    h = {"x-forwarded-for": ip, "User-Agent": UA}

    def tok(telemetry):
        ch = client.get("/api/challenge", headers=h).json()["challenge"]
        return base64.b64encode(json.dumps({"challenge": ch, "telemetry": telemetry}).encode()).decode()

    first = client.post("/api/score", json={"token": tok(tel)}, headers=h).json()
    assert first["decision"] == "challenge"
    nonce = _solve(first["pow_salt"], first["pow_difficulty"])
    retry = client.post(
        "/api/score", json={"token": tok(_shift_time(tel, 2100)), "pow_salt": first["pow_salt"], "pow_nonce": nonce}, headers=h
    ).json()
    assert retry["decision"] == "allow", retry
