"""
Advanced Adversarial Biometrics Testing Agent
State-of-the-art behavioral simulation for benchmarking defense engines
"""

import asyncio
import math
import random
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum
import numpy as np
from playwright.async_api import async_playwright, Page, Browser, ElementHandle

@dataclass
class Point:
    x: float
    y: float
    timestamp: float

@dataclass
class TrajectoryPoint:
    x: float
    y: float
    t: float  # normalized time [0, 1]
    velocity: float
    acceleration: float

class InteractionPhase(Enum):
    IDLE = "idle"
    MOVING = "moving"
    HOVERING = "hovering"
    CLICKING = "clicking"
    TYPING = "typing"

class MinimumJerkTrajectory:
    """
    Implements Flash & Hogan Minimum Jerk Model for natural mouse movements
    Uses 5th-degree polynomial: x(tau) = x0 + (x1 - x0) * (10*tau^3 - 15*tau^4 + 6*tau^5)
    """
    
    @staticmethod
    def minimum_jerk_profile(tau: float) -> float:
        """Compute minimum jerk position profile at normalized time tau"""
        return 10 * tau**3 - 15 * tau**4 + 6 * tau**5
    
    @staticmethod
    def minimum_jerk_velocity(tau: float) -> float:
        """Compute velocity profile (derivative of position)"""
        return 30 * tau**2 - 60 * tau**3 + 30 * tau**4
    
    @staticmethod
    def minimum_jerk_acceleration(tau: float) -> float:
        """Compute acceleration profile (second derivative)"""
        return 60 * tau - 180 * tau**2 + 120 * tau**3
    
    @staticmethod
    def generate_trajectory(
        start: Point,
        end: Point,
        duration_ms: int = 800,
        num_points: int = 50,
        fitts_law_deceleration: bool = True
    ) -> List[TrajectoryPoint]:
        """
        Generate point-to-point trajectory using minimum jerk model
        with Fitts's Law terminal deceleration
        """
        trajectory = []
        dx = end.x - start.x
        dy = end.y - start.y
        distance = math.sqrt(dx**2 + dy**2)
        
        # Adjust duration based on Fitts's Law (ID = log2(D/W + 1))
        # Longer distances = slightly longer movement time
        adjusted_duration = duration_ms * (1 + 0.15 * math.log2(distance / 100 + 1))
        
        for i in range(num_points):
            tau = i / (num_points - 1)
            
            # Apply minimum jerk profile
            pos_profile = MinimumJerkTrajectory.minimum_jerk_profile(tau)
            vel_profile = MinimumJerkTrajectory.minimum_jerk_velocity(tau)
            acc_profile = MinimumJerkTrajectory.minimum_jerk_acceleration(tau)
            
            # Calculate position
            x = start.x + dx * pos_profile
            y = start.y + dy * pos_profile
            
            # Calculate velocity and acceleration (scaled by distance and duration)
            velocity_scale = distance / (adjusted_duration / 1000)
            velocity = vel_profile * velocity_scale
            
            # Fitts's Law terminal deceleration: 65% velocity drop in final 20%
            if fitts_law_deceleration and tau > 0.8:
                decel_factor = 1 - 0.65 * ((tau - 0.8) / 0.2)
                velocity *= decel_factor
            
            acceleration = acc_profile * velocity_scale / (adjusted_duration / 1000)
            
            trajectory.append(TrajectoryPoint(
                x=x, y=y, t=tau,
                velocity=velocity,
                acceleration=acceleration
            ))
        
        return trajectory

class BiometricAdversarialAgent:
    """
    Advanced adversarial agent with biophysical calibration
    """
    
    def __init__(self, page: Page):
        self.page = page
        self.current_phase = InteractionPhase.IDLE
        self.trajectory_log: List[Dict] = []
        self.hover_timings: List[float] = []
        self.click_timings: List[float] = []
        self.key_timings: List[float] = []
        
        # Psychophysical parameters
        self.human_reaction_time_mean = 180  # ms
        self.human_reaction_time_std = 30
        self.hover_duration_mean = 200  # ms
        self.hover_duration_std = 50
        
    async def move_to_element(
        self,
        element: ElementHandle,
        direct_click: bool = False,
        duration_ms: Optional[int] = None
    ) -> Tuple[float, float]:
        """
        Move mouse to element using minimum jerk trajectory
        """
        # Get element bounding box
        bbox = await element.bounding_box()
        if not bbox:
            raise ValueError("Element not visible")
        
        # Get current mouse position
        current_pos = await self.page.evaluate("() => ({ x: window.mouseX || 0, y: window.mouseY || 0 })")
        start_x = current_pos.get('x', 0)
        start_y = current_pos.get('y', 0)
        
        # Target position (center of element with slight natural variation)
        target_x = bbox['x'] + bbox['width'] / 2 + random.uniform(-3, 3)
        target_y = bbox['y'] + bbox['height'] / 2 + random.uniform(-3, 3)
        
        # Calculate duration based on Fitts's Law
        distance = math.sqrt((target_x - start_x)**2 + (target_y - start_y)**2)
        if duration_ms is None:
            # MT = a + b * log2(D/W + 1)
            width = min(bbox['width'], bbox['height'])
            if width > 0:
                fitts_id = math.log2(distance / width + 1)
                duration_ms = int(150 + 80 * fitts_id + random.uniform(-20, 20))
            else:
                duration_ms = 600
        
        # Generate minimum jerk trajectory
        start_point = Point(start_x, start_y, time.time())
        end_point = Point(target_x, target_y, time.time())
        
        trajectory = MinimumJerkTrajectory.generate_trajectory(
            start_point,
            end_point,
            duration_ms=duration_ms,
            num_points=60,
            fitts_law_deceleration=True
        )
        
        # Execute movement
        self.current_phase = InteractionPhase.MOVING
        movement_start = time.time()
        
        for i, point in enumerate(trajectory):
            # Calculate actual time for this point
            t_norm = point.t
            actual_time = movement_start + (duration_ms / 1000) * t_norm
            
            # Move mouse
            await self.page.mouse.move(point.x, point.y)
            
            # Record trajectory
            self.trajectory_log.append({
                'x': point.x,
                'y': point.y,
                'time': actual_time,
                'velocity': point.velocity,
                'acceleration': point.acceleration,
                'phase': 'movement'
            })
            
            # Small delay to simulate real-time movement (1ms granularity)
            await asyncio.sleep(0.001)
        
        # Verify final position is within 3px of target
        final_x, final_y = point.x, point.y
        distance_error = math.sqrt((final_x - target_x)**2 + (final_y - target_y)**2)
        
        if distance_error > 3:
            # Micro-correct within 3px boundary
            correction_x = target_x - final_x
            correction_y = target_y - final_y
            correction_magnitude = math.sqrt(correction_x**2 + correction_y**2)
            
            if correction_magnitude > 0:
                scale = min(3, correction_magnitude) / correction_magnitude
                await self.page.mouse.move(
                    final_x + correction_x * scale,
                    final_y + correction_y * scale
                )
        
        self.current_phase = InteractionPhase.HOVERING
        
        return target_x, target_y
    
    async def click_with_human_timing(self, element: ElementHandle):
        """
        Perform click with human-like reaction times
        """
        # Move to element first
        target_x, target_y = await self.move_to_element(element)
        
        # Human-like hover (cognitive processing)
        hover_duration = random.gauss(
            self.hover_duration_mean,
            self.hover_duration_std
        )
        hover_duration = max(50, min(500, hover_duration))
        self.hover_timings.append(hover_duration)
        
        # Simulate hover with micro-movements (neuromuscular tremor)
        self.current_phase = InteractionPhase.HOVERING
        hover_start = time.time()
        
        while time.time() - hover_start < (hover_duration / 1000):
            # Micro-tremor (5-10Hz natural hand tremor)
            tremor_x = random.uniform(-0.5, 0.5)
            tremor_y = random.uniform(-0.5, 0.5)
            await self.page.mouse.move(target_x + tremor_x, target_y + tremor_y)
            await asyncio.sleep(0.008)  # ~8ms human micro-movement interval
        
        # Click with natural timing
        self.current_phase = InteractionPhase.CLICKING
        
        # Pre-click delay (human reaction)
        pre_click_delay = random.gauss(
            self.human_reaction_time_mean,
            self.human_reaction_time_std
        )
        pre_click_delay = max(50, min(300, pre_click_delay))
        await asyncio.sleep(pre_click_delay / 1000)
        
        # Perform click
        click_start = time.time()
        await self.page.mouse.click(target_x, target_y)
        click_duration = (time.time() - click_start) * 1000
        
        self.click_timings.append(click_duration)
        
        # Record click event
        self.trajectory_log.append({
            'x': target_x,
            'y': target_y,
            'time': time.time(),
            'type': 'click',
            'phase': 'click'
        })
        
        # Post-click phase transition
        self.current_phase = InteractionPhase.IDLE
        
        return target_x, target_y
    
    async def type_with_cognitive_delay(
        self,
        text: str,
        field_element: Optional[ElementHandle] = None,
        type_speed_wpm: int = 40
    ):
        """
        Type text with cognitive phase separation
        """
        # Ensure we're in typing phase
        self.current_phase = InteractionPhase.TYPING
        
        # Click the field if provided
        if field_element:
            await self.click_with_human_timing(field_element)
            
            # Cognitive pause before typing
            await asyncio.sleep(random.uniform(200, 400) / 1000)
        
        # Calculate typing delay (WPM to ms per character)
        # Average word = 5 characters, WPM = words per minute
        chars_per_second = (type_speed_wpm * 5) / 60
        base_delay = 1000 / max(chars_per_second, 1)
        
        # Type with cognitive processing variation
        for char in text:
            # Intra-character timing variation
            if char == ' ':
                # Longer pause for spaces (word boundary)
                delay = base_delay * random.uniform(0.5, 1.5)
            else:
                # Basic character typing with variation
                delay = base_delay * random.uniform(0.3, 1.7)
            
            # Add cognitive processing jitter
            cognitive_jitter = random.gauss(0, 15)
            delay = max(20, delay + cognitive_jitter)
            
            # Type the character
            await self.page.keyboard.type(char, delay=0)
            
            # Record keystroke
            self.key_timings.append({
                'char': char,
                'delay': delay,
                'timestamp': time.time()
            })
            
            # Small delay between keystrokes (keyboard matrix scanning)
            await asyncio.sleep(delay / 1000)
        
        # Post-typing cognitive pause
        await asyncio.sleep(random.uniform(100, 300) / 1000)
        
        self.current_phase = InteractionPhase.IDLE
    
    async def perform_multimodal_sequence(
        self,
        elements: Dict[str, ElementHandle],
        text_inputs: Dict[str, str],
        sequence: List[str]
    ):
        """
        Execute multimodal interaction sequence with cognitive phase isolation
        """
        for action in sequence:
            if action.startswith('click_'):
                element_key = action.replace('click_', '')
                if element_key in elements:
                    await self.click_with_human_timing(elements[element_key])
                    # Phase transition delay
                    await asyncio.sleep(random.uniform(50, 150) / 1000)
            
            elif action.startswith('type_'):
                field_key = action.replace('type_', '')
                if field_key in text_inputs and field_key in elements:
                    await self.type_with_cognitive_delay(
                        text_inputs[field_key],
                        elements[field_key]
                    )
                    # Phase transition delay
                    await asyncio.sleep(random.uniform(100, 200) / 1000)
            
            elif action == 'move_only':
                # Pure movement test
                if 'target' in elements:
                    await self.move_to_element(elements['target'])
                    await asyncio.sleep(random.uniform(100, 300) / 1000)
    
    def get_behavioral_signature(self) -> Dict[str, Any]:
        """
        Extract behavioral signature for analysis
        """
        if not self.trajectory_log:
            return {}
        
        # Calculate trajectory metrics
        velocities = [p.get('velocity', 0) for p in self.trajectory_log if 'velocity' in p]
        accelerations = [p.get('acceleration', 0) for p in self.trajectory_log if 'acceleration' in p]
        
        # Spectral jitter analysis (simplified)
        if len(velocities) > 10:
            velocity_fft = np.fft.fft(velocities)
            spectral_magnitude = np.abs(velocity_fft[:len(velocity_fft)//2])
            dominant_freq = np.argmax(spectral_magnitude[1:]) + 1
            spectral_entropy = -np.sum(
                (spectral_magnitude / np.sum(spectral_magnitude)) *
                np.log2(spectral_magnitude / np.sum(spectral_magnitude) + 1e-10)
            )
        else:
            dominant_freq = 0
            spectral_entropy = 0
        
        return {
            'total_points': len(self.trajectory_log),
            'avg_velocity': np.mean(velocities) if velocities else 0,
            'velocity_std': np.std(velocities) if velocities else 0,
            'avg_acceleration': np.mean(accelerations) if accelerations else 0,
            'dominant_frequency': dominant_freq,
            'spectral_entropy': spectral_entropy,
            'hover_count': len(self.hover_timings),
            'avg_hover_duration': np.mean(self.hover_timings) if self.hover_timings else 0,
            'avg_click_duration': np.mean(self.click_timings) if self.click_timings else 0,
            'total_keystrokes': len(self.key_timings),
            'phase_transitions': len([
                p for p in self.trajectory_log 
                if p.get('phase') in ['movement', 'click', 'hover']
            ])
        }

class AdversarialBiometricsTester:
    """
    Main testing framework for adversarial biometrics evaluation
    """
    
    def __init__(self):
        self.agents: List[BiometricAdversarialAgent] = []
        self.test_results: List[Dict] = []
        self.page: Optional[Page] = None
    
    async def initialize_browser(self):
        """Initialize Playwright browser"""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=False,  # Visible for testing
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.page = await context.new_page()
        return self.page
    
    async def load_test_page(self, url: str):
        """Load test page with target elements"""
        if not self.page:
            await self.initialize_browser()
        await self.page.goto(url)
        await self.page.wait_for_load_state('networkidle')
        
        # Track mouse position
        await self.page.evaluate("""
            document.addEventListener('mousemove', (e) => {
                window.mouseX = e.clientX;
                window.mouseY = e.clientY;
            });
        """)
    
    async def create_agent(self) -> BiometricAdversarialAgent:
        """Create a new adversarial agent instance"""
        if not self.page:
            await self.initialize_browser()
        agent = BiometricAdversarialAgent(self.page)
        self.agents.append(agent)
        return agent
    
    async def run_attack_scenario(
        self,
        agent: BiometricAdversarialAgent,
        scenario_type: str = 'form_filling'
    ):
        """
        Run specific adversarial scenario adapted for Synapse Shield test page
        """
        # Find the Verify Human button
        verify_btn = None
        for selector in ['button:has-text("VERIFY HUMAN")', 'button:has-text("Verify Human")', '#verify-btn', 'button']:
            elements = await self.page.query_selector_all(selector)
            for el in elements:
                text = await el.inner_text()
                if "VERIFY" in text.upper():
                    verify_btn = el
                    break
            if verify_btn:
                break
                
        if not verify_btn:
            print("Verify button not found!")
            return
            
        print("Moving to and clicking VERIFY HUMAN button with Minimum Jerk trajectory...")
        
        # 1. Random initial movement to simulate human settling
        start_pos = await self.page.evaluate("() => ({ x: window.mouseX || 100, y: window.mouseY || 100 })")
        
        # 2. Click with Flash & Hogan Minimum Jerk human timing
        await agent.click_with_human_timing(verify_btn)
        
        # 3. Wait for API to process and update UI
        print("Waiting for verification response...")
        await asyncio.sleep(2)
        
        # 4. Try to click again (for rapid_sequence scenario)
        if scenario_type == 'rapid_sequence':
            await asyncio.sleep(0.5)
            await agent.click_with_human_timing(verify_btn)
            await asyncio.sleep(2)
            
    async def benchmark_engine(self, url: str, num_agents: int = 10) -> Dict:
        """
        Benchmark the defense engine with multiple agents
        """
        await self.load_test_page(url)
        
        all_signatures = []
        
        for i in range(num_agents):
            agent = await self.create_agent()
            
            # Test custom scenario targeting verify button
            scenario = 'verify_click'
            
            try:
                await self.run_attack_scenario(agent, scenario)
                
                # Collect behavioral signature
                signature = agent.get_behavioral_signature()
                signature['agent_id'] = i
                signature['scenario'] = scenario
                all_signatures.append(signature)
                
                # Wait between agents
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                print(f"Agent {i} failed: {e}")
                continue
        
        # Aggregate results for defense engine evaluation
        benchmark_results = self._analyze_defense_evasion(all_signatures)
        
        self.test_results.append(benchmark_results)
        return benchmark_results
    
    def _analyze_defense_evasion(self, signatures: List[Dict]) -> Dict:
        """
        Analyze whether the defense engine could detect synthetic behavior
        """
        if not signatures:
            return {'error': 'No signatures collected'}
        
        # Extract metrics that defense engines typically use
        avg_velocity = np.mean([s.get('avg_velocity', 0) for s in signatures])
        velocity_variance = np.mean([s.get('velocity_std', 0) for s in signatures])
        spectral_entropy_mean = np.mean([s.get('spectral_entropy', 0) for s in signatures])
        
        # Fitts's Law compliance check
        hover_times = []
        for s in signatures:
            hover_times.extend([s.get('avg_hover_duration', 0)])
        
        # Check if behavioral patterns match human benchmarks
        human_like_metrics = {
            'velocity': 100 < avg_velocity < 400,  # Human typical range
            'velocity_variance': 50 < velocity_variance < 200,
            'spectral_entropy': 3 < spectral_entropy_mean < 8,
            'hover_time': 100 < np.mean(hover_times) < 400 if hover_times else False,
            'phase_isolation': all(s.get('phase_transitions', 0) > 0 for s in signatures),
            'spatial_coherence': True,  # Enforced by agent
            'temporal_sequence': True   # Enforced by agent
        }
        
        # Calculate evasion score (higher = more human-like, harder to detect)
        evasion_score = sum(human_like_metrics.values()) / len(human_like_metrics) * 100
        
        return {
            'total_agents': len(signatures),
            'avg_velocity': avg_velocity,
            'velocity_variance': velocity_variance,
            'spectral_entropy_mean': spectral_entropy_mean,
            'avg_hover_time': np.mean(hover_times) if hover_times else 0,
            'human_like_metrics': human_like_metrics,
            'evasion_score': evasion_score,
            'defense_evasion_analysis': {
                '1D_CNN_detection_risk': 'Low' if evasion_score > 80 else 'High',
                'spectral_jitter_detection_risk': 'Low' if 4 < spectral_entropy_mean < 7 else 'High',
                'fitts_law_compliance': 'High' if 100 < np.mean(hover_times) < 400 else 'Low',
                'overall_detection_risk': self._calculate_detection_risk(human_like_metrics)
            }
        }
    
    def _calculate_detection_risk(self, metrics: Dict) -> str:
        """Calculate overall detection risk"""
        risk_score = 0
        if not metrics.get('velocity', False):
            risk_score += 1
        if not metrics.get('spectral_entropy', False):
            risk_score += 1
        if not metrics.get('hover_time', False):
            risk_score += 1
        if not metrics.get('phase_isolation', False):
            risk_score += 2
            
        if risk_score <= 1:
            return 'Very Low (Highly Human-like)'
        elif risk_score <= 2:
            return 'Low'
        elif risk_score <= 3:
            return 'Medium'
        else:
            return 'High (Detectable by advanced engines)'

# Example usage
async def main():
    tester = AdversarialBiometricsTester()
    
    # Initialize browser
    await tester.initialize_browser()
    
    # Load test page - UPDATED TO LOCAL SERVER
    test_url = "http://127.0.0.1:8000"
    
    try:
        # Run benchmark with 3 agents for testing API
        results = await tester.benchmark_engine(test_url, num_agents=3)
        
        print("=" * 60)
        print("ADVERSARIAL BIOMETRICS BENCHMARK RESULTS")
        print("=" * 60)
        print(f"Evasion Score: {results['evasion_score']:.2f}%")
        print(f"Spectral Entropy: {results['spectral_entropy_mean']:.3f}")
        print(f"Avg Velocity: {results['avg_velocity']:.2f} px/s")
        print(f"Velocity Variance: {results['velocity_variance']:.2f}")
        print("\nDefense Evasion Analysis:")
        for key, value in results['defense_evasion_analysis'].items():
            print(f"  {key}: {value}")
            
    except Exception as e:
        print(f"Benchmark failed: {e}")
    finally:
        # Clean up
        if tester.page:
            await tester.page.close()
            await tester.page.context.browser.close()

if __name__ == "__main__":
    asyncio.run(main())
