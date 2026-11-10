"""Bilinen bot desenlerinin tam motor kararında (analyze_behavior) ne oranda "Bot" sayıldığını ölçer (TPR).

Eşik/kural değişikliğinden önce ve sonra çalıştırılıp karşılaştırılır.
Kullanım: python research/human_sim/bot_tpr.py
"""

from __future__ import annotations

import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))

from curvature_study import bots  # noqa: E402
from synapse_shield.engine import analyze_behavior  # noqa: E402

BROWSER = {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
           "touch_supported": False}


def main() -> None:
    for integer in (False, True):
        print(f"--- bot koordinatları: {'tam sayı px (tarayıcı gibi)' if integer else '0,01 px (üretici)'} ---")
        random.seed(5)
        total_b = total_n = 0
        for name, lst in bots(integer=integer).items():
            b = 0
            for moves in lst:
                last = moves[-1]
                tel = {"mouse_movements": moves, "clicks": [{"x": last["x"], "y": last["y"], "t": last["t"] + 80}],
                       "keystrokes": [], "scrolls": [], "browser": dict(BROWSER)}
                _, decision, _, _ = analyze_behavior(tel)
                b += decision == "Bot"
            total_b += b
            total_n += len(lst)
            print(f"{name:10s} n={len(lst):4d}  Bot: {100 * b / len(lst):5.1f}%")
        print(f"{'toplam':10s} n={total_n:4d}  Bot: {100 * total_b / total_n:5.1f}%")


if __name__ == "__main__":
    main()
