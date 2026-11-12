"""The shipped Grafana dashboard and Prometheus alert rules must only reference metrics and labels that exist."""

import json
import re
from pathlib import Path

import pytest

from synapse_shield import metrics

pytest.importorskip("prometheus_client")

MON = Path(__file__).resolve().parents[1] / "deploy" / "monitoring"
DASHBOARD = MON / "grafana-shadow-cohorts.json"
ALERTS = MON / "shadow-alerts.yml"

SELECTOR = re.compile(r"(synapse_\w+)\s*\{([^}]*)\}")
METRIC = re.compile(r"\b(synapse_[a-z_]+_total|synapse_[a-z_]+_seconds)\b")
BY = re.compile(r"\bby\s*\(([^)]*)\)")
LABEL = re.compile(r"(\w+)\s*(?:=~|!=|=)")


def _labels_of(metric_name: str) -> set[str]:
    return set(getattr(metrics, metric_name)._labelnames)


def _check_expr(expr: str) -> None:
    names = set(METRIC.findall(expr))
    assert names, f"no synapse metric in: {expr}"
    for n in names:
        assert getattr(metrics, n, None) is not None, f"unknown metric {n}"
    for name, body in SELECTOR.findall(expr):
        for label in LABEL.findall(body):
            assert label in _labels_of(name), f"{name} has no label {label!r}"
    allowed = set().union(*(_labels_of(n) for n in names))
    for group in BY.findall(expr):
        for label in (x.strip() for x in group.split(",") if x.strip()):
            assert label in allowed, f"'by ({label})' is not a label of {sorted(names)}"


def _exprs_from_dashboard(dash: dict) -> list[str]:
    out = [t["expr"] for p in dash["panels"] for t in p.get("targets", [])]
    for v in dash["templating"]["list"]:
        out.append(v["query"]["query"])
    return out


def test_dashboard_is_valid_json_with_panels():
    dash = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert dash["uid"] and dash["panels"]
    ids = [p["id"] for p in dash["panels"]]
    assert len(ids) == len(set(ids)), "duplicate panel ids"


def test_dashboard_expressions_reference_real_metrics_and_labels():
    dash = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    for expr in _exprs_from_dashboard(dash):
        # label_values(metric, label) is a variable query, not PromQL
        m = re.fullmatch(r"label_values\((synapse_\w+),\s*(\w+)\)", expr.strip())
        if m:
            assert m.group(2) in _labels_of(m.group(1))
            continue
        _check_expr(expr)


def test_dashboard_parentheses_are_balanced():
    dash = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    for expr in _exprs_from_dashboard(dash):
        assert expr.count("(") == expr.count(")") and expr.count("{") == expr.count("}"), expr


def test_alert_rules_reference_real_metrics_and_labels():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    rules = [r for g in doc["groups"] for r in g["rules"]]
    assert {r["alert"] for r in rules} >= {"SynapseShadowCohortFalsePositives", "SynapseShadowCohortBlockRateOutlier"}
    for r in rules:
        _check_expr(r["expr"])
        assert r["expr"].count("(") == r["expr"].count(")")
        assert r["labels"]["severity"] and r["annotations"]["summary"]
        assert "200" in r["expr"], "every alert needs a minimum sample size"


def test_all_shadow_metrics_are_documented_in_readme():
    readme = (MON.parents[1] / "README.md").read_text(encoding="utf-8")
    for name in ("synapse_shadow_cohort_total", "synapse_shadow_outcomes_total", "synapse_shadow_rules_total"):
        assert name in readme
