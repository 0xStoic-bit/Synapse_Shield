"""Offline replay: load recorded telemetry, report block rate, rules and cohorts without a server."""

import json
import os
import subprocess
import sys
from pathlib import Path

from synapse_shield import replay as rp
from synapse_shield.adversarial import generate_adversarial_telemetry_batch, generate_synthetic_human_batch

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "synapse_shield.cli", "replay", *args], capture_output=True,
                          text=True, encoding="utf-8", env=env, cwd=str(ROOT), timeout=120)


def test_bots_are_replayed_as_blocked_with_rule_codes():
    bots = generate_adversarial_telemetry_batch(30)
    r = rp.replay(bots)
    assert r["sessions"] == len(bots)
    assert r["block_rate"] > 0.9
    assert r["rules"] and "other" not in r["rules"]


def test_synthetic_humans_are_mostly_allowed():
    r = rp.replay(generate_synthetic_human_batch(30))
    assert r["block_rate"] < 0.2


def test_threshold_changes_the_verdict():
    humans = generate_synthetic_human_batch(10)
    assert rp.replay(humans, threshold=0.0)["blocked"] == len(humans)


def test_cohorts_cover_every_session():
    r = rp.replay(generate_synthetic_human_batch(12) + generate_adversarial_telemetry_batch(12))
    assert sum(v["sessions"] for v in r["cohorts"].values()) == r["sessions"]
    assert sum(v["blocked"] for v in r["cohorts"].values()) == r["blocked"]


def test_empty_input_does_not_divide_by_zero():
    r = rp.replay([])
    assert r["sessions"] == 0 and r["block_rate"] == 0.0
    assert "No telemetry objects found" in rp.format_report(r)


def test_loading_accepts_object_list_jsonl_envelope_and_directory(tmp_path):
    items = generate_adversarial_telemetry_batch(4)
    (tmp_path / "one.json").write_text(json.dumps(items[0]), encoding="utf-8")
    (tmp_path / "many.json").write_text(json.dumps(items[1:3]), encoding="utf-8")
    (tmp_path / "lines.jsonl").write_text("\n".join(json.dumps({"telemetry": t}) for t in items[3:]) + "\n",
                                          encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "junk.json").write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    assert len(rp.load_telemetry(str(tmp_path))) == 4
    assert len(rp.load_telemetry(str(tmp_path / "many.json"))) == 2


def test_hidden_directories_are_skipped(tmp_path):
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "x.json").write_text(json.dumps(generate_adversarial_telemetry_batch(1)[0]), encoding="utf-8")
    assert rp.load_telemetry(str(tmp_path)) == []


def test_report_labels():
    r = rp.replay(generate_adversarial_telemetry_batch(10))
    assert "detection rate (TPR)" in rp.format_report(r, "bot")
    assert "false-positive rate" in rp.format_report(r, "human")
    assert "TPR" not in rp.format_report(r)


def test_replay_touches_no_storage(monkeypatch):
    from synapse_shield import storage

    def boom(*a, **k):
        raise AssertionError("replay must not use storage")

    monkeypatch.setattr(storage, "get_storage", boom)
    rp.replay(generate_synthetic_human_batch(3))


def test_cli_text_and_json(tmp_path):
    f = tmp_path / "bots.json"
    f.write_text(json.dumps(generate_adversarial_telemetry_batch(10)), encoding="utf-8")
    out = _run_cli(str(f), "--label", "bot")
    assert out.returncode == 0, out.stderr
    assert "would be blocked" in out.stdout and "TPR" in out.stdout
    js = _run_cli(str(f), "--json")
    data = json.loads(js.stdout)
    assert data["sessions"] == 10 and "rules" in data and "cohorts" in data


def test_cli_missing_file_exits_2(tmp_path):
    out = _run_cli(str(tmp_path / "nope.json"))
    assert out.returncode == 2 and "Could not read telemetry" in out.stderr


def test_cli_bad_json_exits_2(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json", encoding="utf-8")
    assert _run_cli(str(f)).returncode == 2
