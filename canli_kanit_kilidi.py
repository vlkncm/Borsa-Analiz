"""Canlı sonuçla kanıtlanmamış stratejiler için otomatik işlem kilidi.

Bu modül bir kazanç tahmini değildir. Yeterli sayıda kapanmış, maliyet sonrası
pozitif sinyal yoksa alım senaryolarını izleme durumuna düşürür.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple
import pandas as pd


ALIM_KARARLARI = {"BUGÜN AL", "ALIM BÖLGESİNİ BEKLE"}


def strateji_performansi(history: pd.DataFrame, strategy: str, min_islem: int = 30, maliyet_yuzde: float = 0.35) -> Dict[str, Any]:
    columns = {"Kapanan İşlem": 0, "Hedef Başarı %": 0.0, "Net Ortalama Getiri %": 0.0, "En Kötü Net Getiri %": 0.0}
    if history is None or history.empty:
        return {**columns, "Strateji": strategy, "Canlı Kanıt Durumu": "KANIT TOPLANIYOR", "Strateji Aktif": False, "Kilit Nedeni": f"En az {min_islem} kapanmış işlem gerekli"}
    work = history.copy()
    if "Strateji" in work:
        work = work[work["Strateji"].fillna("GENEL").eq(strategy)]
    if "Durum" not in work:
        work = work.iloc[0:0]
    else:
        work = work[work["Durum"].astype(str).str.contains("HEDEF|STOP|SÜRE SONU|SURE SONU", regex=True, na=False)]
    if work.empty:
        return {**columns, "Strateji": strategy, "Canlı Kanıt Durumu": "KANIT TOPLANIYOR", "Strateji Aktif": False, "Kilit Nedeni": f"{strategy} için kapanmış işlem yok"}
    net = pd.to_numeric(work.get("Gerçekleşen Getiri %", 0), errors="coerce").fillna(0) - maliyet_yuzde
    target_rate = work["Durum"].astype(str).str.startswith("HEDEF").mean() * 100
    result = {"Strateji": strategy, "Kapanan İşlem": len(work), "Hedef Başarı %": round(target_rate, 2), "Net Ortalama Getiri %": round(float(net.mean()), 2), "En Kötü Net Getiri %": round(float(net.min()), 2)}
    approved = len(work) >= min_islem and target_rate >= 52 and float(net.mean()) > 0 and float(net.min()) >= -12
    result.update({"Canlı Kanıt Durumu": "AKTİF" if approved else "KANIT YETERSİZ", "Strateji Aktif": approved, "Kilit Nedeni": "Maliyet sonrası canlı performans eşiği geçildi" if approved else "İşlem sayısı, başarı, net getiri veya düşüş eşiği yetersiz"})
    return result


def strateji_kilidi_uygula(results: Iterable[Dict[str, Any]], history: pd.DataFrame) -> Tuple[list[Dict[str, Any]], pd.DataFrame]:
    updated, reports = [], []
    cache: Dict[str, Dict[str, Any]] = {}
    for source in results:
        item = dict(source)
        strategy = str(item.get("strateji", "GENEL"))
        report = cache.setdefault(strategy, strateji_performansi(history, strategy))
        reports.append(report)
        item.update({"canli_kanit_durumu": report["Canlı Kanıt Durumu"], "canli_kanit_islem": report["Kapanan İşlem"], "canli_kanit_net_getiri": report["Net Ortalama Getiri %"], "canli_kanit_kilit_nedeni": report["Kilit Nedeni"]})
        if item.get("yatirim_karari") in ALIM_KARARLARI and not report["Strateji Aktif"]:
            item["yatirim_karari"] = "İZLE - CANLI KANIT YETERSİZ"
        updated.append(item)
    return updated, pd.DataFrame(reports).drop_duplicates() if reports else pd.DataFrame()
