"""Günlük trade için AlphaTrend + EMA + BBW + MACD-V teyitleri.

MACD-V: Alex Spiroglou'nun oynaklığa normalize yaklaşımı:
    100 * (EMA(12) - EMA(26)) / ATR(26)
Bu modül göstergeleri karar motoruna kanıt olarak verir; tek başına AL üretmez.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100/(1+rs)
    return out.where(loss.ne(0), 100.0).where(gain.ne(0), 0.0).fillna(50.0)


def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    prev = frame["Close"].shift(1)
    tr = pd.concat([(frame["High"]-frame["Low"]), (frame["High"]-prev).abs(),
                    (frame["Low"]-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()


def macd_v(frame: pd.DataFrame, fast: int = 12, slow: int = 26,
           signal: int = 9, atr_period: int = 26) -> pd.DataFrame:
    close = pd.to_numeric(frame["Close"], errors="coerce")
    atr = _atr(frame, atr_period).replace(0, np.nan)
    value = 100 * (close.ewm(span=fast, adjust=False).mean()-close.ewm(span=slow, adjust=False).mean())/atr
    signal_line = value.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"MACD_V": value, "MACD_V_SIGNAL": signal_line,
                         "MACD_V_HIST": value-signal_line}, index=frame.index)


def alpha_trend_rsi(frame: pd.DataFrame, period: int = 14, coefficient: float = 1.0) -> pd.DataFrame:
    rsi = _rsi(pd.to_numeric(frame["Close"], errors="coerce"), period)
    atr = _atr(frame, period)
    lower_candidate = frame["Low"]-atr*coefficient
    upper_candidate = frame["High"]+atr*coefficient
    values = pd.Series(np.nan, index=frame.index, dtype=float)
    for i in range(len(frame)):
        candidate = lower_candidate.iloc[i] if rsi.iloc[i] >= 50 else upper_candidate.iloc[i]
        previous = values.iloc[i-1] if i else candidate
        if pd.isna(candidate):
            values.iloc[i] = previous
        elif rsi.iloc[i] >= 50:
            values.iloc[i] = max(candidate, previous) if pd.notna(previous) else candidate
        else:
            values.iloc[i] = min(candidate, previous) if pd.notna(previous) else candidate
    direction = pd.Series(np.where(rsi >= 50, "YUKARI", "AŞAĞI"), index=frame.index)
    return pd.DataFrame({"ALPHA_TREND": values, "ALPHA_YON": direction, "ALPHA_RSI": rsi}, index=frame.index)


def gunluk_trade_teyitleri(frame: pd.DataFrame) -> dict:
    if frame is None or len(frame) < 30:
        return {"alpha_trend_yonu": "VERİ YETERSİZ", "ema20_durumu": "VERİ YETERSİZ",
                "bbw_yuzde": None, "bbw_durumu": "VERİ YETERSİZ", "macd_v": None,
                "macd_v_sinyal": None, "macd_v_durumu": "VERİ YETERSİZ", "gunluk_trade_teyit": "VERİ YETERSİZ"}
    data = frame[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    alpha = alpha_trend_rsi(data)
    mv = macd_v(data)
    close = data["Close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    basis = close.rolling(20).mean()
    deviation = close.rolling(20).std(ddof=0)
    bbw = 100 * (4*deviation) / basis.replace(0, np.nan)
    quiet_threshold = bbw.rolling(120, min_periods=30).quantile(.25)
    last_bbw, last_threshold = float(bbw.iloc[-1]), float(quiet_threshold.iloc[-1])
    bbw_status = "YATAY / SIKIŞIK" if pd.notna(last_threshold) and last_bbw <= last_threshold else "HAREKETLİ"
    alpha_up = alpha.iloc[-1]["ALPHA_YON"] == "YUKARI"
    ema_up = close.iloc[-1] > ema20.iloc[-1] and ema20.iloc[-1] >= ema20.iloc[-2]
    macd_value, macd_signal = float(mv.iloc[-1]["MACD_V"]), float(mv.iloc[-1]["MACD_V_SIGNAL"])
    macd_status = "POZİTİF" if macd_value > macd_signal and macd_value > 0 else "NEGATİF / ZAYIF"
    confirmed = alpha_up and ema_up and bbw_status == "HAREKETLİ" and macd_status == "POZİTİF"
    return {
        "alpha_trend_yonu": str(alpha.iloc[-1]["ALPHA_YON"]),
        "ema20_durumu": "ÜSTÜNDE / YÜKSELİYOR" if ema_up else "TEYİTSİZ",
        "bbw_yuzde": last_bbw, "bbw_durumu": bbw_status,
        "macd_v": macd_value, "macd_v_sinyal": macd_signal, "macd_v_durumu": macd_status,
        "gunluk_trade_teyit": "4/4 TEYİTLİ" if confirmed else "TEYİT BEKLE",
    }
