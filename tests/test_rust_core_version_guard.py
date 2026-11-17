"""
Stale native core guard (#32).

v0.10.8 shipped with two "known" test failures that were really a gitignored 0.10.5 .pyd left in
src/synapse_shield/ and loaded instead of the fresh build. These tests make that loud: the Rust
core that features.py uses must report the package version, and `synapse-shield doctor` must FAIL
(with the load path) when it does not.
"""

import os

import pytest

from synapse_shield import doctor, features
from synapse_shield._version import __version__

core = features.synapse_core_rs
requires_core = pytest.mark.skipif(core is None, reason="Rust core (synapse_core_rs) not built")


@requires_core
def test_loaded_rust_core_matches_package_version():
    status = doctor.rust_core_version_status()
    assert status is not None
    assert status["core_version"] == core.get_core_version()
    assert status["package_version"] == __version__
    assert status["matches"], (
        f"Stale native core: {status['core_version']} loaded from {status['path']} "
        f"but package is {__version__}"
    )
    assert os.path.isfile(status["path"])


@requires_core
def test_doctor_passes_and_reports_load_path_for_matching_core():
    result = doctor.check_rust_simd_core()
    assert result["passed"] is True
    assert result["warning"] is False
    assert core.get_core_version() in result["message"]
    assert doctor.rust_core_version_status()["path"] in result["message"]


@requires_core
def test_doctor_fails_on_stale_core(monkeypatch):
    # Reproduce the v0.10.8 incident: the real module, reporting an older build's version string.
    real_suffix = core.get_core_version().split("-", 1)[1]
    monkeypatch.setattr(core, "get_core_version", lambda: f"0.10.5-{real_suffix}")

    result = doctor.check_rust_simd_core()
    assert result["passed"] is False
    assert "0.10.5" in result["message"]
    assert __version__ in result["message"]
    assert doctor.rust_core_version_status()["path"] in result["message"]


def test_version_status_is_none_without_core(monkeypatch):
    monkeypatch.setattr(features, "synapse_core_rs", None)
    assert doctor.rust_core_version_status() is None
