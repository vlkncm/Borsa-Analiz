"""Olağandışı fiyat-hacim hareketleri için muhafazakar risk monitörü.

Bu modül tavan tahmini veya alım önerisi üretmez. Amaç, KAP ile açıklanmayan
veya likiditesi zayıf hızlı yükselişlerde kovalama riskini görünür kılmaktır.
"""
from __future__ import annotations

import math
from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def olaganustu_hareket_degerlendir(item: Dict[str, Any]) -> Dict[str, Any]:
    price = _f(item.get("price"))
    ret20 = _f(item.get("ret_20"))
    volume_ratio = _f(item.get("volume_ratio"), 1.0)
    turnover = _f(item.get("ortalama_gunluk_islem_tutari"))
    kap_score = _f(item.get("kap_skor"))
    events = str(item.get("kap_olaylari", ""))

    reasons = []
    risk = 0
    if ret20 >= 25:
        risk += 30
        reasons.append("20 günlük fiyat artışı olağandışı yüksek")
    elif ret20 >= 15:
        risk += 15
        reasons.append("20 günlük fiyat artışı yüksek")
    if volume_ratio >= 3:
        risk += 25
        reasons.append("hacim 20 günlük ortalamanın 3 katı üzerinde")
    elif volume_ratio >= 1.8:
        risk += 12
        reasons.append("hacim sıçraması var")
    if turnover < 5_000_000:
        risk += 25
        reasons.append("ortalama işlem tutarı düşük; çıkış/kayma riski yüksek")
    official_support = kap_score > 0 and events not in ("", "SINIFLANDIRILACAK OLAY YOK")
    if not official_support and (ret20 >= 15 or volume_ratio >= 1.8):
        risk += 20
        reasons.append("hareketi destekleyen sınıflanmış olumlu KAP olayı yok")
    if kap_score < -10:
        risk += 20
        reasons.append("olumsuz KAP etkisi var")
    risk = min(100, risk)
    extraordinary = ret20 >= 15 and volume_ratio >= 1.8
    chase_block = extraordinary and (risk >= 45 or ret20 >= 30)
    # Tavanın bozulması/likiditenin kaybolması halinde iki günlük %10 ters hareket
    # varsayımıdır; gerçekleşecek fiyat için tahmin veya garanti değildir.
    stress_exit = price * 0.80 if price > 0 else 0.0
    return {
        "olaganustu_hareket": extraordinary,
        "olaganustu_risk_puani": risk,
        "resmi_kap_destegi": "VAR" if official_support else "YOK / DOĞRULANAMADI",
        "kovalama_engeli": chase_block,
        "stres_cikis_fiyati": round(stress_exit, 2),
        "stres_kayip_yuzde": 20.0 if price > 0 else 0.0,
        "olaganustu_not": " | ".join(reasons) if reasons else "Belirgin olağandışı fiyat-hacim hareketi yok",
        "izleme_etiketi": "OLAĞANDIŞI HAREKET - YÜKSEK RİSK" if chase_block else "NORMAL İZLEME",
    }
