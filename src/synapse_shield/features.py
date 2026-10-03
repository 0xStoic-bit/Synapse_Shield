"""
Synapse Shield - Kinematic Feature Extractor v0.8.0 (Native Rust Core Accelerated)
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
        x_arr = np.asarray(x, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        t_arr = np.asarray(t, dtype=np.float64)
        n = min(len(x_arr), len(y_arr), len(t_arr))
        if n < 4:
            return {"curvature_score": 0.0, "mean_curvature": 0.0, "curvature_var": 0.0, "curvature_rate_var": 0.0}

        dt = np.maximum(np.diff(t_arr[:n]), 0.1)
        vx = np.diff(x_arr[:n]) / dt
        vy = np.diff(y_arr[:n]) / dt

        dt_a = (dt[1:] + dt[:-1]) * 0.5
        ax = np.diff(vx) / np.maximum(dt_a, 0.1)
        ay = np.diff(vy) / np.maximum(dt_a, 0.1)

        vx_s = vx[1:]
        vy_s = vy[1:]

        num = np.abs(vx_s * ay - vy_s * ax)
        v_sq = vx_s**2 + vy_s**2 + 1e-6
        denom = v_sq * np.sqrt(v_sq)
        kappa = num / denom

        mean_k = float(np.mean(kappa))
        var_k = float(np.var(kappa))
        d_k = np.diff(kappa) / np.maximum(dt_a[1:], 0.1) if len(kappa) > 1 else np.array([0.0])
        var_dk = float(np.var(d_k)) if len(d_k) > 0 else 0.0

        score = 0.10
        if mean_k < 1e-6 and var_k < 1e-7:
            score = 0.95
        elif var_dk < 1e-8 and var_k < 1e-4:
            score = 0.90
        elif var_dk > 5.0 or var_k > 10.0:
            score = 0.85

        return {
            "curvature_score": score,
            "mean_curvature": mean_k,
            "curvature_var": var_k,
            "curvature_rate_var": var_dk,
        }
    except Exception:
        return {"curvature_score": 0.0, "mean_curvature": 0.0, "curvature_var": 0.0, "curvature_rate_var": 0.0}


def extract_features(telemetry: dict[str, Any], force_python: bool = False) -> dict[str, Any]:
    # 0. High-Performance Native Rust Core (v0.8.0)
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
    }

    if not isinstance(telemetry, dict):
        return features

    # 1. Tarayıcı ve Ekran
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

    # 2. Sayaçlar
    scrolls = telemetry.get("scrolls", [])
    clicks = telemetry.get("clicks", [])
    features["scroll_count"] = len(scrolls) if isinstance(scrolls, list) else 0
    features["click_count"] = len(clicks) if isinstance(clicks, list) else 0

    # 3. Klavye Dinamikleri (Dwell & Flight Time Parity v0.9.2)
    keystrokes = telemetry.get("keystrokes", [])
    if isinstance(keystrokes, list) and len(keystrokes) > 0:
        keystrokes = keystrokes[:150]  # DoS koruması: en fazla 150 tuş vuruşu işle
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
                    detailed.append({"key": key_str, "down": t_val, "up": up_val})

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
                    b = min(7, int(f / 50.0))
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

                if dwell_times:
                    if features["avg_dwell_time"] < 15.0:
                        score += 0.75
                    elif features["dwell_time_var"] < 2.0 and len(dwell_times) >= 3:
                        score += 0.80

                # Digraph linguistic correlation check
                frequent_digraphs = {
                    "th", "er", "on", "an", "re", "he", "in", "ed", "nd", "ha",
                    "at", "en", "es", "of", "or", "nt", "ea", "ti", "to", "it",
                    "st", "io", "le", "is", "ou", "ar", "as", "de", "rt", "ve",
                    "la", "le", "ik", "ak", "el", "al", "ma", "me", "ba", "ka",
                }
                digraph_flights = {}
                for i in range(1, len(detailed)):
                    prev_k = str(detailed[i - 1]["key"]).lower()
                    curr_k = str(detailed[i]["key"]).lower()
                    if len(prev_k) == 1 and len(curr_k) == 1:
                        pair = prev_k + curr_k
                        fl = detailed[i]["down"] - detailed[i - 1]["down"]
                        if 0.0 < fl < 2000.0:
                            digraph_flights.setdefault(pair, []).append(fl)

                if digraph_flights:
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
                        })
                except (ValueError, TypeError):
                    continue

        features["mouse_points"] = len(valid_moves)

        # 4.1 Dokunmatik & Kapasitif Biyometri (Touch Biometrics)
        radii = [m["r"] for m in valid_moves if m.get("r", 0.0) > 0.0]
        forces = [m["f"] for m in valid_moves if m.get("f", 0.0) > 0.0]
        features["touch_event_count"] = len(radii)
        if radii:
            avg_r = sum(radii) / len(radii)
            features["avg_touch_radius"] = avg_r
            features["touch_radius_var"] = sum((r_val - avg_r) ** 2 for r_val in radii) / len(radii)
        if forces:
            features["avg_touch_force"] = sum(forces) / len(forces)

        if len(valid_moves) >= 3:
            # En fazla 300 nokta işleyerek CPU darboğazını engelle
            movements = sorted(valid_moves, key=lambda m: m["t"])[:300]

            # 4.2 Diferansiyel Eğrilik Analizi (κ(t) - AI & Bézier Bot Avcısı v0.9.2)
            if len(movements) >= 4:
                n_m = len(movements)
                vx_c, vy_c, dt_vc = [], [], []
                for i in range(1, n_m):
                    dt_c = max(0.1, movements[i]["t"] - movements[i - 1]["t"])
                    dt_vc.append(dt_c)
                    vx_c.append((movements[i]["x"] - movements[i - 1]["x"]) / dt_c)
                    vy_c.append((movements[i]["y"] - movements[i - 1]["y"]) / dt_c)

                dt_ac, ax_c, ay_c = [], [], []
                for i in range(1, len(vx_c)):
                    dta = (dt_vc[i] + dt_vc[i - 1]) * 0.5
                    dt_ac.append(dta)
                    ax_c.append((vx_c[i] - vx_c[i - 1]) / max(0.1, dta))
                    ay_c.append((vy_c[i] - vy_c[i - 1]) / max(0.1, dta))

                kappas = []
                for i in range(len(ax_c)):
                    vxs = vx_c[i + 1]
                    vys = vy_c[i + 1]
                    num = abs(vxs * ay_c[i] - vys * ax_c[i])
                    denom = (vxs * vxs + vys * vys + 1e-6) ** 1.5
                    kappas.append(num / denom)

                if kappas:
                    k_len = len(kappas)
                    mean_k = sum(kappas) / k_len
                    var_k = sum((k - mean_k) ** 2 for k in kappas) / k_len

                    d_kappas = []
                    for i in range(1, k_len):
                        dt_k = max(0.1, dt_ac[i])
                        d_kappas.append((kappas[i] - kappas[i - 1]) / dt_k)

                    if d_kappas:
                        dk_len = len(d_kappas)
                        mean_dk = sum(d_kappas) / dk_len
                        var_dk = sum((dk - mean_dk) ** 2 for dk in d_kappas) / dk_len
                    else:
                        var_dk = 0.0

                    c_score = 0.10
                    if mean_k < 1e-6 and var_k < 1e-7:
                        c_score = 0.95
                    elif var_dk < 1e-8 and var_k < 1e-4:
                        c_score = 0.90
                    elif var_dk > 5.0 or var_k > 10.0:
                        c_score = 0.85
                    else:
                        high_peaks = sum(1 for k in kappas if k > 0.1)
                        if high_peaks > (k_len // 2) and var_dk > 2.0:
                            c_score = 0.75
                        else:
                            c_score = 0.10

                    features["curvature_score"] = c_score
                    features["mean_curvature"] = mean_k
                    features["curvature_var"] = var_k
                    features["curvature_rate_var"] = var_dk

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
                # İnsan el hareketleri hedefe ulaşana kadar birden fazla yerel hız tepe noktası (çan profili) üretir.
                peak_count = 0
                min_peak_thresh = 0.15 * max_vel if max_vel > 1e-5 else 0.0
                for i in range(1, len(velocities) - 1):
                    if velocities[i] > velocities[i - 1] and velocities[i] > velocities[i + 1]:
                        if velocities[i] >= min_peak_thresh:
                            peak_count += 1
                features["submovement_count"] = max(1, peak_count) if max_vel > 1e-5 else 0

                # Spektral Analiz (FFT & PSD)
                # Hız serisindeki osilasyonların frekans spektrumunu inceler
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

        # O(N) hold_times eşleştirmesi (iç içe arama / O(N^2) CPU kilitlenmesini engelle)
        from collections import defaultdict

        pending_downs = defaultdict(list)
        hold_times = []

        for k in sorted_keys:
            k_type = k.get("type")
            t_val = k.get("t", 0.0)
            k_code = k.get("code") or k.get("key") or "default"
            if k_type == "down":
                pending_downs[k_code].append(t_val)
            elif k_type == "up":
                if pending_downs[k_code]:
                    down_t = pending_downs[k_code].pop(0)
                    if t_val >= down_t:
                        hold_times.append(t_val - down_t)
                elif pending_downs["default"]:
                    down_t = pending_downs["default"].pop(0)
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
