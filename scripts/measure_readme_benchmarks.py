"""Re-measure the README "Attack Simulation Benchmarks" table against the in-process server.

Usage:  python scripts/measure_readme_benchmarks.py   (no server needed, nothing leaves the machine)

Decision / risk: real POST /api/score (TestClient bound to 127.0.0.1, a trusted proxy, so each
vector gets its own X-Forwarded-For IP, exactly like `synapse-shield test` against a dev server).
Latency: median wall time of engine.analyze_behavior() over 200 runs on that vector's telemetry.
"""
import base64
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time

os.environ["SYNAPSE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "synapse_bench_measure.db")
os.environ["SYNAPSE_ADMIN_SECRET"] = "bench"
os.environ.setdefault("SYNAPSE_MIN_ELAPSED_MS", "0")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from fastapi.testclient import TestClient  # noqa: E402

from synapse_shield.engine import analyze_behavior  # noqa: E402
from synapse_shield.main import app  # noqa: E402

client = TestClient(app, client=("127.0.0.1", 50000))
ADMIN = {"X-Admin-Secret": "bench"}


def headers(name, ip):
    ua = name.encode("ascii", "ignore").decode()
    return {"User-Agent": f"BenchBot ({ua})", "x-forwarded-for": f"198.51.100.{ip}"}


def score(name, ip, telemetry, token_override=None):
    h = headers(name, ip)
    if token_override is None:
        ch = client.get("/api/challenge", headers=h).json()["challenge"]
        env = {"challenge": ch, "telemetry": telemetry, "created_at": int(time.time() * 1000)}
        token = base64.b64encode(json.dumps(env).encode()).decode()
    else:
        token = token_override
    r = client.post("/api/score", json={"token": token}, headers=h)
    body = r.json()
    if "classification" not in body:  # gateway rejection {"detail": ...}
        body = {"classification": "Bot", "bot_score": 100.0, "reasons": [body.get("detail")], "http": r.status_code}
    return body, token


def latency_ms(telemetry):
    runs = []
    for _ in range(200):
        t0 = time.perf_counter()
        analyze_behavior(telemetry, 1, False, False, [])
        runs.append((time.perf_counter() - t0) * 1000)
    return statistics.median(runs)


def human_trace(rng, t):
    pts, ht = [], t
    for i in range(40):
        progress = 1 - (1 - i / 39) ** 2
        pts.append({"x": round(100 + progress * 600 + rng.gauss(0, 2.5)),
                    "y": round(150 + math.sin(i / 3) * 20 + rng.gauss(0, 2.5)), "t": ht})
        ht += rng.randint(14, 38)
    return {"mouse_movements": pts, "clicks": [{"x": pts[-1]["x"], "y": pts[-1]["y"], "t": ht + 120}],
            "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "max_touch_points": 0,
                        "plugins_length": 5}}


client.post("/api/clear", headers=ADMIN)
t = int(time.time() * 1000)
p0, p1, p2 = (50, 50), (400, 700), (900, 200)
vectors = {
    "Selenium Crawler": {"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}},
    "Linear Bot": {"mouse_movements": [{"x": 50 + i * 30, "y": 50 + i * 20, "t": t + i * 20} for i in range(25)]},
    "Bézier Stealth Bot": {"mouse_movements": [
        {"x": round((1 - i / 30) ** 2 * p0[0] + 2 * (1 - i / 30) * (i / 30) * p1[0] + (i / 30) ** 2 * p2[0]),
         "y": round((1 - i / 30) ** 2 * p0[1] + 2 * (1 - i / 30) * (i / 30) * p1[1] + (i / 30) ** 2 * p2[1]),
         "t": t + i * 20} for i in range(30)]},
    "Robotic Auto-Typer": {"keystrokes": [{"type": "down", "key": "masked", "t": t + i * 50} for i in range(12)],
                           "clicks": [{"x": 100, "y": 100, "t": t}]},
}
rows = []
for n, (name, tel) in enumerate(vectors.items()):
    body, _ = score(name, 10 + n, tel)
    rows.append((name, body["classification"], body["bot_score"], body.get("threat_type"), latency_ms(tel), body.get("reasons", [])[:2]))

# Poisson flooder: 8 valid human-looking tokens from one IP inside 500 ms.
rng = random.Random(7)
client.post("/api/clear", headers=ADMIN)
tokens_ = []
for _ in range(8):
    h = headers("Flood", 40)
    ch = client.get("/api/challenge", headers=h).json()["challenge"]
    env = {"challenge": ch, "telemetry": human_trace(rng, t), "created_at": int(time.time() * 1000)}
    tokens_.append(base64.b64encode(json.dumps(env).encode()).decode())
t0 = time.perf_counter()
flood = [score("Flood", 40, None, tok)[0] for tok in tokens_]
flood_ms = (time.perf_counter() - t0) * 1000
blocked = sum(1 for b in flood if b["classification"] == "Bot")
rows.append(("Poisson Flooder", f"{blocked}/8 Bot", flood[-1]["bot_score"], flood[-1].get("threat_type"),
             latency_ms(human_trace(rng, t)), [f"8 req in {flood_ms:.0f} ms", *flood[-1].get("reasons", [])[:1]]))

# Replay: same IP + UA, same token twice.
client.post("/api/clear", headers=ADMIN)
first, tok = score("Replay", 50, human_trace(random.Random(1), t))
second, _ = score("Replay", 50, None, tok)
rows.append(("Replay Attack", second["classification"], second["bot_score"], second.get("threat_type"), 0.0,
             [f"1st send: {first['classification']}", *second.get("reasons", [])[:1]]))

# Natural human: 50 seeds, each from its own IP.
client.post("/api/clear", headers=ADMIN)
human_scores, human_bot = [], 0
for seed in range(50):
    tel = human_trace(random.Random(1000 + seed), t)
    body, _ = score("Human", 100 + seed, tel)
    human_scores.append(body["bot_score"])
    human_bot += body["classification"] == "Bot"
rows.append(("Natural Human", f"{50 - human_bot}/50 Human", statistics.median(human_scores), "CLEAN_HUMAN",
             latency_ms(human_trace(random.Random(1000), t)), [f"max risk {max(human_scores):.1f}%"]))

out = [{"vector": r[0], "decision": r[1], "risk": r[2], "threat": r[3], "latency_ms": round(r[4], 3), "reasons": r[5]} for r in rows]
print(json.dumps(out, indent=1, ensure_ascii=False))
