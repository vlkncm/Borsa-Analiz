"""Günde iki kontrollü tarama için karar planı üretir; canlı fiyat iddiası taşımaz."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pandas as pd


def _num(value: Any) -> float:
    try:
        return float(value) if pd.notna(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def gun_sonu_plani(results: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Kapanış sonrası bakılacak adayları, risk sınırlarıyla birlikte verir."""
    rows = []
    for item in results:
        decision = str(item.get("yatirim_karari", ""))
        if decision not in {"BUGÜN AL", "ALIM BÖLGESİNİ BEKLE", "İZLE"}:
            continue
        price = _num(item.get("price"))
        low, high = _num(item.get("onerilen_alis_alt")), _num(item.get("onerilen_alis_ust"))
        target, stop = _num(item.get("onerilen_satis")), _num(item.get("onerilen_stop"))
        if price <= 0:
            continue
        rows.append({
            "Hisse": str(item.get("symbol", "")).replace(".IS", ""),
            "Kapanış Fiyatı": round(price, 2), "Karar": decision,
            "Alış Alt": round(low, 2), "Alış Üst": round(high, 2),
            "Hedef": round(target, 2), "Stop": round(stop, 2),
            "Model Olasılığı %": round(_num(item.get("model_olasiligi")), 1),
            "Risk/Getiri": round(_num(item.get("karar_risk_getiri")), 2),
            "KAP/Risk Notu": str(item.get("karar_uyarisi", item.get("canli_uyarilar", ""))),
            "Akşam Eylemi": "KAP ve rapor notunu kontrol et; emri ancak sabah fiyat kontrolünden sonra değerlendir.",
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["Model Olasılığı %", "Risk/Getiri"], ascending=False).head(25)


def sabah_fiyat_kontrolu(plan: pd.DataFrame, fiyatlar: dict[str, float]) -> pd.DataFrame:
    """Kullanıcının aracı kurumdan gördüğü son fiyatla planı karşılaştırır."""
    rows = []
    for _, row in plan.iterrows():
        symbol = str(row["Hisse"])
        current = _num(fiyatlar.get(symbol, 0))
        low, high, stop = _num(row["Alış Alt"]), _num(row["Alış Üst"]), _num(row["Stop"])
        if current <= 0:
            status = "SON FİYAT GİRİLMEDİ — işlem yapma"
        elif stop > 0 and current <= stop:
            status = "STOP ALTINDA — yeni alım yapma"
        elif low <= current <= high:
            status = "ALIŞ BANDINDA — diğer risk kontrollerini doğrula"
        elif current > high:
            status = "ALIŞ BANDI ÜSTÜNDE — fiyat kovalanmamalı"
        else:
            status = "ALIŞ BANDI ALTINDA — yeniden teknik teyit bekle"
        rows.append({**row.to_dict(), "Sabah Son Fiyat": round(current, 2), "Sabah Kararı": status,
                     "Kontrol Zamanı": datetime.now().isoformat(timespec="minutes")})
    return pd.DataFrame(rows)
