from __future__ import annotations

import math
from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def satis_karari_uret(item: Dict[str, Any], maliyet: float) -> Dict[str, Any]:
    """
    Kullanıcının gerçek alış maliyetine göre teknik satış senaryosu üretir.
    Kesin yatırım tavsiyesi veya getiri garantisi değildir.
    """
    price = _f(item.get("price"))
    target = _f(item.get("onerilen_satis"), _f(item.get("hedef_2"), _f(item.get("hedef_1"))))
    stop = _f(item.get("onerilen_stop"), _f(item.get("stop_loss")))
    atr = max(_f(item.get("atr"), price * 0.025), price * 0.008)
    score = _f(item.get("v4_guven_puani", item.get("broker_skor", 50)), 50)
    rsi = _f(item.get("rsi"), 50)
    fib_resistance = _f(item.get("fib_direnc"))
    form_down = (
        str(item.get("formasyon_yonu", "")).upper() == "AŞAĞI"
        and str(item.get("formasyon_teyit", "")).lower() == "evet"
    )
    mtf_negative = "negatif" in str(item.get("mtf_uyum", "")).lower()

    if price <= 0 or maliyet <= 0:
        return {
            "satis_karari": "VERİ YOK",
            "kar_zarar_yuzde": 0.0,
            "kar_zarar_tutar": 0.0,
            "hedefe_kalan_yuzde": 0.0,
            "satis_nedeni": "Geçerli fiyat veya maliyet bulunamadı.",
            "yeni_stop": 0.0,
            "kar_realizasyon_orani": 0,
            "satis_uyarisi": "Teknik senaryodur; kesin yatırım tavsiyesi değildir.",
        }

    pnl_pct = (price / maliyet - 1) * 100
    pnl_amount_per_share = price - maliyet
    target_gap = ((target / price) - 1) * 100 if target > 0 else 0.0
    target_progress = ((price - maliyet) / (target - maliyet) * 100) if target > maliyet else 0.0

    reasons = []
    decision = "TUT"
    realize = 0

    # Öncelik: zarar kes / teknik bozulma
    if stop > 0 and price <= stop:
        decision = "ACİL ÇIK"
        realize = 100
        reasons.append("Fiyat model stop seviyesinin altına indi")
    elif pnl_pct <= -8 and (score < 55 or form_down or mtf_negative):
        decision = "SAT"
        realize = 100
        reasons.append("Zarar büyürken teknik görünüm zayıfladı")
    elif form_down and score < 62:
        decision = "SAT"
        realize = 100
        reasons.append("Teyitli düşüş formasyonu oluştu")

    # Kâr alma katmanları
    elif target > 0 and price >= target:
        if score >= 78 and not form_down and not mtf_negative:
            decision = "KISMİ KÂR AL"
            realize = 50
            reasons.append("İlk hedefe ulaşıldı ancak teknik görünüm hâlâ güçlü")
        else:
            decision = "KÂR AL"
            realize = 100
            reasons.append("Model hedef fiyatına ulaşıldı")
    elif target_progress >= 90:
        decision = "KISMİ KÂR AL"
        realize = 50
        reasons.append("Hedef fiyatın en az %90'ına ulaşıldı")
    elif fib_resistance > 0 and abs(price - fib_resistance) / price <= 0.012 and rsi >= 68:
        decision = "KISMİ KÂR AL"
        realize = 50
        reasons.append("Fibonacci direncine yakın ve RSI yüksek")
    elif pnl_pct >= 15 and (rsi >= 72 or score < 65):
        decision = "KISMİ KÂR AL"
        realize = 50
        reasons.append("Kâr güçlü, momentumda yorulma riski var")
    elif pnl_pct >= 25:
        decision = "KÂR AL"
        realize = 100
        reasons.append("Yüksek kâr seviyesi oluştu")
    elif pnl_pct > 0:
        decision = "TUT"
        reasons.append("Hedefe alan var ve teknik bozulma yok")
    else:
        decision = "TUT"
        reasons.append("Stop kırılmadı; maliyet altında kontrollü izleme")

    # Kârda trailing stop: maliyetin altına düşmeyecek şekilde.
    if pnl_pct > 0:
        trailing = max(maliyet * 1.002, price - atr * 1.6)
    else:
        trailing = stop if stop > 0 else price - atr * 1.8

    if decision == "KISMİ KÂR AL":
        reasons.append(f"Pozisyonun yaklaşık %{realize}'si realize edilebilir")
    elif decision in {"KÂR AL", "SAT", "ACİL ÇIK"}:
        reasons.append("Pozisyonu kapatma senaryosu öne çıkıyor")

    return {
        "satis_karari": decision,
        "kar_zarar_yuzde": round(pnl_pct, 2),
        "kar_zarar_tutar": round(pnl_amount_per_share, 2),
        "hedefe_kalan_yuzde": round(target_gap, 2),
        "hedef_ilerleme_yuzde": round(max(0.0, target_progress), 1),
        "satis_nedeni": " | ".join(reasons),
        "yeni_stop": round(max(0.01, trailing), 2),
        "kar_realizasyon_orani": realize,
        "satis_uyarisi": (
            "Bu sonuç maliyet, güncel fiyat ve teknik göstergelere dayalı model senaryosudur; "
            "kesin yatırım tavsiyesi veya getiri garantisi değildir."
        ),
    }
