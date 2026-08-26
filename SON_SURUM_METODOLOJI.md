# Son Sürüm Metodolojisi

Uygulama kesin getiri veya doğru alış/satış tahmini vaat etmez. İşlem senaryosu
oluşması için aynı anda veri kalite kapısı, canlı kanıt kilidi, maliyet/stres
kontrolü ve çok faktörlü teknik doğrulama gerekir.

## Zamana bağlı hedef olasılığı

Günlük Trade için ana ufuk stratejiyle birlikte önceden tanımlanmış 3 tamamlanmış işlem günüdür; denetimde ayrıca 1 ve 5 günlük ufuklar raporlanır. Her ufukta yalnız o süreyi tamamen gözlemiş zaman sıralı OOS sinyaller paydaya alınır. Hedef ve stop yarışan olaylardır; aynı mum belirsizliğinde stop önce kabul edilir. Bu sürüm Aalen–Johansen yerine tam gözlenmiş sabit ufukta sade ampirik oran kullanır. En az 30 olgunlaşmış örnek yoksa yüzde gösterilmez; yeterli örnekte Wilson %95 güven aralığı verilir. BIST seans listesi sağlandığında tatiller bu listeden dışlanır, aksi durumda hafta sonlarını dışlayan iş günü takvimi kullanılır.

## Kullanılan faktörler

- Trend: EMA20/EMA50 ve MACD
- Momentum: RSI ve Stochastic
- Volatilite: ATR ve Bollinger Z
- Hacim/fiyat: 20 günlük VWAP ve OBV
- Piyasa ve göreceli güç: mevcut BIST 100 ve çoklu zaman dilimi katmanı

Bu göstergeler, TA-Lib'in yaygın teknik analiz fonksiyonlarıyla uyumludur. Her
birinin tek başına tahmin gücü varsayılmaz; yalnızca birlikte ve dış örnek
performansında maliyet sonrası başarılı olmaları hâlinde strateji etkinleşir.

## Veri ilkesi

Ekrandaki günlük fiyat `SON RESMÎ KAPANIŞ (CANLI DEĞİL)` olarak etiketlenir.
Lisanslı anlık BIST veri sağlayıcısı yapılandırılmadan piyasa içi alış/satış
fiyatı veya emir defteri analizi üretilmez.
