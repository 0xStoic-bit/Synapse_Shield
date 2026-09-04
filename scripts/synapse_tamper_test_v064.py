"""
Synapse Shield v0.6.4 — Anti-Stealth & Tamper Proofing Test Suite
==================================================================
"""

import asyncio
import argparse
import base64
import json
import math
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import httpx
from rich.console import Console
from rich.table import Table

console = Console()


async def get_challenge(client: httpx.AsyncClient, base_url: str) -> Optional[str]:
    try:
        resp = await client.get(f"{base_url}/api/challenge", timeout=5.0)
        if resp.status_code == 200:
            return resp.json().get("challenge")
    except Exception:
        pass
    return None


def build_token(challenge: str, telemetry: dict) -> str:
    envelope = {
        "challenge": challenge,
        "telemetry": telemetry,
        "created_at": int(time.time() * 1000),
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()


def base_browser(desktop=True) -> dict:
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


def human_mouse(n=45) -> list:
    events, t = [], 0
    x, y = 100, 200
    for i in range(n):
        x += random.randint(5, 20) + random.gauss(0, 2)
        y += random.gauss(0, 8)
        t += max(10, 20 + random.gauss(0, 5))
        events.append({"x": round(x, 1), "y": round(y, 1), "t": round(t, 1)})
    return events


def full_telemetry(browser_overrides: dict = None, desktop=True) -> dict:
    browser = base_browser(desktop)
    if browser_overrides:
        browser.update(browser_overrides)
    return {
        "mouse_movements": human_mouse(),
        "clicks": [{"x": 700, "y": 350, "t": 1100.0}],
        "keystrokes": [],
        "scrolls": [],
        "browser": browser,
    }


def parse_resp(data: dict):
    risk = data.get("bot_score") or data.get("risk_score") or 0.0
    decision = data.get("classification") or data.get("decision") or "—"
    reasons = data.get("reasons", [])
    return float(risk), str(decision), reasons


@dataclass
class TamperResult:
    scenario: str
    expected: str
    http_status: int
    response_ms: float
    risk_score: float
    decision: str
    passed: bool
    tamper_flags: dict
    reasons: list
    error: Optional[str] = None


class TamperTestSuite:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.results: list[TamperResult] = []

    async def _score(self, client, payload) -> tuple[int, float, dict]:
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
            return 0, 0.0, {"error": str(e)}

    async def _run_tamper_test(
        self,
        client,
        scenario: str,
        expected: str,
        tamper_flags: dict,
        desktop: bool = True,
        wait: float = 1.6,
    ) -> TamperResult:
        ch = await get_challenge(client, self.base_url)
        if not ch:
            return TamperResult(scenario, expected, 0, 0, 0, "—", False, tamper_flags, [], error="Challenge alınamadı")

        await asyncio.sleep(wait)
        tel = full_telemetry(browser_overrides=tamper_flags, desktop=desktop)
        token = build_token(ch, tel)
        status, ms, data = await self._score(client, {"token": token})
        risk, decision, reasons = parse_resp(data)

        if expected == "BLOCK":
            passed = status in (403, 429) or risk >= 50.0 or decision.upper() in ("BOT", "BLOCK")
        else:
            passed = status == 200 and risk < 50.0 and decision.upper() in ("HUMAN", "ALLOW", "—")

        return TamperResult(scenario, expected, status, ms, risk, decision, passed, tamper_flags, reasons)

    async def test_plugin_array_fake(self, client):
        return await self._run_tamper_test(client, "Plugin Array Sahte (is_plugin_array_fake=True)", "BLOCK", {"is_plugin_array_fake": True})

    async def test_webdriver_own_prop(self, client):
        return await self._run_tamper_test(client, "WebDriver OwnProp (has_webdriver_own_prop=True)", "BLOCK", {"has_webdriver_own_prop": True})

    async def test_webgl_hooked(self, client):
        return await self._run_tamper_test(client, "WebGL Hooked (is_webgl_hooked=True)", "BLOCK", {"is_webgl_hooked": True})

    async def test_canvas_hooked(self, client):
        return await self._run_tamper_test(client, "Canvas Hooked (is_canvas_hooked=True)", "BLOCK", {"is_canvas_hooked": True})

    async def test_full_stealth_kit(self, client):
        return await self._run_tamper_test(client, "Full Stealth Kit (4 tamper birden)", "BLOCK", {"is_plugin_array_fake": True, "has_webdriver_own_prop": True, "is_webgl_hooked": True, "is_canvas_hooked": True})

    async def test_webgl_canvas_combo(self, client):
        return await self._run_tamper_test(client, "WebGL + Canvas Hooked (80+80 Risk)", "BLOCK", {"is_webgl_hooked": True, "is_canvas_hooked": True})

    async def test_plugin_webdriver_combo(self, client):
        return await self._run_tamper_test(client, "Plugin Sahte + WebDriver OwnProp (200 Risk)", "BLOCK", {"is_plugin_array_fake": True, "has_webdriver_own_prop": True})

    async def test_brave_user(self, client):
        return await self._run_tamper_test(client, "Brave Kullanıcısı (sadece canvas_hooked, temiz mouse)", "ALLOW", {"is_canvas_hooked": True})

    async def test_mobile_clean(self, client):
        return await self._run_tamper_test(client, "Temiz Mobil Kullanıcı (plugins=0, touch=True)", "ALLOW", {}, desktop=False)

    async def test_clean_desktop(self, client):
        return await self._run_tamper_test(client, "Temiz Masaüstü (sıfır tamper)", "ALLOW", {}, desktop=True)

    async def test_stealth_clean_mouse(self, client):
        return await self._run_tamper_test(client, "Stealth + Mükemmel Mouse (160 Risk, mouse temiz)", "BLOCK", {"is_webgl_hooked": True, "is_canvas_hooked": True})

    async def run(self):
        console.rule("[bold cyan]Synapse Shield v0.6.4 — Tamper Proofing Test Suite")
        console.print(f"[dim]Hedef: {self.base_url}[/dim]\n")

        tests = [
            ("Plugin Array Sahte",          self.test_plugin_array_fake),
            ("WebDriver OwnProp",           self.test_webdriver_own_prop),
            ("WebGL Hooked",                self.test_webgl_hooked),
            ("Canvas Hooked",               self.test_canvas_hooked),
            ("Full Stealth Kit",            self.test_full_stealth_kit),
            ("WebGL + Canvas",              self.test_webgl_canvas_combo),
            ("Plugin + WebDriver",          self.test_plugin_webdriver_combo),
            ("Stealth + Temiz Mouse",       self.test_stealth_clean_mouse),
            ("Brave Kullanıcısı",           self.test_brave_user),
            ("Temiz Mobil",                 self.test_mobile_clean),
            ("Temiz Masaüstü",              self.test_clean_desktop),
        ]

        async with httpx.AsyncClient(follow_redirects=True, http2=True) as client:
            for name, fn in tests:
                console.print(f"[yellow]▶ {name}...[/yellow]")
                # IP ban ve rate limit temizliği
                try:
                    await client.post(f"{self.base_url}/api/clear")
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                
                result = await fn(client)
                self.results.append(result)
                icon = "✅" if result.passed else "❌"
                color = "red" if result.risk_score >= 50 else "green"
                console.print(f"  {icon} HTTP {result.http_status} | Risk: [{color}]{result.risk_score:.1f}%[/{color}] | Karar: {result.decision} | {result.response_ms}ms")
                if result.reasons:
                    for r in result.reasons[:2]:
                        console.print(f"  [dim]→ {r[:90]}[/dim]")
                if result.error:
                    console.print(f"  [red]Hata: {result.error}[/red]")
                await asyncio.sleep(0.5)

        self._print_report()
        self._save_report()

    def _print_report(self):
        console.rule("[bold]Sonuç Raporu")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Senaryo", style="cyan")
        table.add_column("Beklenen", justify="center")
        table.add_column("HTTP", justify="center")
        table.add_column("Risk %", justify="right")
        table.add_column("Sonuç", justify="center")

        for r in self.results:
            table.add_row(r.scenario, r.expected, str(r.http_status), f"{r.risk_score:.1f}", "✅ PASS" if r.passed else "❌ FAIL")
        console.print(table)

        block_tests = [r for r in self.results if r.expected == "BLOCK"]
        allow_tests = [r for r in self.results if r.expected == "ALLOW"]
        block_ok = sum(1 for r in block_tests if r.passed)
        allow_ok = sum(1 for r in allow_tests if r.passed)

        console.print(f"\n[bold]Tamper engelleme:[/bold] {block_ok}/{len(block_tests)}")
        console.print(f"[bold]False positive koruması:[/bold] {allow_ok}/{len(allow_tests)}")
        if sum(1 for r in self.results if not r.passed) == 0:
            console.print("\n[green bold]✓ Tüm testler geçti — v0.6.4 tamper koruması sağlam![/green bold]")

    def _save_report(self):
        fname = f"tamper_test_v064_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self.results], f, ensure_ascii=False, indent=2)


async def main():
    parser = argparse.ArgumentParser(description="Synapse Shield v0.6.4 Tamper Test")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    suite = TamperTestSuite(base_url=args.url)
    await suite.run()


if __name__ == "__main__":
    asyncio.run(main())
