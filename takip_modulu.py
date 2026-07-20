from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf


def takip_klasoru() -> Path:
    belgeler = Path.home() / "Documents"
    if not belgeler.exists():
        belgeler = Path.home()
    klasor = belgeler / "Borsa Analiz Pro MAX"
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def takip_dosyasi() -> Path:
    return takip_klasoru() / "takip_listesi.json"


def takip_listesini_oku() -> List[str]:
    path = takip_dosyasi()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        semboller = data.get("semboller", []) if isinstance(data, dict) else data
        return sorted({
            normalize_sembol(x) for x in semboller
            if normalize_sembol(x)
        })
    except Exception:
        return []


def takip_listesini_yaz(semboller: List[str]) -> None:
    temiz = sorted({normalize_sembol(x) for x in semboller if normalize_sembol(x)})
    tmp = takip_dosyasi().with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "semboller": temiz,
                "son_kayit": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(takip_dosyasi())


def normalize_sembol(value: str) -> str:
    sembol = str(value or "").strip().upper()
    if not sembol:
        return ""
    if sembol.endswith(".IS"):
        return sembol
    if 3 <= len(sembol) <= 6 and sembol.replace("_", "").isalnum():
        return f"{sembol}.IS"
    return ""


def _tek_hisse_fiyat(sembol: str, retries: int = 3) -> Dict[str, object]:
    son_hata = ""
    for deneme in range(1, retries + 1):
        try:
            df = yf.download(
                sembol,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
                timeout=20,
            )
            if df is None or df.empty:
                raise ValueError("Fiyat verisi boş döndü.")

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Close"])
            if df.empty:
                raise ValueError("Geçerli kapanış verisi bulunamadı.")

            son = df.iloc[-1]
            onceki = df.iloc[-2] if len(df) >= 2 else son

            son_fiyat = float(son["Close"])
            onceki_kapanis = float(onceki["Close"])
            degisim = (
                ((son_fiyat - onceki_kapanis) / onceki_kapanis) * 100
                if onceki_kapanis
                else 0.0
            )

            return {
                "Hisse": sembol.replace(".IS", ""),
                "Son Fiyat": round(son_fiyat, 2),
                "Günlük Değişim %": round(degisim, 2),
                "Yüksek": round(float(son["High"]), 2),
                "Düşük": round(float(son["Low"]), 2),
                "Hacim": int(float(son["Volume"])) if pd.notna(son["Volume"]) else 0,
                "Son Güncelleme": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "Durum": "Güncel",
            }
        except Exception as exc:
            son_hata = str(exc)
            if deneme < retries:
                time.sleep(deneme * 1.25)

    return {
        "Hisse": sembol.replace(".IS", ""),
        "Son Fiyat": 0.0,
        "Günlük Değişim %": 0.0,
        "Yüksek": 0.0,
        "Düşük": 0.0,
        "Hacim": 0,
        "Son Güncelleme": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "Durum": f"Veri alınamadı: {son_hata[:80]}",
    }


def takip_fiyatlarini_getir(semboller: List[str]) -> pd.DataFrame:
    temiz = [normalize_sembol(x) for x in semboller]
    temiz = [x for x in temiz if x]
    rows = [_tek_hisse_fiyat(sembol) for sembol in temiz]

    kolonlar = [
        "Hisse",
        "Son Fiyat",
        "Günlük Değişim %",
        "Yüksek",
        "Düşük",
        "Hacim",
        "Son Güncelleme",
        "Durum",
    ]
    return pd.DataFrame(rows, columns=kolonlar)
