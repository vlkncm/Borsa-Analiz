"""Canli sinyaller icin muhafazakar, denetlenebilir kalite kapisi.

Bu modül fiyat tahmini yapmaz. Amaci, tarihsel örnegi az, verisi eski ya da
risk profili zayif olan durumlarda kesin görünen bir islem sinyali üretilmesini
engellemektir.
"""

from __future__ import annotations

import math
from typing import Any, Dict


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def wilson_alt_sinir(basari_yuzde: float, ornek_sayisi: int, z: float = 1.96) -> float:
    """Basari oraninin %95 Wilson alt sinirini yüzde olarak döndürür."""
    if ornek_sayisi <= 0:
        return 0.0
    p = min(1.0, max(0.0, basari_yuzde / 100.0))
    n = float(ornek_sayisi)
    center = p + z * z / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    lower = (center - spread) / (1.0 + z * z / n)
    return round(max(0.0, lower * 100.0), 1)


def canli_sinyal_dogrula(
    item: Dict[str, Any],
    beklenen_getiri: float,
    olasi_kayip: float,
    risk_getiri: float,
) -> Dict[str, Any]:
    """Sinyalin canli kullanima uygunlugunu kontrol eder.

    Esikler kasitli olarak muhafazakardir. Bir esik saglanmiyorsa sonuc
    ``IZLE - DOGRULAMA YETERSIZ`` olur; modül asla olumlu sinyal uydurmaz.
    """
    samples = int(_number(item.get("kisa_ornek"), 0))
    historical = _number(item.get("kisa_tarihsel_olasilik"), 0)
    safe_probability = _number(item.get("kisa_guvenli_olasilik"), 0)
    data_confidence = _number(item.get("veri_guven_puani"), 0)
    evidence = _number(item.get("profesyonel_kanit_puani"), 0)
    market = str(item.get("piyasa_rejimi", "")).upper()

    wilson = wilson_alt_sinir(historical, samples)
    # Daha önce hesaplanan güvenli olasılık varsa onu da aşmamak gerekir.
    calibrated = min(x for x in (wilson, safe_probability) if x > 0) if (wilson > 0 and safe_probability > 0) else min(wilson, safe_probability)

    issues = []
    if samples < 40:
        issues.append("yeterli tarihsel örnek yok (en az 40 gerekli)")
    if calibrated < 50:
        issues.append("%95 güven alt sınırında başarı oranı yetersiz")
    if data_confidence < 75:
        issues.append("veri güveni düşük")
    if evidence < 65:
        issues.append("tarihsel kanıt puanı düşük")
    if risk_getiri < 1.8:
        issues.append("risk/getiri oranı 1:1,8 altında")
    if not 2.0 <= beklenen_getiri <= 15.0:
        issues.append("hedef getirisi denetlenebilir aralığın dışında")
    if not 0.8 <= olasi_kayip <= 8.0:
        issues.append("stop mesafesi uygun değil")
    if "DÜŞ" in market or "NEGATİF" in market:
        issues.append("piyasa rejimi olumsuz")

    return {
        "onayli": not issues,
        "dogrulanmis_olasilik": round(calibrated, 1),
        "wilson_alt_sinir": wilson,
        "dogrulama_ornek_sayisi": samples,
        "dogrulama_notu": " | ".join(issues) if issues else "Sinyal, muhafazakar canlı doğrulama eşiklerini geçti.",
    }
