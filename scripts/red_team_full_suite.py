"""
Synapse Shield v0.6.5 — Red Team Full Penetration & Bot Mitigation Suite
=======================================================================
Kapsamlı Güvenlik & Bypass Doğrulama Paketi:
1. Katman 1: Kriptografik Savunmalar (HMAC, Replay, Dwell Time, Time Travel, Timestamp)
2. Katman 2 & 3: Biyometrik Motor & 1D-CNN (Lineer, Bézier, Minimum Jerk, Klavye, Titreme)
3. Katman 4: Anti-Stealth & Tamper Proofing (WebDriver, Prototype Mocking, WebGL/Canvas)
4. Katman 5: Ağ Katmanı Savunmaları (Poisson Anomali, Dinamik IP Ban)
5. Kombinasyon Saldırıları (Stealth + Temiz Mouse, Replay + Hız)
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio
import base64
import hashlib
import hmac
import json
import math
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any

import httpx

BASE_URL = "http://127.0.0.1:8000"


@dataclass
class TestResult:
    name: str
    layer: str
    vector: str
    expected: str
    http_status: int
    risk_score: float
    decision: str
    passed: bool
    latency_ms: float
    reasons: List[str]
    threat_type: str = ""
    error: Optional[str] = None


class SynapseRedTeamSuite:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.results: List[TestResult] = []

    async def clear_db(self, client: httpx.AsyncClient):
        try:
            await client.post(f"{self.base_url}/api/clear", timeout=5.0)
        except Exception:
            pass

    async def get_challenge(self, client: httpx.AsyncClient) -> Optional[str]:
        try:
            resp = await client.get(f"{self.base_url}/api/challenge", timeout=5.0)
            if resp.status_code == 200:
                return resp.json().get("challenge")
        except Exception:
            pass
        return None

    def build_token(self, challenge: str, telemetry: dict, created_at: Optional[int] = None) -> str:
        envelope = {
            "challenge": challenge,
            "telemetry": telemetry,
            "created_at": created_at or int(time.time() * 1000),
        }
        return base64.b64encode(json.dumps(envelope).encode()).decode()

    # --- TELEMETRY GENERATORS ---

    def clean_browser(self, desktop: bool = True) -> dict:
        return {
            "webdriver": False,
            "screen_width": 1920 if desktop else 390,
            "screen_height": 1080 if desktop else 844,
            "touch_supported": not desktop,
            "plugins_length": random.randint(3, 7) if desktop else 0,
            "languages": ["tr-TR", "tr", "en-US"],
            "chrome": True,
            "is_plugin_array_fake": False,
            "has_webdriver_own_prop": False,
            "is_webgl_hooked": False,
            "is_canvas_hooked": False,
        }

    def human_organic_trajectory(self, n=45):
        events, t = [], 0
        x, y = 150, 250
        t_base = int(time.time() * 1000)
        for i in range(n):
            x += random.randint(8, 18) + random.gauss(0, 1.5)
            y += random.gauss(1.2, 5.0)  # Doğal kavisli hareket
            t += max(15, 25 + random.gauss(0, 4))
            events.append({"x": round(x, 1), "y": round(y, 1), "t": t_base + int(t)})
        return events

    def linear_trajectory(self, start=(100, 100), end=(600, 600), steps=40, duration_ms=1000):
        t_start = int(time.time() * 1000)
        events = []
        for i in range(steps):
            ratio = i / (steps - 1)
            x = start[0] + (end[0] - start[0]) * ratio
            y = start[1] + (end[1] - start[1]) * ratio
            t = t_start + int(duration_ms * ratio)
            events.append({"x": round(x, 2), "y": round(y, 2), "t": t})
        return events

    def bezier_trajectory(self, p0=(100, 100), p1=(300, 50), p2=(500, 250), p3=(700, 300), steps=50, duration_ms=1200):
        t_start = int(time.time() * 1000)
        events = []
        for i in range(steps):
            t = i / (steps - 1)
            # Kübik Bézier formülü (matematiksel olarak mükemmel pürüzsüz)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            cur_t = t_start + int(duration_ms * t)
            events.append({"x": round(x, 2), "y": round(y, 2), "t": cur_t})
        return events

    async def _post_score(self, client: httpx.AsyncClient, payload: dict) -> tuple[int, float, dict]:
        t0 = time.perf_counter()
        try:
            resp = await client.post(f"{self.base_url}/api/score", json=payload, timeout=10.0)
            latency = (time.perf_counter() - t0) * 1000
            try:
                data = resp.json()
            except Exception:
                data = {}
            return resp.status_code, latency, data
        except Exception as e:
            return 0, 0.0, {"error": str(e)}

    # ==========================================
    # KATMAN 1: KRİPTOGRAFİK TESTLER
    # ==========================================

    async def test_k1_missing_token(self, client: httpx.AsyncClient) -> TestResult:
        """Token olmadan düz JSON gönderimi"""
        status, ms, data = await self._post_score(client, {"telemetry": {}})
        passed = (status == 403)
        return TestResult(
            name="Kayıp Token Gönderimi",
            layer="Katman 1 (Kriptografi)",
            vector="Missing Token",
            expected="BLOCK",
            http_status=status,
            risk_score=100.0 if status == 403 else 0.0,
            decision="Bot" if status == 403 else "Allow",
            passed=passed,
            latency_ms=ms,
            reasons=["Missing token (HTTP 403)"] if status == 403 else []
        )

    async def test_k1_forged_hmac(self, client: httpx.AsyncClient) -> TestResult:
        """Sahte HMAC İmzası (Yanlış Signature)"""
        fake_challenge = f"0123456789abcdef.{int(time.time())}.badc0ffeebadf00d"
        token = self.build_token(fake_challenge, {"browser": self.clean_browser()})
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 100.0 or decision == "Bot" or status == 403)
        return TestResult(
            name="Sahte HMAC İmzası",
            layer="Katman 1 (Kriptografi)",
            vector="Forged HMAC Signature",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k1_replay_attack(self, client: httpx.AsyncClient) -> TestResult:
        """Replay Attack: Aynı token'ın 2 kez kullanılması"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        telemetry = {
            "mouse_movements": self.human_organic_trajectory(),
            "clicks": [{"x": 720, "y": 310, "t": int(time.time()*1000) + 1670}],
            "keystrokes": [],
            "scrolls": [],
            "browser": self.clean_browser()
        }
        token = self.build_token(ch, telemetry)
        
        # 1. Gönderim (Başarılı olmalı)
        await self._post_score(client, {"token": token})
        
        # 2. Gönderim (Aynı token - Replay Attack engellenmeli)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 100.0 and (decision == "Bot" or data.get("threat_type") == "REPLAY_ATTACK"))
        return TestResult(
            name="Replay Saldırısı (Nonce Tüketimi)",
            layer="Katman 1 (Kriptografi)",
            vector="Replay Attack (Duplicate Token)",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k1_speed_manipulation(self, client: httpx.AsyncClient) -> TestResult:
        """Zaman manipülasyonu: Challenge sonrası 0.2s bekleme (İnsanüstü Hız <1.5s)"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(0.2)  # 0.2s << 1.5s
        telemetry = {"mouse_movements": [], "clicks": [], "keystrokes": [], "scrolls": [], "browser": self.clean_browser()}
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 100.0 or decision == "Bot")
        return TestResult(
            name="Hız Manipülasyonu (<1.5s Dwell Time)",
            layer="Katman 1 (Kriptografi)",
            vector="Speed Manipulation / Instant Token",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k1_time_travel_bot(self, client: httpx.AsyncClient) -> TestResult:
        """Time Travel Bot: Token alınalı 1.6s olmuş ama içine 4.5s telemetri yerleştirilmiş"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        # 4.5 saniyelik sahte telemetri
        t_now = int(time.time() * 1000)
        events = [
            {"x": 100, "y": 100, "t": t_now},
            {"x": 200, "y": 200, "t": t_now + 4500}
        ]
        telemetry = {"mouse_movements": events, "clicks": [], "keystrokes": [], "scrolls": [], "browser": self.clean_browser()}
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 100.0 or decision == "Bot")
        return TestResult(
            name="Zaman Yolculuğu (Time Travel Bot)",
            layer="Katman 1 (Kriptografi)",
            vector="Telemetry Duration > Token Elapsed Time",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    # ==========================================
    # KATMAN 2 & 3: BİYOMETRİK MOTOR & 1D-CNN
    # ==========================================

    async def test_k2_linear_bot(self, client: httpx.AsyncClient) -> TestResult:
        """Düz çizgi botu (straightness=1.0, jerk=0)"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        events = self.linear_trajectory()
        telemetry = {
            "mouse_movements": events,
            "clicks": [{"x": events[-1]["x"], "y": events[-1]["y"], "t": events[-1]["t"] + 30}],
            "keystrokes": [],
            "scrolls": [],
            "browser": self.clean_browser()
        }
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 50.0 and decision == "Bot")
        return TestResult(
            name="Lineer Fare Botu (Düz Çizgi)",
            layer="Katman 2 (Kinematik Biyometri)",
            vector="Euclidean Straight Line (Straightness=1.0)",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k2_bezier_curve_bot(self, client: httpx.AsyncClient) -> TestResult:
        """Bézier Eğrisi Botu (Pürüzsüz ivme, fizyolojik jerk eksikliği)"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        events = self.bezier_trajectory()
        telemetry = {
            "mouse_movements": events,
            "clicks": [{"x": events[-1]["x"], "y": events[-1]["y"], "t": events[-1]["t"] + 30}],
            "keystrokes": [],
            "scrolls": [],
            "browser": self.clean_browser()
        }
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 50.0 and decision == "Bot")
        return TestResult(
            name="Bézier Eğrisi Botu (Ghost-Cursor)",
            layer="Katman 2 & 3 (Kinematik & Jerk Analizi)",
            vector="Polynomial Smooth Curve (Missing Tremor)",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k2_robotic_keyboard(self, client: httpx.AsyncClient) -> TestResult:
        """Robotik Klavye (Sabit 50ms aralıklı tuş vuruşları, varyans=0)"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        t_base = int(time.time() * 1000)
        keys = [{"key": "a", "t": t_base + i * 50} for i in range(10)]
        events = self.human_organic_trajectory()
        telemetry = {
            "mouse_movements": events,
            "clicks": [{"x": events[-1]["x"], "y": events[-1]["y"], "t": events[-1]["t"] + 30}],
            "keystrokes": keys,
            "scrolls": [],
            "browser": self.clean_browser()
        }
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 50.0 and decision == "Bot")
        return TestResult(
            name="Robotik Klavye Girişi",
            layer="Katman 2 (Klavye Biyometrisi)",
            vector="Fixed Interval Keystrokes (Variance=0)",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k2_superhuman_keyboard(self, client: httpx.AsyncClient) -> TestResult:
        """İnsanüstü Hızlı Klavye (<25ms ortalama tuş aralığı)"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        t_base = int(time.time() * 1000)
        keys = [{"key": "x", "t": t_base + i * 15} for i in range(10)]
        events = self.human_organic_trajectory()
        telemetry = {
            "mouse_movements": events,
            "clicks": [],
            "keystrokes": keys,
            "scrolls": [],
            "browser": self.clean_browser()
        }
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (risk >= 50.0 and decision == "Bot")
        return TestResult(
            name="İnsanüstü Hızlı Yazma (<25ms)",
            layer="Katman 2 (Klavye Dinamikleri)",
            vector="Superhuman Keystroke Frequency",
            expected="BLOCK",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k2_clean_human(self, client: httpx.AsyncClient) -> TestResult:
        """Doğal İnsan Biyometrisi (False Positive Kontrolü)"""
        ch = await self.get_challenge(client)
        await asyncio.sleep(1.7)
        events = self.human_organic_trajectory()
        telemetry = {
            "mouse_movements": events,
            "clicks": [{"x": events[-1]["x"], "y": events[-1]["y"], "t": events[-1]["t"] + 35}],
            "keystrokes": [
                {"key": "H", "t": int(time.time()*1000) + 200},
                {"key": "e", "t": int(time.time()*1000) + 330},
                {"key": "l", "t": int(time.time()*1000) + 420},
                {"key": "p", "t": int(time.time()*1000) + 610}
            ],
            "scrolls": [],
            "browser": self.clean_browser()
        }
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        passed = (status == 200 and risk < 50.0 and decision == "Human")
        return TestResult(
            name="Organik İnsan Biyometrisi (Baseline)",
            layer="Katman 2 & 3 (Kinematik Doğrulama)",
            vector="Natural Human Telemetry & Tremor",
            expected="ALLOW",
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    # ==========================================
    # KATMAN 4: ANTI-STEALTH & TAMPER PROOFING
    # ==========================================

    async def _test_tamper_flag(self, client: httpx.AsyncClient, name: str, vector: str, expected: str, overrides: dict) -> TestResult:
        ch = await self.get_challenge(client)
        await asyncio.sleep(2.1)
        browser = self.clean_browser()
        browser.update(overrides)
        events = self.human_organic_trajectory()
        telemetry = {
            "mouse_movements": events,
            "clicks": [{"x": events[-1]["x"], "y": events[-1]["y"], "t": events[-1]["t"] + 30}],
            "keystrokes": [],
            "scrolls": [],
            "browser": browser
        }
        token = self.build_token(ch, telemetry)
        status, ms, data = await self._post_score(client, {"token": token})
        risk = data.get("bot_score", 0.0)
        decision = data.get("classification", "")
        if expected == "BLOCK":
            passed = (risk >= 50.0 or decision == "Bot")
        else:
            passed = (status == 200 and risk < 50.0 and decision == "Human")

        return TestResult(
            name=name,
            layer="Katman 4 (Anti-Stealth & Tamper)",
            vector=vector,
            expected=expected,
            http_status=status,
            risk_score=risk,
            decision=decision,
            passed=passed,
            latency_ms=ms,
            reasons=data.get("reasons", []),
            threat_type=data.get("threat_type", "")
        )

    async def test_k4_webdriver_detected(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_tamper_flag(
            client,
            name="Selenium/Playwright WebDriver",
            vector="navigator.webdriver = True",
            expected="BLOCK",
            overrides={"webdriver": True}
        )

    async def test_k4_fake_plugins(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_tamper_flag(
            client,
            name="Sahte Plugin Array (is_plugin_array_fake)",
            vector="V8 Prototype Tamper on navigator.plugins",
            expected="BLOCK",
            overrides={"is_plugin_array_fake": True}
        )

    async def test_k4_webdriver_own_prop(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_tamper_flag(
            client,
            name="WebDriver OwnProp Kancası",
            vector="has_webdriver_own_prop = True",
            expected="BLOCK",
            overrides={"has_webdriver_own_prop": True}
        )

    async def test_k4_webgl_canvas_combo(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_tamper_flag(
            client,
            name="WebGL + Canvas Çift Kanca (+80 Risk)",
            vector="Both WebGL & Canvas Hooked",
            expected="BLOCK",
            overrides={"is_webgl_hooked": True, "is_canvas_hooked": True}
        )

    async def test_k4_full_stealth_kit(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_tamper_flag(
            client,
            name="Full Stealth Evasion Kiti (4 Tamper)",
            vector="All Tamper Flags Active",
            expected="BLOCK",
            overrides={
                "is_plugin_array_fake": True,
                "has_webdriver_own_prop": True,
                "is_webgl_hooked": True,
                "is_canvas_hooked": True
            }
        )

    async def test_k4_brave_user_false_positive(self, client: httpx.AsyncClient) -> TestResult:
        """Brave Kullanıcısı (Sadece canvas koruması aktif, temiz biyometri) -> ALLOW olmalı"""
        return await self._test_tamper_flag(
            client,
            name="Brave Kullanıcısı (Farbling Koruması)",
            vector="Canvas Farbling Only (+40 Risk, Temiz Biyometri)",
            expected="ALLOW",
            overrides={"is_canvas_hooked": True}
        )

    # ==========================================
    # KATMAN 5: AĞ KATMANI & CEZA MEKANİZMASI
    # ==========================================

    async def test_k5_dynamic_ip_ban(self, client: httpx.AsyncClient) -> TestResult:
        """Dinamik IP Ban: 4 ardışık bot isteği sonrası 5. istekte ban tetiklenmesi"""
        # Önce veritabanını temizle
        await self.clear_db(client)
        await asyncio.sleep(0.3)

        # 4 adet bariz bot isteği gönder (Linear mouse)
        for _ in range(4):
            ch = await self.get_challenge(client)
            await asyncio.sleep(2.1)
            events = self.linear_trajectory()
            token = self.build_token(ch, {"mouse_movements": events, "clicks": [], "keystrokes": [], "scrolls": [], "browser": self.clean_browser()})
            await self._post_score(client, {"token": token})
            await asyncio.sleep(0.1)

        # 5. istek: Artık IP banlanmış olmalı -> HTTP 403
        ch = await self.get_challenge(client)
        token = self.build_token(ch or "dummy", {"browser": self.clean_browser()})
        status, ms, data = await self._post_score(client, {"token": token})
        passed = (status == 403)
        return TestResult(
            name="Dinamik IP Ban (4 Ardışık Bot Cezası)",
            layer="Katman 5 (Ağ Katmanı & IP Ban)",
            vector="Dynamic IP Throttling / 4 Consecutive Bots",
            expected="BLOCK",
            http_status=status,
            risk_score=100.0 if status == 403 else data.get("bot_score", 0.0),
            decision="Banned" if status == 403 else data.get("classification", ""),
            passed=passed,
            latency_ms=ms,
            reasons=["IP temporarily banned due to 4 consecutive malicious requests"] if status == 403 else data.get("reasons", [])
        )

    # ==========================================
    # SUITE KOŞUCUSU
    # ==========================================

    async def run_all(self):
        print("\n" + "="*75)
        print("  🛡️ SYNAPSE SHIELD v0.6.5 — RED TEAM OTOMATİZE SALDIRI TESTİ")
        print(f"  Hedef: {self.base_url} | Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*75 + "\n")

        test_queue = [
            # Katman 1
            ("K1: Kayıp Token", self.test_k1_missing_token),
            ("K1: Sahte HMAC", self.test_k1_forged_hmac),
            ("K1: Replay Attack", self.test_k1_replay_attack),
            ("K1: Hız Manipülasyonu", self.test_k1_speed_manipulation),
            ("K1: Zaman Yolculuğu", self.test_k1_time_travel_bot),
            # Katman 2 & 3
            ("K2: Lineer Mouse", self.test_k2_linear_bot),
            ("K2: Bézier Eğrisi", self.test_k2_bezier_curve_bot),
            ("K2: Robotik Klavye", self.test_k2_robotic_keyboard),
            ("K2: İnsanüstü Klavye", self.test_k2_superhuman_keyboard),
            ("K2: Organik İnsan", self.test_k2_clean_human),
            # Katman 4
            ("K4: WebDriver Tespiti", self.test_k4_webdriver_detected),
            ("K4: Sahte Plugin Array", self.test_k4_fake_plugins),
            ("K4: WebDriver OwnProp", self.test_k4_webdriver_own_prop),
            ("K4: WebGL + Canvas Combo", self.test_k4_webgl_canvas_combo),
            ("K4: Full Stealth Kiti", self.test_k4_full_stealth_kit),
            ("K4: Brave Kullanıcısı", self.test_k4_brave_user_false_positive),
            # Katman 5
            ("K5: Dinamik IP Ban", self.test_k5_dynamic_ip_ban),
        ]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for display_name, test_func in test_queue:
                # İzolasyon için her test öncesi ban ve log temizliği
                if display_name != "K5: Dinamik IP Ban":
                    await self.clear_db(client)
                    await asyncio.sleep(0.2)

                print(f"▶ Çalıştırılıyor: {display_name}...")
                try:
                    res = await test_func(client)
                    self.results.append(res)
                    status_badge = "✅ PASS" if res.passed else "❌ FAIL"
                    print(f"  {status_badge} | HTTP {res.http_status} | Risk: {res.risk_score:.1f}% | Karar: {res.decision} | Süre: {res.latency_ms:.1f}ms")
                    if res.reasons:
                        print(f"    Savunma Tetiklendi: {res.reasons[0][:80]}")
                except Exception as e:
                    print(f"  ❌ TEST HATASI: {e}")
                print("-" * 75)

        self._render_report()
        self._save_report()

    def _render_report(self):
        print("\n" + "="*90)
        print("  📊 SYNAPSE SHIELD v0.6.5 — RED TEAM SALDIRI SONUÇ RAPORU")
        print("="*90)
        header = f"{'Test Adı':<32} | {'Katman':<18} | {'Beklenen':<8} | {'HTTP':<4} | {'Risk %':<7} | {'Karar':<7} | {'Sonuç'}"
        print(header)
        print("-" * 90)

        total_pass = 0
        for r in self.results:
            passed_str = "✅ PASS" if r.passed else "❌ FAIL"
            if r.passed:
                total_pass += 1
            print(f"{r.name[:32]:<32} | {r.layer[:18]:<18} | {r.expected:<8} | {r.http_status:<4} | {r.risk_score:<7.1f} | {r.decision[:7]:<7} | {passed_str}")

        print("-" * 90)
        score_pct = (total_pass / len(self.results)) * 100 if self.results else 0
        print(f"Toplam Test: {len(self.results)} | Başarılı: {total_pass} | Başarı Oranı: %{score_pct:.1f}")
        print("="*90 + "\n")

    def _save_report(self):
        filename = f"red_team_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = [asdict(r) for r in self.results]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"📁 Detaylı JSON raporu kaydedildi: {filename}\n")


if __name__ == "__main__":
    suite = SynapseRedTeamSuite()
    asyncio.run(suite.run_all())
