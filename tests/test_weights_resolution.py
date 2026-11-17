"""Açık #40: CNN ağırlık seçimi çalışma klasöründen bağımsız olmalı, testler/kod yolları cwd'ye ağırlık yazmamalı,
gömülü CNN varsayılan olarak karara katılmamalı (shadow)."""

import logging
import os
import shutil

import numpy as np
import pytest

from synapse_shield import engine, models, train
from synapse_shield.models import BUNDLED_WEIGHTS_PATH, SynapseHybridModel

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SYNAPSE_WEIGHTS_PATH", raising=False)
    monkeypatch.delenv("SYNAPSE_CNN_MODE", raising=False)
    models._warned_cwd_paths.clear()


def _copy_with_fc2_bias(dst, bias):
    """Gömülü ağırlığın FC2 biası değiştirilmiş bir kopyası (dosyaları ayırt edebilmek için)."""
    with np.load(BUNDLED_WEIGHTS_PATH, allow_pickle=False) as data:
        arrays = {k: np.array(data[k]) for k in data.files}
    arrays["fc2_b"] = np.array([bias], dtype=arrays["fc2_b"].dtype)
    np.savez_compressed(dst, **arrays)
    return str(dst)


def test_same_weights_in_two_working_directories(tmp_path, monkeypatch, caplog):
    plain = tmp_path / "plain"
    with_local = tmp_path / "with_local"
    plain.mkdir()
    with_local.mkdir()
    _copy_with_fc2_bias(with_local / "synapse_weights.npz", 7.0)

    monkeypatch.chdir(plain)
    a = SynapseHybridModel()
    monkeypatch.chdir(with_local)
    with caplog.at_level(logging.WARNING, logger="synapse_shield.models"):
        b = SynapseHybridModel()
        SynapseHybridModel()

    assert a.weights_path == b.weights_path == BUNDLED_WEIGHTS_PATH
    np.testing.assert_array_equal(a.fc2_b, b.fc2_b)
    # cwd dosyası kullanılmadı ama bir kez (yineleme olmadan) uyarıldı
    ignored = [r for r in caplog.records if "Ignoring synapse_weights.npz" in r.getMessage()]
    assert len(ignored) == 1


def test_env_overrides_bundled_and_cwd(tmp_path, monkeypatch):
    env_file = _copy_with_fc2_bias(tmp_path / "env_weights.npz", 3.0)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _copy_with_fc2_bias(cwd / "synapse_weights.npz", 7.0)
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("SYNAPSE_WEIGHTS_PATH", env_file)

    model = SynapseHybridModel()
    assert model.weights_path == env_file
    assert float(model.fc2_b[0]) == 3.0
    assert train.get_active_weights_path() == env_file

    explicit = _copy_with_fc2_bias(tmp_path / "explicit.npz", 1.0)
    assert SynapseHybridModel(weights_path=explicit).weights_path == explicit


def test_missing_env_weights_fail_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNAPSE_WEIGHTS_PATH", str(tmp_path / "nope.npz"))
    with pytest.raises(FileNotFoundError):
        SynapseHybridModel()


def test_cnn_shadow_by_default_enforce_opt_in(monkeypatch):
    rng = np.random.default_rng(0)
    mouse, static = rng.random((60, 5)), rng.random(8)

    shadow = SynapseHybridModel()
    assert shadow.cnn_mode == "shadow"
    raw = shadow.predict_raw(mouse, static)
    assert 0.0 <= raw <= 1.0
    assert shadow.predict(mouse, static) == 0.0

    monkeypatch.setenv("SYNAPSE_CNN_MODE", "Enforce")
    enforce = SynapseHybridModel()
    assert enforce.cnn_mode == "enforce"
    assert enforce.predict(mouse, static) == raw

    monkeypatch.setenv("SYNAPSE_CNN_MODE", "bogus")
    assert SynapseHybridModel().cnn_mode == "shadow"


def _human_like_telemetry():
    moves = [{"x": 100 + i * 7 + (i % 3), "y": 200 + int(30 * np.sin(i / 6.0)), "t": 1000 + i * 31} for i in range(60)]
    last = moves[-1]
    return {
        "mouse_movements": moves,
        "clicks": [{"x": last["x"], "y": last["y"], "t": last["t"] + 90}],
        "keystrokes": [],
        "scrolls": [],
        "browser": {"webdriver": False, "screen_width": 1920, "screen_height": 1080, "plugins_length": 5,
                    "touch_supported": False},
    }


def test_shadow_cnn_cannot_drive_the_engine_decision(monkeypatch):
    """CNN tek sinyal olarak engel gerekçesi olamaz: shadow modunda ham çıktı 1.0 olsa bile ai_score 0."""
    model = SynapseHybridModel(cnn_mode="shadow")
    monkeypatch.setattr(model, "predict_raw", lambda *_: 1.0)
    monkeypatch.setattr(engine, "_ai_model", model)
    _, _, reasons, details = engine.analyze_behavior(_human_like_telemetry())
    assert details["ai_score"] == 0.0
    assert not any("1D-CNN AI Engine Confidence" in r for r in reasons)

    enforced = SynapseHybridModel(cnn_mode="enforce")
    monkeypatch.setattr(enforced, "predict_raw", lambda *_: 0.9)
    monkeypatch.setattr(engine, "_ai_model", enforced)
    _, _, _, details = engine.analyze_behavior(_human_like_telemetry())
    assert details["ai_score"] == pytest.approx(90.0)


def test_retrain_without_target_writes_nothing_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = train.retrain_fc2(epochs=1, bootstrap=True)
    assert res["success"] is False
    assert "SYNAPSE_WEIGHTS_PATH" in res["error"]
    assert not list(tmp_path.glob("*.npz"))


def test_retrain_writes_only_to_env_target(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    target = tmp_path / "out" / "w.npz"
    target.parent.mkdir()
    shutil.copy2(BUNDLED_WEIGHTS_PATH, target)
    monkeypatch.setenv("SYNAPSE_WEIGHTS_PATH", str(target))
    base_mtime = os.path.getmtime(BUNDLED_WEIGHTS_PATH)

    res = train.retrain_fc2(epochs=1, bootstrap=True)

    assert res["success"] is True
    assert not list(cwd.iterdir())
    assert os.path.getmtime(BUNDLED_WEIGHTS_PATH) == base_mtime
    assert SynapseHybridModel().weights_path == str(target)


def test_output_path_resolution_rules(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="No output path"):
        train.resolve_output_path()
    monkeypatch.setenv("SYNAPSE_WEIGHTS_PATH", str(tmp_path / "env.npz"))
    assert train.resolve_output_path() == str(tmp_path / "env.npz")
    assert train.resolve_output_path(str(tmp_path / "o.npz")) == str(tmp_path / "o.npz")
    with pytest.raises(ValueError, match="must be .npz"):
        train.resolve_output_path(str(tmp_path / "o.sh"))


def test_degenerate_retrain_is_not_saved(tmp_path, monkeypatch):
    """Doymuş (sabit çıktılı) FC2 kaydedilmez; repo kökündeki yerel ağırlık tam olarak böyle bozulmuştu."""
    target = tmp_path / "w.npz"
    shutil.copy2(BUNDLED_WEIGHTS_PATH, target)
    before = target.read_bytes()
    monkeypatch.setenv("SYNAPSE_WEIGHTS_PATH", str(target))
    monkeypatch.setattr(train, "sigmoid", lambda x: np.zeros_like(np.asarray(x, dtype=float)))

    res = train.retrain_fc2(epochs=1, bootstrap=True)

    assert res["success"] is False
    assert "degenerate" in res["error"]
    assert target.read_bytes() == before


def _root_weights_state():
    path = os.path.join(REPO_ROOT, "synapse_weights.npz")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


_ROOT_STATE_AT_IMPORT = _root_weights_state()


def test_repo_root_weights_untouched_by_this_module():
    """Bu modüldeki eğitimler repo kökündeki synapse_weights.npz'yi oluşturmaz/değiştirmez (son çalışan test)."""
    assert _root_weights_state() == _ROOT_STATE_AT_IMPORT
