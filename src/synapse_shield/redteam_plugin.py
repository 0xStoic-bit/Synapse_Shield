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
