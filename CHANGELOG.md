# Değişiklik Günlüğü

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
