# Borsa Analiz Pro MAX v10.3.1

## Sade Yatırımcı Modu

- Ana analiz tabloları yalnız `Hisse, Karar, Beklenen süre, Güven düzeyi, Güncel fiyat, Alım bölgesi, Hedef, Stop` gösterir.
- Her sayfada eşikleri düşürmeden en fazla beş sonuç bulunur; uygun aday yoksa liste boş kalır.
- Teknik göstergeler ve sistem kayıtları silinmez; **Teknik Ayrıntıları Göster** ve **Sistem Denetimi** altında açılır.
- Portföy hisseleri gerçek alış fiyatı ve tarihine göre `BEKLE`, `KÂR AL` veya `SAT` olarak yeniden değerlendirilir.
- Yeterli örnek dışı geçmiş yoksa sahte başarı yüzdesi yerine `Güven düzeyi: Ölçülemedi` yazılır.

## Ortak yüksek hareket karar sistemi

- T+1/T+2 sonuçları artık worker, dashboard, detay ekranı ve SQLite snapshot'ta aynı `CandidateDecision` kararını kullanır.
- T+1/T+2 ilk 50 Geniş Radar ile güvenlik koşullarını geçen Seçkin Adaylar ayrı gösterilir.
- Her satır “neden aday”, “neden AL değil”, eksik veri, eleme kapısı, giriş, hedef, stop, risk/getiri ve veri zamanını taşır.
- Yeni halka arzlar kalibre yüzde uydurulmadan ayrı radarda; menkul türü belirsiz yüksek sıralı hisseler uyarıyla geniş radarda kalır.
- Günlük değiştirilemez Kaçırılan Hareketler raporu eski snapshot ile ayrı gerçekleşme kaydını karşılaştırır.
- 28 Ağustos incelemesi `KACIRILAN_HAREKETLER_2026-08-28.md` dosyasındadır.

## Uygulama içi kullanım ve yatırım kontrol rehberi

- Sol menüye **Nasıl Kullanılır?** ekranı eklendi.
- Veri güncelliği, karar ifadeleri, alış bandı, hedef, stop ve risk/getiri birlikte açıklanır.
- Pozisyon büyüklüğü için risk tutarı ve azami adet hesabı örnekle gösterilir.
- İşlem öncesi kontrol listesi ve işlem açılmaması gereken durumlar görünür hâle getirildi.
- Ayrıntılı metin `KULLANIM_VE_YATIRIM_REHBERI.md` dosyasındadır.

## v10.3.0 yüksek hareket radarı ve toplu tarama düzeltmesi

- T+1 ve T+2 güçlü hareket tahminleri sembol, tarih, vade, model ve veri sürümüne göre birbirinden ayrıldı.
- Hisseye özel özellik hashleri, kesitsel BIST sıralaması, kalibrasyon güvenliği ve değiştirilemez SQLite tahmin snapshot'ları eklendi.
- Yeni halka arzlar kısa veri geçmişi nedeniyle sessizce elenmeden ayrı analiz yolunda değerlendirilir.
- T+1/T+2 performans ekranı gerçekleşen sonuçları ve sıralama metriklerini SQLite üzerinden gösterir.
- Paketlenmiş uygulamada toplu taramanın eksik `BorsaTaramaMotoru.exe` nedeniyle başlamaması düzeltildi; ana EXE güvenli headless alt süreç başlatır.
- Model veya kalibrasyon bulunmadığında sahte olasılık ve kesin karar gösterilmez.

## v10.2.2 dashboard ve kayıt güvenilirliği güncellemesi

- Ortak koyu lacivert finans dashboardu ve yeniden kullanılabilir sayfa bileşenleri eklendi.
- Ertesi Gün Tavan ve 50 TL Altı taramaları 613 aktif BIST hissesini paketli yedek evrenden de okuyabilir.
- Sütunsuz sonuçların SQLite `CREATE TABLE ()` hatası üretmesi engellendi; önceki geçerli kayıt korunur.
- CSV yedekleme ile SQLite kayıt sonuçları birbirinden bağımsız ve açık biçimde raporlanır.
- Windows kurulum paketi başka bilgisayarlara doğrudan kurulabilecek biçimde GitHub sürümüne eklenir.

## v10.2.0 son büyük stabilizasyon

- Teknik göstergeler `teknik_gostergeler/` altında tek matematiksel kaynağa bağlandı.
- Canlı tarama, Günlük Trade, grafik ve backtest ortak RSI/MACD/ATR/ADX hesaplarını kullanır.
- Veri metadata sözleşmesi ve strateji eklenti altyapısı sürümlendirildi.
- Ayrıntılı kapsam için `ANALIZ_ENVANTERI.md` ve `CHANGELOG.md` dosyalarına bakın.
- Formül geçişi ve test baseline'ı `BASELINE_KARSILASTIRMA.md` dosyasındadır.

Zorunlu karar kapıları veri kalitesi, en az 30 zaman sıralı OOS örnek, uygun piyasa rejimi, likidite/maliyet, pozitif net beklenti, risk/getiri, BIST+sektör göreceli gücü ve aynı-saat RVOL/VWAP teyididir. Hiçbiri listeyi beş adaya tamamlamak için gevşetilmez.

İsteğe bağlı analizlerin tek ayar kaynağı `uygulama_ayarlari.py` dosyasıdır: KAP güçlü ilk adaylarda açık; faaliyet toplu taramada kapalı; temettü normal trade taramasında kapalı; gecelik momentum deneysel/pasiftir.

## v10.1.2 görünür sonuç ve 50 TL uyumluluk düzeltmesi

- Dashboard, katı filtre sonuç üretmese bile hesaplanmış ve güvenilir izleme adaylarını gösterir.
- Günlük Trade intraday servis kesintisinde son güvenilir raporu açık uyarıyla gösterir.
- Kısa ve orta vade ekranları boş kalmaz; iki listede farklı BIST30 adayları sıralanır.
- 50 TL Altı analizi iPhone/PWA ile aynı likidite, trend, momentum, hacim ve risk/getiri puanlamasını kullanır.

## v10.1.1 tarama görevleri düzeltmesi

- Genel, kısa ve orta vade taraması BIST 30 evrenine döndürüldü.
- Günlük Trade bağımsız olarak tüm aktif BIST evrenini tarar.
- 50 TL Altı ve 10X ekranlarına tüm BIST tarama düğmesi eklendi.
- Ayarlar, Yardım, Erken Büyüme ve Uzun Büyüme ekranları kaldırıldı.
- Paketlere çevrimdışı 613 hisselik evren dosyası eklendi.

## v10.1.0 referans dashboard ve geniş BIST taraması

- Koyu lacivert ve yeşil vurgulu yeni ana dashboard eklendi.
- Günlük Trade aktif BIST evrenini tarar; ağ sorusunda 613 hisselik yerel liste kullanılır.
- Kısa ve orta vade listeleri sonuç aşamasında birbirinden ayrılır; analiz formülleri korunur.
- 50 TL altı analiz, likiditesi en yüksek 120 hisse içinden en iyi 20 sonucu seçer.
- Portföy menüsü Takip Listem olarak değiştirildi; KAP bildirim ekranı bulunmaz.

## v10.0.1 kullanılabilirlik düzeltmeleri

- Bugün ekranına görünür hisse, potansiyel ve güven önizlemeleri eklendi.
- Günlük Trade ekranına taramayı doğrudan başlatan düğme eklendi.
- Erken Büyüme ve KAP menüleri kaldırıldı.
- 50 TL altı analiz en fazla 20 seçenek sunacak şekilde genişletildi.

## v10.0.0 sade ve karar odaklı arayüz

- Ana sayfa yalnızca piyasa durumunu ve günlük/kısa/orta vade aday sayılarını gösterir.
- Günlük Trade, Kısa Vade ve Orta Vade listeleri en fazla 5 aday ve sade fiyat/risk bilgileriyle sınırlandırılmıştır.
- Teknik göstergeler analiz motorunda korunmuş, ana ekrandan ve ana Excel raporundan çıkarılmıştır.
- Erken Büyüme, 50 TL Altı Büyüme ve belirsizliği açıkça belirtilen 10X Senaryosu eklenmiştir.
- Ana tablolar 1366×768 ekran için yatay kaydırmasız, PWA ise mobilde tek sütun olacak şekilde düzenlenmiştir.

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

- [Borsa Analiz Pro MAX v10.3.1 kurulum dosyasını aç](SetupOutput/Setup_Borsa_Analiz_Pro_MAX_v10.3.1.exe)
- SHA-256: `1136EBADA4F5239AA092384225D6BB06BF97BEABF465AD739205F3F4E1B7973C`

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
