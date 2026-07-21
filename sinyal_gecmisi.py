from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd


COLUMNS = [
    "Tarama Zamanı", "Hisse", "Karar", "Giriş Fiyatı", "Alış Alt", "Alış Üst",
    "Hedef", "Stop", "Model Olasılığı %", "V4 Güven", "Piyasa Rejimi",
    "Veri Güveni", "Durum", "Son Kontrol", "Son Fiyat", "Gerçekleşen Getiri %",
]


def _path() -> Path:
    path = Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "performans" / "sinyal_gecmisi.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _num(value: Any) -> float:
    try:
        result = float(value)
        return result if pd.notna(result) else 0.0
    except Exception:
        return 0.0


def sinyal_gecmisini_guncelle(results: Iterable[Dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    now = datetime.now()
    path = _path()
    if path.exists():
        try:
            history = pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            history = pd.DataFrame(columns=COLUMNS)
    else:
        history = pd.DataFrame(columns=COLUMNS)

    current = {str(item.get("symbol", "")): item for item in results if item.get("symbol")}
    if not history.empty:
        for index, row in history[history["Durum"].eq("AÇIK")].iterrows():
            item = current.get(str(row["Hisse"]))
            if not item:
                continue
            last = _num(item.get("price"))
            entry = _num(row.get("Giriş Fiyatı"))
            target = _num(row.get("Hedef"))
            stop = _num(row.get("Stop"))
            status = "AÇIK"
            if target > 0 and last >= target:
                status = "HEDEF (KAPANIŞ)"
            elif stop > 0 and last <= stop:
                status = "STOP (KAPANIŞ)"
            history.at[index, "Durum"] = status
            history.at[index, "Son Kontrol"] = now.isoformat(timespec="minutes")
            history.at[index, "Son Fiyat"] = round(last, 2)
            history.at[index, "Gerçekleşen Getiri %"] = round((last / entry - 1) * 100, 2) if entry > 0 else 0

    today = now.strftime("%Y-%m-%d")
    existing_today = set()
    if not history.empty:
        dates = history["Tarama Zamanı"].astype(str).str[:10]
        existing_today = set(history.loc[dates.eq(today), "Hisse"].astype(str))

    rows = []
    accepted = {"BUGÜN AL", "ALIM BÖLGESİNİ BEKLE"}
    for symbol, item in current.items():
        decision = str(item.get("yatirim_karari", ""))
        if decision not in accepted or symbol in existing_today:
            continue
        rows.append({
            "Tarama Zamanı": now.isoformat(timespec="minutes"), "Hisse": symbol,
            "Karar": decision, "Giriş Fiyatı": round(_num(item.get("price")), 2),
            "Alış Alt": round(_num(item.get("onerilen_alis_alt")), 2),
            "Alış Üst": round(_num(item.get("onerilen_alis_ust")), 2),
            "Hedef": round(_num(item.get("onerilen_satis")), 2),
            "Stop": round(_num(item.get("onerilen_stop")), 2),
            "Model Olasılığı %": _num(item.get("model_olasiligi")),
            "V4 Güven": _num(item.get("v4_guven_puani")),
            "Piyasa Rejimi": item.get("piyasa_rejimi", ""),
            "Veri Güveni": _num(item.get("veri_guven_puani")),
            "Durum": "AÇIK", "Son Kontrol": now.isoformat(timespec="minutes"),
            "Son Fiyat": round(_num(item.get("price")), 2), "Gerçekleşen Getiri %": 0.0,
        })
    if rows:
        history = pd.concat([history, pd.DataFrame(rows)], ignore_index=True)
    history = history.reindex(columns=COLUMNS)
    history.to_csv(path, index=False, encoding="utf-8-sig")

    closed = history[history["Durum"].ne("AÇIK")].copy()
    summary = pd.DataFrame([{
        "Toplam Sinyal": len(history),
        "Açık": int(history["Durum"].eq("AÇIK").sum()),
        "Hedef": int(history["Durum"].astype(str).str.startswith("HEDEF").sum()),
        "Stop": int(history["Durum"].astype(str).str.startswith("STOP").sum()),
        "Kapanan Başarı %": round(closed["Durum"].astype(str).str.startswith("HEDEF").mean() * 100, 2) if len(closed) else 0,
        "Ortalama Gerçekleşen Getiri %": round(pd.to_numeric(closed["Gerçekleşen Getiri %"], errors="coerce").mean(), 2) if len(closed) else 0,
    }])
    return history, summary
