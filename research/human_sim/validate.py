"""Simülatörün ürettiği fare hareketlerini, SapiMouse'u ölçen AYNI fonksiyonla ölçüp gerçek insanla karşılaştırır.

Motorla ilgisi yoktur: simülatör gerçek insan dağılımlarına ne kadar benziyor, onu gösterir.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_sapimouse import movement_metrics  # noqa: E402
import simulator as sim  # noqa: E402

KEYS = ["dur", "straightness", "max_lat_ratio", "tpeak_frac", "submovements", "pauses_100ms", "homing_frac"]


def run(n_people: int = 200, per_person: int = 40, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    real = sim.MOUSE["pooled"]
    out = {k: [] for k in KEYS}
    for i in range(n_people):
        p = sim.sample_person(rng, i)
        # SapiMouse: 18-53 yaş, fare ya da touchpad. Karşılaştırma aynı nüfusla yapılır.
        if p.device == "mobile" or p.age == "older":
            continue
        for _ in range(per_person):
            D = sim.qsample(rng, real["dist"], 45.0, 1600.0)
            ang = rng.uniform(0, 2 * np.pi)
            p0 = (800.0, 500.0)
            p1 = (800.0 + D * np.cos(ang), 500.0 + D * np.sin(ang))
            ev, t_end = sim.aimed_movement(rng, p, p0, p1, 0.0)
            if len(ev) < 6:
                continue
            # SapiMouse'ta hareket tıklama basışıyla biter: hedef üstünde bekleme süresi ölçüme dahildir.
            t_click = t_end + rng.uniform(*sim.PRECLICK_DWELL)
            ev = ev + sim.hover(rng, p, ev[-1][1:], t_end, t_click) + [(t_click, ev[-1][1], ev[-1][2])]
            m = movement_metrics(np.array(ev, dtype=float))
            if m:
                for k in KEYS:
                    out[k].append(m[k])
    rows = {}
    for k in KEYS:
        a = np.array(out[k])
        r = real[k]
        rows[k] = (r["p5"], r["median"], r["p95"], float(np.percentile(a, 5)), float(np.median(a)), float(np.percentile(a, 95)))
    return rows


if __name__ == "__main__":
    rows = run()
    print(f"{'ölçü':14s} | {'gerçek p5':>9s} {'medyan':>8s} {'p95':>8s} | {'sim p5':>8s} {'medyan':>8s} {'p95':>8s}")
    for k, (a, b, c, d, e, f) in rows.items():
        print(f"{k:14s} | {a:9.3f} {b:8.3f} {c:8.3f} | {d:8.3f} {e:8.3f} {f:8.3f}")
