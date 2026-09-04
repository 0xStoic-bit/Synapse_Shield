import asyncio
import math
import random
import numpy as np
from playwright.async_api import async_playwright
from datetime import datetime
import json
import time

class StealthBot:
    def __init__(self):
        self.target_url = "http://127.0.0.1:8000"
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "detection_flags": [],
            "mouse_path": [],
            "typing_metrics": []
        }
        
    async def setup_browser(self):
        playwright = await async_playwright().start()
        
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials',
            '--disable-web-security',
            '--disable-features=BlockInsecurePrivateNetworkRequests',
            '--disable-features=OutOfBlinkCors',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-setuid-sandbox',
            '--disable-accelerated-2d-canvas',
            '--disable-accelerated-jpeg-decoding',
            '--disable-accelerated-mjpeg-decode',
            '--disable-accelerated-video-decode'
        ]
        
        browser = await playwright.chromium.launch(
            headless=False,
            args=launch_args
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation', 'notifications'],
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            color_scheme='light',
            accept_downloads=True
        )
        
        page = await context.new_page()
        
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            
            const plugins = [];
            plugins.push({0: {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}, name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1});
            plugins.push({0: {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''}, name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1});
            plugins.push({0: {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}, name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 1});
            plugins.length = 3;
            Object.setPrototypeOf(plugins, Array.prototype);
            Object.defineProperty(navigator, 'plugins', { get: () => plugins, configurable: true });
            
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                if (parameter === 7937) return 'Intel Inc.';
                if (parameter === 7938) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
            
            const originalToString = Function.prototype.toString;
            Function.prototype.toString = function() {
                if (this === navigator.webdriver || this === navigator.plugins) {
                    return 'function () { [native code] }';
                }
                return originalToString.call(this);
            };
            
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32', configurable: true });
            
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = function(parameters) {
                if (parameters.name === 'notifications') return Promise.resolve({state: 'denied'});
                return originalQuery.call(this, parameters);
            };
            
            const originalLog = console.log;
            console.log = function() {
                const args = Array.from(arguments);
                if (args.some(arg => typeof arg === 'string' && (arg.includes('AutomationControlled') || arg.includes('webdriver') || arg.includes('cdp')))) return;
                originalLog.apply(console, args);
            };
        """)
        return browser, context, page
    
    def generate_bezier_curve(self, start_x, start_y, end_x, end_y, num_points=50):
        c1_x = start_x + random.uniform(-100, 100) + random.uniform(50, 150)
        c1_y = start_y + random.uniform(-50, 50) + random.uniform(-50, 50)
        c2_x = end_x + random.uniform(-100, 100) - random.uniform(50, 150)
        c2_y = end_y + random.uniform(-50, 50) + random.uniform(-50, 50)
        
        points = []
        for t in np.linspace(0, 1, num_points):
            x = (1-t)**3 * start_x + 3*(1-t)**2*t * c1_x + 3*(1-t)*t**2 * c2_x + t**3 * end_x
            y = (1-t)**3 * start_y + 3*(1-t)**2*t * c1_y + 3*(1-t)*t**2 * c2_y + t**3 * end_y
            x += random.gauss(0, 0.5)
            y += random.gauss(0, 0.5)
            points.append((x, y))
        return points
    
    def add_tremor(self, points, frequency1=8, frequency2=12, amplitude=1.5):
        tremor_points = []
        for i, (x, y) in enumerate(points):
            t = i / len(points)
            tremor_x = amplitude * (math.sin(2 * math.pi * frequency1 * t) + 0.7 * math.sin(2 * math.pi * frequency2 * t))
            tremor_y = amplitude * (math.sin(2 * math.pi * frequency1 * t + math.pi/2) + 0.7 * math.sin(2 * math.pi * frequency2 * t + math.pi/3))
            noise_x = random.gauss(0, 0.3)
            noise_y = random.gauss(0, 0.3)
            tremor_points.append((x + tremor_x + noise_x, y + tremor_y + noise_y))
        return tremor_points
    
    async def submit_form_with_stealth(self, page):
        try:
            print("Waiting for page to load...")
            await asyncio.sleep(random.uniform(2, 3))
            
            button_selectors = [
                'button:has-text("VERIFY HUMAN")',
                'button:has-text("Verify Human")',
                '#verify-btn',
                '.verify-btn',
                '[data-testid="verify-human"]'
            ]
            
            button = None
            for selector in button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=2000)
                    if button:
                        break
                except:
                    continue
            
            if not button:
                button = await page.locator('button:has-text("verify")').first
                
            if not button:
                print("Verify button not found")
                return
            
            box = await button.bounding_box()
            if not box:
                return
                
            start_x = random.randint(100, 500)
            start_y = random.randint(100, 400)
            end_x = box['x'] + box['width'] / 2
            end_y = box['y'] + box['height'] / 2
            
            print("Moving mouse to verify button with stealth tremor...")
            path = self.generate_bezier_curve(start_x, start_y, end_x, end_y, 60)
            path_with_tremor = self.add_tremor(path)
            
            for x, y in path_with_tremor:
                await page.mouse.move(x, y, steps=1)
                await asyncio.sleep(random.uniform(0.005, 0.015))
            
            self.results['mouse_path'] = path_with_tremor[:20]
            
            await asyncio.sleep(random.uniform(0.3, 0.7))
            
            print("Clicking verify button...")
            await page.mouse.click(end_x, end_y)
            
            print("Waiting for API response...")
            await asyncio.sleep(3)
            
            await self.check_detection_evidence(page)
            
            screenshot_path = f"stealth_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved to {screenshot_path}")
            
        except Exception as e:
            print(f"Error during button click: {e}")
            self.results['detection_flags'].append(f"Error: {str(e)}")
    
    async def check_detection_evidence(self, page):
        pass
    
    async def run(self):
        browser = None
        context = None
        page = None
        try:
            print("Initializing stealth browser...")
            browser, context, page = await self.setup_browser()
            print(f"Navigating to {self.target_url}...")
            await page.goto(self.target_url, wait_until='networkidle', timeout=30000)
            print("Dwelling on page...")
            await asyncio.sleep(random.uniform(2, 3))
            
            await self.submit_form_with_stealth(page)
            
            self.results['success'] = True
            self.results['end_time'] = datetime.now().isoformat()
            
            results_file = f"stealth_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"Test complete. Results saved to {results_file}")
            print(f"Detection flags: {len(self.results['detection_flags'])}")
        except Exception as e:
            print(f"Fatal error: {e}")
            self.results['success'] = False
            self.results['error'] = str(e)
        finally:
            if browser: await browser.close()
            if context: await context.close()
    
async def main():
    bot = StealthBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
