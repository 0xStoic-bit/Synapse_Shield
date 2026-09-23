"""
Synapse Shield - Distributed State & Storage Layer
Provides a unified StorageBackend interface for:
- Replay Attack protection (Nonce deduplication)
- Dynamic IP quarantine (IP bans)
- Sliding-window bot strike tracking

Supports:
1. SQLiteStorageBackend: In-memory/local SQLite storage (default, zero extra dependencies).
2. RedisStorageBackend: Distributed, multi-server Redis cluster storage (enabled via SYNAPSE_REDIS_URL).
"""

from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
from typing import Optional

try:
    import synapse_core_rs

    HAS_RUST_CORE = bool(synapse_core_rs.is_rust_core_active())
except (ImportError, AttributeError):
    synapse_core_rs = None
    HAS_RUST_CORE = False

logger = logging.getLogger("synapse_shield.storage")

DB_FILE = os.environ.get("SYNAPSE_DB_PATH", os.path.join(tempfile.gettempdir(), "synapse_shield.db"))


class StorageBackend(ABC):
    """Abstract base class for Synapse Shield storage providers."""

    @abstractmethod
    def consume_nonce(self, nonce: str, ttl_sec: int = 120) -> bool:
        """
        Record a nonce. Returns True if this is the first time the nonce is seen (valid).
        Returns False if already consumed (Replay Attack detected).
        """
        pass

    @abstractmethod
    def is_ip_banned(self, ip: str) -> bool:
        """Check if an IP address is currently banned."""
        pass

    @abstractmethod
    def ban_ip(self, ip: str, duration_sec: int = 60, reason: str = "4 ardışık bot kararı") -> None:
        """Quarantine/ban an IP address for duration_sec seconds."""
        pass

    @abstractmethod
    def unban_ip(self, ip: str) -> None:
        """Remove an IP address from the ban list."""
        pass

    @abstractmethod
    def record_bot_strike(
        self,
        ip: str,
        threshold: int = 4,
        window_sec: int = 60,
        ban_duration_sec: int = 60,
        reason: str = "4 ardışık bot kararı",
    ) -> bool:
        """
        Record a bot strike for an IP.
        If strikes within window_sec reach threshold, IP is banned for ban_duration_sec and returns True.
        Otherwise returns False.
        """
        pass

    @abstractmethod
    def clear_all(self) -> None:
        """Clear all nonces, bans, and bot strikes (used for tests and admin clear)."""
        pass

    @abstractmethod
    def record_session_telemetry(
        self, session_id: str, metrics: dict, max_history: int = 10, window_sec: int = 300
    ) -> None:
        """Record kinetic summary metrics for a session."""
        pass

    @abstractmethod
    def get_session_telemetries(self, session_id: str, window_sec: int = 300) -> list[dict]:
        """Fetch recent kinetic summaries for a session within window_sec."""
        pass


class SQLiteStorageBackend(StorageBackend):
    """Local SQLite & Thread-safe In-Memory fallback implementation."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_FILE
        self._ip_history: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._ensure_tables()
        if HAS_RUST_CORE and synapse_core_rs is not None:
            self._hydrate_rust_bans()

    def _hydrate_rust_bans(self) -> None:
        """Hydrates unexpired IP bans from SQLite into the Rust L1 In-Memory Cache on startup."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ip, banned_until FROM banned_ips")
                rows = cursor.fetchall()
                active_bans = []
                now_utc = datetime.now(timezone.utc).timestamp()
                for ip, banned_until_str in rows:
                    try:
                        bu = datetime.fromisoformat(banned_until_str)
                        if bu.tzinfo is None:
                            bu = bu.replace(tzinfo=timezone.utc)
                        else:
                            bu = bu.astimezone(timezone.utc)
                        exp_ts = int(bu.timestamp())
                        if exp_ts > now_utc:
                            active_bans.append((ip, exp_ts))
                    except Exception:
                        continue
                if active_bans and synapse_core_rs is not None:
                    synapse_core_rs.hydrate_bans_rs(active_bans)
                    logger.debug("Hydrated %d active IP bans into Rust L1 cache", len(active_bans))
        except Exception as e:
            logger.warning("Failed to hydrate IP bans from SQLite to Rust L1: %s", e)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        return conn

    def _ensure_tables(self):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS used_nonces (
                        nonce TEXT PRIMARY KEY,
                        expires_at INTEGER
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS banned_ips (
                        ip TEXT PRIMARY KEY,
                        banned_until TEXT,
                        reason TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ip_strikes (
                        ip TEXT,
                        timestamp REAL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ip_strikes_ip_ts ON ip_strikes(ip, timestamp)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS session_telemetry (
                        session_id TEXT,
                        timestamp REAL,
                        data_json TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_session_telemetry_sid_ts ON session_telemetry(session_id, timestamp)
                """)
                conn.commit()
        except Exception as e:
            logger.warning(f"SQLite table initialization warning: {e}")

    def _cleanup_expired_nonces(self):
        try:
            now = int(time.time())
            with self._get_connection() as conn:
                conn.execute("DELETE FROM used_nonces WHERE expires_at < ?", (now,))
                conn.commit()
        except Exception as e:
            logger.warning(f"SQLite nonce cleanup failed: {e}")

    def consume_nonce(self, nonce: str, ttl_sec: int = 120) -> bool:
        # L1 Accelerated: Two-Bucket In-Memory Rust Cache (< 1 us)
        if HAS_RUST_CORE and synapse_core_rs is not None:
            try:
                return bool(synapse_core_rs.consume_nonce_rs(nonce))
            except Exception as e:
                logger.warning("Rust consume_nonce_rs failed (%s), falling back to SQLite", e)

        # Fallback to local SQLite disk
        self._cleanup_expired_nonces()
        now_sec = int(time.time())
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO used_nonces (nonce, expires_at) VALUES (?, ?)",
                    (nonce, now_sec + ttl_sec),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"SQLite consume_nonce error: {e}")
            return False

    def is_ip_banned(self, ip: str) -> bool:
        # L1 Accelerated: Nanosecond Rust Hash Lookup (~15 ns)
        if HAS_RUST_CORE and synapse_core_rs is not None:
            try:
                return bool(synapse_core_rs.is_ip_banned_rs(ip))
            except Exception as e:
                logger.warning("Rust is_ip_banned_rs failed (%s), falling back to SQLite", e)

        # Fallback to local SQLite disk
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT banned_until FROM banned_ips WHERE ip = ?", (ip,))
                row = cursor.fetchone()
                if row:
                    banned_until = datetime.fromisoformat(row[0])
                    if banned_until.tzinfo is None:
                        banned_until = banned_until.replace(tzinfo=timezone.utc)
                    else:
                        banned_until = banned_until.astimezone(timezone.utc)

                    if datetime.now(timezone.utc) < banned_until:
                        return True
                    else:
                        cursor.execute("DELETE FROM banned_ips WHERE ip = ?", (ip,))
                        conn.commit()
        except Exception as e:
            logger.error(f"SQLite is_ip_banned check error: {e}")
        return False

    def ban_ip(self, ip: str, duration_sec: int = 60, reason: str = "4 ardışık bot kararı") -> None:
        # 1. Update L1 In-Memory Cache (Instant Write-Through)
        if HAS_RUST_CORE and synapse_core_rs is not None:
            try:
                synapse_core_rs.ban_ip_rs(ip, duration_sec)
            except Exception as e:
                logger.warning("Rust ban_ip_rs error: %s", e)

        # 2. Persist to SQLite for restart survival
        try:
            banned_until = datetime.now(timezone.utc).timestamp() + duration_sec
            banned_until_iso = datetime.fromtimestamp(banned_until, tz=timezone.utc).isoformat()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO banned_ips (ip, banned_until, reason) VALUES (?, ?, ?)",
                    (ip, banned_until_iso, reason),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"SQLite ban_ip error: {e}")

    def unban_ip(self, ip: str) -> None:
        # 1. Remove from L1 In-Memory Cache
        if HAS_RUST_CORE and synapse_core_rs is not None:
            try:
                synapse_core_rs.unban_ip_rs(ip)
            except Exception as e:
                logger.warning("Rust unban_ip_rs error: %s", e)

        # 2. Remove from SQLite
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM banned_ips WHERE ip = ?", (ip,))
                conn.commit()
        except Exception as e:
            logger.error(f"SQLite unban_ip error: {e}")

    def record_bot_strike(
        self,
        ip: str,
        threshold: int = 4,
        window_sec: int = 60,
        ban_duration_sec: int = 60,
        reason: str = "4 ardışık bot kararı",
    ) -> bool:
        try:
            now = time.time()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Pencere dışındaki eski vuruşları temizle
                cursor.execute(
                    "DELETE FROM ip_strikes WHERE ip = ? AND timestamp < ?",
                    (ip, now - window_sec),
                )
                # 2. Yeni vuruşu ekle
                cursor.execute(
                    "INSERT INTO ip_strikes (ip, timestamp) VALUES (?, ?)",
                    (ip, now),
                )
                # 3. Kayan penceredeki güncel vuruş sayısını al
                cursor.execute(
                    "SELECT COUNT(*) FROM ip_strikes WHERE ip = ? AND timestamp >= ?",
                    (ip, now - window_sec),
                )
                count = cursor.fetchone()[0]
                conn.commit()

                if count >= threshold:
                    self.ban_ip(ip, duration_sec=ban_duration_sec, reason=reason)
                    cursor.execute("DELETE FROM ip_strikes WHERE ip = ?", (ip,))
                    conn.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"SQLite record_bot_strike error: {e}")
            return False

    def clear_all(self) -> None:
        if HAS_RUST_CORE and synapse_core_rs is not None:
            try:
                synapse_core_rs.clear_state_engine_rs()
            except Exception as e:
                logger.warning("Rust clear_state_engine_rs error: %s", e)

        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM used_nonces")
                conn.execute("DELETE FROM banned_ips")
                conn.execute("DELETE FROM ip_strikes")
                conn.execute("DELETE FROM session_telemetry")
                conn.commit()
        except Exception as e:
            logger.warning(f"SQLite clear_all error: {e}")

    def record_session_telemetry(
        self, session_id: str, metrics: dict, max_history: int = 10, window_sec: int = 300
    ) -> None:
        try:
            now = time.time()
            data_str = json.dumps(metrics)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM session_telemetry WHERE session_id = ? AND timestamp < ?",
                    (session_id, now - window_sec),
                )
                cursor.execute(
                    "INSERT INTO session_telemetry (session_id, timestamp, data_json) VALUES (?, ?, ?)",
                    (session_id, now, data_str),
                )
                cursor.execute(
                    """DELETE FROM session_telemetry 
                       WHERE session_id = ? 
                         AND rowid NOT IN (
                             SELECT rowid FROM session_telemetry 
                             WHERE session_id = ? 
                             ORDER BY timestamp DESC LIMIT ?
                         )""",
                    (session_id, session_id, max_history),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"SQLite record_session_telemetry error: {e}")

    def get_session_telemetries(self, session_id: str, window_sec: int = 300) -> list[dict]:
        try:
            now = time.time()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT data_json FROM session_telemetry WHERE session_id = ? AND timestamp >= ? ORDER BY timestamp ASC",
                    (session_id, now - window_sec),
                )
                rows = cursor.fetchall()
                results = []
                for (row,) in rows:
                    try:
                        results.append(json.loads(row))
                    except Exception:
                        pass
                return results
        except Exception as e:
            logger.error(f"SQLite get_session_telemetries error: {e}")
            return []


class RedisStorageBackend(StorageBackend):
    """Distributed Redis-backed storage provider for high-availability clusters."""

    def __init__(self, redis_url: str, client: Optional[object] = None, fallback: Optional[StorageBackend] = None):
        self.redis_url = redis_url
        self.fallback = fallback or SQLiteStorageBackend()
        if client is not None:
            self.client = client
        else:
            try:
                import redis

                self.client = redis.Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=1.5,
                    socket_connect_timeout=1.5,
                    retry_on_timeout=False,
                )
            except ImportError:
                raise ImportError(
                    "Redis desteği için 'redis' paketi gereklidir. "
                    "Lütfen 'pip install synapse-shield[redis]' veya 'pip install redis' çalıştırın."
                )

    def consume_nonce(self, nonce: str, ttl_sec: int = 120) -> bool:
        """Atomic SET key 1 EX ttl NX - returns True if key was set, False if already existed."""
        try:
            key = f"synapse:nonce:{nonce}"
            res = self.client.set(key, "1", ex=ttl_sec, nx=True)
            return bool(res)
        except Exception as e:
            logger.warning("Redis consume_nonce failed (%s), falling back to SQLite", e)
            return self.fallback.consume_nonce(nonce, ttl_sec=ttl_sec)

    def is_ip_banned(self, ip: str) -> bool:
        try:
            key = f"synapse:ban:{ip}"
            return bool(self.client.exists(key))
        except Exception as e:
            logger.warning("Redis is_ip_banned failed (%s), falling back to SQLite", e)
            return self.fallback.is_ip_banned(ip)

    def ban_ip(self, ip: str, duration_sec: int = 60, reason: str = "4 ardışık bot kararı") -> None:
        try:
            key = f"synapse:ban:{ip}"
            self.client.set(key, reason, ex=duration_sec)
        except Exception as e:
            logger.warning("Redis ban_ip failed (%s), falling back to SQLite", e)
            self.fallback.ban_ip(ip, duration_sec=duration_sec, reason=reason)

    def unban_ip(self, ip: str) -> None:
        try:
            key = f"synapse:ban:{ip}"
            self.client.delete(key)
        except Exception as e:
            logger.warning("Redis unban_ip failed (%s), falling back to SQLite", e)
            self.fallback.unban_ip(ip)

    def record_bot_strike(
        self,
        ip: str,
        threshold: int = 4,
        window_sec: int = 60,
        ban_duration_sec: int = 60,
        reason: str = "4 ardışık bot kararı",
    ) -> bool:
        try:
            key = f"synapse:strikes:{ip}"
            now = time.time()
            now_ns = time.time_ns()

            pipeline = self.client.pipeline()
            # 1. Pencere dışındaki eski vuruşları sil
            pipeline.zremrangebyscore(key, 0, now - window_sec)
            # 2. Yeni vuruşu ekle (benzersiz üye için timestamp_ns kullanılır)
            pipeline.zadd(key, {f"{now}:{now_ns}": now})
            # 3. Kayan penceredeki güncel vuruş sayısını al
            pipeline.zcard(key)
            # 4. TTL güncelle (pencerenin 2 katı süre)
            pipeline.expire(key, window_sec * 2)
            results = pipeline.execute()

            count = results[2]
            if count >= threshold:
                self.ban_ip(ip, duration_sec=ban_duration_sec, reason=reason)
                self.client.delete(key)
                return True
            return False
        except Exception as e:
            logger.warning("Redis record_bot_strike failed (%s), falling back to SQLite", e)
            return self.fallback.record_bot_strike(
                ip, threshold=threshold, window_sec=window_sec, ban_duration_sec=ban_duration_sec, reason=reason
            )

    def clear_all(self) -> None:
        try:
            keys = list(self.client.scan_iter("synapse:*"))
            if keys:
                self.client.delete(*keys)
        except Exception as e:
            logger.warning("Redis clear_all failed (%s), falling back to SQLite", e)
            self.fallback.clear_all()

    def record_session_telemetry(
        self, session_id: str, metrics: dict, max_history: int = 10, window_sec: int = 300
    ) -> None:
        try:
            key = f"synapse:session:{session_id}"
            now = time.time()
            metrics_payload = {**metrics, "_ts": now}
            data_str = json.dumps(metrics_payload)
            pipeline = self.client.pipeline()
            pipeline.rpush(key, data_str)
            pipeline.ltrim(key, -max_history, -1)
            pipeline.expire(key, window_sec)
            pipeline.execute()
        except Exception as e:
            logger.warning("Redis record_session_telemetry failed (%s), falling back to SQLite", e)
            self.fallback.record_session_telemetry(session_id, metrics, max_history, window_sec)

    def get_session_telemetries(self, session_id: str, window_sec: int = 300) -> list[dict]:
        try:
            key = f"synapse:session:{session_id}"
            items = self.client.lrange(key, 0, -1)
            now = time.time()
            res = []
            for item in items:
                try:
                    d = json.loads(item)
                    if now - d.get("_ts", now) <= window_sec:
                        res.append(d)
                except Exception:
                    pass
            return res
        except Exception as e:
            logger.warning("Redis get_session_telemetries failed (%s), falling back to SQLite", e)
            return self.fallback.get_session_telemetries(session_id, window_sec)


_global_storage: Optional[StorageBackend] = None
_storage_lock = threading.Lock()


def get_storage() -> StorageBackend:
    """
    Factory function returning the active StorageBackend singleton.
    If SYNAPSE_REDIS_URL or REDIS_URL is configured, attempts to connect to Redis.
    Otherwise, gracefully falls back to SQLiteStorageBackend.
    """
    global _global_storage
    if _global_storage is not None:
        return _global_storage

    with _storage_lock:
        if _global_storage is not None:
            return _global_storage

        redis_url = os.environ.get("SYNAPSE_REDIS_URL") or os.environ.get("REDIS_URL")
        if redis_url:
            try:
                backend = RedisStorageBackend(redis_url)
                # Bağlantı testi (ping)
                backend.client.ping()
                logger.info("Synapse Shield: Connected to distributed Redis storage (%s)", redis_url)
                _global_storage = backend
                return _global_storage
            except Exception as e:
                logger.warning(
                    "Synapse Shield: Redis connection to %s failed (%s). Falling back to SQLite.",
                    redis_url,
                    e,
                )

        _global_storage = SQLiteStorageBackend()
        return _global_storage


def set_storage(backend: Optional[StorageBackend]) -> None:
    """Set or reset the global storage provider (primarily for unit tests)."""
    global _global_storage
    with _storage_lock:
        _global_storage = backend
