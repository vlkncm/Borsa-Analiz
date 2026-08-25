import pandas as pd
import numpy as np
from .ortak import wilder_rma
from .oynaklik import atr, true_range


def adx(frame: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high, low = frame["High"].astype(float), frame["Low"].astype(float)
    up, down = high.diff(), -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    smoothed_tr = wilder_rma(true_range(frame), period).mask(lambda value: value == 0)
    plus_di = 100*wilder_rma(plus_dm, period)/smoothed_tr
    minus_di = 100*wilder_rma(minus_dm, period)/smoothed_tr
    denominator = (plus_di+minus_di).mask((plus_di+minus_di) == 0)
    dx = 100*(plus_di-minus_di).abs()/denominator
    return pd.DataFrame({"PLUS_DI": plus_di, "MINUS_DI": minus_di, "ADX": wilder_rma(dx, period)}, index=frame.index)


def ichimoku(frame: pd.DataFrame) -> pd.DataFrame:
    high, low = frame["High"], frame["Low"]
    tenkan = (high.rolling(9).max()+low.rolling(9).min())/2
    kijun = (high.rolling(26).max()+low.rolling(26).min())/2
    return pd.DataFrame({"TENKAN": tenkan, "KIJUN": kijun, "SPAN_A": ((tenkan+kijun)/2).shift(26), "SPAN_B": ((high.rolling(52).max()+low.rolling(52).min())/2).shift(26)}, index=frame.index)


def supertrend(frame: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    high, low, close = frame["High"].astype(float), frame["Low"].astype(float), frame["Close"].astype(float)
    volatility = atr(frame, period)
    midpoint = (high+low)/2
    upper, lower = midpoint+multiplier*volatility, midpoint-multiplier*volatility
    final_upper, final_lower = upper.copy(), lower.copy()
    direction = pd.Series(0, index=frame.index, dtype="int64")
    trend = pd.Series(np.nan, index=frame.index, dtype=float)
    first = volatility.first_valid_index()
    if first is None:
        return pd.DataFrame({"SUPERTREND": trend, "SUPERTREND_DIRECTION": direction}, index=frame.index)
    start = frame.index.get_loc(first)
    direction.iloc[start] = 1; trend.iloc[start] = final_lower.iloc[start]
    for i in range(start+1, len(frame)):
        final_upper.iloc[i] = upper.iloc[i] if upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1] else final_upper.iloc[i-1]
        final_lower.iloc[i] = lower.iloc[i] if lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1] else final_lower.iloc[i-1]
        direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i-1] else (-1 if close.iloc[i] < final_lower.iloc[i-1] else direction.iloc[i-1])
        trend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
    return pd.DataFrame({"SUPERTREND": trend, "SUPERTREND_DIRECTION": direction}, index=frame.index)
