"""
Advanced Async Human-like Bot for Black-Box Protected Sites
Requirements: pip install playwright asyncio aiohttp beautifulsoup4
Run: python -m playwright install chromium
"""

import asyncio
import random
import json
import time
import hashlib
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp
from playwright.async_api import async_playwright, Page, Browser, Response, Route

# ============ KONFIGÜRASYON ============
@dataclass
class BotConfig:
    target_url: str = "http://127.0.0.1:8000"
    username: str = "test_user"
    password: str = "test_pass"
    
    # İnsan davranışı parametreleri
    min_typing_delay: float = 0.05   # 50ms
    max_typing_delay: float = 0.25   # 250ms
    mouse_move_steps: int = 15       # Fare hareketi nokta sayısı
    think_time_min: float = 1.0      # Düşünme süresi (sn)
    think_time_max: float = 3.5
    
    # Headless mod (gelişmiş korumalar için False önerilir)
    headless: bool = False
    
    # Proxy (opsiyonel)
    proxy: Optional[Dict] = None
    
    # User-Agent (gerçek bir tarayıcıdan alınmış)
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ============ TELEMETRI TOPLAYICI ============
class TelemetryCollector:
    """İnsan benzeri telemetri üretir"""
    
    @staticmethod
    async def human_like_mouse_movement(page: Page, target_x: int, target_y: int):
        """Bezier eğrisi ile doğal fare hareketi"""
        # Mevcut fare pozisyonunu al
        current = await page.evaluate("() => ({x: window.mouseX || 0, y: window.mouseY || 0})")
        start_x, start_y = current.get('x', 0), current.get('y', 0)
        
        # Rastgele saptırma (insanlar tam düz çizgi çizmez)
        steps = random.randint(12, 20)
        for i in range(steps):
            t = i / steps
            # Bezier benzeri eğri
            progress = t * t * (3 - 2 * t)  # Smoothstep
            noise_x = random.uniform(-30, 30) * (1 - t)
            noise_y = random.uniform(-30, 30) * (1 - t)
            
            x = int(start_x + (target_x - start_x) * progress + noise_x)
            y = int(start_y + (target_y - start_y) * progress + noise_y)
            
            await page.mouse.move(x, y, steps=1)
            await asyncio.sleep(random.uniform(0.01, 0.03))
        
        # Son noktaya tam git
        await page.mouse.move(target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
    
    @staticmethod
    async def human_typing(page: Page, selector: str, text: str):
        """İnsan gibi yazma (rastgele gecikmeler, hatalar, düzeltmeler)"""
        await page.click(selector)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        
        # Önce temizle
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(random.uniform(0.1, 0.2))
        
        for i, char in enumerate(text):
            # Rastgele hata yapma ihtimali (%2)
            if random.random() < 0.02 and i > 2:
                # Yanlış karakter yaz, sil, düzelt
                wrong_char = random.choice("abcdefghijklmnopqrstuvwxyz")
                await page.keyboard.type(wrong_char, delay=random.randint(30, 80))
                await asyncio.sleep(random.uniform(0.1, 0.2))
                await page.keyboard.press("Backspace")
                await asyncio.sleep(random.uniform(0.05, 0.15))
            
            # Normal karakter
            delay = random.uniform(
                BotConfig.min_typing_delay,
                BotConfig.max_typing_delay
            )
            # Büyük harf veya özel karakterlerde biraz daha yavaş
            if char.isupper() or char in "!@#$%^&*()":
                delay *= 1.5
            await page.keyboard.type(char, delay=delay)
        
        await asyncio.sleep(random.uniform(0.1, 0.3))
    
    @staticmethod
    async def random_mouse_activity(page: Page):
        """Rastgele fare hareketi (insan gibi gezinme)"""
        for _ in range(random.randint(2, 5)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            await TelemetryCollector.human_like_mouse_movement(page, x, y)
            await asyncio.sleep(random.uniform(0.5, 2.0))
    
    @staticmethod
    async def random_scroll(page: Page):
        """Rastgele kaydırma"""
        scrolls = random.randint(1, 3)
        for _ in range(scrolls):
            amount = random.randint(100, 500)
            direction = random.choice([-1, 1])
            await page.mouse.wheel(delta_x=0, delta_y=amount * direction)
            await asyncio.sleep(random.uniform(0.3, 1.0))

# ============ CHALLENGE YAKALAYICI ============
class ChallengeInterceptor:
    """Network intercept ile token/challenge yakalama"""
    
    def __init__(self):
        self.captured_tokens: Dict = {}
        self.challenge_responses: Dict = {}
    
    async def setup_interception(self, page: Page):
        """Request/Response intercept kurulumu"""
        
        # Request intercept - challenge parametrelerini yakala
        await page.route("**/*", self._handle_request)
        
        # Response intercept - token'ları yakala
        page.on("response", self._handle_response)
    
    async def _handle_request(self, route: Route):
        """Request intercept handler"""
        request = route.request
        url = request.url
        
        # Challenge içeren request'leri yakala
        if "challenge" in url.lower() or "token" in url.lower() or "captcha" in url.lower():
            self.captured_tokens[url] = {
                "headers": request.headers,
                "method": request.method,
                "post_data": request.post_data,
                "timestamp": time.time()
            }
        
        # Headers'a ek bilgi ekle (bot tespitini zorlaştır)
        headers = request.headers.copy()
        headers.update({
            "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })
        
        await route.continue_(headers=headers)
    
    async def _handle_response(self, response: Response):
        """Response intercept handler"""
        url = response.url
        if "challenge" in url.lower() or "token" in url.lower():
            try:
                body = await response.body()
                self.challenge_responses[url] = {
                    "body": body.decode('utf-8', errors='ignore'),
                    "headers": response.headers,
                    "status": response.status,
                    "timestamp": time.time()
                }
            except:
                pass

# ============ ANA BOT SINIFI ============
class AdvancedAsyncBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None
        self.challenge_interceptor = ChallengeInterceptor()
        self.session_cookies = {}
        self.session_storage = {}
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def init_browser(self):
        """Playwright tarayıcısını başlat"""
        p = await async_playwright().start()
        
        # Chromium kullan (en iyi emülasyon)
        self.browser = await p.chromium.launch(
            headless=self.config.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-sync",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-component-extensions-with-background-pages",
                "--disable-client-side-phishing-detection",
                "--disable-crash-reporter",
                "--disable-breakpad",
            ]
        )
        
        # Browser context oluştur (session için)
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=self.config.user_agent,
            proxy=self.config.proxy,
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation", "notifications"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            color_scheme="light",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1",
                "Sec-GPC": "1",
            }
        )
        
        # WebGL ve Canvas fingerprint koruması
        await self.context.add_init_script("""
            // WebGL fingerprint koruması
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return "Intel Inc.";
                }
                if (parameter === 37446) {
                    return "Intel Iris OpenGL Engine";
                }
                return getParameter(parameter);
            };
            
            // Canvas fingerprint koruması
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
                if (type === 'image/png' && this.width === 220 && this.height === 30) {
                    const context = this.getContext('2d');
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    // Rastgele gürültü ekle
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] = imageData.data[i] + Math.floor(Math.random() * 2);
                    }
                    context.putImageData(imageData, 0, 0);
                }
                return originalToDataURL.call(this, type, quality);
            };
            
            // navigator.webdriver gizleme
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            
            // window.chrome gizleme
            window.chrome = { runtime: {} };
            
            // Permission API'yi normalleştir
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        self.page = await self.context.new_page()
        
        # Network intercept kurulumu
        await self.challenge_interceptor.setup_interception(self.page)
        
        # Konsol loglarını yakala (debug için)
        self.page.on("console", lambda msg: print(f"Console: {msg.text}"))
        
        return self.page
    
    async def navigate_with_behavior(self, url: str):
        """İnsan benzeri navigasyon"""
        # Önce rastgele fare hareketi
        await TelemetryCollector.random_mouse_activity(self.page)
        
        # Navigate et
        response = await self.page.goto(url, wait_until="networkidle")
        
        # Sayfa yüklendikten sonra rastgele scroll ve fare hareketi
        await TelemetryCollector.random_scroll(self.page)
        await TelemetryCollector.random_mouse_activity(self.page)
        
        # Challenge varsa beklet (JS çalışması için)
        await asyncio.sleep(random.uniform(2, 4))
        
        return response
    
    async def solve_challenge(self) -> bool:
        """Challenge çözümü - Black-box yaklaşımı"""
        # Challenge varsa, Playwright otomatik olarak JS çalıştırır
        # Ekstra olarak, sayfadaki challenge elementlerini bekle
        
        try:
            # Yaygın challenge elementleri
            challenge_selectors = [
                "iframe[src*='challenge']",
                "div[class*='challenge']",
                "#challenge",
                ".cf-browser-verification",
                ".turnstile",
                ".hcaptcha",
                ".g-recaptcha"
            ]
            
            for selector in challenge_selectors:
                loc = self.page.locator(selector)
                if await loc.count() > 0:
                    print(f"Challenge detected: {selector}")
                    # Challenge'ın çözülmesini bekle (maks 30sn)
                    await self.page.wait_for_selector(
                        selector, 
                        state="detached", 
                        timeout=30000
                    )
                    print("Challenge solved!")
                    return True
            
            # Kendi sitemiz için "VERIFY HUMAN" butonuna tıklama denemesi
            try:
                verify_btn = self.page.locator("button:has-text('VERIFY HUMAN')")
                if await verify_btn.count() > 0:
                    print("Found 'VERIFY HUMAN' button, clicking...")
                    
                    # Butonun koordinatlarını al
                    box = await verify_btn.bounding_box()
                    if box:
                        # Butona doğru insan gibi fare hareketi
                        target_x = box['x'] + box['width'] / 2
                        target_y = box['y'] + box['height'] / 2
                        await TelemetryCollector.human_like_mouse_movement(self.page, target_x, target_y)
                        
                        # Tıkla
                        await verify_btn.click()
                        await asyncio.sleep(2)
                        return True
            except Exception as e:
                print(f"Error clicking verify button: {e}")
            
            return True  # Challenge yok veya çözüldü
            
        except Exception as e:
            print(f"Challenge handling error: {e}")
            return False
    
    async def perform_login(self) -> Tuple[bool, Dict]:
        """Login işlemini gerçekleştir"""
        try:
            # 1. Sayfaya git ve challenge'ı bekle
            await self.navigate_with_behavior(self.config.target_url)
            
            # 2. Challenge çözümü
            if not await self.solve_challenge():
                return False, {"error": "Challenge çözülemedi"}
            
            # API skorlaması sonucu UI'da başarı / block durumunu kontrol et
            try:
                # Biraz bekle API cevabı gelsin
                await asyncio.sleep(2)
                
                # Verified Human olup olmadığını kontrol et
                success_el = self.page.locator("text='VERIFIED HUMAN (ALLOW)'")
                if await success_el.count() > 0:
                    print("Success UI detected!")
                    self.session_cookies = {c['name']: c['value'] for c in await self.context.cookies()}
                    return True, {
                        "cookies": self.session_cookies,
                        "storage": {},
                        "captured_tokens": self.challenge_interceptor.captured_tokens,
                        "challenge_responses": self.challenge_interceptor.challenge_responses,
                        "ui_status": "verified_human"
                    }
                    
                # Bot Detected olup olmadığını kontrol et
                block_el = self.page.locator("text='BOT DETECTED (BLOCK 403)'")
                if await block_el.count() > 0:
                    print("Bot Block UI detected!")
                    return False, {"error": "Blocked by Synapse Shield (Bot Detected)"}
                    
            except Exception as e:
                print(f"UI check error: {e}")
                
            return False, {"error": "Login success UI not found"}
            
        except Exception as e:
            return False, {"error": str(e)}
    
    async def check_login_success(self) -> bool:
        """Giriş başarılı mı kontrol et"""
        try:
            # URL değişimi kontrol et
            current_url = self.page.url
            
            # Başarılı giriş URL pattern'leri
            success_patterns = ["dashboard", "home", "account", "profile", "panel"]
            if any(pattern in current_url.lower() for pattern in success_patterns):
                return True
            
            # Cookie kontrolü (session token)
            for cookie in await self.context.cookies():
                if "session" in cookie['name'].lower() or "token" in cookie['name'].lower():
                    return True
            
            # Sayfa içeriği kontrolü
            content = await self.page.content()
            success_texts = ["başarılı", "success", "hoş geldin", "welcome"]
            if any(text in content.lower() for text in success_texts):
                return True
            
            return False
            
        except:
            return False
    
    async def extract_tokens(self) -> Dict:
        """Challenge token'larını ve proof'ları çıkar"""
        tokens = {
            "cookies": self.session_cookies,
            "local_storage": self.session_storage.get("localStorage", {}),
            "session_storage": self.session_storage.get("sessionStorage", {}),
            "captured": self.challenge_interceptor.captured_tokens,
            "challenge_responses": self.challenge_interceptor.challenge_responses
        }
        
        # JavaScript ile token'ları bul
        js_tokens = await self.page.evaluate("""() => {
            const tokens = {};
            // Cookie'leri kontrol et
            document.cookie.split(';').forEach(cookie => {
                const [key, value] = cookie.trim().split('=');
                if (key && value) {
                    tokens[key] = value;
                }
            });
            
            // Meta tag'leri kontrol et
            document.querySelectorAll('meta[name*="token"], meta[name*="csrf"]').forEach(meta => {
                tokens[meta.name] = meta.content;
            });
            
            return tokens;
        }""")
        
        tokens.update(js_tokens)
        return tokens
    
    async def close(self):
        """Kaynakları temizle"""
        if self.browser:
            await self.browser.close()

# ============ ASENKRON ANA FONKSİYON ============
async def main():
    config = BotConfig(
        target_url="http://127.0.0.1:8000",  # Synapse Shield Demo Sitesi
        username="kullanici_adiniz",
        password="sifreniz",
        headless=True  # Test için headless mod
    )
    
    async with AdvancedAsyncBot(config) as bot:
        # Tarayıcıyı başlat
        await bot.init_browser()
        
        # Login işlemi
        success, result = await bot.perform_login()
        
        if success:
            print("✅ Giriş başarılı!")
            print(f"📦 Cookies: {result['cookies']}")
            
            # Token'ları çıkar
            tokens = await bot.extract_tokens()
            # print(f"🔑 Tokens: {tokens}")
            
            # Challenge bilgileri
            print(f"🎯 Challenge bilgileri: {len(result['captured_tokens'])} request yakalandı")
            
        else:
            print(f"❌ Giriş başarısız: {result}")
            if 'error' in result:
                print(f"Hata: {result['error']}")

if __name__ == "__main__":
    asyncio.run(main())
