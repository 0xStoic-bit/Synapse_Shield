"""
Synapse Shield - Kinematic Feature Extractor v0.10.0 (Native Rust Core Accelerated & Mobile SDK v2.0)
"""

import math
from typing import Any

import numpy as np

try:
    from . import synapse_core_rs

    HAS_RUST_CORE = bool(synapse_core_rs.is_rust_core_active())
except (ImportError, AttributeError):
    try:
        import synapse_core_rs

        HAS_RUST_CORE = bool(synapse_core_rs.is_rust_core_active())
    except (ImportError, AttributeError):
        synapse_core_rs = None
        HAS_RUST_CORE = False


def is_rust_accelerated() -> bool:
    """Returns True if the native Rust core extension is loaded and active."""
    return HAS_RUST_CORE


def evaluate_curvature_zerocopy(x: Any, y: Any, t: Any) -> dict[str, float]:
    """Zero-copy evaluation of differential curvature directly from NumPy or contiguous buffers via Rust SIMD."""
    if HAS_RUST_CORE and synapse_core_rs is not None:
        try:
            return synapse_core_rs.evaluate_curvature_zerocopy_rs(x, y, t)
        except Exception:
            pass

    # NumPy fallback
    try:
        return _curvature_metrics(x, y, t)
    except Exception:
        return {"curvature_score": 0.0, "mean_curvature": 0.0, "curvature_var": 0.0, "curvature_rate_var": 0.0}


# Minimum step (px) on both sides of a point for its curvature to count toward the "chaotic" checks (v0.10.6).
# kappa = |v x a| / |v|^3 explodes as the cursor slows to a stop, and 1-px quantisation makes direction
# meaningless there. Chosen on real data (SapiMouse, 4,844 six-second windows): 5 px drops this rule's human
# false positives from 67% to 0.4% while Bezier/linear/minimum-jerk bot detection stays at 99-100%.
CURVATURE_MIN_STEP_PX = 5.0
# Fewer moving points than this: the gated statistics are not used.
CURVATURE_MIN_GATED_POINTS = 10


def _kappa_moments(kappa: np.ndarray, dts: np.ndarray) -> tuple[float, float, float, float]:
    """(mean, var, var of dkappa/dt, fraction of kappa > 0.1); dts[i-1] is the time between kappa[i-1] and kappa[i]."""
    mean_k = float(np.mean(kappa))
    var_k = float(np.var(kappa))
    if len(kappa) > 1:
        d_k = np.diff(kappa) / np.maximum(dts[: len(kappa) - 1], 0.1)
        var_dk = float(np.var(d_k))
    else:
        var_dk = 0.0
    return mean_k, var_k, var_dk, float(np.mean(kappa > 0.1))


def _curvature_metrics(x: Any, y: Any, t: Any) -> dict[str, float]:
    """Differential curvature naturalness; mirrors crates/synapse_core_rs/src/curvature.rs exactly."""
    x_arr = np.asarray(x, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)
    t_arr = np.asarray(t, dtype=np.float64)
    n = min(len(x_arr), len(y_arr), len(t_arr))
    if n < 4:
        return {"curvature_score": 0.0, "mean_curvature": 0.0, "curvature_var": 0.0, "curvature_rate_var": 0.0}
    x_arr, y_arr, t_arr = x_arr[:n], y_arr[:n], t_arr[:n]

    dt = np.maximum(np.diff(t_arr), 0.1)
    dx, dy = np.diff(x_arr), np.diff(y_arr)
    vx = dx / dt
    vy = dy / dt

    dt_a = (dt[1:] + dt[:-1]) * 0.5
    ax = np.diff(vx) / dt_a
    ay = np.diff(vy) / dt_a

    vx_s = vx[1:]
    vy_s = vy[1:]
    num = np.abs(vx_s * ay - vy_s * ax)
    v_sq = vx_s**2 + vy_s**2 + 1e-6
    kappa = num / (v_sq * np.sqrt(v_sq))

    candidates = [_kappa_moments(kappa, dt_a[1:])]
    mean_k, var_k, var_dk, _ = candidates[0]

    # Moments over "moving" points only: both neighbouring steps >= CURVATURE_MIN_STEP_PX.
    step = np.hypot(dx, dy)
    keep = (step[:-1] >= CURVATURE_MIN_STEP_PX) & (step[1:] >= CURVATURE_MIN_STEP_PX)
    gated = None
    if int(keep.sum()) >= CURVATURE_MIN_GATED_POINTS:
        t_kept = t_arr[2:][keep]
        gated = _kappa_moments(kappa[keep], np.diff(t_kept))
        candidates.append(gated)

    if any(m < 1e-6 and v < 1e-7 for m, v, _, _ in candidates):
        score = 0.95  # straight line bot
    elif any(dv < 1e-8 and v < 1e-4 for _, v, dv, _ in candidates):
        score = 0.90  # analytic Bezier / polynomial / minimum-jerk curve
    elif gated is not None and (gated[2] > 5.0 or gated[1] > 10.0):
        score = 0.85  # chaotic curvature while actually moving
    elif gated is not None and gated[3] > 0.5 and gated[2] > 2.0:
        score = 0.75
    else:
        score = 0.10

    return {
        "curvature_score": score,
        "mean_curvature": mean_k,
        "curvature_var": var_k,
        "curvature_rate_var": var_dk,
    }


def extract_features(telemetry: dict[str, Any], force_python: bool = False) -> dict[str, Any]:
    # 0. High-Performance Native Rust Core (v0.8.0+)
    if HAS_RUST_CORE and not force_python and isinstance(telemetry, dict) and synapse_core_rs is not None:
        try:
            return synapse_core_rs.extract_features_rs(telemetry)
        except Exception:
            pass  # Fail gracefully to pure Python/NumPy implementation

    features = {
        "mouse_points": 0,
        "total_distance": 0.0,
        "straightness": 1.0,
        "avg_velocity": 0.0,
        "max_velocity": 0.0,
        "velocity_var": 0.0,
        "avg_acceleration": 0.0,
        "acceleration_var": 0.0,
        "avg_jerk": 0.0,
        "dt_var": 0.0,
        "click_count": 0,
        "key_count": 0,
        "key_interval_avg": 0.0,
        "key_interval_var": 0.0,
        "webdriver": False,
        "screen_valid": True,
        "scroll_count": 0,
        "terminal_decel_ratio": 1.0,
        "plugins_length": 1,
        "touch_supported": False,
        "max_touch_points": 0,
        "avg_touch_radius": 0.0,
        "touch_radius_var": 0.0,
        "avg_touch_force": 0.0,
        "touch_event_count": 0,
        "screen_width": 1024.0,
        "spectral_purity": 0.0,
        "spectral_entropy": 1.0,
        "submovement_count": 0,
        "curvature_score": 0.0,
        "mean_curvature": 0.0,
        "curvature_var": 0.0,
        "curvature_rate_var": 0.0,
        "avg_dwell_time": 0.0,
        "dwell_time_var": 0.0,
        "avg_flight_time": 0.0,
        "flight_time_var": 0.0,
        "digraph_entropy": 0.5,
        "keystroke_score": 0.0,
        "tap_count": 0,
        "avg_tap_duration": 0.0,
        "tap_duration_var": 0.0,
        "device_pixel_ratio": 1.0,
        "motion_variance": 0.0,
        "is_mobile_gpu_mismatch": False,
    }

    if not isinstance(telemetry, dict):
        return features

    # 1. Tarayıcı, Ekran ve Mobil Donanım Telemetrisi
    browser = telemetry.get("browser", {})
    if isinstance(browser, dict):
        features["webdriver"] = bool(browser.get("webdriver", False))
        try:
            screen_width = float(browser.get("screen_width", 0))
            screen_height = float(browser.get("screen_height", 0))
            features["screen_width"] = screen_width
            if screen_width <= 0 or screen_height <= 0 or math.isnan(screen_width) or math.isnan(screen_height):
                features["screen_valid"] = False
        except (ValueError, TypeError):
            features["screen_valid"] = False

        features["touch_supported"] = bool(browser.get("touch_supported", False))
        try:
            features["max_touch_points"] = int(browser.get("max_touch_points", 0))
        except (ValueError, TypeError):
            features["max_touch_points"] = 0
        try:
            features["plugins_length"] = int(browser.get("plugins_length", 1))
        except Exception:
            features["plugins_length"] = 1

        try:
            dpr = float(browser.get("device_pixel_ratio", 1.0))
            if dpr > 0.0 and not math.isnan(dpr) and not math.isinf(dpr):
                features["device_pixel_ratio"] = dpr
        except (ValueError, TypeError):
            features["device_pixel_ratio"] = 1.0

        try:
            mv = float(browser.get("motion_variance", 0.0))
            if mv >= 0.0 and not math.isnan(mv) and not math.isinf(mv):
                features["motion_variance"] = mv
        except (ValueError, TypeError):
            features["motion_variance"] = 0.0

        webgl_renderer = str(browser.get("webgl_renderer", "")).lower()
        if (
            features["touch_supported"]
            and 0.0 < features["screen_width"] < 768.0
            and webgl_renderer
        ):
            desktop_or_emulator_gpus = (
                "swiftshader",
                "llvmpipe",
                "softpipe",
                "virtualbox",
                "vmware",
                "nvidia",
                "geforce",
                "radeon",
                "uhd graphics",
                "iris(tm)",
                "microsoft basic render",
            )
            if any(sig in webgl_renderer for sig in desktop_or_emulator_gpus):
                features["is_mobile_gpu_mismatch"] = True

    # 2. Sayaçlar ve Dokunma (Tap Hold Time) Biyometrisi
    scrolls = telemetry.get("scrolls", [])
    clicks = telemetry.get("clicks", [])
    features["scroll_count"] = len(scrolls) if isinstance(scrolls, list) else 0
    features["click_count"] = len(clicks) if isinstance(clicks, list) else 0

    tap_durations: list[float] = []
    touch_click_count = 0
    if isinstance(clicks, list):
        for c in clicks[:100]:
            if isinstance(c, dict):
                r_c = 0.0
                try:
                    r_c = float(c.get("r", 0.0))
                except (ValueError, TypeError):
                    r_c = 0.0
                is_touch_src = str(c.get("source", "")) == "touch"

                dur_val = c.get("tap_duration_ms", c.get("duration_ms"))
                valid_dur = 0.0
                if isinstance(dur_val, (int, float)) and not math.isnan(dur_val) and not math.isinf(dur_val):
                    d_f = float(dur_val)
                    if 0.0 < d_f < 5000.0:
                        tap_durations.append(d_f)
                        valid_dur = d_f

                if r_c > 0.0 or is_touch_src or valid_dur > 0.0:
                    touch_click_count += 1

    features["tap_count"] = len(tap_durations)
    if tap_durations:
        avg_tap = sum(tap_durations) / len(tap_durations)
        features["avg_tap_duration"] = avg_tap
        features["tap_duration_var"] = sum((d - avg_tap) ** 2 for d in tap_durations) / len(tap_durations)

    # 3. Klavye Dinamikleri (Dwell & Flight Time Parity v0.9.2 + Mobile IME Support)
    keystrokes = telemetry.get("keystrokes", [])
    if isinstance(keystrokes, list) and len(keystrokes) > 0:
        keystrokes = keystrokes[:150]  # DoS koruması: en fazla 150 tuş vuruşu işle

        # A. SDK'dan gelen down/up olay akışını eşleştir (Dwell Time & Key Count Parity)
        has_event_types = any(isinstance(k, dict) and k.get("type") in ("down", "up") for k in keystrokes)

        if has_event_types:
            detailed = []
            pending_downs: dict[str, list[float]] = {}
            for k in keystrokes:
                if not isinstance(k, dict):
                    continue
                k_type = k.get("type", "down")
                k_key = str(k.get("key", "unknown"))
                t_val = None
                for kn in ["t", "down", "time"]:
                    v = k.get(kn)
                    if isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v):
                        t_val = float(v)
                        break
                if t_val is None:
                    continue

                if k_type == "down":
                    pending_downs.setdefault(k_key, []).append((t_val, k.get("is_freq_digraph")))
                elif k_type == "up":
                    up_val = k.get("up")
                    if isinstance(up_val, (int, float)) and not math.isnan(up_val) and not math.isinf(up_val):
                        up_t = float(up_val)
                    else:
                        up_t = t_val

                    down_freq = k.get("is_freq_digraph")
                    if pending_downs.get(k_key):
                        down_t, stored_freq = pending_downs[k_key].pop(0)
                        if stored_freq is not None:
                            down_freq = stored_freq
                        entry = {"key": k_key, "down": down_t, "up": up_t}
                        if down_freq is not None:
                            entry["is_freq_digraph"] = bool(down_freq)
                        detailed.append(entry)
                    elif "duration_ms" in k and isinstance(k["duration_ms"], (int, float)):
                        dur = float(k["duration_ms"])
                        entry = {"key": k_key, "down": up_t - dur, "up": up_t}
                        if down_freq is not None:
                            entry["is_freq_digraph"] = bool(down_freq)
                        detailed.append(entry)
                    elif "down" in k and isinstance(k["down"], (int, float)):
                        entry = {"key": k_key, "down": float(k["down"]), "up": up_t}
                        if down_freq is not None:
                            entry["is_freq_digraph"] = bool(down_freq)
                        detailed.append(entry)

            # Kalan eşleşmemiş keydown'ları ekle
            for k_key, down_list in pending_downs.items():
                for item in down_list:
                    if isinstance(item, tuple):
                        down_t, stored_freq = item
                    else:
                        down_t, stored_freq = item, None
                    entry = {"key": k_key, "down": down_t, "up": None}
                    if stored_freq is not None:
                        entry["is_freq_digraph"] = bool(stored_freq)
                    detailed.append(entry)
        else:
            detailed = []
            for k in keystrokes:
                if isinstance(k, dict):
                    t_val = None
                    for kn in ["t", "down", "time"]:
                        v = k.get(kn)
                        if isinstance(v, (int, float)) and not math.isnan(v) and not math.isinf(v):
                            t_val = float(v)
                            break
                    if t_val is not None:
                        key_str = str(k.get("key", "unknown"))
                        up_val = k.get("up")
                        if isinstance(up_val, (int, float)) and not math.isnan(up_val) and not math.isinf(up_val):
                            up_val = float(up_val)
                        elif "duration_ms" in k and isinstance(k["duration_ms"], (int, float)):
                            up_val = t_val + float(k["duration_ms"])
                        else:
                            up_val = None
                        entry = {"key": key_str, "down": t_val, "up": up_val}
                        if "is_freq_digraph" in k:
                            entry["is_freq_digraph"] = bool(k["is_freq_digraph"])
                        detailed.append(entry)

        features["key_count"] = len(detailed)
        if len(detailed) > 0:
            detailed.sort(key=lambda x: x["down"])
            dwell_times = []
            for d in detailed:
                if d["up"] is not None:
                    dwell = d["up"] - d["down"]
                    if 0.0 < dwell < 5000.0:
                        dwell_times.append(dwell)

            if dwell_times:
                avg_dwell = sum(dwell_times) / len(dwell_times)
                var_dwell = sum((x - avg_dwell) ** 2 for x in dwell_times) / len(dwell_times)
                features["avg_dwell_time"] = avg_dwell
                features["dwell_time_var"] = var_dwell
            else:
                features["avg_dwell_time"] = 0.0
                features["dwell_time_var"] = 0.0

            flight_times = []
            for i in range(1, len(detailed)):
                prev = detailed[i - 1]
                curr = detailed[i]
                flight = (curr["down"] - prev["up"]) if prev["up"] is not None else (curr["down"] - prev["down"])
                if -500.0 < flight < 5000.0:
                    flight_times.append(flight)

            if flight_times:
                avg_flight = sum(flight_times) / len(flight_times)
                var_flight = sum((x - avg_flight) ** 2 for x in flight_times) / len(flight_times)
                features["avg_flight_time"] = avg_flight
                features["flight_time_var"] = var_flight
                features["key_interval_avg"] = avg_flight
                features["key_interval_var"] = var_flight
            else:
                features["avg_flight_time"] = 0.0
                features["flight_time_var"] = 0.0
                features["key_interval_avg"] = 0.0
                features["key_interval_var"] = 0.0

            valid_flights = [f for f in flight_times if 0.0 <= f <= 800.0]
            n_vf = len(valid_flights)
            if n_vf >= 4:
                bins = [0] * 8
                for f in valid_flights:
                    b = min(7, int(f / 100.0))
                    bins[b] += 1
                ent = 0.0
                for c in bins:
                    if c > 0:
                        p = c / n_vf
                        ent -= p * math.log2(p)
                entropy = ent / 3.0
            else:
                entropy = 0.5
            features["digraph_entropy"] = entropy

            score = 0.0
            if len(detailed) >= 3:
                if features["flight_time_var"] < 2.0 and len(flight_times) >= 3:
                    score += 0.85
                elif features["flight_time_var"] < 15.0 and len(flight_times) >= 4:
                    score += 0.60

                if 0.0 < features["avg_flight_time"] < 25.0:
                    score += 0.70

                # Mobile Virtual IME check (Gboard / iOS soft keyboard)
                # Require touch support or majority of keys being IME to prevent desktop bot dwell bypass
                ime_count = sum(
                    1 for d in detailed if str(d.get("key", "")).lower() in ("unidentified", "process")
                )
                # Require majority of keystrokes to be virtual IME to prevent desktop bot dwell bypass (matches Rust core)
                is_mobile_ime = bool(detailed) and (ime_count * 2 >= len(detailed))

                if dwell_times and not is_mobile_ime:
                    if features["avg_dwell_time"] < 15.0:
                        score += 0.75
                    elif features["dwell_time_var"] < 2.0 and len(dwell_times) >= 3:
                        score += 0.80

                # Digraph linguistic correlation check (supports client-side Zero-PII is_freq_digraph)
                frequent_digraphs = {
                    "th", "er", "on", "an", "re", "he", "in", "ed", "nd", "ha",
                    "at", "en", "es", "of", "or", "nt", "ea", "ti", "to", "it",
                    "st", "io", "le", "is", "ou", "ar", "as", "de", "rt", "ve",
                    "la", "le", "ik", "ak", "el", "al", "ma", "me", "ba", "ka",
                }
                digraph_flights = {}
                direct_freq_flights = []
                direct_non_freq_flights = []

                for i in range(1, len(detailed)):
                    fl = detailed[i]["down"] - detailed[i - 1]["down"]
                    if not (0.0 < fl < 2000.0):
                        continue

                    # If client computed is_freq_digraph (Zero-PII mode):
                    if "is_freq_digraph" in detailed[i]:
                        if detailed[i]["is_freq_digraph"]:
                            direct_freq_flights.append(fl)
                        else:
                            direct_non_freq_flights.append(fl)
                        continue

                    prev_k = str(detailed[i - 1].get("key", "")).lower()
                    curr_k = str(detailed[i].get("key", "")).lower()
                    if len(prev_k) == 1 and len(curr_k) == 1:
                        pair = prev_k + curr_k
                        digraph_flights.setdefault(pair, []).append(fl)

                if direct_freq_flights or direct_non_freq_flights:
                    if direct_freq_flights and direct_non_freq_flights:
                        f_mean = sum(direct_freq_flights) / len(direct_freq_flights)
                        nf_mean = sum(direct_non_freq_flights) / len(direct_non_freq_flights)
                        if f_mean >= nf_mean * 1.05 and len(detailed) >= 8:
                            score += 0.40
                        elif f_mean < nf_mean * 0.85:
                            score = max(0.0, score - 0.25)
                elif digraph_flights:
                    freq_avg = []
                    non_freq_avg = []
                    for pair, times in digraph_flights.items():
                        m_t = sum(times) / len(times)
                        if pair in frequent_digraphs:
                            freq_avg.append(m_t)
                        else:
                            non_freq_avg.append(m_t)

                    if freq_avg and non_freq_avg:
                        f_mean = sum(freq_avg) / len(freq_avg)
                        nf_mean = sum(non_freq_avg) / len(non_freq_avg)
                        if f_mean >= nf_mean * 1.05 and len(detailed) >= 8:
                            score += 0.40
                        elif f_mean < nf_mean * 0.85:
                            score = max(0.0, score - 0.25)

                if entropy < 0.15 and len(flight_times) >= 5:
                    score += 0.70
                elif entropy > 0.98 and len(flight_times) >= 8:
                    score += 0.50

            features["keystroke_score"] = min(1.0, max(0.0, score))

    # 4. Fare Kinematiği & Biyomekanik Titreme
    mouse_movements = telemetry.get("mouse_movements", [])
    if isinstance(mouse_movements, list):
        valid_moves = []
        for m in mouse_movements:
            if isinstance(m, dict) and "x" in m and "y" in m and "t" in m:
                try:
                    x = float(m["x"])
                    y = float(m["y"])
                    t = float(m["t"])
                    r = float(m.get("r", 0.0)) if "r" in m else 0.0
                    f = float(m.get("f", 0.0)) if "f" in m else 0.0
                    is_touch_src = str(m.get("source", "")) == "touch"
                    if not (
                        math.isnan(x)
                        or math.isnan(y)
                        or math.isnan(t)
                        or math.isinf(x)
                        or math.isinf(y)
                        or math.isinf(t)
                    ):
                        valid_moves.append({
                            "x": x,
                            "y": y,
                            "t": t,
                            "r": max(0.0, r) if not math.isnan(r) and not math.isinf(r) else 0.0,
                            "f": max(0.0, f) if not math.isnan(f) and not math.isinf(f) else 0.0,
                            "is_touch_source": is_touch_src,
                        })
                except (ValueError, TypeError):
                    continue

        features["mouse_points"] = len(valid_moves)

        # 4.1 Dokunmatik & Kapasitif Biyometri (Touch Biometrics)
        radii = [m["r"] for m in valid_moves if m.get("r", 0.0) > 0.0]
        forces = [m["f"] for m in valid_moves if m.get("f", 0.0) > 0.0]
        explicit_touch_moves = sum(1 for m in valid_moves if m.get("is_touch_source", False))

        if radii:
            features["touch_event_count"] = len(radii)
            avg_r = sum(radii) / len(radii)
            features["avg_touch_radius"] = avg_r
            features["touch_radius_var"] = sum((r_val - avg_r) ** 2 for r_val in radii) / len(radii)
        else:
            features["touch_event_count"] = explicit_touch_moves + touch_click_count

        if forces:
            features["avg_touch_force"] = sum(forces) / len(forces)

        if len(valid_moves) >= 3:
            # En fazla 300 nokta işleyerek CPU darboğazını engelle
            movements = sorted(valid_moves, key=lambda m: m["t"])[:300]

            # 4.2 Diferansiyel Eğrilik Analizi (κ(t) - AI & Bézier Bot Avcısı v0.9.2)
            if len(movements) >= 4:
                features.update(
                    _curvature_metrics(
                        [m["x"] for m in movements], [m["y"] for m in movements], [m["t"] for m in movements]
                    )
                )

            distances, dts, velocities = [], [], []
            start_x, start_y = movements[0]["x"], movements[0]["y"]
            end_x, end_y = movements[-1]["x"], movements[-1]["y"]
            displacement = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)

            for i in range(1, len(movements)):
                x1, y1, t1 = movements[i - 1]["x"], movements[i - 1]["y"], movements[i - 1]["t"]
                x2, y2, t2 = movements[i]["x"], movements[i]["y"], movements[i]["t"]

                d_dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                d_time = max(0.1, t2 - t1)

                distances.append(d_dist)
                dts.append(d_time)
                velocities.append(d_dist / d_time)

            total_dist = sum(distances)
            features["total_distance"] = total_dist
            features["straightness"] = (displacement / total_dist) if total_dist > 1e-4 else 1.0
            features["straightness"] = min(1.0, max(0.0, features["straightness"]))

            if velocities:
                avg_vel = sum(velocities) / len(velocities)
                max_vel = max(velocities)
                features["avg_velocity"] = avg_vel
                features["max_velocity"] = max_vel
                features["velocity_var"] = sum((v - avg_vel) ** 2 for v in velocities) / len(velocities)

                # dt varyansı (Zamanlama jitter'ı)
                avg_dt = sum(dts) / len(dts)
                features["dt_var"] = sum((dt - avg_dt) ** 2 for dt in dts) / len(dts)

                # Fitts Kanunu: Hedefe varırken yavaşlama oranı
                last_segment_count = max(1, int(len(velocities) * 0.25))
                terminal_avg_vel = sum(velocities[-last_segment_count:]) / last_segment_count
                features["terminal_decel_ratio"] = (terminal_avg_vel / max_vel) if max_vel > 1e-5 else 1.0

                # Alt-Hareket (Sub-movement Decomposition)
                peak_count = 0
                min_peak_thresh = 0.15 * max_vel if max_vel > 1e-5 else 0.0
                for i in range(1, len(velocities) - 1):
                    if velocities[i] > velocities[i - 1] and velocities[i] > velocities[i + 1]:
                        if velocities[i] >= min_peak_thresh:
                            peak_count += 1
                features["submovement_count"] = max(1, peak_count) if max_vel > 1e-5 else 0

                # Spektral Analiz (FFT & PSD)
                if len(velocities) >= 8:
                    try:
                        v_centered = [v - avg_vel for v in velocities]
                        fft_vals = np.fft.rfft(v_centered)
                        psd = np.abs(fft_vals) ** 2
                        ac_psd = psd[1:] if len(psd) > 1 else psd
                        total_power = float(np.sum(ac_psd))

                        if total_power > 1e-9:
                            max_power = float(np.max(ac_psd))
                            features["spectral_purity"] = float(max_power / total_power)

                            p = ac_psd / total_power
                            p_nonzero = p[p > 1e-12]
                            entropy = -float(np.sum(p_nonzero * np.log2(p_nonzero)))
                            max_entropy = float(np.log2(len(ac_psd))) if len(ac_psd) > 1 else 1.0
                            features["spectral_entropy"] = float(entropy / max_entropy) if max_entropy > 0 else 0.0
                    except Exception:
                        features["spectral_purity"] = 0.0
                        features["spectral_entropy"] = 1.0

                # İvme ve Jerk (Sarsıntı / Titreme)
                accelerations = []
                for i in range(1, len(velocities)):
                    accelerations.append((velocities[i] - velocities[i - 1]) / dts[i])

                if accelerations:
                    avg_acc = sum(accelerations) / len(accelerations)
                    features["avg_acceleration"] = avg_acc
                    features["acceleration_var"] = sum((a - avg_acc) ** 2 for a in accelerations) / len(accelerations)

                    jerks = []
                    for i in range(1, len(accelerations)):
                        jerks.append((accelerations[i] - accelerations[i - 1]) / dts[i + 1])

                    if jerks:
                        features["avg_jerk"] = sum(map(abs, jerks)) / len(jerks)

    return features


class MultimodalTokenizer:
    """
    v0.6.1 - Temporal Sequence Tokenizer (Late Fusion)
    Fare, Klavye ve Scroll olaylarını 1D-CNN (v0.6.2) modeline uygun
    Tensörlere çevirir.
    """

    def __init__(self, max_mouse_steps=60):
        self.max_mouse_steps = max_mouse_steps

    def tokenize_mouse(self, telemetry: dict) -> list:
        """
        Döner: list of lists (shape: 60x5) [dx, dy, dt, velocity, jerk]
        Veri eksikse: Zero Padding
        Veri fazlaysa: Truncation (Sondan kesilir)
        """
        mouse_movements = telemetry.get("mouse_movements", [])
        if not isinstance(mouse_movements, list):
            mouse_movements = []

        valid_moves = []
        for m in mouse_movements:
            if isinstance(m, dict) and "x" in m and "y" in m and "t" in m:
                try:
                    x = float(m["x"])
                    y = float(m["y"])
                    t = float(m["t"])
                    valid_moves.append({"x": x, "y": y, "t": t})
                except (ValueError, TypeError):
                    pass

        valid_moves = sorted(valid_moves, key=lambda m: m["t"])

        if len(valid_moves) > self.max_mouse_steps + 2:
            valid_moves = valid_moves[-(self.max_mouse_steps + 2) :]

        tensor = []
        if len(valid_moves) >= 3:
            distances, dts, velocities, accelerations = [], [], [], []
            for i in range(1, len(valid_moves)):
                dx = valid_moves[i]["x"] - valid_moves[i - 1]["x"]
                dy = valid_moves[i]["y"] - valid_moves[i - 1]["y"]
                dt = max(0.1, valid_moves[i]["t"] - valid_moves[i - 1]["t"])
                dist = math.sqrt(dx**2 + dy**2)
                vel = dist / dt
                distances.append((dx, dy, dt, vel))
                dts.append(dt)
                velocities.append(vel)

            for i in range(1, len(velocities)):
                acc = (velocities[i] - velocities[i - 1]) / dts[i]
                accelerations.append(acc)

            jerks = []
            for i in range(1, len(accelerations)):
                jerk = (accelerations[i] - accelerations[i - 1]) / dts[i + 1]
                jerks.append(jerk)

            for i in range(len(jerks)):
                dx, dy, dt, vel = distances[i + 2]
                tensor.append([dx, dy, dt, vel, jerks[i]])

        if len(tensor) > self.max_mouse_steps:
            tensor = tensor[-self.max_mouse_steps :]

        while len(tensor) < self.max_mouse_steps:
            tensor.append([0.0, 0.0, 0.0, 0.0, 0.0])

        return tensor

    def tokenize_static(self, telemetry: dict) -> list:
        """
        Döner: list (shape: 8)
        [key_count, avg_interval, interval_var, hold_time_avg, hold_time_var, scroll_count, avg_scroll_speed, scroll_accel_var]
        """
        keystrokes = telemetry.get("keystrokes", [])
        if not isinstance(keystrokes, list):
            keystrokes = []
        else:
            keystrokes = keystrokes[:150]  # DoS koruması

        valid_keys = [k for k in keystrokes if isinstance(k, dict) and "t" in k and "type" in k]
        sorted_keys = sorted(valid_keys, key=lambda k: k["t"])

        key_count = len([k for k in sorted_keys if k["type"] == "down"])

        downs = [k for k in sorted_keys if k["type"] == "down"]

        intervals = []
        for i in range(1, len(downs)):
            intervals.append(max(0.0, downs[i]["t"] - downs[i - 1]["t"]))

        avg_interval = sum(intervals) / len(intervals) if intervals else 0.0
        interval_var = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals) if intervals else 0.0

        # O(N) hold_times eşleştirmesi (deque.popleft() ile O(1) çıkarma, O(N^2) CPU kilitlenmesini engelle)
        from collections import defaultdict, deque

        pending_downs = defaultdict(deque)
        hold_times = []

        for k in sorted_keys:
            k_type = k.get("type")
            t_val = k.get("t", 0.0)
            k_code = k.get("code") or k.get("key") or "default"
            if k_type == "down":
                pending_downs[k_code].append(t_val)
            elif k_type == "up":
                if pending_downs[k_code]:
                    down_t = pending_downs[k_code].popleft()
                    if t_val >= down_t:
                        hold_times.append(t_val - down_t)
                elif pending_downs["default"]:
                    down_t = pending_downs["default"].popleft()
                    if t_val >= down_t:
                        hold_times.append(t_val - down_t)

        hold_time_avg = sum(hold_times) / len(hold_times) if hold_times else 0.0
        hold_time_var = sum((x - hold_time_avg) ** 2 for x in hold_times) / len(hold_times) if hold_times else 0.0

        scrolls = telemetry.get("scrolls", [])
        if not isinstance(scrolls, list):
            scrolls = []
        else:
            scrolls = scrolls[:150]  # DoS koruması

        valid_scrolls = [s for s in scrolls if isinstance(s, dict) and "t" in s and "y" in s]
        valid_scrolls = sorted(valid_scrolls, key=lambda s: s["t"])

        scroll_count = len(valid_scrolls)
        scroll_speeds = []
        for i in range(1, len(valid_scrolls)):
            dy = abs(valid_scrolls[i]["y"] - valid_scrolls[i - 1]["y"])
            dt = max(0.1, valid_scrolls[i]["t"] - valid_scrolls[i - 1]["t"])
            scroll_speeds.append(dy / dt)

        avg_scroll_speed = sum(scroll_speeds) / len(scroll_speeds) if scroll_speeds else 0.0

        scroll_accels = []
        for i in range(1, len(scroll_speeds)):
            dt = max(0.1, valid_scrolls[i + 1]["t"] - valid_scrolls[i]["t"])
            scroll_accels.append((scroll_speeds[i] - scroll_speeds[i - 1]) / dt)

        scroll_accel_var = (
            sum((a - (sum(scroll_accels) / len(scroll_accels))) ** 2 for a in scroll_accels) / len(scroll_accels)
            if scroll_accels
            else 0.0
        )

        return [
            float(key_count),
            float(avg_interval),
            float(interval_var),
            float(hold_time_avg),
            float(hold_time_var),
            float(scroll_count),
            float(avg_scroll_speed),
            float(scroll_accel_var),
        ]

    def fuse(self, telemetry: dict) -> dict:
        return {"mouse_tensor": self.tokenize_mouse(telemetry), "static_vector": self.tokenize_static(telemetry)}
