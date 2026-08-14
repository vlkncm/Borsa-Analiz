from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from bist30 import normalize_bist_sembolu
from pro_moduller import temel_analiz_yfinance
from veri_saglayici import veri as yf


def _sayi(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if pd.notna(number) else default
    except (TypeError, ValueError):
        return default


def _yuzde(value: Any) -> str:
    number = _sayi(value)
    return "Veri yok" if number == 0 else f"%{number * 100:.1f}"


def _oran(value: Any) -> str:
    number = _sayi(value)
    return "Veri yok" if number == 0 else f"{number:.2f}"


def _para(value: Any) -> str:
    number = _sayi(value)
    if number == 0:
        return "Veri yok"
    for divisor, suffix in ((1e12, "trilyon"), (1e9, "milyar"), (1e6, "milyon")):
        if abs(number) >= divisor:
            return f"{number / divisor:.2f} {suffix}"
    return f"{number:,.0f}"


def _satir_bul(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    for name in names:
        if name in frame.index:
            return pd.to_numeric(frame.loc[name], errors="coerce").dropna().sort_index()
    return pd.Series(dtype=float)


def _egilim(series: pd.Series, label: str) -> str:
    if len(series) < 2:
        return f"{label}: karşılaştırma için yeterli dönem yok"
    old, new = _sayi(series.iloc[0]), _sayi(series.iloc[-1])
    if old == 0:
        return f"{label}: dönemsel değişim hesaplanamadı"
    change = (new / abs(old) - 1) * 100
    direction = "arttı" if change > 3 else "azaldı" if change < -3 else "yatay kaldı"
    return f"{label}: {len(series)} raporlama döneminde %{abs(change):.1f} {direction}"


def sirket_arastirmasi(symbol: str) -> dict[str, Any]:
    """Kaynaklı temel araştırma özeti üretir; işlem kararını veya skoru değiştirmez."""
    symbol = normalize_bist_sembolu(symbol)
    ticker = yf.Ticker(symbol)
    temel = temel_analiz_yfinance(symbol)

    try:
        financials = ticker.financials
    except Exception:
        financials = pd.DataFrame()
    try:
        cashflow = ticker.cashflow
    except Exception:
        cashflow = pd.DataFrame()
    try:
        balance = ticker.balance_sheet
    except Exception:
        balance = pd.DataFrame()

    revenue = _satir_bul(financials, ("Total Revenue", "Operating Revenue"))
    net_income = _satir_bul(financials, ("Net Income", "Net Income Common Stockholders"))
    operating_income = _satir_bul(financials, ("Operating Income",))
    free_cashflow = _satir_bul(cashflow, ("Free Cash Flow",))
    debt = _satir_bul(balance, ("Total Debt",))

    score = int(_sayi(temel.get("temel_puan"), 50))
    risks = [x.strip() for x in str(temel.get("temel_risk", "")).split("|") if x.strip()]
    strengths = [x.strip() for x in str(temel.get("temel_not", "")).split("|") if x.strip()]
    strengths = strengths or ["Doğrulanmış güçlü yön üretmek için yeterli temel veri yok"]
    risks = risks or ["Kaynak verinin eksik olma ve gecikme riski"]

    if score >= 65:
        view = "Temel göstergeler olumlu, ancak fiyat ve risk teyidi gerekli."
    elif score <= 40:
        view = "Temel göstergeler zayıf; riskler giderilmeden temkinli yaklaşılmalı."
    else:
        view = "Temel görünüm karışık/nötr; kesin yön için daha fazla doğrulanmış veri gerekli."

    data_points = sum(bool(_sayi(temel.get(key))) for key in (
        "fk", "ileri_fk", "pddd", "borc_ozsermaye", "roe", "kar_marji", "ciro_buyume", "kar_buyume"
    ))
    statement_points = sum(not series.empty for series in (revenue, net_income, operating_income, free_cashflow, debt))
    completeness = round((data_points + statement_points) / 13 * 100)

    lines = [
        f"{symbol.replace('.IS', '')} — DOĞRULANMIŞ ŞİRKET ARAŞTIRMASI",
        f"Oluşturma zamanı: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"Veri kapsamı: %{completeness} | Kaynak: Yahoo Finance finansal tabloları ve oranları", "",
        "1. TEMEL GÖRÜNÜM", f"Temel puan: {score}/100 — {view}",
        f"Sektör: {temel.get('sector', 'Bilinmiyor')}", f"Piyasa değeri: {_para(temel.get('piyasa_degeri'))}", "",
        "2. DEĞERLEME VE KALİTE",
        f"F/K: {_oran(temel.get('fk'))} | İleri F/K: {_oran(temel.get('ileri_fk'))} | PD/DD: {_oran(temel.get('pddd'))}",
        f"ROE: {_yuzde(temel.get('roe'))} | Kâr marjı: {_yuzde(temel.get('kar_marji'))}",
        f"Ciro büyümesi: {_yuzde(temel.get('ciro_buyume'))} | Kâr büyümesi: {_yuzde(temel.get('kar_buyume'))}",
        f"Borç/özsermaye: {_oran(temel.get('borc_ozsermaye'))} | Temettü verimi: {_yuzde(temel.get('temettu_verimi'))}", "",
        "3. FİNANSAL TABLO EĞİLİMLERİ", _egilim(revenue, "Ciro"), _egilim(net_income, "Net kâr"),
        _egilim(operating_income, "Faaliyet kârı"), _egilim(free_cashflow, "Serbest nakit akışı"), _egilim(debt, "Toplam borç"), "",
        "4. GÜÇLÜ YÖNLER", *[f"• {item}" for item in strengths], "",
        "5. RİSKLER", *[f"• {item}" for item in risks], "",
        "6. SENARYOLAR",
        "Boğa: Büyüme ve kârlılık sürer, borç kontrol altında kalırsa değerleme yukarı genişleyebilir.",
        "Temel: Mevcut büyüme ve marj eğilimleri korunursa görünüm temel puan çevresinde dengeli kalabilir.",
        "Ayı: Kârlılık zayıflar, borç artar veya değerleme daralırsa aşağı yönlü risk büyüyebilir.", "",
        "7. DOĞRULAMA NOTU",
        "Bu rapor yapay zekâ tahminiyle veri uydurmaz. Eksik alanlar 'Veri yok' olarak gösterilir.",
        "Rakip/moat, yönetim beklentisi ve analist konsensüsü doğrulanmış kaynak olmadan puanlanmaz.",
        "Rapor yatırım tavsiyesi değildir ve mevcut teknik al-sat kararını değiştirmez.",
    ]
    return {"symbol": symbol, "report": "\n".join(lines), "data_completeness": completeness,
            "source": "Yahoo Finance; KAP/faaliyet ekranları ayrıca kontrol edilmelidir"}
