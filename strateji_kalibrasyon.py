"""Rejim seçimi, maliyet varsayımı, olasılık kalibrasyonu ve portföy çeşitliliği."""
from __future__ import annotations

from typing import Any, Dict, Iterable
import math
import pandas as pd


def _f(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def strateji_sec(item: Dict[str, Any]) -> Dict[str, str]:
    regime = str(item.get("piyasa_rejimi", "")).upper()
    adx, atr_pct = _f(item.get("adx")), _f(item.get("atr")) / max(_f(item.get("price"), 1), 0.01) * 100
    if "DÜŞ" in regime or "NEGATİF" in regime:
        return {"strateji": "SAVUNMACI", "strateji_notu": "Olumsuz piyasa rejiminde yeni alım yerine risk azaltma"}
    if atr_pct >= 4:
        return {"strateji": "YÜKSEK VOLATİLİTE", "strateji_notu": "Daha küçük pozisyon ve daha geniş belirsizlik bandı"}
    if adx >= 25:
        return {"strateji": "TREND TAKİBİ", "strateji_notu": "Trend devamı koşulları değerlendiriliyor"}
    return {"strateji": "YATAY PİYASA", "strateji_notu": "Destek/direnç yakınında teyit beklenir"}


def maliyet_simulasyonu(fiyat: float, adet: int, gunluk_islem_tutari: float, komisyon_bps: float = 10) -> Dict[str, float]:
    """Likiditesi düşük hissede kaymayı artıran muhafazakar maliyet hesabı."""
    tutar = max(0.0, _f(fiyat) * max(0, int(adet)))
    adv = max(0.0, _f(gunluk_islem_tutari))
    participation = tutar / adv if adv else 1.0
    kayma_bps = min(150.0, 5.0 + participation * 500.0)
    toplam_bps = max(0.0, _f(komisyon_bps, 10)) * 2 + kayma_bps * 2
    return {"islem_tutari": round(tutar, 2), "tahmini_kayma_bps": round(kayma_bps, 1), "toplam_maliyet_bps": round(toplam_bps, 1), "tahmini_toplam_maliyet": round(tutar * toplam_bps / 10_000, 2)}


def olasilik_kalibrasyonu(history: pd.DataFrame) -> pd.DataFrame:
    """Tahmin edilen olasılık ile gerçekleşen hedef başarısını dilim bazında karşılaştırır."""
    columns = ["Olasılık Dilimi", "Kapanan Sinyal", "Tahmin Ort. %", "Gerçekleşen Hedef %", "Kalibrasyon Farkı %"]
    if history is None or history.empty or "Model Olasılığı %" not in history:
        return pd.DataFrame(columns=columns)
    work = history.copy()
    work = work[work.get("Durum", "").astype(str).str.contains("HEDEF|STOP", regex=True, na=False)]
    if work.empty:
        return pd.DataFrame(columns=columns)
    work["Tahmin"] = pd.to_numeric(work["Model Olasılığı %"], errors="coerce")
    work["Başarı"] = work["Durum"].astype(str).str.startswith("HEDEF").astype(float) * 100
    work = work.dropna(subset=["Tahmin"])
    work["Olasılık Dilimi"] = pd.cut(work["Tahmin"], bins=[0, 45, 55, 65, 75, 100], labels=["0-45", "46-55", "56-65", "66-75", "76-100"], include_lowest=True)
    result = work.groupby("Olasılık Dilimi", observed=False).agg(**{"Kapanan Sinyal": ("Başarı", "count"), "Tahmin Ort. %": ("Tahmin", "mean"), "Gerçekleşen Hedef %": ("Başarı", "mean")}).reset_index()
    result["Kalibrasyon Farkı %"] = result["Gerçekleşen Hedef %"] - result["Tahmin Ort. %"]
    return result.round(2)


def korelasyon_ve_sektor_kontrolu(returns: pd.DataFrame, positions: Iterable[Dict[str, Any]], max_same_sector: int = 2) -> Dict[str, Any]:
    """Sektör yoğunlaşması ve mevcut fiyat serilerinden en yüksek korelasyonu raporlar."""
    positions = list(positions)
    sectors: Dict[str, int] = {}
    for position in positions:
        sector = str(position.get("sektor", position.get("Sektör", "Bilinmiyor")))
        sectors[sector] = sectors.get(sector, 0) + 1
    concentrated = [sector for sector, count in sectors.items() if sector != "Bilinmiyor" and count > max_same_sector]
    highest = 0.0
    pair = ""
    if returns is not None and not returns.empty and returns.shape[1] >= 2:
        corr = returns.corr().abs()
        for column in corr.columns:
            corr.loc[column, column] = 0
        highest = float(corr.max().max())
        if highest > 0:
            loc = corr.stack().idxmax()
            pair = f"{loc[0]} / {loc[1]}"
    return {"sektor_yogunlasmasi": " | ".join(concentrated), "sektor_uygun": not concentrated, "en_yuksek_korelasyon": round(highest, 3), "en_korelasyonlu_cift": pair, "korelasyon_uyari": "Yüksek korelasyon portföy riskini artırabilir" if highest >= 0.75 else "Belirgin korelasyon uyarısı yok"}
