"""Canli sinyallerin ölçümü, risk kapıları ve uyarıları.

Bu fonksiyonlar tahmin garantisi vermez. Belirsizliği görünür kılar, yetersiz
veriyi eler ve sonuçların sonradan ölçülebilmesini sağlar.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List

import pandas as pd


def _f(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def likidite_degerlendir(fiyat: float, ortalama_hacim: float) -> Dict[str, Any]:
    """20 günlük ortalama işlem tutarıyla likidite riskini sınıflandırır."""
    tutar = max(0.0, _f(fiyat) * _f(ortalama_hacim))
    if tutar >= 20_000_000:
        seviye, uygun = "YÜKSEK", True
    elif tutar >= 5_000_000:
        seviye, uygun = "ORTA", True
    else:
        seviye, uygun = "DÜŞÜK", False
    return {"ortalama_gunluk_islem_tutari": round(tutar, 2), "likidite_seviyesi": seviye, "likidite_uygun": uygun}


def hedef_araligi(fiyat: float, atr: float, hedef: float, gun: int = 20) -> Dict[str, Any]:
    """Tek hedef yerine ATR tabanlı ihtiyatlı fiyat aralığı verir."""
    fiyat, atr, hedef = _f(fiyat), max(0.0, _f(atr)), _f(hedef)
    if fiyat <= 0 or atr <= 0:
        return {"hedef_alt_bant": 0.0, "hedef_merkez": round(hedef, 2), "hedef_ust_bant": 0.0, "bant_notu": "ATR verisi yetersiz"}
    hareket = atr * math.sqrt(max(1, gun)) * 0.75
    merkez = hedef if hedef > 0 else fiyat
    return {"hedef_alt_bant": round(max(0.01, merkez - hareket), 2), "hedef_merkez": round(merkez, 2), "hedef_ust_bant": round(merkez + hareket, 2), "bant_notu": f"{gun} iş günü için ATR-temelli olasılık bandı; fiyat hedefi değildir."}


def temel_risk_degerlendir(item: Dict[str, Any]) -> Dict[str, Any]:
    risks: List[str] = []
    if _f(item.get("borc_ozsermaye")) > 250:
        risks.append("yüksek borçluluk")
    if _f(item.get("kar_marji")) < 0:
        risks.append("negatif kâr marjı")
    if _f(item.get("kar_buyume")) < -0.05:
        risks.append("negatif kâr büyümesi")
    if _f(item.get("kap_skor")) < -10:
        risks.append("olumsuz KAP sinyali")
    return {"temel_risk_uygun": not risks, "temel_risk_notu": " | ".join(risks) if risks else "Belirgin temel risk filtresi yok"}


def uyari_uret(item: Dict[str, Any]) -> List[str]:
    price = _f(item.get("price"))
    stop = _f(item.get("onerilen_stop", item.get("stop_loss")))
    target = _f(item.get("onerilen_satis", item.get("hedef_1")))
    alerts: List[str] = []
    if _f(item.get("veri_islem_gunu_gecikmesi")) > 0 or _f(item.get("veri_yasi_gun")) > 1:
        alerts.append("Fiyat verisi güncel değil")
    if stop > 0 and price <= stop * 1.02:
        alerts.append("Stop seviyesine yakın")
    if target > 0 and price >= target * 0.98:
        alerts.append("Hedef seviyesine yakın")
    if not bool(item.get("likidite_uygun", True)):
        alerts.append("Likidite yetersiz; kayma riski yüksek")
    regime = str(item.get("piyasa_rejimi", "")).upper()
    if "DÜŞ" in regime or "NEGATİF" in regime:
        alerts.append("Piyasa rejimi olumsuz")
    if _f(item.get("kap_skor")) < -10:
        alerts.append("Olumsuz KAP/haber etkisi")
    return alerts


def gelismis_sinyal_degerlendir(item: Dict[str, Any]) -> Dict[str, Any]:
    """Likidite, temel risk, hedef bandı ve canlı uyarıları birleştirir."""
    liquidity = likidite_degerlendir(item.get("price"), item.get("ortalama_hacim_20"))
    fundamentals = temel_risk_degerlendir(item)
    band = hedef_araligi(item.get("price"), item.get("atr"), item.get("onerilen_satis", item.get("hedef_1")))
    merged = {**item, **liquidity, **fundamentals, **band}
    alerts = uyari_uret(merged)
    return {**liquidity, **fundamentals, **band, "canli_uyarilar": " | ".join(alerts), "canli_uyari_sayisi": len(alerts)}


def yuruyen_donem_raporu(df: pd.DataFrame, holding_days: int = 20, min_train: int = 120) -> Dict[str, Any]:
    """Geleceğe bakmadan yürüyen dönem teknik sinyal ölçümü yapar."""
    if df is None or len(df) < min_train + holding_days or "Close" not in df:
        return {"walk_forward_islem": 0, "walk_forward_basari": 0.0, "walk_forward_ortalama_getiri": 0.0, "walk_forward_not": "Yeterli tarihsel veri yok"}
    work = df.copy().dropna(subset=["Close"])
    work["EMA20"] = work["Close"].ewm(span=20, adjust=False).mean()
    work["EMA50"] = work["Close"].ewm(span=50, adjust=False).mean()
    delta = work["Close"].diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    rs = gain.ewm(alpha=1 / 14, adjust=False).mean() / loss.ewm(alpha=1 / 14, adjust=False).mean().replace(0, math.nan)
    work["RSI"] = (100 - 100 / (1 + rs)).fillna(50)
    returns = []
    for i in range(min_train, len(work) - holding_days):
        row = work.iloc[i]
        if row["Close"] > row["EMA20"] > row["EMA50"] and 45 <= row["RSI"] <= 68:
            returns.append((float(work.iloc[i + holding_days]["Close"]) / float(row["Close"]) - 1) * 100)
    return {"walk_forward_islem": len(returns), "walk_forward_basari": round(sum(x > 0 for x in returns) / len(returns) * 100, 2) if returns else 0.0, "walk_forward_ortalama_getiri": round(sum(returns) / len(returns), 2) if returns else 0.0, "walk_forward_not": "Sonraki dönem sonuçlarıyla, ileriye bakış olmadan ölçüldü"}


def portfoy_risk_ozeti(positions: Iterable[Dict[str, Any]], capital: float) -> Dict[str, Any]:
    """Toplam açık riskin sermayenin %5'ini aşmamasını denetler."""
    capital = max(0.0, _f(capital))
    risk = sum(max(0.0, _f(p.get("Maksimum Zarar", p.get("maksimum_zarar")))) for p in positions)
    percent = risk / capital * 100 if capital else 0.0
    return {"toplam_acik_risk": round(risk, 2), "toplam_acik_risk_yuzde": round(percent, 2), "portfoy_risk_uygun": percent <= 5.0, "portfoy_risk_notu": "Toplam açık risk %5 sınırında" if percent <= 5 else "Toplam açık risk %5 sınırını aşıyor"}
