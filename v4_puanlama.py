from __future__ import annotations

import math
from typing import Any, Dict, List


def gf(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _trend_score(item: Dict[str, Any]) -> float:
    price = gf(item.get("price"))
    ema20 = gf(item.get("ema20"))
    ema50 = gf(item.get("ema50"))
    ema200 = gf(item.get("ema200"))
    adx = gf(item.get("adx"))

    score = 45
    if price > ema20 > 0:
        score += 15
    else:
        score -= 15

    if ema20 > ema50 > 0:
        score += 18
    else:
        score -= 10

    if ema200 > 0:
        score += 12 if price > ema200 else -12

    if adx >= 30:
        score += 10
    elif adx >= 20:
        score += 5
    elif 0 < adx < 15:
        score -= 5

    return clamp(score)


def _momentum_score(item: Dict[str, Any]) -> float:
    rsi = gf(item.get("rsi"), 50)
    macd = gf(item.get("macd"))
    signal = gf(item.get("macd_signal"))
    ret20 = gf(item.get("ret_20"))
    ret60 = gf(item.get("ret_60"))

    score = 50
    if 45 <= rsi <= 62:
        score += 15
    elif 35 <= rsi < 45:
        score += 5
    elif 62 < rsi < 70:
        score += 5
    elif rsi >= 75:
        score -= 18
    elif rsi < 30:
        score -= 12

    score += 15 if macd > signal else -10

    if 0 < ret20 <= 15:
        score += 12
    elif ret20 > 25:
        score -= 8
    elif ret20 < -12:
        score -= 12

    if ret60 > 0:
        score += 8
    elif ret60 < -20:
        score -= 8

    return clamp(score)


def _volume_score(item: Dict[str, Any]) -> float:
    ratio = gf(item.get("volume_ratio"), 1.0)
    reasons = " ".join(item.get("reasons", [])).lower()

    if ratio >= 2.0:
        return 90
    if ratio >= 1.5 or "%50 üzerinde" in reasons:
        return 82
    if ratio >= 1.2 or "hacim ortalamanın üzerinde" in reasons:
        return 68
    if ratio < 0.65:
        return 32
    return 50


def _risk_score(item: Dict[str, Any]) -> float:
    rr = gf(item.get("risk_getiri_1"))
    price = gf(item.get("price"))
    atr = gf(item.get("atr"))
    resistance_distance = gf(item.get("direnc_mesafe_yuzde"), 100)

    score = 50
    if rr >= 3:
        score += 25
    elif rr >= 2:
        score += 18
    elif rr >= 1.5:
        score += 8
    elif rr < 1:
        score -= 22

    atr_ratio = atr / price if price > 0 else 0
    if atr_ratio > 0.055:
        score -= 18
    elif atr_ratio > 0.035:
        score -= 8
    elif 0 < atr_ratio < 0.02:
        score += 6

    if resistance_distance <= 2:
        score -= 18
    elif resistance_distance <= 5:
        score -= 8
    elif 8 <= resistance_distance <= 25:
        score += 8

    return clamp(score)


def _kap_haber_score(item: Dict[str, Any]) -> float:
    kap = gf(item.get("kap_skor"))
    haber = gf(item.get("haber_puani"))
    etiket = str(item.get("kap_etiket", "")).lower()

    score = 50 + kap * 1.5 + haber
    if "olumlu" in etiket:
        score += 8
    elif "olumsuz" in etiket:
        score -= 15
    return clamp(score)


def _mtf_score(item: Dict[str, Any]) -> float:
    score = gf(item.get("mtf_skor"), 50)
    uyum = str(item.get("mtf_uyum", "")).lower()
    karar = str(item.get("mtf_karar", "")).upper()

    if "güçlü" in uyum and karar == "AL":
        score += 10
    elif "negatif" in uyum:
        score -= 15
    return clamp(score)


def v4_puanla(item: Dict[str, Any], final: bool = False) -> Dict[str, Any]:
    trend = _trend_score(item)
    momentum = _momentum_score(item)
    volume = _volume_score(item)
    risk = _risk_score(item)
    mtf = _mtf_score(item)
    fundamental = clamp(gf(item.get("temel_puan"), 50))
    kap_news = _kap_haber_score(item)
    activity = clamp(gf(item.get("faaliyet_puani"), 50))
    macro = clamp(gf(item.get("makro_puan"), 50))

    # Historical probability is only available near the end of the run.
    historical = clamp(gf(item.get("30_gun_20_olasilik", item.get("30 Gün %20+ Olasılık", 50)), 50))
    if not final:
        historical = 50

    # Weighted multi-layer model. No single indicator can dominate.
    raw = (
        trend * 0.18 +
        momentum * 0.14 +
        volume * 0.09 +
        risk * 0.14 +
        mtf * 0.10 +
        fundamental * 0.10 +
        kap_news * 0.08 +
        activity * 0.07 +
        macro * 0.05 +
        historical * 0.05
    )

    # Penalize contradictions.
    technical_action = str(item.get("aksiyon", "TUT")).upper()
    if technical_action == "SAT":
        raw -= 12
    if str(item.get("mtf_uyum", "")).lower().startswith("negatif"):
        raw -= 8
    if gf(item.get("rsi")) >= 75:
        raw -= 5
    if gf(item.get("risk_getiri_1")) < 1:
        raw -= 7

    # Formasyon tek başına karar vermez; yalnızca teyitli desenler sınırlı katkı sağlar.
    form_score = gf(item.get("formasyon_puani"))
    form_dir = str(item.get("formasyon_yonu", "NÖTR")).upper()
    form_confirmed = str(item.get("formasyon_teyit", "")).lower() == "evet"
    if form_confirmed and form_score >= 65:
        raw += min(6, (form_score - 60) * 0.12) if form_dir == "YUKARI" else -min(6, (form_score - 60) * 0.12)

    # 100/100 should be practically impossible.
    confidence = int(round(clamp(raw, 8, 97)))

    rr = gf(item.get("risk_getiri_1"))
    mtf_negative = "negatif" in str(item.get("mtf_uyum", "")).lower()

    if confidence >= 88 and technical_action == "AL" and rr >= 1.8 and not mtf_negative:
        view = "ÇOK GÜÇLÜ POZİTİF"
        action = "GÜÇLÜ AL"
    elif confidence >= 80 and technical_action in {"AL", "TUT"} and rr >= 1.4 and not mtf_negative:
        view = "POZİTİF"
        action = "AL"
    elif confidence >= 68:
        view = "YÜKSEK ÖNCELİKLİ İZLE"
        action = "TUT"
    elif confidence >= 55:
        view = "NÖTR / İZLE"
        action = "TUT"
    else:
        view = "NEGATİF / RİSKLİ"
        action = "SAT"

    # Separate 2–6 week score.
    potential = (
        confidence * 0.45 +
        trend * 0.15 +
        momentum * 0.10 +
        risk * 0.15 +
        mtf * 0.10 +
        historical * 0.05
    )
    potential = int(round(clamp(potential, 0, 95)))

    reasons = []
    if trend >= 70:
        reasons.append("Trend güçlü")
    if momentum >= 65:
        reasons.append("Momentum olumlu")
    if volume >= 68:
        reasons.append("Hacim desteği var")
    if risk >= 65:
        reasons.append("Risk/getiri uygun")
    if mtf >= 65:
        reasons.append("Zaman dilimleri uyumlu")
    if fundamental >= 65:
        reasons.append("Temel görünüm olumlu")
    if activity >= 65:
        reasons.append("Faaliyet görünümü olumlu")
    if kap_news >= 65:
        reasons.append("KAP/haber desteği var")
    if form_confirmed and form_score >= 65 and form_dir == "YUKARI":
        reasons.append(f"{item.get('formasyon', 'Formasyon')} teyitli")

    warning = []
    if risk < 45:
        warning.append("Risk/getiri zayıf")
    if momentum < 40:
        warning.append("Momentum zayıf")
    if mtf_negative:
        warning.append("Zaman dilimi uyumsuz")
    if gf(item.get("rsi")) >= 75:
        warning.append("RSI yüksek")
    if form_confirmed and form_score >= 65 and form_dir == "AŞAĞI":
        warning.append(f"{item.get('formasyon', 'Düşüş formasyonu')} teyitli")

    return {
        "v4_guven_puani": confidence,
        "v4_gorunum": view,
        "v4_aksiyon": action,
        "v4_2_6_hafta_puani": potential,
        "v4_trend_puani": round(trend, 1),
        "v4_momentum_puani": round(momentum, 1),
        "v4_hacim_puani": round(volume, 1),
        "v4_risk_puani": round(risk, 1),
        "v4_mtf_puani": round(mtf, 1),
        "v4_temel_puani": round(fundamental, 1),
        "v4_kap_haber_puani": round(kap_news, 1),
        "v4_faaliyet_puani": round(activity, 1),
        "v4_makro_puani": round(macro, 1),
        "v4_nedenler": " | ".join(reasons[:6]) if reasons else "Güçlü ortak sinyal oluşmadı",
        "v4_uyarilar": " | ".join(warning[:5]) if warning else "Belirgin ek uyarı yok",
    }


def v4_toplu_puanla(results: List[Dict[str, Any]], final: bool = False) -> List[Dict[str, Any]]:
    for item in results:
        item.update(v4_puanla(item, final=final))
        # Keep compatibility with old screens and filters.
        item["broker_skor"] = item["v4_guven_puani"]
        item["broker_aksiyon"] = item["v4_aksiyon"]
        item["broker_yorum"] = (
            f"v4 çok katmanlı karar motoru: {item['v4_gorunum']}. "
            f"Güven {item['v4_guven_puani']}/100. "
            f"Nedenler: {item['v4_nedenler']}. "
            f"Uyarılar: {item['v4_uyarilar']}."
        )
    return results
