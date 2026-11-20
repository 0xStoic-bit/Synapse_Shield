# Shadow mode

Run Synapse Shield on real traffic **without blocking anyone**, and find out what it would have done.
Back to the [documentation index](README.md).

## Turn it on

Every adapter accepts `mode="shadow"`. Requests are scored as usual, but a would-be block is returned as `action="shadow_block"` with `allowed=True` and an `X-Synapse-Decision: shadow-block` header, so your app keeps working.

```python
from synapse_shield import evaluate_synapse_request_sync, report_shadow_outcome

decision = evaluate_synapse_request_sync(ip, ua, token, mode="shadow")
# ... later, once your app knows what happened (e.g. the login succeeded):
report_shadow_outcome(decision, completed=True)
```

## Why per-cohort counters

A single global block rate can hide one broken group (touch, high-DPI, zoomed browsers). In shadow mode every behavioural verdict is also counted per coarse cohort, with no pointer traces stored:

| Metric | Labels |
| --- | --- |
| `synapse_shadow_cohort_total` | `action` (`allow`/`block`), `input` (`touch`/`pointer`/`keyboard`/`none`), `dpr` (`lt1`/`1x`/`1.25-1.9x`/`2x+`/`unknown`) |
| `synapse_shadow_outcomes_total` | `simulated_action`, `input`, `dpr`, `outcome` (`completed`/`abandoned`) |
| `synapse_shadow_rules_total` | `input`, `dpr`, `rule` (stable rule code such as `stutter`, `curvature`, `keystroke_superhuman`) |

`pointer` covers mouse and trackpad (they cannot be told apart reliably); `dpr` also separates zoomed sessions.

A high `simulated_action="block"` × `outcome="completed"` count in one cohort means enforcing would hurt real users there, even if the global rate looks fine.

`SynapseDecision.rule_codes` (and `to_dict()["rule_codes"]`) list the same codes per verdict, so a log line can say *which* rule would have blocked.

## Dashboards and alerts

[`deploy/monitoring/`](../deploy/monitoring/README.md) has a Grafana dashboard and Prometheus alert rules for these metrics.

## Replay your own recordings offline

No server, no token, no network:

```bash
synapse-shield replay ./recordings --label human   # false-positive rate, and the rules and cohorts behind the blocks
synapse-shield replay ./bots.jsonl --label bot     # detection rate
```

Input is `.json` / `.jsonl` telemetry (the SDK payload, or an object with a `telemetry` key), a file or a folder.
