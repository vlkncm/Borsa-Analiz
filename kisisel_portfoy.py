"""Kullanıcının yerel CSV portföyünü analiz sonuçlarıyla eşleştirir.

CSV başlıkları: Hisse, Adet, Maliyet. İnternet hesabı veya aracı kurum erişimi
gerektirmez; kullanıcı dosyayı kendisi dışa aktarır veya oluşturur.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable
import pandas as pd


def portfoy_csv_oku(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    required = {"Hisse", "Adet", "Maliyet"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Portföy CSV eksik sütunlar: {', '.join(sorted(missing))}")
    frame = frame.copy()
    frame["Hisse"] = frame["Hisse"].astype(str).str.upper().str.replace(".IS", "", regex=False) + ".IS"
    for column in ("Adet", "Maliyet"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame[frame["Adet"] > 0]


def portfoyu_eslestir(portfoy: pd.DataFrame, results: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    prices = {str(item.get("symbol", "")).upper(): item for item in results}
    rows = []
    for _, position in portfoy.iterrows():
        symbol = position["Hisse"]
        item = prices.get(symbol, {})
        price = float(item.get("price", 0) or 0)
        quantity, cost = float(position["Adet"]), float(position["Maliyet"])
        rows.append({"Hisse": symbol, "Adet": quantity, "Maliyet": cost, "Güncel Fiyat": price, "Tutar": round(quantity * price, 2), "Gerçekleşmemiş Getiri %": round((price / cost - 1) * 100, 2) if price > 0 and cost > 0 else 0.0, "Önerilen Stop": item.get("onerilen_stop", 0), "Önerilen Hedef": item.get("onerilen_satis", 0), "Karar": item.get("yatirim_karari", "VERİ YOK"), "Uyarılar": item.get("canli_uyarilar", "")})
    return pd.DataFrame(rows)
