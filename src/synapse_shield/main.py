import os
import tempfile
import json
import sqlite3
# pyrefly: ignore [missing-import]
import uvicorn
import asyncio
import threading
import atexit
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, List

from synapse_shield.engine import analyze_behavior
from synapse_shield import tokens
from synapse_shield.middleware import shield_protect, SynapseShieldMiddleware
from synapse_shield.tokens import verify_and_consume_token, generate_challenge

DB_FILE = os.environ.get("SYNAPSE_DB_PATH", os.path.join(tempfile.gettempdir(), "synapse_shield.db"))

# Thread-local SQLite bağlantı yönetimi
# NOT: asyncio.to_thread ile kullanıldığında, ThreadPoolExecutor'dan farklı thread'ler
# gelebilir. Küçük ölçekte (default pool_size=min(32, os.cpu_count()+4)) sorun olmaz,
# ancak yüksek ölçekte connection sayısı pool_size kadar olabilir.
_thread_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Thread-local SQLite bağlantısı döndürür. Her thread kendi connection'ını kullanır."""
    conn = getattr(_thread_local, "connection", None)
    if conn is None:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA wal_autocheckpoint=1000;")
        _thread_local.connection = conn
    return conn


def _cleanup_connections():
    """atexit hook: Thread-local bağlantıları temizle."""
    conn = getattr(_thread_local, "connection", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass


atexit.register(_cleanup_connections)

def init_db():
    conn = get_connection()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_ips (
            ip TEXT PRIMARY KEY,
            banned_until TEXT,
            reason TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_nonces (
            nonce TEXT PRIMARY KEY,
            expires_at INTEGER
        )
    """)
    conn.commit()

init_db()

app = FastAPI(title="Synapse Shield - Behavioral Bot Detection Engine")


def _get_cors_origins() -> list:
    """
    CORS origin listesini belirler:
    1. SYNAPSE_CORS_ORIGINS env variable'ı (virgülle ayrılmış origin'ler)
    2. SYNAPSE_DEV_MODE=1 ise yaygın localhost port'ları otomatik eklenir
    3. Hiçbiri yoksa CORS middleware eklenmez
    """
    env_origins = os.environ.get("SYNAPSE_CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    if os.environ.get("SYNAPSE_DEV_MODE", "").lower() in ("1", "true", "yes"):
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8080",
        ]
    return []


_cors_origins = _get_cors_origins()

if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

TRUSTED_PROXIES = {"127.0.0.1", "::1"}

def get_client_ip(request: Request) -> str:
    client_ip = request.client.host if request.client else "127.0.0.1"
    if client_ip in TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client_ip

def get_recent_request_count(ip: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    ten_seconds_ago = (datetime.utcnow() - timedelta(seconds=10)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM logs WHERE ip = ? AND timestamp > ?", (ip, ten_seconds_ago))
    count = cursor.fetchone()[0]
    return count + 1

def is_ip_banned(ip: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT banned_until FROM banned_ips WHERE ip = ?", (ip,))
    row = cursor.fetchone()
    if row:
        banned_until = datetime.fromisoformat(row[0])
        if datetime.utcnow() < banned_until:
            return True
        else:
            cursor.execute("DELETE FROM banned_ips WHERE ip = ?", (ip,))
            conn.commit()
    return False

def ban_ip(ip: str, minutes: int, reason: str):
    banned_until = (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "REPLACE INTO banned_ips (ip, banned_until, reason) VALUES (?, ?, ?)",
        (ip, banned_until, reason)
    )
    conn.commit()


def save_log(ip: str, user_agent: str, bot_score: float, classification: str, reasons: List[str], features: Dict[str, Any], telemetry: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        """
        INSERT INTO logs (timestamp, ip, user_agent, bot_score, classification, reasons, features, telemetry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now, ip, user_agent, bot_score, classification, json.dumps(reasons), json.dumps(features), json.dumps(telemetry))
    )
    # Otomatik temizlik: sadece son 5000 logu tut
    cursor.execute("""
        DELETE FROM logs 
        WHERE id NOT IN (
            SELECT id FROM logs 
            ORDER BY id DESC 
            LIMIT 5000
        )
    """)
    conn.commit()

# YENİ ENDPOINT: İstemciye tek kullanımlık challenge verir
@app.get("/api/challenge")
async def get_challenge():
    return generate_challenge()

@app.post("/api/score")
async def score_telemetry(request: Request):
    ip = get_client_ip(request)
    
    if is_ip_banned(ip):
        raise HTTPException(status_code=403, detail="IP address temporarily banned due to suspicious activity.")

    user_agent = request.headers.get("user-agent", "Unknown")
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    token = body.get("token")
    if not token:
        raise HTTPException(status_code=403, detail="[Synapse Shield] Missing token.")

    # 1. Kriptografik Token Varsa Doğrula
    is_valid, reason, telemetry = verify_and_consume_token(token)
    if not is_valid:
        # Replay Attack veya sahte token durumu
        save_log(ip, user_agent, 100.0, "Bot", [reason], {}, {})
        return {
            "status": "blocked",
            "bot_score": 100.0,
            "classification": "Bot",
            "reasons": [reason],
            "details": {}
        }

    recent_count = get_recent_request_count(ip)
    if recent_count > 100:
        ban_ip(ip, 15, "Extreme request frequency (DoS/Brute-force protection)")
        raise HTTPException(status_code=403, detail="IP address banned due to extreme request frequency.")
    
    bot_score, classification, reasons, details = await asyncio.to_thread(analyze_behavior, telemetry, recent_count)
    
    save_log(ip, user_agent, bot_score, classification, reasons, details.get("features", {}), telemetry)
    
    # Dinamik Ceza Havuzu: 4 ardışık bot aktivitesinden sonra IP'yi 60 saniye boyunca (1 dakika) engelle
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT classification FROM logs WHERE ip = ? ORDER BY id DESC LIMIT 4", (ip,))
    rows = cursor.fetchall()
    
    if len(rows) == 4 and all(r[0] == "Bot" for r in rows):
        ban_ip(ip, 1, "4 consecutive malicious bot requests detected (Dynamic Throttling)")
        
    return {
        "status": "success",
        "bot_score": bot_score,
        "classification": classification,
        "reasons": reasons,
        "details": details
    }

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    conn = get_connection()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    cursor.execute("DELETE FROM banned_ips")
    conn.commit()
    return {"status": "success", "message": "Database logs and bans cleared"}

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

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    try:
        uvicorn.run("synapse_shield.main:app", host="0.0.0.0", port=8000, reload=True)
    except Exception:
        uvicorn.run(app, host="0.0.0.0", port=8000)