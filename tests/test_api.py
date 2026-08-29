import pytest
from fastapi.testclient import TestClient
from synapse_shield.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_challenge_endpoint():
    response = client.get("/api/challenge")
    assert response.status_code == 200
    data = response.json()
    assert "challenge" in data
    assert "expires_in" in data

def test_score_endpoint_invalid_json():
    response = client.post("/api/score", data="invalid json")
    assert response.status_code == 400

def test_logs_endpoint():
    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert "total_requests" in data
