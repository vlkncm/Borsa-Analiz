# Değişiklik Günlüğü

## 10.3.0

- T+1/T+2 point-in-time özellik, etiketleme, model eğitimi ve kalibrasyon altyapısı eklendi.
- Tüm BIST için hisseye özel özellik hashleri ve kesitsel güçlü hareket sıralaması eklendi.
- Yeni halka arz, menkul türü, merkezi sembol eşleme ve veri yetersizliği güvenlikleri korundu.
- Tahmin snapshot'ları ile gerçekleşmeler SQLite'ta ayrı ve değiştirilemez kayıtlar olarak tutulur.
- Toplu taramanın kurulu EXE'de eksik worker dosyası yüzünden başlamaması giderildi.

## 10.2.0

- RSI, EMA/SMA, MACD/MACD-V, ATR, ADX, Bollinger/BBW, VWAP, pivot, hacim ve risk ölçümleri için tek teknik gösterge motoru eklendi.
- Tarama, Günlük Trade, grafik ve backtest hesapları ortak motor API'sine bağlandı.
- OHLCV metadata sözleşmesi sembol, ilk/son bar, zaman dilimi, aralık, fiyat temeli, resmî kapanış ve kurumsal işlem uyarısıyla genişletildi.
- Pasif ve isteğe bağlı analizler envanterde açıklandı.
- Deneysel stratejileri ana karardan izole eden sürümlü eklenti sözleşmesi eklendi.
- Komisyon, spread, kayma ve diğer masrafları ayrı saklayan brüt/net beklenen değer modeli eklendi; net beklenti sıfır veya altındaysa işlem kapısı kapanır.
- `HEDEF_ONCE`, `STOP_ONCE`, `SURE_DOLDU` olayları, Wilson %95 güven aralığı, Brier skoru ve log-loss ile üç sonuçlu OOS kanıt modeli eklendi.
- Zaman hizalı BIST/sektör göreceli gücü, piyasa rejimi, aynı-saat RVOL ve look-ahead güvenli MFE/MAE doğrulaması eklendi.
- Eski veri, yetersiz örnek, uygun olmayan rejim, likidite, negatif net beklenti, risk/getiri, göreceli güç ve RVOL/VWAP zorunlu karar kapıları eklendi.
- Mevcut sade kullanıcı arayüzü korundu.
