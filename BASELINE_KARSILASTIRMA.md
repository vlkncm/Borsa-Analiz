# v10.2.0 Baseline Karşılaştırması

Karşılaştırma 25 Ağustos 2026 tarihinde ağdan bağımsız sabit OHLCV verileriyle yapıldı.

| Ölçüm | v10.1.2 baseline | v10.2.0 |
|---|---:|---:|
| Mevcut regresyon testi | 109/109 başarılı | 109/109 başarılı |
| Yeni kanonik/eşitlik/kanıt/kapı testi | — | 15/15 başarılı |
| Toplam test | 109 | 124 |
| Tarama/backtest/grafik RSI eşitliği | farklı uygulamalar | birebir (warm-up sonrası) |
| Tarama/backtest MACD eşitliği | kopya uygulamalar | birebir |
| RSI eski SMA ile yeni Wilder ortalama mutlak farkı | referans | 17.390588 puan |
| ATR eski SMA ile yeni Wilder farkı (sabit TR fixture) | referans | 0.000000 |

RSI farkı bilinçli formül geçişidir: eski tarayıcı kayan SMA kullanırken v10.2, 14 dönem SMA tohumu sonrasında Wilder RMA kullanır. Sabit gerçek aralıklı ATR fixture’ında iki yöntem doğal olarak aynıdır; değişken/gap serilerinde yalnız Wilder sonucu kanoniktir.

Sabit fixture karar testi gerçek piyasa performansı iddiası üretmez. Ağdan bağımsız baseline’da gerçekleşmiş işlem evreni bulunmadığı için kazanma oranı, net getiri, expectancy, profit factor, maksimum düşüş, Brier ve kapsama metrikleri **hesaplanmadı / yeterli out-of-sample örnek yok** olarak bırakılmıştır. Bu değerler uydurulmamış ve eski aday listesini korumak amacıyla eşikler yeniden ayarlanmamıştır.

Backtestte kapanış sinyali sonrası giriş bir sonraki bar açılışındadır; komisyon, kayma, gap stopu ve aynı barda hedef+stop için kötümser stop-önce davranışı mevcut regresyon testleriyle korunmuştur.

## Net beklenti ve maliyet baseline'ı

Sabit referans örneğinde `p_hedef=0.50`, `p_stop=0.30`, `p_süre=0.20`, hedef `%4`, stop `%2`, süre sonu medyanı `%0.5` için brüt beklenti `%1.50`'dir. Varsayılan gidiş-dönüş maliyeti `%0.40` (`%0.20` komisyon, `%0.10` spread, `%0.10` kayma, `%0.00` diğer uygulanabilir masraf) sonrası net beklenti `%1.10` olur. Maliyetler yapılandırılabilir ve sıfır varsayılmaz.

## Kapı ablation özeti

Deterministik test senaryolarında bütün kapıları geçen örnek `Uygun`; aşağıdaki bileşenler tek tek kaldırıldığında güvenlik davranışı kaybolur:

| Devre dışı bırakılan kapı | Gözlenen fark |
|---|---|
| OOS örnek | 29 örnekli aday sayısal olasılıkla geçebilir |
| Rejim | RISK_OFF aday yeni işleme açılabilir |
| Net beklenti | maliyet sonrası negatif aday geçebilir |
| Göreceli güç | endeks/sektörden zayıf aday geçebilir |
| RVOL/VWAP | aynı-saat hacim kanıtı olmayan aday geçebilir |
| Veri tazeliği | eski/bozuk veri aday üretebilir |

Bu ablation bir getiri üstünlüğü iddiası değildir; güvenlik değişmezlerinin gerçekten engelleyici olduğunu gösteren birim/regresyon kanıtıdır. Sabit fixture gerçek piyasa dönemlerini temsil etmediğinden hiçbir yeni bileşene alfa/performance katkısı atfedilmemiştir. Gerçek zaman sıralı OOS veri olmadan eşik optimizasyonu yapılmamış, doğrulanmamış bileşen yalnız sıralama puanıyla ana kapıları ezememiştir.

MFE/MAE; yalnız girişten sonraki erişilebilir high/low değerlerinden, rejim/likidite/strateji sürümü bazında 25/50/70/75 yüzdelikleriyle raporlanır. Yeterli OOS dağılımı yoksa hedef/stop ATR ve teknik seviyelerden sessizce yeniden ayarlanmaz.
