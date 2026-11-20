# Benchmarks and attack tests

Back to the [documentation index](README.md).

## Where the numbers come from

- **Human false positives** are measured on the public **SapiMouse** dataset (120 people, real mouse recordings) and the **CMU keystroke** dataset, replayed through the engine (`research/` tooling, not shipped).
- **Bot detection** is measured with synthetic attack generators (`synapse_shield.adversarial`, the red-team suite). No real bot traffic has been labelled yet, so treat bot numbers as "detects these generators", not as a production detection rate.

## Real-human false positives (v0.11.0)

| Measurement (SapiMouse, real people) | Before v0.11.0 | v0.11.0 |
| :--- | :--- | :--- |
| 6-second windows blocked, production weights | 19.0% | 1.4% |
| 20-second windows blocked, production weights | 19.2% | 0.5% |
| Single short cursor movements blocked | 50.0% | 4.9% |
| 2-second windows blocked | 18.0% | 2.4% |

"Production weights" means the 1D-CNN weights bundled in the package, which are what a Docker deployment loads; v0.11.0 runs that model in shadow mode. Measured before and after on the same seeds; details in the release notes.

## Attack simulation suite

```bash
synapse-shield run --port 8000   # in one terminal
synapse-shield test              # in another
```

`synapse-shield test` is a **smoke test**: the human controls are synthetic, and an HTTP error that carries no Synapse verdict counts as `Error`, never as a block. Vector #10 (humanised Bézier) is printed as a separate measurement row and does not affect the exit code. The exit code is non-zero if a verdict is wrong (1) or the server cannot be reached (2).

Measured on 2026-11-12 (v0.10.7). Reproduce with `python scripts/measure_readme_benchmarks.py`, which needs no server and sends nothing off the machine. Decision and risk come from a real `POST /api/score`. Latency is the median engine time (`analyze_behavior`) over 200 runs.

| Attack vector | Simulated signature | Detection mechanism | Decision | Risk | Latency |
| --- | --- | --- | --- | --- | --- |
| **Selenium crawler** | `navigator.webdriver = true` | WebDriver API detection | 🔴 BLOCK | 100.0% | 0.12 ms |
| **Linear bot** | Straightness = 1.000 & zero jerk | Straightness + velocity variance | 🔴 BLOCK | 100.0% | 0.24 ms |
| **Bézier stealth bot** | Quadratic Bézier, fixed 20 ms timer | Fixed-interval timer + synthetic tremor | 🔴 BLOCK | 100.0% | 0.23 ms |
| **Robotic auto-typer** | Fixed 50 ms key injections, no mouse | Keystroke biometrics + missing mouse telemetry | 🔴 BLOCK | 100.0% | 0.14 ms |
| **Burst flooder** | 8 human-looking requests in ~330 ms | Poisson frequency score (suppressed for organic kinematics) | 🟡 FLAG only (0/8 blocked) | 25.0% | 0.26 ms |
| **Replay attack** | Re-sending a captured valid token | Single-use HMAC nonce | 🔴 BLOCK | 100.0% | — |
| **Natural human** | Ease-out curve, tremor, jittered timing | Biologic jerk & deceleration | 🟢 ALLOW (50/50 seeds) | 0.0% (max) | 0.54 ms |

> **Burst flooding is not blocked on its own.** When the trajectories look organic, the Poisson frequency signal only raises the risk score. Hard blocking starts at the extreme-rate limit (`SYNAPSE_MAX_REQ_10S`, default 100 requests per 10 s, which leads to a 15-minute ban) or after 4 IP strikes in 60 s (see [Configuration](CONFIGURATION.md#ip-strikes-and-bans)). Earlier versions of this table listed this row as `BLOCK 60%`. That figure could not be reproduced: the bundled attack suite had been rejecting every request at the token-binding layer since v0.10.1, so the table did not reflect the biometric layers.

## Known limits

- Short humanised bots pass more often when proof-of-work is off; keep the short-trace challenge on.
- A bot that replays recorded human traces, each once and with small changes, looks human to the behavioural layer. Exact replays are blocked (trajectory fingerprint) and repeated shapes within a session are blocked (shape hash); the rest is the job of rate limits, proof-of-work cost and account-level protections.
- There is no real touchpad, pathological-tremor or real-bot dataset yet.

## Engine micro-benchmarks

```bash
synapse-shield benchmark
```

Profiles the kinematic feature extraction, the 1D-CNN and the end-to-end evaluation on your machine (ASCII or JSON report). Timings depend on the hardware and on whether the native Rust core is loaded (`synapse-shield doctor`).
