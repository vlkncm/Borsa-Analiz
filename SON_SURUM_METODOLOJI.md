# Son Sürüm Metodolojisi

Uygulama kesin getiri veya doğru alış/satış tahmini vaat etmez. İşlem senaryosu
oluşması için aynı anda veri kalite kapısı, canlı kanıt kilidi, maliyet/stres
kontrolü ve çok faktörlü teknik doğrulama gerekir.

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
