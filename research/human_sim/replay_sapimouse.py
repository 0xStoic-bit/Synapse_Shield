"""GERÇEK insan verisini (SapiMouse) Synapse'in karar yolundan geçirir: simülatörden bağımsız FPR ölçümü.

Her oturum WINDOW_MS'lik pencerelere bölünür; SDK'nın yapacağı gibi fare olayları 30 ms'de bir örneklenir,
sol tık basışları "clicks" olur. Klavye yok (SapiMouse yalnızca fare). Tarayıcı profili sıradan bir masaüstü Chrome.

Kullanım: python research/human_sim/replay_sapimouse.py
"""

from __future__ import annotations

import collections
import glob
import os
import sys
import tempfile

os.environ["SYNAPSE_DB_PATH"] = os.path.join(tempfile.gettempdir(), f"synapse_replay_{os.getpid()}.db")
os.environ.setdefault("SYNAPSE_MIN_ELAPSED_MS", "0")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))

import numpy as np  # noqa: E402

from analyze_sapimouse import DATA, load_session  # noqa: E402
from run_eval import make_token  # noqa: E402
import simulator as sim  # noqa: E402
from synapse_shield import core  # noqa: E402

WINDOW_MS = float(os.environ.get("REPLAY_WINDOW_MS", "20000"))


def windows(rows):
    if not rows:
        return
    start = rows[0][0]
    cur = []
    for r in rows:
        if r[0] - start >= WINDOW_MS:
            yield cur
            cur = []
            start = r[0]
        cur.append(r)
    if cur:
        yield cur


def to_telemetry(win, rng) -> dict | None:
    t0 = win[0][0]
    moves, clicks = [], []
    last = -1e9
    for t, button, state, x, y in win:
        rt = int(t - t0) + 1000
        if state in ("Move", "Drag") and rt - last >= sim.SDK_MOVE_THROTTLE_MS:
            moves.append({"x": int(x), "y": int(y), "t": rt})
            last = rt
        elif state == "Released" and button == "Left":
            clicks.append({"x": int(x), "y": int(y), "t": rt})
    if len(moves) < 20 or not clicks:
        return None
    # Gerçek bir gönderim tıklama anında olur: pencereyi son tıklamada bitir (sonrasındaki hareketler gitmez).
    t_submit = clicks[-1]["t"]
    moves = [m for m in moves if m["t"] <= t_submit]
    if len(moves) < 20:
        return None
    p = sim.Person(pid=0, device="mouse", age="young", tremor=False, keyboard_only=False, password_manager=False,
                   platform="desktop", refresh_hz=60, straightness=0, lat_ratio=0, tpeak=0, sub_mean=0, homing=0,
                   dur_c=0, dur_p=0, dur_sd=0, tremor_amp=0, noise_k=0, hold_ms=0, hold_cv=0, iki_ms=0, iki_cv=0,
                   rollover=0, viewport=(1920, 969))
    br = sim.browser_profile(rng, p)
    br["touch_supported"] = False
    return {"mouse_movements": moves[-500:], "clicks": clicks[-50:], "keystrokes": [], "scrolls": [], "browser": br}


def main() -> None:
    rng = np.random.default_rng(0)
    users = sorted(glob.glob(os.path.join(DATA, "user*")))
    rows = []
    i = 0
    for u in users:
        for s in sorted(glob.glob(os.path.join(u, "*.csv"))):
            for win in windows(load_session(s)):
                tel = to_telemetry(win, rng)
                if not tel:
                    continue
                i += 1
                ip = f"10.200.{(i >> 8) & 255}.{i & 255}"
                d = core.evaluate_synapse_request_sync(client_ip=ip, user_agent=sim.UA["desktop"], token=make_token(tel))
                outcome = "allow" if d.allowed else ("challenge" if d.status_code == 429 else "block")
                rows.append({"user": os.path.basename(u), "outcome": outcome, "score": d.bot_score, "reasons": list(d.reasons or [])})
    k = len(rows)
    b = sum(r["outcome"] == "block" for r in rows)
    c = sum(r["outcome"] == "challenge" for r in rows)
    users_blocked = len({r["user"] for r in rows if r["outcome"] == "block"})
    print(f"GERÇEK insan pencereleri (SapiMouse, {WINDOW_MS / 1000:.0f} sn): n={k}  engel={100 * b / k:.1f}%  PoW={100 * c / k:.1f}%  geçti={100 * (k - b - c) / k:.1f}%")
    print(f"En az bir penceresi engellenen kişi: {users_blocked}/{len({r['user'] for r in rows})}")
    scores = np.array([r["score"] for r in rows])
    print(f"Risk skoru: medyan={np.median(scores):.1f}  p25={np.percentile(scores, 25):.1f}  p75={np.percentile(scores, 75):.1f}")
    cnt = collections.Counter()
    for r in rows:
        if r["outcome"] != "allow":
            for reason in r["reasons"]:
                cnt[reason.split(":")[0].split("(")[0].strip()[:90]] += 1
    print("Engellenen/PoW pencerelerde en sık nedenler:")
    for reason, n in cnt.most_common(12):
        print(f"  {n:4d}  {reason}")


if __name__ == "__main__":
    main()
