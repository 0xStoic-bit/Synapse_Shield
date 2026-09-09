import os
import json
import pytest
import sqlite3
import tempfile
import numpy as np
from datetime import datetime, timezone
import shutil

# Set environment variables before importing train.py
TEST_DB_DIR = tempfile.mkdtemp()
TEST_DATASET_DB = os.path.join(TEST_DB_DIR, "synapse_dataset_test.db")
os.environ["SYNAPSE_DATASET_PATH"] = TEST_DATASET_DB

from synapse_shield.train import retrain_fc2, WEIGHTS_PATH
from synapse_shield.main import get_dataset_connection, init_dataset_db

@pytest.fixture(autouse=True)
def setup_teardown():
    init_dataset_db()
    conn = get_dataset_connection()
    cursor = conn.cursor()
    
    # Insert dummy bot telemetry
    telemetry_bot = {
        "mouse_movements": [{"x": 1, "y": 1, "t": 1}],
        "keystrokes": [],
        "clicks": [],
        "scrolls": [],
        "browser": {"webdriver": True}
    }
    cursor.execute(
        "INSERT INTO raw_telemetry (timestamp, mouse_movements, keystrokes, clicks, scrolls, browser) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), json.dumps(telemetry_bot["mouse_movements"]), "[]", "[]", "[]", json.dumps(telemetry_bot["browser"]))
    )
    
    # Insert dummy human telemetry
    telemetry_human = {
        "mouse_movements": [{"x": 100 + i*10, "y": 150 + i*5, "t": i*25} for i in range(20)],
        "keystrokes": [],
        "clicks": [],
        "scrolls": [],
        "browser": {"webdriver": False, "plugins_length": 3}
    }
    cursor.execute(
        "INSERT INTO raw_telemetry (timestamp, mouse_movements, keystrokes, clicks, scrolls, browser) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), json.dumps(telemetry_human["mouse_movements"]), "[]", "[]", "[]", json.dumps(telemetry_human["browser"]))
    )
    conn.commit()
    
    yield
    
    # Teardown
    conn.close()
    shutil.rmtree(TEST_DB_DIR, ignore_errors=True)

def test_retrain_fc2(monkeypatch):
    # Mock WEIGHTS_PATH to avoid overwriting the real model
    tmp_weights_path = os.path.join(TEST_DB_DIR, "dummy_weights.npz")
    shutil.copy2(WEIGHTS_PATH, tmp_weights_path)
    
    monkeypatch.setattr("synapse_shield.train.WEIGHTS_PATH", tmp_weights_path)
    
    # Retrain (transfer learning on FC2)
    retrain_fc2(epochs=1)
    
    # Verify new weights were saved atomically
    assert os.path.exists(tmp_weights_path)
    data = np.load(tmp_weights_path)
    assert "fc2_w" in data
