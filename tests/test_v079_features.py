"""
Unit Tests for Synapse Shield v0.7.9 Features:
1. Biological Synthetic Human Telemetry Generator
2. Isolated Weight Hierarchy Loading (Environment, CWD, and Base)
3. High-Precision Microsecond Benchmark Suite
4. Active Learning Bootstrap Pipeline
"""

import json
import os
import numpy as np

from synapse_shield.adversarial import (
    generate_synthetic_human_telemetry,
    generate_synthetic_human_batch,
)
from synapse_shield.benchmark import run_micro_benchmarks
from synapse_shield.engine import analyze_behavior
from synapse_shield.models import SynapseHybridModel
from synapse_shield.train import retrain_fc2, BASE_WEIGHTS_PATH


def test_synthetic_human_telemetry_generation():
    telemetry = generate_synthetic_human_telemetry()

    assert "mouse_movements" in telemetry
    assert "clicks" in telemetry
    assert "browser" in telemetry
    assert len(telemetry["mouse_movements"]) >= 40
    assert telemetry["browser"]["webdriver"] is False
    assert telemetry["browser"]["plugins_length"] >= 3

    # Analyze with engine: biological modeling should produce a Human decision
    score, cls, reasons, _ = analyze_behavior(telemetry)
    assert cls == "Human", f"Synthetic human flagged as {cls} with reasons: {reasons}"
    assert score <= 30.0


def test_synthetic_human_batch():
    batch = generate_synthetic_human_batch(count=5)
    assert len(batch) == 5
    for item in batch:
        assert len(item["mouse_movements"]) >= 40


def test_synapse_hybrid_model_weight_hierarchy(monkeypatch, tmp_path):
    # 1. Default base load
    monkeypatch.delenv("SYNAPSE_WEIGHTS_PATH", raising=False)
    model_default = SynapseHybridModel()
    assert os.path.exists(model_default.weights_path)
    assert "weights.npz" in model_default.weights_path

    # 2. Custom environment path load
    custom_npz = tmp_path / "custom_weights.npz"
    # Copy base weights to custom path
    with np.load(BASE_WEIGHTS_PATH) as data:
        np.savez_compressed(custom_npz, **{k: data[k] for k in data.files})

    monkeypatch.setenv("SYNAPSE_WEIGHTS_PATH", str(custom_npz))
    model_custom = SynapseHybridModel()
    assert model_custom.weights_path == str(custom_npz)


def test_benchmark_suite_execution(tmp_path):
    export_file = str(tmp_path / "bench_test.json")
    report = run_micro_benchmarks(iterations=10, export_path=export_file)

    assert "system_info" in report
    assert "benchmarks" in report
    assert "19D Kinematic Feature Extraction" in report["benchmarks"]
    assert "1D-CNN Pure NumPy Inference" in report["benchmarks"]
    assert "Crypto Token & Atomic Nonce" in report["benchmarks"]
    assert "Full End-to-End Pipeline" in report["benchmarks"]

    # Verify JSON export
    assert os.path.exists(export_file)
    with open(export_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "benchmarks" in data


def test_retrain_fc2_with_bootstrap(tmp_path):
    out_file = str(tmp_path / "test_retrained.npz")
    base_mtime_before = os.path.getmtime(BASE_WEIGHTS_PATH)

    res = retrain_fc2(epochs=1, bootstrap=True, output_path=out_file)

    assert res["success"] is True
    assert res["samples"] >= 20
    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 1000

    # Guarantee base package weights.npz was NEVER touched
    base_mtime_after = os.path.getmtime(BASE_WEIGHTS_PATH)
    assert base_mtime_before == base_mtime_after
