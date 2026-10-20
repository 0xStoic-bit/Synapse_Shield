import os
import tempfile

import numpy as np
import pytest

from synapse_shield.models import SynapseHybridModel


def test_model_loading_missing_weights():
    with tempfile.TemporaryDirectory() as tmpdirname:
        missing_weights = os.path.join(tmpdirname, "missing.npz")
        with pytest.raises(FileNotFoundError):
            SynapseHybridModel(weights_path=missing_weights)


def test_model_inference_shape_and_range():
    model = SynapseHybridModel()

    # Dummy data
    mouse_tensor = [[0.0 for _ in range(5)] for _ in range(60)]
    static_vector = [0.0 for _ in range(8)]

    prob = model.predict(mouse_tensor, static_vector)

    # Olasılık değeri her zaman 0.0 ile 1.0 arasında olmalıdır
    assert isinstance(prob, float)
    assert 0.0 <= prob <= 1.0


def test_model_inference_with_random_data():
    model = SynapseHybridModel()

    mouse_tensor = np.random.rand(60, 5).tolist()
    static_vector = np.random.rand(8).tolist()

    prob = model.predict(mouse_tensor, static_vector)
    assert 0.0 <= prob <= 1.0


def test_model_vectorized_conv_parity():
    """Verify that vectorized sliding window matrix multiplication matches manual conv loop."""
    model = SynapseHybridModel()

    mouse = np.random.rand(5, 60).astype(np.float32)
    padded_mouse = np.pad(mouse, ((0, 0), (1, 1)), mode="constant", constant_values=0.0)

    # 1. Manual loop reference
    c_out_loop = np.zeros((16, 60), dtype=np.float32)
    for j in range(60):
        window = padded_mouse[:, j : j + 3]
        c_out_loop[:, j] = np.sum(model.conv_w * window, axis=(1, 2)) + model.conv_b

    # 2. Vectorized BLAS matrix multiplication
    windows = np.lib.stride_tricks.sliding_window_view(padded_mouse, window_shape=3, axis=1)
    windows_flat = windows.transpose(1, 0, 2).reshape(60, 15)
    c_out_vec = np.dot(model.conv_w_flat, windows_flat.T) + model.conv_b_col

    np.testing.assert_allclose(c_out_loop, c_out_vec, rtol=1e-5, atol=1e-5)
