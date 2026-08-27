import os
import sys
import argparse
import json
import sqlite3
import uvicorn
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, List

from .engine import analyze_behavior
from . import live_attacker

DB_FILE = "synapse_shield.db"

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
    conn.commit()
    conn.close()

app = FastAPI(title="Synapse Shield - Behavioral Bot Detection Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_recent_request_count(ip: str) -> int:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    ten_seconds_ago = (datetime.utcnow() - timedelta(seconds=10)).isoformat()
    cursor.execute(
        "SELECT COUNT(*) FROM logs WHERE ip = ? AND timestamp > ?",
        (ip, ten_seconds_ago)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count + 1

def save_log(ip: str, user_agent: str, bot_score: float, classification: str, reasons: List[str], features: Dict[str, Any], telemetry: Dict[str, Any]):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        """
        INSERT INTO logs (timestamp, ip, user_agent, bot_score, classification, reasons, features, telemetry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            ip,
            user_agent,
            bot_score,
            classification,
            json.dumps(reasons),
            json.dumps(features),
            json.dumps(telemetry)
        )
    )
    conn.commit()
    conn.close()

@app.post("/api/score")
async def score_telemetry(request: Request):
    try:
        telemetry = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown")
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()

    recent_count = get_recent_request_count(ip)
    bot_score, classification, reasons, details = analyze_behavior(telemetry, recent_count)
    save_log(ip, user_agent, bot_score, classification, reasons, details["features"], telemetry)

    return {
        "status": "success",
        "bot_score": bot_score,
        "classification": classification,
        "reasons": reasons,
        "details": details
    }

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, timestamp, ip, user_agent, bot_score, classification, reasons, features FROM logs ORDER BY id DESC LIMIT ?",
        (limit,)
    )
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
            "reasons": json.loads(r["reasons"]),
            "features": json.loads(r["features"])
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
async def clear_logs():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Database logs successfully cleared"}

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")

@app.get("/")
def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Synapse Shield Static files directory mapping incomplete. Place index.html inside the static folder.</h2>")

@app.get("/static/synapse-sdk.js")
def read_sdk():
    sdk_path = os.path.join(STATIC_DIR, "synapse-sdk.js")
    if os.path.exists(sdk_path):
        return FileResponse(sdk_path, media_type="application/javascript")
    return HTMLResponse("<h2>synapse-sdk.js file missing.</h2>", status_code=404)

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def main():
    parser = argparse.ArgumentParser(description="Synapse Shield CLI Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run parser
    run_parser = subparsers.add_parser("run", help="Start the FastAPI behavioral scoring backend dashboard")
    run_parser.add_argument("--host", default="0.0.0.0", help="Binding host address")
    run_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")

    # Test parser
    test_parser = subparsers.add_parser("test", help="Run the automated bot attack simulation suite")
    test_parser.add_argument("--target", default="http://127.0.0.1:8000/api/score", help="Dashboard scoring API endpoint")

    args = parser.parse_args()

    if args.command == "run":
        init_db()
        uvicorn.run(app, host=args.host, port=args.port)
    elif args.command == "test":
        live_attacker.main(target_url=args.target)

if __name__ == "__main__":
    main()
