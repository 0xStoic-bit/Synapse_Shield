"""Biyomekanik insan nüfusu simülatörü: Synapse SDK'sının göndereceği telemetriyi üretir.

İlke: parametreler Synapse motorunun eşiklerinden DEĞİL, gerçek insan verisinden ve literatürden gelir.
  * Fare: SapiMouse (120 kişi, tarayıcı) -> params/sapimouse_stats.json (analyze_sapimouse.py)
  * Klavye: CMU Keystroke Benchmark (51 kişi) -> params/cmu_stats.json (analyze_cmu.py)
            + Aalto 136M yayınındaki genel hız (5.1 ± 2.1 tuş/sn) serbest metin için.
  * Hareket felsefesi: optimize alt-hareket modeli (Meyer vd. 1988): hızlı bir birincil hareket hedefin
    yakınına gider, yavaş düzeltici alt-hareketler hedefe yerleşir. Her alt-hareket minimum-jerk profilli
    (Flash & Hogan 1985). Gürültü hızla orantılı (Harris & Wolpert 1998). Yaşlılarda daha düşük tepe hız
    ve daha çok alt-hareket (Walker vd. 1997; Keates vd.).
  * Tarayıcı katmanı: mousemove olayları ekran karesiyle (60/120/144 Hz) gelir, piksel yuvarlanır,
    konum değişmezse olay yoktur; SDK 30 ms'de bir örnekler (synapse-sdk.js ile aynı).

VARSAYIM olarak işaretli oranlar (cihaz dağılımı, erişilebilirlik, yaş grupları, titreme yaygınlığı) veriyle
değil, literatürle ya da makul tahminle seçildi; raporda ayrıca gösterilir.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
PARAMS = os.path.join(ROOT, "params")

# Hedef üstünde tıklamadan önceki bekleme (ms); SapiMouse süreleri bunu içerir.
PRECLICK_DWELL = (30.0, 150.0)
PRECLICK_DWELL_MEAN = sum(PRECLICK_DWELL) / 2

# SDK ile aynı (src/synapse_shield/static/synapse-sdk.js)
SDK_MOVE_THROTTLE_MS = 30
SDK_SCROLL_THROTTLE_MS = 100
FREQUENT_DIGRAPHS = {
    "th", "er", "on", "an", "re", "he", "in", "ed", "nd", "ha", "at", "en", "es", "of", "or", "nt", "ea", "ti",
    "to", "it", "st", "io", "le", "is", "ou", "ar", "as", "de", "rt", "ve", "la", "ik", "ak", "el", "al", "ma",
    "me", "ba", "ka",
}

# VARSAYIMLAR (veriyle değil, literatür/tahminle)
ASSUME = {
    "device": {"mouse": 0.55, "touchpad": 0.25, "mobile": 0.20},
    "age": {"young": 0.45, "middle": 0.40, "older": 0.15},
    "tremor_prevalence": {"young": 0.0, "middle": 0.01, "older": 0.06},  # Aachen/Sensors: 65+ ~%6
    "keyboard_only": 0.04,  # Tab ile gezinen (erişilebilirlik, alışkanlık)
    "password_manager": 0.06,  # parolayı otomatik dolduran
    "mobile_android": 0.70,  # Android IME tuşları "unidentified" gönderir
    "refresh_hz": {60: 0.70, 120: 0.20, 144: 0.10},
}

WORDS = ["mustafa", "ayse", "kerem", "deniz", "ahmet", "zeynep", "elif", "burak", "selin", "omer", "info", "admin",
         "test", "user", "kaplan", "yildiz", "demir", "celik", "arslan", "korkmaz", "sahin", "ozturk", "aydin"]

UA = {
    "desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "android": "Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36",
    "ios": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
}


def _load(name: str) -> dict:
    with open(os.path.join(PARAMS, name), encoding="utf-8") as f:
        return json.load(f)


MOUSE = _load("sapimouse_stats.json")
KEYS = _load("cmu_stats.json")


def qsample(rng: np.random.Generator, d: dict, lo: float | None = None, hi: float | None = None) -> float:
    """Özet istatistikteki (p5, p25, median, p75, p95) dağılımdan parça doğrusal örnek çeker."""
    xs = [d["p5"], d["p25"], d["median"], d["p75"], d["p95"]]
    ps = [0.05, 0.25, 0.5, 0.75, 0.95]
    u = rng.uniform(0.0, 1.0)
    if u < 0.05:
        v = xs[0] - (xs[1] - xs[0]) * (0.05 - u) / 0.2
    elif u > 0.95:
        v = xs[4] + (xs[4] - xs[3]) * (u - 0.95) / 0.2
    else:
        v = float(np.interp(u, ps, xs))
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return float(v)


def _choice(rng: np.random.Generator, table: dict):
    keys = list(table)
    return keys[int(rng.choice(len(keys), p=np.array([table[k] for k in keys], dtype=float)))]


@dataclass
class Person:
    pid: int
    device: str
    age: str
    tremor: bool
    keyboard_only: bool
    password_manager: bool
    platform: str  # desktop | android | ios
    refresh_hz: int
    # fare (kişiler arası dağılımdan)
    straightness: float
    lat_ratio: float
    tpeak: float
    sub_mean: float
    homing: float
    dur_c: float
    dur_p: float
    dur_sd: float
    tremor_amp: float
    noise_k: float
    # klavye
    hold_ms: float
    hold_cv: float
    iki_ms: float
    iki_cv: float
    rollover: float
    viewport: tuple = field(default=(1366, 657))


def sample_person(rng: np.random.Generator, pid: int) -> Person:
    bu = MOUSE["between_users"]
    bk = KEYS["between_subjects"]
    device = _choice(rng, ASSUME["device"])
    age = _choice(rng, ASSUME["age"])
    tremor = rng.uniform() < ASSUME["tremor_prevalence"][age]
    platform = "desktop" if device != "mobile" else ("android" if rng.uniform() < ASSUME["mobile_android"] else "ios")

    straight = qsample(rng, bu["straightness_median"], 0.5, 0.99)
    lat = qsample(rng, bu["max_lat_ratio_median"], 0.01, 0.4)
    tpeak = qsample(rng, bu["tpeak_frac_median"], 0.04, 0.6)
    sub_mean = qsample(rng, bu["submovements_mean"], 1.0, 8.0)
    homing = qsample(rng, bu["homing_frac_median"], 0.1, 0.9)
    # Süre: kişinin 400 px'lik tipik süresi ve mesafeye duyarlılığı ayrı örneklenir, c bunlardan çıkar
    # (c ile p'yi bağımsız örneklemek gerçek olmayan uç süreler üretir).
    dur_400 = qsample(rng, bu["dur_at_400"], 250.0, 2500.0)
    dur_p = qsample(rng, bu["dur_power_p"], 0.0, 0.6)
    dur_sd = qsample(rng, bu["dur_residual_sd_log"], 0.1, 0.8)

    # Yaş ve cihaz etkileri (literatür: yaşlılarda tepe hız %30-70 düşük, daha çok alt-hareket)
    if age == "older":
        dur_400 *= rng.uniform(1.3, 1.8)
        sub_mean += rng.uniform(0.5, 2.0)
        homing = min(0.9, homing * rng.uniform(1.05, 1.3))
    if device == "touchpad":
        dur_400 *= rng.uniform(1.15, 1.4)
        sub_mean += rng.uniform(0.3, 1.2)

    # Klavye: CMU kişiler arası dağılımı; serbest metin için Aalto hızı (5.1 ± 2.1 tuş/sn)
    hold = qsample(rng, bk["hold_median"], 30.0, 250.0)
    hold_cv = qsample(rng, bk["hold_cv_within_rep"], 0.08, 0.6)
    kps = max(1.2, rng.normal(5.1, 2.1))
    iki = 1000.0 / kps
    iki_cv = qsample(rng, bk["dd_cv_within_rep"], 0.2, 0.9)
    roll = qsample(rng, bk["rollover_frac"], 0.0, 0.6)
    if age == "older":
        iki *= rng.uniform(1.2, 1.8)
        hold *= rng.uniform(1.0, 1.3)
    if device == "mobile":
        iki *= rng.uniform(1.3, 2.0)  # dokunmatik klavye daha yavaş

    vp = [(1366, 657), (1920, 969), (1536, 754), (1440, 789), (2560, 1329), (1280, 649)]
    viewport = vp[int(rng.integers(len(vp)))] if device != "mobile" else [(390, 664), (412, 783), (360, 640)][int(rng.integers(3))]
    hz = _choice(rng, ASSUME["refresh_hz"]) if device != "mobile" else 60

    return Person(
        pid=pid, device=device, age=age, tremor=tremor,
        keyboard_only=(device != "mobile" and rng.uniform() < ASSUME["keyboard_only"]),
        password_manager=rng.uniform() < ASSUME["password_manager"],
        platform=platform, refresh_hz=hz,
        straightness=straight, lat_ratio=lat, tpeak=tpeak, sub_mean=sub_mean, homing=homing,
        dur_c=dur_400 / 400.0**dur_p, dur_p=dur_p, dur_sd=dur_sd,
        tremor_amp=(rng.uniform(1.0, 3.5) if tremor else rng.uniform(0.05, 0.3)),
        noise_k=rng.uniform(0.04, 0.10),
        hold_ms=hold, hold_cv=hold_cv, iki_ms=iki, iki_cv=iki_cv, rollover=roll,
        viewport=viewport,
    )


# --- Hareket ---------------------------------------------------------------------

def _min_jerk(tau: np.ndarray) -> np.ndarray:
    tau = np.clip(tau, 0.0, 1.0)
    return 10 * tau**3 - 15 * tau**4 + 6 * tau**5


def aimed_movement(rng: np.random.Generator, p: Person, p0, p1, t0: float) -> tuple[list, float]:
    """p0'dan p1'e hedefe yönelik hareket: (olaylar [(t, x, y)], bitiş zamanı) döner. Olaylar ham tarayıcı hızında."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    vec = p1 - p0
    D = float(np.hypot(*vec))
    if D < 2:
        return [], t0
    # SapiMouse süreleri tıklamadan önceki hedef üstü beklemeyi içerir; hareketin kendisi için onu düşeriz.
    T = p.dur_c * D**p.dur_p * math.exp(rng.normal(0.0, p.dur_sd)) - PRECLICK_DWELL_MEAN
    T = float(np.clip(T, 150.0, 4000.0))
    u = vec / D
    n = np.array([-u[1], u[0]])

    # Birincil alt-hareket: süresinin oranı, tepe hızın erken gelmesini sağlar (tpeak ~ d1/2).
    tp = float(np.clip(p.tpeak * math.exp(rng.normal(0.0, 0.35)), 0.05, 0.6))
    d1 = float(np.clip(2.0 * tp, 0.12, 1.0))
    # Ölçülen alt-hareket sayısı düzeltmelerden fazladır (duraklama ve gürültü tepeleri de sayılır);
    # 0.6 katsayısı simülatörün ÖLÇÜLEN dağılımını SapiMouse'a oturtur (validate.py).
    k_total = 1 + int(rng.poisson(max(0.0, (p.sub_mean - 1.0) * 0.6)))
    if d1 > 0.92:
        k_total = 1
    k_total = min(k_total, 6)

    # Birincil hareket çoğu zaman hedefin gerisine, bazen ilerisine (aşma) ve yanına düşer; düzelticiler kapatır.
    # Ara sıra (arama/tereddüt) birincil hareket hedeften uzak bir ara noktaya gider: düşük düzlüğün kaynağı.
    wander = rng.uniform() < 0.12
    if wander:
        k_total = max(k_total, 2)
        end1 = p0 + vec * rng.uniform(0.2, 0.9) + n * rng.uniform(0.4, 1.4) * D * (1 if rng.uniform() < 0.5 else -1)
    elif k_total > 1:
        under = abs(rng.normal(0.12, 0.06)) if rng.uniform() > 0.25 else -abs(rng.normal(0.05, 0.04))
        end1 = p0 + vec * (1.0 - under) + n * rng.normal(0.0, 0.025) * D
    else:
        end1 = p1.copy()
    bow = p.lat_ratio * D * (1 if rng.uniform() < 0.5 else -1) * abs(rng.normal(1.0, 0.5))

    pieces = [(t0, t0 + d1 * T, p0, end1, bow)]
    t_cur = t0 + d1 * T
    cur = end1
    rest_T = (1.0 - d1) * T
    for i in range(1, k_total):
        last = i == k_total - 1
        share = rest_T / (k_total - 1)
        # Düzeltmeler kısa ve hızlıdır; aradaki süre beklemedir (insan hedefe sürünmez).
        dur = max(60.0, share * rng.uniform(0.35, 0.7)) if not (wander and i == 1) else max(150.0, share * 0.9)
        gap = max(0.0, share - dur)
        if rng.uniform() < 0.1:
            gap += rng.uniform(100, 250)
        if last:
            tgt = p1
        else:
            rem = p1 - cur
            tgt = cur + rem * rng.uniform(0.6, 0.95) + n * rng.normal(0.0, 0.01) * D
        small_bow = rng.normal(0.0, 0.1) * float(np.hypot(*(tgt - cur)))
        pieces.append((t_cur + gap, t_cur + gap + dur, cur, tgt, small_bow))
        t_cur = t_cur + gap + dur
        cur = tgt
    t_end = t_cur

    # 1 ms çözünürlükte sürekli yörünge
    ts = np.arange(t0, t_end + 1.0, 1.0)
    pos = np.repeat(p0[None, :], len(ts), axis=0)
    for (a, b, s, e, bw) in pieces:
        seg = e - s
        L = float(np.hypot(*seg)) or 1.0
        nn = np.array([-seg[1], seg[0]]) / L
        m = ts >= a
        tau = np.clip((ts[m] - a) / max(1.0, b - a), 0.0, 1.0)
        prog = _min_jerk(tau)
        pos[m] = s + np.outer(prog, seg) + np.outer(bw * np.sin(math.pi * prog), nn)

    # Hıza orantılı gürültü (Harris-Wolpert) ve titreme
    vel = np.vstack([np.zeros((1, 2)), np.diff(pos, axis=0)])
    speed = np.hypot(vel[:, 0], vel[:, 1])
    raw = rng.normal(0.0, 1.0, size=pos.shape)
    kn = max(1, min(25, len(ts)))
    kern = np.ones(kn) / kn
    lp = np.column_stack([np.convolve(raw[:, j], kern, mode="same") for j in range(2)])
    noise = np.cumsum(lp * speed[:, None] * p.noise_k, axis=0)
    ramp = np.clip((ts - t0) / max(1.0, t_end - t0), 0, 1)[:, None]
    noise = noise - ramp * noise[-1]  # hedefte sıfıra iner
    f_tr = rng.uniform(8.0, 12.0)
    ph = rng.uniform(0, 2 * math.pi, size=2)
    tremor = p.tremor_amp * np.column_stack([np.sin(2 * math.pi * f_tr * ts / 1000.0 + ph[0]),
                                             np.sin(2 * math.pi * f_tr * ts / 1000.0 + ph[1])])
    pos = pos + noise + tremor

    return browser_sample(rng, p, ts, pos), t_end


def hover(rng: np.random.Generator, p: Person, xy, t0: float, t1: float) -> list:
    """Hedef üstünde beklerken el tam durmaz: kare başına küçük bir olasılıkla 1 px kıpırdanma."""
    out = []
    frame = 1000.0 / p.refresh_hz
    x, y = int(round(xy[0])), int(round(xy[1]))
    t = t0 + frame
    while t < t1:
        if rng.uniform() < 0.12:
            x += int(rng.choice([-1, 1]))
            out.append((t, x, y))
        t += frame
    return out


def browser_sample(rng: np.random.Generator, p: Person, ts: np.ndarray, pos: np.ndarray) -> list:
    """Ekran karesi hızında olay: piksel yuvarlanır, konum değişmezse olay yoktur."""
    frame = 1000.0 / p.refresh_hz
    out = []
    t = float(ts[0])
    last = None
    while t <= ts[-1]:
        i = int(min(len(ts) - 1, max(0, round(t - ts[0]))))
        xy = (int(round(pos[i, 0])), int(round(pos[i, 1])))
        if xy != last:
            out.append((t, xy[0], xy[1]))
            last = xy
        t += frame + rng.normal(0.0, 0.8)
    # son nokta her zaman hedef
    end = (int(round(pos[-1, 0])), int(round(pos[-1, 1])))
    if end != last:
        out.append((float(ts[-1]), end[0], end[1]))
    return out


# --- Klavye ----------------------------------------------------------------------

def type_text(rng: np.random.Generator, p: Person, text: str, t0: float, sensitive: bool) -> tuple[list, float]:
    """SDK'nın keydown/keyup olaylarını üretir. Basılan her karakter "masked" gider (Zero-PII)."""
    ev = []
    t = t0
    prev = ""
    mobile_android = p.platform == "android"
    for ch in text:
        raw = ch.lower()
        is_freq = bool(prev) and (prev + raw) in FREQUENT_DIGRAPHS
        prev = raw
        if mobile_android:
            name = "unidentified"
            hold = max(1.0, rng.normal(12.0, 6.0))  # Gboard: keydown/keyup neredeyse eşzamanlı
        else:
            name = "masked"
            hold = p.hold_ms * math.exp(rng.normal(0.0, p.hold_cv))
        shift = ch.isupper() and not mobile_android
        if shift:
            sh_down = t - rng.uniform(60, 160)
            ev.append({"type": "down", "key": "shift", "t": sh_down, "is_freq_digraph": False})
        ev.append({"type": "down", "key": name, "t": t, "is_freq_digraph": is_freq})
        up = t + hold
        ev.append({"type": "up", "key": name, "t": up, "down": t, "up": up, "duration_ms": up - t, "is_freq_digraph": is_freq})
        if shift:
            su = up + rng.uniform(10, 60)
            ev.append({"type": "up", "key": "shift", "t": su, "down": sh_down, "up": su, "duration_ms": su - sh_down, "is_freq_digraph": False})
        # Sonraki tuşa kadar: lognormal IKI; rollover'da bir sonraki basış bu bırakıştan önce olur
        iki = p.iki_ms * math.exp(rng.normal(0.0, p.iki_cv))
        if rng.uniform() < 0.06:
            iki += rng.uniform(300, 1500)  # düşünme / kelime arası duraklama
        if rng.uniform() < p.rollover:
            iki = min(iki, hold * rng.uniform(0.5, 0.95))
        t = t + max(25.0, iki)
        # Yazım hatası ve düzeltme
        if rng.uniform() < 0.02:
            b_hold = p.hold_ms * math.exp(rng.normal(0.0, p.hold_cv))
            ev.append({"type": "down", "key": "backspace", "t": t, "is_freq_digraph": False})
            ev.append({"type": "up", "key": "backspace", "t": t + b_hold, "down": t, "up": t + b_hold, "duration_ms": b_hold, "is_freq_digraph": False})
            t += max(80.0, p.iki_ms * math.exp(rng.normal(0.0, p.iki_cv)))
    ev.sort(key=lambda e: e["t"])
    return ev, t


def press_key(rng: np.random.Generator, p: Person, key: str, t0: float) -> tuple[list, float]:
    hold = p.hold_ms * math.exp(rng.normal(0.0, p.hold_cv))
    return ([{"type": "down", "key": key, "t": t0, "is_freq_digraph": False},
             {"type": "up", "key": key, "t": t0 + hold, "down": t0, "up": t0 + hold, "duration_ms": hold, "is_freq_digraph": False}],
            t0 + hold)


# --- Dokunma -----------------------------------------------------------------------

def tap(rng: np.random.Generator, p: Person, xy, t0: float) -> tuple[list, dict, float]:
    """touchstart + küçük parmak kayması (touchmove) + touchend -> (hareket olayları, tıklama, bitiş)."""
    r = float(rng.uniform(8.0, 20.0))
    f = float(rng.uniform(0.2, 0.9)) if p.platform == "android" else 0.0
    dur = float(np.clip(rng.lognormal(math.log(100.0), 0.35), 40.0, 400.0))
    x, y = float(xy[0]), float(xy[1])
    moves = [{"x": int(round(x)), "y": int(round(y)), "t": t0, "r": round(r, 3), "f": round(f, 3), "source": "touch"}]
    k = int(rng.integers(0, 3))
    for i in range(k):
        x += rng.normal(0, 1.5)
        y += rng.normal(0, 1.5)
        moves.append({"x": int(round(x)), "y": int(round(y)), "t": t0 + dur * (i + 1) / (k + 1), "r": round(r + rng.normal(0, 1), 3),
                      "f": round(f, 3), "source": "touch"})
    click = {"x": int(round(x)), "y": int(round(y)), "t": t0 + dur, "r": round(r, 3), "tap_duration_ms": round(dur), "source": "touch"}
    return moves, click, t0 + dur


# --- Oturum ------------------------------------------------------------------------

def _target(rng: np.random.Generator, center, w: float, h: float):
    return (center[0] + rng.normal(0, w / 6.0), center[1] + rng.normal(0, h / 6.0))


def _sdk_throttle(events: list) -> list:
    out = []
    last = -1e9
    for (t, x, y) in events:
        if t - last >= SDK_MOVE_THROTTLE_MS:
            out.append({"x": x, "y": y, "t": t})
            last = t
    return out


def login_session(rng: np.random.Generator, p: Person) -> dict:
    """Bir giriş formunu dolduran insanın telemetrisi (SDK biçiminde, göreli ms zaman damgalarıyla)."""
    W, H = p.viewport
    user_f = (W / 2, H * 0.42)
    pass_f = (W / 2, H * 0.52)
    btn = (W / 2, H * 0.63)
    username = WORDS[int(rng.integers(len(WORDS)))] + (str(int(rng.integers(1, 99))) if rng.uniform() < 0.4 else "")
    if rng.uniform() < 0.2:
        username = username.capitalize()
    pw_len = int(rng.integers(8, 15))
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    password = "".join(alphabet[int(rng.integers(len(alphabet)))] for _ in range(pw_len))

    moves_raw: list = []
    touch_moves: list = []
    clicks: list = []
    keys: list = []
    scrolls: list = []
    t = float(rng.uniform(800, 4000))  # sayfa açıldıktan sonra ilk etkileşime kadar
    cursor = (rng.uniform(0.2, 0.8) * W, rng.uniform(0.2, 0.9) * H)

    def mouse_to(target, t):
        nonlocal cursor
        ev, t_end = aimed_movement(rng, p, cursor, target, t)
        moves_raw.extend(ev)
        cursor = target
        t_click = t_end + rng.uniform(*PRECLICK_DWELL)
        if ev:
            moves_raw.extend(hover(rng, p, ev[-1][1:], t_end, t_click))
        return t_click

    def mouse_click(t):
        hold = qsample(rng, MOUSE["click_hold_ms"], 20.0, 600.0)
        clicks.append({"x": int(round(cursor[0])), "y": int(round(cursor[1])), "t": t + hold})
        return t + hold

    def gap_kb_mouse(t):
        return t + rng.uniform(150, 700)  # el klavyeden fareye / fareden klavyeye

    # İsteğe bağlı: önce sayfayı biraz kaydırır
    if rng.uniform() < 0.25:
        y = 0.0
        for _ in range(int(rng.integers(2, 8))):
            y += rng.uniform(40, 160)
            scrolls.append({"y": round(y), "t": t})
            t += rng.uniform(SDK_SCROLL_THROTTLE_MS, 400)

    if p.device == "mobile":
        for field_c, text, sens in ((user_f, username, False), (pass_f, password, True)):
            mv, ck, t = tap(rng, p, _target(rng, field_c, W * 0.8, 44), t)
            touch_moves.extend(mv)
            clicks.append(ck)
            t += rng.uniform(300, 900)  # klavyenin açılması
            if not (sens and p.password_manager):
                ev, t = type_text(rng, p, text, t, sens)
                keys.extend(ev)
            t += rng.uniform(200, 800)
        mv, ck, t = tap(rng, p, _target(rng, btn, W * 0.8, 48), t)
        touch_moves.extend(mv)
        clicks.append(ck)
    elif p.keyboard_only:
        for _ in range(int(rng.integers(1, 4))):  # forma kadar Tab
            ev, t = press_key(rng, p, "tab", t)
            keys.extend(ev)
            t += rng.uniform(150, 600)
        ev, t = type_text(rng, p, username, t, False)
        keys.extend(ev)
        t += rng.uniform(100, 400)
        ev, t = press_key(rng, p, "tab", t)
        keys.extend(ev)
        t += rng.uniform(150, 500)
        if not p.password_manager:
            ev, t = type_text(rng, p, password, t, True)
            keys.extend(ev)
        t += rng.uniform(150, 600)
        ev, t = press_key(rng, p, "enter", t)
        keys.extend(ev)
    else:
        t = mouse_to(_target(rng, user_f, 300, 36), t)
        t = mouse_click(t)
        t = gap_kb_mouse(t)
        ev, t = type_text(rng, p, username, t, False)
        keys.extend(ev)
        if rng.uniform() < 0.5:
            t += rng.uniform(100, 400)
            ev, t = press_key(rng, p, "tab", t)
            keys.extend(ev)
            t += rng.uniform(150, 400)
        else:
            t = gap_kb_mouse(t)
            t = mouse_to(_target(rng, pass_f, 300, 36), t)
            t = mouse_click(t)
            t = gap_kb_mouse(t)
        if not p.password_manager:
            ev, t = type_text(rng, p, password, t, True)
            keys.extend(ev)
        if rng.uniform() < 0.5:
            t += rng.uniform(100, 400)
            ev, t = press_key(rng, p, "enter", t)
            keys.extend(ev)
        else:
            t = gap_kb_mouse(t)
            t = mouse_to(_target(rng, btn, 120, 40), t)
            t = mouse_click(t)

    keys.sort(key=lambda e: e["t"])
    mouse = _sdk_throttle(moves_raw) + touch_moves
    mouse.sort(key=lambda e: e["t"])
    telemetry = {
        "mouse_movements": [_round_t(m) for m in mouse[-500:]],
        "clicks": [_round_t(c) for c in clicks[-50:]],
        "keystrokes": [_round_keys(k) for k in keys[-50:]],
        "scrolls": [_round_t(s) for s in scrolls[-200:]],
        "browser": browser_profile(rng, p),
    }
    return telemetry


def _round_t(d: dict) -> dict:
    d = dict(d)
    d["t"] = int(round(d["t"]))
    return d


def _round_keys(d: dict) -> dict:
    d = dict(d)
    for k in ("t", "down", "up", "duration_ms"):
        if k in d:
            d[k] = int(round(d[k]))
    return d


def browser_profile(rng: np.random.Generator, p: Person) -> dict:
    W, H = p.viewport
    if p.device == "mobile":
        return {
            "webdriver": False, "screen_width": W, "screen_height": H,
            "device_pixel_ratio": float(rng.choice([2.0, 2.625, 3.0])), "touch_supported": True, "max_touch_points": 5,
            "motion_variance": round(float(rng.lognormal(math.log(0.6), 0.8)), 6),
            "webgl_renderer": "Adreno (TM) 642L" if p.platform == "android" else "Apple GPU",
            "orientation": "portrait-primary", "plugins_length": 0, "languages": "tr-TR,tr,en-US,en",
            "is_plugin_array_fake": False, "has_webdriver_own_prop": False, "is_webgl_hooked": False, "is_canvas_hooked": False,
        }
    return {
        "webdriver": False, "screen_width": W, "screen_height": H,
        "device_pixel_ratio": float(rng.choice([1.0, 1.25, 1.5, 2.0])), "touch_supported": p.device == "touchpad" and rng.uniform() < 0.2,
        "max_touch_points": 0, "motion_variance": 0.0,
        "webgl_renderer": str(rng.choice(["ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                                           "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                                           "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
                                           "Apple M1"])),
        "orientation": "landscape-primary", "plugins_length": 5, "languages": "tr-TR,tr,en-US,en",
        "is_plugin_array_fake": False, "has_webdriver_own_prop": False, "is_webgl_hooked": False, "is_canvas_hooked": False,
    }


def user_agent(p: Person) -> str:
    return UA[p.platform]
