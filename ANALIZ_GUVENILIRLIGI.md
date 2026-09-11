# Analiz güvenilirliği incelemesi

Taban: `436efe434263a55c196042c4486502d4aafbb841` (origin/main).
Başlangıç: APP_VERSION ve paketleme 10.2.1; README de 10.2.1.
v10.3.4 etiketi başka commit üzerinde; main yerine kullanılmadı.
Baseline: mevcut .venv ile `python -m unittest discover -v`: 176 PASS.
Sistem Python'unda bağımlılıklar eksik (27 import hatası); .venv kullanıldı.

## Değişiklik öncesi gerçek akış

| Yol | Evren / veri / doğrulama | Göstergeler, skor ve risk | UI, cache ve test |
|---|---|---|---|
| Ertesi gün tavan | tarama_evreni CEILING_POTENTIAL: tüm BIST; main → borsa_tarayici.teknik_analiz → merkezi veri_saglayici; BIST bülteni birleştirme | ertesi_gun_tavan günlük özellikleri; main profesyonel rejim/sektör bağlamını ekliyor; aday_degerlendir mevcut aile ağırlıkları | adaylari_tabloya_cevir → Excel → app_qt.ertesi_gun_tavan_gorunumu; ortak SQLite fiyat cache ve strateji metadata; test_ertesi_gun_tavan, test_merkezi_tarama_mimarisi |
| Günlük Trade | DAILY_TRADE: tüm BIST; günlük rapor + ayrı intraday adapter yolu | gunluk_trade_gostergeleri AlphaTrend/EMA20/BBW/MACD-V; gunluk_trade_motoru VWAP/pivot/ATR/doji ve ampirik örnek kapısı; karar_motoru resmî kapanış kalite kapısı | günlük ekran worker ve rapor fallback; merkezi sağlayıcı; test_gunluk_trade, test_gunluk_trade_arayuzu |
| Kısa / orta | SHORT_TERM ve MEDIUM_TERM BIST30; ortak teknik tarama | profesyonel_analiz, v4, karar_motoru, vade_motoru farklı ağırlıklar ve 5–20 gün / 1–3 ay; kanıt ve R/R filtresi | rapor + sade görünüm/fallback; stratejiye özel cache ve evren maskesi; test_bist30_evreni, test_tarama_evreni_tutarliligi |
| 50 TL altı | rapor: tüm BIST → likit_120_sec → elli_tl_adaylari; bağımsız Under50Worker tüm BIST → get_daily_ohlcv → elli_tl_ohlcv_adayi | fiyat <=50 ve 5 milyon TL işlem tutarı; mevcut teknik puanlama; worker sağlayıcı metadata'sını atıyordu | Under50Page, bağımsız request/cache; test_page_scan_isolation, test_sade_karar_modeli |

Fiyat cache'i veri_saglayici SQLite/RLock ile merkezi; benchmark ayrıca kilitli
hafıza cache'i kullanıyor. Scan runner ayrı süreç, UI worker'ları QThread kullanıyor.
Yeni indirme motoru veya thread havuzu gerekmiyor.

## Kanıtlanan hatalar

Yeni adversarial testlerin ilk koşusu: 8 test başarısız (11 assertion).
Bozuk son barın geçmiş kapanışa düşmesi; sıfır/negatif hacim; RVOL paydasına
karar barının girmesi; gelecek KAP'ın puan artırması; intraday ATR'ye gelecekteki
günlük barın girmesi; BIST100 yerine BIST30 indirilmesi; ilk işlem kaybının
drawdown'a katılmaması; veri bütünlüğünde yayın zamanının yalnız varlığının kontrolü.

## Model doğrulama sınırı

Doğrulanmış point-in-time evren, finansal yayın zamanları ve eşlenmiş OOS
işlem veri seti repository'de bulunmadığından yeni ağırlık optimizasyonu yapılmaz.
Mevcut aile ağırlıkları korunur. Sentetik testler performans kanıtı değildir.
Gerçek işlem sayısı, win rate, getiri, drawdown ve profit factor: VERİ YOK.
Eksik finansal veriyle kalite/değerleme başarısı veya ucuzluk iddiası üretilmez.

## Uygulanan değişiklikler ve sınırlar

- Mevcut aile ağırlıkları, dört teknik teyit, evrenler, likit 120 ön seçimi,
  merkezi fiyat sağlayıcı ve worker mimarisi korundu.
- Ortak DATA_CONFIDENCE; tavan, günlük, vade ve 50 TL çıktılarında veri güveni.
  Rapor fallback'leri de aynı güven sıralamasına tabi. Eski metadata'sız rapor
  alış kararı yerine doğrulama bekler; 50 TL için doğrulanmış girdi zorunlu.
- KAP ve OOS kalibrasyon zaman kontrolü; intraday yalnız tamamlanmış önceki
  günlük barları ATR'de kullanır. Sonucu henüz belli olmayan geçmiş sinyaller
  walk-forward kalibrasyona giremez.
- Tavan RVOL, CLV/üst fitil, direnç20/50, ATR kırılımı, ROC1/3/5 ve BIST100
  göreceli gücü; eksik benchmark boş kalır. Sektör/rejim mevcut motorlardan gelir.
- Bozuk son OHLCV, sıfır hacim, gelecek KAP, unverified OOS, stale/fallback
  ve ilk işlem kaybı için adversarial testler eklendi.
- 50 TL fiyat filtresi ucuzluk/finansal kalite iddiası değildir. Bu yolun mevcut
  teknik skorunu finansal kalite modeli gibi yeniden etiketlemedik.
- Geniş taramanın benchmark beklentisini taşıyan iki eski test BIST100'e,
  fiyat sınırı testinin fixture'ı doğrulanmış veri girdisine güncellendi.
  Hiçbir eski test silinmedi.
- Skor grubu ölçümleri OOS veri sağlandığında kullanılabilir; tek başına
  veri setinin OOS olduğunu kanıtlamaz. İşlem sıralı bileşik drawdown portföy
  drawdown'ı değildir; eşzamanlı işlemler için portföy zaman serisi gerekir.
- Sürüm 10.4.0: main kaynak sürümü 10.2.1; başka dallarda mevcut v10.3.4
  etiketiyle çakışmadan sonraki minor. Başka dalın kodu main yerine kullanılmadı.

## Son doğrulama

Tam unittest suite: 194 passed, 0 failed, 0 skipped (.venv).
12 ekran, dolu tavan tablosu, 1366×768 ve Qt olay döngüsü heartbeat smoke: PASS.
Offscreen ortamda sistem fontları bulunmadığından yalnız test betiğinde mevcut
DejaVu fontu kaydedilerek görüntü denetlendi; uygulama fontları değiştirilmedi.
Canlı tüm BIST ağ taraması ve yeni EXE/installer üretimi bu smoke kapsamına girmez.
Look-ahead regresyonları: günlük/intraday gelecek bar, benchmark, KAP ve OOS
sonuç zamanı: PASS. Bu, tüm tarihsel veri kaynaklarının bağımsız sertifikası değildir.
Test logları ve ekran görüntüsü sistem geçici klasöründe; repository'ye eklenmez.
