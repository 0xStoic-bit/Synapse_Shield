"""
Synapse Shield - v0.6.2 The Micro-Brain (Pure NumPy Inference Engine)
Sıfır Bağımlılık (Zero-Dependency) prensibiyle 1D-CNN + Late Fusion 
yapay zeka modelini çalıştırır. PyTorch veya TensorFlow gerektirmez.
"""
import os
import numpy as np

class SynapseHybridModel:
    def __init__(self, weights_path=None):
        if weights_path is None:
            # Otomatik olarak paket içindeki weights.npz'yi bulur
            weights_path = os.path.join(os.path.dirname(__file__), "weights.npz")
            
        if not os.path.exists(weights_path):
            raise FileNotFoundError(f"[Synapse Shield] Model weights not found at: {weights_path}")
            
        # Belleğe Yükleme (Isınma / Warmup)
        # Sadece 1 kez okunur (~0.05s)
        data = np.load(weights_path)
        self.conv_w = data['conv_w'] # shape: (16, 5, 3)
        self.conv_b = data['conv_b'] # shape: (16,)
        
        self.fc1_w = data['fc1_w']   # shape: (24, 16)
        self.fc1_b = data['fc1_b']   # shape: (16,)
        
        self.fc2_w = data['fc2_w']   # shape: (16, 1)
        self.fc2_b = data['fc2_b']   # shape: (1,)

    def predict(self, mouse_tensor, static_vector) -> float:
        """
        mouse_tensor: list of lists (60x5)
        static_vector: list (8)
        """
        # (60, 5) olan matrisi (5, 60) şekline getir (PyTorch uyumlu)
        mouse = np.array(mouse_tensor, dtype=np.float32).T 
        static = np.array(static_vector, dtype=np.float32)
        
        # 1. 1D Convolution (Sliding Window, padding=1)
        # Input: (5, 60), Output: (16, 60)
        padded_mouse = np.pad(mouse, ((0,0), (1,1)), mode='constant', constant_values=0.0)
        c_out = np.zeros((16, 60), dtype=np.float32)
        
        # Manuel Konvolüsyon (Hızlandırılmış döngü)
        for j in range(60):
            # Window shape: (5, 3)
            window = padded_mouse[:, j:j+3]
            # (16, 5, 3) ile (5, 3) tensör çarpımı
            # sum over axes 1 and 2
            c_out[:, j] = np.sum(self.conv_w * window, axis=(1, 2)) + self.conv_b

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
        x = np.maximum(0, x) # ReLU
        
        # 6. Fully Connected 2
        x = np.dot(x, self.fc2_w) + self.fc2_b
        
        # 7. Sigmoid
        # Sayısal stabilite için clip
        x = np.clip(x, -500, 500)
        prob = 1.0 / (1.0 + np.exp(-x[0]))
        
        return float(prob)
