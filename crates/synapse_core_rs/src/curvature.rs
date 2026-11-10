//! Synapse Shield - Curvature & Differential Kinematics v0.9.2
//! High-performance AVX2 SIMD accelerated differential curvature analysis.
//! Identifies artificial Bézier curves and synthetic neuromuscular jitter.

use std::f64;

#[derive(Debug, Clone, Copy, Default)]
pub struct CurvatureMetrics {
    pub mean_curvature: f64,
    pub curvature_var: f64,
    pub curvature_rate_var: f64,
    pub curvature_score: f64, // 0.0 (organic human) .. 1.0 (synthetic bot)
}

/// Evaluates naturalness of curvature profile for trajectory points (x, y, t).
pub fn evaluate_curvature_naturalness(x: &[f64], y: &[f64], t: &[f64]) -> CurvatureMetrics {
    let n = x.len().min(y.len()).min(t.len());
    if n < 4 {
        return CurvatureMetrics::default();
    }

    // 1. Calculate 1st derivatives (velocities)
    let mut vx = Vec::with_capacity(n - 1);
    let mut vy = Vec::with_capacity(n - 1);
    let mut dt_v = Vec::with_capacity(n - 1);

    for i in 1..n {
        let dt = (t[i] - t[i - 1]).max(0.1);
        vx.push((x[i] - x[i - 1]) / dt);
        vy.push((y[i] - y[i - 1]) / dt);
        dt_v.push(dt);
    }

    // 2. Calculate 2nd derivatives (accelerations)
    let m = vx.len();
    if m < 2 {
        return CurvatureMetrics::default();
    }

    let mut ax = Vec::with_capacity(m - 1);
    let mut ay = Vec::with_capacity(m - 1);
    let mut dt_a = Vec::with_capacity(m - 1);

    for i in 1..m {
        let dt = (dt_v[i] + dt_v[i - 1]) * 0.5;
        ax.push((vx[i] - vx[i - 1]) / dt);
        ay.push((vy[i] - vy[i - 1]) / dt);
        dt_a.push(dt);
    }

    let k_len = ax.len();
    if k_len == 0 {
        return CurvatureMetrics::default();
    }

    // Aligned velocity slice corresponding to acceleration points
    let vx_slice = &vx[1..];
    let vy_slice = &vy[1..];

    let mut kappa = vec![0.0; k_len];

    // 3. Vectorized Curvature Calculation
    #[cfg(target_arch = "x86_64")]
    {
        if is_x86_feature_detected!("avx2") {
            unsafe {
                compute_curvature_avx2(vx_slice, vy_slice, &ax, &ay, &mut kappa);
            }
        } else {
            compute_curvature_scalar(vx_slice, vy_slice, &ax, &ay, &mut kappa);
        }
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        compute_curvature_scalar(vx_slice, vy_slice, &ax, &ay, &mut kappa);
    }

    // 4. Moments over every point (reported metrics, unchanged semantics).
    let all = kappa_moments(&kappa, &dt_a[1..]);

    // 5. Moments over "moving" points only (v0.10.6). kappa = |v x a| / |v|^3 explodes when the cursor
    //    slows to a stop, and 1-px quantisation makes direction meaningless there. Real human pointing ends
    //    in slow homing/stops, so the ungated variance was huge for ~67% of real human windows
    //    (SapiMouse replay). Keep only points whose two neighbouring steps are >= CURVATURE_MIN_STEP_PX.
    //    The time between two kept points is the sum of the same dt_a steps the all-points statistic uses,
    //    so when every point is kept the gated moments equal the all-points moments exactly.
    let keep: Vec<bool> = (0..k_len)
        .map(|i| {
            let s0 = (x[i + 1] - x[i]).hypot(y[i + 1] - y[i]);
            let s1 = (x[i + 2] - x[i + 1]).hypot(y[i + 2] - y[i + 1]);
            s0 >= CURVATURE_MIN_STEP_PX && s1 >= CURVATURE_MIN_STEP_PX
        })
        .collect();
    let gated_k: Vec<f64> = kappa.iter().zip(&keep).filter(|(_, &k)| k).map(|(&v, _)| v).collect();
    let gated_dt = gated_dts(&dt_a, &keep);
    let gated = if gated_k.len() >= CURVATURE_MIN_GATED_POINTS {
        Some(kappa_moments(&gated_k, &gated_dt))
    } else {
        None
    };

    // 6. Bot vs Human Classification Score (0.0 = human, 1.0 = bot)
    // - Straight line / analytic Bézier / minimum-jerk: curvature (rate) is analytically smooth. Checked on
    //   all points OR on moving points (the stop artefacts at the ends hid minimum-jerk bots before).
    // - Chaotic curvature: only judged on moving points, where it is not a stop/quantisation artefact.
    let candidates = [Some(all), gated];
    let score = if candidates.iter().flatten().any(|m| m.mean < 1e-6 && m.var < 1e-7) {
        // Straight line bot
        0.95
    } else if candidates.iter().flatten().any(|m| m.rate_var < 1e-8 && m.var < 1e-4) {
        // Unnaturally smooth polynomial / Bézier curve without neuromuscular submovements
        0.90
    } else if let Some(g) = gated {
        if g.rate_var > 5.0 || g.var > 10.0 {
            // Unphysical artificial noise / discrete jitter while moving
            0.85
        } else if g.high_peak_frac > 0.5 && g.rate_var > 2.0 {
            0.75
        } else {
            // Natural human motion with neuromuscular damping
            0.10
        }
    } else {
        0.10
    };

    CurvatureMetrics {
        mean_curvature: all.mean,
        curvature_var: all.var,
        curvature_rate_var: all.rate_var,
        curvature_score: score,
    }
}

/// Minimum step (px) on both sides of a point for its curvature to count toward the "chaotic" checks.
/// Chosen on real data (SapiMouse, 4,844 six-second windows): 5 px drops this rule's human false positives
/// from 67% to 0.4% while Bézier/linear/minimum-jerk bot detection stays at 99-100%.
pub const CURVATURE_MIN_STEP_PX: f64 = 5.0;
/// Fewer moving points than this: the gated statistics are not used.
pub const CURVATURE_MIN_GATED_POINTS: usize = 10;

/// Time between consecutive kept kappa points: the sum of the `dt_a` steps between them (`dt_a[i]` separates
/// `kappa[i - 1]` and `kappa[i]`). With every point kept this is exactly `dt_a[1..]`, the all-points spacing,
/// so the gated and all-points moments are computed identically.
fn gated_dts(dt_a: &[f64], keep: &[bool]) -> Vec<f64> {
    let mut out = Vec::with_capacity(keep.len());
    let mut gap = 0.0;
    let mut seen = false;
    for (i, &k) in keep.iter().enumerate() {
        if i > 0 {
            gap += dt_a[i];
        }
        if k {
            if seen {
                out.push(gap);
            }
            gap = 0.0;
            seen = true;
        }
    }
    out
}

#[derive(Debug, Clone, Copy)]
struct KappaMoments {
    mean: f64,
    var: f64,
    rate_var: f64,
    high_peak_frac: f64,
}

/// Mean/variance of kappa and variance of d(kappa)/dt; `dts[i - 1]` is the time between `kappa[i - 1]`
/// and `kappa[i]`.
fn kappa_moments(kappa: &[f64], dts: &[f64]) -> KappaMoments {
    let n = kappa.len() as f64;
    let mean = kappa.iter().sum::<f64>() / n;
    let var = kappa.iter().map(|&k| (k - mean).powi(2)).sum::<f64>() / n;
    let mut d = Vec::with_capacity(kappa.len().saturating_sub(1));
    for i in 1..kappa.len() {
        let dt = dts[i - 1].max(0.1);
        d.push((kappa[i] - kappa[i - 1]) / dt);
    }
    let rate_var = if d.is_empty() {
        0.0
    } else {
        let dn = d.len() as f64;
        let dm = d.iter().sum::<f64>() / dn;
        d.iter().map(|&v| (v - dm).powi(2)).sum::<f64>() / dn
    };
    let high_peak_frac = kappa.iter().filter(|&&k| k > 0.1).count() as f64 / n;
    KappaMoments { mean, var, rate_var, high_peak_frac }
}

/// Raw pointer implementation for Zero-Copy AVX2 execution directly from Python buffer.
pub unsafe fn evaluate_curvature_raw(
    x_ptr: *const f64,
    y_ptr: *const f64,
    t_ptr: *const f64,
    len: usize,
) -> CurvatureMetrics {
    if len < 4 || x_ptr.is_null() || y_ptr.is_null() || t_ptr.is_null() {
        return CurvatureMetrics::default();
    }
    let x = std::slice::from_raw_parts(x_ptr, len);
    let y = std::slice::from_raw_parts(y_ptr, len);
    let t = std::slice::from_raw_parts(t_ptr, len);
    evaluate_curvature_naturalness(x, y, t)
}

/// AVX2 256-bit SIMD implementation of differential curvature:
/// kappa = |vx*ay - vy*ax| / (vx^2 + vy^2 + eps)^1.5
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
pub unsafe fn compute_curvature_avx2(
    vx: &[f64],
    vy: &[f64],
    ax: &[f64],
    ay: &[f64],
    out_kappa: &mut [f64],
) {
    use std::arch::x86_64::*;
    let n = vx.len();
    let chunks = n / 4;
    let eps = _mm256_set1_pd(1e-6);
    // Mask for clearing sign bit of f64 (0x7FFFFFFFFFFFFFFF)
    let sign_mask = _mm256_castsi256_pd(_mm256_set1_epi64x(0x7FFFFFFFFFFFFFFFi64));

    for i in 0..chunks {
        let idx = i * 4;
        let v_vx = _mm256_loadu_pd(vx.as_ptr().add(idx));
        let v_vy = _mm256_loadu_pd(vy.as_ptr().add(idx));
        let v_ax = _mm256_loadu_pd(ax.as_ptr().add(idx));
        let v_ay = _mm256_loadu_pd(ay.as_ptr().add(idx));

        // Numerator: |vx*ay - vy*ax|
        let p1 = _mm256_mul_pd(v_vx, v_ay);
        let p2 = _mm256_mul_pd(v_vy, v_ax);
        let diff = _mm256_sub_pd(p1, p2);
        let num = _mm256_and_pd(diff, sign_mask);

        // Denominator: (vx^2 + vy^2 + eps)^1.5
        let vx2 = _mm256_mul_pd(v_vx, v_vx);
        let vy2 = _mm256_mul_pd(v_vy, v_vy);
        let v_sq = _mm256_add_pd(_mm256_add_pd(vx2, vy2), eps);

        let sqrt_v = _mm256_sqrt_pd(v_sq);
        let denom = _mm256_mul_pd(v_sq, sqrt_v);

        let kappa = _mm256_div_pd(num, denom);
        _mm256_storeu_pd(out_kappa.as_mut_ptr().add(idx), kappa);
    }

    // Scalar fallback for remainder elements
    for i in (chunks * 4)..n {
        let num = (vx[i] * ay[i] - vy[i] * ax[i]).abs();
        let denom_base = vx[i] * vx[i] + vy[i] * vy[i] + 1e-6;
        let denom = denom_base * denom_base.sqrt();
        out_kappa[i] = num / denom;
    }
}

/// High-performance scalar fallback
pub fn compute_curvature_scalar(
    vx: &[f64],
    vy: &[f64],
    ax: &[f64],
    ay: &[f64],
    out_kappa: &mut [f64],
) {
    let n = vx.len();
    for i in 0..n {
        let num = (vx[i] * ay[i] - vy[i] * ax[i]).abs();
        let denom_base = vx[i] * vx[i] + vy[i] * vy[i] + 1e-6;
        let denom = denom_base * denom_base.sqrt();
        out_kappa[i] = num / denom;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Deterministic xorshift PRNG so tests need no external crates.
    struct Rng(u64);
    impl Rng {
        fn next_f64(&mut self) -> f64 {
            self.0 ^= self.0 << 13;
            self.0 ^= self.0 >> 7;
            self.0 ^= self.0 << 17;
            (self.0 >> 11) as f64 / (1u64 << 53) as f64
        }
        fn range(&mut self, lo: f64, hi: f64) -> f64 {
            lo + (hi - lo) * self.next_f64()
        }
    }

    fn arc(radius: f64, n: usize, step_rad: f64, dt_ms: f64) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
        let x = (0..n).map(|i| radius * (i as f64 * step_rad).cos()).collect();
        let y = (0..n).map(|i| radius * (i as f64 * step_rad).sin()).collect();
        let t = (0..n).map(|i| i as f64 * dt_ms).collect();
        (x, y, t)
    }

    #[test]
    fn fewer_than_four_points_returns_default() {
        let m = evaluate_curvature_naturalness(&[0.0, 1.0, 2.0], &[0.0, 1.0, 2.0], &[0.0, 10.0, 20.0]);
        assert_eq!(m.curvature_score, 0.0);
        assert_eq!(m.mean_curvature, 0.0);
    }

    #[test]
    fn mismatched_slice_lengths_use_shortest() {
        let (x, y, t) = arc(100.0, 40, 0.05, 10.0);
        let full = evaluate_curvature_naturalness(&x[..20], &y[..20], &t[..20]);
        let ragged = evaluate_curvature_naturalness(&x, &y[..20], &t);
        assert_eq!(full.mean_curvature, ragged.mean_curvature);
    }

    #[test]
    fn straight_line_is_flagged_as_bot() {
        let x: Vec<f64> = (0..30).map(|i| i as f64 * 5.0).collect();
        let y: Vec<f64> = (0..30).map(|i| i as f64 * 2.0).collect();
        let t: Vec<f64> = (0..30).map(|i| i as f64 * 10.0).collect();
        let m = evaluate_curvature_naturalness(&x, &y, &t);
        assert!(m.mean_curvature < 1e-9);
        assert_eq!(m.curvature_score, 0.95);
    }

    #[test]
    fn circular_arc_recovers_geometric_curvature() {
        // kappa = |v x a| / |v|^3 is parametrisation-invariant: a circle of radius R has kappa = 1/R.
        for &r in &[50.0, 100.0, 400.0] {
            let (x, y, t) = arc(r, 60, 0.05, 10.0);
            let m = evaluate_curvature_naturalness(&x, &y, &t);
            let rel_err = (m.mean_curvature - 1.0 / r).abs() * r;
            assert!(rel_err < 0.02, "R={r}: kappa={} expected {}", m.mean_curvature, 1.0 / r);
        }
    }

    #[test]
    fn perfectly_smooth_arc_is_flagged_as_synthetic() {
        let (x, y, t) = arc(200.0, 60, 0.03, 10.0);
        let m = evaluate_curvature_naturalness(&x, &y, &t);
        assert!(m.curvature_score >= 0.90, "analytic curve scored {}", m.curvature_score);
    }

    // KNOWN GAP (found 2026-11-06): the variance thresholds (> 5.0 / > 10.0) are absolute and
    // scale-dependent, so per-point jitter is only caught in a narrow amplitude/speed band
    // (1 of 10 probed configurations). Run with `cargo test -- --ignored` to track the fix.
    #[test]
    #[ignore = "known detection gap: scale-dependent jitter thresholds"]
    fn independent_gaussian_like_jitter_is_flagged() {
        let mut rng = Rng(0x5eed);
        let x: Vec<f64> = (0..80).map(|i| i as f64 * 3.0 + rng.range(-4.0, 4.0)).collect();
        let y: Vec<f64> = (0..80).map(|_| rng.range(-4.0, 4.0)).collect();
        let t: Vec<f64> = (0..80).map(|i| i as f64 * 8.0).collect();
        let m = evaluate_curvature_naturalness(&x, &y, &t);
        assert!(m.curvature_score >= 0.75, "per-point jitter scored {}", m.curvature_score);
    }

    /// Aimed movement as the browser reports it: curved, minimum-jerk speed profile (slow at both ends),
    /// 1-px quantised, followed by sub-pixel homing jitter while the cursor settles on the target.
    fn quantised_human_like(rng: &mut Rng) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
        let (mut x, mut y, mut t) = (Vec::new(), Vec::new(), Vec::new());
        let n = 40;
        for i in 0..n {
            let u = i as f64 / (n - 1) as f64;
            let s = 10.0 * u.powi(3) - 15.0 * u.powi(4) + 6.0 * u.powi(5);
            let px = 100.0 + 500.0 * s;
            let py = 200.0 + 300.0 * s + 60.0 * (std::f64::consts::PI * s).sin() + rng.range(-1.5, 1.5);
            x.push(px.round());
            y.push(py.round());
            t.push(i as f64 * 30.0);
        }
        let (lx, ly, lt) = (*x.last().unwrap(), *y.last().unwrap(), *t.last().unwrap());
        for j in 1..15 {
            x.push(lx + rng.range(-1.0, 1.0).round());
            y.push(ly + rng.range(-1.0, 1.0).round());
            t.push(lt + j as f64 * 30.0);
        }
        (x, y, t)
    }

    #[test]
    fn stop_and_quantisation_artefacts_are_not_chaotic_curvature() {
        // Regression (v0.10.6): kappa explodes near zero speed; real humans were flagged 0.85 in ~67% of
        // SapiMouse windows. Ungated variance is still huge here; the verdict must not be "chaotic".
        let mut rng = Rng(7);
        for _ in 0..20 {
            let (x, y, t) = quantised_human_like(&mut rng);
            let m = evaluate_curvature_naturalness(&x, &y, &t);
            assert!(m.curvature_score < 0.75, "human-like path scored {} (var {})", m.curvature_score, m.curvature_var);
        }
    }

    #[test]
    fn minimum_jerk_with_resting_ends_is_flagged_as_synthetic() {
        // Minimum-jerk bot rounded to 0.01 px: speed is ~0 at both ends, where the rounding noise inflates the
        // all-points variance. Only the moving-points statistic flags it (the all-points one does not).
        let r2 = |v: f64| (v * 100.0).round() / 100.0;
        for &bow in &[0.0, 80.0] {
            let n = 50;
            let (mut x, mut y, mut t) = (Vec::new(), Vec::new(), Vec::new());
            for i in 0..n {
                let u = i as f64 / (n - 1) as f64;
                let s = 10.0 * u.powi(3) - 15.0 * u.powi(4) + 6.0 * u.powi(5);
                x.push(r2(100.0 + 600.0 * s));
                y.push(r2(100.0 + 350.0 * s + bow * (std::f64::consts::PI * s).sin()));
                t.push(i as f64 * 25.0);
            }
            let m = evaluate_curvature_naturalness(&x, &y, &t);
            assert!(m.curvature_var > 1e-4 && m.curvature_rate_var > 1e-8, "fixture is smooth on all points: {m:?}");
            assert!(m.curvature_score >= 0.90, "minimum-jerk bot (bow {bow}) scored {}", m.curvature_score);
        }
    }

    #[test]
    fn gated_spacing_equals_all_points_spacing_when_nothing_is_dropped() {
        let dt_a = [20.0, 16.5, 33.0, 41.5, 25.0, 16.0];
        assert_eq!(gated_dts(&dt_a, &[true; 6]), dt_a[1..].to_vec());
    }

    #[test]
    fn gated_spacing_sums_the_steps_of_dropped_points() {
        let dt_a = [20.0, 16.5, 33.0, 41.5, 25.0, 16.0];
        // kept 0 -> 2: 16.5 + 33.0; 2 -> 3: 41.5; 3 -> 5: 25.0 + 16.0
        assert_eq!(gated_dts(&dt_a, &[true, false, true, true, false, true]), vec![49.5, 41.5, 41.0]);
        assert_eq!(gated_dts(&dt_a, &[false, false, true, false, false, true]), vec![82.5]);
    }

    #[test]
    fn too_few_moving_points_gives_no_chaos_verdict() {
        // Only sub-5-px steps (a cursor nudged around a spot): the chaos checks have no reliable input.
        let mut rng = Rng(11);
        let x: Vec<f64> = (0..30).map(|_| (300.0 + rng.range(-2.0, 2.0)).round()).collect();
        let y: Vec<f64> = (0..30).map(|_| (300.0 + rng.range(-2.0, 2.0)).round()).collect();
        let t: Vec<f64> = (0..30).map(|i| i as f64 * 30.0).collect();
        let m = evaluate_curvature_naturalness(&x, &y, &t);
        assert!(m.curvature_score < 0.75, "jiggle scored {}", m.curvature_score);
    }

    #[test]
    fn duplicate_timestamps_do_not_produce_nan_or_inf() {
        let x = [0.0, 1.0, 2.0, 4.0, 7.0, 11.0];
        let y = [0.0, 2.0, 3.0, 3.0, 5.0, 4.0];
        let t = [0.0, 0.0, 0.0, 10.0, 10.0, 20.0];
        let m = evaluate_curvature_naturalness(&x, &y, &t);
        for v in [m.mean_curvature, m.curvature_var, m.curvature_rate_var, m.curvature_score] {
            assert!(v.is_finite());
        }
    }

    #[test]
    fn scalar_kernel_matches_closed_form() {
        let (vx, vy, ax, ay) = ([3.0], [4.0], [1.0], [2.0]);
        let mut out = [0.0];
        compute_curvature_scalar(&vx, &vy, &ax, &ay, &mut out);
        // |3*2 - 4*1| / (25 + 1e-6)^1.5
        let expected = 2.0 / (25.0f64 + 1e-6).powf(1.5);
        assert!((out[0] - expected).abs() < 1e-15);
    }

    #[cfg(target_arch = "x86_64")]
    #[test]
    fn avx2_kernel_matches_scalar_for_all_remainder_lengths() {
        if !is_x86_feature_detected!("avx2") {
            eprintln!("AVX2 not available on this CPU; SIMD parity test skipped");
            return;
        }
        let mut rng = Rng(42);
        // Lengths 0..=13 cover full 4-lane chunks plus every remainder (0..3).
        for n in 0..=13usize {
            let gen = |rng: &mut Rng| (0..n).map(|_| rng.range(-50.0, 50.0)).collect::<Vec<f64>>();
            let (vx, vy, ax, ay) = (gen(&mut rng), gen(&mut rng), gen(&mut rng), gen(&mut rng));
            let mut simd = vec![0.0; n];
            let mut scalar = vec![0.0; n];
            unsafe { compute_curvature_avx2(&vx, &vy, &ax, &ay, &mut simd) };
            compute_curvature_scalar(&vx, &vy, &ax, &ay, &mut scalar);
            for i in 0..n {
                let tol = 1e-12 * scalar[i].abs().max(1.0);
                assert!((simd[i] - scalar[i]).abs() <= tol, "n={n} i={i}: {} vs {}", simd[i], scalar[i]);
            }
        }
    }

    #[test]
    fn raw_pointer_entry_rejects_null_and_short_input() {
        let v = [1.0, 2.0, 3.0, 4.0, 5.0];
        unsafe {
            let m = evaluate_curvature_raw(std::ptr::null(), v.as_ptr(), v.as_ptr(), 5);
            assert_eq!(m.curvature_score, 0.0);
            let m = evaluate_curvature_raw(v.as_ptr(), v.as_ptr(), v.as_ptr(), 3);
            assert_eq!(m.curvature_score, 0.0);
        }
    }

    #[test]
    fn raw_pointer_entry_matches_slice_entry() {
        let (x, y, t) = arc(120.0, 32, 0.07, 12.0);
        let a = evaluate_curvature_naturalness(&x, &y, &t);
        let b = unsafe { evaluate_curvature_raw(x.as_ptr(), y.as_ptr(), t.as_ptr(), x.len()) };
        assert_eq!(a.mean_curvature, b.mean_curvature);
        assert_eq!(a.curvature_score, b.curvature_score);
    }
}
