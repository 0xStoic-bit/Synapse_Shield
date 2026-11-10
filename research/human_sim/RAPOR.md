# v0.10.6 — İnsan yanlış-pozitif ölçümü (ilk tur)

Tarih: 2026-11-10. Durum: ilk ölçüm motor değişmeden yapıldı; ardından eğrilik kuralı (Düzeltme 1) ve inceleme bulguları (Düzeltme 2) motorda düzeltildi ve yeniden ölçüldü.

## Yöntem

İki bağımsız ölçüm yapıldı:

1. **Gerçek insan verisi (yüksek güven):** SapiMouse (120 kişi, tarayıcıda toplanmış fare verisi) oturumları pencerelere bölündü, SDK'nın yapacağı gibi 30 ms örneklendi, gönderim son tıklamada kabul edildi ve `core.evaluate_synapse_request_sync` karar yolundan geçirildi (`replay_sapimouse.py`). Klavye verisi yok; tarayıcı profili sıradan bir masaüstü Chrome.
2. **Biyomekanik simülatör (orta-düşük güven):** Parametreleri motorun eşiklerinden değil, SapiMouse ve CMU Keystroke verisinden ölçülen insan dağılımlarından gelen bir nüfus (`simulator.py`). Giriş formu senaryoları: fare, touchpad, klavye-only, parola yöneticisi, mobil (Android/iOS). Cihaz/yaş/titreme oranları literatüre dayalı varsayımdır.

Veri setleri `data/external/` altında, depoya girmez. Çıkarılan özet istatistikler `params/` altında.

## Simülatörün gerçek veriye uyumu (validate.py)

Simülatörün ürettiği hareketler, SapiMouse'u ölçen aynı fonksiyonla ölçüldü (18-53 yaş, fare/touchpad):

| Ölçü | Gerçek p5 / medyan / p95 | Simülatör |
| --- | --- | --- |
| Süre (ms) | 372 / 684 / 1497 | 221 / 666 / 1462 |
| Düzlük | 0,24 / 0,89 / 0,99 | 0,44 / 0,94 / 0,99 |
| Yanal sapma / mesafe | 0,02 / 0,11 / 1,07 | 0,03 / 0,12 / 0,98 |
| Tepe hız zamanı (oran) | 0,05 / 0,25 / 0,58 | 0,06 / 0,26 / 0,68 |
| Alt-hareket | 1 / 2 / 6 | 1 / 2 / 14 |
| 100 ms+ duraklama | 0 / 0 / 2 | 0 / 0 / 2 |
| Son %10'da geçen süre | 0,18 / 0,49 / 0,84 | 0,19 / 0,43 / 0,84 |

**Bilinen eksik:** Simülatörün yörüngeleri üst türevlerde (ivme/jerk dokusu) gerçek elden daha pürüzsüz: motorun "polynomial acceleration" ve "mathematical smoothness" kuralları simüle insanlarda sık, gerçek insanlarda nadiren tetikleniyor. Bu yüzden simülatörün mutlak FPR'si henüz güvenilir değil; gerçek veri ölçümü esas alınmalı.

## Sonuçlar

### Gerçek insanlar (SapiMouse)

| Pencere | n | Engellendi | Geçti | En az bir penceresi engellenen kişi |
| --- | --- | --- | --- | --- |
| 20 sn (son tıklamada biter) | 1.507 | %87,8 | %12,2 | 120 / 120 |
| 6 sn (girişe yakın) | 4.844 | %68,0 | %32,0 | 120 / 120 |

Engellenen pencerelerde tetiklenen kurallar (6 sn): "Synthetic differential curvature profile" 3.260 (pencerelerin %67'si; kural tek başına +65 puan, eşik 50), "Superhuman mouse velocity" 75, "Lack of physiological sub-movement decomposition" 28, "Superhuman artificial sub-movement stutter" 20.

"Sub-movement stutter" pencere uzunluğuna bağlı: 20 sn'de 969 kez, 6 sn'de 20 kez. Kural, tepe sayısını hareket sayısına göre normalize etmiyor gibi.

### Simüle nüfus (2.000 kişi; dikkatle okunmalı)

| Grup | n | Engellendi |
| --- | --- | --- |
| Genel | 2.000 | %81,2 |
| Fare | 1.035 | %73,1 |
| Touchpad | 499 | %82,6 |
| Klavye-only | 66 | %95,5 |
| Mobil Android | 273 | %98,2 |
| Mobil iOS | 127 | %97,6 |

Simülasyonun gösterdiği, gerçek veriyle henüz doğrulanmamış ama kuralları adıyla işaret eden riskler:
- **Klavye-only kullanıcılar:** "Interactive events occurred without mouse movement telemetry" (bilinen sorun, engine.py +50 kuralı).
- **Dokunmatik ekranlı dizüstü:** "Spoofed touch_supported flag on non-capacitive desktop pointer trajectory": dokunmatik ekranlı laptopta fare kullanan gerçek insanlar bu kurala takılabilir.
- **Mobil:** Neredeyse tamamı engelleniyor; ama mobil için gerçek veri yok (HuMIdb imzalı lisans istiyor), simülatörün mobil modeli doğrulanmadı.

## Sonuç

Gerçek insan verisi, motorun mevcut hâliyle masaüstü fare kullanıcılarının büyük çoğunluğunu (6 sn'lik pencerelerde %68) engellediğini gösteriyor; nedenin neredeyse tamamı tek bir kural (eğrilik profili). v0.10.5 raporundaki "curvature jitter eşikleri ölçek bağımlı" açık maddesiyle tutarlı. Test fikstürleri sentetik insanlar olduğu için bu, testlerde görünmüyordu.

## Sınırlar

- SapiMouse bir tıklama görevi, giriş formu değil; klavye yok. Ama hareketler gerçek insan hareketi.
- Yalnızca 120 kişi, çoğu genç üniversite öğrencisi. Yaşlılar ve dokunmatik cihazlar temsil edilmiyor.
- SapiMouse'un lisansı yazılı değil; yalnızca yerel değerlendirme yapıldı, ham veri paylaşılmıyor.
- Simülatörün mutlak sayıları, üst türev dokusu düzeltilene kadar güvenilir değil.

## Düzeltme 1: eğrilik kuralı (2026-11-10)

**Kök neden.** κ = |v×a| / |v|³ hız sıfıra yaklaşınca patlıyor. Gerçek insan hedefe yaklaşınca duruyor; tarayıcı imleç dururken olay göndermediği için, sonraki 1 piksellik düzeltme 150-550 ms'lik bir boşluğa bölünüyor ve |v| ≈ 0,003 px/ms çıkıyor. Bu noktalarda κ 30-100'e ulaşıyor ve `var_k > 10` koşulu ("kaotik eğrilik", 0.85) gerçek pencerelerin %67'sinde tetikleniyordu. Aynı dal botların neredeyse hiçbirini yakalamıyordu (min-jerk %5,5, jitter %13; o yakalamalar da aynı durma artefaktındandı). Ölçüm: `curvature_study.py`.

**Düzeltme.** Kaotiklik dalları (0.85/0.75) artık yalnızca "hareket eden" noktalarda değerlendiriliyor: iki komşu adımı da ≥ 5 px olan noktalar, en az 10 tane. Düzgünlük dalları (0.95/0.90) tüm noktalarda VEYA hareket eden noktalarda bakıyor; bu sayede uçlarda duran min-jerk botları da yakalanıyor. Rust (`curvature.rs`) ve Python (`features._curvature_metrics`) aynı mantıkta; eşitlik testi var.

Yalnızca eğrilik kuralının ≥ 0.75 verdiği oran. Botlar iki biçimde ölçüldü: üreticilerin verdiği 0,01 px koordinatlarla ve tarayıcının gönderdiği gibi tam sayı piksele yuvarlanmış hâlde. İnsan verisi (SapiMouse) zaten tam sayı.

| Kural | İnsan | Bézier (0,01 / tam) | Doğrusal (0,01 / tam) | Min-jerk (0,01 / tam) |
| --- | --- | --- | --- | --- |
| Eski | %67,3 | %98,5 / %23,5 | %100 / %45,5 | %6,5 / %0,5 |
| Yeni, 3 px | %3,1 | %99 / %23,5 | %100 / %45,5 | %100 / %4 |
| **Yeni, 5 px (seçilen)** | **%0,39** | %99 / %23,5 | %100 / %45,5 | %100 / %17 |
| Yeni, 6 px | %0,23 | %99,5 / %23,5 | %100 / %45,5 | %100 / %35 |

Tam sayı koordinatlarda eğrilik kuralının botları tek başına yakalama gücü düşük: merdiven biçimli kuantizasyon `var_k`'yı 1e-4'ün üstüne çıkarıyor. Bu eski kuralda da aynıydı. Yeni kural hiçbir bot türünde eskisinden kötü değil. Not: depodaki `generate_minimum_jerk_telemetry` düz çizgi üretiyor (straightness = 1.0); eğri min-jerk botu testlerde ayrıca var.

**Sonuç (tam karar yolu):**

| Ölçüm | Önce | Sonra |
| --- | --- | --- |
| Gerçek insan, 6 sn pencere | %68,0 engel | %1,4 engel |
| Gerçek insan, 20 sn pencere | %87,8 engel | %2,7 engel |
| Depodaki bot desenleri, 0,01 px (1.200, `bot_tpr.py`) | %100 Bot | %100 Bot |
| Depodaki bot desenleri, tam sayı px (1.200) | - | %100 Bot (başka kurallar sayesinde) |
| Simüle nüfus (2.000) | %81,2 | %65,8 (Düzeltme 2 sonrası: %47,2) |

Kalan gerçek-insan engellemeleri (6 sn): sub-movement decomposition 28, eğrilik 19, polinom ivme 12, pürüzsüzlük 11. 20 sn'de: stutter 36, superhuman velocity 35; stutter kuralı medyan risk skorunu 45'e taşıyor (tek başına eşik altı ama başka bir kuralla birleşince engelliyor).

**Sınırlar:**
- Bot tarafı yalnızca depodaki üreticilerle ölçüldü; bunlar zaten başka kurallara da takılıyor. Gerçek bir TPR için daha güçlü bir bot düzeneği gerekli.
- **Atlatma riski:** Kuralı bilen bir bot, adımlarını 5 px'in altında tutarak (ya da iki ardışık adımın birlikte ≥ 5 px olmasını engelleyerek) kaotiklik dallarını (0.85/0.75) devre dışı bırakabilir. Düzgünlük dalları (0.95/0.90) tüm noktalarda çalışmaya devam ediyor. Kaotiklik dalları eski hâlinde de botların neredeyse hiçbirini yakalamıyordu (jitter botunun %13'ü, o da durma artefaktından). Kalıcı çözüm, eğriliği yay uzunluğuna göre yeniden örneklemek olur; açık iş.

## Düzeltme 2: dış inceleme bulguları (2026-11-10)

Dış incelemedeki her madde kodla doğrulandı. Doğrulananlar:

| Bulgu | Durum | Etki |
| --- | --- | --- |
| Min-jerk testleri `gated` yolunu sınamıyordu (Rust testi düz çizgi, Python testi yuvarlanmamış) | Düzeltildi: 0,01 px'e yuvarlanmış min-jerk testleri yalnızca `gated` yoluyla geçiyor; testte bunun koşulu da doğrulanıyor | Mutasyon testinde `gated` adayı artık yakalanır |
| `all` ve `gated` için dκ/dt zaman adımı farklıydı | Düzeltildi: gated aralık, aradaki `dt_a` adımlarının toplamı (`_gated_dts` / `gated_dts`); hiç nokta atılmadığında iki hesap aynı | Doğrudan test edildi |
| Kural 4.C (polinom ivme) dokunmatikte de çalışıyordu | Düzeltildi: `and not is_touch` | Simüle mobil: %97 → %2-3 engel |
| `key_interval_avg` için alt sınır yoktu (negatif/0 aralık +50 alıyordu) | Düzeltildi: kural, Brave istisnası ve tehdit etiketi tek `_superhuman_key_interval` fonksiyonunu kullanıyor (`0 < aralık < 25`) | Shift/rollover'lı yazımda yanlış uyarı, Brave tavanının kaybı ve yanlış `ROBOTIC_KEYSTROKE` etiketi kalktı |
| `bump_version.py`, `_version.py`'yi güncellemiyordu | Düzeltildi; dosya yoksa ya da satır bulunamazsa hata veriyor | Testle doğrulandı |
| Mobil güven indirimleri (-15/-10/-10) Bölüm 4'ten önce, risk 0 iken uygulanıyor | **Doğru, değiştirilmedi.** İndirimler şu an fiilen etkisiz. Etkin hâle getirmek mobil botların puanını 35'e kadar düşürür; mobil yanlış pozitifin asıl kaynağı 4.C'ydi. Karar bekliyor | - |
| Simülatörde titreme saf sinüs | Değiştirildi: 8-12 Hz dar bantlı gürültü. **Ama FFT uyarısının sebebi bu değil:** titreme tamamen kapatılınca da uyarı sayısı aynı kalıyor (77 → 84). Sebep simülatörün aşırı pürüzsüz yolları | - |

Yeni gerçek veri bulgusu (CMU): "Superhuman input frequency" kuralı (ortalama up→down aralığı 0-25 ms) gerçek şifre yazımlarının **%1,4'ünü** yakalıyor; 51 kişiden 3'ü yazımlarının en az %10'unda bu kurala takılıyor. Kuralın eşiği ayrıca incelenmeli. Simülatör bu oranı fazla gösteriyor (%4).

## Önerilen sonraki adımlar

1. ~~Eğrilik kuralı~~ (düzeltildi, yukarıda).
2. "Sub-movement stutter" kuralını hareket sayısına/süreye göre normalize et (20 sn pencerelerde en sık neden).
3. Simülatöre gerçek elin üst türev dokusunu ekle (SapiMouse'tan ivme/jerk spektrumu ölçülerek) ve yeniden doğrula. FFT, pürüzsüzlük ve polinom ivme uyarılarının simülatördeki kaynağı bu.
4. Klavye-only ve dokunmatik ekranlı dizüstü kurallarını ayrıca incele.
5. "Superhuman input frequency" eşiğini CMU dağılımına göre yeniden belirle.
6. Mobil güven indirimlerinin sırası için karar ver (yukarıda).
7. Tam sayı koordinatlarda eğrilik kuralını güçlendir (yay uzunluğuna göre yeniden örnekleme); bu, 5 px atlatma riskini de kapatır.
8. Her değişiklikten sonra `replay_sapimouse.py` ve `run_eval.py` ile yeniden ölç; bot tarafını (TPR) bot düzeneğiyle kontrol et.
