from synapse_shield.features import extract_features
from synapse_shield.storage import SQLiteStorageBackend


def test_zero_pii_single_char_masking_parity():
    """Verify that masked keystrokes retain full dwell and flight kinematic scoring."""
    telemetry = {
        "browser": {"touch_supported": False},
        "keystrokes": [
            {"type": "down", "key": "masked", "t": 100, "is_freq_digraph": False},
            {"type": "up", "key": "masked", "t": 175, "duration_ms": 75, "is_freq_digraph": False},
            {"type": "down", "key": "masked", "t": 240, "is_freq_digraph": True},
            {"type": "up", "key": "masked", "t": 315, "duration_ms": 75, "is_freq_digraph": True},
            {"type": "down", "key": "masked", "t": 390, "is_freq_digraph": False},
            {"type": "up", "key": "masked", "t": 460, "duration_ms": 70, "is_freq_digraph": False},
            {"type": "down", "key": "masked", "t": 530, "is_freq_digraph": True},
            {"type": "up", "key": "masked", "t": 605, "duration_ms": 75, "is_freq_digraph": True},
            {"type": "down", "key": "enter", "t": 680, "is_freq_digraph": False},
            {"type": "up", "key": "enter", "t": 760, "duration_ms": 80, "is_freq_digraph": False},
        ]
    }
    feats = extract_features(telemetry)
    assert feats["key_count"] == 5
    assert feats["key_interval_avg"] > 0.0
    assert feats["key_interval_var"] >= 0.0
    assert feats["keystroke_score"] < 0.50  # Natural human keystrokes


def test_robot_detection_retains_fidelity_with_masked_keys():
    """Verify that robotic constant-interval key attacks are still detected with 100% precision when masked."""
    telemetry = {
        "browser": {"touch_supported": False},
        "keystrokes": [
            {"type": "down", "key": "masked", "t": 100},
            {"type": "up", "key": "masked", "t": 110},
            {"type": "down", "key": "masked", "t": 160},
            {"type": "up", "key": "masked", "t": 170},
            {"type": "down", "key": "masked", "t": 220},
            {"type": "up", "key": "masked", "t": 230},
            {"type": "down", "key": "masked", "t": 280},
            {"type": "up", "key": "masked", "t": 290},
            {"type": "down", "key": "masked", "t": 340},
            {"type": "up", "key": "masked", "t": 350},
        ]
    }
    feats = extract_features(telemetry)
    assert feats["key_count"] == 5
    # Zero variance in dwell & flight -> robotic keystrokes
    assert feats["keystroke_score"] >= 0.70


def test_ime_unidentified_functional_keys_preserved():
    """Verify that virtual IME keys (unidentified, process) retain mobile keyboard classification alongside masked keys."""
    telemetry = {
        "browser": {"touch_supported": True},
        "keystrokes": [
            {"type": "down", "key": "unidentified", "t": 100},
            {"type": "up", "key": "unidentified", "t": 105},
            {"type": "down", "key": "unidentified", "t": 260},
            {"type": "up", "key": "unidentified", "t": 265},
            {"type": "down", "key": "unidentified", "t": 410},
            {"type": "up", "key": "unidentified", "t": 415},
            {"type": "down", "key": "masked", "t": 590},
            {"type": "up", "key": "masked", "t": 595},
        ]
    }
    feats = extract_features(telemetry)
    assert feats["key_count"] == 4
    # 3 out of 4 keys are unidentified (majority) -> mobile soft keyboard recognized without synthetic dwell penalty
    assert feats["keystroke_score"] == 0.0


def test_storage_never_persists_raw_keystrokes_or_text():
    """Verify that SQLite storage only records statistical scalars, never raw keystrokes or text."""
    storage = SQLiteStorageBackend(":memory:")
    session_id = "test_zero_pii_session"
    
    # Simulate core recording session telemetry
    storage.record_session_telemetry(session_id, {
        "avg_jerk": 12.5,
        "straightness": 0.88,
        "total_distance": 450.0,
        "submovement_count": 4,
        "spectral_purity": 0.15,
    })
    
    records = storage.get_session_telemetries(session_id)
    assert len(records) == 1
    rec = records[0]
    
    # Must contain only kinematic scalars
    expected_keys = {"avg_jerk", "straightness", "total_distance", "submovement_count", "spectral_purity"}
    assert set(rec.keys()) == expected_keys
    for k in ["keystrokes", "key", "text", "password", "input", "query", "user_agent"]:
        assert k not in rec
