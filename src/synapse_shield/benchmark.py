"""
Synapse Shield — High-Precision Latency & Throughput Benchmark Suite
Profiles microsecond-level execution times for:
1. 19D Kinematic Feature Extraction (Jerk, Curvature, Spectral Entropy, Fitts)
2. 1D-CNN Pure NumPy Matmul Inference
3. Cryptographic Token Generation & Atomic Nonce Verification
4. End-to-End Decision Pipeline
"""

import argparse
import json
import platform
import secrets
import time
from typing import Any

import numpy as np

from synapse_shield import __version__
from synapse_shield.adversarial import generate_synthetic_human_telemetry
from synapse_shield.engine import analyze_behavior
from synapse_shield.features import MultimodalTokenizer, extract_features, is_rust_accelerated
from synapse_shield.models import SynapseHybridModel
from synapse_shield.tokens import generate_challenge, verify_and_consume_token


def measure_latencies(func, iterations: int = 500, warmup: int = 50) -> list[float]:
    """
    Executes func() for warmup + iterations times and records execution duration in microseconds.
    """
    for _ in range(warmup):
        func()

    latencies_us = []
    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        func()
        t1 = time.perf_counter_ns()
        latencies_us.append((t1 - t0) / 1000.0)  # ns to us

    return latencies_us


def compute_statistics(latencies_us: list[float]) -> dict[str, float]:
    arr = np.array(latencies_us, dtype=np.float64)
    mean_us = float(np.mean(arr))
    p50_us = float(np.percentile(arr, 50))
    p95_us = float(np.percentile(arr, 95))
    p99_us = float(np.percentile(arr, 99))
    min_us = float(np.min(arr))
    max_us = float(np.max(arr))
    throughput = float(1_000_000.0 / mean_us) if mean_us > 0 else 0.0

    return {
        "mean_us": mean_us,
        "p50_us": p50_us,
        "p95_us": p95_us,
        "p99_us": p99_us,
        "min_us": min_us,
        "max_us": max_us,
        "throughput_ops_sec": throughput,
    }


def run_micro_benchmarks(iterations: int = 500, export_path: str | None = None) -> dict[str, Any]:
    """
    Runs the comprehensive micro-benchmark suite across all 4 critical architectural stages.
    """
    sample_telemetry = generate_synthetic_human_telemetry()
    tokenizer = MultimodalTokenizer(max_mouse_steps=60)
    tokenized = tokenizer.fuse(sample_telemetry)
    mouse_tensor = tokenized["mouse_tensor"]
    static_vector = tokenized["static_vector"]

    model = SynapseHybridModel()

    # Stage 1a: Native Rust Kinematic Feature Extraction
    def bench_features_rust():
        extract_features(sample_telemetry, force_python=False)

    # Stage 1b: Pure Python / NumPy Fallback Feature Extraction
    def bench_features_python():
        extract_features(sample_telemetry, force_python=True)

    # Stage 2: 1D-CNN Pure NumPy Inference
    def bench_inference():
        model.predict(mouse_tensor, static_vector)

    # Stage 3: Cryptographic Token Challenge & Verification
    def bench_crypto():
        chal = generate_challenge(expires_in_sec=60)
        verify_and_consume_token(chal["challenge"])

    # Stage 3b: In-Memory Two-Bucket Nonce Verification
    from synapse_shield.storage import get_storage
    storage = get_storage()

    def bench_two_bucket():
        storage.consume_nonce("bench_" + secrets.token_hex(12))

    # Stage 4: End-to-End Decision Pipeline
    def bench_e2e():
        analyze_behavior(sample_telemetry)

    stages = [
        ("Native Rust 19D Kinematics", bench_features_rust),
        ("Python NumPy Fallback Kinematics", bench_features_python),
        ("1D-CNN Pure NumPy Inference", bench_inference),
        ("Rust Two-Bucket Nonce Verification", bench_two_bucket),
        ("Crypto Token & Atomic Nonce", bench_crypto),
        ("Full End-to-End Pipeline", bench_e2e),
    ]

    results = {}
    for name, fn in stages:
        raw = measure_latencies(fn, iterations=iterations, warmup=max(20, iterations // 10))
        results[name] = compute_statistics(raw)

    # Backwards compatibility alias
    results["19D Kinematic Feature Extraction"] = results.get(
        "Native Rust 19D Kinematics", results.get("Python NumPy Fallback Kinematics")
    )

    system_info = {
        "synapse_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown CPU",
        "numpy_version": np.__version__,
        "iterations": iterations,
    }

    report = {
        "system_info": system_info,
        "benchmarks": results,
    }

    print_benchmark_report(report)

    if export_path:
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n[+] Benchmark metrics saved to: {export_path}")

    return report


def print_benchmark_report(report: dict[str, Any]) -> None:
    info = report["system_info"]
    benchmarks = report["benchmarks"]

    width = 92
    print("=" * width)
    print(f"  SYNAPSE SHIELD // DETERMINISTIC MICROSECOND BENCHMARK [v{info['synapse_version']}]")
    print("=" * width)
    print(f"  Host Platform : {info['platform']} ({info['processor']})")
    core_status = "Native Rust Core (synapse_core_rs) [ACTIVE]" if is_rust_accelerated() else "Pure Python/NumPy (Fallback)"
    print(f"  Runtime Env   : Python {info['python_version']} | NumPy {info['numpy_version']} | {core_status}")
    print(f"  Sample Size   : {info['iterations']} iterations per pipeline stage")
    print("-" * width)
    print(
        f"  {'STAGE / PIPELINE MODULE':<35} | {'MEAN (us)':<10} | {'P50 (us)':<10} | {'P95 (us)':<10} | {'THROUGHPUT':<12}"
    )
    print("-" * width)

    for stage_name, stats in benchmarks.items():
        mean_str = f"{stats['mean_us']:.1f} us"
        p50_str = f"{stats['p50_us']:.1f} us"
        p95_str = f"{stats['p95_us']:.1f} us"
        thru_str = f"{stats['throughput_ops_sec']:,.0f} ops/s"

        print(f"  {stage_name:<35} | {mean_str:<10} | {p50_str:<10} | {p95_str:<10} | {thru_str:<12}")

    print("=" * width)
    e2e = benchmarks.get("Full End-to-End Pipeline", {})
    if e2e:
        mean_ms = e2e["mean_us"] / 1000.0
        print(f"  [RESULT] End-to-End Decision Latency: {mean_ms:.3f} ms (p95: {e2e['p95_us'] / 1000.0:.3f} ms)")
        print(f"  [RPS] Single-Core Throughput Capacity: ~{e2e['throughput_ops_sec']:,.0f} req/sec")
    print("=" * width)


def main():
    parser = argparse.ArgumentParser(description="Synapse Shield Latency & Throughput Benchmark")
    parser.add_argument(
        "--iterations", "-n", type=int, default=500, help="Number of benchmark iterations (default: 500)"
    )
    parser.add_argument("--export", "-e", type=str, default=None, help="Export benchmark metrics to JSON file")
    args = parser.parse_args()

    run_micro_benchmarks(iterations=args.iterations, export_path=args.export)


if __name__ == "__main__":
    main()
