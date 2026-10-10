import asyncio
import importlib
import pkgutil
from typing import Callable, Dict, Any, List, Tuple

# Central Registry
ATTACK_REGISTRY: Dict[str, List[Tuple[int, Callable]]] = {}

def redteam_attack(category: str, weight: int = 1):
    """
    Decorator to register a function as a red team plugin.
    Categories can represent lifecycle phases (e.g., 'init', 'teardown')
    or attack types (e.g., 'tamper', 'pow_bypass').
    """
    def decorator(func: Callable):
        if category not in ATTACK_REGISTRY:
            ATTACK_REGISTRY[category] = []
        ATTACK_REGISTRY[category].append((weight, func))
        ATTACK_REGISTRY[category].sort(key=lambda x: x[0], reverse=True)
        return func
    return decorator

class SynapseRedTeamOrchestrator:
    def __init__(self):
        self.registry = ATTACK_REGISTRY
        self.shared_state: Dict[str, Any] = {}

    def discover_plugins(self, package_name: str):
        """
        Dynamically load all modules in a package so decorators are triggered.
        (Grafted from Candidate 2)
        """
        package = importlib.import_module(package_name)
        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            importlib.import_module(f"{package_name}.{module_name}")
        print(f"[Orchestrator] Discovered attacks in categories: {list(self.registry.keys())}")

    async def run_category(self, category: str):
        funcs = self.registry.get(category, [])
        if not funcs:
            return []
            
        print(f"[Orchestrator] Running {len(funcs)} attacks in '{category}'")
        tasks = [func(self.shared_state) for _, func in funcs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def run_full_scenario(self):
        """
        Lifecycle execution (Concept grafted from Candidate 1)
        """
        print("[Orchestrator] Starting Full Red Team Scenario")
        await self.run_category("init")
        
        # Run all categories that aren't init/teardown
        attack_categories = [cat for cat in self.registry.keys() if cat not in ("init", "teardown")]
        for cat in attack_categories:
            await self.run_category(cat)
            
        await self.run_category("teardown")
        print("[Orchestrator] Scenario Complete")


import time

@redteam_attack(category="bot", weight=10)
async def linear_bot_plugin(shared_state: Dict[str, Any]):
    print("[Attack] Executing linear_bot_plugin (Straightness = 1.0, Jerk = 0)...")
    try:
        from .live_attacker import send_attack
    except ImportError:
        return
    t = int(time.time() * 1000)
    payload = {"mouse_movements": [{"x": 50 + i * 30, "y": 50 + i * 20, "t": t + i * 20} for i in range(25)]}
    return await asyncio.to_thread(send_attack, "Linear Bot Plugin", payload, 201)

@redteam_attack(category="stealth", weight=20)
async def bezier_stealth_plugin(shared_state: Dict[str, Any]):
    print("[Attack] Executing bezier_stealth_plugin (Curvature violation)...")
    try:
        from .live_attacker import send_attack
    except ImportError:
        return
    t = int(time.time() * 1000)
    p0, p1, p2 = (50, 50), (400, 700), (900, 200)
    bezier_pts = [
        {
            "x": round((1 - i / 30) ** 2 * p0[0] + 2 * (1 - i / 30) * (i / 30) * p1[0] + (i / 30) ** 2 * p2[0]),
            "y": round((1 - i / 30) ** 2 * p0[1] + 2 * (1 - i / 30) * (i / 30) * p1[1] + (i / 30) ** 2 * p2[1]),
            "t": t + i * 20,
        }
        for i in range(30)
    ]
    return await asyncio.to_thread(send_attack, "Bezier Stealth Plugin", {"mouse_movements": bezier_pts}, 202)

@redteam_attack(category="bot", weight=15)
async def keystroke_injection_plugin(shared_state: Dict[str, Any]):
    print("[Attack] Executing keystroke_injection_plugin (Fixed delay)...")
    try:
        from .live_attacker import send_attack
    except ImportError:
        return
    t = int(time.time() * 1000)
    keys = [{"type": "down", "t": t + i * 50} for i in range(12)]
    return await asyncio.to_thread(send_attack, "Keystroke Injection Plugin", {"keystrokes": keys, "clicks": [{"x": 100, "y": 100, "t": t}]}, 203)

@redteam_attack(category="tamper", weight=30)
async def stealth_tamper_plugin(shared_state: Dict[str, Any]):
    print("[Attack] Executing stealth_tamper_plugin (Headless WebDriver)...")
    try:
        from .live_attacker import send_attack
    except ImportError:
        return
    payload = {"browser": {"webdriver": True, "screen_width": 800, "screen_height": 600}}
    return await asyncio.to_thread(send_attack, "Stealth Tamper Plugin", payload, 204)

@redteam_attack(category="flood", weight=25)
async def poisson_flooder_plugin(shared_state: Dict[str, Any]):
    print("[Attack] Executing poisson_flooder_plugin (Token bombardment)...")
    try:
        from .live_attacker import send_attack
    except ImportError:
        return
    tasks = []
    for i in range(15):
        tasks.append(asyncio.to_thread(send_attack, f"Poisson Flood {i}", {"__raw__": True, "telemetry": {}}, 205))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

@redteam_attack(category="crypto", weight=35)
async def replay_attack_plugin(shared_state: Dict[str, Any]):
    print("[Attack] Executing replay_attack_plugin (HMAC Nonce reuse)...")
    try:
        from .live_attacker import get_challenge, send_attack
        import base64
        import json
    except ImportError:
        return
    ch = await asyncio.to_thread(get_challenge)
    if not ch: return
    await asyncio.sleep(1.6)
    envelope = {"challenge": ch, "telemetry": {}, "created_at": int(time.time() * 1000)}
    valid_token = base64.b64encode(json.dumps(envelope).encode()).decode()
    await asyncio.to_thread(send_attack, "Replay Attack (1st)", {"token": valid_token}, 206)
    return await asyncio.to_thread(send_attack, "Replay Attack Plugin (2nd)", {"token": valid_token}, 206)
