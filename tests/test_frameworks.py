import json
from unittest.mock import MagicMock


def test_flask_middleware():
    from flask import Flask

    from synapse_shield.flask import shield_protect_flask
    
    app = Flask(__name__)
    
    @app.route("/api/test", methods=["POST"])
    @shield_protect_flask(max_risk_score=50.0)
    def test_route():
        return "OK"
    
    client = app.test_client()
    
    # Invalid telemetry payload -> 403
    res1 = client.post("/api/test", data="invalid json")
    assert res1.status_code == 403
    assert "Missing" in res1.json["error"]
    
    # Clean Human -> 200 OK
    res2 = client.post("/api/test", json={
        "telemetry": {
            "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [{"x": 100+i, "y": 100+i, "t": i*20} for i in range(20)]
        }
    })
    assert res2.status_code == 200
    assert res2.data == b"OK"
    
    # Bot (Webdriver) -> 403 Blocked
    res3 = client.post("/api/test", json={
        "telemetry": {
            "browser": {"webdriver": True}
        }
    })
    assert res3.status_code == 403
    assert "Access Denied" in res3.json["error"]

def test_django_middleware():
    from django.conf import settings

    from synapse_shield.django import SynapseShieldMiddleware
    
    if not settings.configured:
        settings.configure(
            SYNAPSE_SHIELD_PROTECTED_PATHS=['/api/protected'],
            SYNAPSE_SHIELD_MAX_RISK=50.0
        )
        
    middleware = SynapseShieldMiddleware(get_response=lambda r: "OK")
    
    # Mock GET request (not protected)
    req_get = MagicMock()
    req_get.path = "/api/protected"
    req_get.method = "GET"
    assert middleware.process_request(req_get) is None
    
    # Mock POST request (unprotected path)
    req_post_unprotected = MagicMock()
    req_post_unprotected.path = "/api/public"
    req_post_unprotected.method = "POST"
    assert middleware.process_request(req_post_unprotected) is None
    
    # Mock POST request (protected path, missing body)
    req_post_protected = MagicMock()
    req_post_protected.path = "/api/protected"
    req_post_protected.method = "POST"
    req_post_protected.body = b'invalid json'
    
    response = middleware.process_request(req_post_protected)
    assert response.status_code == 403
    assert b"Missing or invalid" in response.content
    
    # Clean human payload
    human_payload = {
        "telemetry": {
            "browser": {"webdriver": False, "plugins_length": 3, "screen_width": 1920, "screen_height": 1080},
            "mouse_movements": [{"x": 100+i, "y": 100+i, "t": i*20} for i in range(20)]
        }
    }
    req_post_protected.body = json.dumps(human_payload).encode()
    response2 = middleware.process_request(req_post_protected)
    assert response2 is None  # Allowed
    
    # Bot payload
    bot_payload = {"telemetry": {"browser": {"webdriver": True}}}
    req_post_protected.body = json.dumps(bot_payload).encode()
    response3 = middleware.process_request(req_post_protected)
    assert response3.status_code == 403
    assert b"Access Denied" in response3.content
