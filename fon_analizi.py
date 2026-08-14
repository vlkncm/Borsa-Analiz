from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


TEFAS_URL = "https://www.tefas.gov.tr/tr/fon-getirileri?fundType=YAT"


def _cache_path() -> Path:
    root = Path.home() / "AppData" / "Local" / "BorsaAnalizProMAX"
    root.mkdir(parents=True, exist_ok=True)
    return root / "tefas_fon_listesi.json"


def tefas_liste_verisini_ayikla(content: str) -> list[dict[str, Any]]:
    marker = 'initialFundListingData\\":'
    start = content.find(marker)
    if start < 0:
        raise ValueError("TEFAS toplu fon veri alanı bulunamadı")
    start += len(marker)
    if start >= len(content) or content[start] != "[":
        raise ValueError("TEFAS fon listesi beklenen biçimde değil")
    # Next.js uçuş verisinde JSON tırnakları ters bölü ile kaçırılmıştır. Fon
    # adının içinde ']' bulunabileceği için ilk kapanış parantezinde kesmek
    # güvenli değildir; JSON ayrıştırıcısı dizinin gerçek sonunu belirler.
    raw = content[start:].replace('\\"', '"')
    data, _end = json.JSONDecoder().raw_decode(raw)
    if not isinstance(data, list) or not data:
        raise ValueError("TEFAS boş fon listesi döndürdü")
    return data


def tefas_fonlarini_getir(timeout: int = 30) -> tuple[list[dict[str, Any]], str]:
    cache = _cache_path()
    try:
        response = requests.get(
            TEFAS_URL,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 BorsaAnalizProMAX/8.5"},
        )
        response.raise_for_status()
        data = tefas_liste_verisini_ayikla(response.text)
        cache.write_text(
            json.dumps({"time": datetime.now().isoformat(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
        return data, "TEFAS güncel fon getirileri"
    except Exception as exc:
        if cache.exists():
            cached = json.loads(cache.read_text(encoding="utf-8"))
            return cached.get("data", []), f"TEFAS önbelleği ({cached.get('time', 'tarih yok')}); güncelleme hatası: {exc}"
        raise RuntimeError(f"TEFAS verisi alınamadı: {exc}") from exc


def _number(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _monthly(total_return: float, months: int) -> float:
    if not math.isfinite(total_return) or total_return <= -100:
        return float("nan")
    return ((1 + total_return / 100) ** (1 / months) - 1) * 100


def _holding_period(fund_type: str) -> str:
    text = fund_type.casefold()
    if "para piyasası" in text:
        return "1–6 ay"
    if "borçlanma" in text:
        return "6–18 ay"
    if "kıymetli maden" in text or "altın" in text:
        return "1–3 yıl"
    if "hisse" in text or "değişken" in text or "fon sepeti" in text:
        return "en az 2–3 yıl"
    return "en az 1 yıl"


def fonlari_puanla(records: list[dict[str, Any]], max_risk: int = 7) -> pd.DataFrame:
    rows = []
    for item in records:
        if item.get("tefasDurum") is not True:
            continue
        risk = _number(item.get("riskDegeri"))
        r1, r3, r6 = (_number(item.get(key)) for key in ("getiri1a", "getiri3a", "getiri6a"))
        if not all(math.isfinite(x) for x in (risk, r1, r3, r6)) or not 1 <= risk <= max_risk:
            continue
        m3, m6 = _monthly(r3, 3), _monthly(r6, 6)
        if not math.isfinite(m3) or not math.isfinite(m6):
            continue
        rows.append({
            "Fon Kodu": str(item.get("fonKodu", "")),
            "Fon Adı": str(item.get("fonUnvan", "")),
            "Kategori": str(item.get("fonTurAciklama", "Bilinmiyor")),
            "Risk": int(risk), "1 Ay %": r1, "3 Ay %": r3, "6 Ay %": r6,
            "3A Aylık Hız %": m3, "6A Aylık Hız %": m6,
            "1 Yıl %": _number(item.get("getiri1y")),
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    category_groups = frame.groupby("Kategori")
    category_median = category_groups["3 Ay %"].transform("median")
    category_count = category_groups["Fon Kodu"].transform("count")
    relative = frame["3 Ay %"] - category_median
    p1 = category_groups["1 Ay %"].rank(pct=True)
    p3 = category_groups["3 Ay %"].rank(pct=True)
    p6 = category_groups["6 Ay %"].rank(pct=True)
    consistency = (
        (frame["1 Ay %"] > 0).astype(int)
        + (frame["3 Ay %"] > 0).astype(int)
        + (frame["6 Ay %"] > 0).astype(int)
    )
    acceleration = frame["1 Ay %"] - frame["3A Aylık Hız %"]
    chasing = (frame["1 Ay %"] >= 20) | (acceleration >= 12)
    slowing = frame["1 Ay %"] < frame["3A Aylık Hız %"] * 0.45
    score = (
        (p1 * 0.35 + p3 * 0.30 + p6 * 0.20) * 100
        + consistency * 3.0
        - (frame["Risk"] - 4).clip(lower=0) * 2
        - chasing.astype(int) * 9
        - slowing.astype(int) * 12
        - (category_count < 5).astype(int) * 8
    )
    frame["Momentum Puanı"] = score.clip(0, 100).round().astype(int)
    frame["20%+ Uç Senaryo"] = (
        (frame["1 Ay %"] >= 10) & (frame["3A Aylık Hız %"] >= 4)
        & (frame["Risk"] >= 5) & (frame["Momentum Puanı"] >= 72) & ~slowing
    ).map({True: "VAR", False: "ZAYIF"})

    decisions = []
    for idx, row in frame.iterrows():
        if chasing.loc[idx]:
            decision = "YÜKSELİŞİ KOVALAMA – GERİ ÇEKİLME BEKLE"
        elif row["20%+ Uç Senaryo"] == "VAR":
            decision = "20%+ POTANSİYEL ADAYI – ÇOK YÜKSEK RİSK"
        elif row["Momentum Puanı"] >= 80 and consistency.loc[idx] == 3 and not slowing.loc[idx] and relative.loc[idx] > 0:
            decision = "KATEGORİ LİDERİ – KADEMELİ AL"
        elif row["Momentum Puanı"] >= 68 and consistency.loc[idx] >= 2 and not slowing.loc[idx]:
            decision = "GÜÇLÜ İZLE"
        elif row["Momentum Puanı"] >= 52:
            decision = "BEKLE"
        else:
            decision = "ZAYIF – ALMA"
        decisions.append(decision)
    frame["Karar"] = decisions
    frame["Önerilen Asgari Süre"] = frame["Kategori"].map(_holding_period)
    frame["Çıkış Koşulu"] = "3 aylık kategori ortalamasının altına düşer ve momentum iki kontrolde zayıflarsa azalt"
    frame["Uyarı"] = "%20–30 getiri garanti değildir; yüksek potansiyel yüksek kayıp riski taşır"
    order = [
        "Fon Kodu", "Karar", "Momentum Puanı", "20%+ Uç Senaryo", "Risk", "1 Ay %", "3 Ay %",
        "6 Ay %", "Kategori", "Önerilen Asgari Süre", "Çıkış Koşulu", "Fon Adı", "Uyarı",
    ]
    frame["_uc_oncelik"] = frame["20%+ Uç Senaryo"].eq("VAR").astype(int)
    return frame.sort_values(
        ["_uc_oncelik", "Momentum Puanı", "3 Ay %"], ascending=False
    )[order].reset_index(drop=True)


def fon_taramasi(max_risk: int = 7) -> tuple[pd.DataFrame, str]:
    records, source = tefas_fonlarini_getir()
    return fonlari_puanla(records, max_risk=max_risk), source
