# Borsa Analiz Pro MAX v8.5.0

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

- [Borsa Analiz Pro MAX v8.5.0 kurulum dosyasını indir](downloads/v8.5.0/Setup_Borsa_Analiz_Pro_MAX_v8.5.0.exe)
- SHA-256: `2C3FE17675CC9B4085ED9EA44E8B92CE17731B14705A8939CEF45E95CFE42DF4`

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
