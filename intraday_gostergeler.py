"""Günlük trade için saf ve ileriye bakmayan gösterge hesapları."""
from __future__ import annotations

import math
import pandas as pd


def klasik_pivot(previous_high: float, previous_low: float, previous_close: float) -> dict[str, float]:
    h, l, c = map(float, (previous_high, previous_low, previous_close))
    if not all(math.isfinite(x) and x > 0 for x in (h, l, c)) or h < max(l, c):
        raise ValueError("Geçersiz önceki gün OHLC")
    p = (h + l + c) / 3.0
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + h - l, "S2": p - h + l}


def pivot_serisi(daily: pd.DataFrame) -> pd.DataFrame:
    """Her satır için sadece bir önceki tamamlanmış günün pivotunu verir."""
    prev = daily[["High", "Low", "Close"]].shift(1)
    p = prev.sum(axis=1, min_count=3) / 3.0
    return pd.DataFrame({"P": p, "R1": 2*p-prev["Low"], "S1": 2*p-prev["High"],
                         "R2": p+prev["High"]-prev["Low"], "S2": p-prev["High"]+prev["Low"]}, index=daily.index)


def seans_vwap(intraday: pd.DataFrame) -> pd.Series:
    """Hacimsiz barlarda NaN üretir ve her İstanbul işlem gününde sıfırlar."""
    if intraday.empty or "Volume" not in intraday:
        return pd.Series(index=intraday.index, dtype=float, name="VWAP")
    volume = pd.to_numeric(intraday["Volume"], errors="coerce")
    typical = intraday[["High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    if isinstance(intraday.index, pd.DatetimeIndex):
        idx = intraday.index
        idx = idx.tz_localize("Europe/Istanbul") if idx.tz is None else idx.tz_convert("Europe/Istanbul")
        sessions = pd.Series(idx.date, index=intraday.index)
    else:
        sessions = pd.Series(0, index=intraday.index)
    valid_volume = volume.where(volume > 0)
    numerator = (typical * valid_volume).groupby(sessions).cumsum()
    denominator = valid_volume.groupby(sessions).cumsum()
    return (numerator / denominator).rename("VWAP")


def wilder_atr(daily: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = (pd.to_numeric(daily[c], errors="coerce") for c in ("High", "Low", "Close"))
    previous = close.shift(1)
    tr = pd.concat([high-low, (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean().rename("ATR")


def pozisyon_boyutu(hesap_buyuklugu: float | None, risk_yuzdesi: float, giris: float, stop: float,
                    max_portfoy_yuzdesi: float = 25.0, kullanilabilir_nakit: float | None = None,
                    likidite_adet_limiti: int | None = None, komisyon_orani: float = 0.001) -> dict:
    giris, stop = float(giris), float(stop)
    hisse_basi_risk = giris - stop + giris * max(0.0, komisyon_orani) * 2
    base = {"adet": None, "pozisyon_tutari": None, "risk_tutari": None, "hisse_basi_risk": hisse_basi_risk}
    if not hesap_buyuklugu or hesap_buyuklugu <= 0 or hisse_basi_risk <= 0:
        return base
    risk_yuzdesi = min(max(float(risk_yuzdesi), 0.0), 1.0)
    risk_tutari = float(hesap_buyuklugu) * risk_yuzdesi / 100.0
    risk_adet = math.floor(risk_tutari / hisse_basi_risk)
    nakit = float(hesap_buyuklugu) if kullanilabilir_nakit is None else max(0.0, float(kullanilabilir_nakit))
    portfoy_limit = min(nakit, float(hesap_buyuklugu) * max(0.0, float(max_portfoy_yuzdesi)) / 100.0)
    adetler = [risk_adet, math.floor(portfoy_limit / giris)]
    if likidite_adet_limiti is not None:
        adetler.append(max(0, int(likidite_adet_limiti)))
    adet = max(0, min(adetler))
    return {"adet": adet, "pozisyon_tutari": adet*giris, "risk_tutari": adet*hisse_basi_risk,
            "hisse_basi_risk": hisse_basi_risk}
