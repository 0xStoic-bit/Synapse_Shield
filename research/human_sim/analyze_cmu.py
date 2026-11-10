"""CMU Keystroke Benchmark'tan (Killourhy & Maxion, DSN-2009) insan klavye zamanlaması istatistikleri.

Synapse motorunun eşiklerine bakmaz. Girdi: data/external/cmu/DSL-StrongPasswordData.csv
Sütunlar: H.<tuş> (basılı tutma, s), DD.<a>.<b> (basış→basış, s), UD.<a>.<b> (bırakış→basış, s; negatifse rollover).
Çıktı: research/human_sim/params/cmu_stats.json (yalnızca özet istatistik).
"""

from __future__ import annotations

import csv
import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "..", "..", "data", "external", "cmu", "DSL-StrongPasswordData.csv")
OUT = os.path.join(ROOT, "params", "cmu_stats.json")


def describe(a) -> dict:
    a = np.asarray(a, dtype=float)
    q = np.percentile(a, [5, 25, 50, 75, 95])
    return {"n": int(a.size), "mean": float(a.mean()), "sd": float(a.std()), "p5": float(q[0]), "p25": float(q[1]),
            "median": float(q[2]), "p75": float(q[3]), "p95": float(q[4])}


def main() -> None:
    with open(DATA, newline="") as f:
        rows = list(csv.DictReader(f))
    hcols = [c for c in rows[0] if c.startswith("H.")]
    ddcols = [c for c in rows[0] if c.startswith("DD.")]
    udcols = [c for c in rows[0] if c.startswith("UD.")]

    H = np.array([[float(r[c]) for c in hcols] for r in rows]) * 1000.0
    DD = np.array([[float(r[c]) for c in ddcols] for r in rows]) * 1000.0
    UD = np.array([[float(r[c]) for c in udcols] for r in rows]) * 1000.0
    subj = np.array([r["subject"] for r in rows])
    sess = np.array([int(r["sessionIndex"]) for r in rows])

    per_subject = []
    for s in sorted(set(subj)):
        m = subj == s
        h, dd, ud = H[m], DD[m], UD[m]
        per_subject.append({
            "hold_median": float(np.median(h)),
            "hold_cv_within_rep": float(np.median(h.std(axis=1) / h.mean(axis=1))),  # bir yazışın içindeki tuşlar arası
            "hold_cv_across_reps": float(np.median(h.std(axis=0) / h.mean(axis=0))),  # aynı tuşun tekrarlar arası
            "dd_median": float(np.median(dd)),
            "dd_cv_within_rep": float(np.median(dd.std(axis=1) / dd.mean(axis=1))),
            "rollover_frac": float((ud < 0).mean()),
            "dd_session1_median": float(np.median(dd[sess[m] == 1])),
            "dd_session8_median": float(np.median(dd[sess[m] == 8])),
        })

    stats = {
        "source": "CMU Keystroke Dynamics Benchmark (Killourhy & Maxion 2009), 51 kişi x 400 tekrar, sabit parola '.tie5Roanl'",
        "caveat": "Sabit, ezberlenmiş parola ve laptop; serbest metne göre daha hızlı ve tutarlı. Genellemede dikkat.",
        "pooled": {
            "hold_ms": describe(H.ravel()),
            "dd_ms": describe(DD.ravel()),
            "ud_ms": describe(UD.ravel()),
            "rollover_frac": float((UD < 0).mean()),
            "shift_hold_ms": describe(H[:, hcols.index("H.Shift.r")]),
            "return_hold_ms": describe(H[:, hcols.index("H.Return")]),
        },
        "between_subjects": {k: describe([p[k] for p in per_subject]) for k in per_subject[0]},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1, ensure_ascii=False)
    for k, d in stats["pooled"].items():
        if isinstance(d, dict):
            print(f"{k:16s} median={d['median']:.1f}  p5={d['p5']:.1f}  p95={d['p95']:.1f}  sd={d['sd']:.1f}")
        else:
            print(f"{k:16s} {d:.3f}")
    for k, d in stats["between_subjects"].items():
        print(f"[kişiler arası] {k:22s} median={d['median']:.3f}  p5={d['p5']:.3f}  p95={d['p95']:.3f}")


if __name__ == "__main__":
    main()
