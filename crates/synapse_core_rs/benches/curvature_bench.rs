use criterion::{black_box, criterion_group, criterion_main, Criterion};
use synapse_core_rs::curvature::evaluate_curvature_naturalness;

fn generate_bezier_trajectory(steps: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let mut xs = Vec::with_capacity(steps);
    let mut ys = Vec::with_capacity(steps);
    let mut ts = Vec::with_capacity(steps);

    let p0 = (100.0, 100.0);
    let p1 = (300.0, 150.0);
    let p2 = (500.0, 450.0);
    let p3 = (800.0, 600.0);

    for i in 0..steps {
        let u = i as f64 / (steps - 1) as f64;
        let b0 = (1.0 - u).powi(3);
        let b1 = 3.0 * (1.0 - u).powi(2) * u;
        let b2 = 3.0 * (1.0 - u) * u.powi(2);
        let b3 = u.powi(3);

        let x = b0 * p0.0 + b1 * p1.0 + b2 * p2.0 + b3 * p3.0;
        let y = b0 * p0.1 + b1 * p1.1 + b2 * p2.1 + b3 * p3.1;
        let t = 1000.0 + i as f64 * 16.6;

        xs.push(x);
        ys.push(y);
        ts.push(t);
    }

    (xs, ys, ts)
}

fn generate_human_like_trajectory(steps: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let mut xs = Vec::with_capacity(steps);
    let mut ys = Vec::with_capacity(steps);
    let mut ts = Vec::with_capacity(steps);

    let start = (100.0, 100.0);
    let end = (800.0, 600.0);

    for i in 0..steps {
        let t_norm = i as f64 / (steps - 1) as f64;
        // Sigmoid submovement profile
        let s = 3.0 * t_norm.powi(2) - 2.0 * t_norm.powi(3);
        let base_x = start.0 + (end.0 - start.0) * s;
        let base_y = start.1 + (end.1 - start.1) * s;

        // Biological tremor & curvature deviation
        let tremor_x = (i as f64 * 0.7).sin() * 0.8;
        let tremor_y = (i as f64 * 0.9).cos() * 0.8;

        xs.push(base_x + tremor_x);
        ys.push(base_y + tremor_y);
        ts.push(1000.0 + i as f64 * 16.6);
    }

    (xs, ys, ts)
}

fn bench_curvature(c: &mut Criterion) {
    let (bezier_x, bezier_y, bezier_t) = generate_bezier_trajectory(100);
    let (human_x, human_y, human_t) = generate_human_like_trajectory(100);

    let mut group = c.benchmark_group("Curvature_Kinematics");

    group.bench_function("bezier_bot_trajectory_100_points", |b| {
        b.iter(|| {
            evaluate_curvature_naturalness(
                black_box(&bezier_x),
                black_box(&bezier_y),
                black_box(&bezier_t),
            )
        })
    });

    group.bench_function("human_trajectory_100_points", |b| {
        b.iter(|| {
            evaluate_curvature_naturalness(
                black_box(&human_x),
                black_box(&human_y),
                black_box(&human_t),
            )
        })
    });

    group.finish();
}

criterion_group!(benches, bench_curvature);
criterion_main!(benches);
