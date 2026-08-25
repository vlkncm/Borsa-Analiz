"""Teknik motorların çıktısını sade, karar odaklı sonuçlara dönüştürür."""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


SADE_KOLONLAR = [
    "Hisse", "Karar", "Referans Fiyat", "Alım Bölgesi", "Hedef", "Stop",
    "Potansiyel %", "Tahmini Süre", "Güven Skoru", "Risk",
]
VADE_ADAYLARI = {
    "kisa": (5, 10, 15, 20, 30, 40),
    "orta": (40, 60, 90, 120, 180, 252),
}


def _num(frame: pd.DataFrame, names: Iterable[str], default=0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _text(frame: pd.DataFrame, names: Iterable[str], default="") -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name].fillna(default).astype(str)
    return pd.Series(default, index=frame.index, dtype=object)


def _risk(risk_pct: pd.Series) -> pd.Series:
    return pd.cut(risk_pct, [-math.inf, 3, 7, math.inf], labels=["DÜŞÜK RİSK", "ORTA RİSK", "YÜKSEK RİSK"]).astype(str)


def sade_gerekce(row: dict) -> str:
    reasons = []
    if float(row.get("Güven Skoru", 0) or 0) >= 75:
        reasons.append("Son dönemde benzer koşullardaki sonuçlar güçlü.")
    if float(row.get("Potansiyel %", 0) or 0) > 0:
        reasons.append("Hedefe göre mevcut risk kabul edilebilir.")
    if str(row.get("Karar", "")).upper() in {"GÜÇLÜ ADAY", "UYGUN BÖLGEDE AL", "TAKİP"}:
        reasons.append("Fiyat ve alım ilgisi birlikte olumlu görünüyor.")
    return " ".join(reasons) or "Henüz yeterince güçlü ve ortak bir olumlu koşul oluşmadı."


def sade_firsatlar(df: pd.DataFrame, vade: str, limit: int = 5, sure: str | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=SADE_KOLONLAR)
    work = df.copy()
    price = _num(work, ("Referans Fiyat", "Fiyat"))
    buy_low = _num(work, ("Önerilen Alış Alt", "Alış Alt"), price)
    buy_high = _num(work, ("Önerilen Alış Üst", "Alış Üst"), price)
    target_names = ("Gün İçi Hedef", "Önerilen Satış", "Hedef") if vade == "gunluk" else ("Önerilen Satış", "Hedef 1", "Hedef")
    target = _num(work, target_names)
    stop = _num(work, ("Önerilen Stop", "Stop Loss", "Stop"))
    score = _num(work, ("Günlük Trade Skoru", "Vade Skoru", "v4 Güven Puanı", "AI Güven Puanı"))
    potential = ((target / price.replace(0, pd.NA)) - 1).mul(100).fillna(0)
    rr = (target - price) / (price - stop).replace(0, pd.NA)
    valid = (price > 0) & (target > price) & (stop > 0) & (stop < price) & (score >= 60) & (rr >= 1.3)
    if "Veri Durumu" in work:
        valid &= work["Veri Durumu"].astype(str).str.upper().eq("GÜVENİLİR")
    work = work.loc[valid].copy()
    if work.empty:
        return pd.DataFrame(columns=SADE_KOLONLAR)
    idx = work.index
    p, lo, hi, tg, st, sc, pot = price.loc[idx], buy_low.loc[idx], buy_high.loc[idx], target.loc[idx], stop.loc[idx], score.loc[idx], potential.loc[idx]
    result = pd.DataFrame({
        "Hisse": _text(work, ("Hisse",)),
        "Karar": "GÜÇLÜ ADAY" if vade == "gunluk" else "UYGUN BÖLGEDE AL",
        "Referans Fiyat": p.round(2),
        "Alım Bölgesi": [f"{a:.2f} – {b:.2f} TL" for a, b in zip(lo, hi)],
        "Hedef": tg.round(2), "Stop": st.round(2), "Potansiyel %": pot.round(2),
        "Tahmini Süre": sure or ("Gün içi" if vade == "gunluk" else "Model belirleyecek"),
        "Güven Skoru": sc.clip(0, 100).round(0).astype(int),
        "Risk": _risk(((p - st) / p * 100).fillna(99)),
    }, index=idx)
    return result.sort_values(["Güven Skoru", "Potansiyel %"], ascending=False).head(limit).reset_index(drop=True)


def en_iyi_vade(backtest: pd.DataFrame | None, tur: str) -> tuple[int, str]:
    """Out-of-sample risk ayarlı puanı en yüksek gerçekçi tutma süresini seçer."""
    candidates = VADE_ADAYLARI[tur]
    default = 20 if tur == "kisa" else 90
    if backtest is None or backtest.empty:
        return default, "yeterli out-of-sample kayıt yok; korumacı varsayılan"
    period = _num(backtest, ("Tutma Süresi", "Holding Period", "Süre"), -1)
    ret = _num(backtest, ("Ortalama Getiri %", "Net Getiri %"))
    drawdown = _num(backtest, ("Max Drawdown %", "Maksimum Düşüş %")).abs()
    success = _num(backtest, ("Başarı %", "Kazanma Oranı %"), 50)
    samples = _num(backtest, ("İşlem Sayısı", "Örnek"), 0)
    score = ret - drawdown * 0.6 + (success - 50) * 0.15
    eligible = period.isin(candidates) & (samples >= 20)
    if not eligible.any():
        return default, "yeterli out-of-sample kayıt yok; korumacı varsayılan"
    best = score[eligible].idxmax()
    days = int(period.loc[best])
    return days, f"{int(samples.loc[best])} out-of-sample işlem; risk ayarlı puan {score.loc[best]:.1f}"


def sure_metni(days: int) -> str:
    if days < 30:
        return f"{max(1, days - 3)}–{days + 3} işlem günü"
    weeks = round(days / 5)
    return f"{max(1, weeks - 2)}–{weeks + 2} hafta"


def buyume_adaylari(df: pd.DataFrame, fiyat_limiti: float | None = None, limit: int = 5, min_score: float = 65) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Hisse", "Büyüme Skoru", "Mevcut Fiyat", "Risk", "Beklenen Süre", "Büyüme Potansiyeli", "Ana Gerekçe"])
    work = df.copy()
    price = _num(work, ("Fiyat", "Referans Fiyat"))
    financial = _num(work, ("Temel Puan", "Faaliyet Puanı"), 50)
    quality = _num(work, ("Usta Skor", "v4 Güven Puanı", "AI Güven Puanı"), 50)
    momentum = _num(work, ("Broker Skor", "MTF Skor"), 50)
    debt = _num(work, ("Borç/Özsermaye",), 1)
    revenue_growth = _num(work, ("Ciro Büyüme",)).clip(-1, 1).mul(100)
    profit_growth = _num(work, ("Kâr Büyüme",)).clip(-1, 1).mul(100)
    roe = _num(work, ("ROE",)).clip(-1, 1).mul(100)
    valuation = _num(work, ("F/K",), 30)
    fundamental = (revenue_growth.clip(0, 40) + profit_growth.clip(0, 40) + roe.clip(0, 30)) / 1.1
    valuation_bonus = (35 - valuation).clip(0, 25)
    debt_penalty = (debt - 1).clip(0, 4).mul(7)
    score = (financial * .25 + quality * .25 + momentum * .15 + fundamental * .25 + valuation_bonus * .4 - debt_penalty).clip(0, 100)
    valid = (price > 0) & (score >= min_score)
    if fiyat_limiti is not None:
        valid &= price < fiyat_limiti
    work = work.loc[valid].copy()
    idx = work.index
    result = pd.DataFrame({
        "Hisse": _text(work, ("Hisse",)), "Büyüme Skoru": score.loc[idx].round().astype(int),
        "Mevcut Fiyat": price.loc[idx].round(2), "Risk": _risk(pd.Series(8 - score.loc[idx] / 20, index=idx)),
        "Beklenen Süre": "1–3 yıl", "Büyüme Potansiyeli": pd.cut(score.loc[idx], [0, 70, 85, 100], labels=["İZLENEBİLİR", "GÜÇLÜ", "ÇOK GÜÇLÜ"], include_lowest=True).astype(str),
        "Ana Gerekçe": "Finansal büyüme, şirket kalitesi ve fiyat gücü birlikte değerlendirildi.",
    }, index=idx)
    return result.sort_values("Büyüme Skoru", ascending=False).head(limit).reset_index(drop=True)


def on_x_senaryosu(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    growth = buyume_adaylari(df, limit=max(limit * 3, 10))
    if growth.empty:
        return pd.DataFrame(columns=["Hisse", "10X Potansiyel Skoru", "Senaryo", "Bugünkü Fiyat", "Gerekli Yıllık Büyüme", "Ufuk", "Belirsizlik"])
    score = (growth["Büyüme Skoru"] * .9).clip(0, 100).round().astype(int)
    years = score.map(lambda x: 7 if x < 80 else 5 if x < 90 else 4)
    cagr = ((10 ** (1 / years)) - 1) * 100
    label = pd.cut(score, [-1, 69, 79, 89, 100], labels=["10X ADAYI DEĞİL", "İZLENEBİLİR", "YÜKSEK POTANSİYEL", "ÇOK YÜKSEK SPEKÜLATİF POTANSİYEL"])
    caps = _num(df.set_index(_text(df, ("Hisse",))), ("Piyasa Değeri",), 0)
    current_cap = growth["Hisse"].map(caps).fillna(0)
    result = pd.DataFrame({"Hisse": growth["Hisse"], "10X Potansiyel Skoru": score, "Senaryo": label.astype(str),
                           "Bugünkü Fiyat": growth["Mevcut Fiyat"], "Gerekli Yıllık Büyüme": cagr.round(1).map(lambda x: f"%{x}"),
                           "Bugünkü Piyasa Değeri": current_cap, "Gerekli 10X Piyasa Değeri": current_cap.mul(10),
                           "Ufuk": years.map(lambda x: f"{x} yıl"), "Belirsizlik": "ÇOK YÜKSEK"})
    return result[result["10X Potansiyel Skoru"] >= 70].head(limit).reset_index(drop=True)
