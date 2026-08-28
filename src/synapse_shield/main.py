import hmac
import json
import os
import sqlite3
import threading
import time
import warnings
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, List

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .engine import analyze_behavior
from .tokens import SECRET_KEY_IS_EPHEMERAL, generate_challenge, verify_and_consume_token

DB_FILE = os.environ.get("SYNAPSE_SHIELD_DB", "synapse_shield.db")
ADMIN_TOKEN = os.environ.get("SYNAPSE_SHIELD_ADMIN_TOKEN", "")

if SECRET_KEY_IS_EPHEMERAL:
    warnings.warn(
        "SYNAPSE_SHIELD_SECRET_KEY is not set; using an ephemeral random key. "
        "Challenge tokens will not survive a restart or work across multiple "
        "workers. Set SYNAPSE_SHIELD_SECRET_KEY for production.",
        RuntimeWarning,
        stacklevel=2,
    )
if not ADMIN_TOKEN:
    warnings.warn(
        "SYNAPSE_SHIELD_ADMIN_TOKEN is not set; /api/logs and /api/clear are "
        "exposed without authentication. Set it to require a Bearer/X-Admin-Token header.",
        RuntimeWarning,
        stacklevel=2,
    )


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ip TEXT,
            user_agent TEXT,
            bot_score REAL,
            classification TEXT,
            reasons TEXT,
            features TEXT,
            telemetry TEXT
        )
    """)
    cursor.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()


init_db()

app = FastAPI(title="Synapse Shield - Behavioral Bot Detection Engine")

_cors_env = os.environ.get("SYNAPSE_SHIELD_CORS_ORIGINS", "*").strip()
_cors_origins = ["*"] if _cors_env == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

TRUSTED_PROXIES = {"127.0.0.1", "::1"}

_RATE_WINDOW_SEC = 10.0
_RATE_LOCK = threading.Lock()
_REQ_TIMES: Dict[str, Deque[float]] = defaultdict(deque)


def record_and_count_recent(ip: str) -> int:
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW_SEC
    with _RATE_LOCK:
        dq = _REQ_TIMES[ip]
        dq.append(now)
        while dq and dq[0] < cutoff:
            dq.popleft()
        count = len(dq)
        if len(_REQ_TIMES) > 10000:
            for key in [k for k, v in list(_REQ_TIMES.items()) if not v or v[-1] < cutoff]:
                _REQ_TIMES.pop(key, None)
        return count


def require_admin(request: Request) -> None:
    if not ADMIN_TOKEN:
        return
    supplied = request.headers.get("x-admin-token", "")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


def get_client_ip(request: Request) -> str:
    client_ip = request.client.host if request.client else "127.0.0.1"
    if client_ip in TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client_ip


def save_log(ip: str, user_agent: str, bot_score: float, classification: str, reasons: List[str], features: Dict[str, Any], telemetry: Dict[str, Any]):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        """
        INSERT INTO logs (timestamp, ip, user_agent, bot_score, classification, reasons, features, telemetry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now, ip, user_agent, bot_score, classification, json.dumps(reasons), json.dumps(features), json.dumps(telemetry))
    )
    conn.commit()
    conn.close()


# İstemciye tek kullanımlık challenge verir
@app.get("/api/challenge")
async def get_challenge():
    return generate_challenge()


@app.post("/api/score")
async def score_telemetry(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "Unknown")

    # 1. Kriptografik Token Varsa Doğrula
    if isinstance(body, dict) and "token" in body:
        is_valid, reason, telemetry = verify_and_consume_token(body["token"])
        if not is_valid:
            # Replay Attack veya sahte token durumu
            background_tasks.add_task(save_log, ip, user_agent, 100.0, "Bot", [reason], {}, {})
            return {
                "status": "blocked",
                "bot_score": 100.0,
                "classification": "Bot",
                "reasons": [reason],
                "details": {}
            }
    else:
        # Geriye dönük uyumluluk: doğrudan telemetri gönderildiyse
        telemetry = body.get("telemetry", body) if isinstance(body, dict) else {}

    recent_count = record_and_count_recent(ip)
    bot_score, classification, reasons, details = analyze_behavior(telemetry, recent_count)
    background_tasks.add_task(
        save_log, ip, user_agent, bot_score, classification, reasons, details.get("features", {}), telemetry
    )

    return {
        "status": "success",
        "bot_score": bot_score,
        "classification": classification,
        "reasons": reasons,
        "details": details
    }


@app.get("/api/logs")
async def get_logs(limit: int = 50, _: None = Depends(require_admin)):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, ip, user_agent, bot_score, classification, reasons, features FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()

    recent_logs = []
    for r in rows:
        recent_logs.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "ip": r["ip"],
            "user_agent": r["user_agent"],
            "bot_score": r["bot_score"],
            "classification": r["classification"],
            "reasons": json.loads(r["reasons"]) if r["reasons"] else [],
            "features": json.loads(r["features"]) if r["features"] else {}
        })

    cursor.execute("SELECT COUNT(*) FROM logs")
    total_requests = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM logs WHERE classification = 'Bot'")
    bot_requests = cursor.fetchone()[0]
    cursor.execute("SELECT AVG(bot_score) FROM logs WHERE classification = 'Bot'")
    avg_bot = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT AVG(bot_score) FROM logs WHERE classification = 'Human'")
    avg_human = cursor.fetchone()[0] or 0.0
    conn.close()

    return {
        "total_requests": total_requests,
        "bot_requests": bot_requests,
        "human_requests": total_requests - bot_requests,
        "bot_ratio": (bot_requests / total_requests * 100) if total_requests > 0 else 0.0,
        "avg_bot_score": round(avg_bot, 2),
        "avg_human_score": round(avg_human, 2),
        "logs": recent_logs
    }


@app.post("/api/clear")
async def clear_logs(_: None = Depends(require_admin)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Database logs cleared"}


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/")
def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Synapse Shield Cockpit: index.html missing.</h2>")


@app.get("/static/synapse-sdk.js")
def read_sdk():
    sdk_path = os.path.join(STATIC_DIR, "synapse-sdk.js")
    if os.path.exists(sdk_path):
        return FileResponse(sdk_path, media_type="application/javascript")
    return HTMLResponse("<h2>synapse-sdk.js missing.</h2>", status_code=404)


if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run("synapse_shield.main:app", host="0.0.0.0", port=8000, reload=True)
