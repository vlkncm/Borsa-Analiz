# Borsa Analiz Pro MAX v7.4.1

Sadeleştirilmiş BIST yatırım karar motoru.

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

- [Borsa Analiz Pro MAX v7.4.1 kurulum dosyasını indir](downloads/v7.4.1/Setup_Borsa_Analiz_Pro_MAX_v7.4.1.exe)
- SHA-256: `ECF4EB6E89BE9463FC8EADB37E3E597B4192F17E9AED554C6AED82C614885AFE`

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
