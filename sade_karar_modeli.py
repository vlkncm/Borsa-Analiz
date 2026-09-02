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


def gunluk_rapor_adaylari(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    """Intraday servis yokken son güvenilir günlük raporu görünür yedek listeye çevirir."""
    if df is None or df.empty:
        return pd.DataFrame(columns=SADE_KOLONLAR)
    work = df.copy()
    price = _num(work, ("Fiyat", "Referans Fiyat"))
    low = _num(work, ("Önerilen Alış Alt", "Alış Alt"), price)
    high = _num(work, ("Önerilen Alış Üst", "Alış Üst"), price)
    target = _num(work, ("Gün İçi Hedef", "Önerilen Satış", "Hedef"))
    stop = _num(work, ("Önerilen Stop", "Stop Loss", "Stop"))
    score = _num(work, ("Günlük Trade Skoru", "v4 Güven Puanı", "AI Güven Puanı"))
    ema20, ema50 = _num(work, ("EMA20",)), _num(work, ("EMA50",))
    rsi, macd, signal = _num(work, ("RSI",), 50), _num(work, ("MACD",)), _num(work, ("MACD Signal",))
    volume, adx = _num(work, ("Hacim Oranı",), 1), _num(work, ("ADX",), 20)
    potential_all = ((target / price.replace(0, pd.NA)) - 1).mul(100).fillna(0)
    combo_count = ((price > ema20).astype(int) + (ema20 > ema50).astype(int) +
                   rsi.between(50, 70, inclusive="neither").astype(int) +
                   (macd > signal).astype(int) + (volume >= 1.0).astype(int))
    valid = ((price > 0) & (target > price) & (stop > 0) & (stop < price) & (score >= 65) &
             potential_all.between(3, 5, inclusive="both") & (combo_count >= 4) & (adx >= 20))
    if "Veri Durumu" in work:
        valid &= work["Veri Durumu"].astype(str).str.upper().eq("GÜVENİLİR")
    idx = work.index[valid]
    if idx.empty:
        return pd.DataFrame(columns=SADE_KOLONLAR)
    potential = ((target.loc[idx] / price.loc[idx]) - 1) * 100
    result = pd.DataFrame({
        "Hisse": _text(work.loc[idx], ("Hisse",)).str.replace(".IS", "", regex=False),
        "Karar": "GÜNCEL FİYATLA DOĞRULA",
        "Referans Fiyat": price.loc[idx].round(2),
        "Alım Bölgesi": [f"{a:.2f} – {b:.2f} TL" for a, b in zip(low.loc[idx], high.loc[idx])],
        "Hedef": target.loc[idx].round(2), "Stop": stop.loc[idx].round(2),
        "Potansiyel %": potential.round(2), "Tahmini Süre": "Gün içi",
        "Güven Skoru": score.loc[idx].clip(0, 100).round().astype(int),
        "Risk": _risk(((price.loc[idx] - stop.loc[idx]) / price.loc[idx] * 100).fillna(99)),
    }, index=idx)
    return result.sort_values(["Güven Skoru", "Potansiyel %"], ascending=False).head(limit).reset_index(drop=True)


def vade_rapor_adaylari(df: pd.DataFrame, sure: str, limit: int = 5, haric: Iterable[str] = ()) -> pd.DataFrame:
    """Katı fırsat filtresi boş kaldığında hesaplanmış hedef/stopu olan izleme adaylarını gösterir."""
    if df is None or df.empty:
        return pd.DataFrame(columns=SADE_KOLONLAR)
    work = df.copy()
    symbols = _text(work, ("Hisse",)).str.replace(".IS", "", regex=False).str.upper()
    if haric:
        work = work.loc[~symbols.isin({str(x).replace(".IS", "").upper() for x in haric})].copy()
    price = _num(work, ("Fiyat", "Referans Fiyat"))
    low, high = _num(work, ("Önerilen Alış Alt", "Alış Alt"), price), _num(work, ("Önerilen Alış Üst", "Alış Üst"), price)
    target, stop = _num(work, ("Önerilen Satış", "Hedef 1", "Hedef")), _num(work, ("Önerilen Stop", "Stop Loss", "Stop"))
    score = _num(work, ("v4 Güven Puanı", "AI Güven Puanı", "Broker Skor"))
    valid = (price > 0) & (target > price) & (stop > 0) & (stop < price) & (score >= 50)
    idx = work.index[valid]
    if idx.empty:
        return pd.DataFrame(columns=SADE_KOLONLAR)
    result = pd.DataFrame({
        "Hisse": _text(work.loc[idx], ("Hisse",)).str.replace(".IS", "", regex=False),
        "Karar": "TAKİP ET", "Referans Fiyat": price.loc[idx].round(2),
        "Alım Bölgesi": [f"{a:.2f} – {b:.2f} TL" for a, b in zip(low.loc[idx], high.loc[idx])],
        "Hedef": target.loc[idx].round(2), "Stop": stop.loc[idx].round(2),
        "Potansiyel %": (((target.loc[idx] / price.loc[idx]) - 1) * 100).round(2),
        "Tahmini Süre": sure, "Güven Skoru": score.loc[idx].clip(0, 100).round().astype(int),
        "Risk": _risk(((price.loc[idx] - stop.loc[idx]) / price.loc[idx] * 100).fillna(99)),
    }, index=idx)
    return result.sort_values(["Güven Skoru", "Potansiyel %"], ascending=False).head(limit).reset_index(drop=True)


def elli_tl_adaylari(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """iPhone/PWA 50 TL altı taramasındaki teknik ve likidite puanını masaüstünde uygular."""
    columns = ["Hisse", "Durum", "Mevcut Fiyat", "Alım Bölgesi", "Hedef", "Stop", "Potansiyel %", "Hedefe Ulaşma Olasılığı %", "Tahmini Hedef Süresi", "Süre Güveni", "Beklenen Getiri / Süre", "Skor", "Risk/Getiri"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    work = df.copy()
    price = _num(work, ("Fiyat", "Referans Fiyat"))
    turnover = _num(work, ("Ortalama Günlük İşlem Tutarı",))
    e20, e50, e200 = (_num(work, (name,)) for name in ("EMA20", "EMA50", "EMA200"))
    rsi = _num(work, ("RSI",), 50)
    macd, signal = _num(work, ("MACD",)), _num(work, ("MACD Signal",))
    volume_ratio = _num(work, ("Hacim Oranı",), 1)
    ret20, ret60 = _num(work, ("Son 20 Gün %",)), _num(work, ("Son 60 Gün %",))
    stop = _num(work, ("Önerilen Stop", "Stop Loss"), price * .97)
    target = _num(work, ("Önerilen Satış", "Hedef 1"), price * 1.08)
    rr = (target - price) / (price - stop).replace(0, pd.NA)
    score = (
        (price > e20).astype(int) * 12 + (e20 > e50).astype(int) * 18 +
        (price > e200).astype(int) * 15 + rsi.between(45, 68).astype(int) * 18 +
        (macd > signal).astype(int) * 15 + (volume_ratio >= 1.15).astype(int) * 12 +
        ((ret20 > 0) & (ret20 < 20)).astype(int) * 5 + (ret60 > 0).astype(int) * 5 +
        (rr >= 1.5).astype(int) * 5
    ).clip(0, 100)
    valid = price.between(1, 50, inclusive="both") & (turnover >= 5_000_000) & (score >= 48) & (target > price) & (stop < price)
    idx = work.index[valid]
    if idx.empty:
        return pd.DataFrame(columns=columns)
    status = pd.Series("TEYİT BEKLE", index=idx)
    status.loc[(score.loc[idx] >= 75) & (price.loc[idx] <= e20.loc[idx] * 1.04)] = "ALIM BÖLGESİNDE"
    status.loc[price.loc[idx] > e20.loc[idx] * 1.08] = "GERİ ÇEKİLME BEKLE"
    potential = ((target.loc[idx] / price.loc[idx]) - 1) * 100
    atr = _num(work.loc[idx], ("ATR", "ATR14"), 0)
    atr_pct = (atr / price.loc[idx].replace(0, pd.NA)).fillna(0).clip(.002, .2)
    # Sabit vade dayatmak yerine hedef mesafesi/gerçekleşen volatilite ve momentum hızından bounded tahmin.
    momentum_speed = (_num(work.loc[idx], ("Son 20 Gün %",), 0).abs() / 20).clip(.05, 3) / 100
    daily_capacity = (atr_pct * .8 + momentum_speed * .2).clip(.002, .12)
    target_days = (potential.loc[idx].abs() / 100 / daily_capacity).clip(2, 252)
    probability = (52 + (score.loc[idx] - 50) * .45 + (rr.loc[idx].clip(0, 4) - 1.5) * 5 - atr_pct * 80).clip(20, 85)
    time_conf = pd.cut(target_days, [-1, 10, 30, 90, 999], labels=["YÜKSEK", "ORTA", "DÜŞÜK", "DÜŞÜK"], right=True).astype(str)
    result = pd.DataFrame({
        "Hisse": _text(work.loc[idx], ("Hisse",)).str.replace(".IS", "", regex=False),
        "Durum": status, "Mevcut Fiyat": price.loc[idx].round(2),
        "Alım Bölgesi": [f"{min(p * .98, e):.2f} – {p * 1.01:.2f} TL" for p, e in zip(price.loc[idx], e20.loc[idx])],
        "Hedef": target.loc[idx].round(2), "Stop": stop.loc[idx].round(2),
        "Potansiyel %": potential.round(2), "Hedefe Ulaşma Olasılığı %": probability.round(1),
        "Tahmini Hedef Süresi": target_days.round(0).astype(int).astype(str) + " işlem günü",
        "Süre Güveni": time_conf, "Beklenen Getiri / Süre": (potential / target_days).round(3),
        "Skor": score.loc[idx].astype(int),
        "Risk/Getiri": rr.loc[idx].round(2),
    }, index=idx)
    return result.sort_values(["Skor", "Risk/Getiri"], ascending=False).head(limit).reset_index(drop=True)


def elli_tl_ohlcv_adayi(symbol: str, frame: pd.DataFrame) -> dict | None:
    """50 TL taramasını v10.2 kanonik günlük feature hattıyla hesaplar."""
    if frame is None or frame.empty or "Close" not in frame:
        return None
    data = frame.copy().dropna(subset=["Close", "High", "Low"])
    if data.empty:
        return None
    price = float(pd.to_numeric(data["Close"], errors="coerce").iloc[-1])
    if not 1 <= price <= 50:
        return None
    if len(data) < 60:
        from yeni_halka_arz import yeni_halka_arz_analizi
        ipo = yeni_halka_arz_analizi(symbol, data)
        return {"Hisse": ipo["Hisse"], "Durum": ipo["Durum"], "Mevcut Fiyat": price,
                "Skor": ipo["Momentum Puani"], "Risk/Getiri": None,
                "Ortalama İşlem Tutarı": ipo["Ortalama İşlem Tutarı"],
                "Model Yolu": ipo["Model Yolu"], "Neden Kodu": ipo["Neden Kodu"],
                "Eleme Nedeni": ipo["Eleme Nedeni"], "Veri Yeterlilik Seviyesi": ipo["Veri Yeterlilik Seviyesi"]}
    if len(data) < 200:
        return {"Hisse": symbol.replace(".IS", ""), "Durum": "VERİ GEÇMİŞİ SINIRLI",
                "Mevcut Fiyat": price, "Skor": 0, "Risk/Getiri": None,
                "Ortalama İşlem Tutarı": float((data["Close"]*data.get("Volume", 0)).mean()),
                "Model Yolu": "STANDART", "Neden Kodu": "INSUFFICIENT_HISTORY",
                "Eleme Nedeni": "50 TL standart modeli için 200 seans gerekli"}
    # RSI, EMA, MACD ve ATR burada yeniden yazılmaz. Masaüstü tarama,
    # backtest ve mobil sözleşmenin dayandığı tek kanonik motor kullanılır.
    from sinyal_pipeline import daily_features

    features = daily_features(data)
    close = pd.to_numeric(features["Close"], errors="coerce")
    high, low = pd.to_numeric(data["High"], errors="coerce"), pd.to_numeric(data["Low"], errors="coerce")
    volume = pd.to_numeric(data.get("Volume", 0), errors="coerce").fillna(0)
    price = float(close.iloc[-1])
    turnover = float((close * volume).tail(20).mean())
    if not math.isfinite(turnover) or turnover < 5_000_000:
        return None
    last = features.iloc[-1]
    e20, e50, e200 = float(last["EMA20"]), float(last["EMA50"]), float(last["EMA200"])
    rsi = float(last["RSI"])
    macd_value, macd_signal_value = float(last["MACD"]), float(last["MACD_SIGNAL"])
    volume_ratio = float(volume.iloc[-1] / max(volume.tail(20).mean(), 1))
    ret20 = float((price / close.iloc[-21] - 1) * 100); ret60 = float((price / close.iloc[-61] - 1) * 100)
    atr = float(last["ATR"]); support = float(low.tail(20).min())
    if not all(math.isfinite(value) for value in (e20, e50, e200, rsi, macd_value, macd_signal_value, atr)):
        return None
    stop = min(price*.985, max(price-atr*1.5, support*.98))
    target = price + max(atr*2.2, price*.08)
    rr = (target-price) / max(price-stop, .01)
    score = (12*(price>e20) + 18*(e20>e50) + 15*(price>e200) + 18*(45<=rsi<=68) +
             15*(macd_value>macd_signal_value) + 12*(volume_ratio>=1.15) +
             5*(0<ret20<20) + 5*(ret60>0) + 5*(rr>=1.5))
    if score < 48:
        return None
    target_probability = float(max(20, min(85, 52 + (score - 50)*.45 + (rr-1.5)*5 - (atr/price)*80)))
    daily_capacity = max(.002, min(.12, (atr/price)*.8 + max(abs(ret20)/20/100, .0005)*.2))
    target_days = int(max(2, min(252, ((target/price-1) / daily_capacity))))
    status = "ALIM BÖLGESİNDE" if score >= 75 and price <= e20*1.04 else "GERİ ÇEKİLME BEKLE" if price > e20*1.08 else "TEYİT BEKLE"
    result = {"Hisse": symbol.replace(".IS", ""), "Durum": status, "Mevcut Fiyat": round(price, 2),
            "Alım Bölgesi": f"{min(price*.98, e20):.2f} – {price*1.01:.2f} TL", "Hedef": round(target, 2),
            "Stop": round(stop, 2), "Potansiyel %": round((target/price-1)*100, 2), "Skor": int(score),
            "Risk/Getiri": round(rr, 2), "Ortalama İşlem Tutarı": round(turnover)}
    result.update({"Hedefe Ulaşma Olasılığı %": round(target_probability, 1), "Tahmini Hedef Süresi": f"{target_days} işlem günü",
                   "Süre Güveni": "ORTA" if target_days <= 30 else "DÜŞÜK", "Beklenen Getiri / Süre": round((target/price-1)*100/target_days, 3)})
    return result


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


def orta_vadeden_kisa_adaylari_cikar(short_frame: pd.DataFrame, medium_source: pd.DataFrame) -> pd.DataFrame:
    """Formüllere dokunmadan kullanıcı tercihine göre iki sonuç listesini ayrıştırır."""
    if medium_source is None or medium_source.empty or "Hisse" not in medium_source:
        return pd.DataFrame() if medium_source is None else medium_source.copy()
    if short_frame is None or short_frame.empty or "Hisse" not in short_frame:
        return medium_source.copy()
    short_symbols = short_frame["Hisse"].astype(str).str.replace(".IS", "", regex=False).str.upper()
    medium_symbols = medium_source["Hisse"].astype(str).str.replace(".IS", "", regex=False).str.upper()
    return medium_source[~medium_symbols.isin(set(short_symbols))].copy()


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
