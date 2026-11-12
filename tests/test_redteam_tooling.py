"""
Red-team tooling and CLI.

* live_attacker: the 9-vector attack suite (`synapse-shield test`) is executed end-to-end against
  the in-process FastAPI app. urllib is routed to a TestClient bound to 127.0.0.1 (a trusted proxy,
  exactly like the live dev server), so X-Forwarded-For per-attack IPs are honoured. Each attack's
  verdict is asserted, turning the CLI suite into a regression test. No network traffic is made.
* redteam_plugin: registry ordering, orchestrator lifecycle, plugin discovery, and every bundled
  plugin executed against the same in-process app.
* cli: every sub-command is dispatched with its heavy target stubbed out.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import types
import urllib.error
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from synapse_shield import live_attacker, redteam_plugin


# --------------------------------------------------------------------------------------------
# In-process urllib -> FastAPI bridge
# --------------------------------------------------------------------------------------------


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def inprocess_server(monkeypatch):
    from synapse_shield.main import app

    client = TestClient(app, client=("127.0.0.1", 50000))
    seen: list[tuple[str, str]] = []

    def fake_urlopen(req, *a, **k):
        if isinstance(req, str):
            url, method, data, headers = req, "GET", None, {}
        else:
            url, method, data = req.full_url, req.get_method(), req.data
            headers = dict(req.header_items())
        parsed = urllib.parse.urlsplit(url)
        assert parsed.hostname == "127.0.0.1" and parsed.port == 8000, f"unexpected target {url}"
        seen.append((method, parsed.path))
        r = client.request(method, parsed.path, content=data, headers=headers)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(url, r.status_code, r.reason_phrase, r.headers, io.BytesIO(r.content))
        return _Resp(r.content)

    monkeypatch.setattr(live_attacker.urllib.request, "urlopen", fake_urlopen)
    # Skipping sleeps must not freeze the clock: a no-op sleep hid the Stale Telemetry bug
    # (the real CLI waits 1.6 s per vector, so suite-start timestamps went stale). Advance a
    # shared virtual clock instead; the in-process server reads the same time.time().
    import time as _time

    real_time = _time.time
    offset = [0.0]

    def fake_sleep(s):
        offset[0] += s

    monkeypatch.setattr(_time, "time", lambda: real_time() + offset[0])
    monkeypatch.setattr(live_attacker.time, "sleep", fake_sleep)
    return seen


# --------------------------------------------------------------------------------------------
# live_attacker
# --------------------------------------------------------------------------------------------


def test_live_attack_suite_verdicts(inprocess_server, monkeypatch, capsys):
    results: dict[int, tuple[str, dict, bool]] = {}
    real_print = live_attacker.print_result

    def capture(num, title, res, expected_blocked=True):
        results[num] = (title, res, expected_blocked)
        return real_print(num, title, res, expected_blocked)

    monkeypatch.setattr(live_attacker, "print_result", capture)
    # The human control traces are synthetic (sine + Gaussian noise). Pin the seed so this
    # regression test is deterministic (an unseeded live run also passed 10/10 in review).
    import random

    monkeypatch.setattr(live_attacker, "random", random.Random(20261106))
    assert live_attacker.main() == 0

    assert sorted(results) == list(range(1, 10)), "all 9 attack vectors must run"
    for num, (title, res, expected_blocked) in results.items():
        blocked = res.get("classification") == "Bot" or res.get("bot_score", 0.0) >= 50.0
        assert blocked == expected_blocked, f"#{num} {title}: {res}"
        # Every vector must be judged by the layer it targets, never short-circuited by the
        # challenge client-binding check (that would mean the suite itself is misconfigured).
        assert res.get("threat_type") != "TOKEN_RELAY_ATTACK", f"#{num} {title} hit relay binding: {res}"
    # Replay (#9) must be stopped by the single-use nonce.
    assert "replay" in json.dumps(results[9][1], ensure_ascii=False).lower()
    out = capsys.readouterr().out
    assert "BAŞARISIZ" not in out
    assert ("POST", "/api/score") in inprocess_server


def test_send_attack_error_shapes(monkeypatch):
    def http_error_non_json(req, *a, **k):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))

    monkeypatch.setattr(live_attacker.urllib.request, "urlopen", http_error_non_json)
    res = live_attacker.send_attack("x", {"token": "t"})
    assert res["classification"] == "Bot" and "HTTP 502" in res["reasons"][0]

    def conn_refused(req, *a, **k):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(live_attacker.urllib.request, "urlopen", conn_refused)
    res = live_attacker.send_attack("x", {"token": "t"})
    assert res["status"] == "error" and res["network_latency_ms"] == 0.0
    # A transport failure is not a verdict: it must never be reported as a blocked bot.
    assert res["classification"] == "Error" and res["bot_score"] == 0.0
    # No server: challenge fetch fails -> empty token, and clear_bans swallows the error.
    assert live_attacker.get_challenge() is None
    assert live_attacker.make_token({}) == ""
    live_attacker.clear_bans()


def test_print_result_reports_false_negative_and_threat_tags(capsys):
    live_attacker.print_result(1, "t", {"bot_score": 10.0, "classification": "Human"}, expected_blocked=True)
    live_attacker.print_result(
        2, "t", {"bot_score": 90.0, "classification": "Bot", "threat_attribution": ["webdriver"]},
        expected_blocked=False,
    )
    out = capsys.readouterr().out
    assert out.count("BAŞARISIZ") == 2
    assert "webdriver" in out


def test_live_attack_suite_without_server_fails_loudly(monkeypatch, capsys):
    def conn_refused(req, *a, **k):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(live_attacker.urllib.request, "urlopen", conn_refused)
    assert live_attacker.main() == 2
    out = capsys.readouterr().out
    assert "KALKAN BAŞARILI" not in out and "GEÇTİ" not in out


def test_print_result_transport_error_is_not_a_pass(capsys):
    res = {"status": "error", "classification": "Error", "bot_score": 0.0, "reasons": ["refused"]}
    assert live_attacker.print_result(1, "t", res, expected_blocked=True) is None
    assert "KALKAN BAŞARILI" not in capsys.readouterr().out


# --------------------------------------------------------------------------------------------
# redteam_plugin
# --------------------------------------------------------------------------------------------


@pytest.fixture
def isolated_registry(monkeypatch):
    reg: dict = {}
    monkeypatch.setattr(redteam_plugin, "ATTACK_REGISTRY", reg)
    return reg


def test_registry_orders_by_weight_and_lifecycle(isolated_registry):
    order: list[str] = []

    def plugin(name, cat, weight):
        @redteam_plugin.redteam_attack(cat, weight=weight)
        async def f(state):
            order.append(name)
            state.setdefault("seen", []).append(name)
            if name == "boom":
                raise RuntimeError("plugin failure is captured, not raised")
            return name

        return f

    plugin("teardown", "teardown", 1)
    plugin("low", "bot", 1)
    plugin("high", "bot", 50)
    plugin("init", "init", 1)
    plugin("boom", "tamper", 1)

    assert [w for w, _ in isolated_registry["bot"]] == [50, 1]

    orch = redteam_plugin.SynapseRedTeamOrchestrator()
    assert asyncio.run(orch.run_category("missing")) == []
    res = asyncio.run(orch.run_category("tamper"))
    assert isinstance(res[0], RuntimeError)

    order.clear()
    asyncio.run(orch.run_full_scenario())
    assert order[0] == "init" and order[-1] == "teardown"
    assert order[1:3] == ["high", "low"]
    assert "boom" in orch.shared_state["seen"]


def test_discover_plugins_imports_package_modules(isolated_registry, tmp_path, monkeypatch):
    pkg = tmp_path / "rt_plugins_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "custom.py").write_text(
        "from synapse_shield.redteam_plugin import redteam_attack\n"
        "@redteam_attack('custom', weight=3)\n"
        "async def custom(state):\n"
        "    return 'ok'\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    redteam_plugin.SynapseRedTeamOrchestrator().discover_plugins("rt_plugins_pkg")
    assert "custom" in isolated_registry
    monkeypatch.delitem(sys.modules, "rt_plugins_pkg.custom", raising=False)
    monkeypatch.delitem(sys.modules, "rt_plugins_pkg", raising=False)


def test_bundled_plugins_are_blocked_by_the_server(inprocess_server, monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(redteam_plugin.asyncio, "sleep", lambda s: real_sleep(0))

    bundled = {
        "linear_bot_plugin", "bezier_stealth_plugin", "keystroke_injection_plugin",
        "stealth_tamper_plugin", "poisson_flooder_plugin", "replay_attack_plugin",
        "mobile_emulator_spoof_plugin",
    }
    registered = {f.__name__ for funcs in redteam_plugin.ATTACK_REGISTRY.values() for _, f in funcs}
    assert bundled <= registered

    async def run_all():
        return {name: await getattr(redteam_plugin, name)({}) for name in sorted(bundled)}

    results = asyncio.run(run_all())
    flood = results.pop("poisson_flooder_plugin")
    assert len(flood) == 15 and all(r["classification"] == "Bot" for r in flood)
    for name, res in results.items():
        assert res["classification"] == "Bot" or res.get("bot_score", 0) >= 50, f"{name} bypassed: {res}"
        assert res.get("threat_type") != "TOKEN_RELAY_ATTACK", f"{name} hit relay binding: {res}"


def test_replay_plugin_without_server_returns_none(monkeypatch):
    monkeypatch.setattr(live_attacker, "get_challenge", lambda *a: None)
    assert asyncio.run(redteam_plugin.replay_attack_plugin({})) is None


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _run_cli(monkeypatch, *argv):
    from synapse_shield import cli

    monkeypatch.setattr(sys, "argv", ["synapse-shield", *argv])
    return cli.main()


def test_cli_run_starts_uvicorn(monkeypatch, capsys):
    calls = []
    fake = types.SimpleNamespace(run=lambda *a, **k: calls.append((a, k)))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    _run_cli(monkeypatch, "run", "--host", "127.0.0.1", "--port", "9001")
    assert calls == [(("synapse_shield.main:app",), {"host": "127.0.0.1", "port": 9001, "reload": True})]
    _run_cli(monkeypatch)  # no sub-command defaults to "run"
    assert calls[-1][1]["port"] == 8000
    assert "Starting Synapse Shield" in capsys.readouterr().out


def test_cli_run_without_uvicorn_exits(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, "run")
    assert exc.value.code == 1
    assert "Uvicorn is required" in capsys.readouterr().out


def test_cli_dispatches_subcommands(monkeypatch):
    from synapse_shield import benchmark, doctor, train

    got: dict = {}
    monkeypatch.setattr(live_attacker, "main", lambda: got.setdefault("test", True) and 0)
    monkeypatch.setattr(benchmark, "run_micro_benchmarks", lambda **k: got.setdefault("benchmark", k))
    monkeypatch.setattr(train, "retrain_fc2", lambda **k: got.setdefault("retrain", k))
    monkeypatch.setattr(doctor, "run_doctor", lambda: 3)

    with pytest.raises(SystemExit) as test_exit:
        _run_cli(monkeypatch, "test")
    assert test_exit.value.code == 0  # the suite's return value becomes the process exit code
    _run_cli(monkeypatch, "benchmark", "-n", "7", "-e", "out.json")
    _run_cli(monkeypatch, "retrain", "--bootstrap", "--epochs", "2", "--output", "w.npz")
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, "doctor")

    assert got["test"] is True
    assert got["benchmark"] == {"iterations": 7, "export_path": "out.json"}
    assert got["retrain"] == {"epochs": 2, "bootstrap": True, "output_path": "w.npz"}
    assert exc.value.code == 3


def test_cli_redteam_full_and_category(monkeypatch):
    ran: list = []

    class FakeOrch:
        async def run_category(self, c):
            ran.append(c)

        async def run_full_scenario(self):
            ran.append("full")

    monkeypatch.setattr(redteam_plugin, "SynapseRedTeamOrchestrator", FakeOrch)
    monkeypatch.setattr(live_attacker, "server_reachable", lambda: True)
    _run_cli(monkeypatch, "redteam")
    _run_cli(monkeypatch, "redteam", "--category", "crypto")
    assert ran == ["full", "crypto"]


def test_cli_redteam_unreachable_server_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(live_attacker, "server_reachable", lambda: False)
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, "redteam")
    assert exc.value.code == 2
    assert "unreachable" in capsys.readouterr().err


def test_cli_run_no_reload_flag(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=lambda *a, **k: calls.append(k)))
    _run_cli(monkeypatch, "run", "--no-reload")
    assert calls[-1]["reload"] is False


def test_clear_bans_sends_admin_secret(monkeypatch):
    seen = {}

    def fake_urlopen(req, *a, **k):
        seen.update(dict(req.header_items()))
        return _Resp(b"{}")

    monkeypatch.setattr(live_attacker.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SYNAPSE_ADMIN_SECRET", "s3cret")
    live_attacker.clear_bans()
    assert seen.get("X-admin-secret") == "s3cret"


def test_score_decision_field_on_challenge_and_expired_paths():
    import inspect

    from synapse_shield import main

    src = inspect.getsource(main.score_telemetry)
    assert '"decision": "challenge"' in src and '"decision": "error"' in src


def test_cli_telemetry(monkeypatch, capsys):
    import synapse_shield

    fake_rs = types.SimpleNamespace(get_state_engine_stats_rs=lambda: {"nonces": 1})
    monkeypatch.setattr(synapse_shield, "synapse_core_rs", fake_rs, raising=False)
    monkeypatch.setitem(sys.modules, "synapse_shield.synapse_core_rs", fake_rs)
    _run_cli(monkeypatch, "telemetry")
    assert json.loads(capsys.readouterr().out.split("\n", 1)[1]) == {"nonces": 1}

    def broken():
        raise RuntimeError("engine offline")

    fake_rs.get_state_engine_stats_rs = broken
    _run_cli(monkeypatch, "telemetry")
    assert "Error reading telemetry: engine offline" in capsys.readouterr().out

    monkeypatch.setattr(synapse_shield, "synapse_core_rs", None, raising=False)
    monkeypatch.setitem(sys.modules, "synapse_shield.synapse_core_rs", None)
    _run_cli(monkeypatch, "telemetry")
    out = capsys.readouterr().out
    assert "not available" in out or "Error reading telemetry" in out


def test_cli_help_smoke():
    import os
    import subprocess

    # Do not rely on an editable install: point the child interpreter at this checkout's src/.
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env = {**os.environ, "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", "")}
    r = subprocess.run(
        [sys.executable, "-m", "synapse_shield.cli", "--help"], capture_output=True, text=True, timeout=60, env=env
    )
    assert r.returncode == 0
    for cmd in ("run", "test", "benchmark", "retrain", "redteam", "telemetry", "doctor"):
        assert cmd in r.stdout
