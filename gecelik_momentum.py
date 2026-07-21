from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Tuple

import numpy as np
import pandas as pd


def _wilson_alt(k: int, n: int, z: float = 1.2816) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / d)


def gecelik_aday_puanla(df: pd.DataFrame, sembol: str = "") -> Dict[str, Any]:
    """Kapanıştan ertesi seansa taşınacak momentum adayını puanlar.

    Hedef, ertesi gün girişe göre +%10 görülmesidir. Bu nadir bir olaydır; motor
    ham geçmiş oranını değil, küçük örneği cezalandıran Wilson alt sınırını kullanır.
    """
    gerekli = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or len(df) < 260 or not gerekli.issubset(df.columns):
        return {"sembol": sembol, "uygun": False, "neden": "En az 260 geçerli günlük OHLCV gerekli."}

    w = df.copy().sort_index()
    for c in gerekli:
        w[c] = pd.to_numeric(w[c], errors="coerce")
    w = w.dropna(subset=list(gerekli))
    if len(w) < 260:
        return {"sembol": sembol, "uygun": False, "neden": "Temiz veri yetersiz."}

    close, high, low, volume = w["Close"], w["High"], w["Low"], w["Volume"]
    ret1 = close.pct_change() * 100
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    vma20 = volume.rolling(20).mean()
    volume_ratio = volume / vma20.replace(0, np.nan)
    breakout20 = close / high.shift(1).rolling(20).max() - 1
    clv = (close - low) / (high - low).replace(0, np.nan)
    turnover20 = (close * volume).rolling(20).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr_pct = tr.ewm(alpha=1 / 14, adjust=False).mean() / close * 100

    # Bugünkü yapıya benzeyen geçmiş sinyaller. Gelecek gün sadece sonuç
    # ölçümünde kullanılır; bugünkü puanın girdisi değildir.
    state = (
        ret1.between(1.0, 7.5) & volume_ratio.between(1.25, 5.0) &
        (close > ema20) & (ema20 > ema50) & rsi.between(52, 76) &
        (clv >= 0.70) & atr_pct.between(1.5, 7.0)
    )
    next_high_return = high.shift(-1) / close - 1
    samples_mask = state & next_high_return.notna()
    samples = int(samples_mask.sum())
    winners = int((next_high_return[samples_mask] >= 0.10).sum())
    raw_probability = winners / samples if samples else 0.0
    safe_probability = _wilson_alt(winners, samples)

    last = -1
    points, reasons, risks = 0.0, [], []
    day_ret = float(ret1.iloc[last])
    vr = float(volume_ratio.iloc[last])
    rsi_now = float(rsi.iloc[last])
    clv_now = float(clv.iloc[last])
    atr_now = float(atr_pct.iloc[last])
    breakout_now = float(breakout20.iloc[last])
    turnover = float(turnover20.iloc[last])

    if 1.0 <= day_ret <= 5.5:
        points += 14; reasons.append("Kontrollü pozitif günlük momentum")
    elif day_ret > 8.0:
        points -= 20; risks.append("Tavana yakın; ertesi gün kâr satışı riski")
    if 1.4 <= vr <= 4.0:
        points += 18; reasons.append("Hacim teyidi")
    elif vr > 6:
        points -= 8; risks.append("Olağandışı hacim boşalması olabilir")
    if close.iloc[last] > ema20.iloc[last] > ema50.iloc[last]:
        points += 18; reasons.append("EMA20/EMA50 trendi pozitif")
    if 55 <= rsi_now <= 70:
        points += 12; reasons.append("RSI momentum bölgesinde")
    elif rsi_now > 78:
        points -= 12; risks.append("RSI aşırı alım")
    if clv_now >= 0.80:
        points += 12; reasons.append("Kapanış gün içi zirveye yakın")
    if breakout_now >= 0:
        points += 12; reasons.append("20 günlük zirve kırılımı")
    if 2.0 <= atr_now <= 6.0:
        points += 7; reasons.append("Hedef için yeterli volatilite")
    if turnover >= 25_000_000:
        points += 7; reasons.append("Asgari likidite filtresi geçti")
    else:
        points -= 20; risks.append("Likidite yetersiz")
    if samples >= 30:
        points += min(10.0, safe_probability * 100)
    else:
        risks.append("Benzer tarihsel örnek sayısı düşük")

    points = round(max(0.0, min(100.0, points)), 1)
    data_date = pd.Timestamp(w.index[-1]).strftime("%Y-%m-%d")
    eligible = bool(state.iloc[-1] and points >= 72 and turnover >= 25_000_000 and samples >= 20)
    return {
        "sembol": sembol,
        "veri_tarihi": data_date,
        "uygun": eligible,
        "gecelik_puan": points,
        "kapanis": round(float(close.iloc[-1]), 2),
        "gunluk_getiri_yuzde": round(day_ret, 2),
        "hacim_orani": round(vr, 2),
        "rsi": round(rsi_now, 1),
        "atr_yuzde": round(atr_now, 2),
        "ortalama_islem_tutari": round(turnover, 0),
        "tarihsel_ornek": samples,
        "ertesi_gun_yuzde10_ham_olasilik": round(raw_probability * 100, 2),
        "ertesi_gun_yuzde10_guvenli_olasilik": round(safe_probability * 100, 2),
        "referans_alis": round(float(close.iloc[-1]), 2),
        "hedef": round(float(close.iloc[-1]) * 1.10, 2),
        "acilis_risk_stop": round(float(close.iloc[-1]) * 0.96, 2),
        "nedenler": " | ".join(reasons),
        "riskler": " | ".join(risks),
        "uyari": "Ertesi gün +%10 garanti değildir; gece boşluğu nedeniyle stop fiyatı aşılarak açılabilir.",
    }


def tek_gecelik_aday(adaylar: Iterable[Tuple[str, pd.DataFrame]]) -> Dict[str, Any]:
    sonuclar = [gecelik_aday_puanla(df, symbol) for symbol, df in adaylar]
    uygunlar = [x for x in sonuclar if x.get("uygun")]
    if not uygunlar:
        return {"uygun": False, "karar": "BUGÜN ADAY YOK", "taranan": len(sonuclar)}
    uygunlar.sort(key=lambda x: (x["gecelik_puan"], x["ertesi_gun_yuzde10_guvenli_olasilik"]), reverse=True)
    return {**uygunlar[0], "karar": "TEK GECE ADAYI"}
