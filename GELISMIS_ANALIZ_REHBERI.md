# Gelişmiş Analiz ve İzleme

Bu sürüm, hedef fiyatı kesin tahmin olarak kullanmaz. Her sinyal için likidite,
temel risk, ATR-temelli belirsizlik bandı ve canlı risk uyarıları gösterilir.

- `yuruyen_donem_raporu`, teknik kuralı yalnızca o gün mevcut verilerle ölçer.
- Mevcut `sinyal_gecmisi.csv`, açık sinyalleri hedef/stop kapanışıyla izler.
- `portfoy_risk_ozeti`, tüm açık işlemlerde toplam riskin sermayenin %5'ini
  geçip geçmediğini denetler.
- `kullanici_karar_gunlugu.karar_kaydet`, kullanıcının sinyali alıp almadığını
  ve gerekçesini yerel olarak kaydeder.

Bu araç yatırım tavsiyesi, emir veya getiri garantisi değildir.
