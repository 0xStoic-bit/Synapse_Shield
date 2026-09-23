# Synapse Shield — Uçtan Uca Mimari Akış ve Sistem Spesifikasyonu (v0.7.9)

> **Mimar & Geliştirici:** Mustafa Güngör (`0xStoic-bit`)  
> **Sürüm:** v0.7.9 (PyPI: `synapse-shield==0.7.9`)  
> **Lisans:** MIT — Açık Kaynak, Sıfır Dış Bağımlılık (Pure NumPy / Zero-PII)

---

## 🏛️ 1. Mimari Felsefe ve Vizyon

Geleneksel bot koruma sistemleri (Google reCAPTCHA, Cloudflare Turnstile); kullanıcıya bulmaca çözdürerek kullanıcı deneyimini (UX) felç eder, kişisel verileri (PII) üçüncü parti sunuculara aktararak KVKK/GDPR uyumsuzluğu yaratır ve binlerce dolarlık bulut faturalarıyla satıcı bağımlılığı (vendor lock-in) oluşturur.

**Synapse Shield**, bu paradigmayı kökten yıkar:
1. **Self-Hosted & Egemen (Sovereign):** Dışarıya 1 byte veri sızdırmaz, tamamen kendi sunucunda çalışır.
2. **Sıfır Sürtünme (Zero Friction):** Kullanıcıya hiçbir bulmaca çözdürmez, arka planda mikrosaniyelik biyomekanik ve kinematik analizle insan-bot ayrımını yapar.
3. **Sıfır Ağır Bağımlılık:** PyTorch veya TensorFlow gibi yüzlerce megabaytlık kütüphanelere ihtiyaç duymadan, saf **NumPy BLAS C-seviyesi matris çarpımlarıyla** CPU üzerinde $<1\,\text{ms}$ gecikmeyle karar verir.

---

## 🔄 2. Sistem Bileşen Mimarisi ve Akış Şeması

### 2.1. Yüksek Seviye Bileşen ve Blok Mimarisi (Component Architecture)

Aşağıdaki şemalar; İstemci Katmanı, Giriş Katmanı, 5 Katmanlı Savunma Hattı, Durum/Depolama Katmanı ve Karar Mekanizması arasındaki modüler ilişkiyi göstermektedir:

#### 📌 Metin Tabanlı Mimari Blok Şeması (Raw Editor Preview)

```
+---------------------------------------------------------------------------------------------------+
|                                SYNAPSE SHIELD SİSTEM MİMARİSİ (v0.7.9)                            |
+---------------------------------------------------------------------------------------------------+

 [🌐 1. İSTEMCİ KATMANI (Client Tier)]
   │
   ├── Web / Mobil UI (Vanilla JS / React / Vue SDK)
   └── İstemci Çıktısı: HMAC Challenge Token + 19D Biyometrik Telemetri Paketi
         │
         ▼
 [⚡ 2. GİRİŞ VE ORTA KATMAN (Edge Ingestion)]
   │
   └── SynapseShieldMiddleware / @shield_protect  -->  FastAPI / ASGI Çekirdeği
         │
         ▼
 [🛡️ 3. ÇEKİRDEK 5 KATMANLI SAVUNMA HATTI (Core Defense Pipeline)]
   │
   ├── [KATMAN 1] 🔑 Kriptografi & Nonce      --> HMAC-SHA256, Replay Attack Koruması, 400 Expired
   ├── [KATMAN 2] 🧬 19D Kinematik DSP (73µs)  --> Jerk d³x/dt³, Fitts Yavaşlaması, FFT Entropi
   ├── [KATMAN 3] 🧠 1D-CNN Model (451µs)      --> Saf NumPy BLAS, İzole Model Ağırlıkları
   ├── [KATMAN 4] 🕵️ V8 Anti-Stealth          --> Webdriver, Fake Plugins, Native toString Hook
   └── [KATMAN 5] 🌐 Ağ & Poisson Analizi     --> Poisson (λ=2.0), Davranış Değişmezliği, Ban Merdiveni
         │
         ├──◄───► [🗄️ DURUM VE DEPOLAMA]
         │          ├── SQLite WAL Motoru (synapse_shield.db)
         │          ├── Redis Kümesi (Opsiyonel Distributed Locks)
         │          └── İzole Model Dosyası (./synapse_weights.npz)
         │
         ▼
 [🎯 4. NİHAİ KARAR VE GERİ BİLDİRİM (Decisions & Telemetry)]
   │
   ├── ✅ ALLOW   (HTTP 200) --> Doğrulanmış İnsan İstekleri (Hedef API Yürütülür)
   ├── ❌ BLOCK   (HTTP 403) --> Bot Saldırısı Bloklandı (Dinamik IP Ban + Webhook)
   ├── 🔄 EXPIRED (HTTP 400) --> Token Süresi Doldu (Sessiz Yenileme, Ban Yok)
   └── 📊 Cyber-Console     --> WebSocket Canlı Terminal + Discord / Telegram Webhookları
+---------------------------------------------------------------------------------------------------+
```

#### 📊 Mermaid Grafiksel Akış Diyagramı (Markdown Rendered Preview)

```mermaid
graph TD
    UI["🌐 Web / Mobil Arayüz"] --> SDK["📦 Synapse SDK"]
    SDK --> PAYLOAD["📄 HMAC Token + 19D Telemetri"]
    PAYLOAD --> MW["⚡ SynapseShieldMiddleware"]
    MW --> ROUTER["⚙️ FastAPI / ASGI Çekirdeği"]
    
    ROUTER --> L1["🔑 Katman 1: Kriptografi & Nonce"]
    L1 --> L2["🧬 Katman 2: 19D Kinematik DSP"]
    L2 --> L3["🧠 Katman 3: 1D-CNN Mikro-Beyin"]
    L3 --> L4["🕵️ Katman 4: V8 Anti-Stealth"]
    L4 --> L5["🌐 Katman 5: Ağ & Poisson Analizi"]
    
    L5 -.-> DB[("🗄️ SQLite WAL / Redis")]
    L5 -.-> WEIGHTS[("🧠 synapse_weights.npz")]
    
    L5 --> ALLOW["✅ ALLOW (HTTP 200)"]
    L5 --> BLOCK["❌ BLOCK (HTTP 403)"]
    L5 --> EXPIRED["🔄 EXPIRED (HTTP 400)"]
    L5 --> TELEMETRY["📊 WebSocket Console & Webhooks"]

---

### 2.2. Uçtan Uca Protokol ve Sıralama Akışı (Sequence Flow)

Aşağıdaki sıralama diyagramı (sequence diagram), bir istemcinin (tarayıcı veya bot) korunan bir API rotasına istek attığı andan kararın verildiği ana kadarki tüm yaşam döngüsünü göstermektedir:

```mermaid
sequenceDiagram
    autonumber
    actor Client as 🌐 İstemci (Kullanıcı / Bot)
    participant SDK as 📦 Synapse SDK (JS / React / Vue)
    participant Server as 🛡️ Synapse Shield Sunucusu (FastAPI / WSGI)
    participant Crypto as 🔑 Katman 1: Kripto & Nonce
    participant Biometrics as 🧬 Katman 2: 19D Kinematik DSP
    participant AI as 🧠 Katman 3: 1D-CNN Model
    participant AntiTamper as 🕵️ Katman 4: V8 Anti-Stealth
    participant NetLayer as 🌐 Katman 5: Ağ & Poisson Havuzu
    participant Storage as 🗄️ SQLite / Redis Depolama

    Note over Client, Server: FAZ 1: Kriptografik El Sıkışma
    Client->>Server: GET /api/challenge
    Server->>Crypto: generate_challenge()
    Crypto->>Crypto: HMAC-SHA256(nonce + ts, SECRET_KEY)
    Crypto-->>Server: Token: nonce.timestamp.signature (60s TTL)
    Server-->>SDK: Challenge Token Teslimi

    Note over Client, SDK: FAZ 2: Biyometrik Telemetri Toplama
    Client->>SDK: Fare Hareketi, Tıklama, Tuş Vuruşu, İvme
    SDK->>SDK: Submovement Ayrıştırma, Jitter & V8 Native Prototip Kontrolü

    Note over Client, Server: FAZ 3: Doğrulama ve Savunma Hattı
    Client->>Server: POST /api/analyze (veya Korumalı Endpoint) + Token + Telemetri
    
    rect rgb(25, 35, 55)
        Note over Server, Crypto: KATMAN 1: Kriptografik Bütünlük
        Server->>Crypto: verify_and_consume_token(token)
        alt Token Geçersiz veya Replay Attack?
            Crypto-->>Server: REPLAY_ATTACK / INVALID_SIGNATURE
            Server->>NetLayer: record_ip_decision(ip, is_bot=True)
            Server-->>Client: HTTP 403 Forbidden [Bot Strike]
        else Token Süresi Dolmuş (Expired >60s)?
            Crypto-->>Server: TOKEN_EXPIRED (False Positive Engeli)
            Server-->>Client: HTTP 400 Bad Request [Token Refresh Required]
        end
    end

    rect rgb(20, 45, 45)
        Note over Server, Biometrics: KATMAN 2: 19D Kinematik Analiz
        Server->>Biometrics: extract_features(telemetry)
        Biometrics->>Biometrics: Jerk Türevi d³x/dt³, FFT Spektral Purity, Fitts Yavaşlaması
    end

    rect rgb(45, 25, 45)
        Note over Server, AI: KATMAN 3: 1D-CNN Çıkarımı
        Server->>AI: SynapseHybridModel.predict(mouse_tensor, static_vector)
        AI->>AI: Conv1D (16 filt.) + ReLU + MaxPool + FC1 + FC2 (NumPy BLAS)
        AI-->>Server: AI Güven Skoru (0.0 - 1.0)
    end

    rect rgb(45, 40, 20)
        Note over Server, AntiTamper: KATMAN 4: Anti-Stealth & V8 Tamper
        Server->>AntiTamper: Webdriver, Fake Plugins, Canvas/WebGL Native Kontrolü
    end

    rect rgb(35, 35, 35)
        Note over Server, NetLayer: KATMAN 5: Ağ & Dinamik IP Cezalandırma
        Server->>NetLayer: Poisson Dağılımı (lambda=2.0) & Sliding-Window Invariance
        Server->>Storage: Atomik WAL Log Yazımı & Strike Kaydı
    end

    alt Nihai Bot Skoru >= 65.0?
        Server-->>Client: HTTP 403 Forbidden [BLOCK] + Webhook Alarmı
    else Nihai Bot Skoru < 65.0?
        Server-->>Client: HTTP 200 OK [ALLOW] (Hedef API Yürütülür)
    end
```

---

## 🛡️ 3. 5 Katmanlı Savunma Hattı Detayları

### Katman 1: Kriptografik Bütünlük ve Tek Kullanımlık Nonce
* **HMAC-SHA256 Challenge:** İstemciye sunulan her challenge token'ı `nonce.timestamp.signature` biçimindedir. Sunucu tarafında `hmac.compare_digest` ile sabit zamanlı doğrulanır (Timing Attack koruması).
* **Atomik Replay Attack Engeli:** Doğrulanan token'ın nonce değeri SQLite (`used_nonces` tablosu) veya Redis (`SET NX EX`) üzerine atomik olarak işlenir. Aynı token milisaniyeler sonra tekrar gönderilirse anında yakalanır ve saldırgan IP'ye ceza yazılır.
* **Akıllı Süre Aşımı (False Positive Engeli):** Sayfada uzun süre bekleyen gerçek bir kullanıcının süresi dolduğunda (`TOKEN_EXPIRED`), kullanıcı bot sanılıp banlanmaz; sessizce `HTTP 400` dönülerek token yenilemesi istenir.

---

### Katman 2: 19 Boyutlu Kinematik ve Biyomekanik Motoru
İnsan hareketi fiziksel kas-iskelet eylemsizliğine ve sinir sistemi titreşimlerine tabidir. Bu katman şunları hesaplar:
1. **Jerk Analizi ($d^3x/dt^3$):** İvmenin zamana göre türevi. İnsan kaslarının mikro-düzeltmeleri asla 0 Jerk üretmez. Düz çizgide giden botlar anında elenir.
2. **Fitts Kanunu Terminal Yavaşlaması:** İnsanlar bir butona tıklamadan önceki son %25'lik mesafede hedefi tutturmak için yavaşlarlar. Botlar ise son piksele kadar sabit hızla gider.
3. **FFT Spektral Saflık ve Entropi (DSP):** Hız serisi Fast Fourier Transform (`np.fft.rfft`) ile frekans düzlemine açılır. Botların sinüs dalgalı titreşim taklitleri tek frekansta sivrilirken (`spectral_purity > 0.65`), organik insan tremoru stokastik pembe gürültü ($1/f$) dağılımı gösterir.
4. **Alt-Hareket (Submovement) Ayrıştırması:** Hareket yolundaki yerel hız tepeleri ve çan eğrileri sayılır. Fizyolojik darbe içermeyen matematiksel yollar elenir.
5. **Klavye Dinamikleri:** Tuşa basma ve bırakma arasındaki bekleme süreleri (Dwell Time) ve iki tuş arası uçuş süreleri (Flight Time) $O(N)$ kuyruk algoritmasıyla taranır. Sabit aralıklı mekanik vuruşlar bloke edilir.

---

### Katman 3: 1D-CNN Mikro-Beyin Yapay Zeka Motoru
* **Girdi:** 60 adımlık normalize edilmiş hareket tensörü $(5 \times 60)$ ve 8 boyutlu statik özellik vektörü.
* **Mimari:**
  $$\text{Input} \rightarrow \text{Conv1D}(16, \text{kernel}=3, \text{pad}=1) \rightarrow \text{ReLU} \rightarrow \text{AdaptiveMaxPool1D}(1) \rightarrow \text{Concat}(\text{Static}) \rightarrow \text{FC1}(24 \times 16) \rightarrow \text{ReLU} \rightarrow \text{FC2}(16 \times 1) \rightarrow \text{Sigmoid}$$
* **Sıfır Bağımlılık Çıkarımı:** Bu katman PyTorch bağımlılığı olmadan saf NumPy matris çarpımlarıyla **$451\,\mu s$** içinde CPU üzerinde koşar.
* **İzole Model Hiyerarşisi (`train.py` & `models.py`):** Yerel fine-tuning yapıldığında ana paket dosyası bozulmaz; ağırlıklar `./synapse_weights.npz`'ye yazılır. Öncelik: `SYNAPSE_WEIGHTS_PATH` $\rightarrow$ `./synapse_weights.npz` $\rightarrow$ Dahili temel model.

---

### Katman 4: V8 Anti-Stealth ve Tarayıcı Bütünlüğü
* **`navigator.webdriver` Tespiti:** Selenium, Puppeteer ve Playwright gibi otomasyon araçlarının bıraktığı izler.
* **Fake Plugin Array:** Headless tarayıcıların boş veya sahte `navigator.plugins` yapıları.
* **Native Hook Tespiti:** Saldırganların Canvas veya WebGL fonksiyonlarını JavaScript ile ezmesini (override) engellemek için `Function.prototype.toString` V8 native kod kontrolü ve gizli iframe üzerinden temiz prototip karşılaştırması.
* **Gated Brave Farbling:** Brave tarayıcısının parmak izi korumasından kaynaklanan sahte gürültü, yalnızca başka kritik bot anomalisi yoksa tolere edilir.

---

### Katman 5: Ağ Katmanı, Poisson Dağılımı ve Dinamik Ban
* **Poisson Anomali Analizi ($\lambda=2.0$):** İnsan tıklama ve istek aralıkları rastgeledir. Kısa sürede gerçekleşen aşırı yoğun istekler Poisson olasılık dağılımıyla hesaplanır ($P > 99\% \rightarrow \text{BLOCK}$).
* **Davranışsal Değişmezlik (Behavioral Invariance):** Farklı oturumlarda aynı deterministik fare şablonunu tekrar eden botnet'ler sliding-window ile izlenir.
* **Dinamik Ceza Merdiveni:**
  * 4 ardışık bot eylemi $\rightarrow$ 1 dakika dinamik IP karantinası.
  * 10 saniyede 100 istek (DoS/Brute-force) $\rightarrow$ Anında IP banı.
* **Anlık Olay Bildirimi (Webhooks):** Kritik bloklamalar arka planda Discord ve Telegram kanallarına asenkron olarak iletilir.

---

## ⚡ 4. Kanıtlanmış Performans Kriterleri (v0.7.9 Benchmark)

`synapse-shield benchmark` motoru ile AMD Ryzen / Intel modern CPU üzerinde 100 iterasyonla ölçülen deterministik gecikme tablosu:

| HATTIN ADIMI | ORTALAMA (Mean) | ORTANCA (P50) | P95 DAĞILIMI | KAPASİTE (Throughput) |
| :--- | :--- | :--- | :--- | :--- |
| 🧬 **19D Kinematik Çıkarım (Jerk, Fitts, DSP)** | **$73.7\,\mu s$** | $63.9\,\mu s$ | $106.8\,\mu s$ | **13.562 işlem / sn** |
| 🧠 **1D-CNN Pure NumPy Matmul Çıkarımı** | **$451.2\,\mu s$** | $404.7\,\mu s$ | $649.7\,\mu s$ | **2.216 çıkarım / sn** |
| 🔑 **Kriptografik Token & SQLite Atomik Nonce** | **$961.8\,\mu s$** | $843.2\,\mu s$ | $1.533\,\mu s$ | **1.040 doğrulama / sn** |
| 🛡️ **Uçtan Uca Tam Karar Gecikmesi** | **$828.1\,\mu s$ ($0.82\text{ ms}$)** | $734.8\,\mu s$ | $1.251\,\mu s$ | **~1.208 istek / sn** |

> **Özet:** Standart bir CPU çekirdeğinde **milisaniyenin altında ($<0.85\,\text{ms}$)** karar verilir; tek bir makine saniyede **1.200'den fazla** botu filtreler.

---

## 🚀 5. Gelecek Yol Haritası (v0.8.0 $\rightarrow$ v1.0.0)

```
  v0.7.9 (Mevcut)       --> Saf NumPy DSP & Kinematik (0.82 ms E2E / 73 us Kinematik)
        │
        ▼
  v0.8.0 [Ekim 2026]    --> "The Native Core" (Rust / PyO3, AVX2 SIMD) (<0.025 ms / 200k RPS)
        │
        ▼
  v0.8.5 [Kasım 2026]   --> "The Edge Sentinel" (Client-Side WASM & Sıfır-Bilgi KVKK)
        │
        ▼
  v0.9.0 [Aralık 2026]  --> "The Forensic SIEM" (Bot Tehdit Atfı & TÜBİTAK 2209-A)
        │
        ▼
  v1.0.0 LTS [Şubat 2027]--> "The Sovereign Shield" (Envoy/NGINX Sidecar & Enterprise WAF)
```

1. **v0.8.0 — Rust Çekirdeği (`synapse_core_rs`):** C-seviyesinde bellek güvenliği sağlayan Rust + PyO3 entegrasyonu ile AVX2 SIMD vektör komutları kullanılarak gecikme **$15 - 25\,\mu s$'ye** indirilecek; kapasite tek makinede **200.000+ RPS** seviyesine çıkacak.
2. **v0.8.5 — WebAssembly (WASM):** Tarayıcıda koşan istemci tarafı WASM motoru ile ham telemetri sunucuya gitmeden yerel doğrulanacak (Sıfır-Bilgi Gizlilik).
3. **v1.0.0 — Envoy / NGINX Sidecar:** Dilden bağımsız kurumsal bir WAF eklentisine dönüştürülerek Kubernetes kümelerinde Go, Java, Node.js servislerinin önüne kalkan olarak konumlandırılacak.
