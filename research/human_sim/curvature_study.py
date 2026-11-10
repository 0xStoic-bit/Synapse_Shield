"""Eğrilik kuralının (curvature_score) gerçek insanlarda ve bilinen botlarda neye baktığını ölçer.

Gerçek insan: SapiMouse pencereleri, replay_sapimouse.py ile aynı biçimde (30 ms örnekleme, son tıklamada biter).
Bot: synapse_shield.adversarial üreticileri ve test/red-team dosyalarındaki tipik desenler.

Motorun mevcut hesabını birebir yeniden üretir; ayrıca hız eşiğinin (durma anlarını dışarıda bırakma) etkisini gösterir.
Kullanım: python research/human_sim/curvature_study.py
"""

from __future__ import annotations

import glob
import os
import random
import sys

os.environ.setdefault("REPLAY_WINDOW_MS", "6000")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))

import numpy as np  # noqa: E402

import replay_sapimouse as rp  # noqa: E402
from analyze_sapimouse import DATA, load_session  # noqa: E402
from synapse_shield import adversarial as adv  # noqa: E402


def curvature_parts(moves: list[dict], min_step_px: float = 0.0) -> dict | None:
    """features.py'deki hesabın aynısı; min_step_px > 0 ise κ yalnızca iki komşu adımı da en az bu kadar olan noktalarda alınır."""
    m = sorted(moves, key=lambda d: d["t"])[:300]
    if len(m) < 4:
        return None
    x = np.array([d["x"] for d in m], float)
    y = np.array([d["y"] for d in m], float)
    t = np.array([d["t"] for d in m], float)
    dt = np.maximum(np.diff(t), 0.1)
    dx, dy = np.diff(x), np.diff(y)
    vx, vy = dx / dt, dy / dt
    dta = (dt[1:] + dt[:-1]) * 0.5
    ax, ay = np.diff(vx) / np.maximum(dta, 0.1), np.diff(vy) / np.maximum(dta, 0.1)
    vs_x, vs_y = vx[1:], vy[1:]
    v2 = vs_x**2 + vs_y**2 + 1e-6
    k = np.abs(vs_x * ay - vs_y * ax) / (v2 * np.sqrt(v2))
    step = np.hypot(dx, dy)
    keep = np.ones(len(k), bool)
    if min_step_px > 0:
        keep = (step[1:] >= min_step_px) & (step[:-1] >= min_step_px)
    kk = k[keep]
    tk = (t[2:])[keep]
    if len(kk) < 3:
        return {"n": len(kk), "mean_k": 0.0, "var_k": 0.0, "var_dk": 0.0, "kept": float(keep.mean())}
    dk = np.diff(kk) / np.maximum(np.diff(tk), 0.1)
    return {"n": len(kk), "mean_k": float(kk.mean()), "var_k": float(kk.var()), "var_dk": float(dk.var()),
            "kept": float(keep.mean()), "frac_k_gt_01": float((kk > 0.1).mean())}


def score(p: dict) -> float:
    if p["mean_k"] < 1e-6 and p["var_k"] < 1e-7:
        return 0.95
    if p["var_dk"] < 1e-8 and p["var_k"] < 1e-4:
        return 0.90
    if p["var_dk"] > 5.0 or p["var_k"] > 10.0:
        return 0.85
    if p.get("frac_k_gt_01", 0) > 0.5 and p["var_dk"] > 2.0:
        return 0.75
    return 0.10


def humans() -> list[list[dict]]:
    rng = np.random.default_rng(0)
    out = []
    for u in sorted(glob.glob(os.path.join(DATA, "user*"))):
        for s in sorted(glob.glob(os.path.join(u, "*.csv"))):
            for win in rp.windows(load_session(s)):
                tel = rp.to_telemetry(win, rng)
                if tel:
                    out.append(tel["mouse_movements"])
    return out


def jitter_bot(rnd: random.Random) -> list[dict]:
    """Doğrusal yol + noktadan bağımsız düzgün gürültü (Rust'taki bilinen-açık testinin deseni)."""
    amp = rnd.uniform(1, 6)
    step = rnd.uniform(2, 12)
    dt = rnd.choice([8, 16, 30])
    return [{"x": 100 + i * step + rnd.uniform(-amp, amp), "y": 300 + rnd.uniform(-amp, amp), "t": 1000 + i * dt}
            for i in range(80)]


def bots() -> dict[str, list[list[dict]]]:
    random.seed(1)
    rnd = random.Random(2)
    out: dict[str, list[list[dict]]] = {}
    gens = {
        "bezier": adv.generate_bezier_telemetry,
        "linear": adv.generate_linear_telemetry,
        "sine_osc": adv.generate_sine_oscillator_telemetry,
        "min_jerk": adv.generate_minimum_jerk_telemetry,
    }
    for name, g in gens.items():
        out[name] = []
        for _ in range(200):
            s = (rnd.uniform(50, 300), rnd.uniform(50, 300))
            e = (rnd.uniform(400, 900), rnd.uniform(400, 800))
            out[name].append(g(start=s, end=e, steps=rnd.randint(35, 65), duration_ms=rnd.uniform(800, 1800))["mouse_movements"])
    out["jitter"] = [jitter_bot(rnd) for _ in range(400)]
    return out


def summarize(label: str, rows: list[dict]) -> None:
    rows = [r for r in rows if r]
    sc = np.array([score(r) for r in rows])
    vk = np.array([r["var_k"] for r in rows])
    vdk = np.array([r["var_dk"] for r in rows])
    print(f"{label:22s} n={len(rows):5d}  ≥0.75: {100 * (sc >= 0.75).mean():5.1f}%  "
          f"0.95:{100 * (sc == 0.95).mean():5.1f}% 0.90:{100 * (sc == 0.90).mean():5.1f}% "
          f"0.85:{100 * (sc == 0.85).mean():5.1f}% 0.75:{100 * (sc == 0.75).mean():5.1f}%  "
          f"var_k p50={np.median(vk):.3g} p95={np.percentile(vk, 95):.3g}  var_dk p50={np.median(vdk):.3g} p95={np.percentile(vdk, 95):.3g}")


def score_combined(moves: list[dict], gate: float, min_pts: int) -> float:
    """Önerilen kural: düzgünlük dalları (0.95/0.90) tüm noktalarda VEYA hız eşikli noktalarda;
    kaos dalları (0.85/0.75) yalnızca hız eşikli noktalarda ve en az min_pts nokta kaldıysa."""
    a = curvature_parts(moves, 0.0)
    g = curvature_parts(moves, gate)
    if not a:
        return 0.0
    for p in (a, g if g and g["n"] >= min_pts else None):
        if p is None:
            continue
        if p["mean_k"] < 1e-6 and p["var_k"] < 1e-7:
            return 0.95
    for p in (a, g if g and g["n"] >= min_pts else None):
        if p is None:
            continue
        if p["var_dk"] < 1e-8 and p["var_k"] < 1e-4:
            return 0.90
    if g and g["n"] >= min_pts:
        if g["var_dk"] > 5.0 or g["var_k"] > 10.0:
            return 0.85
        if g.get("frac_k_gt_01", 0) > 0.5 and g["var_dk"] > 2.0:
            return 0.75
    return 0.10


def main() -> None:
    H = humans()
    B = bots()
    for gate in (0.0, 2.0, 3.0, 5.0):
        print(f"\n=== κ yalnızca komşu adımlar ≥ {gate:g} px olan noktalarda (0 = mevcut motor) ===")
        summarize("İNSAN (SapiMouse 6 sn)", [curvature_parts(h, gate) for h in H])
        for name, lst in B.items():
            summarize(f"bot:{name}", [curvature_parts(b, gate) for b in lst])
    print("\n=== Önerilen birleşik kural: skor ≥ 0.75 oranı ===")
    for gate in (3.0, 4.0, 5.0, 6.0):
        for min_pts in (5, 10):
            hs = np.array([score_combined(h, gate, min_pts) for h in H])
            line = f"eşik={gate:g}px min_nokta={min_pts:2d}  İNSAN {100 * (hs >= 0.75).mean():5.2f}%"
            for name, lst in B.items():
                bs = np.array([score_combined(b, gate, min_pts) for b in lst])
                line += f" | {name} {100 * (bs >= 0.75).mean():5.1f}%"
            print(line)


if __name__ == "__main__":
    main()
