"""
Synapse Shield - Automated Version Synchronization Script
Usage:
    python bump_version.py 0.6.1
"""

import sys
import re

if len(sys.argv) < 2:
    print("Kullanım: python bump_version.py <yeni_surum> (Örn: python bump_version.py 0.6.1)")
    sys.exit(1)

new_version = sys.argv[1].strip()

# 1. pyproject.toml güncelle
with open("pyproject.toml", "r", encoding="utf-8") as f:
    content = f.read()
content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content)
with open("pyproject.toml", "w", encoding="utf-8") as f:
    f.write(content)
print(f"✔ pyproject.toml -> {new_version}")

# 2. __init__.py güncelle
init_path = "src/synapse_shield/__init__.py"
try:
    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', content)
    with open(init_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ {init_path} -> {new_version}")
except FileNotFoundError:
    pass

# 3. README.md içindeki sürüm başlığını güncelle
try:
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'Key Features & Hardening \(v[0-9\.]+\)', f'Key Features & Hardening (v{new_version})', content)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ README.md -> {new_version}")
except FileNotFoundError:
    pass

print(f"\n🚀 Sürüm senkronizasyonu tamamlandı: v{new_version}")
