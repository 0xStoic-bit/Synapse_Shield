# Python tests

The project is tested in three layers; CI runs all of them on every push and pull request (`.github/workflows/ci.yml`).

| Layer | Suite | What it guards |
| :--- | :--- | :--- |
| 🐍 Python | `tests/` (pytest) | API, tokens, engine, storage, Rust ↔ Python parity. One security contract (no token → 403, replay → 403, bot → 403, shadow mode, 256 KB limit) runs against the **real** FastAPI, Flask, Sanic and Litestar pipelines. Redis runs on `fakeredis` with real command semantics, including the Redis → SQLite failover. The red-team suite (`synapse-shield test`) runs end-to-end in-process and each verdict is asserted |
| 🦀 Rust core | `#[cfg(test)]` modules in `crates/synapse_core_rs/src/` | See [crates/synapse_core_rs](../crates/synapse_core_rs/README.md) |
| 🌐 Browser SDKs | `sdk-tests/` (Vitest + jsdom) | See [sdk-tests](../sdk-tests/README.md) |

## Run

```bash
pip install -e ".[all]" && pip install pytest pytest-cov httpx sanic-testing fakeredis
pytest tests -rsxX --cov=synapse_shield --cov-branch --cov-fail-under=85
```

CI fails if the native Rust core is not loaded, so the parity tests can never silently skip. Locally, rebuild it after Rust changes (`maturin develop --release`).

## Coverage and mutation testing

- **Coverage floor:** CI fails below 85% line + branch coverage.
- **Mutation testing:** coverage only shows that a line ran; mutation testing checks that the tests would notice if the line were wrong. [`mutmut`](https://github.com/boxed/mutmut) mutates `tokens.py`, `core.py` and `storage.py` (config in `[tool.mutmut]` in `pyproject.toml`), weekly and on demand in `.github/workflows/mutation.yml`. mutmut 3 needs Linux or WSL:

  ```bash
  pip install "mutmut>=3.3,<4" && mutmut run && mutmut results
  ```

## Conventions

- **No invented numbers.** Synthetic inputs test rules and edge cases; accuracy claims are measured on real datasets outside the test suite.
- **Known gaps stay visible.** They are marked `xfail(strict=True)` with the reason in the test, so the suite fails the moment behaviour changes.
- Files named after a release (`test_v0107_*.py`) or a work item (`test_p2a_*.py`) pin the behaviour introduced there.
