"""Günlük trade için saf ve ileriye bakmayan gösterge hesapları."""
from __future__ import annotations

import math
import pandas as pd
from teknik_gostergeler import atr as canonical_atr
from teknik_gostergeler import classic_pivot, pivot_series as canonical_pivot_series, session_vwap


def klasik_pivot(previous_high: float, previous_low: float, previous_close: float) -> dict[str, float]:
    h, l, c = map(float, (previous_high, previous_low, previous_close))
    if not all(math.isfinite(x) and x > 0 for x in (h, l, c)) or h < max(l, c):
        raise ValueError("Geçersiz önceki gün OHLC")
    return classic_pivot(h, l, c)


def pivot_serisi(daily: pd.DataFrame) -> pd.DataFrame:
    """Her satır için sadece bir önceki tamamlanmış günün pivotunu verir."""
    return canonical_pivot_series(daily)


def seans_vwap(intraday: pd.DataFrame) -> pd.Series:
    """Hacimsiz barlarda NaN üretir ve her İstanbul işlem gününde sıfırlar."""
    if intraday.empty or "Volume" not in intraday:
        return pd.Series(index=intraday.index, dtype=float, name="VWAP")
    return session_vwap(intraday)


def wilder_atr(daily: pd.DataFrame, period: int = 14) -> pd.Series:
    return canonical_atr(daily, period)


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
