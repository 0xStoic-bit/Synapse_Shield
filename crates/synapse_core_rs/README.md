# `synapse_core_rs`: native Rust core

Optional native acceleration for the Python package: kinematic and keystroke feature extraction, differential curvature (AVX2 / NEON with a scalar fallback) and an in-memory nonce / ban cache. Exposed to Python through PyO3.

The Python package works without it (pure-Python fallback), but the published wheels include it. Python and Rust must produce the same features to within 1e-5; `tests/test_rust_python_parity.py` enforces this.

## Build

The crate uses PyO3 0.30 with `abi3-py310`: one compiled module per platform runs on every CPython ≥ 3.10.

```bash
pip install maturin
maturin develop --release        # builds and installs into the active environment
```

After editing any `.rs` file, rebuild; otherwise pytest silently runs against the previously compiled module. `synapse-shield doctor` (and `tests/test_rust_core_version_guard.py`) fail when the loaded core's version does not match the package version.

## Test

```bash
cd crates/synapse_core_rs
PYO3_PYTHON=$(which python) cargo test --all-targets
```

On Windows, point `PYO3_PYTHON` at the official CPython interpreter. An MSYS2 / MinGW `python` earlier on `PATH` is picked up by default and fails to link with the MSVC toolchain.

`curvature::tests::independent_gaussian_like_jitter_is_flagged` is `#[ignore]`d on purpose: it documents a known gap (curvature thresholds are scale-dependent).

## Layout

| File | Role |
| :--- | :--- |
| `src/lib.rs` | PyO3 module: Python-facing functions, strict parsing of browser fields (shared rules with `features.py`) |
| `src/kinematics.rs` | Feature extraction from mouse / touch telemetry |
| `src/curvature.rs` | SIMD differential curvature |
| `src/keystrokes.rs` | Dwell / flight timing, IME handling, digraph entropy |
| `src/nonce_cache.rs` | In-memory nonce and IP-ban cache (L1 in front of SQLite / Redis) |
| `benches/curvature_bench.rs` | Criterion benchmark for the curvature kernel (`cargo bench`) |
