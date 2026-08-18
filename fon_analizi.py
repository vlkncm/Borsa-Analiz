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
TEFAS_DETAIL_URL = "https://www.tefas.gov.tr/tr/fon-detayli-analiz/{code}"


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


def _embedded_object(content: str, marker: str) -> dict[str, Any]:
    start = content.find(marker)
    if start < 0:
        raise ValueError(f"TEFAS {marker} alanı bulunamadı")
    start += len(marker)
    raw = content[start:].replace('\\"', '"')
    data, _end = json.JSONDecoder().raw_decode(raw)
    if not isinstance(data, dict):
        raise ValueError(f"TEFAS {marker} alanı beklenen biçimde değil")
    return data


def tefas_fon_detayi(code: str, timeout: int = 30) -> dict[str, Any]:
    code = re.sub(r"[^A-Z0-9]", "", str(code).upper())
    response = requests.get(
        TEFAS_DETAIL_URL.format(code=code), timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 BorsaAnalizProMAX/8.6"},
    )
    response.raise_for_status()
    content = response.text
    bilgi = _embedded_object(content, 'bilgiData\\":')
    profil = _embedded_object(content, 'profilData\\":')
    return {**bilgi, **profil}


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


def fon_kurumunu_bul(detail: dict[str, Any], fund_name: str = "") -> str:
    """TEFAS detayındaki kurucu/yönetici kurum adını şema değişikliklerine dayanıklı bulur."""
    preferred = (
        "kurucuUnvan", "kurucuAdi", "kurucu", "fonKurucuUnvan",
        "yoneticiUnvan", "yoneticiAdi", "portfoyYonetimSirketi",
    )
    for key in preferred:
        value = detail.get(key)
        if value and str(value).strip():
            return str(value).strip()
    for key, value in detail.items():
        folded = str(key).casefold()
        if value and any(token in folded for token in ("kurucu", "yonetici", "yönetici", "portfoy", "portföy")):
            return str(value).strip()
    # Detay servisi kurum alanı döndürmezse fon unvanı tahmin olarak etiketlenmez.
    return "TEFAS detayında kurum bilgisi yok"


def en_iyi_fonlari_sec(max_risk: int = 7, sermaye: float = 0, adet: int = 3) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    """2-3 aylık ufuk için en fazla üç risk-ayarlı adayı ve ölçülebilir planı üretir."""
    frame, source = fon_taramasi(max_risk=max_risk)
    if frame.empty:
        return frame, source, {"uygun": False, "fonlar": [], "rapor": "ALIMA UYGUN FON BULUNAMADI."}

    candidates = frame[
        frame["Karar"].isin([
            "20%+ POTANSİYEL ADAYI – ÇOK YÜKSEK RİSK",
            "KATEGORİ LİDERİ – KADEMELİ AL",
            "GÜÇLÜ İZLE",
        ])
        & (frame["Momentum Puanı"] >= 68)
        & (frame["1 Ay %"] > 0) & (frame["3 Ay %"] > 0) & (frame["6 Ay %"] > 0)
    ].copy()
    if candidates.empty:
        return frame, source, {
            "uygun": False, "fonlar": [],
            "rapor": "BU TARAMADA 2-3 AYLIK UFUK İÇİN YETERLİ ORTAK TEYİT YOK. ZORLA ALIM ÖNERİLMEDİ.",
        }

    candidates["Risk Ayarlı Puan"] = (
        candidates["Momentum Puanı"] - candidates["Risk"] * 1.5
        + candidates["3 Ay %"].clip(-30, 60) * 0.08
    )
    winners = candidates.sort_values(
        ["Risk Ayarlı Puan", "3 Ay %", "6 Ay %"], ascending=False
    ).head(max(1, min(int(adet), 3)))
    capital = max(0.0, _number(sermaye))
    allocation = capital / len(winners) if len(winners) else 0.0
    reports, selected = [], []

    for rank, (_, winner) in enumerate(winners.iterrows(), start=1):
        detail_error = ""
        try:
            detail = tefas_fon_detayi(winner["Fon Kodu"])
        except Exception as exc:
            detail, detail_error = {}, str(exc)
        price = _number(detail.get("sonFiyat"))
        m1 = float(winner["1 Ay %"])
        m3 = _monthly(float(winner["3 Ay %"]), 3)
        m6 = _monthly(float(winner["6 Ay %"]), 6)
        monthly = max(-8.0, min(12.0, m1 * 0.20 + m3 * 0.50 + m6 * 0.30))
        target_2 = price * ((1 + monthly / 100) ** 2) if math.isfinite(price) else float("nan")
        target_3 = price * ((1 + monthly / 100) ** 3) if math.isfinite(price) else float("nan")
        downside_pct = min(20.0, max(4.0, float(winner["Risk"]) * 2.5))
        stop = price * (1 - downside_pct / 100) if math.isfinite(price) else float("nan")
        institution = fon_kurumunu_bul(detail, winner["Fon Adı"])
        availability = (
            "TEFAS'ta işlem görüyor; kesin banka/kanal erişimi yatırım hesabından kontrol edilmeli"
        )
        price_text = f"{price:.6f} TL" if math.isfinite(price) else "alınamadı"
        target_text = (
            f"2 ay {target_2:.6f} TL | 3 ay {target_3:.6f} TL | risk eşiği {stop:.6f} TL"
            if math.isfinite(price) else "fiyat olmadığı için üretilemedi"
        )
        reports.append("\n".join([
            f"{rank}. ADAY: {winner['Fon Kodu']} — {winner['Fon Adı']}",
            f"Kurucu/yönetici kurum: {institution}",
            f"Alım kanalı: {availability}",
            f"Karar: {winner['Karar']} | Risk ayarlı puan: {winner['Risk Ayarlı Puan']:.1f}/100 | Risk: {winner['Risk']}/7",
            f"Güncel pay fiyatı / alış referansı: {price_text}",
            f"2-3 aylık model hedefi: {target_text}",
            f"Geçmiş getiri: 1 ay %{m1:.2f} | 3 ay %{winner['3 Ay %']:.2f} | 6 ay %{winner['6 Ay %']:.2f}",
            f"Ayrılan tutar: {allocation:,.2f} TL; %40 şimdi, %30 7 gün ve %30 14 gün sonra yalnızca sinyal korunursa",
            f"Çıkış/azaltma: {winner['Çıkış Koşulu']}",
            f"Alış valörü: T+{detail.get('fonSatisValor', '?')} | Satış valörü: T+{detail.get('fonGeriAlisValor', '?')}",
            f"Detay notu: {detail_error}" if detail_error else "Kaynak: TEFAS fon ve profil verileri",
        ]))
        selected.append({"fon": winner["Fon Kodu"], "kurum": institution})

    header = (
        "2-3 AYLIK UFUK İÇİN EN GÜÇLÜ MODEL ADAYLARI\n"
        "Hedefler garanti veya satış emri değil; geçmiş momentumdan türetilen koşullu senaryolardır.\n"
        "TEFAS işlem durumu, fonun yalnızca kurucu bankadan alınacağı anlamına gelmez.\n"
    )
    return frame, source, {"uygun": True, "fonlar": selected, "rapor": header + "\n\n".join(reports)}


def tek_fon_secimi(max_risk: int = 7, sermaye: float = 0) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    frame, source = fon_taramasi(max_risk=max_risk)
    if frame.empty:
        return frame, source, {"uygun": False, "rapor": "ALIMA UYGUN FON BULUNAMADI."}
    eligible = frame[
        frame["Karar"].isin([
            "20%+ POTANSİYEL ADAYI – ÇOK YÜKSEK RİSK",
            "KATEGORİ LİDERİ – KADEMELİ AL",
        ])
        & (frame["Momentum Puanı"] >= 82)
        & (frame["1 Ay %"] > 0) & (frame["3 Ay %"] > 0) & (frame["6 Ay %"] > 0)
    ].copy()
    if eligible.empty:
        return frame, source, {
            "uygun": False,
            "rapor": "BU TARAMADA TEK FON İÇİN YETERLİ ORTAK TEYİT YOK. ZORLA ALIM ÖNERİLMEDİ.",
        }
    eligible["Risk Ayarlı Puan"] = eligible["Momentum Puanı"] - eligible["Risk"] * 1.5
    winner = eligible.sort_values(["Risk Ayarlı Puan", "3 Ay %"], ascending=False).iloc[0]
    detail_error = ""
    try:
        detail = tefas_fon_detayi(winner["Fon Kodu"])
    except Exception as exc:
        detail, detail_error = {}, str(exc)
    price = _number(detail.get("sonFiyat"))
    m1 = float(winner["1 Ay %"])
    m3 = _monthly(float(winner["3 Ay %"]), 3)
    m6 = _monthly(float(winner["6 Ay %"]), 6)
    base_monthly = max(0.0, min(12.0, m1 * 0.25 + m3 * 0.45 + m6 * 0.30))
    horizon = 3
    downside_pct = min(20.0, max(4.0, float(winner["Risk"]) * 2.5))
    base_price = price * ((1 + base_monthly / 100) ** horizon) if math.isfinite(price) else float("nan")
    optimistic_monthly = min(18.0, max(base_monthly * 1.25, max(m1, m3, m6) * 0.80))
    optimistic_price = price * ((1 + optimistic_monthly / 100) ** horizon) if math.isfinite(price) else float("nan")
    downside_price = price * (1 - downside_pct / 100) if math.isfinite(price) else float("nan")
    capital = max(0.0, _number(sermaye))
    tranches = (capital * 0.40, capital * 0.30, capital * 0.30)
    money_risk = capital * downside_pct / 100
    price_text = f"{price:.6f} TL" if math.isfinite(price) else "TEFAS detayından alınamadı"
    scenario_text = (
        f"Olumsuz: {downside_price:.6f} TL | 3 aylık temel: {base_price:.6f} TL | "
        f"iyimser: {optimistic_price:.6f} TL"
        if math.isfinite(price) else "Fiyat verisi olmadığı için fiyat senaryosu üretilmedi"
    )
    report = "\n".join([
        "MODELİN TEK FON ADAYI",
        f"Fon: {winner['Fon Kodu']} — {winner['Fon Adı']}",
        f"Karar: {winner['Karar']}",
        f"Risk ayarlı puan: {winner['Risk Ayarlı Puan']:.1f}/100 | Resmî risk değeri: {winner['Risk']}/7",
        f"Güncel TEFAS pay fiyatı: {price_text}",
        f"Geçmiş getiri: 1 ay %{m1:.2f} | 3 ay %{winner['3 Ay %']:.2f} | 6 ay %{winner['6 Ay %']:.2f}",
        f"Önerilen asgari tutma süresi: {winner['Önerilen Asgari Süre']}",
        f"Model değerlendirme ufku: {horizon} ay",
        f"Fiyat senaryosu: {scenario_text}",
        f"Olumsuz senaryo kaybı: yaklaşık %{downside_pct:.1f}",
        "",
        "KADEMELİ ALIM PLANI",
        f"1. kademe şimdi: {tranches[0]:,.2f} TL (%40)",
        f"2. kademe 7 gün sonra, karar korunursa: {tranches[1]:,.2f} TL (%30)",
        f"3. kademe 14 gün sonra, kategori liderliği sürerse: {tranches[2]:,.2f} TL (%30)",
        f"Olumsuz senaryoda yaklaşık parasal risk: {money_risk:,.2f} TL",
        "",
        f"SATIŞ/AZALTMA KOŞULU: {winner['Çıkış Koşulu']}",
        f"Alış valörü: T+{detail.get('fonSatisValor', '?')} | Satış valörü: T+{detail.get('fonGeriAlisValor', '?')}",
        "",
        "Bu sonuç banka emri değildir. Fiyatlar tahmin değil, geçmiş momentumdan üretilen stres senaryolarıdır.",
        "Hiçbir fon veya formül kazanç garantisi vermez; zarar olasılığı sermaye planında gösterilmiştir.",
        f"Detay veri notu: {detail_error}" if detail_error else "Kaynak: TEFAS güncel fon ve profil verileri",
    ])
    return frame, source, {"uygun": True, "fon": winner["Fon Kodu"], "rapor": report}
