"""RSI ikili toparlanma + SuperTrend deneysel sinyali."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from teknik_gostergeler import rsi as canonical_rsi, sma, supertrend as canonical_supertrend


@dataclass(frozen=True)
class RsiSupertrendAyarlar:
    rsi_periyodu: int = 10
    rsi_sma_periyodu: int = 10
    tetik_siniri: float = 50.0
    ozel_sinyal_sirasi: int = 2
    atr_periyodu: int = 10
    supertrend_carpani: float = 2.5


def _rsi(close: pd.Series, period: int) -> pd.Series:
    """Deprecated: kanonik Wilder RSI motoruna yönlendirir."""
    return canonical_rsi(close, period)


def _supertrend(df: pd.DataFrame, period: int, multiplier: float) -> tuple[pd.Series, pd.Series]:
    """Deprecated: kanonik SuperTrend motoruna yönlendirir."""
    values = canonical_supertrend(df, period, multiplier)
    return values["SUPERTREND"], values["SUPERTREND_DIRECTION"]


def hesapla(df: pd.DataFrame, ayarlar: RsiSupertrendAyarlar | None = None, zaman_dilimi: str = "1G") -> dict:
    ayar = ayarlar or RsiSupertrendAyarlar(); gerekli = {"High", "Low", "Close"}
    if df is None or len(df) < max(ayar.rsi_periyodu + ayar.rsi_sma_periyodu, ayar.atr_periyodu) + 5 or not gerekli.issubset(df.columns): return _bos("Yetersiz fiyat verisi", zaman_dilimi)
    work = df.copy().dropna(subset=list(gerekli)); work["RSI_DIP"] = _rsi(work["Close"].astype(float), ayar.rsi_periyodu)
    work["RSI_SMA"] = sma(work["RSI_DIP"], ayar.rsi_sma_periyodu); work["ST"], work["ST_YON"] = _supertrend(work, ayar.atr_periyodu, ayar.supertrend_carpani)
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
