"""
Synapse Shield - Automated Version Synchronization Script
Usage:
    python bump_version.py 0.6.1
"""

import sys
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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

# 1.1 crates/synapse_core_rs/Cargo.toml güncelle
cargo_path = "crates/synapse_core_rs/Cargo.toml"
try:
    with open(cargo_path, "r", encoding="utf-8") as f:
        cargo_content = f.read()
    cargo_content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', cargo_content, count=1)
    with open(cargo_path, "w", encoding="utf-8") as f:
        f.write(cargo_content)
    print(f"✔ {cargo_path} -> {new_version}")
except FileNotFoundError:
    pass

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

# 3. synapse-shield-react package.json & README.md
for pkg_path in ["synapse-shield-react/package.json", "synapse-shield-vue/package.json"]:
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r'"version": "[^"]+"', f'"version": "{new_version}"', content)
        with open(pkg_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✔ {pkg_path} -> {new_version}")
    except FileNotFoundError:
        pass

# 4. synapse-sdk.js header
sdk_path = "src/synapse_shield/static/synapse-sdk.js"
try:
    with open(sdk_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'Synapse Shield SDK v[0-9\.]+', f'Synapse Shield SDK v{new_version}', content)
    with open(sdk_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ {sdk_path} -> {new_version}")
except FileNotFoundError:
    pass

# 5. test_sdk.py assertion
test_sdk_path = "tests/test_sdk.py"
try:
    with open(test_sdk_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'Synapse Shield SDK v[0-9\.]+', f'Synapse Shield SDK v{new_version}', content)
    with open(test_sdk_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ {test_sdk_path} -> {new_version}")
except FileNotFoundError:
    pass

# 6. README.md files & Chinese README
for r_path in ["README.md", "README_ZH.md", "synapse-shield-react/README.md", "synapse-shield-vue/README.md"]:
    try:
        with open(r_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r'Features \(v[0-9\.]+\)', f'Features (v{new_version})', content)
        content = re.sub(r'Key Features & Security Architecture \(v[0-9\.]+\)', f'Key Features & Security Architecture (v{new_version})', content)
        content = re.sub(r'核心特性与安全架构 \(v[0-9\.]+\)', f'核心特性与安全架构 (v{new_version})', content)
        content = re.sub(r'#\-key\-features\-\-security\-architecture\-v[0-9]+', f'#-key-features--security-architecture-v{new_version.replace(".", "")}', content)
        content = re.sub(r'#\-核心特性与安全架构\-v[0-9]+', f'#-核心特性与安全架构-v{new_version.replace(".", "")}', content)
        with open(r_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✔ {r_path} -> {new_version}")
    except FileNotFoundError:
        pass

# 7. static/index.html
index_html_path = "src/synapse_shield/static/index.html"
try:
    with open(index_html_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'\(v0\.[0-9\.]+\)', f'(v{new_version})', content)
    with open(index_html_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ {index_html_path} -> {new_version}")
except FileNotFoundError:
    pass

# 8. crates/synapse_core_rs/src/lib.rs version string
rust_lib_path = "crates/synapse_core_rs/src/lib.rs"
try:
    with open(rust_lib_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'"[0-9\.]+-native-rust"', f'"{new_version}-native-rust"', content)
    with open(rust_lib_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ {rust_lib_path} -> {new_version}-native-rust")
except FileNotFoundError:
    pass

# 9. live_attacker.py
live_attacker_path = "src/synapse_shield/live_attacker.py"
try:
    with open(live_attacker_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'SYNAPSE SHIELD v[0-9\.]+', f'SYNAPSE SHIELD v{new_version}', content)
    with open(live_attacker_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✔ {live_attacker_path} -> {new_version}")
except FileNotFoundError:
    pass

print(f"\n🚀 Sürüm senkronizasyonu tamamlandı: v{new_version}")
