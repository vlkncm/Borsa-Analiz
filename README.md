# Borsa Analiz Pro MAX v9.2.0

## v9.2.0 mum formasyonları ve en iyi 5 Günlük Trade

- Hammer, Hanging Man, Bullish Engulfing, Bearish Engulfing, Morning Star ve Cornering formasyonları ölçülebilir gövde/fitil, trend ve hacim kurallarıyla eklendi; mevcut Gravestone Doji korunur.
- Aynı mum geometrisinin düşüş sonunda Hammer, yükseliş sonunda Hanging Man sayılması için trend bağlamı zorunludur.
- Mum formasyonu tek başına AL üretmez; AlphaTrend, EMA20, BBW ve MACD-V birleşik skoruna en fazla 15 puan katkı verir. Düşüş formasyonu 25 puan risk cezası uygular.
- Günlük Trade sayfası bütün hisseleri göstermez. Yalnız `GÜVENİLİR` veri durumundaki, pozitif gün içi hedefi bulunan sonuçlar `Günlük Trade Skoru`, ardından yükseliş yüzdesiyle sıralanır ve en güçlü 5 aday gösterilir.
- Uygun veri yoksa listeyi zayıf veya eski hisselerle zorla doldurmaz.

## v9.1.0 dört teyitli sade Günlük Trade

- Günlük Trade yeniden ayrı fakat sade bir tablo olarak eklendi; ayrı ağ taraması yapmaz, profesyonel taramanın aynı doğrulanmış raporunu kullanır.
- Tweet yaklaşımı ölçülebilir dört filtreye çevrildi: RSI tabanlı AlphaTrend yönü, yükselen EMA20, BBW yatay/sıkışık piyasa filtresi ve ATR'ye normalize MACD-V momentumu.
- MACD-V formülü `100 × (EMA12 − EMA26) / ATR26`; sinyal çizgisi MACD-V'nin EMA9'udur. Pozitif teyit için MACD-V hem sıfırın hem sinyal çizgisinin üzerinde olmalıdır.
- BBW formülü `100 × (üst Bollinger − alt Bollinger) / SMA20`; son değer 120 barlık geçmişin alt çeyreğindeyse yatay/sıkışık kabul edilir ve tam teyit verilmez.
- Yükseliş alanı `(gün içi hedef / açılış − 1) × 100` olarak korunur. Tek göstergeden AL üretilmez; dört filtrenin tamamı geçerse `4/4 TEYİTLİ` yazılır.
- Faaliyet raporu sayfası sol menüden ve masaüstü sayfa akışından kaldırıldı; KAP sayfası korunur.

Kaynak yaklaşımı: [Kıvanç Özbilgiç MACD-V](https://www.tradingview.com/script/mionn7XC-MACD-V-Volatility-Normalized-MACD/). Gösterge fikri yeniden uygulanmış, Pine Script kaynak kodu kopyalanmamıştır.

## v9.0.0 Sade gün içi yükseliş göstergesi

- Eski `BIST 30 Alış–Satış Fırsatları` görünümü korunur; ayrı ve karmaşık bir trade sayfası gösterilmez.
- Tabloya açılış fiyatı, ATR ile sınırlı gün içi hedef ve `(gün içi hedef / açılış fiyatı - 1) × 100` formülüyle `Gün İçi Yükseliş %` eklenir.
- Ücretsiz Yahoo intraday verisinin gecikmesi garanti edilmez ve ekranda açıkça gösterilir. Eski, hacimsiz veya eksik veri `AL ADAYI` üretemez.
- Doji türü, trend bağlamı ve sonraki tamamlanmış mum teyidi; seans VWAP'ı, önceki gün pivotları ve Wilder ATR(14) ayrı test edilebilir motorlarda hesaplanır.
- Hedef potansiyeli matematiksel fiyat mesafesidir. Beklenen gün sonu hareketi ve hedefe stop'tan önce ulaşma olasılığı yalnızca en az 30 geçmiş out-of-sample örnek varsa gösterilir; aksi halde `Yetersiz örnek` yazılır.
- Hesap riski varsayılan `%0,5`, kullanıcı üst sınırı `%1`; pozisyon adedi risk tutarı, nakit/portföy ve likidite sınırlarının en küçüğüdür.
- Kâğıt işlemler tahmin anındaki alanlarla hash zincirli JSONL günlüğüne eklenir; uygulama gerçek aracı kurum emri göndermez.
- Aynı barda hedef ve stop görülürse backtest kötümser biçimde stopu önce kabul eder; komisyon ve kayma net getiriden düşülür.

### Günlük Trade metodolojisi ve sınırlamalar

Klasik pivotlar yalnızca önceki tamamlanmış günlük `High/Low/Close` değerlerinden hesaplanır. VWAP her İstanbul seansında sıfırlanır ve yalnızca pozitif hacimli tamamlanmış intraday barları kullanır. Stop; yapı/doji geçersizliği, pivot desteği ve varsayılan `1,5 × ATR` adaylarının korumacı birleşimidir. Hedef, kullanıcının minimum risk/getiri oranını ve yakın pivot/ATR alanını gözetir.

Olasılık kanıtı Beta taban oranına küçültülmüş ampirik geçmiş hedef-önce oranıdır; sabit bir yüzde aralığına sıkıştırılmaz. Walk-forward değerlendirmede her tahmin yalnızca kendisinden önceki işlemleri görür. Brier skoru ancak geçmiş tahmin ve sonuç çifti varsa raporlanabilir. Bu sürüm beraberinde lisanslı gerçek zamanlı BIST verisi veya hazır tarihsel intraday veri seti getirmediğinden, yeterli out-of-sample kayıt oluşana kadar olasılık ve tahmin aralığı bilinmiyor gösterilebilir; bu güvenlik davranışıdır.

Testler çevrimdışı ve deterministik fixture'larla çalıştırılır:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

## v8.8.0 RSI–SuperTrend deneysel dip teyidi

- RSI ortalamasındaki ikinci toparlanmayı dip adayı olarak izler.
- SuperTrend yukarı yönlü olduğunda sinyali teyitli olarak işaretler.
- Ana AL/SAT puanını otomatik değiştirmez; bağımsız kanıt alanı olarak gösterilir.
- Sosyal medyadaki `%80 başarı` iddiasını garanti olarak kullanmaz.
- Tarama sonucuna RSI-ST durumu, trend yönü ve son sinyal yaşı eklenir.

## v8.7.8 kararlılık ve paket güncellemesi

- Grafik görüntüleme Windows/Qt ortamlarında daha güvenli olacak şekilde güncellendi.
- Analiz ve satış işlemlerindeki hata yakalama, sayı biçimlendirme ve tekrar tıklama korumaları iyileştirildi.
- EXE paketindeki sürüm kaynak koduyla eşitlendi.

## v8.7.3 bağımsız tarama motoru

- Profesyonel tarama, GUI uygulamasının ikinci kopyası yerine ayrı `BorsaTaramaMotoru.exe` ile çalışır.
- Konsol tabanlı motorun çıktısı canlı log ekranına satır satır aktarılır.
- Tarama motoru ile arayüz tamamen ayrıldığı için düğmenin sessiz kalması ve GUI'nin taramayla birlikte kapanması önlenir.

## v8.7.2 temiz ve canlı tarama günlüğü

- Pandas'ın taramayı durdurmayan tekrar eden `FutureWarning` satırları kullanıcı günlüğünden kaldırıldı.
- Alt süreç çıktısı tamponsuz çalıştırılarak hisse ve tarama ilerlemesi ekranda anlık gösterilir.

## v8.7.1 tarama kapanma koruması

- Ağır profesyonel tarama ana arayüzden ayrı bir alt süreçte çalıştırılır.
- Veri/Python motorunda yerel çökme olsa bile ana pencere açık kalır ve hata canlı logda gösterilir.
- Alt süreç raporu oluşturabildiyse normal kapanmasa dahi son rapor güvenli biçimde yüklenir.
- Yerel çökme ayrıntıları tanı için `tarama_cokme.log` dosyasına kaydedilir.

## v8.7.0 en iyi 3 hisse ve fon karar listesi

- Hisse taraması, ortak teyit eşiklerini geçen en güçlü 3 adayı alış bandı, hedef, stop ve risk/getiri oranıyla gösterir.
- Fon taraması, 2–3 aylık ufuk için en fazla 3 risk-ayarlı adayı seçer; zayıf koşullarda listeyi zorla doldurmaz.
- Her fon için güncel pay fiyatı, 2 ve 3 aylık koşullu hedef, risk eşiği, kademeli alım ve ölçülebilir çıkış koşulu üretilir.
- TEFAS profilinden kurucu/yönetici kurum gösterilir; fonun TEFAS'ta bulunmasının tek bir bankadan alınacağı anlamına gelmediği açıklanır.

## v8.6.0 tek fon seçimi ve alım planı

- Fon taraması uygun koşulları geçenler arasından yalnızca bir risk-ayarlı model adayı seçer.
- Kullanıcının yazdığı sermaye `%40 + %30 + %30` şeklinde koşullu kademelere ayrılır.
- Güncel TEFAS pay fiyatı, üç aylık olumsuz/temel/iyimser fiyat senaryosu ve yaklaşık parasal risk gösterilir.
- Fonun önerilen asgari tutma süresi, alış/satış valörü ve ölçülebilir azaltma koşulu aynı kartta bulunur.
- Ortak teyit yoksa sistem fon seçmez ve `zorla alım önerilmedi` sonucunu verir.

## v8.5.0 Fon Karar Merkezi

- Resmî TEFAS sayfasındaki halka açık fon listesi ve dönemsel getiriler taranır.
- Yalnızca TEFAS'ta işlem gören, risk değeri ve yeterli 1/3/6 aylık geçmişi bulunan fonlar değerlendirilir.
- Fonlar kendi kategorilerindeki getiri, çok dönemli momentum, hızlanma ve risk değerine göre sıralanır.
- `%20+ Uç Senaryo` alanı garanti değil, yüksek riskli bir momentum işaretidir.
- Aşırı hızlanan fonlarda `Yükselişi Kovalama` uyarısı, diğerlerinde kademeli al/izle/bekle/alma kararları gösterilir.
- Önerilen asgari süre ve ölçülebilir çıkış koşulu her satırda bulunur.

## v8.4.0 karar odaklı arayüz

- Kısa/orta/uzun vade sekmeleri yerine `Bugün Alınabilir`, `Alım İçin Bekle` ve `Riskli / Uzak Dur` grupları kullanılır.
- Tek hisse teknik analizi ile doğrulanmış şirket araştırması aynı `Hisse Karar Merkezi` ekranında birleştirilmiştir.
- Alış bandı, hedef, stop, tahmini süre, teknik gerekçeler ve temel görünüm aynı incelemede gösterilir.
- Maliyet girilerek kullanılan ayrı satış kararı ekranı korunmuştur.

## v8.3.0 doğrulanmış şirket araştırması

- Seçilen hisse için finansal tablo eğilimleri, değerleme ve kalite oranları tek raporda gösterilir.
- Güçlü yönler, riskler ve boğa/temel/ayı senaryoları doğrulanabilen verilerden üretilir.
- Eksik finansal alanlar tahmin edilmez; `Veri yok` olarak işaretlenir.
- Araştırma raporu mevcut teknik al-sat kararını veya puanını değiştirmez.
- KAP ve faaliyet raporu ekranları kaynak doğrulaması için ayrı tutulur.

## iPhone PWA sürümü

Grafiksiz, iPhone ana ekranına eklenebilen mobil sürüm:

- [Borsa Analiz PWA'yı aç](https://borsa-analiz-pwa.volkan-borsa-analiz.workers.dev)
- Tek hisse teknik analizi
- 50 TL altı likit hisseler için fırsat taraması
- Yerel takip listesi
- Manuel adet ve alış fiyatıyla portföy kâr/zarar takibi
- Cloudflare Workers üzerinde telefondan bağımsız çalışma

Kaynaklar `ios_pwa/`, `worker.js` ve `wrangler.jsonc` dosyalarındadır. Yayımlama adımları `PWA_YAYINLAMA.md` belgesinde açıklanmıştır.

Sadeleştirilmiş BIST 30 yatırım karar motoru.

## BIST 30 odaklı analiz

- Tarama ve tek hisse analizi yalnızca BIST 30 bileşenlerinde çalışır.
- Güncel kod listesi tek bir denetlenebilir modülde tutulur.
- Mevcut liste 01.07.2026-30.09.2026 endeks dönemine aittir.
- Göreceli güç karşılaştırması BIST 100 yerine BIST 30 endeksiyle yapılır.
- Eski 613 hisselik dosyalar arşiv olarak kalır, analiz evrenine alınmaz.

## v7.5.0 resmî Borsa İstanbul kapanış entegrasyonu

- Yahoo Finance tarihsel serisi, Borsa İstanbul Pay Piyasası günlük bülteniyle doğrulanır.
- Son resmî OHLCV satırı eksikse seriye eklenir; farklıysa resmî bülten değeri kullanılır.
- Bülten çevrimdışı kullanım için yerel olarak önbelleğe alınır.
- MEGMT için 31 Temmuz 2026 resmî kapanışı 68,15 TL olarak doğrulanır.
- Veri kaynağı analiz ve raporlarda `Yahoo tarihsel + Borsa İstanbul resmî kapanış` olarak gösterilir.

## v7.4.2 grafik boyutu düzeltmesi

- Sonuç grafiğinin her yeniden çizimde büyümesine yol açan yerleşim geri besleme döngüsü kaldırıldı.
- Grafik alanı 460 piksel sabit yükseklikte tutulur ve sayfadaki yazılı analizi kapatmaz.
- Grafik görüntüsü kendi alanının kullanılabilir iç ölçülerine göre ölçeklenir.
- Tekrarlanan yeniden boyutlandırmaları denetleyen otomatik arayüz testi eklendi.

## v7.4.1 donma ve tepki süresi düzeltmesi

- Tek hisse analizi sırasında gereksiz döviz, altın ve petrol sorguları kaldırıldı.
- Analizin hangi aşamada olduğu ekranda canlı olarak gösterilir.
- Büyük sonuç grafiği yalnızca pencere boyutu sabitlendikten sonra yeniden ölçeklenir.
- Büyük Excel rapor tablolarının açılış ve sütun boyutlandırma maliyeti azaltıldı.
- Etkileşimli veri isteğinin uzun ağ tekrarları sınırlandı.

## v7.4 birleşik tek hisse analizi

- Tek Hisse Analizi ve Sonuç Grafiği aynı ekranda birleştirildi.
- Günlük ve haftalık yön, BIST piyasa rejimi, veri güveni ve tarihsel kanıt birlikte değerlendirilir.
- Karar, alış bandı, hedef ve stop grafikte gösterilir.
- Grafiğin altında trend, momentum, hacim, çoklu zaman dilimi ve riskler yazılı olarak açıklanır.
- Eski veya güvenilmez veriyle işlem kararı üretilmez.

## Windows kurulumu

- [Borsa Analiz Pro MAX v8.8.0 kurulum dosyasını indir](downloads/v8.8.0/Setup_Borsa_Analiz_Pro_MAX_v8.8.0.exe)
- SHA-256: `2E036351D6900B15EA787F3C7B399795DF01CD3B2C34B9B21327AEE0AF649731`

## v7.2 merkezi veri katmanı

- Fiyat verileri tek bir sağlayıcı katmanından alınır.
- Ham OHLCV verileri yerel SQLite önbelleğinde saklanır.
- Ağ kesintisinde son sağlam veri kullanılır; eski veri kalite filtresinden geçemez.
- Lisanslı BIST API'si geldiğinde analiz motorları değiştirilmeden yeni adaptör eklenebilir.
- Yahoo Finance geçici/yedek veri kaynağıdır.

## Ana kullanım

- Kısa vade: 5–20 iş günü için en güçlü 5 hisse
- Orta vade: 1–3 ay için en güçlü 5 hisse
- Uzun vade: 3–12 ay için en güçlü 5 hisse
- Grafik ve gerekçeli yazılı yorum içeren birleşik tek hisse analizi
- Satış kararı
- Takip listesi
- Seçili hisse için KAP ve faaliyet raporu analizi

Teknik göstergeler arka planda çalışır. Kullanıcıya alış aralığı, hedef, stop,
tahmini getiri, süre, model olasılığı ve kısa karar gösterilir.

> Bu yazılım yatırım tavsiyesi değildir. Model sonuçları kesinlik veya getiri garantisi içermez.

## Profesyonel sinyal güvenliği

- Tek tuşla BIST taraması ve kısa, orta, uzun vade listeleri
- Güncel olmayan veriyi otomatik eleme
- Tutarlı alış, stop, hedef ve minimum risk/getiri kontrolü
- Alım bölgesinde / geri çekilme bekle / teyit bekle işlem durumu
- Kısa, orta ve uzun vade için ayrı puanlama
- İki yıllık teknik geçmiş ve uzun vadede 252 günlük momentum
- Sonraki gün giriş, komisyon, kayma ve bileşik getiri içeren backtest

Sistem uygun kalite eşiğini geçen hisse bulamazsa listeyi boş bırakır. Bu davranış,
zayıf piyasa koşullarında zorla alım önerisi üretilmesini önler.

## v7.0 kanıt tabanlı analiz

- Bollinger Z, Stochastic RSI, ROC, OBV, CMF, MFI, Sharpe ve Sortino ölçümleri
- Kısa, orta ve uzun vade için benzer geçmiş piyasa rejimi analizi
- Az örnekte başarı oranını aşağı çeken Wilson güven alt sınırı
- Profesyonel kanıt puanı ve vade bazlı minimum kanıt filtresi
- Yeterli benzer tarihsel örnek yoksa otomatik `İZLE - KANIT YETERSİZ` kararı
- CCI, Supertrend ve Ichimoku trend teyitleri
- BIST 100'e karşı 1 ay, 3 ay ve 1 yıllık göreceli güç ile beta
- Normal dağılım dayatmayan 5.000 yollu tarihsel bootstrap Monte Carlo risk bantları
- 1 aylık VaR95 ve kuyruk kaybını gösteren CVaR95

Hiçbir model veya hisse için yüzde 100 kazanç garantisi verilemez. Uygulamadaki alış,
satış, stop, süre ve olasılık alanları ölçülebilir senaryolardır; emir veya garanti değildir.
