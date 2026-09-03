"""
Synapse Shield v0.6.0 — Adversarial Test Suite
================================================
0.6.0'daki yeni savunmaları hedef alan test senaryoları:

1. Zaman Manipülasyonu     → challenge_ts < 1.5s kontrolü
2. Replay Attack           → Atomik SQLite nonce
3. Token Bypass            → middleware token zorunluluğu
4. SDK Fallback Bypass     → token olmadan düz JSON
5. Headless Plugin Tespiti → plugins_length == 0 + masaüstü
6. Sentetik İnsan          → Bézier + tremor (önceki bypass)
7. Sahte İmza              → HMAC forge denemesi

Kullanım:
    pip install httpx numpy rich
    python synapse_adversarial_v060.py --url http://127.0.0.1:8000
"""

import asyncio
import argparse
import base64
import json
import math
import random
import time
import hmac
import hashlib
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import httpx
import numpy as np
from rich.console import Console
from rich.table import Table

console = Console()


# ─── Biyometrik Sentez (0.5.x'ten taşındı) ────────────────────────────────────

def bezier_curve(p0, p1, p2, p3, n=60):
    points = []
    for i in range(n):
        t = i / (n - 1)
        x = (1-t)**3*p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0]
        y = (1-t)**3*p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
        points.append((round(x, 2), round(y, 2)))
    return points


def add_tremor(points, amplitude=1.1):
    noisy = []
    for i, (x, y) in enumerate(points):
        t = i / len(points)
        jx = amplitude * math.sin(2 * math.pi * 8 * t + random.uniform(0, math.pi))
        jy = amplitude * math.cos(2 * math.pi * 10.4 * t + random.uniform(0, math.pi))
        jx += random.gauss(0, 0.3)
        jy += random.gauss(0, 0.3)
        noisy.append((round(x + jx, 3), round(y + jy, 3)))
    return noisy


def synth_mouse_events(n=55):
    x0, y0 = random.randint(100, 400), random.randint(100, 400)
    x3, y3 = random.randint(500, 900), random.randint(300, 600)
    x1 = x0 + random.randint(50, 200)
    y1 = y0 + random.randint(-100, 100)
    x2 = x3 - random.randint(50, 200)
    y2 = y3 + random.randint(-100, 100)
    raw = bezier_curve((x0,y0),(x1,y1),(x2,y2),(x3,y3), n=n)
    path = add_tremor(raw)
    events, t = [], 0
    for x, y in path:
        dt = max(8, 20 + random.gauss(0, 4))
        t += dt
        events.append({"x": x, "y": y, "t": round(t, 2)})
    return events


def synth_keystrokes(n=8):
    avg = 60000 / (55 * 5)
    result = []
    for _ in range(n):
        iki = float(np.random.lognormal(math.log(avg), 0.25))
        iki = max(60, min(800, iki))
        result.append({"type": "down", "t": round(iki, 2)})
    return result


def human_telemetry(desktop=True):
    """0.6.0 SDK formatına uygun tam telemetri."""
    return {
        "mouse_movements": synth_mouse_events(),
        "clicks": [{"x": random.randint(400, 800), "y": random.randint(200, 500), "t": 1200.0}],
        "keystrokes": synth_keystrokes(),
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920 if desktop else 390,
            "screen_height": 1080 if desktop else 844,
            "touch_supported": not desktop,
            "plugins_length": random.randint(3, 7) if desktop else 0,
            "languages": ["tr-TR", "tr", "en-US"],
            "chrome": True,
        }
    }


# ─── Challenge Yardımcıları ────────────────────────────────────────────────────

async def get_challenge(client: httpx.AsyncClient, base_url: str) -> Optional[str]:
    try:
        resp = await client.get(f"{base_url}/api/challenge", timeout=5.0)
        if resp.status_code == 200:
            return resp.json().get("challenge")
    except Exception:
        pass
    return None


def build_token(challenge: str, telemetry: dict, created_at: Optional[int] = None) -> str:
    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": created_at or int(time.time() * 1000),
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()


# ─── Test Sonucu ──────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    scenario: str
    http_status: int
    response_ms: float
    risk_score: Optional[float]
    decision: Optional[str]
    passed: bool
    expected: str  # "BLOCK" veya "ALLOW"
    notes: str = ""
    error: Optional[str] = None


def parse_response(data: dict):
    risk = data.get("bot_score") or data.get("risk_score") or data.get("score")
    decision = data.get("classification") or data.get("decision") or data.get("status")
    if isinstance(risk, str):
        try:
            risk = float(risk.strip("%"))
        except Exception:
            risk = None
    return risk, decision


# ─── Ana Test Sınıfı ──────────────────────────────────────────────────────────

class SynapseAdversaryV060:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.results: list[TestResult] = []

    async def _post_score(self, client, payload, label) -> tuple[int, float, dict]:
        start = time.monotonic()
        try:
            resp = await client.post(
                f"{self.base_url}/api/score",
                json=payload,
                timeout=10.0,
            )
            ms = (time.monotonic() - start) * 1000
            try:
                data = resp.json()
            except Exception:
                data = {}
            return resp.status_code, round(ms, 1), data
        except Exception as e:
            ms = (time.monotonic() - start) * 1000
            return 0, round(ms, 1), {"error": str(e)}

    # ── 1. Zaman Manipülasyonu: challenge_ts < 1.5s ────────────────────────────
    async def test_time_manipulation(self, client):
        """
        0.6.0'ın en yeni savunması: sunucu challenge ürettiği andan itibaren
        1.5 saniye geçmeden gelen token → BOT.
        Biz hemen (0ms sonra) token gönderiyoruz.
        """
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TestResult("Zaman Manipülasyonu", 0, 0, None, None, False, "BLOCK", error="Challenge alınamadı")

        # Anlık gönder — 1.5s beklemiyoruz (bot davranışı)
        token = build_token(ch, human_telemetry())
        status, ms, data = await self._post_score(client, {"token": token}, "ZamanManip")
        risk, decision = parse_response(data)

        blocked = status in (403, 429) or (decision or "").upper() in ("BOT", "BLOCK")
        return TestResult(
            scenario="Zaman Manipülasyonu (<1.5s)",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=blocked,  # engellemeli
            expected="BLOCK",
            notes="Challenge alındıktan hemen sonra gönderildi"
        )

    # ── 2. Geçerli Zamanlama (1.5s bekle) → ALLOW beklenir ────────────────────
    async def test_valid_timing(self, client):
        """
        1.5s bekledikten sonra gönderilen token → ALLOW olmalı.
        """
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TestResult("Geçerli Zamanlama", 0, 0, None, None, False, "ALLOW", error="Challenge alınamadı")

        await asyncio.sleep(1.6)  # 1.5s eşiğini geç
        token = build_token(ch, human_telemetry())
        status, ms, data = await self._post_score(client, {"token": token}, "ValidTiming")
        risk, decision = parse_response(data)

        allowed = status == 200 and (decision or "").upper() in ("HUMAN", "ALLOW", "")
        return TestResult(
            scenario="Geçerli Zamanlama (1.6s beklendi)",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=allowed,
            expected="ALLOW",
            notes="1.6s beklendi, insan telemetrisi gönderildi"
        )

    # ── 3. Replay Attack ───────────────────────────────────────────────────────
    async def test_replay_attack(self, client):
        """Atomik SQLite nonce — aynı token 2 kez kullanılamaz."""
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TestResult("Replay Attack", 0, 0, None, None, False, "BLOCK", error="Challenge alınamadı")

        await asyncio.sleep(1.6)
        token = build_token(ch, human_telemetry())

        # 1. gönderim
        await self._post_score(client, {"token": token}, "Replay-1")
        await asyncio.sleep(0.2)

        # 2. gönderim — aynı token
        status, ms, data = await self._post_score(client, {"token": token}, "Replay-2")
        risk, decision = parse_response(data)

        blocked = status in (403, 429) or (decision or "").upper() in ("BOT", "BLOCK")
        return TestResult(
            scenario="Replay Attack (aynı token 2x)",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=blocked,
            expected="BLOCK",
            notes="Atomik SQLite nonce kontrolü"
        )

    # ── 4. Token Olmadan Düz JSON (SDK Fallback Bypass) ───────────────────────
    async def test_no_token_fallback(self, client):
        """
        0.6.0'da SDK fallback kaldırıldı — token olmadan istek → 403.
        """
        payload = {"telemetry": human_telemetry()}  # token yok
        status, ms, data = await self._post_score(client, payload, "NoToken")
        risk, decision = parse_response(data)

        blocked = status == 403
        return TestResult(
            scenario="Token Yok (Fallback Bypass)",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=blocked,
            expected="BLOCK",
            notes="0.6.0'da token zorunlu"
        )

    # ── 5. Sahte HMAC İmzası ──────────────────────────────────────────────────
    async def test_forged_signature(self, client):
        """Kendi ürettiğimiz HMAC ile imzalanmış sahte challenge."""
        fake_key = secrets.token_hex(32).encode()
        nonce = secrets.token_hex(16)
        ts = int(time.time()) - 2  # 2 saniye önce
        fake_sig = hmac.new(fake_key, f"{nonce}:{ts}".encode(), hashlib.sha256).hexdigest()
        fake_challenge = f"{nonce}.{ts}.{fake_sig}"

        token = build_token(fake_challenge, human_telemetry())
        status, ms, data = await self._post_score(client, {"token": token}, "ForgeSig")
        risk, decision = parse_response(data)

        blocked = status in (403, 429) or (decision or "").upper() in ("BOT", "BLOCK")
        return TestResult(
            scenario="Sahte HMAC İmzası",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=blocked,
            expected="BLOCK",
            notes="Yanlış secret key ile imzalandı"
        )

    # ── 6. Headless Plugin Tespiti (Masaüstü + plugins=0) ─────────────────────
    async def test_headless_plugin(self, client):
        """
        0.6.0 yeni kuralı: masaüstü + touch=False + plugins_length=0 → +50 Risk
        """
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TestResult("Headless Plugin", 0, 0, None, None, False, "BLOCK", error="Challenge alınamadı")

        await asyncio.sleep(1.6)
        tel = human_telemetry(desktop=True)
        tel["browser"]["plugins_length"] = 0  # headless sinyal
        tel["browser"]["touch_supported"] = False
        tel["browser"]["screen_width"] = 1920

        token = build_token(ch, tel)
        status, ms, data = await self._post_score(client, {"token": token}, "HeadlessPlugin")
        risk, decision = parse_response(data)

        blocked = status in (403, 429) or (risk or 0) >= 50
        return TestResult(
            scenario="Headless Plugin (plugins=0, desktop)",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=blocked,
            expected="BLOCK",
            notes="0.6.0 yeni kuralı: +50 risk"
        )

    # ── 7. Sentetik İnsan Bypass (ana saldırı) ────────────────────────────────
    async def test_synthetic_human_bypass(self, client):
        """
        Tüm 0.6.0 savunmalarını aşmaya çalışan tam bypass:
        - Geçerli token + 1.6s bekleme
        - Bézier + tremor mouse
        - Log-normal keystroke
        - Gerçekçi browser profili
        """
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TestResult("Sentetik İnsan Bypass", 0, 0, None, None, False, "ALLOW", error="Challenge alınamadı")

        await asyncio.sleep(1.6)
        tel = human_telemetry(desktop=True)
        token = build_token(ch, tel)
        status, ms, data = await self._post_score(client, {"token": token}, "SynthHuman")
        risk, decision = parse_response(data)

        allowed = status == 200 and (risk or 100) < 50
        return TestResult(
            scenario="Sentetik İnsan Bypass (ana test)",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=allowed,
            expected="ALLOW",
            notes="Bézier+tremor+lognormal — geçebilirse kritik açık"
        )

    # ── 8. Mobil Cihaz (plugins=0 yanlış pozitif koruması) ────────────────────
    async def test_mobile_false_positive(self, client):
        """
        Mobil cihazda plugins=0 normal — yanlış pozitif olmamalı.
        iOS Safari / Android Chrome → touch=True, plugins=0 → ALLOW beklenir.
        """
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TestResult("Mobil Yanlış Pozitif", 0, 0, None, None, False, "ALLOW", error="Challenge alınamadı")

        await asyncio.sleep(1.6)
        tel = human_telemetry(desktop=False)  # touch=True, plugins=0, ekran küçük
        token = build_token(ch, tel)
        status, ms, data = await self._post_score(client, {"token": token}, "MobileFP")
        risk, decision = parse_response(data)

        allowed = status == 200 and (risk or 100) < 50
        return TestResult(
            scenario="Mobil Yanlış Pozitif Koruması",
            http_status=status,
            response_ms=ms,
            risk_score=risk,
            decision=decision,
            passed=allowed,
            expected="ALLOW",
            notes="touch=True + plugins=0 → mobil normal, engellenmemeli"
        )

    # ── Ana Koşucu ─────────────────────────────────────────────────────────────
    async def run(self):
        console.rule("[bold cyan]Synapse Shield v0.6.0 — Adversarial Test Suite")
        console.print(f"[dim]Hedef: {self.base_url}[/dim]\n")

        tests = [
            ("Zaman Manipülasyonu",          self.test_time_manipulation),
            ("Geçerli Zamanlama",            self.test_valid_timing),
            ("Replay Attack",                self.test_replay_attack),
            ("Token Yok / Fallback",         self.test_no_token_fallback),
            ("Sahte HMAC",                   self.test_forged_signature),
            ("Headless Plugin",              self.test_headless_plugin),
            ("Sentetik İnsan Bypass",        self.test_synthetic_human_bypass),
            ("Mobil Yanlış Pozitif",         self.test_mobile_false_positive),
        ]

        async with httpx.AsyncClient(follow_redirects=True, http2=True) as client:
            for name, fn in tests:
                console.print(f"[yellow]▶ {name}...[/yellow]")
                result = await fn(client)
                self.results.append(result)

                icon = "✅" if result.passed else "❌"
                color = "green" if result.passed else "red"
                console.print(
                    f"  {icon} HTTP {result.http_status} | "
                    f"Risk: [{color}]{result.risk_score}%[/{color}] | "
                    f"Karar: {result.decision} | "
                    f"{result.response_ms}ms"
                )
                if result.notes:
                    console.print(f"  [dim]{result.notes}[/dim]")
                if result.error:
                    console.print(f"  [red]Hata: {result.error}[/red]")

                await asyncio.sleep(random.uniform(0.5, 1.5))

        self._print_report()
        self._save_report()

    def _print_report(self):
        console.rule("[bold]Sonuç Raporu")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Senaryo", style="cyan", no_wrap=True)
        table.add_column("Beklenen", justify="center")
        table.add_column("HTTP", justify="center")
        table.add_column("Risk %", justify="center")
        table.add_column("Sonuç", justify="center")

        for r in self.results:
            table.add_row(
                r.scenario,
                r.expected,
                str(r.http_status),
                f"{r.risk_score:.1f}" if r.risk_score is not None else "—",
                "✅ PASS" if r.passed else "❌ FAIL",
            )
        console.print(table)

        block_tests = [r for r in self.results if r.expected == "BLOCK"]
        allow_tests = [r for r in self.results if r.expected == "ALLOW"]
        block_ok = sum(1 for r in block_tests if r.passed)
        allow_ok = sum(1 for r in allow_tests if r.passed)

        console.print(f"\n[bold]Savunma testleri (BLOCK):[/bold] {block_ok}/{len(block_tests)}")
        console.print(f"[bold]Geçiş testleri (ALLOW):[/bold]   {allow_ok}/{len(allow_tests)}")

        # Kritik bulgular
        bypass = next((r for r in self.results if r.scenario.startswith("Sentetik") and r.passed), None)
        if bypass:
            console.print("\n[red bold]⚠ KRİTİK: Sentetik insan bypass başarılı — biyometrik eşikleri gözden geçir![/red bold]")

        fp = next((r for r in self.results if "Mobil" in r.scenario and not r.passed), None)
        if fp:
            console.print("[red bold]⚠ YANLIŞ POZİTİF: Mobil kullanıcılar engelleniyor![/red bold]")

        time_ok = next((r for r in self.results if "Zaman" in r.scenario and r.passed), None)
        if time_ok:
            console.print("[green]✓ Zaman manipülasyonu koruması aktif[/green]")

    def _save_report(self):
        fname = f"synapse_v060_adversarial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self.results], f, ensure_ascii=False, indent=2)
        console.print(f"\n[dim]Rapor: {fname}[/dim]")


# ─── Entry Point ───────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Synapse Shield v0.6.0 Adversarial Test")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Synapse Shield base URL")
    args = parser.parse_args()
    bot = SynapseAdversaryV060(base_url=args.url)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
