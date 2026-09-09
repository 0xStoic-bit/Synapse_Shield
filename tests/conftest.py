import os
import sys
import tempfile

# Testler için zorunlu olarak Mutlak Yol (Absolute Path) temp veritabanı kullanılsın.
# (Göreceli yollar 'test_ci.db' veya in-memory ':memory:' Github Actions'da thread-local patlamalara sebep oluyor)
os.environ["SYNAPSE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "synapse_pytest.db")

# Testleri hızlandırmak için zaman manipülasyon beklemesini kapatıyoruz (test_adversarial_bot.py haricinde)
os.environ["SYNAPSE_MIN_ELAPSED_MS"] = "0"
os.environ["SYNAPSE_ADMIN_SECRET"] = "pytest-secret"

# Add src folder to PYTHONPATH for test discovery
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clear_db_before_test():
    """Her testten önce veritabanındaki logları ve IP banlarını temizler, test izolasyonu sağlar."""
    from synapse_shield.main import app
    client = TestClient(app)
    client.post("/api/clear", headers={"X-Admin-Secret": "pytest-secret"})
