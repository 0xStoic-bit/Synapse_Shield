"""scripts/sri_hash.py: the SRI value must match the real published synapse-sdk.js byte for byte."""

import base64
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sri_hash.py"
SDK = ROOT / "src" / "synapse_shield" / "static" / "synapse-sdk.js"


def _load():
    spec = importlib.util.spec_from_file_location("sri_hash", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _expected(path: Path) -> str:
    # Independent reference: what a browser computes for integrity="sha384-..." (base64 of the raw sha384 digest).
    return "sha384-" + base64.b64encode(hashlib.sha384(path.read_bytes()).digest()).decode()


def test_default_path_is_the_published_sdk():
    assert _load().DEFAULT_SDK.resolve() == SDK.resolve()
    assert SDK.is_file()


def test_hash_matches_the_real_sdk_file():
    value = _load().sri_hash(SDK)
    assert value == _expected(SDK)
    assert value.startswith("sha384-")
    assert len(base64.b64decode(value.split("-", 1)[1])) == 48


def test_known_vector():
    # sha384("") is a published constant; guards against hex/base64 or text-mode mixups.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        empty = Path(d) / "empty.js"
        empty.write_bytes(b"")
        assert _load().sri_hash(empty) == "sha384-OLBgp1GsljhM2TJ+sbHjaiH9txEUvgdDTAzHv2P24donTt6/529l+9Ua0vFImLlb"


def test_hash_changes_with_a_single_byte(tmp_path):
    mod = _load()
    a = tmp_path / "a.js"
    a.write_bytes(SDK.read_bytes())
    before = mod.sri_hash(a)
    a.write_bytes(SDK.read_bytes() + b"\n")
    assert mod.sri_hash(a) != before


def test_cli_prints_integrity_and_tag_for_the_real_file():
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--src", "https://cdn.example.com/synapse-sdk.js"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    expected = _expected(SDK)
    assert out[0] == f'integrity="{expected}"'
    assert out[1] == (
        f'<script src="https://cdn.example.com/synapse-sdk.js" integrity="{expected}" crossorigin="anonymous"></script>'
    )


def test_cli_check_mode():
    ok = subprocess.run([sys.executable, str(SCRIPT), "--check", _expected(SDK)], capture_output=True, text=True)
    assert ok.returncode == 0
    bad = subprocess.run([sys.executable, str(SCRIPT), "--check", "sha384-AAAA"], capture_output=True, text=True)
    assert bad.returncode == 1


def test_rejects_unsupported_algorithm():
    with pytest.raises(ValueError):
        _load().sri_hash(SDK, "md5")
