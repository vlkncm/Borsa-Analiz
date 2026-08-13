from __future__ import annotations

import math
from typing import Any, Dict

from canli_dogrulama import canli_sinyal_dogrula
from gelismis_analiz import gelismis_sinyal_degerlendir
from strateji_kalibrasyon import strateji_sec
from olaganustu_hareket import olaganustu_hareket_degerlendir
from veri_kalite_kapisi import veri_kalite_kapisi


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def _hedef_suresi_hesapla(item: Dict[str, Any], price: float, target: float, atr: float,
                          market_regime: str) -> Dict[str, Any]:
    """Hedefe erişim için yönlü hız ve oynaklıktan temkinli bir zaman aralığı üretir."""
    required_move = max(1.0, (target / price - 1) * 100)
    atr_pct = max(0.1, atr / price * 100)
    ret20 = _f(item.get("ret_20"))
    ret60 = _f(item.get("ret_60"))
    adx = _f(item.get("adx"))

    # ATR'nin tamamı hedef yönünde ilerleme değildir. Geçmiş net momentum ile
    # günlük hareket kapasitesini birleştirerek daha gerçekçi yönlü hız kullan.
    momentum_speed = max(0.0, ret20 / 20) * 0.60 + max(0.0, ret60 / 60) * 0.40
    volatility_speed = atr_pct * 0.22
    daily_speed = max(0.12, momentum_speed * 0.65 + volatility_speed * 0.35)

    if adx >= 25 and ret20 > 0:
        daily_speed *= 1.12
    elif adx < 18:
        daily_speed *= 0.82
    if "DÜŞÜŞ" in market_regime:
        daily_speed *= 0.72
    elif "YÜKSELİŞ" in market_regime:
        daily_speed *= 1.08

    center_days = int(max(5, min(90, round(required_move / max(daily_speed, 0.08)))))
    uncertainty = 0.30 if adx >= 25 and ret20 > 0 and ret60 > 0 else 0.45
    day_low = max(3, int(round(center_days * (1 - uncertainty))))
    day_high = min(120, max(day_low + 5, int(round(center_days * (1 + uncertainty)))))
    week_low = day_low / 5
    week_high = day_high / 5

    if ret20 > 0 and ret60 > 0 and adx >= 20:
        confidence = "ORTA"
    elif ret20 <= 0 or "DÜŞÜŞ" in market_regime:
        confidence = "DÜŞÜK"
    else:
        confidence = "ORTA-DÜŞÜK"

    return {
        "beklenen_sure": f"{day_low}-{day_high} iş günü (yaklaşık {week_low:.1f}-{week_high:.1f} hafta)",
        "beklenen_sure_alt": day_low,
        "beklenen_sure_ust": day_high,
        "beklenen_hafta_alt": round(week_low, 1),
        "beklenen_hafta_ust": round(week_high, 1),
        "sure_tahmin_guveni": confidence,
        "sure_tahmin_yontemi": "20/60 günlük momentum, ATR, ADX ve piyasa rejimi",
    }


def karar_uret(item: Dict[str, Any]) -> Dict[str, Any]:
    price = _f(item.get("price"))
    atr = max(_f(item.get("atr"), price * 0.025), price * 0.008)
    score = _f(item.get("v4_guven_puani", item.get("broker_skor", item.get("guven", 50))), 50)
    fib_score = _f(item.get("fib_puani"), 50)
    form_score = _f(item.get("formasyon_puani"))
    mtf = _f(item.get("mtf_skor"), 50)
    rr = _f(item.get("risk_getiri_1"))
    fib_support = _f(item.get("fib_destek"))
    fib_resistance = _f(item.get("fib_direnc"))
    technical_target = _f(item.get("hedef_2"), _f(item.get("hedef_1")))
    technical_stop = _f(item.get("stop_loss"))
    market_regime = str(item.get("piyasa_rejimi", "YATAY / BELİRSİZ")).upper()
    data_confidence = _f(item.get("veri_guven_puani"), 0)
    evidence = _f(item.get("profesyonel_kanit_puani"), 0)
    short_safe_probability = _f(item.get("kisa_guvenli_olasilik"), 0)
    evidence_samples = int(_f(item.get("kisa_ornek"), 0))

    if price <= 0:
        return _empty()

    # Alış aralığı: mevcut fiyat ile yakın Fibonacci/teknik destek birlikte kullanılır.
    candidate_supports = [
        x for x in [
            fib_support,
            _f(item.get("ana_destek")),
            _f(item.get("alis_araligi_alt")),
        ] if x > 0 and x <= price * 1.03
    ]
    base_support = max(candidate_supports) if candidate_supports else price - atr
    buy_low = max(0.01, min(price, base_support) - atr * 0.20)
    buy_high = min(price * 1.01, max(price, base_support + atr * 0.25))

    # Hedef: teknik hedef, Fibonacci direnç ve ATR projeksiyonunun temkinli birleşimi.
    candidates = [
        x for x in [technical_target, fib_resistance, price + atr * 4.0]
        if x > price * 1.015
    ]
    target = min(candidates) if candidates else price + atr * 3.0
    if target < price * 1.04:
        target = price + atr * 3.0

    stop_candidates = [
        x for x in [technical_stop, base_support - atr * 0.65]
        if 0 < x < price
    ]
    stop = max(stop_candidates) if stop_candidates else price - atr * 1.8

    expected_return = max(0.0, (target / max(buy_high, 0.01) - 1) * 100)
    possible_loss = max(0.1, (1 - stop / max(buy_low, 0.01)) * 100)
    calculated_rr = expected_return / possible_loss if possible_loss > 0 else 0
    rr = max(rr, calculated_rr)
    validation = canli_sinyal_dogrula(item, expected_return, possible_loss, rr)
    advanced = {
        **gelismis_sinyal_degerlendir({**item, "onerilen_satis": target, "onerilen_stop": stop}),
        **strateji_sec(item),
    }
    extraordinary = olaganustu_hareket_degerlendir({**item, **advanced})
    quality = veri_kalite_kapisi(item)

    # Olasılık ifadesi yalnızca tarihsel/teknik model tahminidir; garanti değildir.
    probability = (
        score * 0.55 +
        fib_score * 0.12 +
        mtf * 0.13 +
        min(form_score, 90) * 0.08 +
        min(max(rr, 0), 4) / 4 * 100 * 0.12
    )
    probability = int(max(25, min(88, round(probability))))
    # Yeterli tarihsel örnek varsa sezgisel skoru kanıtın güvenli alt sınırıyla
    # birleştir. Böylece yüksek puan tek başına yüksek olasılık gibi sunulmaz.
    if evidence_samples >= 20:
        probability = int(round(probability * 0.45 + short_safe_probability * 0.55))
    else:
        probability = min(probability, 55)
    if "DÜŞÜŞ" in market_regime:
        probability = max(25, probability - 8)
    elif "YÜKSELİŞ" in market_regime:
        probability = min(88, probability + 3)
    if data_confidence < 60:
        probability = min(probability, 50)

    time_estimate = _hedef_suresi_hesapla(item, price, target, atr, market_regime)

    form_down = (
        str(item.get("formasyon_yonu", "")).upper() == "AŞAĞI"
        and str(item.get("formasyon_teyit", "")).lower() == "evet"
    )
    mtf_negative = "negatif" in str(item.get("mtf_uyum", "")).lower()

    if score >= 80 and probability >= 65 and evidence >= 58 and rr >= 1.5 and not form_down and not mtf_negative:
        decision = "BUGÜN AL"
    elif score >= 68 and probability >= 62 and rr >= 1.2 and not form_down:
        decision = "ALIM BÖLGESİNİ BEKLE"
    elif score >= 55:
        decision = "İZLE"
    else:
        decision = "ALMA"

    if price > buy_high * 1.025 and decision == "BUGÜN AL":
        decision = "ALIM BÖLGESİNİ BEKLE"
    if "DÜŞÜŞ" in market_regime and decision == "BUGÜN AL":
        decision = "ALIM BÖLGESİNİ BEKLE"
    if data_confidence < 60:
        decision = "VERİ KONTROLÜ GEREKLİ"
    if evidence_samples < 20 and decision in ("BUGÜN AL", "ALIM BÖLGESİNİ BEKLE"):
        decision = "İZLE - KANIT YETERSİZ"
    if not validation["onayli"] and decision in ("BUGÜN AL", "ALIM BÖLGESİNİ BEKLE"):
        decision = "İZLE - DOĞRULAMA YETERSİZ"
    if (not advanced["likidite_uygun"] or not advanced["temel_risk_uygun"]) and decision == "BUGÜN AL":
        decision = "İZLE - RİSK FİLTRESİ"
    if extraordinary["kovalama_engeli"] and decision in ("BUGÜN AL", "ALIM BÖLGESİNİ BEKLE"):
        decision = "İZLE - OLAĞANDIŞI HAREKET RİSKİ"
    if not quality["veri_kalite_onayli"]:
        decision = "VERİ KONTROLÜ GEREKLİ"
    if _f(item.get("uluslararasi_faktor_puani")) < 60 and decision == "BUGÜN AL":
        decision = "İZLE - FAKTÖR UYUMU YETERSİZ"

    reason_parts = []
    if score >= 70:
        reason_parts.append("Çok katmanlı teknik skor güçlü")
    if fib_score >= 65:
        reason_parts.append("Fibonacci görünümü destekliyor")
    if form_score >= 65:
        reason_parts.append(f"{item.get('formasyon', 'Formasyon')} sinyali")
    if mtf >= 65:
        reason_parts.append("Zaman dilimleri uyumlu")
    if rr >= 1.5:
        reason_parts.append(f"Risk/getiri yaklaşık 1:{rr:.1f}")
    if not reason_parts:
        reason_parts.append("Yeterli ortak teyit oluşmadı")

    return {
        "yatirim_karari": decision,
        "onerilen_alis_alt": round(buy_low, 2),
        "onerilen_alis_ust": round(buy_high, 2),
        "onerilen_satis": round(target, 2),
        "onerilen_stop": round(stop, 2),
        "beklenen_getiri_yuzde": round(expected_return, 2),
        **time_estimate,
        "model_olasiligi": probability,
        "karar_risk_getiri": round(rr, 2),
        "karar_nedenleri": " | ".join(reason_parts),
        "piyasa_rejimi": market_regime,
        "karar_veri_guveni": int(data_confidence),
        "karar_kanit_puani": round(evidence, 1),
        "karar_kanit_ornegi": evidence_samples,
        "dogrulanmis_olasilik": validation["dogrulanmis_olasilik"],
        "dogrulama_ornek_sayisi": validation["dogrulama_ornek_sayisi"],
        "dogrulama_notu": validation["dogrulama_notu"],
        **advanced,
        **extraordinary,
        **quality,
        "karar_uyarisi": "Tahmini teknik senaryodur; hedef, süre ve olasılık garanti değildir.",
    }


def _empty() -> Dict[str, Any]:
    return {
        "yatirim_karari": "VERİ YOK",
        "onerilen_alis_alt": 0.0,
        "onerilen_alis_ust": 0.0,
        "onerilen_satis": 0.0,
        "onerilen_stop": 0.0,
        "beklenen_getiri_yuzde": 0.0,
        "beklenen_sure": "Veri yok",
        "beklenen_sure_alt": 0,
        "beklenen_sure_ust": 0,
        "beklenen_hafta_alt": 0.0,
        "beklenen_hafta_ust": 0.0,
        "sure_tahmin_guveni": "YOK",
        "sure_tahmin_yontemi": "Veri yok",
        "model_olasiligi": 0,
        "karar_risk_getiri": 0.0,
        "karar_nedenleri": "Fiyat verisi bulunamadı.",
        "karar_uyarisi": "Tahmin üretilemedi.",
    }
