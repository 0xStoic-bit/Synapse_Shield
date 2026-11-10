"""Simüle insan nüfusunu Synapse'in gerçek karar yolundan geçirir ve yanlış-pozitif oranını raporlar.

Kullanım:  python research/human_sim/run_eval.py [kişi_sayısı] [tohum]
Çıktı:     research/human_sim/results/eval_<tohum>.json ve ekrana özet.

Hepsi insan; dolayısıyla "block" ve "challenge" kararlarının hepsi yanlış-pozitiftir.
"""

from __future__ import annotations

import base64
import collections
import json
import os
import sys
import tempfile
import time

# Gerçek veritabanına dokunmamak için ayrı bir SQLite; challenge yaşı kontrolü kapalı (testlerle aynı).
os.environ["SYNAPSE_DB_PATH"] = os.path.join(tempfile.gettempdir(), f"synapse_humansim_{os.getpid()}.db")
os.environ.setdefault("SYNAPSE_MIN_ELAPSED_MS", "0")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))

import numpy as np  # noqa: E402

import simulator as sim  # noqa: E402
from synapse_shield import core, tokens  # noqa: E402


def make_token(telemetry: dict) -> str:
    env = {"challenge": tokens.generate_challenge()["challenge"], "telemetry": telemetry}
    return base64.b64encode(json.dumps(env).encode()).decode()


def persona(p: sim.Person) -> str:
    if p.device == "mobile":
        return f"mobil-{p.platform}"
    if p.keyboard_only:
        return "klavye-only"
    return p.device


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rng = np.random.default_rng(seed)
    rows = []
    t0 = time.time()
    for i in range(n):
        p = sim.sample_person(rng, i)
        tel = sim.login_session(rng, p)
        ip = f"10.{(i >> 16) & 255}.{(i >> 8) & 255}.{i & 255}"
        d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent=sim.user_agent(p), token=make_token(tel))
        outcome = "allow" if d.allowed else ("challenge" if d.status_code == 429 else "block")
        rows.append({
            "persona": persona(p), "age": p.age, "tremor": p.tremor, "password_manager": p.password_manager,
            "outcome": outcome, "status": d.status_code, "score": d.bot_score, "classification": d.classification,
            "reasons": list(d.reasons or []),
        })
    dt = time.time() - t0

    def rate(sel):
        k = len(sel)
        if k == 0:
            return "  -"
        b = sum(r["outcome"] == "block" for r in sel)
        c = sum(r["outcome"] == "challenge" for r in sel)
        return f"n={k:4d}  engel={100 * b / k:5.1f}%  PoW={100 * c / k:5.1f}%  geçti={100 * (k - b - c) / k:5.1f}%"

    print(f"{n} simüle insan oturumu, {dt:.1f} sn\n")
    print("Genel           ", rate(rows))
    for key, title in (("persona", "Cihaz/tarz"), ("age", "Yaş")):
        print(f"\n{title}:")
        for v in sorted({r[key] for r in rows}):
            print(f"  {v:14s}", rate([r for r in rows if r[key] == v]))
    print("\nTitreme:")
    for v in (False, True):
        print(f"  {'var' if v else 'yok':14s}", rate([r for r in rows if r["tremor"] == v]))
    print("\nParola yöneticisi:")
    for v in (False, True):
        print(f"  {'evet' if v else 'hayır':14s}", rate([r for r in rows if r["password_manager"] == v]))

    fp = [r for r in rows if r["outcome"] != "allow"]
    cnt = collections.Counter()
    for r in fp:
        for reason in r["reasons"]:
            cnt[reason.split(":")[0].split("(")[0].strip()[:90]] += 1
    print(f"\nYanlış-pozitiflerde ({len(fp)}) en sık tetiklenen nedenler:")
    for reason, c in cnt.most_common(12):
        print(f"  {c:4d}  {reason}")

    out_dir = os.path.join(HERE, "results")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"eval_{seed}.json"), "w", encoding="utf-8") as f:
        json.dump({"n": n, "seed": seed, "assumptions": sim.ASSUME, "rows": rows}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
