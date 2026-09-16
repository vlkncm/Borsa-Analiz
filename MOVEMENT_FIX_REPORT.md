# Yüksek Hareket Radarı düzeltmesi — sonuç raporu

**MODEL PERFORMANS KABULÜ: FAIL.** Skor doygunluğu giderildi; aynı örnek-dışı veride öncelikli başarı metrikleri iyileşmedi. Bu EXE deneysel düzeltme çıktısıdır; başarılı model sürümü olarak kabul edilmedi. Kurulu uygulamanın yerine yüklenmedi.

## Baz

- BAZ ALINAN SÜRÜM: v10.4.2 (`APP_VERSION=10.4.2`, en yeni tag v10.4.2).
- BAZ COMMIT: `7abcfaa924e762436cfa3d76023d28316d9565de`.
- Tek kod kaynağı: https://github.com/vlkncm/Borsa-Analiz
- `origin` doğrulandı; fetch/tags, checkout main, ff-only pull, log, tag ve HEAD kontrolleri tamamlandı.
- Eski yerel v10.3.3 dosyaları kullanılmadı. OLD karşılaştırması yukarıdaki güncel v10.4.2 commit’inden alınan kodla yapıldı. İlk doğrulama aşamasında push yapılmadı; kullanıcının sonraki talebiyle düzeltme v10.4.3 yayınına hazırlandı.

## Kök neden

1. `ertesi_gun_motoru.t1_movement_trade_scores`: `clip(50 + katkılar, 0, 100)`. Pozitif katkıların teorik toplamı yaklaşık 94 puan; +50 başlangıcıyla normal güçlü adaylar 100 sınırında birbirine eşitleniyor. Sonradan sıralama kaybolan bilgiyi geri getiremiyor.
2. RVOL ve hacim ivmesi aşağı yönlü fiyat hareketinde de olumlu katkı yapabiliyordu. Para akışı/RS gibi göstergeler hareket skorunda yeterince yer almıyordu. MACD değişiminin fiyat birimini ATR yüzdesine bölmek de ölçek sorununa yol açıyordu.
3. Python min/max zincirleri bazı NaN girdilerini olumlu sınırlara çevirebiliyordu; sonradan yapılan sonlu-değer kontrolü bunu yakalamıyordu.
4. Radar önce kesilmiş skorla geniş 30’u seçiyordu. Güven etiketi canlı veri teyidinden bağımsız olarak kalite skorundan türetiliyordu. Seviye aritmetiğinin geçerli olması canlı teyit yerine kullanılabiliyordu.
5. Arka plan taraması benchmark göndermediğinden BIST Relative Strength boş kalıyordu. T+1/T+2 ham model logit’i ile hareket puanı da aynı alanda karışıyordu.

## Düzeltme

- İşaretli, boyutsuz faktör katkıları sabit ağırlık normuyla ölçekleniyor: `raw = sum(katkılar) / sqrt(sum(ağırlık²))`; `Movement = 50 + 100/pi * atan(raw)`. Kesme yok; aynı skora zorlayan sıra bazlı değer ataması yok. Sıralama yuvarlanmamış sürekli değerle yapılıyor.
- Pozitif RS, para akışı, yön teyitli hacim/ivme, kapanış, breakout ve varsa VWAP katkıları; başarısız breakout, üst fitil, gap, likidite, eski/eksik veri, kötü R/R ve yönsüz oynaklık cezaları eklendi.
- Negatif piyasa taramayı kapatmıyor. Negatif piyasada zayıf RS cezalandırılıyor; güçlü pozitif ayrışma aday kalabiliyor.
- Güven, veri kapsamı ve canlı teyitten ayrı hesaplanıyor. Günlük veri canlı teyit sayılmıyor; teyitsiz aday yüksek güvenli/seçkin olamıyor.
- XU100 benchmark’ı arka plan işçisinde taşınıyor. Sektör ve VWAP verisi yoksa olumlu veri uydurulmuyor.
- Hareket skoru kalibre olasılık değildir. Mevcut olasılık model dosyası yeniden eğitilmedi ve değiştirilmedi.

## OLD → NEW — aynı örnek-dışı kayıtlar

02, 03 ve 04 Eylül 2026: sırasıyla 470, 513 ve 514 ortak hisse; toplam 1.497 hisse/oturum. Seans kapanmadan kaydedilen veya eşzamanlı cache’i/ileri penceresi olmayan kayıtlar dışlandı. Bu küçük, yeniden kurulabilen kesişim tüm BIST evrenini temsil etmez.

Pozitif etiket: sonraki 1/2 seansın en yüksek fiyatı T kapanışına göre en az %7 artmış mı? Precision ve Hit Rate radar ilk 10; Recall@20 geniş listenin ilk 20’si; FPR = seçilen yanlış pozitif / evrendeki tüm negatifler. Oranlar oturum ortalaması; ileri getiri sonraki 1/2 seans kapanışına göre ilk 10’un getirisi, medyan bütün seçili kayıtların medyanıdır.

### T+1

| Metrik | OLD | NEW |
|---|---:|---:|
| Precision@3 | %44.444 | %33.333 |
| Precision@5 | %26.667 | %20.000 |
| Precision@10 | %20.000 | %16.667 |
| Recall@20 | %11.024 | %12.328 |
| %7+ Hit Rate | %20.000 | %16.667 |
| False Positive Rate | %1.755 | %1.835 |
| Average Forward Return | %0.040 | %-0.386 |
| Median Forward Return | %0.254 | %0.494 |

### T+2

| Metrik | OLD | NEW |
|---|---:|---:|
| Precision@3 | %55.556 | %55.556 |
| Precision@5 | %46.667 | %46.667 |
| Precision@10 | %40.000 | %36.667 |
| Recall@20 | %8.939 | %7.863 |
| %7+ Hit Rate | %40.000 | %36.667 |
| False Positive Rate | %1.490 | %1.565 |
| Average Forward Return | %2.517 | %1.766 |
| Median Forward Return | %2.546 | %3.125 |

**Sonuç:** T+1 Precision@3/@5/@10 ve ortalama ileri getiri geriledi. T+2 Precision@10 ve ileri getiri de geriledi. Test sonuçlarını gördükten sonra aynı pencerelerde başarı üretmek için ağırlık ayarı yapılmadı. Performans artışı iddia edilmiyor.

## 15.09.2026 regresyonu

- Yerel tarama zamanı: 2026-09-15 00:32:01+03:00 – 2026-09-15 00:32:14+03:00.
- Girdi kesimi: 14.09.2026. 515 yeniden kurulabilen standart hisse. 15.09 kapanışı ne girdiye ne bu kontrole katıldı.
- Yeniden oynatılan ilk 10’da 100’e doyan aday: **7 → 0**.
- Yeni ilk 10 skorları 77,231–82,708 aralığında, birbirinden farklı; tümünde canlı teyit olmadığı için güven DÜŞÜK ve Seçkin Aday HAYIR.
- Kayıt, radar ekranının kendisini saklamıyor. Kullanıcının bildirdiği 10/10 görünümü birebir yeniden üretilemedi; yeniden kurulan kayıtta 7/10 doygunluk var. Bunun sınırı açıkça korunmuştur.

## %7+ modeli / değerlendirme kontrolü

- Paketli artefaktın test pozitif oranı: T+1 %8,231; T+2 %15,046. Accuracy başarı ölçütü olarak kullanılmadı.
- Eski günlük metrik hesabı pozitif örnek olmayan günleri dışlıyordu; bu seçim yanlılığı kaldırıldı.
- Eski `false_positive_rate_at_10`, gerçekte ilk 10 içindeki yanlış keşif oranıydı. FPR paydası tüm negatif örnekler olarak düzeltildi.
- Yeni eğitim çağrılarında train/calibration/test sınıf desteği denetleniyor ve sınıf sayıları raporlanıyor. Sonuç/ileri getiri alanlarının özellik olarak geçirilmesi reddediliyor.
- Gelecekte tamamlanan test dönemine ait artefaktla geçmiş tarihe tahmin üretilmesi engellendi. Gelecek etiketler yalnız evaluation tarafında.

## Değişen dosyalar

- `ertesi_gun_motoru.py`: sürekli yönlü hareket skoru, veri kesimi ve özellik aktarımı.
- `trade_adaylari.py`: ham skora göre deterministik sıralama, bağımsız güven ve seçkin kapısı.
- `t1t2_tahmin_sistemi.py`: yönlü özellikler, logit/skor ayrımı, zaman ve metrik kontrolleri.
- `app_qt.py`: yalnız `NextDayWorker` veri/benchmark bağlantısı. Görsel kod değiştirilmedi.
- `test_movement_regression.py`: 20 regresyon testi.
- `movement_evaluation.py`: salt okunur eşlenik tarihsel karşılaştırma aracı.
- `MOVEMENT_FIX_REPORT.md`: bu rapor. `.validation/`: test/build kayıtları ve tekrar üretim yardımcıları.

## Test / build / koruma

- SCORE SATURATION: **PASS**.
- LOOK-AHEAD: **PASS** — test edilen kesim, geçmiş artefakt ve offline replay yolları. Veri sağlayıcısının cache kaydından önce yapmış olabileceği tarihsel revizyonlar bağımsız doğrulanamadı.
- TEST: **Passed — 259 test + 4 alt test; 1 skipped, 1 warning.** Atlanan mevcut test `eb04eb9:backtest.py` tarihsel baseline’ını `git` PATH üzerinden arıyor; bu ortamda Git PATH’te yok. Güncel kaynakla Günlük Trade testleri geçti.
- BUILD: **PASS** — mevcut iki `.spec` dosyası değişmeden PyInstaller ile üretildi.
- EXE startup: **PASS**, ayrı profil/offscreen, 15 saniye.
- Paket içindeki scoring, T+1/T+2, Günlük Trade, dashboard ve app kodları kaynakla karşılaştırıldı: eşleşiyor.
- `app_qt.py` içinde arka plan işçisi dışındaki AST aynı. `dashboard_ui.py`, Günlük Trade motoru/göstergeleri, BIST30 ve 50 TL altı seçim modülü değişmedi.
- ARAYÜZ DEĞİŞİKLİĞİ: **YOK** — tema, renk, font, sekme, buton, tablo sütunları ve yerleşim korunmuştur. Talep edilen skor/güven içerikleri değişmiştir.

## Yeni EXE

`C:\Users\yeliz\Projects\Borsa-Analiz\dist\BorsaAnalizProMAX\BorsaAnalizProMAX.exe`

Aynı klasörde `BorsaTaramaMotoru.exe` ve `_internal` bağımlılıkları bulunur; paket klasörünü birlikte kullanın. Installer istenmediğinden ayrıca kurulmadı. Kurulu sürümün üzerine yazılmadı.

SHA-256: `6c661a06c7386091d9731786bb770b31ddebd674b47ab708fe947b37cc485480`

## Kanıt dosyaları

- `.validation/full-tests.log`, `.validation/full-tests.xml`
- `.validation/build-main.log`, `.validation/build-scanner.log`, `.validation/build-dependencies.txt`
- `.validation/packaged-code.json`, `.validation/smoke-result.json`, `.validation/preservation.txt`
- `.validation/replay/comparison.json`, `.validation/replay/paired_scores.json`
- `.validation/regression_20260915.json`, `.validation/SHA256SUMS.txt`

**Genel kabul: FAIL (performans).** Teknik düzeltme ve EXE tamamlandı; daha iyi hisse seçimi hedefi bu veriyle sağlanmadı.

## v10.4.3 yayın notu — 16.09.2026

Kullanıcının sonraki talebiyle aynı düzeltme v10.4.3 olarak sürümlendi. Uygulama ve installer sürümü, README indirme bağlantıları ve CHANGELOG güncellendi. Yukarıdaki skor/model karşılaştırması değişmedi; performans kabulü hâlâ FAIL.

Yayın paketi `release/v10.4.3/` altında mevcut `.spec` dosyalarıyla yeniden derlenir. Kurulum dosyası `SetupOutput/Setup_Borsa_Analiz_Pro_MAX_v10.4.3.exe` olur. GitHub `main` ve `v10.4.3` etiketi bu düzeltmeyi içerir; release en son sürüm olarak yayımlanır. Önceki bölümlerdeki yerel EXE yolu ve SHA-256 ilk doğrulama çıktısına aittir. v10.4.3 paketinin güncel hash değerleri release ile verilen `SHA256SUMS.txt` dosyasındadır.

Arayüz düzeni değişmedi; pencere başlığındaki sürüm numarası v10.4.3 oldu. Kurulu uygulama ve kullanıcı geçmişi üzerine yerel kurulum yapılmadı.
