# İleri Düzey Yazılım Projeleri: Mimari Tasarım Dokümanı

Bu doküman, saf yazılım (pure-software) kısıtlamalarına bağlı kalınarak tasarlanmış 8 farklı ileri düzey yazılım projesinin sistem mimarilerini, bileşen yapılarını ve teknoloji yığınlarını (Tech Stack) içermektedir. Doküman tamamen objektif mühendislik standartlarına göre hazırlanmıştır.

---

## 1. SonarX (Akustik Doppler Arayüzü)
Ultrasonik ses dalgaları ve Doppler kayması (Doppler Shift) prensibini kullanarak fiziksel donanım (kamera/sensör) gerektirmeden el hareketlerini algılayan etkileşim motoru.

### 1.1. Sistem Bileşenleri
* **Emitter Daemon:** Hoparlör üzerinden insan duyma eşiği üzerindeki (18-22 kHz) sabit veya sweep frekanslı sinyalleri sürekli yayınlayan servis.
* **Audio Capture Interface:** Mikrofon donanımından RAW PCM verisini kesintisiz ve asenkron (non-blocking) şekilde okuyan katman.
* **DSP (Dijital Sinyal İşleme) Pipeline:** Gelen ses sinyallerine bant geçiren filtre (Band-pass filter) uygulayan ve STFT (Short-Time Fourier Transform) ile frekans spektrumunu hesaplayan modül.
* **Inference Engine:** Zaman-frekans matrislerindeki Doppler kaymalarını algılayarak, 1D-CNN (Convolutional Neural Network) modeli ile (Sağ, Sol, Tıkla) sınıflandıran analiz motoru.
* **OS Event Injector:** Elde edilen tahmini (prediction) işletim sistemi seviyesindeki sanal fare/klavye komutlarına dönüştüren sürücü/servis.

### 1.2. Teknoloji Yığını
* **Ses İşleme:** Python `sounddevice`, `numpy`, `scipy` (Signal Processing)
* **Model Eğitimi & Çıkarım:** `TensorFlow` / `PyTorch`, `ONNX Runtime`
* **Sistem Entegrasyonu:** `PyAutoGUI` / `ctypes` (WinAPI)

---

## 2. Vocalis (Ses Biyobelirteç Tanılama)
İnsan sesindeki mikro dalgalanmaları ve akustik anormallikleri analiz ederek nörolojik hastalık (Depresyon, Parkinson vb.) riskini hesaplayan biyometrik analiz yazılımı.

### 2.1. Sistem Bileşenleri
* **Audio Preprocessor:** Ses kaydındaki arka plan gürültüsünü gideren (Noise Reduction) ve sesli/sessiz segmentleri ayıran (VAD - Voice Activity Detection) katman.
* **Feature Extractor:** Temizlenmiş sesten MFCC (Mel-frequency cepstral coefficients), Jitter (frekans kararsızlığı), Shimmer (genlik kararsızlığı) ve Formant frekanslarını matematiksel vektörler olarak çıkaran motor.
* **Predictive Modeling Layer:** İstatistiksel özellik vektörlerini alarak, önceden eğitilmiş XGBoost veya LSTM tabanlı model üzerinden anomali olasılık skoru hesaplayan yapay zeka katmanı.
* **Diagnostic Report Generator:** Analiz sonuçlarını tıbbi bir ön değerlendirme formatına (PDF/JSON) dönüştüren raporlama arayüzü.

### 2.2. Teknoloji Yığını
* **Ses & Spektral Analiz:** `librosa`, `parselmouth` (Praat tabanlı), `pydub`
* **Makine Öğrenmesi:** `scikit-learn`, `XGBoost`, `PyTorch`
* **Arayüz:** `FastAPI` (Backend API), `PySide6` (Desktop UI)

---

## 3. Cogni-Scroll (Bilişsel Etkileşim Motoru)
Standart web kamerası üzerinden yüz ve göz irisi hareketlerini izleyerek, kullanıcının bilişsel yükünü (Cognitive Load) ölçen ve arayüzü buna göre otonom yöneten sistem.

### 3.1. Sistem Bileşenleri
* **Vision Acquisition:** Kameradan RGB kareleri yakalayan ve donanım hızlandırması ile boyutlandıran görüntü okuyucu.
* **Landmark Detector:** MediaPipe entegrasyonu ile yüzdeki 468 koordinatı, özellikle göz kapağı açıklığını (EAR - Eye Aspect Ratio) ve iris konumlarını gerçek zamanlı hesaplayan motor.
* **Cognitive State Estimator:** Göz bebeği fiksasyon (odaklanma) sürelerini, göz kırpma frekansını ve mikro-mimikleri analiz ederek kullanıcının okuma hızını ve zorlanma seviyesini belirleyen algoritma.
* **Actuation Logic:** Bilişsel duruma göre (kullanıcı hızlı okuyorsa) ekranı otomatik kaydıran veya (kullanıcı zorlanıyorsa) ilgili cümlenin arka plan rengini/kontrastını artıran arayüz denetleyicisi.

### 3.2. Teknoloji Yığını
* **Görüntü İşleme:** `OpenCV`, `MediaPipe Face Mesh`
* **Durum Makinesi (State Machine):** `numpy`, özel Python heuristik sınıfları
* **Otonom Arayüz Yönetimi:** Ekran içi highlight işlemleri için `PyQt6` / Web eklentisi (JavaScript)

---

## 4. Omni-Recall (Semantik İşletim Sistemi Hafızası)
Sistem arka planında düzenli ekran kaydı alarak elde edilen optik verileri, vektör uzayına çıkaran ve doğal dil işleme (NLP) ile arama imkanı sunan lokal bellek motoru.

### 4.1. Sistem Bileşenleri
* **Capture Daemon:** CPU/GPU tüketimini minimize etmek için SSIM/pHash gibi yöntemlerle sadece değişen kareleri yakalayan ve WebP formatında sıkıştıran arka plan servisi.
* **Perception Engine:** Görüntü karelerindeki metinleri OCR ile çıkartan ve içerik yapısını analiz eden ayrıştırıcı katman.
* **Embedding Pipeline:** Çıkarılan metinleri ve sistem meta verilerini (pencere adı, zaman), ONNX tabanlı hafif bir transformer modeli ile yüksek boyutlu vektörlere çeviren modül.
* **Vector Database:** Tüm vektörlerin lokal olarak depolandığı, bellek ve disk optimizasyonlu veritabanı.
* **Query & Retrieval Engine:** Doğal dil sorgusunu vektör uzayına çevirerek Kosinüs Benzerliği aramasını yürüten ve lokal LLM aracılığıyla sonuçları anlamlandıran modül.

### 4.2. Teknoloji Yığını
* **Görüntüleme & OCR:** `mss` (Ekran yakalama), Windows `WinRT OCR` veya `Tesseract`
* **Vektörizasyon:** `sentence-transformers`, `ONNX Runtime`
* **Veritabanı:** `LanceDB` veya `SQLite` (`sqlite-vec` uzantısı ile)
* **Lokal LLM:** `llama.cpp` (Python bağlamaları ile)

---

## 5. Aero-Net (Merkeziyetsiz Afet Ağı)
Mevcut internet altyapısı kesildiğinde donanımların dahili ağ bileşenleri üzerinden mesh (örümcek) topolojisi kurarak iletişimi sürdüren iletişim katmanı.

### 5.1. Sistem Bileşenleri
* **Hardware Bridge Controller:** İşletim sisteminin Wi-Fi Direct ve Bluetooth Low Energy (BLE) arayüzlerini asenkron yöneten bağlantı katmanı.
* **Gossip Protocol Router:** Ağa bağlı bir düğümün (node) aldığı veri paketlerini, verinin yaşam döngüsüne (TTL) ve kimliğine göre diğer düğümlere dağıtan yönlendirme (routing) mantığı.
* **Local Storage & Sync:** Aktif bağlantı olmadığında mesajları geçici olarak saklayan ve yeni bir düğüm bulunduğunda veri senkronizasyonunu başlatan depolama birimi.
* **LLM Triage Engine (Opsiyonel):** Gelen afet yardım mesajlarını cihaz üzerinde çalışan minimal bir NLP modeli ile analiz ederek aciliyet skoruna göre kategorize eden önceliklendirme motoru.

### 5.2. Teknoloji Yığını
* **Ağ & Protokol:** TCP/UDP Socket Programlama, `bleak` (BLE), `Zeroconf` / `mDNS`
* **Şifreleme:** Veri bütünlüğü ve gizliliği için `cryptography` (AES-GCM / Elliptic Curve)
* **Veritabanı:** `SQLite` / `LevelDB`

---

## 6. Deep-Armor (Davranışsal Ransomware Terminatörü)
Sistem çağrılarını (System Calls) statik imzalara göre değil, davranışsal desenlere göre analiz ederek sıfırıncı gün (Zero-Day) zararlı yazılımlarını izole eden güvenlik duvarı.

### 6.1. Sistem Bileşenleri
* **User-Mode API Hooker:** İşletim sistemindeki kritik API fonksiyonlarına (Örn: `CreateFile`, `WriteFile`, `CryptEncrypt`) kanca atarak argümanları ve çağrı sıklıklarını dinleyen katman.
* **Telemetry Aggregator:** Dosya yazma hızları, işlem (process) yolları ve diske yazılan verinin Shannon Entropisi (şifrelenme belirtisi) gibi verileri pencereli (sliding-window) zaman aralıklarında toplayan modül.
* **ML Isolation Engine:** Gelen telemetri akışını Isolation Forest veya One-Class SVM gibi makine öğrenmesi modelleriyle değerlendirerek anomali skoru üreten motor.
* **Enforcement Module:** Anomali eşiği aşıldığında hedef uygulamanın (process) thread'lerini işletim sistemi seviyesinde durduran (Suspend) ve kullanıcıdan onay bekleyen aksiyon modülü.

### 6.2. Teknoloji Yığını
* **Sistem Kancalama (Hooking):** `Frida` / `MinHook` veya özel Python `ctypes` DLL wrapper'ları
* **Analiz & Model:** `numpy`, `scikit-learn`
* **Loglama & UI:** Windows Event Tracing (ETW) Entegrasyonu, `PyQt6`

---

## 7. Ghost-Swarm (Otonom Kodlama Ajanları)
Doğal dil istemlerini (prompt) kabul ederek gereksinim analizi, kod yazımı, test ve hata ayıklama süreçlerini tamamen otonom ajanlar arası haberleşme ile yürüten Swarm mimarisi.

### 7.1. Sistem Bileşenleri
* **Swarm Orchestrator:** Kullanıcı girdisini çözümleyerek görevleri ilgili alt ajanlara (Mimar, Geliştirici, Test Uzmanı vb.) dağıtan merkezi denetleyici.
* **Agent Framework:** Her bir ajanın sistem promptlarını (rol tanımı, amaç, kullanılabilir araçlar) ve hafıza geçmişlerini (context window) yöneten iletişim ağı.
* **Sandboxed Execution Environment:** Geliştirilen kodun ana işletim sistemine zarar vermeden, kısıtlı kaynaklara sahip bir konteyner içerisinde asenkron derlenip çalıştırıldığı güvenli alan.
* **Feedback & Debug Loop:** Derleme ve çalışma sırasındaki hata çıktılarını (stderr, traceback) otomatik olarak toplayan ve çözümü için ilgili ajana geri besleme (feedback) yapan iterasyon döngüsü.

### 7.2. Teknoloji Yığını
* **Ajan (Agent) Mimarisi:** `LangChain`, `CrewAI`, veya `AutoGen`
* **LLM Arayüzü:** API bağlamaları (OpenAI/Anthropic) veya yerel modeller için `Ollama` / `vLLM`
* **İzolasyon (Sandboxing):** `Docker SDK for Python`, asenkron süreç (subprocess) yönetimi

---

## 8. Nero-Compress (Üretken Video Sıkıştırma)
Geleneksel piksel tabanlı video sıkıştırma algoritmaları yerine, kaynakta kinematik işaretçilerin elde edilip hedefte üretken (Generative) yapay zeka ile görselin yeniden oluşturulduğu iletim protokolü.

### 8.1. Sistem Bileşenleri
* **Sender / Landmark Extractor:** Kamera akışından sadece yüzdeki ve bedendeki spesifik x, y, z koordinatlarını çıkaran (piksel verisini çöpe atan) bileşen.
* **Serializer & Transmit Protocol:** Çıkarılan koordinatları, delta sıkıştırması (sadece değişen noktaların gönderilmesi) ile birleştirerek çok düşük bant genişliğine sahip UDP paketlerine dönüştüren katman.
* **Receiver / Deserializer:** Karşı tarafın ağ arayüzünde UDP paketlerini dinleyen ve kayıpları enterpolasyon ile telafi ederek düzgün (smooth) bir koordinat akışı sağlayan modül.
* **GAN Generator (Üretici Ağ):** Göndericinin önceden alınmış tek bir referans fotoğrafı ve gelen koordinat haritalarını girdi olarak kabul ederek, pikselleri yapay zeka aracılığıyla hedef tarafta yeniden "çizen" render motoru.

### 8.2. Teknoloji Yığını
* **Özellik Çıkarımı:** `MediaPipe` (Face Mesh / Pose)
* **Ağ Aktarımı:** Asenkron `UDP Sockets`, `Protobuf` / `MessagePack`
* **Görüntü Üretimi (Generation):** `PyTorch` tabanlı First-Order-Model (veya benzeri bir AutoEncoder / GAN ağı)
* **Görüntü İşleme / Gösterim:** `OpenCV`, `NumPy`
