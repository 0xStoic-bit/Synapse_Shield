# Scripts

Helpers that are not part of the installed package. Most attack scripts target a local server (`synapse-shield run`, `http://127.0.0.1:8000`); only point them at systems you own.

## Release and documentation

| Script | Purpose |
| :--- | :--- |
| `bump_version.py` | Synchronise the version number across the Python package, Rust crate and SDK packages |
| `sri_hash.py` | Subresource Integrity tag for the published browser SDK (`--check <hash>` for CI) |
| `measure_readme_benchmarks.py` | Re-measure the attack table in [docs/BENCHMARKS.md](../docs/BENCHMARKS.md), in-process, no network |
| `make_readme_gifs.py` | Regenerate `docs/assets/*.gif` from the project's own generators and engine |
| `train_sequence_ai.py` | Original (v0.6) training script of the bundled CNN weights: synthetic data only |

## Attack simulators and stress tests

| Script | Purpose |
| :--- | :--- |
| `red_team_full_suite.py`, `red_team_v076_suite.py` | Full penetration and bot-mitigation suites |
| `attack_sim.py`, `synapse_adversarial_test.py`, `apex_adversarial_test.py` | Adversarial attack and bot simulation |
| `minimum_jerk_bot.py`, `stealth_bot.py`, `playwright_bypass_bot.py`, `dumb_playwright_bot.py` | Specific bot strategies (minimum-jerk motion, stealth browser, Playwright) |
| `test_direct_api_bypass.py`, `test_session_invariance.py`, `test_lorenz_attack.py` | Targeted bypass attempts (raw API, session replay, chaotic motion) |
| `synapse_tamper_test_v064.py` | Anti-stealth and tamper-detection checks |
| `flood_10k_stress.py`, `stress_test_bot.py`, `stress_test_distributed.py` | Load, botnet-flood and multi-worker / Redis fallback tests |
| `retrain_with_lorenz.py` | Adversarial retraining experiment |

Older scripts named after a release (`bypass_bot_v060.py`, `smoke_test_v072.py`, `test_v070.py`, …) are kept as historical reproductions of earlier findings and may not match current behaviour.
