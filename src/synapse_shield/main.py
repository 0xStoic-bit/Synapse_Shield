import asyncio
import atexit
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
import urllib.request
import urllib.error
import urllib.parse
import hmac

# pyrefly: ignore [missing-import]
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from synapse_shield.engine import analyze_behavior
from synapse_shield.storage import get_storage
from synapse_shield.tokens import (
    generate_challenge,
    generate_pow_salt,
    verify_and_consume_token,
    verify_pow_salt,
    verify_and_consume_pow,
)

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
            threat_type TEXT DEFAULT 'UNKNOWN',
            reasons TEXT,
            features TEXT,
            telemetry TEXT
        )
    """)
    # Migration check: eğer logs tablosu önceden varsa ve threat_type kolonu yoksa ekle
    cursor.execute("PRAGMA table_info(logs)")
    columns = [col[1] for col in cursor.fetchall()]
    if "threat_type" not in columns:
        cursor.execute("ALTER TABLE logs ADD COLUMN threat_type TEXT DEFAULT 'UNKNOWN'")

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_settings (
            id INTEGER PRIMARY KEY,
            discord_url TEXT,
            telegram_token TEXT,
            telegram_chat_id TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO webhook_settings (id, discord_url, telegram_token, telegram_chat_id) VALUES (1, '', '', '')")
    conn.commit()

init_db()

DATASET_DB_FILE = os.environ.get("SYNAPSE_DATASET_PATH", os.path.join(tempfile.gettempdir(), "synapse_dataset.db"))
_dataset_thread_local = threading.local()

def get_dataset_connection() -> sqlite3.Connection:
    conn = getattr(_dataset_thread_local, "connection", None)
    if conn is None:
        conn = sqlite3.connect(DATASET_DB_FILE, check_same_thread=False, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        _dataset_thread_local.connection = conn
    return conn

def init_dataset_db():
    conn = get_dataset_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            mouse_movements TEXT,
            keystrokes TEXT,
            clicks TEXT,
            scrolls TEXT,
            browser TEXT
        )
    """)
    conn.commit()

init_dataset_db()

app = FastAPI(title="Synapse Shield - Behavioral Bot Detection Engine")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()


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
    ten_seconds_ago = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM logs WHERE ip = ? AND timestamp > ?", (ip, ten_seconds_ago))
    count = cursor.fetchone()[0]
    return count + 1

def is_ip_banned(ip: str) -> bool:
    return get_storage().is_ip_banned(ip)


def record_ip_decision(ip: str, is_bot: bool):
    """
    Sliding Window (Kayan Pencere) Tabanlı Dinamik IP Karantina Takibi:
    Son 60 saniye içerisinde 4 veya daha fazla bot kararı tespit edilirse IP 1 dakika banlanır.
    """
    if is_bot:
        get_storage().record_bot_strike(
            ip,
            threshold=4,
            window_sec=60,
            ban_duration_sec=60,
            reason="High bot density in sliding time window (4 bot requests in last 60 seconds)",
        )


def ban_ip(ip: str, minutes: int, reason: str):
    get_storage().ban_ip(ip, duration_sec=minutes * 60, reason=reason)


def save_log(
    ip: str, 
    user_agent: str, 
    bot_score: float, 
    classification: str, 
    threat_type: str, 
    reasons: list[str], 
    features: dict[str, Any], 
    telemetry: dict[str, Any]
):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        INSERT INTO logs (timestamp, ip, user_agent, bot_score, classification, threat_type, reasons, features, telemetry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now, ip, user_agent, bot_score, classification, threat_type, json.dumps(reasons), json.dumps(features), json.dumps(telemetry))
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

def send_webhook_notification(ip: str, threat_type: str, risk_score: float, reasons: list[str]):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT discord_url, telegram_token, telegram_chat_id FROM webhook_settings WHERE id = 1")
        row = cursor.fetchone()
        if not row:
            return
        discord_url, telegram_token, telegram_chat_id = row
        
        # Don't do anything if no webhooks are configured
        if not discord_url and not (telegram_token and telegram_chat_id):
            return
            
        reason_str = reasons[0] if reasons else "Unknown anomaly"
        now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")
        
        if discord_url and discord_url.startswith("http"):
            discord_payload = {
                "embeds": [{
                    "title": "🚨 [SYNAPSE SHIELD] KRİTİK TEHDİT ENGELLENDİ",
                    "color": 16711680,
                    "description": (
                        f"**• Hedef IP:** `{ip}` (Banned)\n"
                        f"**• Tehdit Türü:** `{threat_type}`\n"
                        f"**• Risk Skoru:** `%{(risk_score):.1f}` (BLOCK)\n"
                        f"**• Tetiklenen:** {reason_str}\n"
                        f"**• Zaman:** {now_str}"
                    )
                }]
            }
            req = urllib.request.Request(
                discord_url,
                data=json.dumps(discord_payload).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'User-Agent': 'SynapseShield/1.0'}
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
                
        if telegram_token and telegram_chat_id:
            msg = (
                "🚨 *[SYNAPSE SHIELD] KRİTİK TEHDİT ENGELLENDİ*\n"
                "─────────────────────────────\n"
                f"• *Hedef IP:* `{ip}` (Banned)\n"
                f"• *Tehdit Türü:* `{threat_type}`\n"
                f"• *Risk Skoru:* `%{(risk_score):.1f}` (BLOCK)\n"
                f"• *Tetiklenen:* {reason_str}\n"
                f"• *Zaman:* {now_str}"
            )
            tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            tg_payload = {
                "chat_id": telegram_chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            }
            req = urllib.request.Request(
                tg_url,
                data=json.dumps(tg_payload).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'User-Agent': 'SynapseShield/1.0'}
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
    except Exception as e:
        print(f"Webhook Notification Error: {e}")

def verify_admin(request: Request):
    """Admin endpoint'leri için yetkilendirme doğrulaması."""
    admin_secret = os.environ.get("SYNAPSE_ADMIN_SECRET")
    if admin_secret:
        provided_secret = request.headers.get("X-Admin-Secret") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not provided_secret or not hmac.compare_digest(provided_secret, admin_secret):
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin secret")
    elif os.environ.get("SYNAPSE_DEV_MODE", "0") != "1":
        raise HTTPException(status_code=403, detail="Forbidden: Admin operations disabled in production without secret")

ALLOWED_WEBHOOK_DOMAINS = {
    "discord.com",
    "discordapp.com",
    "api.telegram.org",
}

def validate_webhook_url(url: str):
    """SSRF ve DNS Rebinding koruması: Sadece izinli resmi webhook alan adları kabul edilir."""
    if not url:
        return
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Only HTTPS allowed for webhooks")
    hostname = (parsed.hostname or "").lower()
    is_allowed = any(
        hostname == d or hostname.endswith("." + d)
        for d in ALLOWED_WEBHOOK_DOMAINS
    )
    if not is_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid webhook domain '{hostname}'. Only official Discord and Telegram domains are allowed."
        )

# YENİ ENDPOINT: İstemciye tek kullanımlık challenge verir
@app.get("/api/challenge")
async def get_challenge():
    return generate_challenge()

@app.post("/api/score")
async def score_telemetry(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    if len(raw_body) > 262_144:
        raise HTTPException(status_code=413, detail="Payload Too Large: Maximum allowed size is 256 KB")

    ip = get_client_ip(request)
    
    if await asyncio.to_thread(is_ip_banned, ip):
        raise HTTPException(status_code=403, detail="IP address temporarily banned due to suspicious activity.")

    user_agent = request.headers.get("user-agent", "Unknown")
    
    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    token = body.get("token")
    if not token:
        raise HTTPException(status_code=403, detail="[Synapse Shield] Missing token.")

    # 1. Kriptografik Token Varsa Doğrula
    is_valid, reason, telemetry = verify_and_consume_token(token)
    if not is_valid:
        # Süresi dolan token: Kullanıcıyı banlama, token yenileme iste (False Positive Engeli)
        if reason == "TOKEN_EXPIRED":
            return JSONResponse(
                status_code=400,
                content={
                    "status": "token_expired",
                    "code": "EXPIRED",
                    "error": "Token expired, please refresh challenge.",
                    "bot_score": 0.0,
                    "classification": "Unknown",
                    "threat_type": "EXPIRED_CHALLENGE"
                }
            )
        # Replay Attack veya sahte token durumu: Ceza havuzuna ekle
        record_ip_decision(ip, is_bot=True)
        threat_type = "REPLAY_ATTACK"
        background_tasks.add_task(save_log, ip, user_agent, 100.0, "Bot", threat_type, [reason], {}, {})
        background_tasks.add_task(asyncio.to_thread, send_webhook_notification, ip, threat_type, 100.0, [reason])
        return {
            "status": "blocked",
            "bot_score": 100.0,
            "classification": "Bot",
            "threat_type": threat_type,
            "reasons": [reason],
            "details": {"threat_type": threat_type}
        }

    recent_count = await asyncio.to_thread(get_recent_request_count, ip)
    if recent_count > 100:
        ban_ip(ip, 15, "Extreme request frequency (DoS/Brute-force protection)")
        raise HTTPException(status_code=403, detail="IP address banned due to extreme request frequency.")
    
    pow_nonce = body.get("pow_nonce")
    pow_salt = body.get("pow_salt")

    bot_score, classification, reasons, details = await asyncio.to_thread(analyze_behavior, telemetry, recent_count)
    threat_type = details.get("threat_type", "CLEAN_HUMAN" if classification == "Human" else "UNKNOWN_ANOMALY")
    
    # Proof of Work (Smart Challenge) for Gray Area - Tek kullanımlık Nonce Tüketimi
    if 35.0 <= bot_score <= 65.0:
        is_pow_valid = False
        if pow_nonce and pow_salt:
            is_pow_valid = verify_and_consume_pow(pow_salt, str(pow_nonce))
                    
        if is_pow_valid:
            bot_score = max(0.0, bot_score - 20.0)
            classification = "Human"
            threat_type = "CLEAN_HUMAN"
            reasons.append("Gray area PoW Challenge successfully solved (Risk reduced).")
        else:
            return {
                "status": "challenge_required",
                "pow_difficulty": 4,
                "pow_salt": generate_pow_salt()
            }
    
    # Atomik ceza takibi
    record_ip_decision(ip, is_bot=(classification == "Bot"))
    
    background_tasks.add_task(save_log, ip, user_agent, bot_score, classification, threat_type, reasons, details.get("features", {}), telemetry)
        
    if classification == "Bot":
        background_tasks.add_task(manager.broadcast, f"[BOT {bot_score:.1f}%] -> {threat_type} (IP: {ip})")
        background_tasks.add_task(asyncio.to_thread, send_webhook_notification, ip, threat_type, bot_score, reasons)

    return {
        "status": "success",
        "bot_score": bot_score,
        "classification": classification,
        "threat_type": threat_type,
        "reasons": reasons,
        "details": details
    }

@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, token: str | None = Query(None)):
    admin_secret = os.environ.get("SYNAPSE_ADMIN_SECRET")
    if admin_secret:
        if not token or not hmac.compare_digest(token, admin_secret):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    elif os.environ.get("SYNAPSE_DEV_MODE", "0") != "1":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    await websocket.send_text("Synapse Shield Cyber-Console [Version 0.8.0]")
    await websocket.send_text("Type 'help' for available commands.")
    try:
        while True:
            data = await websocket.receive_text()
            cmd = data.strip().lower()
            if cmd == "help":
                await websocket.send_text("Available commands: status, ban list, unban <ip>, retrain, help")
            elif cmd == "status":
                try:
                    stats = await get_logs(limit=1)
                    await websocket.send_text(f"[STATUS] Total Req: {stats['total_requests']}, Bots: {stats['bot_requests']} ({stats['bot_ratio']:.1f}%)")
                except Exception as e:
                    await websocket.send_text(f"[ERROR] Could not fetch status: {e}")
            elif cmd == "ban list":
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT ip, reason FROM banned_ips LIMIT 50")
                    bans = cursor.fetchall()
                    if bans:
                        res = "\n".join([f"IP: {b[0]} | Reason: {b[1]}" for b in bans])
                        await websocket.send_text(f"[BAN LIST]\n{res}")
                    else:
                        await websocket.send_text("[BAN LIST] No IPs are currently banned.")
                except Exception as e:
                    await websocket.send_text(f"[ERROR] {e}")
            elif cmd.startswith("unban "):
                parts = cmd.split(" ", 1)
                if len(parts) > 1:
                    ip_to_unban = parts[1].strip()
                    try:
                        get_storage().unban_ip(ip_to_unban)
                        await websocket.send_text(f"[UNBAN] IP {ip_to_unban} has been removed from quarantine.")
                    except Exception as e:
                        await websocket.send_text(f"[ERROR] Could not unban {ip_to_unban}: {e}")
            elif cmd == "retrain":
                await websocket.send_text("[RETRAIN] Telemetri logları taranıyor ve transfer learning başlatılıyor...")
                from .train import retrain_fc2
                
                # Asenkron event loop'u tıkamamak için thread havuzunda koştur:
                res = await asyncio.to_thread(retrain_fc2)
                
                if res.get("success"):
                    samples = res.get("samples", 0)
                    loss = res.get("loss", 0.0)
                    await websocket.send_text(f"[SUCCESS] 1D-CNN başarıyla güncellendi! Örneklem: {samples}, Kayıp (Loss): {loss:.4f}")
                else:
                    msg = res.get("error", "Bilinmeyen durum")
                    await websocket.send_text(f"[INFO] Yeniden eğitim atlandı: {msg}")
            else:
                await websocket.send_text(f"[ERROR] Unknown command: {cmd}. Type 'help'.")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, ip, user_agent, bot_score, classification, threat_type, reasons, features FROM logs ORDER BY id DESC LIMIT ?", (limit,))
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
            "threat_type": r["threat_type"] if r["threat_type"] else "UNKNOWN",
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
    
    # Tehdit Dağılım İstatistiği (Threat Distribution)
    cursor.execute("SELECT threat_type, COUNT(*) FROM logs WHERE classification = 'Bot' GROUP BY threat_type")
    threat_distribution = {row[0]: row[1] for row in cursor.fetchall()}
    
    return {
        "total_requests": total_requests,
        "bot_requests": bot_requests,
        "human_requests": total_requests - bot_requests,
        "bot_ratio": (bot_requests / total_requests * 100) if total_requests > 0 else 0.0,
        "avg_bot_score": round(avg_bot, 2),
        "avg_human_score": round(avg_human, 2),
        "threat_distribution": threat_distribution,
        "logs": recent_logs
    }

@app.post("/api/clear")
async def clear_logs(request: Request):
    verify_admin(request)

    get_storage().clear_all()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    return {"status": "success", "message": "Database logs and bans cleared"}

@app.post("/api/collect_dataset")
async def collect_dataset(request: Request):
    verify_admin(request)

    raw_body = await request.body()
    if len(raw_body) > 524288:  # 512KB
        raise HTTPException(status_code=413, detail="Payload Too Large: Maximum allowed size is 512 KB")

    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    mouse_movements = json.dumps(body.get("mouse_movements", []))
    keystrokes = json.dumps(body.get("keystrokes", []))
    clicks = json.dumps(body.get("clicks", []))
    scrolls = json.dumps(body.get("scrolls", []))
    browser = json.dumps(body.get("browser", {}))
    
    conn = get_dataset_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        INSERT INTO raw_telemetry (timestamp, mouse_movements, keystrokes, clicks, scrolls, browser)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (now, mouse_movements, keystrokes, clicks, scrolls, browser)
    )
    conn.commit()
    return {"status": "success", "message": "Telemetry collected for dataset."}

@app.get("/api/settings/webhooks")
async def get_webhooks(request: Request):
    verify_admin(request)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT discord_url, telegram_token, telegram_chat_id FROM webhook_settings WHERE id = 1")
    row = cursor.fetchone()
    if not row:
        return {"discord_url": "", "telegram_token": "", "telegram_chat_id": ""}
    return {
        "discord_url": row[0] or "",
        "telegram_token": row[1] or "",
        "telegram_chat_id": row[2] or ""
    }

@app.post("/api/settings/webhooks")
async def update_webhooks(request: Request):
    verify_admin(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    discord_url = body.get("discord_url", "").strip()
    telegram_token = body.get("telegram_token", "").strip()
    telegram_chat_id = body.get("telegram_chat_id", "").strip()
    
    # SSRF & DNS Rebinding koruması
    if discord_url:
        validate_webhook_url(discord_url)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE webhook_settings 
        SET discord_url = ?, telegram_token = ?, telegram_chat_id = ? 
        WHERE id = 1
    """, (discord_url, telegram_token, telegram_chat_id))
    conn.commit()
    return {"status": "success"}

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

@app.get("/")
def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Synapse Shield Cockpit: index.html missing.</h2>")

@app.get("/store")
def read_store():
    store_path = os.path.join(STATIC_DIR, "store.html")
    if os.path.exists(store_path):
        return FileResponse(store_path)
    return HTMLResponse("<h2>Synapse Shield Store: store.html missing.</h2>")

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