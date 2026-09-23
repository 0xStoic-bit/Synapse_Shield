use std::f64;

#[derive(Debug, Clone)]
pub struct MousePoint {
    pub x: f64,
    pub y: f64,
    pub t: f64,
}

#[derive(Debug, Clone)]
pub struct KeyPoint {
    pub t: f64,
}

#[derive(Debug, Clone)]
pub struct RawTelemetry {
    pub mouse_movements: Vec<MousePoint>,
    pub click_count: usize,
    pub scroll_count: usize,
    pub keystrokes: Vec<KeyPoint>,
    pub webdriver: bool,
    pub screen_width: f64,
    pub screen_height: f64,
    pub screen_valid: bool,
    pub plugins_length: i64,
    pub touch_supported: bool,
}

impl Default for RawTelemetry {
    fn default() -> Self {
        Self {
            mouse_movements: Vec::new(),
            click_count: 0,
            scroll_count: 0,
            keystrokes: Vec::new(),
            webdriver: false,
            screen_width: 1024.0,
            screen_height: 768.0,
            screen_valid: true,
            plugins_length: 1,
            touch_supported: false,
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

    // 2. Event counters
    feat.click_count = raw.click_count;
    feat.scroll_count = raw.scroll_count;

    // 3. Keyboard Dynamics
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
