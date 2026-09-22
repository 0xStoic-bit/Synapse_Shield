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
