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

    // 4. Rate of change of curvature: d_kappa / dt
    let mut d_kappa = Vec::with_capacity(k_len.saturating_sub(1));
    for i in 1..k_len {
        let dt = dt_a[i].max(0.1);
        d_kappa.push((kappa[i] - kappa[i - 1]) / dt);
    }

    // 5. Statistical moments
    let kappa_count = kappa.len() as f64;
    let mean_kappa: f64 = kappa.iter().sum::<f64>() / kappa_count;
    let var_kappa: f64 = kappa.iter().map(|&k| (k - mean_kappa).powi(2)).sum::<f64>() / kappa_count;

    let var_d_kappa: f64 = if !d_kappa.is_empty() {
        let d_count = d_kappa.len() as f64;
        let d_mean: f64 = d_kappa.iter().sum::<f64>() / d_count;
        d_kappa.iter().map(|&dk| (dk - d_mean).powi(2)).sum::<f64>() / d_count
    } else {
        0.0
    };

    // 6. Bot vs Human Classification Score (0.0 = human, 1.0 = bot)
    // - Synthetic Bézier: rate of curvature variance is analytically smooth (< 1e-6)
    // - Synthetic Gaussian Noise: independent per-point jitter causes variance explosion (> 2.0)
    // - Natural Human: bounded biological tremor (typically 1e-4 .. 0.5) with physiological damping
    let score: f64;

    if mean_kappa < 1e-6 && var_kappa < 1e-7 {
        // Straight line bot
        score = 0.95;
    } else if var_d_kappa < 1e-8 && var_kappa < 1e-4 {
        // Unnaturally smooth polynomial / Bézier curve without neuromuscular submovements
        score = 0.90;
    } else if var_d_kappa > 5.0 || var_kappa > 10.0 {
        // Unphysical artificial noise / discrete Gaussian jitter
        score = 0.85;
    } else {
        // Check curvature distribution: biological curves show log-normal or localized peaks
        let high_peak_count = kappa.iter().filter(|&&k| k > 0.1).count();
        if high_peak_count > (k_len / 2) && var_d_kappa > 2.0 {
            score = 0.75;
        } else {
            // Natural human motion with neuromuscular damping
            score = 0.10;
        }
    }

    CurvatureMetrics {
        mean_curvature: mean_kappa,
        curvature_var: var_kappa,
        curvature_rate_var: var_d_kappa,
        curvature_score: score.clamp(0.0, 1.0),
    }
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
