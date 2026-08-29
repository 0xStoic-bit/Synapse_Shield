import pytest
import base64
import json
from synapse_shield.tokens import generate_challenge, verify_and_consume_token

def test_token_generation():
    challenge_data = generate_challenge()
    assert "challenge" in challenge_data
    assert "expires_in" in challenge_data

def test_valid_token_consumption():
    ch_data = generate_challenge()
    tok_envelope = {"challenge": ch_data["challenge"], "telemetry": {"mouse_movements": []}}
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()
    
    is_valid, reason, telemetry = verify_and_consume_token(tok_b64)
    assert is_valid == True
    assert reason == "Geçerli"

def test_forged_signature():
    ch_data = generate_challenge()
    bad_challenge = ch_data["challenge"][:-5] + "12345"
    tok_envelope = {"challenge": bad_challenge, "telemetry": {}}
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()
    
    is_valid, reason, telemetry = verify_and_consume_token(tok_b64)
    assert is_valid == False
    assert "Sahte challenge imzası" in reason

def test_replay_attack():
    ch_data = generate_challenge()
    tok_envelope = {"challenge": ch_data["challenge"], "telemetry": {}}
    tok_b64 = base64.b64encode(json.dumps(tok_envelope).encode()).decode()
    
    is_valid1, reason1, _ = verify_and_consume_token(tok_b64)
    assert is_valid1 == True
    
    # 2. Kez aynı tokenı deneyince Replay algılamalı
    is_valid2, reason2, _ = verify_and_consume_token(tok_b64)
    assert is_valid2 == False
    assert "Replay Detected" in reason2
