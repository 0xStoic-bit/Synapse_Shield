import os
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

# 1. Dataset Generation
def generate_synthetic_data(num_samples=10000):
    X_mouse = []
    X_static = []
    y = []
    for i in range(num_samples):
        is_bot = i % 2 == 0
        if is_bot:
            # Bot Data: pürüzsüz hız, sıfır veya tekdüze jerk, 0.0 varyanslı static
            mouse = np.random.normal(loc=1.0, scale=0.1, size=(5, 60)) # (dx, dy, dt, v, jerk)
            mouse[4, :] = np.random.normal(0, 0.01, size=(60,)) # jerk=0
            static = np.array([
                np.random.randint(5, 10), # key_count
                100.0, # avg_interval
                0.0,   # interval_var
                40.0,  # hold_time_avg
                0.0,   # hold_time_var (BOT FLAG)
                1.0,   # scroll_count
                0.5,   # avg_scroll_speed
                0.0    # scroll_accel_var (BOT FLAG)
            ])
            label = 1.0
        else:
            # Human Data: yüksek jerk (tremor), yüksek varyanslı klavye
            mouse = np.random.normal(loc=1.0, scale=0.5, size=(5, 60))
            mouse[4, :] = np.random.normal(10, 5.0, size=(60,)) # yüksek jerk
            static = np.array([
                np.random.randint(5, 15),
                180.0 + np.random.normal(0, 20),
                500.0 + np.random.normal(0, 100),
                80.0 + np.random.normal(0, 10),
                200.0 + np.random.normal(0, 50), # hold_time_var yüksek
                np.random.randint(1, 5),
                0.5 + np.random.normal(0, 0.1),
                10.0 + np.random.normal(0, 2)    # scroll accel var yüksek
            ])
            label = 0.0
            
        X_mouse.append(mouse)
        X_static.append(static)
        y.append([label])
        
    return torch.tensor(np.array(X_mouse), dtype=torch.float32), \
           torch.tensor(np.array(X_static), dtype=torch.float32), \
           torch.tensor(np.array(y), dtype=torch.float32)

# 2. PyTorch Model
class HybridCNN(nn.Module):
    def __init__(self):
        super().__init__()
        # 1D CNN: in=5 (dx,dy,dt,v,jerk), out=16, kernel=3, padding=1
        self.conv1 = nn.Conv1d(5, 16, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.pool = nn.AdaptiveMaxPool1d(1)
        
        self.fc1 = nn.Linear(16 + 8, 16) # 16 CNN + 8 Static
        self.fc2 = nn.Linear(16, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, mouse, static):
        # mouse: (batch, 5, 60)
        c = self.conv1(mouse)
        c = self.relu(c)
        c = self.pool(c).squeeze(2) # (batch, 16)
        
        merged = torch.cat((c, static), dim=1) # (batch, 24)
        x = self.fc1(merged)
        x = self.relu(x)
        x = self.fc2(x)
        return self.sigmoid(x)

def main():
    print("Sentetik veri üretiliyor (10.000 samples)...")
    X_m, X_s, y = generate_synthetic_data(10000)
    
    model = HybridCNN()
    optimizer = optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.BCELoss()
    
    print("Eğitim başlıyor...")
    for epoch in range(15):
        optimizer.zero_grad()
        out = model(X_m, X_s)
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()
        
        # Test Accuracy
        preds = (out > 0.5).float()
        acc = (preds == y).float().mean()
        print(f"Epoch {epoch+1:02d}/15 | Loss: {loss.item():.4f} | Accuracy: {acc.item():.4f}")
        
    print("Ağırlıklar (weights.npz) olarak dışa aktarılıyor...")
    
    # Numpy Export
    conv_w = model.conv1.weight.detach().numpy() # (16, 5, 3)
    conv_b = model.conv1.bias.detach().numpy()   # (16,)
    
    fc1_w = model.fc1.weight.detach().numpy()    # (16, 24) -> NumPy Matmul için (24, 16) yapalım
    fc1_b = model.fc1.bias.detach().numpy()      # (16,)
    
    fc2_w = model.fc2.weight.detach().numpy()    # (1, 16)  -> NumPy Matmul için (16, 1) yapalım
    fc2_b = model.fc2.bias.detach().numpy()      # (1,)
    
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "synapse_shield")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "weights.npz")
    np.savez(out_path, 
             conv_w=conv_w, conv_b=conv_b,
             fc1_w=fc1_w.T, fc1_b=fc1_b,
             fc2_w=fc2_w.T, fc2_b=fc2_b)
             
    print(f"Başarıyla kaydedildi: {out_path}")
    print(f"Dosya Boyutu: {os.path.getsize(out_path) / 1024:.2f} KB")

if __name__ == "__main__":
    main()
