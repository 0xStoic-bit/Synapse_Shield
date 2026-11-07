use std::f64;
use crate::curvature::evaluate_curvature_naturalness;
use crate::keystrokes::{evaluate_keystroke_dynamics, DetailedKeystroke};

#[derive(Debug, Clone)]
pub struct MousePoint {
    pub x: f64,
    pub y: f64,
    pub t: f64,
    pub r: f64,
    pub f: f64,
    pub is_touch_source: bool,
}

#[derive(Debug, Clone)]
pub struct KeyPoint {
    pub t: f64,
}

#[derive(Debug, Clone)]
pub struct RawTelemetry {
    pub mouse_movements: Vec<MousePoint>,
    pub click_count: usize,
    pub touch_click_count: usize,
    pub tap_durations: Vec<f64>,
    pub scroll_count: usize,
    pub keystrokes: Vec<KeyPoint>,
    pub detailed_keystrokes: Vec<DetailedKeystroke>,
    pub webdriver: bool,
    pub screen_width: f64,
    pub screen_height: f64,
    pub screen_valid: bool,
    pub plugins_length: i64,
    pub touch_supported: bool,
    pub max_touch_points: i64,
    pub device_pixel_ratio: f64,
    pub motion_variance: f64,
    pub webgl_renderer: String,
}

impl Default for RawTelemetry {
    fn default() -> Self {
        Self {
            mouse_movements: Vec::new(),
            click_count: 0,
            touch_click_count: 0,
            tap_durations: Vec::new(),
            scroll_count: 0,
            keystrokes: Vec::new(),
            detailed_keystrokes: Vec::new(),
            webdriver: false,
            screen_width: 1024.0,
            screen_height: 768.0,
            screen_valid: true,
            plugins_length: 1,
            touch_supported: false,
            max_touch_points: 0,
            device_pixel_ratio: 1.0,
            motion_variance: 0.0,
            webgl_renderer: String::new(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ExtractedFeatures {
    pub mouse_points: usize,
    pub total_distance: f64,
    pub straightness: f64,
    pub avg_velocity: f64,
    pub max_velocity: f64,
    pub velocity_var: f64,
    pub avg_acceleration: f64,
    pub acceleration_var: f64,
    pub avg_jerk: f64,
    pub dt_var: f64,
    pub click_count: usize,
    pub key_count: usize,
    pub key_interval_avg: f64,
    pub key_interval_var: f64,
    pub webdriver: bool,
    pub screen_valid: bool,
    pub scroll_count: usize,
    pub terminal_decel_ratio: f64,
    pub plugins_length: i64,
    pub touch_supported: bool,
    pub screen_width: f64,
    pub spectral_purity: f64,
    pub spectral_entropy: f64,
    pub submovement_count: usize,
    pub max_touch_points: i64,
    pub avg_touch_radius: f64,
    pub touch_radius_var: f64,
    pub avg_touch_force: f64,
    pub touch_event_count: usize,
    // --- v0.9.2 Upgrades ---
    pub curvature_score: f64,
    pub mean_curvature: f64,
    pub curvature_var: f64,
    pub curvature_rate_var: f64,
    pub avg_dwell_time: f64,
    pub dwell_time_var: f64,
    pub avg_flight_time: f64,
    pub flight_time_var: f64,
    pub digraph_entropy: f64,
    pub keystroke_score: f64,
    // --- Mobile SDK v2.0 Biometrics ---
    pub tap_count: usize,
    pub avg_tap_duration: f64,
    pub tap_duration_var: f64,
    pub device_pixel_ratio: f64,
    pub motion_variance: f64,
    pub is_mobile_gpu_mismatch: bool,
}

impl Default for ExtractedFeatures {
    fn default() -> Self {
        Self {
            mouse_points: 0,
            total_distance: 0.0,
            straightness: 1.0,
            avg_velocity: 0.0,
            max_velocity: 0.0,
            velocity_var: 0.0,
            avg_acceleration: 0.0,
            acceleration_var: 0.0,
            avg_jerk: 0.0,
            dt_var: 0.0,
            click_count: 0,
            key_count: 0,
            key_interval_avg: 0.0,
            key_interval_var: 0.0,
            webdriver: false,
            screen_valid: true,
            scroll_count: 0,
            terminal_decel_ratio: 1.0,
            plugins_length: 1,
            touch_supported: false,
            screen_width: 1024.0,
            spectral_purity: 0.0,
            spectral_entropy: 1.0,
            submovement_count: 0,
            max_touch_points: 0,
            avg_touch_radius: 0.0,
            touch_radius_var: 0.0,
            avg_touch_force: 0.0,
            touch_event_count: 0,
            curvature_score: 0.0,
            mean_curvature: 0.0,
            curvature_var: 0.0,
            curvature_rate_var: 0.0,
            avg_dwell_time: 0.0,
            dwell_time_var: 0.0,
            avg_flight_time: 0.0,
            flight_time_var: 0.0,
            digraph_entropy: 0.5,
            keystroke_score: 0.0,
            tap_count: 0,
            avg_tap_duration: 0.0,
            tap_duration_var: 0.0,
            device_pixel_ratio: 1.0,
            motion_variance: 0.0,
            is_mobile_gpu_mismatch: false,
        }
    }
}

pub fn compute_kinematics(raw: &RawTelemetry) -> ExtractedFeatures {
    let mut feat = ExtractedFeatures::default();

    // 1. Browser & Screen metadata
    feat.webdriver = raw.webdriver;
    feat.screen_width = raw.screen_width;
    feat.screen_valid = raw.screen_valid;
    feat.plugins_length = raw.plugins_length;
    feat.touch_supported = raw.touch_supported;
    feat.max_touch_points = raw.max_touch_points;
    feat.device_pixel_ratio = raw.device_pixel_ratio;
    feat.motion_variance = raw.motion_variance;

    if raw.touch_supported && raw.screen_width > 0.0 && raw.screen_width < 768.0 && !raw.webgl_renderer.is_empty() {
        let renderer_lower = raw.webgl_renderer.to_lowercase();
        const DESKTOP_OR_EMULATOR_GPUS: &[&str] = &[
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
        ];
        if DESKTOP_OR_EMULATOR_GPUS.iter().any(|&sig| renderer_lower.contains(sig)) {
            feat.is_mobile_gpu_mismatch = true;
        }
    }

    // 1.5 Touch & Capacitive Biometrics
    let mut touch_radii = Vec::new();
    let mut touch_forces = Vec::new();
    let mut explicit_touch_moves = 0usize;
    for m in &raw.mouse_movements {
        if m.r > 0.0 {
            touch_radii.push(m.r);
        }
        if m.f > 0.0 {
            touch_forces.push(m.f);
        }
        if m.is_touch_source {
            explicit_touch_moves += 1;
        }
    }
    if !touch_radii.is_empty() {
        feat.touch_event_count = touch_radii.len();
        let count = touch_radii.len() as f64;
        let avg_r: f64 = touch_radii.iter().sum::<f64>() / count;
        let var_r: f64 = touch_radii.iter().map(|&r| (r - avg_r).powi(2)).sum::<f64>() / count;
        feat.avg_touch_radius = avg_r;
        feat.touch_radius_var = var_r;
    } else {
        feat.touch_event_count = explicit_touch_moves + raw.touch_click_count;
    }
    if !touch_forces.is_empty() {
        let count = touch_forces.len() as f64;
        feat.avg_touch_force = touch_forces.iter().sum::<f64>() / count;
    }

    // 1.6 Tap Hold Time Biometrics (touchend - touchstart duration)
    feat.tap_count = raw.tap_durations.len();
    if !raw.tap_durations.is_empty() {
        let count = raw.tap_durations.len() as f64;
        let avg_tap: f64 = raw.tap_durations.iter().sum::<f64>() / count;
        let var_tap: f64 = raw.tap_durations.iter().map(|&d| (d - avg_tap).powi(2)).sum::<f64>() / count;
        feat.avg_tap_duration = avg_tap;
        feat.tap_duration_var = var_tap;
    }

    // 2. Event counters
    feat.click_count = raw.click_count;
    feat.scroll_count = raw.scroll_count;

    // 3. Keyboard Dynamics (Dwell & Flight Time & Digraph Entropy v0.9.2)
    if !raw.detailed_keystrokes.is_empty() {
        let km = evaluate_keystroke_dynamics(&raw.detailed_keystrokes);
        feat.key_count = km.key_count;
        feat.avg_dwell_time = km.avg_dwell_time;
        feat.dwell_time_var = km.dwell_time_var;
        feat.avg_flight_time = km.avg_flight_time;
        feat.flight_time_var = km.flight_time_var;
        feat.digraph_entropy = km.digraph_entropy;
        feat.keystroke_score = km.keystroke_score;
        feat.key_interval_avg = km.avg_flight_time;
        feat.key_interval_var = km.flight_time_var;
    } else {
        let key_len = raw.keystrokes.len();
        feat.key_count = key_len;
        if key_len > 1 {
            let mut sorted_keys = raw.keystrokes.clone();
            sorted_keys.sort_by(|a, b| a.t.partial_cmp(&b.t).unwrap_or(std::cmp::Ordering::Equal));

            let mut intervals = Vec::with_capacity(sorted_keys.len() - 1);
            for i in 1..sorted_keys.len() {
                let t_curr = sorted_keys[i].t;
                let t_prev = sorted_keys[i - 1].t;
                if t_curr > t_prev {
                    intervals.push(t_curr - t_prev);
                }
            }

            if !intervals.is_empty() {
                let count = intervals.len() as f64;
                let avg_int: f64 = intervals.iter().sum::<f64>() / count;
                let var_int: f64 = intervals.iter().map(|&x| (x - avg_int).powi(2)).sum::<f64>() / count;
                feat.key_interval_avg = avg_int;
                feat.key_interval_var = var_int;
                feat.avg_flight_time = avg_int;
                feat.flight_time_var = var_int;
                if var_int < 2.0 && intervals.len() >= 3 {
                    feat.keystroke_score = 0.85;
                }
            }
        }
    }

    // 4. Mouse Movement Kinematics
    let move_len = raw.mouse_movements.len();
    feat.mouse_points = move_len;

    if move_len >= 3 {
        // En fazla 300 nokta al (DoS koruması)
        let mut moves = raw.mouse_movements.clone();
        moves.sort_by(|a, b| a.t.partial_cmp(&b.t).unwrap_or(std::cmp::Ordering::Equal));
        if moves.len() > 300 {
            moves.truncate(300);
        }

        let n = moves.len();
        if n >= 4 {
            let xs: Vec<f64> = moves.iter().map(|m| m.x).collect();
            let ys: Vec<f64> = moves.iter().map(|m| m.y).collect();
            let ts: Vec<f64> = moves.iter().map(|m| m.t).collect();
            let cm = evaluate_curvature_naturalness(&xs, &ys, &ts);
            feat.curvature_score = cm.curvature_score;
            feat.mean_curvature = cm.mean_curvature;
            feat.curvature_var = cm.curvature_var;
            feat.curvature_rate_var = cm.curvature_rate_var;
        }

        let start_x = moves[0].x;
        let start_y = moves[0].y;
        let end_x = moves[n - 1].x;
        let end_y = moves[n - 1].y;
        let displacement = ((end_x - start_x).powi(2) + (end_y - start_y).powi(2)).sqrt();

        let mut distances = Vec::with_capacity(n - 1);
        let mut dts = Vec::with_capacity(n - 1);
        let mut velocities = Vec::with_capacity(n - 1);

        for i in 1..n {
            let x1 = moves[i - 1].x;
            let y1 = moves[i - 1].y;
            let t1 = moves[i - 1].t;

            let x2 = moves[i].x;
            let y2 = moves[i].y;
            let t2 = moves[i].t;

            let d_dist = ((x2 - x1).powi(2) + (y2 - y1).powi(2)).sqrt();
            let d_time = (t2 - t1).max(0.1);

            distances.push(d_dist);
            dts.push(d_time);
            velocities.push(d_dist / d_time);
        }

        let total_dist: f64 = distances.iter().sum();
        feat.total_distance = total_dist;

        if total_dist > 1e-4 {
            feat.straightness = (displacement / total_dist).clamp(0.0, 1.0);
        } else {
            feat.straightness = 1.0;
        }

        if !velocities.is_empty() {
            let vel_count = velocities.len() as f64;
            let avg_vel: f64 = velocities.iter().sum::<f64>() / vel_count;
            let mut max_vel: f64 = 0.0;
            for &v in &velocities {
                if v > max_vel {
                    max_vel = v;
                }
            }

            feat.avg_velocity = avg_vel;
            feat.max_velocity = max_vel;
            feat.velocity_var = velocities.iter().map(|&v| (v - avg_vel).powi(2)).sum::<f64>() / vel_count;

            // dt varyansı
            let avg_dt: f64 = dts.iter().sum::<f64>() / (dts.len() as f64);
            feat.dt_var = dts.iter().map(|&dt| (dt - avg_dt).powi(2)).sum::<f64>() / (dts.len() as f64);

            // Fitts Kanunu: Terminal Deceleration
            let last_count = (velocities.len() / 4).max(1);
            let start_idx = velocities.len() - last_count;
            let terminal_avg: f64 = velocities[start_idx..].iter().sum::<f64>() / (last_count as f64);
            if max_vel > 1e-5 {
                feat.terminal_decel_ratio = terminal_avg / max_vel;
            } else {
                feat.terminal_decel_ratio = 1.0;
            }

            // Submovement count (local peaks >= 15% max_vel)
            let mut peak_count = 0;
            let min_peak_thresh = if max_vel > 1e-5 { 0.15 * max_vel } else { 0.0 };
            for i in 1..velocities.len().saturating_sub(1) {
                if velocities[i] > velocities[i - 1] && velocities[i] > velocities[i + 1] {
                    if velocities[i] >= min_peak_thresh {
                        peak_count += 1;
                    }
                }
            }
            feat.submovement_count = if max_vel > 1e-5 { peak_count.max(1) } else { 0 };

            // Spectral Analysis (Fast Discrete Fourier Transform & PSD)
            if velocities.len() >= 8 {
                compute_spectral_features(&velocities, avg_vel, &mut feat);
            }

            // Accelerations & Jerk
            if velocities.len() >= 2 {
                let mut accelerations = Vec::with_capacity(velocities.len() - 1);
                for i in 1..velocities.len() {
                    accelerations.push((velocities[i] - velocities[i - 1]) / dts[i]);
                }

                let acc_count = accelerations.len() as f64;
                let avg_acc: f64 = accelerations.iter().sum::<f64>() / acc_count;
                feat.avg_acceleration = avg_acc;
                feat.acceleration_var = accelerations.iter().map(|&a| (a - avg_acc).powi(2)).sum::<f64>() / acc_count;

                if accelerations.len() >= 2 {
                    let mut jerks = Vec::with_capacity(accelerations.len() - 1);
                    for i in 1..accelerations.len() {
                        jerks.push((accelerations[i] - accelerations[i - 1]) / dts[i + 1]);
                    }

                    if !jerks.is_empty() {
                        let jerk_sum: f64 = jerks.iter().map(|&j| j.abs()).sum();
                        feat.avg_jerk = jerk_sum / (jerks.len() as f64);
                    }
                }
            }
        }
    }

    feat
}

fn compute_spectral_features(velocities: &[f64], avg_vel: f64, feat: &mut ExtractedFeatures) {
    let n = velocities.len();
    let num_freqs = n / 2 + 1;
    let mut psd = Vec::with_capacity(num_freqs);

    let v_centered: Vec<f64> = velocities.iter().map(|&v| v - avg_vel).collect();

    // RFFT via direct discrete evaluation (optimal for N < 300)
    for k in 0..num_freqs {
        let mut re = 0.0;
        let mut im = 0.0;
        let angle_factor = 2.0 * f64::consts::PI * (k as f64) / (n as f64);
        for (t, &val) in v_centered.iter().enumerate() {
            let angle = angle_factor * (t as f64);
            re += val * angle.cos();
            im -= val * angle.sin();
        }
        psd.push(re * re + im * im);
    }

    let ac_psd = if psd.len() > 1 { &psd[1..] } else { &psd[..] };
    let total_power: f64 = ac_psd.iter().sum();

    if total_power > 1e-9 {
        let mut max_power: f64 = 0.0;
        for &p in ac_psd {
            if p > max_power {
                max_power = p;
            }
        }
        feat.spectral_purity = max_power / total_power;

        let mut entropy = 0.0;
        for &val in ac_psd {
            let p = val / total_power;
            if p > 1e-12 {
                entropy -= p * p.log2();
            }
        }

        let max_entropy = if ac_psd.len() > 1 {
            (ac_psd.len() as f64).log2()
        } else {
            1.0
        };

        feat.spectral_entropy = if max_entropy > 0.0 {
            entropy / max_entropy
        } else {
            0.0
        };
    } else {
        feat.spectral_purity = 0.0;
        feat.spectral_entropy = 1.0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pt(x: f64, y: f64, t: f64) -> MousePoint {
        MousePoint { x, y, t, r: 0.0, f: 0.0, is_touch_source: false }
    }

    fn uniform_line(n: usize) -> Vec<MousePoint> {
        (0..n).map(|i| pt(i as f64 * 10.0, 0.0, i as f64 * 10.0)).collect()
    }

    #[test]
    fn empty_telemetry_yields_defaults() {
        let f = compute_kinematics(&RawTelemetry::default());
        assert_eq!(f.mouse_points, 0);
        assert_eq!(f.key_count, 0);
        assert_eq!(f.straightness, 1.0);
        assert_eq!(f.submovement_count, 0);
        assert!(!f.is_mobile_gpu_mismatch);
    }

    #[test]
    fn uniform_straight_line_kinematics() {
        let raw = RawTelemetry { mouse_movements: uniform_line(12), ..Default::default() };
        let f = compute_kinematics(&raw);
        assert_eq!(f.mouse_points, 12);
        assert!((f.total_distance - 110.0).abs() < 1e-9);
        assert!((f.straightness - 1.0).abs() < 1e-12);
        assert!((f.avg_velocity - 1.0).abs() < 1e-12, "10 px / 10 ms = 1 px/ms");
        assert!(f.velocity_var < 1e-12);
        assert!(f.avg_jerk.abs() < 1e-12, "constant velocity has zero jerk");
        assert!((f.terminal_decel_ratio - 1.0).abs() < 1e-12, "no terminal deceleration");
        assert_eq!(f.submovement_count, 1);
        assert_eq!(f.curvature_score, 0.95, "straight line flagged by curvature engine");
    }

    #[test]
    fn out_of_order_points_are_sorted_by_time() {
        let ordered = uniform_line(10);
        let mut shuffled = ordered.clone();
        shuffled.swap(1, 7);
        shuffled.swap(3, 9);
        shuffled.reverse();
        let a = compute_kinematics(&RawTelemetry { mouse_movements: ordered, ..Default::default() });
        let b = compute_kinematics(&RawTelemetry { mouse_movements: shuffled, ..Default::default() });
        assert_eq!(a.total_distance, b.total_distance);
        assert_eq!(a.avg_velocity, b.avg_velocity);
        assert_eq!(a.straightness, b.straightness);
    }

    #[test]
    fn trajectory_is_capped_at_300_points() {
        let raw = RawTelemetry { mouse_movements: uniform_line(1_000), ..Default::default() };
        let f = compute_kinematics(&raw);
        assert_eq!(f.mouse_points, 1_000, "reported count is the raw count");
        assert!((f.total_distance - 2_990.0).abs() < 1e-9, "distance computed over first 300 points only");
    }

    #[test]
    fn decelerating_approach_lowers_terminal_ratio() {
        // Fast ballistic phase then slow corrective approach (Fitts's law profile).
        let mut moves = Vec::new();
        let mut x = 0.0;
        for i in 0..20 {
            let step = if i < 15 { 20.0 } else { 2.0 };
            moves.push(pt(x, 0.0, i as f64 * 10.0));
            x += step;
        }
        let f = compute_kinematics(&RawTelemetry { mouse_movements: moves, ..Default::default() });
        assert!(f.terminal_decel_ratio < 0.5, "ratio {}", f.terminal_decel_ratio);
    }

    #[test]
    fn coincident_timestamps_stay_finite() {
        let moves = vec![pt(0.0, 0.0, 5.0), pt(3.0, 4.0, 5.0), pt(6.0, 8.0, 5.0), pt(9.0, 12.0, 5.0)];
        let f = compute_kinematics(&RawTelemetry { mouse_movements: moves, ..Default::default() });
        for v in [f.avg_velocity, f.max_velocity, f.avg_acceleration, f.avg_jerk, f.velocity_var] {
            assert!(v.is_finite());
        }
    }

    #[test]
    fn mobile_viewport_with_desktop_or_emulator_gpu_is_flagged() {
        let base = RawTelemetry { touch_supported: true, screen_width: 390.0, ..Default::default() };
        for gpu in ["Google SwiftShader", "ANGLE (NVIDIA GeForce RTX 3080)", "llvmpipe (LLVM 15)"] {
            let f = compute_kinematics(&RawTelemetry { webgl_renderer: gpu.into(), ..base.clone() });
            assert!(f.is_mobile_gpu_mismatch, "{gpu} not flagged");
        }
        for gpu in ["Apple GPU", "Adreno (TM) 740", "Mali-G78"] {
            let f = compute_kinematics(&RawTelemetry { webgl_renderer: gpu.into(), ..base.clone() });
            assert!(!f.is_mobile_gpu_mismatch, "{gpu} wrongly flagged");
        }
        // Desktop viewport and non-touch devices are never flagged.
        let desktop = RawTelemetry { screen_width: 1440.0, webgl_renderer: "NVIDIA".into(), ..base.clone() };
        assert!(!compute_kinematics(&desktop).is_mobile_gpu_mismatch);
        let no_touch = RawTelemetry { touch_supported: false, webgl_renderer: "SwiftShader".into(), ..base };
        assert!(!compute_kinematics(&no_touch).is_mobile_gpu_mismatch);
    }

    #[test]
    fn capacitive_touch_statistics() {
        let mut moves = Vec::new();
        for (i, (r, f)) in [(10.0, 0.5), (12.0, 0.7), (14.0, 0.0)].iter().enumerate() {
            moves.push(MousePoint { x: i as f64, y: 0.0, t: i as f64 * 16.0, r: *r, f: *f, is_touch_source: true });
        }
        let feat = compute_kinematics(&RawTelemetry { mouse_movements: moves, ..Default::default() });
        assert_eq!(feat.touch_event_count, 3);
        assert!((feat.avg_touch_radius - 12.0).abs() < 1e-12);
        assert!((feat.touch_radius_var - 8.0 / 3.0).abs() < 1e-12);
        assert!((feat.avg_touch_force - 0.6).abs() < 1e-12, "zero force samples are excluded");
    }

    #[test]
    fn touch_events_without_radius_still_counted() {
        let moves = vec![MousePoint { x: 0.0, y: 0.0, t: 0.0, r: 0.0, f: 0.0, is_touch_source: true }];
        let raw = RawTelemetry { mouse_movements: moves, touch_click_count: 2, ..Default::default() };
        assert_eq!(compute_kinematics(&raw).touch_event_count, 3);
    }

    #[test]
    fn tap_duration_statistics() {
        let raw = RawTelemetry { tap_durations: vec![80.0, 100.0, 120.0], ..Default::default() };
        let f = compute_kinematics(&raw);
        assert_eq!(f.tap_count, 3);
        assert!((f.avg_tap_duration - 100.0).abs() < 1e-12);
        assert!((f.tap_duration_var - 800.0 / 3.0).abs() < 1e-9);
    }

    #[test]
    fn legacy_timestamp_keystrokes_detect_fixed_intervals() {
        let keys = (0..6).map(|i| KeyPoint { t: i as f64 * 100.0 }).collect();
        let f = compute_kinematics(&RawTelemetry { keystrokes: keys, ..Default::default() });
        assert_eq!(f.key_count, 6);
        assert!((f.key_interval_avg - 100.0).abs() < 1e-12);
        assert_eq!(f.keystroke_score, 0.85);
    }

    #[test]
    fn detailed_keystrokes_take_precedence_over_legacy() {
        let detailed = vec![
            DetailedKeystroke { key: "masked".into(), down: 0.0, up: Some(90.0), is_freq_digraph: None },
            DetailedKeystroke { key: "masked".into(), down: 250.0, up: Some(330.0), is_freq_digraph: None },
        ];
        let legacy = (0..6).map(|i| KeyPoint { t: i as f64 * 100.0 }).collect();
        let raw = RawTelemetry { detailed_keystrokes: detailed, keystrokes: legacy, ..Default::default() };
        let f = compute_kinematics(&raw);
        assert_eq!(f.key_count, 2);
        assert!((f.avg_dwell_time - 85.0).abs() < 1e-12);
        assert_eq!(f.key_interval_avg, f.avg_flight_time);
    }

    #[test]
    fn browser_metadata_is_passed_through() {
        let raw = RawTelemetry {
            webdriver: true,
            plugins_length: 0,
            max_touch_points: 5,
            device_pixel_ratio: 3.0,
            motion_variance: 0.42,
            click_count: 4,
            scroll_count: 7,
            ..Default::default()
        };
        let f = compute_kinematics(&raw);
        assert!(f.webdriver);
        assert_eq!(f.plugins_length, 0);
        assert_eq!(f.max_touch_points, 5);
        assert_eq!(f.device_pixel_ratio, 3.0);
        assert_eq!(f.motion_variance, 0.42);
        assert_eq!(f.click_count, 4);
        assert_eq!(f.scroll_count, 7);
    }
}
