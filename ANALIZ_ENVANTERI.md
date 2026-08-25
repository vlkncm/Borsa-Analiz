# Analiz Envanteri — v10.2.0

Durumlar: **AKTİF** ana akışta, **OPSİYONEL** ayarla açılır, **PASİF/LEGACY** ana kararı etkilemez. Matematiksel uygulamaların tek kaynağı `teknik_gostergeler/` paketidir.

| Gösterge/model | Kanonik tanım / varsayılan | Kullanım ve zaman dilimi | Durum | Veri/test/backtest/görünürlük |
|---|---|---|---|---|
| RSI | Wilder RMA(14), SMA tohumu | tarama, trade, grafik; günlük/intraday | AKTİF | Close; birim+eşitlik; evet; denetim |
| EMA/SMA | adjust=False EMA; kayan SMA | bütün teknik akışlar | AKTİF | Close; eşitlik; evet; evet |
| MACD / MACD-V | EMA12−EMA26, sinyal 9; MACD-V/ATR26 | tarama/trade/backtest | AKTİF | OHLC; birim+eşitlik; evet; denetim |
| ATR | Wilder TR RMA(14) | risk, stop, boyut; günlük | AKTİF | OHLC; gap testi; evet; evet |
| ADX/+DI/−DI | Wilder DM/TR RMA(14) | trend teyidi | AKTİF | OHLC; birim; evet; denetim |
| Bollinger/BBW | SMA20 ±2σ, ddof=0 | sıkışma teyidi | AKTİF | Close; birim; evet; denetim |
| AlphaTrend | RSI14 ve ATR14 | günlük trade | AKTİF | OHLC; regresyon; dolaylı; denetim |
| Stoch RSI / ROC | RSI14 aralığı / 12 bar değişim | profesyonel analiz | AKTİF | Close; birim; hayır; denetim |
| OBV/CMF/MFI/CCI | standart hacim/momentum formülleri | profesyonel analiz | AKTİF | OHLCV; birim; hayır; denetim |
| SuperTrend / RSI–SuperTrend | ATR trend / RSI dip teyidi | strateji kanıtı | AKTİF | OHLC; mevcut test; hayır; denetim |
| Ichimoku | 9/26/52, 26 kaydırma | profesyonel analiz | AKTİF | OHLC; warm-up; hayır; denetim |
| Seans VWAP | tipik fiyat×hacim kümülatif, günlük reset | intraday | AKTİF | tamamlanmış OHLCV; reset testi; evet; evet |
| Klasik pivot | önceki tamamlanmış gün P/R/S | intraday | AKTİF | günlük OHLC; look-ahead testi; evet; evet |
| Fibonacci / mum / büyük formasyon | salınım seviyeleri / bağlamlı kalıplar | karar ve grafik | AKTİF | OHLCV; mevcut test; hayır; evet |
| Hacim oranları | son hacim / geçmiş medyan-ortalama | tarama/trade | AKTİF | Volume; regresyon; evet; evet |
| Sharpe/Sortino | yıllıklaştırılmış getiri/risk, 252 | profesyonel analiz | AKTİF | getiriler; sıfır risk testi; evet; denetim |
| Beta/göreceli güç | kovaryans/varyans; benchmark getiri | profesyonel analiz | AKTİF | hisse+XU030; eksik test; hayır; denetim |
| Monte Carlo, VaR95, CVaR95 | bootstrap ve kuyruk riski | profesyonel analiz | AKTİF | uzun günlük seri; deterministik seed testi; hayır; denetim |
| Çoklu zaman dilimi | 1G/1H/15m ortak göstergeler | grafik/karar | AKTİF | çoklu OHLCV; eşitlik; hayır; evet |
| Tarihsel olasılık/kalibrasyon | ≥30 OOS; Wilson/Brier | trade kanıtı | AKTİF | sonuç geçmişi; düşük örnek testi; evet; ayrı alan |
| V4 / karar motoru | çoklu kanıt puanı / risk kapıları | ana karar | AKTİF | tüm özellikler; regresyon; evet; evet |
| Günlük Trade beşli kombo | EMA, RSI, MACD, hacim, VWAP | intraday | AKTİF | ortak pipeline; eşitlik; evet; sade sonuç |
| Faktör/usta yatırımcı | eşit ağırlıklı kanıt portföyü | ayrı analiz | AKTİF | fiyat+temel; mevcut test; hayır; ayrı ekran |
| KAP/haber/temel/makro | kaynak bazlı ayrı puan | aday/tek hisse | OPSİYONEL | ağ verisi; hata nötr; hayır; denetim |
| Backtest/maliyet | sonraki açılış, 10 bps komisyon, 5 bps kayma, stop-önce | strateji doğrulama | AKTİF | OHLCV; maliyet/look-ahead; —; rapor |
| Net beklenti | üç sonuçlu brüt beklenti − komisyon/spread/kayma/masraf | bütün trade kararları | AKTİF | OOS olayları+maliyet; birim; evet; sade/denetim |
| Hedef/stop/süre olasılığı | zaman sıralı OOS, Wilson %95, ≥30 örnek | Günlük Trade/kalibrasyon | AKTİF | sürümlü olaylar; birim; evet; sade/denetim |
| Piyasa rejimi | XU100 trendi+genişlik+volatilite+sektör+veri | işlem-yapmama kapısı | AKTİF | hizalı piyasa verisi; birim; evet; sade/denetim |
| BIST/sektör göreceli güç | hisse getirisi−endeks/sektör getirisi, 5/20/60 | aday kapısı/sıralama | AKTİF | hizalı kapanışlar; birim; evet; denetim |
| Aynı-saat RVOL | bugünkü kümülatif / önceki 20 gün aynı-saat medyanı | intraday hacim teyidi | AKTİF | intraday hacim; birim; evet; sade/denetim |
| MFE/MAE | giriş sonrası erişilebilir high/low dağılımı | hedef-stop doğrulama | AKTİF | OOS işlem barları; birim; evet; denetim |
| Gecelik momentum | doğrulanmamış deneysel akış | ana akış dışı | PASİF/LEGACY | ana kararı etkilemez |
| Kişisel portföy | yerel yardımcı modül | ana akış dışı | PASİF/LEGACY | kullanıcı verisi silinmez |
| Kullanıcı karar günlüğü | yerel denetim kaydı | analiz dışı | PASİF/LEGACY | yalnız kayıt |

Eski uyumluluk fonksiyonları v10.2 boyunca korunur ve kanonik pakete yönlenir. Kaldırılmaları en erken bir sonraki ana sürümde, çağıran kalmadığı testle kanıtlandıktan sonra değerlendirilecektir.
