# Synapse Shield v0.8.0 Release Notes
**Release Date:** 23 September 2026  
**Codename:** *Titanium Core (Native Rust Acceleration & Distributed Botnet Defense)*  
**Author:** Mustafa Güngör ([@0xStoic-bit](https://github.com/0xStoic-bit))

---

## 🚀 Executive Summary

Synapse Shield **v0.8.0**, biyometrik bot savunma motorunu Python yorumlayıcısının ve disk I/O sınırlarının ötesine taşıyarak **yerel Rust çekirdeği (Native Rust Core - `synapse_core_rs`)** ile güçlendiriyor.

Bu sürümle birlikte, yüksek trafikli DDoS ve bot saldırıları altındaki en kritik darboğaz olan **SQLite disk I/O gecikmesi (984 µs)** tamamen ortadan kaldırılmış; bellek içi (in-memory) çift kova (Two-Bucket) ve L1 IP ban mimarisi sayesinde kriptografik doğrulama ve IP engelleme gecikmeleri **mikrosaniye altı (sub-microsecond) seviyelere** indirilmiştir.

Sürüm, **250 dağıtık IP üzerinden 10.000 istekli zombi botnet simülasyonu** ile sıfır kilitlenme, sıfır veri kaybı ve sıfır HTTP 500 hatası ile doğrulanmıştır.

---

## ⚡ Temel Yenilikler ve Mimari Değişiklikler

### 1. Yerel Rust Durum Motoru (`crates/synapse_core_rs`)
PyO3 ve Maturin kullanılarak CPython C-ABI seviyesinde bağlanan sıfır maliyetli (zero-cost) Rust motoru entegre edildi:
* **Çift Kova (Two-Bucket) Nonce Önbelleği (`TwoBucketNonceStore`):**
  - Replay saldırılarını önlemek için kullanılan SQLite disk yazma işlemi yerine, 60 saniyelik dönen iki adet `HashSet<String>` kovası kullanıldı.
  - 60 saniye dolduğunda eski kova $O(1)$ bellek işaretçi takası (pointer swap) ile temizlenir; arkada hiçbir bellek sızıntısı veya çöp toplayıcı (GC) duraklaması bırakmaz.
  - **Nonce Doğrulama Hızı:** 984 µs $\rightarrow$ **0.8 µs (P50)** (**1.200 kat hızlanma**, 794.000 ops/sn kapasite).
* **L1 Bellek İçi IP Ban Önbelleği (`HashMap<String, u64>`):**
  - Gelen her istekte IP karantina kontrolü ~15 nanosaniyede tamamlanır.
  - **Cold-Start Hidrasyonu:** Sunucu yeniden başladığında SQLite diskinde henüz süresi dolmamış aktif ban kayıtları otomatik olarak Rust L1 önbelleğine aktarılır (Cold-Start Hydration).
  - **Dual-Write Stratejisi:** Yeni banlar hem mikrosaniye hızında L1 RAM'e yazılır hem de SQLite'a kalıcı olarak kaydedilir.

---

### 2. Çoklu Platform & Çoklu Python Sürümü Binary Wheel Matrisi (`.github/workflows/wheels.yml`)
Kullanıcıların sistemlerinde Rust veya C derleyicisi bulunmasa dahi doğrudan `pip install synapse-shield` ile önceden derlenmiş binary tekerlekleri (wheels) çalıştırabilmesi için **Python 3.10, 3.11 ve 3.12** sürümlerini kapsayan GitHub Actions matrix iş akışı kuruldu:
* **Linux (manylinux):** `x86_64` (py3.10, py3.11, py3.12), `aarch64` (py3.10, py3.11, py3.12) $\rightarrow$ 6 Wheel
* **Windows (MSVC):** `x64` (py3.10, py3.11, py3.12) $\rightarrow$ 3 Wheel
* **macOS:** `x86_64` Intel (py3.10, py3.11, py3.12), `arm64` Apple Silicon (py3.10, py3.11, py3.12) $\rightarrow$ 6 Wheel
* **Toplam:** **15 platform-spesifik Native Rust binary wheel** + **2 Universal Python paketi** (`.whl` & `.tar.gz`).
* **Otomatik Yayın:** GitHub üzerinde `v*` etiketi oluşturulduğunda binary paketler doğrudan derlenip PyPI'a dağıtıma hazır hale getirilir.

---

### 3. Dağıtık Botnet DDoS & Yük Testi Paketi
Sistemin kurumsal seviyedeki dayanıklılığını ölçmek için 3 yeni test ve simülasyon aracı eklendi:
* **10.000 İsteklik Dağıtık Botnet Simülasyonu (`scripts/flood_10k_stress.py`):**
  - 250 farklı zombi IP (`X-Forwarded-For`) üzerinden eşzamanlı 10.000 istek gönderildi.
  - **Sonuç:** 0 HTTP 500, 0 `database is locked`, 0 çöken istek.
  - 685 istek Rust L1 Ban Cache tarafından HTTP 403 ile engellendi.
  - 631 istek 1D-CNN + Kinematik motor tarafından tespit edilip işaretlendi.
  - 8.684 istek kriptografik 60s zaman aşımı tuzağına (HTTP 400 Expired) takıldı.
  - Bellek tüketimi 10k istek boyunca sadece +130 MB artış gösterdi ve stabil kaldı.
* **Locust Yük Testi Süiti (`tests/locustfile.py`):**
  - 4 gerçekçi kullanıcı ve saldırgan profili (`LegitimateHumanUser`, `ReplayAttackBot`, `SyntheticLinearBot`, `RapidFloodBot`).
* **Canlı ANSI Saldırı Simülatörü (`scripts/attack_sim.py`):**
  - Terminalde strike birikimini ve L1 ban durumuna geçişi renkli olarak gerçek zamanlı görselleştiren CLI aracı.

---

### 4. Geriye Dönük Uyumluluk & Graceful Fallback
* Rust uzantısı (`synapse_core_rs`) derlenmemiş veya mevcut olmayan ortamlarda `SQLiteStorageBackend` otomatik olarak standart optimize edilmiş disk sorgularına düşer (fallback).
* Sistem hiçbir dış C bağımlılığı zorunlu kılmadan saf Python/NumPy ortamlarında da eksiksiz çalışmaya devam eder.

---

## 📊 Performans Kıyaslama Tablosu (Ryzen 7 8845HS)

| Test Aşaması | v0.7.9 (Saf Python / SQLite) | v0.8.0 (Rust Çekirdeği) | Hızlanma / Kazanç |
| :--- | :--- | :--- | :--- |
| **Nonce Tüketimi (Replay Check)** | 984.0 µs | **0.8 µs** | **~1.200x Kat Daha Hızlı** |
| **Kriptografik Token Döngüsü** | 956.0 µs | **8.2 µs** | **~116x Kat Daha Hızlı** |
| **IP Ban Kontrolü (L1)** | ~450.0 µs (Disk) | **< 0.02 µs (15 ns)** | **~22.000x Kat Daha Hızlı** |
| **19D Kinematik Çıkarımı** | 150.2 µs (NumPy) | **23.3 µs (Rust)** | **6.4x Kat Daha Hızlı** |
| **Tam Uçtan Uca Değerlendirme** | 828.1 µs | **580.0 µs** | **1.470 req/sec tek çekirdek** |

---

## 🛠️ Değişen & Eklenen Dosyalar

* `crates/synapse_core_rs/`: Rust durum motoru, Two-Bucket önbelleği ve PyO3 CPython köprüsü.
* `.github/workflows/wheels.yml`: Çoklu platform Maturin binary derleme ve PyPI dağıtım iş akışı.
* `src/synapse_shield/storage.py`: Rust L1 entegrasyonu, ban hidrasyonu ve disk fallback mekanizması.
* `src/synapse_shield/tokens.py`: Two-Bucket devredeyken gereksiz disk temizleme taramalarının bypass edilmesi.
* `src/synapse_shield/adversarial.py`: `generate_linear_telemetry()` mekanik bot simülatörü.
* `src/synapse_shield/benchmark.py`: Rust Two-Bucket doğrulama aşaması profillemesi.
* `tests/locustfile.py`: Dağıtık kullanıcı ve botnet Locust senaryoları.
* `tests/test_rust_core.py`: Rust Two-Bucket ve L1 ban yaşam döngüsü birim testleri (84/84 test passed).
* `scripts/flood_10k_stress.py`: 10.000 istekli dağıtık botnet DDoS stres testi.
* `scripts/attack_sim.py`: Canlı terminal saldırı görselleştiricisi.
* `SIMULATION_REPORT_v080.md`: 10.000 istekli stres testinin detaylı teknik raporu.

---

## 🔒 Güvenlik Doğrulaması
* **Replay Attack Koruması:** $O(1)$ çift kova ile %100 oranında doğrulandı.
* **Bellek Güvenliği:** Rust'ın sahiplik (ownership) modeli ve `RwLock` eşzamanlılığı sayesinde sıfır race condition ve sıfır panic.
* **Birim Testleri:** `84 passed in 4.33s` (%100 başarı oranı).
