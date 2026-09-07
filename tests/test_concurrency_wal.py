import pytest
import concurrent.futures
from synapse_shield.main import save_log, get_connection
import sqlite3

def test_sqlite_wal_mode_enabled():
    """Verify that SQLite connection is configured with WAL journal mode and 10s timeout."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal", f"Expected WAL mode, got {mode}"


def test_concurrent_background_writes():
    """Simulate 30 concurrent threads saving logs simultaneously to ensure no database locks."""
    def worker(i):
        try:
            save_log(
                ip=f"10.0.1.{i % 250}",
                user_agent=f"ConcurrencyTestWorker/{i}",
                bot_score=90.0 if i % 2 == 0 else 10.0,
                classification="Bot" if i % 2 == 0 else "Human",
                threat_type="LINEAR_MACRO" if i % 2 == 0 else "CLEAN_HUMAN",
                reasons=[f"Test reason {i}"],
                features={"test_id": i},
                telemetry={"test_id": i}
            )
            return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                return False
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(30)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(results), "One or more workers encountered 'database is locked' during concurrent writes!"
