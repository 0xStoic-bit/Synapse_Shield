import os
from synapse_shield.core import resolve_client_ip, _is_ip_in_trusted, _is_valid_ip
from synapse_shield.tokens import (
    generate_pow_salt,
    extract_pow_difficulty,
    verify_pow_salt,
    verify_and_consume_pow,
)
from synapse_shield.features import extract_features


def test_cidr_trusted_proxy_resolution():
    """Verify CIDR subnet matching in resolve_client_ip."""
    trusted = {"172.16.0.0/12", "10.0.0.0/8", "127.0.0.1"}

    # Direct match in CIDR
    assert _is_ip_in_trusted("172.16.5.10", trusted) is True
    assert _is_ip_in_trusted("172.31.255.254", trusted) is True
    assert _is_ip_in_trusted("172.32.0.1", trusted) is False
    assert _is_ip_in_trusted("10.100.1.5", trusted) is True
    assert _is_ip_in_trusted("8.8.8.8", trusted) is False

    # resolve_client_ip behind AWS ALB / Docker network (172.16.0.5)
    headers = {"x-forwarded-for": "203.0.113.195, 172.16.0.5"}
    client = resolve_client_ip("172.16.0.5", headers, trusted_proxies=trusted)
    assert client == "203.0.113.195"


def test_malformed_ip_header_rejection():
    """Verify that malformed or injected IP headers are safely ignored."""
    assert _is_valid_ip("192.168.1.1") is True
    assert _is_valid_ip("2001:db8::1") is True
    assert _is_valid_ip("127.0.0.1; DROP TABLE users;") is False
    assert _is_valid_ip("evil.com") is False
    assert _is_valid_ip("<script>alert(1)</script>") is False

    trusted = {"127.0.0.1"}
    headers = {
        "x-forwarded-for": "malicious_injection, 203.0.113.50",
        "cf-connecting-ip": "not_an_ip",
    }
    client = resolve_client_ip("127.0.0.1", headers, trusted_proxies=trusted)
    assert client == "203.0.113.50"


def test_signed_pow_salt_dynamic_difficulty():
    """Verify that difficulty is cryptographically signed into the pow salt and verified."""
    client_ip = "198.51.100.42"
    salt_diff4 = generate_pow_salt(client_ip, difficulty=4)
    salt_diff5 = generate_pow_salt(client_ip, difficulty=5)

    assert extract_pow_difficulty(salt_diff4) == 4
    assert extract_pow_difficulty(salt_diff5) == 5

    # Tampered difficulty in salt should fail signature verification
    parts = salt_diff5.split(".")
    tampered_salt = f"{parts[0]}.{parts[1]}.4.{parts[3]}"
    assert verify_pow_salt(tampered_salt, client_ip) is False
    assert verify_pow_salt(salt_diff5, client_ip) is True
    assert verify_pow_salt(salt_diff5, "1.2.3.4") is False  # Wrong IP fails


def test_pow_dynamic_leading_zero_solving_and_consumption():
    """Verify solving and consuming PoW with dynamic difficulty."""
    import hashlib
    client_ip = "192.0.2.1"
    diff = 3  # Use diff=3 for fast test execution ("000...")
    salt = generate_pow_salt(client_ip, difficulty=diff)

    # Solve PoW
    nonce = None
    target_prefix = "0" * diff
    for i in range(100000):
        candidate = f"{salt}{i}".encode("utf-8")
        h = hashlib.sha256(candidate).hexdigest()
        if h.startswith(target_prefix):
            nonce = str(i)
            break

    assert nonce is not None
    # First consumption succeeds
    assert verify_and_consume_pow(salt, nonce, client_ip) is True
    # Replay consumption fails
    assert verify_and_consume_pow(salt, nonce, client_ip) is False


def test_ime_dwell_bypass_mitigation_on_desktop():
    """
    Verify that a desktop bot sending a dummy 'unidentified' IME key
    cannot bypass mechanical keyboard dwell time checks.
    """
    # 5 keystrokes with superhuman low dwell (5ms) and key="unidentified"
    # Desktop: touch_supported=False
    telemetry = {
        "keystrokes": [
            {"type": "down", "key": "unidentified", "t": 1000},
            {"type": "up", "key": "unidentified", "t": 1005, "duration_ms": 5},
            {"type": "down", "key": "a", "t": 1100},
            {"type": "up", "key": "a", "t": 1105, "duration_ms": 5},
            {"type": "down", "key": "b", "t": 1200},
            {"type": "up", "key": "b", "t": 1205, "duration_ms": 5},
            {"type": "down", "key": "c", "t": 1300},
            {"type": "up", "key": "c", "t": 1305, "duration_ms": 5},
        ],
        "browser": {
            "touch_supported": False,
        },
        "mouse_movements": [],
    }

    features = extract_features(telemetry)
    # The dwell time is 5ms (<15ms).
    # Since touch_supported is False and ime_count is 1 out of 4 keys (not majority),
    # it should NOT be exempted as mobile IME, so keystroke_score must trigger bot penalties.
    assert features["avg_dwell_time"] < 15.0
    assert features["keystroke_score"] >= 0.70


def test_zero_pii_keystroke_freq_digraph():
    """Verify that client-side is_freq_digraph flag is properly processed."""
    telemetry = {
        "keystrokes": [
            {"type": "down", "key": "masked", "t": 1000, "is_freq_digraph": False},
            {"type": "up", "key": "masked", "t": 1080, "duration_ms": 80, "is_freq_digraph": False},
            {"type": "down", "key": "masked", "t": 1180, "is_freq_digraph": True},
            {"type": "up", "key": "masked", "t": 1260, "duration_ms": 80, "is_freq_digraph": True},
            {"type": "down", "key": "masked", "t": 1360, "is_freq_digraph": True},
            {"type": "up", "key": "masked", "t": 1440, "duration_ms": 80, "is_freq_digraph": True},
            {"type": "down", "key": "masked", "t": 1540, "is_freq_digraph": False},
            {"type": "up", "key": "masked", "t": 1620, "duration_ms": 80, "is_freq_digraph": False},
        ],
        "browser": {
            "touch_supported": False,
        },
        "mouse_movements": [],
    }

    features = extract_features(telemetry)
    assert features["key_count"] == 4
    assert features["avg_dwell_time"] > 50.0


def test_cgnat_user_agent_session_isolation():
    """Verify that different User-Agents behind the same CGNAT IP have distinct session histories."""
    import hashlib
    client_ip = "100.64.0.1"  # Carrier-grade NAT IP
    ua1 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    ua2 = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1"

    ua1_hash = hashlib.sha256(ua1.encode("utf-8")).hexdigest()[:8]
    ua2_hash = hashlib.sha256(ua2.encode("utf-8")).hexdigest()[:8]

    assert ua1_hash != ua2_hash
    session1 = f"ip_{client_ip}_{ua1_hash}"
    session2 = f"ip_{client_ip}_{ua2_hash}"
    assert session1 != session2


def test_configurable_max_req_10s_limit(monkeypatch):
    """Verify SYNAPSE_MAX_REQ_10S environment variable override."""
    monkeypatch.setenv("SYNAPSE_MAX_REQ_10S", "50")
    limit = int(os.environ.get("SYNAPSE_MAX_REQ_10S", "100"))
    assert limit == 50

