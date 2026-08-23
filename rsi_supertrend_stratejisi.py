"""RSI ikili toparlanma + SuperTrend deneysel sinyali."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RsiSupertrendAyarlar:
    rsi_periyodu: int = 10
    rsi_sma_periyodu: int = 10
    tetik_siniri: float = 50.0
    ozel_sinyal_sirasi: int = 2
    atr_periyodu: int = 10
    supertrend_carpani: float = 2.5


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean(); avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    result = 100 - (100 / (1 + avg_gain / avg_loss.mask(avg_loss == 0)))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0).mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    return result.fillna(50.0).astype(float)


def _supertrend(df: pd.DataFrame, period: int, multiplier: float) -> tuple[pd.Series, pd.Series]:
    high, low, close = df["High"].astype(float), df["Low"].astype(float), df["Close"].astype(float)
    previous_close = close.shift(1)
    tr = pd.concat([(high-low).abs(), (high-previous_close).abs(), (low-previous_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean(); midpoint = (high + low) / 2
    upper, lower = midpoint + multiplier * atr, midpoint - multiplier * atr
    final_upper, final_lower = upper.copy(), lower.copy(); direction = pd.Series(1, index=df.index, dtype="int64")
    trend = pd.Series(np.nan, index=df.index, dtype="float64")
    for i in range(1, len(df)):
        final_upper.iloc[i] = upper.iloc[i] if upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1] else final_upper.iloc[i-1]
        final_lower.iloc[i] = lower.iloc[i] if lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1] else final_lower.iloc[i-1]
        if close.iloc[i] > final_upper.iloc[i-1]: direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i-1]: direction.iloc[i] = -1
        else: direction.iloc[i] = direction.iloc[i-1]
        trend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
    trend.iloc[0] = final_lower.iloc[0]
    return trend, direction


def hesapla(df: pd.DataFrame, ayarlar: RsiSupertrendAyarlar | None = None, zaman_dilimi: str = "1G") -> dict:
    ayar = ayarlar or RsiSupertrendAyarlar(); gerekli = {"High", "Low", "Close"}
    if df is None or len(df) < max(ayar.rsi_periyodu + ayar.rsi_sma_periyodu, ayar.atr_periyodu) + 5 or not gerekli.issubset(df.columns): return _bos("Yetersiz fiyat verisi", zaman_dilimi)
    work = df.copy().dropna(subset=list(gerekli)); work["RSI_DIP"] = _rsi(work["Close"].astype(float), ayar.rsi_periyodu)
    work["RSI_SMA"] = work["RSI_DIP"].rolling(ayar.rsi_sma_periyodu).mean(); work["ST"], work["ST_YON"] = _supertrend(work, ayar.atr_periyodu, ayar.supertrend_carpani)
    cross = (work["RSI_DIP"] > work["RSI_SMA"]) & (work["RSI_DIP"].shift(1) <= work["RSI_SMA"].shift(1)) & (work["RSI_DIP"] < ayar.tetik_siniri)
    count = 0; special = pd.Series(False, index=work.index)
    for i in range(len(work)):
        if work["RSI_DIP"].iloc[i] >= ayar.tetik_siniri: count = 0
        elif bool(cross.iloc[i]):
            count += 1
            if count >= ayar.ozel_sinyal_sirasi: special.iloc[i] = True; count = 0
    confirmed = special & (work["ST_YON"] == 1) & (work["Close"] > work["ST"]); positions = np.flatnonzero(confirmed.to_numpy())
    bars_since = int(len(work)-1-positions[-1]) if len(positions) else None; active = bool(confirmed.iloc[-1])
    trend_up = bool(work["ST_YON"].iloc[-1] == 1 and work["Close"].iloc[-1] > work["ST"].iloc[-1])
    status = "YENİ TEYİTLİ DİP" if active else "YUKARI TREND / SİNYAL BEKLENİYOR" if trend_up else "TEYİT YOK"
    return {"rsi_st_durum": status, "rsi_st_yeni_sinyal": active, "rsi_st_trend_yukari": trend_up, "rsi_st_rsi": round(float(work["RSI_DIP"].iloc[-1]), 2), "rsi_st_rsi_sma": round(float(work["RSI_SMA"].iloc[-1]), 2), "rsi_st_supertrend": round(float(work["ST"].iloc[-1]), 4), "rsi_st_son_sinyal_bar": bars_since, "rsi_st_zaman_dilimi": zaman_dilimi, "rsi_st_not": "Deneysel gösterge; %80 başarı garantisi değildir ve ana kararı değiştirmez."}


def _bos(reason: str, timeframe: str) -> dict:
    return {"rsi_st_durum": "VERİ YOK", "rsi_st_yeni_sinyal": False, "rsi_st_trend_yukari": False, "rsi_st_rsi": None, "rsi_st_rsi_sma": None, "rsi_st_supertrend": None, "rsi_st_son_sinyal_bar": None, "rsi_st_zaman_dilimi": timeframe, "rsi_st_not": reason}
