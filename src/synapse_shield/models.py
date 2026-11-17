"""
Synapse Shield - v0.6.2 The Micro-Brain (Pure NumPy Inference Engine)
Sıfır Bağımlılık (Zero-Dependency) prensibiyle 1D-CNN + Late Fusion
yapay zeka modelini çalıştırır. PyTorch veya TensorFlow gerektirmez.
"""

import logging
import os

import numpy as np

logger = logging.getLogger("synapse_shield.models")

WEIGHTS_ENV = "SYNAPSE_WEIGHTS_PATH"
CNN_MODE_ENV = "SYNAPSE_CNN_MODE"
BUNDLED_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "weights.npz")
# Eski sürümler (v0.7.9-v0.10.8) çalışma klasöründeki bu dosyayı örtük olarak yüklüyordu. Artık YÜKLENMEZ:
# aynı kurulum repo kökünden başka, Docker'dan başka model çalıştırıyordu (açık #40). Yalnızca uyarılır.
LEGACY_CWD_WEIGHTS_NAME = "synapse_weights.npz"

# CNN karar modu. "shadow" (varsayılan): olasılık hesaplanır (predict_raw) ama karara katkısı 0'dır.
# "enforce": ham olasılık karara girer (eski davranış). Gömülü ağırlık yalnızca sentetik gürültüyle eğitildi
# (scripts/train_sequence_ai.py); gerçek insan kayıtlarının yeniden oynatımında (research/human_sim/
# replay_sapimouse.py) insanları engellerken bilinen bot desenlerinde (bot_tpr.py) ek tespit sağlamadı.
# Kendi verinizle eğitip doğrulamadığınız bir ağırlık tek başına engelleme gerekçesi olmamalı.
CNN_MODES = ("shadow", "enforce")
DEFAULT_CNN_MODE = "shadow"

_warned_cwd_paths: set[str] = set()


def _warn_ignored_cwd_weights() -> None:
    cwd_path = os.path.abspath(os.path.join(os.getcwd(), LEGACY_CWD_WEIGHTS_NAME))
    if cwd_path in _warned_cwd_paths or not os.path.exists(cwd_path):
        return
    _warned_cwd_paths.add(cwd_path)
    logger.warning(
        "[Synapse Shield] Ignoring %s in the working directory: weights are no longer loaded implicitly from "
        "the current directory. Set %s=%s to use them. Loading the bundled weights instead.",
        LEGACY_CWD_WEIGHTS_NAME,
        WEIGHTS_ENV,
        cwd_path,
    )


def resolve_weights_path(weights_path=None) -> str:
    """Hangi ağırlık dosyasının yükleneceği; çalışma klasöründen bağımsızdır.

    Öncelik: (1) açık ``weights_path`` parametresi, (2) ``SYNAPSE_WEIGHTS_PATH`` ortam değişkeni,
    (3) paket içi ``weights.npz``. Açıkça seçilmiş bir yol yoksa ``FileNotFoundError`` (sessizce başka
    bir modele düşmek, yanlış modelin fark edilmeden çalışmasına yol açar).
    """
    if weights_path is not None:
        return os.fspath(weights_path)
    env_path = os.environ.get(WEIGHTS_ENV, "").strip()
    if env_path:
        if not os.path.exists(env_path):
            raise FileNotFoundError(f"[Synapse Shield] {WEIGHTS_ENV} points to a missing file: {env_path}")
        return env_path
    _warn_ignored_cwd_weights()
    return BUNDLED_WEIGHTS_PATH


def resolve_cnn_mode(mode=None) -> str:
    """CNN karar modu: parametre > ``SYNAPSE_CNN_MODE`` > ``shadow``. Geçersiz değer ``shadow`` olur (uyarıyla)."""
    raw = mode if mode is not None else os.environ.get(CNN_MODE_ENV, "")
    value = str(raw).strip().lower() or DEFAULT_CNN_MODE
    if value not in CNN_MODES:
        logger.warning("[Synapse Shield] Unknown %s=%r; using %r.", CNN_MODE_ENV, raw, DEFAULT_CNN_MODE)
        value = DEFAULT_CNN_MODE
    return value


class SynapseHybridModel:
    def __init__(self, weights_path=None, cnn_mode=None):
        weights_path = resolve_weights_path(weights_path)
        self.cnn_mode = resolve_cnn_mode(cnn_mode)

        if not os.path.exists(weights_path):
            raise FileNotFoundError(f"[Synapse Shield] Model weights not found at: {weights_path}")

        self.weights_path = weights_path

        # Belleğe Yükleme (Isınma / Warmup)
        # Sadece 1 kez okunur (~0.05s) - allow_pickle=False ile RCE saldırılarına karşı korunur
        with np.load(weights_path, allow_pickle=False) as data:
            self.conv_w = np.array(data["conv_w"])  # shape: (16, 5, 3)
            self.conv_b = np.array(data["conv_b"])  # shape: (16,)

            self.fc1_w = np.array(data["fc1_w"])  # shape: (24, 16)
            self.fc1_b = np.array(data["fc1_b"])  # shape: (16,)

            self.fc2_w = np.array(data["fc2_w"])  # shape: (16, 1)
            self.fc2_b = np.array(data["fc2_b"])  # shape: (1,)

            # Vektörel matris çarpımı için düzleştirilmiş ağırlıklar (5x+ hızlanma)
            self.conv_w_flat = self.conv_w.reshape(16, 15)  # shape: (16, 15)
            self.conv_b_col = self.conv_b[:, None]  # shape: (16, 1)

    def predict(self, mouse_tensor, static_vector) -> float:
        """Karara giren CNN olasılığı: ``enforce`` modunda ham olasılık, ``shadow`` modunda 0.0."""
        prob = self.predict_raw(mouse_tensor, static_vector)
        return prob if self.cnn_mode == "enforce" else 0.0

    def predict_raw(self, mouse_tensor, static_vector) -> float:
        """
        Kalibre edilmemiş ağ çıktısı (0.0-1.0); moddan bağımsız, gözlem ve ölçüm için.
        mouse_tensor: list of lists (60x5) or np.ndarray
        static_vector: list (8) or np.ndarray
        """
        mouse = np.asarray(mouse_tensor, dtype=np.float32)
        if mouse.ndim == 3 and mouse.shape[0] == 1:
            mouse = mouse[0]
        # (60, 5) olan matrisi (5, 60) şekline getir (PyTorch uyumlu)
        mouse = mouse.T
        static = np.asarray(static_vector, dtype=np.float32).ravel()

        # 1. 1D Convolution (Vektörel Sliding Window & BLAS Matris Çarpımı)
        # Input: (5, 60), Output: (16, 60)
        padded_mouse = np.pad(mouse, ((0, 0), (1, 1)), mode="constant", constant_values=0.0)
        windows = np.lib.stride_tricks.sliding_window_view(padded_mouse, window_shape=3, axis=1)  # (5, 60, 3)
        windows_flat = windows.transpose(1, 0, 2).reshape(60, 15)  # (60, 15)
        c_out = np.dot(self.conv_w_flat, windows_flat.T) + self.conv_b_col

        # 2. ReLU
        c_out = np.maximum(0, c_out)

        # 3. Global Max Pooling 1D (AdaptiveMaxPool1d(1))
        # Input: (16, 60) -> Output: (16,)
        pool_out = np.max(c_out, axis=1)

        # 4. Late Fusion (Concat)
        # Output: (16 + 8) = (24,)
        merged = np.concatenate((pool_out, static))

        # 5. Fully Connected 1
        x = np.dot(merged, self.fc1_w) + self.fc1_b
        x = np.maximum(0, x)  # ReLU

        # 6. Fully Connected 2
        x = np.dot(x, self.fc2_w) + self.fc2_b

        # 7. Sigmoid
        # Sayısal stabilite için float32 uyumlu clip (-50, 50)
        x = np.clip(x, -50.0, 50.0)
        prob = 1.0 / (1.0 + np.exp(-x[0]))

        return float(prob)
