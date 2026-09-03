import sys
import os

# Add src folder to PYTHONPATH for test discovery
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def clear_db_before_test():
    """Her testten önce veritabanındaki logları ve IP banlarını temizler, test izolasyonu sağlar."""
    from synapse_shield.main import app
    client = TestClient(app)
    client.post("/api/clear")
