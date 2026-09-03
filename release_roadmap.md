# Synapse Shield — İleri Seviye Sürüm Yol Haritası (v0.6.1 $\rightarrow$ v0.7.0)

Bu yol haritası, Synapse Shield'ı temel bir algoritmik süzgeçten, kurumsal düzeyde (Enterprise-grade) çalışan **Hibrit Yapay Zeka ve Adli Siber İstihbarat** motoruna dönüştürmek için hazırlanmıştır. Geliştirme süreci, "Sıfır Bağımlılık (Zero-Dependency)" prensibine katı bir şekilde bağlı kalarak tasarlanmıştır.

---

## 🎯 v0.6.1 - "The Sequence" (Veri Hazırlığı ve Standardizasyon)
**Ana Odak:** Projenin sürüm bağımsızlığını sağlamak ve ham telemetri verisini yapay zekanın anlayacağı tensör formatına çevirmek.

### Yapılacaklar (To-Do):
- [ ] **Sürüm Standardizasyonu:** `bump_version.py` yazılarak `__init__.py`, `pyproject.toml` ve dokümantasyonların tek komutla güncellenmesi sağlanacak.
- [ ] **README Güncellemesi:** *"Key Features & Security Architecture"* başlığı eklenerek mimari daha kurumsal bir dille anlatılacak.
- [ ] **Temporal Sequence Tokenizer (Sıralı Dönüştürücü):** 
  - `features.py` içine yeni bir sınıf eklenecek.
  - Ham fare koordinatları $(x, y, t)$, 60 adımlık sabit boyutlu bir tensöre $[\Delta x, \Delta y, \Delta t, \text{Jerk}, \kappa]$ dönüştürülecek.
  - Zaman serilerinde "Padding" (boşluk doldurma) ve "Truncation" (kesme) işlemleri kodlanacak.
- [ ] **Veritabanı İyileştirmeleri:** SQLite üzerinde `timeout=10.0` ve WAL (Write-Ahead Logging) modunun stabilizasyonu test edilecek.

> [!TIP]
> **Neden Önemli?** Bu sürüm, sistemin temellerini yapay zeka entegrasyonu için temiz ve standart bir formata sokar. Veri ne kadar temizse, v0.6.2'deki yapay zeka o kadar akıllı olur.

---

## 🧠 v0.6.2 - "The Micro-Brain" (Saf NumPy SLM Entegrasyonu)
**Ana Odak:** Dış bağımlılık (PyTorch/TensorFlow) olmadan, sadece 15 KB'lık bir ağırlık dosyasıyla çalışan Mini-GRU/LSTM modelinin (SLM) sisteme yerleştirilmesi.

### Yapılacaklar (To-Do):
- [ ] **Yerel Eğitim Ortamı (Local Training):** `scripts/train_sequence_ai.py` oluşturulacak. Bu script, PyTorch kullanarak sentetik bot hareketleri (Bézier eğrileri) ve organik insan verileriyle yerelde model eğitecek.
- [ ] **Model Mimarisi:** 1 Katmanlı, 16 Nöronlu GRU/LSTM. Çıkışta Sigmoid aktivasyonu.
- [ ] **NumPy Export:** Eğitilen modelin ağırlıkları (`.npz` formatında) dışa aktarılacak.
- [ ] **Saf Python Çıkarımı (Inference):** `models.py` adında yeni bir modül yazılacak. Bu modül sadece `numpy` kütüphanesini kullanarak matris çarpımlarını gerçekleştirecek ve 0.0 - 1.0 arası bir "Doğallık Skoru" (Humanity Score) üretecek.
- [ ] **Veri Toplama Boru Hattı (Data Pipeline):**
  - **Sentetik Bot Verisi:** `live_attacker.py` üzerinden 10.000 adet kusursuz doğrusal ve Bézier bot tensörü (Label=1) üretilecek.
  - **Açık Kaynak İnsan Verisi:** "Balabit" veya "TWOS" gibi akademik veri setlerindeki insan fare hareketleri (Label=0) sisteme entegre edilecek.
  - **Topluluk Kalibrasyonu (Honeypot):** Pakete `synapse-shield-calibrate` komutu eklenecek ve 3000+ geliştiricinin kendi fare hareketlerini buluta anonim olarak göndererek modelin eğitilmesine katkı sağlaması (Crowdsourcing) sağlanacak.

> [!IMPORTANT]
> **Kritik Kural:** `requirements.txt` dosyasına KESİNLİKLE PyTorch, TensorFlow veya Keras eklenmeyecektir. Model çıkarımı saniyenin onda biri süresinde NumPy üzerinden çalışmalıdır.

---

## ⚡ v0.6.3 - "The Fusion" (İki Aşamalı Kapılama ve Hibrit Karar)
**Ana Odak:** Kural tabanlı motor ile Yapay Zeka modelini "Maliyet ve Hız" odaklı bir füzyonla birleştirmek (Cloudflare Mantığı).

### Yapılacaklar (To-Do):
- [ ] **Gating (Kapılama) Mantığının Yazılması (`engine.py`):**
  - Kural motoru bariz bot bulursa (Risk $\ge 70$) $\rightarrow$ Model çalışmaz, anında BLOCK (403).
  - Kural motoru kusursuz insan bulursa (Risk $< 25$) $\rightarrow$ Model çalışmaz, anında ALLOW (200).
  - Risk %25 ile %70 arasında kalırsa $\rightarrow$ v0.6.2'deki Mikro-GRU modeli devreye girer.
- [ ] **Karar Füzyonu Formülü:** `Nihai Skor = (0.60 x Kural Riski) + (0.40 x LSTM Bot Olasılığı)` hesaplamasının entegrasyonu.
- [ ] **Adversarial Test Güncellemesi:** `live_attacker.py` süitine yapay insan taklidi yapan gelişmiş botlar eklenerek hibrit füzyonun başarı oranı ölçülecek.

> [!CAUTION]
> **SLA Gereksinimi:** Bu sürümdeki "Hibrit Karar" mekanizması, gelen her istek için toplamda **0.35 ms'den kısa** sürede sonuç vermelidir.

---

## 🕵️ v0.7.0 - "The Forensic" (Asenkron Tehdit İstihbaratı)
**Ana Odak:** Savunma kalkanını, saldıran botların "kimliğini ve aracını" tespit eden bir Siber İstihbarat (SIEM) merkezine dönüştürmek.

### Yapılacaklar (To-Do):
- [ ] **Asenkron Analiz Kuyruğu:** FastAPI `BackgroundTasks` kullanılarak, canlı akışı bloklamadan, şüpheli oturumların analiz edilmesi.
- [ ] **Tehdit Atıf Modeli (Attribution Profiler):** Yakalanan botun "hangi aracı" kullandığını (Selenium, Puppeteer-Stealth, Simple Script vb.) matematiksel parmak izinden tespit eden fonksiyonların yazılması.
- [ ] **SecOps Loglama:** `/api/logs` endpoint'i ve Prometheus metrikleri güncellenecek. `bot_type="headless_chromium"` gibi yeni etiketler (labels) eklenecek.
- [ ] **Dokümantasyon:** "Kurumsal Entegrasyon" ve "SIEM Raporlaması" başlıklarıyla README ve Wiki sayfaları v0.7.0 için tamamen yenilenecek.

> [!NOTE]
> Bu sürüm yayınlandığında Synapse Shield sadece bir "bot engelleyici" olmaktan çıkacak, kurumsal şirketlerin SOC (Security Operations Center) ekiplerine "Kim, hangi otomasyon aracıyla saldırıyor?" raporu sunan Enterprise bir ürüne dönüşecektir.
