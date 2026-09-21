"""
Synapse Shield - Adversarial Synthetic Telemetry Generator
Generates mathematical, polynomial, and sinusoidal bot patterns for AI model hardening and adversarial training.
"""

import math
import random
from typing import Any


def generate_bezier_telemetry(
    start: tuple[float, float] = (100.0, 100.0),
    end: tuple[float, float] = (500.0, 400.0),
    steps: int = 45,
    duration_ms: float = 1200.0,
) -> dict[str, Any]:
    """Generates cubic Bézier mouse trajectory with smooth polynomial progression."""
    # Control points
    p0 = start
    p3 = end
    p1 = (start[0] + (end[0] - start[0]) * 0.3 + random.uniform(-20, 20), start[1] + (end[1] - start[1]) * 0.1)
    p2 = (start[0] + (end[0] - start[0]) * 0.7, start[1] + (end[1] - start[1]) * 0.9 + random.uniform(-20, 20))

    movements = []
    base_t = 1000.0
    dt = duration_ms / steps

    for i in range(steps):
        u = i / (steps - 1)
        # Bernstein polynomials
        b0 = (1 - u) ** 3
        b1 = 3 * (1 - u) ** 2 * u
        b2 = 3 * (1 - u) * u ** 2
        b3 = u ** 3

        x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
        y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
        t = base_t + i * dt
        movements.append({"x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})

    return {
        "mouse_movements": movements,
        "clicks": [{"x": end[0], "y": end[1], "t": base_t + duration_ms + 50.0}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
            "touch_supported": False,
        },
    }


def generate_sine_oscillator_telemetry(
    start: tuple[float, float] = (150.0, 200.0),
    end: tuple[float, float] = (600.0, 500.0),
    frequency_hz: float = 10.0,
    amplitude: float = 4.0,
    steps: int = 50,
    duration_ms: float = 1500.0,
) -> dict[str, Any]:
    """Generates synthetic mouse path with a pure sine-wave tremor oscillation."""
    movements = []
    base_t = 1000.0
    dt = duration_ms / steps

    dx = (end[0] - start[0]) / (steps - 1)
    dy = (end[1] - start[1]) / (steps - 1)

    # Perpendicular vector for tremor
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length

    for i in range(steps):
        t_sec = (i * dt) / 1000.0
        osc = amplitude * math.sin(2 * math.pi * frequency_hz * t_sec)

        x = start[0] + i * dx + nx * osc
        y = start[1] + i * dy + ny * osc
        t = base_t + i * dt
        movements.append({"x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})

    return {
        "mouse_movements": movements,
        "clicks": [{"x": end[0], "y": end[1], "t": base_t + duration_ms + 60.0}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
            "touch_supported": False,
        },
    }


def generate_minimum_jerk_telemetry(
    start: tuple[float, float] = (100.0, 100.0),
    end: tuple[float, float] = (700.0, 450.0),
    steps: int = 60,
    duration_ms: float = 1400.0,
) -> dict[str, Any]:
    """
    Generates Flash & Hogan (1985) Minimum Jerk biological trajectory.
    Formula: r(tau) = start + (end - start) * (10*tau^3 - 15*tau^4 + 6*tau^5)
    """
    movements = []
    base_t = 1000.0
    dt = duration_ms / steps

    for i in range(steps):
        tau = i / (steps - 1)
        poly = 10 * (tau ** 3) - 15 * (tau ** 4) + 6 * (tau ** 5)

        x = start[0] + (end[0] - start[0]) * poly
        y = start[1] + (end[1] - start[1]) * poly
        t = base_t + i * dt
        movements.append({"x": round(x, 2), "y": round(y, 2), "t": round(t, 2)})

    return {
        "mouse_movements": movements,
        "clicks": [{"x": end[0], "y": end[1], "t": base_t + duration_ms + 40.0}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {
            "webdriver": False,
            "screen_width": 1920,
            "screen_height": 1080,
            "plugins_length": 3,
            "touch_supported": False,
        },
    }


def generate_adversarial_telemetry_batch(count: int = 30) -> list[dict[str, Any]]:
    """Generates a diverse batch of adversarial synthetic bot telemetries."""
    batch = []
    generators = [
        generate_bezier_telemetry,
        generate_sine_oscillator_telemetry,
        generate_minimum_jerk_telemetry,
    ]

    for i in range(count):
        gen = random.choice(generators)
        sx = random.uniform(50, 300)
        sy = random.uniform(50, 300)
        ex = random.uniform(400, 800)
        ey = random.uniform(400, 800)
        steps = random.randint(35, 60)
        dur = random.uniform(1000.0, 1800.0)
        batch.append(gen(start=(sx, sy), end=(ex, ey), steps=steps, duration_ms=dur))

    return batch
