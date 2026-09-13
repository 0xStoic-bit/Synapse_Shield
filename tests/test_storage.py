"""
Tests for Synapse Shield Storage Layer (SQLite and Distributed Redis).
Validates:
- Nonce deduplication & replay attack defense
- Dynamic IP quarantine / banning
- Sliding-window bot strike triggers
- Graceful Redis fallback to SQLite
"""

from unittest.mock import MagicMock, patch

from synapse_shield.storage import (
    SQLiteStorageBackend,
    RedisStorageBackend,
    get_storage,
    set_storage,
)


def test_sqlite_nonce_deduplication(tmp_path):
    """Verify that SQLiteStorageBackend allows a nonce once and blocks replays."""
    db_file = str(tmp_path / "test_synapse.db")
    backend = SQLiteStorageBackend(db_path=db_file)

    nonce = "unique_nonce_12345"

    # İlk kullanım geçerli olmalı
    assert backend.consume_nonce(nonce, ttl_sec=120) is True

    # İkinci kullanım (Replay Attack) reddedilmeli
    assert backend.consume_nonce(nonce, ttl_sec=120) is False


def test_sqlite_ip_ban_and_expiration(tmp_path):
    """Verify that SQLiteStorageBackend bans an IP and unbans when expired."""
    db_file = str(tmp_path / "test_synapse.db")
    backend = SQLiteStorageBackend(db_path=db_file)

    ip = "192.168.1.100"

    assert backend.is_ip_banned(ip) is False

    # 1 saniyeliğine banla
    backend.ban_ip(ip, duration_sec=1, reason="Test ban")
    assert backend.is_ip_banned(ip) is True

    # Manuel unban
    backend.unban_ip(ip)
    assert backend.is_ip_banned(ip) is False


def test_sqlite_bot_strike_threshold(tmp_path):
    """Verify that 4 bot strikes trigger an automatic IP ban."""
    db_file = str(tmp_path / "test_synapse.db")
    backend = SQLiteStorageBackend(db_path=db_file)

    ip = "10.0.0.5"

    # İlk 3 vuruş henüz ban tetiklememeli
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is False
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is False
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is False
    assert backend.is_ip_banned(ip) is False

    # 4. vuruş ban tetiklemeli
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is True
    assert backend.is_ip_banned(ip) is True


def test_sqlite_clear_all(tmp_path):
    """Verify clear_all clears nonces and banned IPs."""
    db_file = str(tmp_path / "test_synapse.db")
    backend = SQLiteStorageBackend(db_path=db_file)

    backend.consume_nonce("nonce_abc", ttl_sec=120)
    backend.ban_ip("1.2.3.4", duration_sec=60)

    assert backend.is_ip_banned("1.2.3.4") is True
    assert backend.consume_nonce("nonce_abc", ttl_sec=120) is False

    backend.clear_all()

    assert backend.is_ip_banned("1.2.3.4") is False
    assert backend.consume_nonce("nonce_abc", ttl_sec=120) is True


def test_redis_nonce_deduplication():
    """Verify that RedisStorageBackend uses atomic SET NX for replay defense."""
    mock_redis = MagicMock()
    # İlk çağrıda True (anahtar yazıldı), ikinci çağrıda False (anahtar mevcuttu)
    mock_redis.set.side_effect = [True, False]

    backend = RedisStorageBackend(redis_url="redis://localhost:6379/0", client=mock_redis)

    assert backend.consume_nonce("token_999", ttl_sec=120) is True
    mock_redis.set.assert_called_with("synapse:nonce:token_999", "1", ex=120, nx=True)

    assert backend.consume_nonce("token_999", ttl_sec=120) is False


def test_redis_ip_ban_and_unban():
    """Verify RedisStorageBackend correctly interacts with redis keys for bans."""
    mock_redis = MagicMock()
    mock_redis.exists.side_effect = [False, True, False]

    backend = RedisStorageBackend(redis_url="redis://localhost:6379/0", client=mock_redis)

    ip = "203.0.113.1"
    assert backend.is_ip_banned(ip) is False

    backend.ban_ip(ip, duration_sec=60, reason="DDoS suspect")
    mock_redis.set.assert_called_with("synapse:ban:203.0.113.1", "DDoS suspect", ex=60)

    assert backend.is_ip_banned(ip) is True

    backend.unban_ip(ip)
    mock_redis.delete.assert_called_with("synapse:ban:203.0.113.1")


def test_redis_bot_strike_sliding_window():
    """Verify Redis sorted set pipeline strikes and ban trigger."""
    mock_redis = MagicMock()
    pipeline = MagicMock()
    mock_redis.pipeline.return_value = pipeline

    # Pipeline execute returns: [zrem_res, zadd_res, count, expire_res]
    pipeline.execute.side_effect = [
        [0, 1, 1, True],  # 1. vuruş
        [0, 1, 2, True],  # 2. vuruş
        [0, 1, 3, True],  # 3. vuruş
        [0, 1, 4, True],  # 4. vuruş -> Ban tetiklenmeli
    ]

    backend = RedisStorageBackend(redis_url="redis://localhost:6379/0", client=mock_redis)

    ip = "198.51.100.42"
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is False
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is False
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is False
    # 4. vuruşta True dönmeli
    assert backend.record_bot_strike(ip, threshold=4, window_sec=60) is True


def test_get_storage_fallback():
    """Verify get_storage returns SQLite by default and falls back safely if Redis fails."""
    set_storage(None)

    # Env yokken SQLiteStorageBackend dönmeli
    with patch.dict("os.environ", {}, clear=True):
        storage = get_storage()
        assert isinstance(storage, SQLiteStorageBackend)

    set_storage(None)

    # Hatalı Redis URL verildiğinde SQLiteStorageBackend'e zarifçe düşmeli (fallback)
    with patch.dict("os.environ", {"SYNAPSE_REDIS_URL": "redis://non_existent_host:6379/0"}):
        storage = get_storage()
        assert isinstance(storage, SQLiteStorageBackend)

    set_storage(None)
