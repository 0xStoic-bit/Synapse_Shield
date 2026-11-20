# Monitoring assets

Ready-made Grafana and Prometheus files for [shadow mode](../../docs/SHADOW_MODE.md).

| File | What it is |
| :--- | :--- |
| `grafana-shadow-cohorts.json` | Grafana dashboard: would-block rate per cohort, completed-but-would-block sessions, top rules, rule × cohort |
| `shadow-alerts.yml` | Prometheus alert rules that compare cohorts with each other and need at least 200 sessions before firing |

The server must expose Prometheus metrics (`pip install "synapse-shield[metrics]"`, scrape `GET /metrics/prometheus` with `Authorization: Bearer $SYNAPSE_ADMIN_SECRET`); see [Configuration](../../docs/CONFIGURATION.md#prometheus-metrics).

The PromQL is checked against the metric and label names in CI, but not executed. Load it in a test Prometheus before relying on it.
