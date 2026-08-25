# Borsa Analiz Pro MAX — Günlük Trade, Doji, VWAP, Pivot ve Olasılıklı Yükseliş Tahmini

## Codex’e verilecek görev

`https://github.com/vlkncm/Borsa-Analiz.git` deposunda aşağıdaki geliştirmeyi uçtan uca uygula. Yalnızca plan veya örnek kod üretme; mevcut kodu incele, değişiklikleri gerçekten yap, testleri yaz ve çalıştır, hataları düzelt, dokümantasyonu güncelle ve sonunda değişen dosyaları, doğrulama sonuçlarını ve kalan sınırlamaları özetle.

Bu çalışma kısa vadeli işlem kararlarının kalitesini ve ölçülebilirliğini artırmayı amaçlar. Hiçbir yerde “kesin kazanç”, “garantili yükseliş” veya gerçekleşeceği kesinmiş gibi tek bir fiyat tahmini üretme. Sonuçları olasılık, tahmin aralığı, veri tarihi, örnek sayısı ve geçmiş test sonuçlarıyla birlikte göster. Uygulama emir göndermeyecek; karar-destek ve kâğıt işlem aracı olarak kalacak.

## 1. İlk olarak depoyu ve mevcut davranışı doğrula

1. Depodaki tüm `AGENTS.md` dosyalarını ve ilgili talimatları oku.
2. `main` dalındaki mevcut mimariyi, sürümü, bağımlılıkları ve test komutlarını belirle.
3. Özellikle şu dosyaları incele:
   - `app_qt.py`
   - `borsa_tarayici.py`
   - `karar_motoru.py`
   - `gunluk_islem_plani.py`
   - `formasyon_motoru.py`
   - `veri_saglayici.py`
   - `backtest.py`
   - `gelismis_analiz.py`
   - `test_gunluk_plan.py`
   - ilgili diğer testler, mobil/PWA dosyaları ve paketleme dosyaları
4. Mevcut kullanıcı değişikliklerini ve ilgisiz davranışları koru. Büyük dosyaları gereksiz yere yeniden yazma.
5. Önce kısa bir uygulama planı çıkar; ardından kullanıcıdan tekrar onay beklemeden uygulamaya geç.

Mevcut depoda `beklenen_getiri_yuzde` ve `model_olasiligi` alanlarının zaten bulunduğunu dikkate al. Bunları yeni günlük işlem tahminiyle isim veya anlam bakımından karıştırma. Gerekirse geriye uyumlu, daha açık adlara taşı ve eski alanları bir geçiş süresince koru.

## 2. Yeni “GÜNLÜK TRADE” bölümü

PySide6 masaüstü uygulamasına, sol menüden açılan ayrı bir `GÜNLÜK TRADE` sayfası ekle. Mevcut `QStackedWidget` indekslerini körlemesine kaydırma; bütün bağlantıları ve sabit indeks kullanan metotları denetle. Mümkünse sayfa kimliği/enum benzeri daha güvenli bir yönlendirme kullan.

Yeni ekranın amacı, aynı gün içinde değerlendirilebilecek BIST adaylarını veri kalitesi ve risk kapılarından geçirerek göstermektir. Varsayılan evren BIST 30 olsun; mevcut takip listesinden tarama seçeneği de eklenebilir. Uygun aday yoksa tabloyu zorla doldurma ve açıkça `Bugün ölçütleri geçen aday bulunamadı` yaz.

Ekranda en az şu kontroller yer alsın:

- “Taramayı Başlat / Yenile” düğmesi
- Tercih edilen intraday zaman aralığı: 5 dakika ve 15 dakika
- Hesap büyüklüğü (TL)
- İşlem başına risk yüzdesi; varsayılan `%0,5`, kullanıcı üst sınırı `%1`
- En düşük risk/getiri; varsayılan `1,8`
- Yalnızca teyitli sinyalleri göster seçeneği
- Kâğıt işlem kaydı oluşturma imkânı; gerçek aracı kurum emri gönderme yok

Tabloda ve detay kartında en az şu alanları göster:

- Hisse
- Sinyal ve veri zamanı
- Veri kaynağı, veri gecikmesi ve tazelik durumu
- Referans/güncel fiyat
- Önerilen alış bandı
- Hedef fiyat
- Stop fiyatı
- `Hedef Potansiyeli %`
- `Beklenen Gün Sonu Hareketi %`
- `Tahmin Aralığı %` (örneğin P10–P90 veya uygun, dokümante edilmiş başka bir aralık)
- `Hedefe Stop’tan Önce Ulaşma Olasılığı %`
- Bu olasılığın tarihsel örnek sayısı ve kalibrasyon durumu
- Risk/getiri oranı
- Önerilen azami adet ve pozisyon tutarı
- İşlemde riske edilen yaklaşık TL
- Doji türü, bağlamı ve teyit durumu
- VWAP ve fiyatın VWAP’a göre konumu
- Pivot P, R1, R2, S1, S2
- ATR ve kullanılan stop katsayısı
- Hacim oranı
- Kısa gerekçe ve bütün uyarılar
- Sonuç: `AL ADAYI`, `TEYİT BEKLE`, `FİYAT KOVALAMA`, `İŞLEM YOK` veya `VERİ YETERSİZ`

Kullanıcıya tek satırda örneğin `THYAO — 313,00–314,00 TL alış; 318,00 TL hedef; 309,50 TL stop; hedef potansiyeli %1,44; geçmiş benzer durumlarda medyan gün sonu hareketi %0,72; hedefe stop’tan önce ulaşma olasılığı %58 (n=84)` gibi okunabilir bir özet ver. Bu örnekteki değerleri sabit kodlama veya gerçek öneri olarak kullanma.

## 3. Veri katmanı: günlük veri ile intraday veriyi ayır

Mevcut `veri_saglayici.py` günlük Yahoo verisini son resmî Borsa İstanbul kapanışıyla doğruluyor. Bu günlük akışı bozma. Yeni intraday hesaplamalar için sağlayıcı soyutlaması ekle. Örneğin:

- `get_daily_ohlcv(symbol, ...)`
- `get_intraday_ohlcv(symbol, interval, ...)`
- veriyle beraber `source`, `fetched_at`, `last_bar_at`, `exchange_timezone`, `is_delayed`, `delay_minutes`, `is_stale`, `is_complete_bar` metadatası

Ücretsiz/gecikmeli kaynak kullanılıyorsa bunu arayüzde açıkça göster. Kaynak gecikmesini ölçemiyorsan `gecikme bilinmiyor` yaz; `canlı` deme. BIST için saat dilimini `Europe/Istanbul` olarak normalize et. Tamamlanmamış son mumu sinyal, VWAP teyidi veya geçmiş test hesabında kullanma.

Intraday veri yoksa veya hacim değerleri sıfır/geçersizse VWAP, intraday doji ve gün içi olasılık uydurma. Günlük pivot ve günlük ATR hesaplanabiliyorsa bunları `kapanış verisine dayalı plan` olarak göster; sonuç `VERİ YETERSİZ / CANLI TEYİT YOK` olsun. Eski önbellekten işlem adayı üretme.

Sağlayıcı mimarisi ileride lisanslı/gecikmeli BIST veri adaptörü eklenebilecek şekilde protokol/adapter tabanlı olsun. API anahtarı kodda tutulmasın. Ağ hatası, rate limit, boş veri, bozuk OHLC, yinelenen zaman damgası ve saat dilimi sorunları güvenli biçimde ele alınsın.

## 4. Doji mum motoru

Mevcut `formasyon_motoru.py` büyük fiyat formasyonlarını tespit ediyor. Mum formasyonlarını bu dosyaya karmaşık biçimde yığmak yerine, gerekirse `mum_formasyonlari.py` gibi test edilebilir ayrı bir modül oluştur ve mevcut analiz akışına entegre et.

OHLC verilerinde açılış ve kapanışın matematiksel olarak birebir eşit olmasını şart koşma. Aşağıdaki değerleri güvenli biçimde hesapla:

```text
range = high - low
body = abs(close - open)
upper_shadow = high - max(open, close)
lower_shadow = min(open, close) - low
body_ratio = body / range
upper_ratio = upper_shadow / range
lower_ratio = lower_shadow / range
```

Sıfır aralıklı, eksik veya geçersiz mumları ele. Eşikleri tek yerde, isimlendirilmiş ve test edilebilir ayarlar olarak tut. Başlangıç varsayılanları aşağıdaki gibi olabilir; mevcut veri üzerinde makul sonuç üretmiyorsa değişikliği dokümante et:

- Doji adayı: `body_ratio <= 0.10`
- Mezar taşı doji: doji adayı + `upper_ratio >= 0.60` + `lower_ratio <= 0.10`
- Yusufçuk doji: doji adayı + `lower_ratio >= 0.60` + `upper_ratio <= 0.10`
- Uzun bacaklı doji: doji adayı + `upper_ratio >= 0.30` + `lower_ratio >= 0.30`

Öncelik sırasını belirle; aynı mum birden fazla türe yazılmasın. Her sonuçta oranları, kullanılan eşikleri ve neden o sınıfa girdiğini döndür.

Doji tek başına AL/SAT üretmesin. Bağlam ve teyit zorunlu olsun:

- Mezar taşı doji ancak öncesinde ölçülebilir yükseliş eğilimi varsa düşüş riski olarak değerlendirilsin.
- Yusufçuk doji ancak öncesinde ölçülebilir düşüş eğilimi/destek testi varsa yükseliş adayı olsun.
- Uzun bacaklı doji her zaman önce `kararsızlık` olarak işaretlensin.
- Sonraki tamamlanmış mum teyidi olmadan sonuç `TEYİT BEKLE` olsun.
- Yusufçuk için örnek teyit: sonraki tamamlanmış mumun doji tepesinin üzerinde kapanması.
- Mezar taşı için örnek teyit: sonraki tamamlanmış mumun doji dibinin altında kapanması.
- Uzun bacaklı için yön, sonraki mumun doji aralığı dışındaki kapanışıyla belirlensin.
- Hacim, VWAP, pivot/destek-direnci ve genel piyasa rejimi ek teyit olarak kullanılsın; doji puanı toplam kararı tek başına domine etmesin.

Günlük mumdaki doji ile 5/15 dakikalık intraday dojiyi farklı zaman dilimi etiketiyle göster. Günlük doji, aynı gün aç-kapa işlemi için tek başına yeterli sayılmasın.

## 5. Pivot, VWAP ve ATR hesapları

### Klasik pivot seviyeleri

Yalnızca önceki tamamlanmış işlem gününün High, Low ve Close değerlerini kullan:

```text
P  = (High + Low + Close) / 3
R1 = (2 * P) - Low
S1 = (2 * P) - High
R2 = P + (High - Low)
S2 = P - (High - Low)
```

Geleceğe bakış sızıntısı olmamalı. Resmî günlük OHLC ile geçici kaynak çelişiyorsa mevcut veri kalite yaklaşımını kullan ve kaynak bilgisini taşı.

### VWAP

VWAP’ı yalnızca o işlem seansındaki tamamlanmış intraday barlardan hesapla:

```text
typical_price = (High + Low + Close) / 3
VWAP = cumulative_sum(typical_price * Volume) / cumulative_sum(Volume)
```

Her yeni işlem gününde kümülatif hesabı sıfırla. Farklı günleri veya günlük barları tek VWAP serisine karıştırma. Hacim yoksa VWAP üretme. `Fiyat > VWAP` yalnızca alıcı tarafı lehine bir teyit olsun; tek başına AL sinyali olmasın.

### ATR ve stop

Wilder ATR(14) hesaplamasını kullan veya mevcut doğru uygulamayla uyumlu hale getir. ATR yön tahmini değildir; oynaklık ölçüsüdür. Stop adaylarını şu kaynaklardan üret:

- Yapısal destek/pivot altı
- Sinyal/doji mumunun geçersizleşme seviyesi
- `entry - ATR * katsayı` (varsayılan 1,5; ayarlanabilir 1,0–2,0)

Seçilen stop mantığını ve katsayıyı sonuçta yaz. Stop mesafesi sıfır/negatifse, fiyat limitlerine veya normal gürültüye anlamsız derecede yakınsa işlem üretme. Hedef için yakın pivot direnç, teknik direnç, ATR projeksiyonu ve minimum risk/getiriyi birlikte değerlendir. Fiyat hedefin üstündeyse veya giriş bandını anlamlı ölçüde aşmışsa `FİYAT KOVALAMA` üret.

## 6. Yükseliş yüzdesi ve olasılık: üç ayrı kavram

Kullanıcının istediği “ne kadar yükselebilir?” bilgisini tek bir yanıltıcı sayı olarak sunma. Aşağıdaki alanları ayrı hesapla:

1. `hedef_potansiyeli_yuzde = ((hedef_fiyat / referans_giris) - 1) * 100`
2. `beklenen_gun_sonu_hareketi_yuzde`: aynı kurallarla geçmişte oluşmuş, yalnızca o tarihte bilinen verilerden üretilmiş benzer sinyallerin işlem maliyeti sonrası gün sonu getirilerinin küçültülmüş/sağlam merkezi tahmini
3. `hedef_once_olasiligi_yuzde`: hedefe stop’tan önce ulaşan geçmiş out-of-sample işlemlerin kalibre edilmiş olasılığı

`hedef_potansiyeli_yuzde` matematiksel hedef mesafesidir; model olasılığı değildir. `beklenen_gun_sonu_hareketi_yuzde` için tercihen medyan veya uç değerlerden etkilenmeyen sağlam bir tahmin kullan. Tahminin yanında P10–P90 gibi ampirik aralık ver.

Olasılık modelini şu kurallarla geliştir:

- Özellikler yalnızca sinyal anında mevcut veriden oluşsun: doji türü/bağlam/teyit, VWAP mesafesi, pivot konumu, ATR%, hacim oranı, RSI, MACD, ADX, kısa momentum, piyasa rejimi ve saat dilimi.
- Gelecek getirileri özelliklere sızdırma.
- Rastgele train/test bölmesi yerine zaman sıralı walk-forward değerlendirme kullan.
- Aynı hisse ve aynı dönemin tekrarları yüzünden sahte güven oluşmasını önle.
- Az örnekte tahmini sıfıra/genel ortalamaya doğru küçült; `n < 30` ise yüzde olasılık yerine `Yetersiz örnek` göster. Daha yüksek güven için daha yüksek asgari örnek eşiği kullanabilirsin.
- Olasılığı 25–88 gibi keyfî sabit bir aralığa sıkıştırma. Kalibrasyon yöntemi ve taban oranı açık olsun.
- Olasılığın kalibrasyonunu Brier skoru ve güvenilirlik dilimleriyle ölç.
- Tahmin aralığının kapsama oranını raporla.
- Hem hedef hem stop aynı bar içinde görülür ve daha küçük zaman dilimi verisi yoksa iyimser varsayım yapma; stop önce olmuş kabul et veya sonucu `sırası belirsiz` olarak dışarıda raporla. Tercihi test ve dokümantasyonla sabitle.
- Komisyon, BSMV/vergisel maliyet uygulanıyorsa mevcut mevzuat/ayar yapısına göre yapılandırılabilir tut; en azından komisyon ve kayma varsayımını parametreleştir ve net getiride göster.

Intraday geçmiş yetersizse günlük veriden “intraday hedefe ulaşma olasılığı” türetme. Bunun yerine alanı bilinmiyor olarak göster. Günlük OHLC ile ayrı bir sonraki-gün/aynı-gün yüksek-düşük araştırması yapılabilir ama bu, gerçek intraday yürüyüş sırasını kanıtlamaz.

## 7. Sinyal ve risk kapıları

Yeni motoru mevcut karar motoruna paralel, açık bir günlük işlem motoru olarak oluştur; mevcut orta/uzun vade kararlarının anlamını bozma. Önerilen modüller:

- `mum_formasyonlari.py`
- `intraday_gostergeler.py`
- `gunluk_trade_motoru.py`
- gerekiyorsa `intraday_backtest.py`

Bir `AL ADAYI` için en az şu zorunlu kapıları uygula:

- Güncel ve yeterli intraday veri
- Tamamlanmış mum
- Yeterli likidite ve geçerli hacim
- Alış bandında fiyat; fiyat kovalamama
- Stop ve hedefin mantıksal sıralaması
- Kullanıcının minimum risk/getiri eşiği
- Yeterli tarihsel out-of-sample örnek veya açıkça `deneysel` durum
- Olumsuz veri kalitesi/KAP/piyasa rejimi varsa uygun engel veya güçlü uyarı

Doji ek kuralları:

- Teyitli yusufçuk doji long aday puanını destekleyebilir.
- Mezar taşı doji, long işlemde risk/kaçınma veya pozisyon azaltma uyarısı üretir; BIST’te açığa satış yetkisi ve mevzuat koşullarını varsayarak otomatik short önerme.
- Uzun bacaklı doji teyit gelene kadar işlem engeli oluşturur.

Örnek sinyal birleşimi: fiyat VWAP üstünde, R1 altında hâlâ makul alan var, hacim teyitli, piyasa rejimi olumsuz değil, risk/getiri yeterli ve doji/diğer momentum teyidi mevcut. Bu yalnızca başlangıç yaklaşımıdır; ağırlıkları geçmiş veride walk-forward test et. En iyi geçmiş sonucu bulmak için sınırsız eşik taraması yapıp aşırı uyum üretme.

## 8. Pozisyon büyüklüğü

Kullanıcının hesap büyüklüğü ve işlem başına risk yüzdesine göre:

```text
risk_tutari = hesap_buyuklugu * risk_yuzdesi
hisse_basi_risk = giris_fiyati - stop_fiyati
adet_risk_limiti = floor(risk_tutari / hisse_basi_risk)
```

Komisyon/kaymayı hesaba kat. Pozisyonu ayrıca kullanılabilir nakit, kullanıcı tarafından ayarlanabilen azami portföy yüzdesi ve likidite sınırıyla sınırla. Son adet bu sınırların minimumu olsun. Kesirli BIST hissesi önerme. Hesap büyüklüğü girilmediyse adet uydurma; yalnızca hisse başı risk ve yüzde risk göster.

## 9. Backtest, kayıt ve dürüst performans raporu

Yeni günlük işlem stratejisi için ayrı, tekrar üretilebilir walk-forward backtest ekle. En az şu ölçümleri raporla:

- Toplam sinyal ve işlem sayısı
- Hedef, stop, gün sonu ve belirsiz sonuç sayısı
- Net kazanma oranı
- Ortalama ve medyan net getiri
- Beklenen değer (expectancy)
- Profit factor
- Maksimum düşüş
- Ortalama risk/getiri
- İşlem maliyeti ve kayma varsayımı
- Hedefe stop’tan önce ulaşma oranı
- Olasılık Brier skoru ve kalibrasyon özeti
- Tahmin aralığı kapsama oranı
- Hisse ve dönem bazında sonuçlar; yalnızca toplu ortalama değil

Sonuçları uygulamada “geçmiş performans, gelecek sonucu garanti etmez” uyarısıyla göster. Kâğıt işlem kayıtlarında sinyal zamanı, o anda görülen veri, giriş, hedef, stop, tahminler ve daha sonra gerçekleşen sonuç değiştirilemez/audit edilebilir biçimde saklansın. Sonradan gelen veriler eski tahmin satırını geriye dönük değiştirmesin.

## 10. Testler

En az aşağıdaki otomatik testleri ekle:

- Mezar taşı, yusufçuk, uzun bacaklı ve doji olmayan mumlar için sentetik OHLC testleri
- Sıfır aralık, NaN, negatif/geçersiz OHLC ve eşik sınırları
- Aynı mumun yalnızca bir doji sınıfına girmesi
- Trend bağlamı olmadan doji yön sinyali üretilmemesi
- Sonraki tamamlanmış mum teyidi ve tamamlanmamış mumun dışlanması
- Pivot formüllerinin bilinen örnekle doğrulanması ve yalnızca önceki günün kullanılması
- VWAP’ın bilinen örnekle doğrulanması, gün değişiminde sıfırlanması ve hacimsiz veride üretilmemesi
- ATR ve stop hesabı
- Hedef potansiyeli yüzdesi ile fiyatların matematiksel tutarlılığı
- Düşük örnekte olasılık gösterilmemesi
- Walk-forward akışta ileriye bakış sızıntısı olmaması
- Aynı barda hedef+stop belirsizliğinin kötümser/kararlaştırılmış şekilde ele alınması
- Komisyon ve kaymanın net getiriye eklenmesi
- Pozisyon büyüklüğü ve tüm üst sınırlar
- Eski/gecikmeli veride `AL ADAYI` üretilmemesi
- Uygun aday yokken listenin boş kalması
- Mevcut `gunluk_islem_plani.py`, karar motoru ve arayüz davranışlarının geriye dönük bozulmaması
- Yeni sayfa için en az bir PySide6 smoke testi; indeks ve menü yönlendirmesi

Mevcut test paketinin tamamını çalıştır. Ağ gerektiren testleri deterministik fixture/mock ile ayır; testler internetin o anki durumuna bağlı olmasın.

## 11. Arayüz, dokümantasyon ve sürüm

- Mevcut siyah/kırmızı arayüz stiline uy.
- Tablo kolonları okunabilir, sıralanabilir ve detay penceresi erişilebilir olsun.
- Renk tek başına anlam taşımasın; metin etiketi de kullan.
- Veri zamanı, kaynak ve gecikme ekranda görünür olsun.
- İstatistiksel alanlar için kısa araç ipuçları ekle: `hedef potansiyeli`, `beklenen hareket`, `olasılık` ve `model güveni` aynı şey değildir.
- `README.md`, metodoloji belgesi, kullanım rehberi ve gerekiyorsa sürüm/paketleme dosyalarını güncelle.
- Yeni bağımlılık eklemeden önce mevcut `pandas/numpy` ile yapılabilirliğini değerlendir. Yeni bağımlılık gerekiyorsa sabitle, gerekçelendir ve PyInstaller paketine dâhil edildiğini doğrula.
- Sürüm artırma geleneğini mevcut depo geçmişinden belirle; bütün sürüm referanslarını tutarlı güncelle.

Masaüstü sürüm ana teslimattır. `mobile_app.py`, `worker.js` ve PWA ayrı bir hesap motoru kullanıyorsa, Python mantığını JavaScript’e kopyalayıp iki farklı doğruluk kaynağı oluşturma. Önce ortak API/şema veya sürdürülebilir paylaşım yolunu değerlendir. Güvenli ve test edilebilir değilse mobilde yalnızca desteklenen alanları göster ve bu sınırlamayı raporla.

## 12. Tamamlanma ölçütleri

Görev ancak aşağıdakilerin tamamı sağlanınca bitmiş sayılır:

1. `GÜNLÜK TRADE` sayfası açılıyor ve ana uygulamanın diğer sayfalarını bozmuyor.
2. Doji türleri ölçülebilir oranlarla doğru sınıflandırılıyor; bağlam ve teyit olmadan işlem üretmiyor.
3. Pivot, VWAP ve ATR hesapları testlerle doğrulanıyor.
4. Hedef potansiyeli, beklenen gün sonu hareketi ve hedefe ulaşma olasılığı ayrı alanlar olarak gösteriliyor.
5. Olasılık ve beklenen hareket geçmiş out-of-sample kanıt yoksa uydurulmuyor.
6. Veri eski/gecikmeli/eksik olduğunda sistem güvenli şekilde işlem üretmiyor.
7. Pozisyon büyüklüğü hesap riski ve stop mesafesine göre hesaplanıyor.
8. Backtest maliyet, kayma, ileriye bakış ve aynı-bar belirsizliğini doğru ele alıyor.
9. Yeni ve mevcut testlerin tamamı geçiyor.
10. Dokümantasyon ve sürüm bilgisi güncel.

## 13. Çalışma sonunda verilecek rapor

Son mesajında şunları yaz:

- Uygulanan mimari ve kullanıcı açısından görünen yenilikler
- Değiştirilen/eklenen dosyalar
- Kullanılan veri kaynağı ve gerçek gecikme sınırlaması
- Tahmin yüzdesi ile olasılığın tam olarak nasıl hesaplandığı
- Walk-forward test dönemi, örnek sayısı ve ana performans ölçümleri
- Çalıştırılan test/lint/build komutları ve sonuçları
- Yapılamayan veya güvenilir veri gerektiren maddeler
- Hiçbir sonucun kâr garantisi olmadığını açıkça belirten kısa not

## İncelenecek kaynaklar

- Mevcut depo: https://github.com/vlkncm/Borsa-Analiz
- Doji açıklamasının geldiği paylaşım: https://x.com/HisseKralicesi/status/2092179236010504294
- Day trading genel çerçevesi ve riskler: https://www.investopedia.com/articles/trading/05/011705.asp
- Intraday formül/strateji sayfası: https://www.tradebulls.in/basics-intraday-trading/intraday-trading-strategies-formula
- TradingView day-trading açık kaynak göstergeleri: https://tr.tradingview.com/scripts/daytrading/
- Kotak Neo intraday formülleri: https://www.kotakneo.com/investing-guide/intraday-trading/intraday-trading-formula/
- Kotak Neo pivot açıklaması: https://www.kotakneo.com/investing-guide/intraday-trading/how-to-use-pivot-point-in-intraday-trading/
- ATR tanımı: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
- ATR’nin stop/limit planlamasındaki kullanımı: https://www.schwab.com/learn/story/average-true-range-indicator-and-volatility

Kaynaklardaki pazarlama iddialarını veya yayıncıların belirttiği başarı oranlarını doğrudan model sabiti yapma. Formülleri test et, veri ve piyasa yapısına uygunluğunu doğrula; TradingView topluluk betiklerini fikir kaynağı olarak kullan, kopyalanacak kanıtlanmış strateji olarak kabul etme.
