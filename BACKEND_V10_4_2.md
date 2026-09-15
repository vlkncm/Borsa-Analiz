# v10.4.2 backend karşılaştırması

Başlangıç: temiz çalışma ağacı, `eb04eb9`, uygulama/installer v10.3.3.
Referanslar: v10.3.4 etiketi `a7d761f`; GitHub ana dalı `b201c34`,
`APP_VERSION=10.4.1` (v10.4.1 etiketi bulunmuyor).

## Seçilen geliştirmeler

- v10.3.4: İstanbul saatinde günlük bar tamamlama; düzeltilmiş/ham fiyat için
  ayrı cache; düzeltilmiş seriye ham resmî fiyat eklememe; eski fallback bilgisini
  taşıma; direnç hedefini zorla yükseltmeme; alış bandının üstünden risk hesabı;
  giriş/hedef/stop üzerinden yeniden hesaplanan risk/getiri.
- v10.4.1: ilk sermayeyi drawdown hesabına katma; eğitimde sinyal zamanı kadar
  sonuçlanma zamanını da kontrol etme; veri güvenliği veto koşullarını yedek
  aday listelerine de uygulama. Sonuç zamanı bilinmeyen kayıtlar için yeni
  sürümün yaklaşık seans-sonu varsayımı yerine olasılık üretimi durduruldu.
- Yerel: kanonik Wilder RSI/ATR/ADX, ortak canlı/backtest indikatör pipeline'ı,
  SuperTrend, Ichimoku, hacim/para akışı/risk göstergeleri, üç sonuçlu ve Wilson
  aralıklı işlem kanıtları, T+1/T+2 snapshot ve kalibrasyon sistemi, tüm BIST
  kısa/orta vade listeleri, günlük trade teyitleri, IPO analizi ve arayüz korundu.

## İlave doğruluk düzeltmeleri

- Sonsuz OHLC değerlerini geçersiz sayma; tarih/saat ve cache frekansı tutarlılığı.
- Intraday serinin bütün barlarında tamamlanma kontrolü.
- Backtestte split/temettü düzeltilmiş seri, benzersiz ve sıralı tarihler;
  ATR başlangıcında gelecekteki değeri geriye doldurmama.
- Eksik/sıfır hacim ve eski fallback ile alım kararını engelleme.
- Serinin kaynak adı yerine son bar tarihini resmî BIST bülteni tarihiyle de
  eşleştirme; önceki günü doğrulayan bülteni bugünün kapanış teyidi saymama.
- Ham seride %25'i aşan kopmalarda kurumsal aksiyon/veri kontrolü gerektirme
  (bu bir split/temettü doğrulaması değil, ihtiyatlı güvenlik filtresidir).
- 200 bar dolmadan uzun trendi olumlu kabul etmeme.
- Tarihsel rejim olasılığında örtüşen ileri getiri pencerelerini ayrı örnek saymama.
- Vade ağırlıklarını toplam 1.10'dan normalize etme; geçersiz stop/alış bandı ve
  veri kalitesi veto koşullarını fallback dahil aday seçiminde koruma.
- İsteğe bağlı olasılık/sonuç-belirsizliği sütunları yokken performans özeti
  çalışma zamanı hatasını düzeltme.

## Doğrulama ve sınırlar

Yeni regresyon testleri; mevcut temel/arayüz testleri; kaynak uygulamada bütün
menülerin açılması; teknik analiz ve karar üretimi kontrol edildi. `app_qt.py`
başlangıca göre yalnız sürüm sabitinde değişti; `dashboard_ui.py` ve assets aynı.
520 barlık sabit tohumlu sentetik geçmişte temiz verinin eski/yeni backtest
işlemleri aynı kaldı; sırasız/tekrarlı veri yeni sürümde aynı sonucu üretti.
Son test turu: 240 test ve 4 alt test başarılı (1 kritik olmayan uyarı).

Projede doğrulanmış tarihsel OHLCV/PIT evren veri seti bulunmadı. Gerçek piyasa
verisinde başarı, getirinin veya risk ayarlı performansın arttığı kanıtlanmadı.
Eski teknik senaryo skoru kalibre edilmiş olasılık veya kazanç garantisi değildir.
Başlangıçtaki BIST30 benchmark sağlayıcı sembolü korunmuştur; adı BIST100 olan
yerel yardımcı fonksiyonun referansı fiilen BIST30'dur.

Build: `release/v10.4.2/BorsaAnalizProMAX` ve `BorsaTaramaMotoru`.
Installer: `release/v10.4.2/installer/Setup_Borsa_Analiz_Pro_MAX_v10.4.2.exe`.
Yeni bağımlılık eklenmedi. Test/build günlükleri `.validation` altında.
Paketlenmiş EXE içindeki backend kodu son kaynaklarla karşılaştırıldı ve eşleşti.
Paketlenmiş uygulama offscreen modunda 15 saniye açık kaldı; startup kontrolü
başarılı. Artifact SHA-256 değerleri `release/v10.4.2/SHA256SUMS.txt` içinde.

## Değiştirilen dosyalar

- `veri_saglayici.py`, `veri_kalite_kapisi.py`, `borsa_tarayici.py`
- `backtest.py`, `intraday_backtest.py`, `profesyonel_analiz.py`
- `karar_motoru.py`, `vade_motoru.py`, `sade_karar_modeli.py`
- `main.py`, `app_qt.py` (yalnız sürüm), `BorsaAnalizProMAX_v2.iss`
- `test_finansal_motorlar.py`, `test_gunluk_trade.py`
- `test_backend_integrity_v10_4_2.py` (yeni), `BACKEND_V10_4_2.md` (yeni)
- `.validation/`: test, smoke ve build doğrulama yardımcıları/günlükleri.
- `release/v10.4.2/`: yeni EXE, tarama motoru, installer ve SHA-256 listesi.
