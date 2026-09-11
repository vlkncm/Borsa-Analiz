"""Fiyat verisinin işlem kararı için yeterli güncellikte olup olmadığını denetler."""
from __future__ import annotations
from typing import Any, Dict
import math


def _f(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def veri_kalite_kapisi(item: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    age = _f(item.get("veri_islem_gunu_gecikmesi", item.get("veri_yasi_gun")), 99)
    confidence = _f(item.get("veri_guven_puani"))
    source = str(item.get("veri_kaynagi", ""))
    if age > 0: reasons.append("Son işlem gününün kapanış verisi yok")
    if confidence < 80: reasons.append("Veri güven puanı 80 altında")
    if "Borsa İstanbul" not in source: reasons.append("Resmî BIST kapanışıyla doğrulanmadı")
    adjustment = _f(item.get("kurumsal_aksiyon_riski"))
    if adjustment > 0: reasons.append("Kurumsal aksiyon/fiyat serisi kontrolü gerekli")
    return {"veri_kalite_onayli": not reasons, "veri_kalite_notu": " | ".join(reasons) if reasons else "Güncel resmî kapanış verisi doğrulandı", "fiyat_tipi": "SON RESMÎ KAPANIŞ (CANLI DEĞİL)"}


def data_confidence(item: Dict[str, Any], features=None, require_financial=False) -> Dict[str, Any]:
    """Skordan bağımsız veri güveni; eksik kanıtı yüksek güven kabul etmez."""
    features = features or item.get("ertesi_gun_ozellikleri") or {}
    quality = veri_kalite_kapisi(item)
    reasons = [] if quality["veri_kalite_onayli"] else [quality["veri_kalite_notu"]]
    critical = not quality["veri_kalite_onayli"]
    if not features.get("veri_yeterli") or _f(features.get("bar_sayisi")) < 60:
        critical = True
        reasons.append("Yeterli doğrulanmış OHLCV barı yok")
    if _f(features.get("eksik_bar_sayisi")) > 0:
        reasons.append("Eksik/geçersiz OHLCV barı var")
    if not features.get("benchmark_mevcut"):
        reasons.append("Benchmark verisi yok")
    if item.get("cache_fallback"):
        reasons.append("Sağlayıcı hatası sonrası cache fallback")
        critical = True
    if require_financial and item.get("finansal_veri_dogrulandi") is not True:
        reasons.append("Doğrulanmış finansal veri: VERİ YOK")
    level = "LOW" if critical else "MEDIUM" if reasons else "HIGH"
    return {"DATA_CONFIDENCE": level, "data_confidence_notu": " | ".join(reasons) or "Veri kontrolleri tamamlandı"}
