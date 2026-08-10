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
