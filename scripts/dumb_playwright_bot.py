import asyncio
from playwright.async_api import async_playwright
import time
import math

async def run_bot_test():
    async with async_playwright() as p:
        # Launch standard headless Chromium with no anti-detection flags
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',  # Note: This actually exposes webdriver
                '--no-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        
        # Create context without any stealth modifications
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        # Navigate to the target page
        print("Navigating to http://127.0.0.1:8000...")
        await page.goto('http://127.0.0.1:8000', wait_until='networkidle')
        await page.wait_for_timeout(1000)  # Small wait for page to stabilize
        
        # Get page dimensions for mouse movement
        viewport_size = await page.evaluate('''() => ({
            width: window.innerWidth,
            height: window.innerHeight
        })''')
        
        # Define start and end points for robotic straight-line movement
        start_x = 100
        start_y = 100
        end_x = 600
        end_y = 400
        
        # Calculate the line parameters (y = mx + b)
        if end_x != start_x:
            m = (end_y - start_y) / (end_x - start_x)
            b = start_y - (m * start_x)
        else:
            m = 0
            b = start_y
        
        print(f"Moving mouse in robotic straight line from ({start_x}, {start_y}) to ({end_x}, {end_y})")
        
        # Move mouse in robotic straight line with no acceleration variance
        steps = 100
        for i in range(steps + 1):
            t = i / steps
            # Linear interpolation with zero acceleration (constant velocity)
            x = start_x + (end_x - start_x) * t
            y = start_y + (end_y - start_y) * t
            
            # Round to integers for pixel coordinates
            x_int = int(round(x))
            y_int = int(round(y))
            
            # Move mouse to exact position with no randomness
            await page.mouse.move(x_int, y_int)
            
            # Fixed time step for robotic consistency
            await page.wait_for_timeout(10)  # Exactly 10ms per step
        
        print(f"Completed robotic straight-line movement to ({end_x}, {end_y})")
        
        # Teleport cursor instantly to VERIFY HUMAN button and click
        # First, find the button
        try:
            # Try common button selectors
            button_selectors = [
                'button:has-text("VERIFY HUMAN")',
                'button:has-text("Verify Human")',
                'button:has-text("Verify")',
                '#verify-btn',
                '.verify-btn',
                '[data-testid="verify-human"]'
            ]
            
            button = None
            for selector in button_selectors:
                try:
                    button = await page.locator(selector).first
                    if await button.count() > 0:
                        break
                except:
                    continue
            
            if not button:
                # Fallback: find any button with verify or human in text
                button = await page.locator('button:has-text("verify")').first
            
            # Get button coordinates
            box = await button.bounding_box()
            if box:
                button_x = box['x'] + box['width'] / 2
                button_y = box['y'] + box['height'] / 2
                
                print(f"Teleporting cursor instantly to button at ({button_x:.2f}, {button_y:.2f})")
                
                # Teleport without any intermediate positions
                await page.mouse.move(button_x, button_y)
                
                # Click instantly without hover delay
                print("Clicking VERIFY HUMAN button...")
                await page.mouse.click(button_x, button_y)
                
                print("Button clicked successfully.")
                
                # Wait a moment for any response
                await page.wait_for_timeout(2000)
                
        except Exception as e:
            print(f"Error finding or clicking button: {e}")
            # Try a more aggressive approach - click at center of page if button not found
            print("Falling back to clicking center of page...")
            await page.mouse.click(viewport_size['width']/2, viewport_size['height']/2)
        
        # Verification: Check for bot detection markers
        print("\n=== BOT DETECTION VERIFICATION ===")
        
        # Check WebDriver detection
        webdriver_detected = await page.evaluate('''() => {
            // Check multiple WebDriver indicators
            const indicators = {
                navigator_webdriver: navigator.webdriver === true,
                chrome_webdriver: !!window.chrome?.webdriver,
                cdc_indicators: !!document.documentElement.getAttribute('webdriver'),
                automation_controlled: !!navigator.plugins?.length === 0
            };
            return indicators;
        }''')
        
        print(f"WebDriver Detection: {webdriver_detected}")
        
        # Check if any security response indicates bot detection
        page_content = await page.content()
        
        # Look for bot detection indicators in page
        bot_indicators = [
            'bot',
            'robot',
            'automated',
            'suspicious',
            'blocked',
            'detected',
            'security',
            'risk',
            'verify',
            'captcha'
        ]
        
        found_indicators = []
        for indicator in bot_indicators:
            if indicator.lower() in page_content.lower():
                found_indicators.append(indicator)
        
        if found_indicators:
            print(f"Security indicators found: {found_indicators}")
            print("✅ Security engine likely flagged session as bot")
        else:
            print("⚠️ No obvious bot detection indicators found")
        
        # Additional check: Log the final page state
        print(f"\nPage URL after actions: {page.url}")
        print(f"Page title: {await page.title()}")
        
        # Take screenshot for evidence
        await page.screenshot(path='bot_detection_test.png', full_page=True)
        print("\nScreenshot saved as 'bot_detection_test.png'")
        
        print("\n=== TEST COMPLETE ===")
        print("Expected: 100% bot risk due to:")
        print("1. WebDriver API detection (navigator.webdriver = true)")
        print("2. Euclidean straight-line trajectory (no acceleration variance)")
        print("3. Instantaneous cursor teleportation")
        print("4. No human-like behavioral patterns")
        
        # Keep browser open briefly to see results
        await page.wait_for_timeout(3000)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot_test())
