"""SapiMouse'tan insan fare hareketinin istatistiklerini çıkarır (simülatör parametreleri için).

Synapse motorunun eşiklerine bakmaz; yalnızca gerçek insan verisini ölçer.
Girdi: data/external/sapimouse/sapimouse/userN/session_*.csv  (client timestamp, button, state, x, y)
Çıktı: research/human_sim/params/sapimouse_stats.json  (yalnızca özet istatistik, ham veri yok)

Hareket tanımı: dinlenmeden (>= REST_MS boşluk ya da önceki tıklamanın bırakılması) sonra başlayıp
bir sol tık basışında biten "Move" olayları dizisi. Hedefe yönelik (aimed) hareketlerdir.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "..", "..", "data", "external", "sapimouse", "sapimouse")
OUT = os.path.join(ROOT, "params", "sapimouse_stats.json")

REST_MS = 300.0  # bu kadar hareketsizlik yeni bir hareketin başladığı sayılır
MIN_DIST = 40.0  # px; daha kısa olanlar hedefe yönelik hareket sayılmaz
MIN_POINTS = 6


def load_session(path: str) -> list[tuple[float, str, str, float, float]]:
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f)
        next(r, None)
        for t, button, state, x, y in r:
            try:
                rows.append((float(t), button, state, float(x), float(y)))
            except ValueError:
                continue
    return rows


def segment(rows):
    """Tıklamayla biten hedefe yönelik hareketleri ve tıklama basılı tutma sürelerini çıkarır."""
    moves, clicks, rests = [], [], []
    cur: list[tuple[float, float, float]] = []
    last_t = None
    press_t = None
    last_release = None
    for t, button, state, x, y in rows:
        if state == "Move":
            if last_t is not None and t - last_t > REST_MS and cur:
                cur = []
            if not cur and last_release is not None:
                rests.append(t - last_release)
                last_release = None
            cur.append((t, x, y))
            last_t = t
        elif state == "Pressed" and button == "Left":
            if len(cur) >= MIN_POINTS:
                cur.append((t, x, y))
                moves.append(np.array(cur))
            cur = []
            press_t = t
            last_t = t
        elif state == "Released" and button == "Left":
            if press_t is not None:
                clicks.append(t - press_t)
            press_t = None
            last_release = t
            last_t = t
            cur = []
        elif state == "Drag":
            cur = []
            last_t = t
    return moves, clicks, rests


def smooth(v: np.ndarray, k: int = 3) -> np.ndarray:
    if len(v) < k:
        return v
    return np.convolve(v, np.ones(k) / k, mode="same")


def movement_metrics(m: np.ndarray) -> dict | None:
    t, x, y = m[:, 0], m[:, 1], m[:, 2]
    dist = float(np.hypot(x[-1] - x[0], y[-1] - y[0]))
    dur = float(t[-1] - t[0])
    if dist < MIN_DIST or dur <= 50 or dur > 6000:
        return None
    seg = np.hypot(np.diff(x), np.diff(y))
    dt = np.diff(t)
    path = float(seg.sum())
    if path <= 0:
        return None
    ok = dt > 0
    v = np.zeros_like(dt)
    v[ok] = seg[ok] / dt[ok] * 1000.0  # px/s
    vs = smooth(v, 3)
    i_peak = int(np.argmax(vs))
    t_mid = (t[:-1] + t[1:]) / 2.0
    tp = float((t_mid[i_peak] - t[0]) / dur)
    vmax = float(vs[i_peak])
    # Alt-hareketler: tepe hızın %15'inden büyük belirginlikte yerel maksimumlar.
    peaks = 0
    for i in range(1, len(vs) - 1):
        if vs[i] >= vs[i - 1] and vs[i] > vs[i + 1] and vs[i] > 0.15 * vmax:
            left = vs[: i + 1].min() if i > 0 else 0.0
            right = vs[i:].min()
            if vs[i] - max(left, right) > 0.15 * vmax or peaks == 0:
                peaks += 1
    # Düz çizgiden en büyük yanal sapma (mesafeye oranla) ve yay yönü.
    ux, uy = (x[-1] - x[0]) / dist, (y[-1] - y[0]) / dist
    lat = (x - x[0]) * (-uy) + (y - y[0]) * ux
    i_lat = int(np.argmax(np.abs(lat)))
    # Son %10 mesafede geçen süre oranı (hedefe yerleşme / homing evresi).
    prog = (x - x[0]) * ux + (y - y[0]) * uy
    j = int(np.argmax(prog >= 0.9 * dist))
    homing = float((t[-1] - t[j]) / dur) if j > 0 else 0.0
    return {
        "dist": dist,
        "dur": dur,
        "straightness": dist / path,
        "max_lat_ratio": float(abs(lat[i_lat]) / dist),
        "lat_sign": float(np.sign(lat[i_lat])),
        "vmax": vmax,
        "tpeak_frac": tp,
        "submovements": max(1, peaks),
        "pauses_100ms": int((dt > 100).sum()),
        "homing_frac": homing,
        "dt_median": float(np.median(dt)),
    }


def describe(a) -> dict:
    a = np.asarray(a, dtype=float)
    if a.size == 0:
        return {}
    q = np.percentile(a, [5, 25, 50, 75, 95])
    return {"n": int(a.size), "mean": float(a.mean()), "sd": float(a.std()), "p5": float(q[0]), "p25": float(q[1]),
            "median": float(q[2]), "p75": float(q[3]), "p95": float(q[4])}


def main() -> None:
    users = sorted(glob.glob(os.path.join(DATA, "user*")))
    if not users:
        sys.exit("SapiMouse bulunamadı: " + DATA)
    all_m, per_user, clicks_all, rests_all, dts = [], [], [], [], []
    for u in users:
        um = []
        for s in glob.glob(os.path.join(u, "*.csv")):
            rows = load_session(s)
            ts = np.array([r[0] for r in rows if r[2] == "Move"])
            if ts.size > 2:
                d = np.diff(ts)
                dts.extend(d[(d > 0) & (d < 100)].tolist())
            moves, clicks, rests = segment(rows)
            clicks_all.extend([c for c in clicks if 0 < c < 1000])
            rests_all.extend([r for r in rests if 0 < r < 10000])
            for m in moves:
                mm = movement_metrics(m)
                if mm:
                    um.append(mm)
        if len(um) < 5:
            continue
        all_m.extend(um)
        # Kişi başına: tipik değerler ve süre ~ mesafe güç yasası (T = c * D^p).
        D = np.array([m["dist"] for m in um])
        T = np.array([m["dur"] for m in um])
        p, logc = np.polyfit(np.log(D), np.log(T), 1)
        per_user.append({
            "n": len(um),
            "straightness_median": float(np.median([m["straightness"] for m in um])),
            "max_lat_ratio_median": float(np.median([m["max_lat_ratio"] for m in um])),
            "tpeak_frac_median": float(np.median([m["tpeak_frac"] for m in um])),
            "submovements_mean": float(np.mean([m["submovements"] for m in um])),
            "homing_frac_median": float(np.median([m["homing_frac"] for m in um])),
            "dur_power_p": float(p),
            "dur_power_c": float(np.exp(logc)),
            "dur_residual_sd_log": float(np.std(np.log(T) - (logc + p * np.log(D)))),
            "vmax_median": float(np.median([m["vmax"] for m in um])),
            # Kişinin orta mesafedeki (250-700 px) tipik hareket süresi: hız ile mesafe duyarlılığını ayırır.
            "dur_at_400": float(np.median(T[(D >= 250) & (D <= 700)])) if ((D >= 250) & (D <= 700)).sum() >= 3 else float(np.exp(logc) * 400 ** p),
        })

    keys = ["dist", "dur", "straightness", "max_lat_ratio", "vmax", "tpeak_frac", "submovements", "pauses_100ms",
            "homing_frac"]
    stats = {
        "source": "SapiMouse (Antal et al.), 120 kullanıcı, tarayıcı; yalnızca özet istatistik",
        "method": {"rest_ms": REST_MS, "min_dist_px": MIN_DIST, "min_points": MIN_POINTS},
        "users_used": len(per_user),
        "movements": len(all_m),
        "pooled": {k: describe([m[k] for m in all_m]) for k in keys},
        "lat_sign_positive_frac": float(np.mean([m["lat_sign"] > 0 for m in all_m])),
        "between_users": {k: describe([u[k] for u in per_user]) for k in per_user[0] if k != "n"},
        "click_hold_ms": describe(clicks_all),
        "rest_between_movements_ms": describe(rests_all),
        "raw_sample_dt_ms": describe(dts),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: stats[k] for k in ["users_used", "movements", "lat_sign_positive_frac"]}, ensure_ascii=False))
    for k in keys:
        d = stats["pooled"][k]
        print(f"{k:16s} median={d['median']:.3f}  p5={d['p5']:.3f}  p95={d['p95']:.3f}")
    for k, d in stats["between_users"].items():
        print(f"[kişiler arası] {k:22s} median={d['median']:.3f}  p5={d['p5']:.3f}  p95={d['p95']:.3f}")
    for k in ["click_hold_ms", "rest_between_movements_ms", "raw_sample_dt_ms"]:
        d = stats[k]
        print(f"{k:26s} median={d['median']:.1f}  p5={d['p5']:.1f}  p95={d['p95']:.1f}")


if __name__ == "__main__":
    main()
