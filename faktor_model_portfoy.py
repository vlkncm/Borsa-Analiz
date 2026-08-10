"""Şeffaf BIST kalite-değer-momentum model portföyü.

Evren, taramadaki en likit 100 hisse ile sınırlıdır; bu BIST 100'ün resmi
bileşen listesinin yerine geçen bir vekil değildir, likidite filtresidir.
"""
from __future__ import annotations

from typing import Any, Iterable
import pandas as pd


def _n(value: Any) -> float:
    try:
        return float(value) if pd.notna(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def faktor_model_portfoyu(results: Iterable[dict[str, Any]], adet: int = 10) -> pd.DataFrame:
    rows = []
    for item in results:
        fk, pddd, roe = _n(item.get("fk")), _n(item.get("pddd")), _n(item.get("roe"))
        margin, debt = _n(item.get("kar_marji")), _n(item.get("borc_ozsermaye"))
        liquidity = _n(item.get("ortalama_gunluk_islem_tutari"))
        if fk <= 0 or pddd <= 0 or roe <= 0 or liquidity <= 0:
            continue
        rows.append({"Hisse": str(item.get("symbol", "")).replace(".IS", ""),
                     "Sektör": item.get("sector", "Bilinmiyor"), "F/K": fk, "PD/DD": pddd,
                     "ROE": roe, "Kâr Marjı": margin, "Borç/Özsermaye": debt,
                     "20 Günlük İşlem Tutarı": liquidity,
                     "Momentum": _n(item.get("v4_momentum_puani")),
                     "KAP Risk": str(item.get("kap_etiket", ""))})
    df = pd.DataFrame(rows)
    if len(df) < 8:
        return pd.DataFrame(columns=["Hisse", "Model Notu"])
    # En likit 100: küçük/oynak hisselerle formülün bozulmasını azaltır.
    df = df.nlargest(100, "20 Günlük İşlem Tutarı").copy()
    df["Kalite Sırası"] = (df["ROE"].rank(ascending=False, method="min") +
                            df["Kâr Marjı"].rank(ascending=False, method="min") +
                            df["Borç/Özsermaye"].rank(ascending=True, method="min"))
    df["Değer Sırası"] = (df["F/K"].rank(ascending=True, method="min") +
                           df["PD/DD"].rank(ascending=True, method="min"))
    df["Momentum Sırası"] = df["Momentum"].rank(ascending=False, method="min")
    df["Birleşik Sıra"] = df["Kalite Sırası"] * 0.45 + df["Değer Sırası"] * 0.40 + df["Momentum Sırası"] * 0.15
    df = df[~df["KAP Risk"].str.contains("olumsuz|risk", case=False, na=False)].sort_values("Birleşik Sıra")
    # Sektör yoğunluğunu sınırlayarak en fazla iki hisse seçilir.
    picked, counts = [], {}
    for _, row in df.iterrows():
        sector = str(row["Sektör"])
        if counts.get(sector, 0) >= 2:
            continue
        picked.append(row)
        counts[sector] = counts.get(sector, 0) + 1
        if len(picked) == adet:
            break
    out = pd.DataFrame(picked)
    if out.empty:
        return out
    out["Portföy Ağırlığı %"] = round(100 / len(out), 2)
    out["Model Notu"] = "Kalite + değer + momentum; aylık/bilanço dönemi gözden geçir. Yatırım garantisi değildir."
    return out.reset_index(drop=True)
