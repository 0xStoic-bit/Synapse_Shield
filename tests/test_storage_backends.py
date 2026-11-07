"""
Storage backend behaviour: Redis (via fakeredis, real command semantics), Redis -> SQLite
failover, SQLite disk/L1-cache paths, Rust L1 hydration and failure handling.

The existing tests/test_storage.py drives Redis through MagicMock, which only proves the right
method names are called. Here fakeredis executes the actual SET NX / ZSET / LIST semantics so a
wrong key, TTL or pipeline index would fail.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from synapse_shield import storage as storage_mod
from synapse_shield.storage import RedisStorageBackend, SQLiteStorageBackend, get_storage, set_storage

fakeredis = pytest.importorskip("fakeredis")


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------


@pytest.fixture
def sqlite_backend(tmp_path):
    b = SQLiteStorageBackend(db_path=str(tmp_path / "s.db"))
    yield b
    b.close()


@pytest.fixture
def redis_backend(tmp_path):
    client = fakeredis.FakeRedis(decode_responses=True)
    fallback = SQLiteStorageBackend(db_path=str(tmp_path / "fallback.db"))
    b = RedisStorageBackend("redis://fake:6379/0", client=client, fallback=fallback)
    yield b
    fallback.close()


@pytest.fixture
def no_rust(monkeypatch):
    """Force the pure-SQLite code paths (no Rust L1 cache)."""
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", False)


class _BrokenRedis:
    """A client whose every command raises, emulating a Redis outage."""

    def __getattr__(self, name):
        def boom(*a, **k):
            raise ConnectionError("redis down")

        return boom


# --------------------------------------------------------------------------------------------
# Redis — real command semantics
# --------------------------------------------------------------------------------------------


def test_redis_nonce_is_single_use_and_expires(redis_backend):
    assert redis_backend.consume_nonce("n1", ttl_sec=60) is True
    assert redis_backend.consume_nonce("n1", ttl_sec=60) is False
    ttl = redis_backend.client.ttl("synapse:nonce:n1")
    assert 0 < ttl <= 60


def test_redis_ban_lifecycle(redis_backend):
    assert redis_backend.is_ip_banned("9.9.9.9") is False
    redis_backend.ban_ip("9.9.9.9", duration_sec=30, reason="flood")
    assert redis_backend.is_ip_banned("9.9.9.9") is True
    assert redis_backend.client.get("synapse:ban:9.9.9.9") == "flood"
    assert 0 < redis_backend.client.ttl("synapse:ban:9.9.9.9") <= 30
    redis_backend.unban_ip("9.9.9.9")
    assert redis_backend.is_ip_banned("9.9.9.9") is False


def test_redis_strikes_ban_at_threshold_and_reset(redis_backend):
    ip = "10.1.1.1"
    assert [redis_backend.record_bot_strike(ip, threshold=3) for _ in range(2)] == [False, False]
    assert redis_backend.get_bot_strike_count(ip) == 2
    assert redis_backend.record_bot_strike(ip, threshold=3) is True
    assert redis_backend.is_ip_banned(ip) is True
    assert redis_backend.get_bot_strike_count(ip) == 0, "strike set must be cleared after ban"


def test_redis_strikes_outside_window_are_dropped(redis_backend):
    ip = "10.2.2.2"
    old = time.time() - 120
    redis_backend.client.zadd(f"synapse:strikes:{ip}", {f"{old}:1": old, f"{old}:2": old})
    assert redis_backend.get_bot_strike_count(ip, window_sec=60) == 0
    assert redis_backend.record_bot_strike(ip, threshold=3, window_sec=60) is False


def test_redis_request_counter_sliding_window(redis_backend):
    ip = "10.3.3.3"
    counts = [redis_backend.record_and_get_request_count(ip, window_sec=10) for _ in range(5)]
    assert counts == [1, 2, 3, 4, 5]
    old = time.time() - 60
    key = f"synapse:req_count:{ip}"
    redis_backend.client.delete(key)
    redis_backend.client.zadd(key, {"stale": old})
    assert redis_backend.record_and_get_request_count(ip, window_sec=10) == 1


def test_redis_counters_do_not_merge_events_with_identical_timestamps(redis_backend, monkeypatch):
    """Regression: members used to be f"{time}:{time_ns}". With a coarse clock (Windows) or
    concurrent workers, same-tick events collided and ZADD merged them, so a burst of N requests
    counted as 1 — undercounting both the request-flood counter and bot strikes."""
    frozen = time.time()
    monkeypatch.setattr(storage_mod.time, "time", lambda: frozen)
    monkeypatch.setattr(storage_mod.time, "time_ns", lambda: int(frozen * 1e9))
    counts = [redis_backend.record_and_get_request_count("14.0.0.1") for _ in range(5)]
    assert counts == [1, 2, 3, 4, 5]
    strikes = [redis_backend.record_bot_strike("14.0.0.2", threshold=4) for _ in range(4)]
    assert strikes == [False, False, False, True]


def test_redis_session_telemetry_history_window_and_garbage(redis_backend):
    sid = "sess-1"
    for i in range(15):
        redis_backend.record_session_telemetry(sid, {"i": i}, max_history=10, window_sec=300)
    got = redis_backend.get_session_telemetries(sid, window_sec=300)
    assert [g["i"] for g in got] == list(range(5, 15)), "LTRIM must keep the newest max_history items"
    # Stale and corrupt entries are skipped, not raised.
    key = f"synapse:session:{sid}"
    redis_backend.client.rpush(key, '{"i": -1, "_ts": 0}', "{corrupt")
    got = redis_backend.get_session_telemetries(sid, window_sec=300)
    assert [g["i"] for g in got] == list(range(5, 15))


def test_redis_clear_all_only_touches_synapse_keys(redis_backend):
    redis_backend.client.set("app:unrelated", "keep")
    redis_backend.consume_nonce("x")
    redis_backend.ban_ip("1.1.1.1")
    redis_backend.clear_all()
    assert redis_backend.client.get("app:unrelated") == "keep"
    assert list(redis_backend.client.scan_iter("synapse:*")) == []
    redis_backend.clear_all()  # empty keyspace path


# --------------------------------------------------------------------------------------------
# Redis outage -> SQLite fallback
# --------------------------------------------------------------------------------------------


def test_redis_outage_falls_back_to_sqlite_for_every_operation(tmp_path):
    fallback = SQLiteStorageBackend(db_path=str(tmp_path / "fb.db"))
    b = RedisStorageBackend("redis://down", client=_BrokenRedis(), fallback=fallback)
    try:
        assert b.consume_nonce("fb-nonce") is True
        assert b.consume_nonce("fb-nonce") is False, "replay protection must survive a Redis outage"
        b.ban_ip("2.2.2.2", duration_sec=60)
        assert b.is_ip_banned("2.2.2.2") is True
        b.unban_ip("2.2.2.2")
        assert b.is_ip_banned("2.2.2.2") is False
        assert b.record_bot_strike("3.3.3.3", threshold=2) is False
        assert b.get_bot_strike_count("3.3.3.3") == 1
        assert b.record_bot_strike("3.3.3.3", threshold=2) is True
        assert b.record_and_get_request_count("4.4.4.4") == 1
        b.record_session_telemetry("s", {"v": 1})
        assert b.get_session_telemetries("s") == [{"v": 1}]
        b.clear_all()
        assert b.get_bot_strike_count("3.3.3.3") == 0
    finally:
        fallback.close()


def test_redis_ban_survives_redis_outage(tmp_path, no_rust):
    """Regression (was fail-open): bans written while Redis was healthy used to live only in Redis,
    so during an outage is_ip_banned() fell back to a SQLite store that had never seen them and
    quarantined IPs passed. Bans (and unbans) are now mirrored into the fallback."""
    fallback = SQLiteStorageBackend(db_path=str(tmp_path / "gap.db"))
    healthy = RedisStorageBackend("redis://fake", client=fakeredis.FakeRedis(decode_responses=True), fallback=fallback)
    try:
        healthy.ban_ip("6.6.6.6", duration_sec=300)
        healthy.ban_ip("6.6.6.7", duration_sec=300)
        healthy.unban_ip("6.6.6.7")
        assert healthy.is_ip_banned("6.6.6.6") is True
        fallback._ip_ban_cache.clear()
        healthy.client = _BrokenRedis()
        assert healthy.is_ip_banned("6.6.6.6") is True, "ban must stay visible during a Redis outage"
        assert healthy.is_ip_banned("6.6.6.7") is False, "unban must be mirrored too"
    finally:
        fallback.close()


def test_redis_ban_mirror_failure_does_not_break_banning(tmp_path):
    class BrokenFallback:
        def ban_ip(self, *a, **k):
            raise RuntimeError("disk full")

        def unban_ip(self, *a, **k):
            raise RuntimeError("disk full")

    b = RedisStorageBackend("redis://fake", client=fakeredis.FakeRedis(decode_responses=True), fallback=BrokenFallback())
    b.ban_ip("6.6.6.8", duration_sec=60)
    assert b.is_ip_banned("6.6.6.8") is True
    b.unban_ip("6.6.6.8")
    assert b.is_ip_banned("6.6.6.8") is False


def test_redis_backend_requires_redis_package(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "redis", None)
    with pytest.raises(ImportError, match="redis"):
        RedisStorageBackend("redis://x", fallback=SQLiteStorageBackend(db_path=str(tmp_path / "r.db")))


def test_get_storage_prefers_reachable_redis(monkeypatch):
    redis = pytest.importorskip("redis")
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: fake))
    monkeypatch.setenv("SYNAPSE_REDIS_URL", "redis://fake:6379/0")
    set_storage(None)
    try:
        s = get_storage()
        assert isinstance(s, RedisStorageBackend)
        assert get_storage() is s, "factory must return a singleton"
    finally:
        set_storage(None)


def test_get_storage_double_checked_lock(monkeypatch, tmp_path):
    """A backend installed while a caller waited on the lock is returned, not replaced."""
    sentinel = SQLiteStorageBackend(db_path=str(tmp_path / "dc.db"))

    class InstallingLock:
        def __enter__(self):
            storage_mod._global_storage = sentinel

        def __exit__(self, *a):
            return False

    set_storage(None)
    monkeypatch.setattr(storage_mod, "_storage_lock", InstallingLock())
    try:
        assert get_storage() is sentinel
    finally:
        storage_mod._global_storage = None
        sentinel.close()


# --------------------------------------------------------------------------------------------
# SQLite — disk paths (no Rust L1)
# --------------------------------------------------------------------------------------------


def _write_ban(db_path: str, ip: str, banned_until: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO banned_ips (ip, banned_until, reason) VALUES (?, ?, ?)",
            (ip, banned_until, "test"),
        )


def test_sqlite_ban_from_other_worker_is_seen_and_cached(no_rust, sqlite_backend):
    future_naive = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(tzinfo=None).isoformat()
    future_aware = (datetime.now(timezone(timedelta(hours=3))) + timedelta(minutes=5)).isoformat()
    _write_ban(sqlite_backend.db_path, "7.7.7.1", future_naive)
    _write_ban(sqlite_backend.db_path, "7.7.7.2", future_aware)
    assert sqlite_backend.is_ip_banned("7.7.7.1") is True
    assert sqlite_backend.is_ip_banned("7.7.7.2") is True
    assert sqlite_backend._ip_ban_cache["7.7.7.1"][0] is True
    # Positive cache hit (no disk read needed).
    assert sqlite_backend.is_ip_banned("7.7.7.1") is True


def test_sqlite_expired_ban_is_purged(no_rust, sqlite_backend):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    _write_ban(sqlite_backend.db_path, "7.7.7.3", past)
    assert sqlite_backend.is_ip_banned("7.7.7.3") is False
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM banned_ips WHERE ip='7.7.7.3'").fetchone()[0] == 0


def test_sqlite_nonce_cleanup_removes_expired_rows(no_rust, sqlite_backend):
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        conn.execute("INSERT INTO used_nonces VALUES ('old', ?)", (int(time.time()) - 10,))
    sqlite_backend._last_nonce_cleanup = 0.0
    assert sqlite_backend.consume_nonce("fresh") is True
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        rows = {r[0] for r in conn.execute("SELECT nonce FROM used_nonces")}
    assert rows == {"fresh"}
    # Cleanup is rate-limited to once per minute.
    sqlite_backend._cleanup_expired_nonces()


def test_sqlite_session_telemetry_cold_start_from_disk(no_rust, tmp_path):
    db = str(tmp_path / "tele.db")
    writer = SQLiteStorageBackend(db_path=db)
    writer.record_session_telemetry("s1", {"v": 1})
    writer.record_session_telemetry("s1", {"v": 2})
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO session_telemetry VALUES ('s1', ?, '{bad json')", (time.time(),))
    writer.close()

    reader = SQLiteStorageBackend(db_path=db)  # fresh process: empty L1
    try:
        assert reader.get_session_telemetries("s1") == [{"v": 1}, {"v": 2}]
        assert "s1" in reader._session_telemetry_l1, "disk read must warm the L1 cache"
        assert reader.get_session_telemetries("s1") == [{"v": 1}, {"v": 2}]
    finally:
        reader.close()


def test_sqlite_strike_count_from_other_worker(no_rust, sqlite_backend):
    now = time.time()
    with sqlite3.connect(sqlite_backend.db_path) as conn:
        conn.executemany("INSERT INTO ip_strikes VALUES ('8.8.8.8', ?)", [(now,), (now,)])
    assert sqlite_backend.get_bot_strike_count("8.8.8.8") == 2
    # The next strike counts the other worker's strikes too and crosses the threshold.
    assert sqlite_backend.record_bot_strike("8.8.8.8", threshold=3) is True


def test_sqlite_l1_maps_are_bounded(no_rust, sqlite_backend):
    stale = time.time() - 10_000
    from collections import deque

    sqlite_backend._ip_strikes_l1 = {f"ip{i}": deque([stale]) for i in range(5001)}
    sqlite_backend._ip_history = {f"ip{i}": deque([stale]) for i in range(5001)}
    sqlite_backend._session_telemetry_l1 = {f"s{i}": deque([(stale, {})]) for i in range(5001)}

    sqlite_backend.record_bot_strike("new", threshold=99)
    sqlite_backend.record_and_get_request_count("new")
    sqlite_backend.record_session_telemetry("new", {"a": 1})

    assert len(sqlite_backend._ip_strikes_l1) == 1
    assert len(sqlite_backend._ip_history) == 1
    assert len(sqlite_backend._session_telemetry_l1) == 1


def test_sqlite_close_is_idempotent(sqlite_backend):
    sqlite_backend._get_connection()
    sqlite_backend.close()
    sqlite_backend.close()
    assert getattr(sqlite_backend._local, "conn", None) is None


# --------------------------------------------------------------------------------------------
# SQLite — failure handling (unusable database file)
# --------------------------------------------------------------------------------------------


def test_sqlite_unusable_database_fails_closed_for_nonces(no_rust, tmp_path):
    """A directory path makes every sqlite3.connect fail.

    Nonce consumption must fail CLOSED (reject) so a broken DB cannot enable replays.
    Ban lookups fail OPEN (return False) and strikes fall back to the in-memory L1 window.
    """
    b = SQLiteStorageBackend(db_path=str(tmp_path))  # a directory, not a file
    assert b.consume_nonce("x") is False
    assert b.is_ip_banned("1.1.1.1") is False
    b.ban_ip("1.1.1.1")
    b.unban_ip("1.1.1.1")
    assert b.record_bot_strike("5.5.5.5", threshold=2) is False
    assert b.get_bot_strike_count("5.5.5.5") == 1
    assert b.record_bot_strike("5.5.5.5", threshold=2) is True, "L1 window must still ban"
    b.record_session_telemetry("s", {"a": 1})
    b._session_telemetry_l1.clear()
    assert b.get_session_telemetries("s") == []
    b._last_nonce_cleanup = 0.0
    b._cleanup_expired_nonces()
    b.clear_all()


def test_sqlite_pragma_failure_is_tolerated(tmp_path, monkeypatch):
    real_connect = sqlite3.connect

    class NoPragmaConn:
        def __init__(self, conn):
            self._c = conn

        def execute(self, sql, *a):
            if sql.startswith("PRAGMA"):
                raise sqlite3.OperationalError("pragma blocked")
            return self._c.execute(sql, *a)

        def __getattr__(self, name):
            return getattr(self._c, name)

        def __enter__(self):
            self._c.__enter__()
            return self

        def __exit__(self, *a):
            return self._c.__exit__(*a)

    monkeypatch.setattr(storage_mod.sqlite3, "connect", lambda *a, **k: NoPragmaConn(real_connect(*a, **k)))
    b = SQLiteStorageBackend(db_path=str(tmp_path / "p.db"))
    assert b.consume_nonce("ok") is True
    b.close()


# --------------------------------------------------------------------------------------------
# Rust L1 cache integration
# --------------------------------------------------------------------------------------------


rust = pytest.mark.skipif(not storage_mod.HAS_RUST_CORE, reason="native Rust core not built")


@rust
def test_rust_hydrates_unexpired_bans_on_startup(tmp_path):
    rs = storage_mod.synapse_core_rs
    rs.clear_state_engine_rs()
    db = str(tmp_path / "hyd.db")
    SQLiteStorageBackend(db_path=db).close()  # create schema
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    _write_ban(db, "11.0.0.1", future.replace(tzinfo=None).isoformat())  # naive
    _write_ban(db, "11.0.0.2", future.astimezone(timezone(timedelta(hours=-5))).isoformat())  # aware
    _write_ban(db, "11.0.0.3", (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())  # expired
    _write_ban(db, "11.0.0.4", "not-a-date")  # corrupt row is skipped
    b = SQLiteStorageBackend(db_path=db)
    try:
        assert rs.is_ip_banned_rs("11.0.0.1") is True
        assert rs.is_ip_banned_rs("11.0.0.2") is True
        assert rs.is_ip_banned_rs("11.0.0.3") is False
        assert rs.is_ip_banned_rs("11.0.0.4") is False
    finally:
        b.close()
        rs.clear_state_engine_rs()


@rust
def test_rust_hydration_survives_a_corrupt_row_before_valid_ones(tmp_path):
    """Mutation-testing finding (storage #52): a `continue` -> `break` mutant survived, i.e. nothing
    proved that one corrupt row does not stop every later ban from being hydrated on restart."""
    rs = storage_mod.synapse_core_rs
    rs.clear_state_engine_rs()
    db = str(tmp_path / "hyd2.db")
    SQLiteStorageBackend(db_path=db).close()
    _write_ban(db, "11.1.0.1", "garbage")  # inserted first -> read first
    _write_ban(db, "11.1.0.2", (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    b = SQLiteStorageBackend(db_path=db)
    try:
        assert rs.is_ip_banned_rs("11.1.0.2") is True
    finally:
        b.close()
        rs.clear_state_engine_rs()


@pytest.mark.parametrize("backend_name", ["sqlite", "redis"])
def test_default_strike_policy_is_4_strikes_60s_ban(backend_name, sqlite_backend, redis_backend, no_rust):
    """core.py calls record_bot_strike(ip) with the defaults on every token failure, so the defaults
    ARE the production policy: 4 strikes within 60 s -> 60 s ban."""
    b = sqlite_backend if backend_name == "sqlite" else redis_backend
    ip = f"15.0.0.{1 if backend_name == 'sqlite' else 2}"
    assert [b.record_bot_strike(ip) for _ in range(4)] == [False, False, False, True]
    assert b.is_ip_banned(ip)
    if backend_name == "redis":
        assert 55 <= b.client.ttl(f"synapse:ban:{ip}") <= 60
    else:
        with sqlite3.connect(b.db_path) as conn:
            until = datetime.fromisoformat(conn.execute("SELECT banned_until FROM banned_ips WHERE ip=?", (ip,)).fetchone()[0])
        assert 55 <= (until - datetime.now(timezone.utc)).total_seconds() <= 60


def test_sqlite_pragmas_for_multi_worker_safety(sqlite_backend):
    """WAL alone is not enough under multi-worker load: busy_timeout and synchronous matter too."""
    conn = sqlite_backend._get_connection()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2  # MEMORY
    assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 1000


@rust
def test_rust_disk_ban_is_promoted_to_l1(tmp_path):
    rs = storage_mod.synapse_core_rs
    rs.clear_state_engine_rs()
    b = SQLiteStorageBackend(db_path=str(tmp_path / "promo.db"))
    try:
        _write_ban(b.db_path, "12.0.0.1", (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())
        assert rs.is_ip_banned_rs("12.0.0.1") is False
        assert b.is_ip_banned("12.0.0.1") is True
        assert rs.is_ip_banned_rs("12.0.0.1") is True
    finally:
        b.close()
        rs.clear_state_engine_rs()


class _RaisingRust:
    """Stand-in for a misbehaving native module: every call raises."""

    def __getattr__(self, name):
        def boom(*a, **k):
            raise RuntimeError(f"{name} exploded")

        return boom


def test_rust_errors_fall_back_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_mod, "HAS_RUST_CORE", True)
    monkeypatch.setattr(storage_mod, "synapse_core_rs", _RaisingRust())
    b = SQLiteStorageBackend(db_path=str(tmp_path / "rerr.db"))  # hydration error is logged
    try:
        assert b.consume_nonce("r1") is True
        assert b.consume_nonce("r1") is False, "SQLite must still block the replay"
        b.ban_ip("13.0.0.1", duration_sec=60)
        b._ip_ban_cache.clear()
        assert b.is_ip_banned("13.0.0.1") is True
        b.unban_ip("13.0.0.1")
        b._ip_ban_cache.clear()
        assert b.is_ip_banned("13.0.0.1") is False
        b.clear_all()
    finally:
        b.close()
