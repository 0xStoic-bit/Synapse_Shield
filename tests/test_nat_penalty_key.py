"""Acik #11: the short "+50 penalized" signal must be keyed per device (IP + User-Agent hash), not per IP.

Behind CGNAT / Eduroam / a corporate NAT many devices share one address. Before this change a single bot
verdict on that address added +50 to every other device for 60 s, which pushed gray-area humans (e.g.
keyboard-only users, +40) over the block threshold. The IP-level ban (4 bot verdicts / 60 s -> 60 s ban)
is deliberately unchanged and still counts per IP.

Storage is exercised with real backends: SQLite on disk and fakeredis (real ZSET semantics).
"""

from __future__ import annotations

import base64
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from synapse_shield import adversarial as adv
from synapse_shield import main as main_mod
from synapse_shield import storage as storage_mod
from synapse_shield.storage import RedisStorageBackend, SQLiteStorageBackend, client_strike_key, set_storage
from test_keyboard_only_access import _human_keyboard_only_session

fakeredis = pytest.importorskip("fakeredis")

NAT_IP = "100.64.7.9"
BOT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/130.0.0.0 Safari/537.36"
HUMAN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
PENALTY_REASON = "temporarily penalized"


class _BrokenRedis:
    def __getattr__(self, name):
        def boom(*a, **k):
            raise ConnectionError("redis down")

        return boom


@pytest.fixture
def sqlite_backend(tmp_path):
    b = SQLiteStorageBackend(db_path=str(tmp_path / "nat.db"))
    yield b
    b.close()


@pytest.fixture
def redis_backend(tmp_path):
    fb = SQLiteStorageBackend(db_path=str(tmp_path / "nat_fb.db"))
    yield RedisStorageBackend("redis://fake:6379/0", client=fakeredis.FakeRedis(decode_responses=True), fallback=fb)
    fb.close()


@pytest.fixture(params=["sqlite", "redis"])
def backend(request, sqlite_backend, redis_backend):
    return sqlite_backend if request.param == "sqlite" else redis_backend


@pytest.fixture
def app_on(backend):
    """Run the real FastAPI app on the given storage backend, from one NAT address."""
    previous = storage_mod._global_storage
    set_storage(backend)
    main_mod._challenge_limiter.cache.clear()
    try:
        yield TestClient(main_mod.app, client=(NAT_IP, 50000)), backend
    finally:
        set_storage(previous)
        main_mod._challenge_limiter.cache.clear()


def _score(client, ua, telemetry):
    h = {"User-Agent": ua}
    challenge = client.get("/api/challenge", headers=h).json()["challenge"]
    env = {"challenge": challenge, "telemetry": telemetry, "created_at": int(time.time() * 1000)}
    token = base64.b64encode(json.dumps(env).encode()).decode()
    return client.post("/api/score", json={"token": token}, headers=h)


def _linear_bot():
    return adv.generate_linear_telemetry(start=(120.0, 140.0), end=(700.0, 520.0), steps=50, duration_ms=1200.0)


# ------------------------------------------------------------------------------------------------
# Storage contract (both backends)
# ------------------------------------------------------------------------------------------------


def test_key_is_opaque_and_separates_devices_on_one_ip():
    k_bot = client_strike_key(NAT_IP, BOT_UA)
    k_human = client_strike_key(NAT_IP, HUMAN_UA)
    assert k_bot != k_human
    assert k_bot == client_strike_key(NAT_IP, BOT_UA), "deterministic: the same device must map to the same key"
    assert k_bot != client_strike_key("100.64.7.10", BOT_UA), "same UA on another IP is another client"
    assert k_bot.startswith("c_") and len(k_bot) == 34
    assert NAT_IP not in k_bot and "HeadlessChrome" not in k_bot


def test_key_is_hmac_with_secret_key_not_plain_sha256():
    """IP and UA are low entropy: a plain SHA-256 of the pair could be brute-forced back offline. The key is an
    HMAC under the token-signing SECRET_KEY, so without that key the stored value is not reversible."""
    import hashlib
    import hmac

    from synapse_shield.tokens import SECRET_KEY

    raw = f"{NAT_IP}\x1f{BOT_UA}".encode("utf-8")
    assert client_strike_key(NAT_IP, BOT_UA) != "c_" + hashlib.sha256(raw).hexdigest()[:32]
    assert client_strike_key(NAT_IP, BOT_UA) == "c_" + hmac.new(SECRET_KEY, raw, hashlib.sha256).hexdigest()[:32]
    assert client_strike_key(NAT_IP, BOT_UA, secret_key=b"other-key") != client_strike_key(NAT_IP, BOT_UA)


def test_key_rotation_forgets_strikes_only_within_the_window(sqlite_backend):
    """Documented trade-off: rotating SYNAPSE_SECRET_KEY changes every client key, so a strike recorded under the
    old key is not seen under the new one. It would have expired after window_sec (60 s) anyway."""
    old = client_strike_key(NAT_IP, BOT_UA, secret_key=b"old-secret")
    new = client_strike_key(NAT_IP, BOT_UA, secret_key=b"new-secret")
    sqlite_backend.record_client_strike(old, 60)
    assert sqlite_backend.get_client_strike_count(new, 60) == 0
    assert sqlite_backend.get_client_strike_count(old, 60) == 1


def test_sqlite_purges_expired_rows_of_keys_never_seen_again(sqlite_backend):
    """Per-device keys are high cardinality; rows of a device that never returns must not accumulate."""
    gone = client_strike_key("100.64.7.200", BOT_UA)
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        conn.execute("INSERT INTO client_strikes (client_key, timestamp) VALUES (?, ?)", (gone, time.time() - 600))
    sqlite_backend._last_client_strike_purge = 0.0
    sqlite_backend.record_client_strike(client_strike_key(NAT_IP, BOT_UA), 60)
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        keys = {r[0] for r in conn.execute("SELECT client_key FROM client_strikes")}
    assert gone not in keys


def test_client_strikes_are_per_key_and_windowed(backend):
    k_bot, k_human = client_strike_key(NAT_IP, BOT_UA), client_strike_key(NAT_IP, HUMAN_UA)
    backend.record_client_strike(k_bot, window_sec=60)
    assert backend.get_client_strike_count(k_bot, 60) == 1
    assert backend.get_client_strike_count(k_human, 60) == 0, "another device behind the NAT must not inherit it"
    # client strikes never ban and never touch the IP-level counter
    assert backend.get_bot_strike_count(NAT_IP, 60) == 0
    assert backend.is_ip_banned(NAT_IP) is False


def test_client_strike_window_expiry_redis(redis_backend):
    k = client_strike_key(NAT_IP, BOT_UA)
    old = time.time() - 120
    redis_backend.client.zadd(f"synapse:cstrikes:{k}", {f"{old}:a": old})
    assert redis_backend.get_client_strike_count(k, 60) == 0
    redis_backend.record_client_strike(k, 60)
    assert redis_backend.get_client_strike_count(k, 60) == 1
    assert 0 < redis_backend.client.ttl(f"synapse:cstrikes:{k}") <= 120


def test_client_strike_window_expiry_sqlite(sqlite_backend):
    k = client_strike_key(NAT_IP, BOT_UA)
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        conn.execute("INSERT INTO client_strikes (client_key, timestamp) VALUES (?, ?)", (k, time.time() - 120))
    assert sqlite_backend.get_client_strike_count(k, 60) == 0
    sqlite_backend.record_client_strike(k, 60)
    assert sqlite_backend.get_client_strike_count(k, 60) == 1


def test_redis_outage_uses_the_same_key_in_sqlite_fallback(tmp_path):
    fb = SQLiteStorageBackend(db_path=str(tmp_path / "outage.db"))
    try:
        b = RedisStorageBackend("redis://down", client=_BrokenRedis(), fallback=fb)
        k = client_strike_key(NAT_IP, BOT_UA)
        b.record_client_strike(k, 60)
        assert b.get_client_strike_count(k, 60) == 1
        assert fb.get_client_strike_count(k, 60) == 1
        assert fb.get_client_strike_count(client_strike_key(NAT_IP, HUMAN_UA), 60) == 0
        with sqlite3.connect(fb.db_path) as conn:
            keys = {r[0] for r in conn.execute("SELECT client_key FROM client_strikes")}
        assert keys == {k}
    finally:
        fb.close()


def test_clear_all_drops_client_strikes(backend):
    k = client_strike_key(NAT_IP, BOT_UA)
    backend.record_client_strike(k, 60)
    backend.clear_all()
    assert backend.get_client_strike_count(k, 60) == 0


def test_backend_without_new_methods_keeps_working():
    """Third-party backends written against the old abstract interface get a process-local window."""

    class Legacy(storage_mod.StorageBackend):
        def consume_nonce(self, nonce, ttl_sec=120): return True
        def is_ip_banned(self, ip): return False
        def ban_ip(self, ip, duration_sec=60, reason=""): pass
        def unban_ip(self, ip): pass
        def record_bot_strike(self, ip, threshold=4, window_sec=60, ban_duration_sec=60, reason=""): return False
        def get_bot_strike_count(self, ip, window_sec=60): return 0
        def clear_all(self): pass
        def record_session_telemetry(self, session_id, metrics, max_history=10, window_sec=300): pass
        def record_and_get_request_count(self, ip, window_sec=10): return 1
        def get_session_telemetries(self, session_id, window_sec=300): return []

    b = Legacy()
    b.record_client_strike("c_x", 60)
    assert b.get_client_strike_count("c_x", 60) == 1
    assert b.get_client_strike_count("c_y", 60) == 0


# ------------------------------------------------------------------------------------------------
# End to end through main.py (/api/challenge -> /api/score), real engine, real storage
# ------------------------------------------------------------------------------------------------


def _spy_penalty(monkeypatch):
    seen = []
    real = main_mod.analyze_behavior

    def spy(telemetry, recent, penalized, accessibility, history, ip_history=None):
        seen.append(penalized)
        return real(telemetry, recent, penalized, accessibility, history, ip_history=ip_history)

    monkeypatch.setattr(main_mod, "analyze_behavior", spy)
    return seen


def test_e2e_other_device_behind_nat_is_not_penalized_but_bot_repeat_is(app_on, monkeypatch):
    client, backend = app_on
    seen = _spy_penalty(monkeypatch)

    bot = _score(client, BOT_UA, _linear_bot()).json()
    assert bot["decision"] == "block"
    assert backend.get_bot_strike_count(NAT_IP, 60) == 1, "IP-level strike counter still counts per IP"

    # (a) keyboard-only human on the same NAT IP, different UA: no +50, stays in the gray-area challenge
    human = _score(client, HUMAN_UA, _human_keyboard_only_session(7)).json()
    assert seen[-1] is False
    assert human["decision"] == "challenge", human

    # (b) the same bot (same IP + same UA) comes back: +50 applies
    again = _score(client, BOT_UA, _human_keyboard_only_session(8)).json()
    assert seen[-1] is True
    assert again["decision"] == "block"
    assert any(PENALTY_REASON in r for r in again["reasons"])


def test_e2e_ip_level_ban_still_counts_per_ip_across_rotating_uas(app_on):
    """(c) Unchanged: 4 bot verdicts in 60 s from one IP ban the IP, whatever UA each request used."""
    client, backend = app_on
    for i in range(4):
        assert _score(client, f"{BOT_UA} r{i}", _linear_bot()).json()["decision"] == "block"
    assert backend.is_ip_banned(NAT_IP) is True
    assert _score(client, HUMAN_UA, _human_keyboard_only_session(3)).status_code == 403


def test_e2e_raw_ua_and_ip_never_reach_strike_storage(app_on, tmp_path):
    """(e) Only the truncated hash is stored for the per-device penalty."""
    client, backend = app_on
    assert _score(client, BOT_UA, _linear_bot()).json()["decision"] == "block"
    k = client_strike_key(NAT_IP, BOT_UA)
    if isinstance(backend, RedisStorageBackend):
        keys = list(backend.client.scan_iter("synapse:cstrikes:*"))
        assert keys == [f"synapse:cstrikes:{k}"]
        dump = " ".join(keys + [m for key in keys for m in backend.client.zrange(key, 0, -1)])
    else:
        with sqlite3.connect(backend.db_path) as conn:
            rows = conn.execute("SELECT client_key, timestamp FROM client_strikes").fetchall()
        assert [r[0] for r in rows] == [k]
        dump = " ".join(str(c) for r in rows for c in r)
    assert "HeadlessChrome" not in dump and "Mozilla" not in dump and NAT_IP not in dump
