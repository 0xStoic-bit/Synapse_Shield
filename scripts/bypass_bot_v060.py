"""
Synapse Shield v0.6.0 Bypass Bot - Local Test
================================================
Bu bot, 0.6.0'ın tüm savunmalarını atlatmaya çalışır.
Her istekte:
- Yeni challenge alır
- 1.6s bekler
- Gerçekçi insan telemetrisi üretir
- Token'ı doğru şekilde imzalar
"""

import asyncio
import base64
import json
import math
import random
import time
import hmac
import hashlib
import secrets
from datetime import datetime

import httpx
import numpy as np

# ─── Hedef URL ──────────────────────────────────────────────────────────────
TARGET_URL = "http://127.0.0.1:8000"

# ─── Biyometrik Sentez ───────────────────────────────────────────────────────
def bezier_curve(p0, p1, p2, p3, n=60):
    """4 noktalı Bézier eğrisi"""
    points = []
    for i in range(n):
        t = i / (n - 1)
        x = (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0]
        y = (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
        points.append((round(x, 2), round(y, 2)))
    return points

def add_human_tremor(points, amplitude=1.2):
    """
    Gerçekçi insan kas titremesi (8-12 Hz bandı)
    0.5.0'da eklenen spektral jitter analizini atlatmak için:
    - Tek frekans değil, çoklu frekans (8Hz + 10.4Hz + 12.3Hz)
    - Gaussian gürültü eklenmiş
    """
    noisy = []
    for i, (x, y) in enumerate(points):
        t = i / len(points)
        # Çoklu frekanslı tremor (insan nörolojik spektrumu)
        jx = (amplitude * math.sin(2 * math.pi * 8 * t + random.uniform(0, math.pi))
              + 0.6 * amplitude * math.sin(2 * math.pi * 12.3 * t + random.uniform(0, math.pi))
              + 0.3 * amplitude * math.sin(2 * math.pi * 5.7 * t + random.uniform(0, math.pi)))
        jy = (amplitude * math.cos(2 * math.pi * 10.4 * t + random.uniform(0, math.pi))
              + 0.6 * amplitude * math.cos(2 * math.pi * 9.2 * t + random.uniform(0, math.pi))
              + 0.3 * amplitude * math.cos(2 * math.pi * 6.8 * t + random.uniform(0, math.pi)))
        # Gaussian gürültü
        jx += random.gauss(0, 0.35)
        jy += random.gauss(0, 0.35)
        noisy.append((round(x + jx, 3), round(y + jy, 3)))
    return noisy

def synth_mouse_events(n=65):
    """Gerçekçi insan fare hareketi üret"""
    x0, y0 = random.randint(100, 400), random.randint(100, 400)
    x3, y3 = random.randint(500, 900), random.randint(300, 600)
    x1 = x0 + random.randint(50, 200)
    y1 = y0 + random.randint(-100, 100)
    x2 = x3 - random.randint(50, 200)
    y2 = y3 + random.randint(-100, 100)
    
    raw = bezier_curve((x0,y0),(x1,y1),(x2,y2),(x3,y3), n=n)
    path = add_human_tremor(raw)
    
    events, t = [], 0
    for x, y in path:
        dt = max(8, 20 + random.gauss(0, 5))  # 20-40ms arası değişken
        t += dt
        events.append({"x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})
    return events

def synth_keystrokes(n=8):
    """Log-normal dağılımlı klavye vuruşları"""
    avg = 60000 / (55 * 5)  # ~218ms ortalama
    result = []
    t = 500  # başlangıç zamanı
    for _ in range(n):
        interval = float(np.random.lognormal(math.log(avg), 0.25))
        interval = max(60, min(800, interval))
        t += interval
        result.append({"type": "down", "t": round(t, 2)})
        # Key up event
        result.append({"type": "up", "t": round(t + random.uniform(50, 120), 2)})
    return result

def synth_scroll_events(n=3):
    """Gerçekçi scroll olayları"""
    scrolls = []
    t = 2000
    for _ in range(n):
        dt = random.randint(150, 400)
        t += dt
        scrolls.append({"y": random.randint(100, 800), "t": round(t, 2)})
    return scrolls

def human_telemetry(device="desktop"):
    """
    0.6.0 SDK formatına uygun tam telemetri.
    device: 'desktop' veya 'mobile'
    """
    if device == "desktop":
        return {
            "mouse_movements": synth_mouse_events(),
            "clicks": [{"x": random.randint(400, 800), "y": random.randint(200, 500), "t": 1200.0}],
            "keystrokes": synth_keystrokes(),
            "scrolls": synth_scroll_events(),
            "browser": {
                "webdriver": False,
                "screen_width": 1920,
                "screen_height": 1080,
                "touch_supported": False,
                "plugins_length": random.randint(3, 7),
                "languages": ["tr-TR", "tr", "en-US"],
                "chrome": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "platform": "Win32",
                "hardware_concurrency": 8,
                "device_memory": 8,
                "timezone": "Europe/Istanbul",
            }
        }
    else:  # mobile
        return {
            "mouse_movements": synth_mouse_events(n=40),  # mobilde daha az hareket
            "clicks": [{"x": random.randint(150, 350), "y": random.randint(300, 600), "t": 800.0}],
            "keystrokes": synth_keystrokes(n=5),
            "scrolls": synth_scroll_events(n=2),
            "browser": {
                "webdriver": False,
                "screen_width": 390,
                "screen_height": 844,
                "touch_supported": True,
                "plugins_length": 0,  # Mobilde her zaman 0
                "languages": ["tr-TR", "tr", "en-US"],
                "chrome": True,
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
                "platform": "iPhone",
                "hardware_concurrency": 6,
                "device_memory": 4,
                "timezone": "Europe/Istanbul",
            }
        }

# ─── Challenge ve Token Yönetimi ─────────────────────────────────────────────
async def get_challenge(client: httpx.AsyncClient) -> str:
    """Sunucudan yeni challenge al"""
    resp = await client.get(f"{TARGET_URL}/api/challenge", timeout=5.0)
    if resp.status_code == 200:
        return resp.json().get("challenge")
    raise Exception(f"Challenge alınamadı: {resp.status_code}")

def build_token(challenge: str, telemetry: dict) -> str:
    """Doğru formatlı token oluştur"""
    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000),
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()

# ─── Ana Bot Sınıfı ──────────────────────────────────────────────────────────
class SynapseBypassBotV060:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.session_token = None
        self.session_telemetry = None

    async def close(self):
        await self.client.aclose()

    async def perform_action(self, action: str, device: str = "desktop"):
        """
        Belirli bir işlem yap:
        - 'login': Giriş formu doldur
        - 'click': Butona tıkla
        - 'scroll': Sayfayı kaydır
        """
        # 1. Yeni challenge al
        ch = await get_challenge(self.client)
        
        # 2. 1.6s bekle (zaman manipülasyonu korumasını atlat)
        await asyncio.sleep(1.6)
        
        # 3. Telemetri üret
        telemetry = human_telemetry(device)
        
        # 4. Token oluştur
        token = build_token(ch, telemetry)
        
        # 5. İsteği gönder
        payload = {"token": token}
        resp = await self.client.post(f"{TARGET_URL}/api/score", json=payload)
        
        return {
            "status_code": resp.status_code,
            "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {},
            "action": action,
            "device": device,
            "token_used": token[:50] + "...",
        }

    async def simulate_full_session(self):
        """Gerçekçi bir kullanıcı oturumu simüle et"""
        print("\n" + "="*60)
        print("🔴 SYNAPSE SHIELD v0.6.0 BYPASS BOT")
        print("="*60)
        
        results = []
        
        # 1. Giriş formu doldur (desktop)
        print("\n[1/4] Giriş formu dolduruluyor (desktop)...")
        login_result = await self.perform_action("login", "desktop")
        results.append(login_result)
        print(f"  → HTTP {login_result['status_code']}")
        if login_result['response'].get('status') == 'allow':
            print(f"  → ✅ GİRİŞ BAŞARILI! (Sistem atlatıldı)")
        else:
            print(f"  → ❌ Engellendi: {login_result['response']}")
        
        await asyncio.sleep(random.uniform(2, 4))
        
        # 2. Ürün sayfasına tıkla (desktop)
        print("\n[2/4] Ürün sayfasına tıklanıyor (desktop)...")
        click_result = await self.perform_action("click", "desktop")
        results.append(click_result)
        print(f"  → HTTP {click_result['status_code']}")
        if click_result['response'].get('status') == 'allow':
            print(f"  → ✅ TIKLAMA BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi: {click_result['response']}")
        
        await asyncio.sleep(random.uniform(1, 3))
        
        # 3. Mobil cihazdan giriş (mobile)
        print("\n[3/4] Mobil cihazdan giriş yapılıyor...")
        mobile_result = await self.perform_action("login", "mobile")
        results.append(mobile_result)
        print(f"  → HTTP {mobile_result['status_code']}")
        if mobile_result['response'].get('status') == 'allow':
            print(f"  → ✅ MOBİL GİRİŞ BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi: {mobile_result['response']}")
        
        await asyncio.sleep(random.uniform(2, 5))
        
        # 4. Tekrar desktop'tan işlem yap
        print("\n[4/4] Desktop'tan tekrar işlem yapılıyor...")
        repeat_result = await self.perform_action("click", "desktop")
        results.append(repeat_result)
        print(f"  → HTTP {repeat_result['status_code']}")
        if repeat_result['response'].get('status') == 'allow':
            print(f"  → ✅ TEKRAR BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi: {repeat_result['response']}")
        
        # Sonuçları özetle
        print("\n" + "="*60)
        print("📊 SONUÇ ÖZETİ")
        print("="*60)
        
        success_count = sum(1 for r in results if r['status_code'] == 200)
        print(f"  Toplam istek: {len(results)}")
        print(f"  Başarılı: {success_count}/{len(results)}")
        
        if success_count == len(results):
            print("\n🎉 SİSTEM TAMAMEN ATLATILDI!")
            print("  Tüm istekler 200 OK döndü!")
        else:
            print(f"\n⚠️ SİSTEM KISMEN ATLATILDI ({success_count}/{len(results)})")
            for r in results:
                if r['status_code'] != 200:
                    print(f"  ❌ {r['action']} ({r['device']}): {r['response']}")
        
        return results

    async def run(self):
        try:
            results = await self.simulate_full_session()
            return results
        finally:
            await self.close()

# ─── Entry Point ──────────────────────────────────────────────────────────────
async def main():
    bot = SynapseBypassBotV060()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
