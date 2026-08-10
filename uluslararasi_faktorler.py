"""Yaygın teknik analiz formüllerinden çok faktörlü doğrulama katmanı.

RSI, MACD, ADX, ATR, Bollinger, VWAP, OBV ve Stochastic tek başlarına alım-satım
tahmini değildir. Bu modül bunları bağımsız faktörler olarak birleştirir ve
sonucu yalnızca karar denetiminde kullanır.
"""
from __future__ import annotations

from typing import Any, Dict
import math
import pandas as pd


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def faktorleri_hesapla(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or len(df) < 60 or any(name not in df for name in ("Close", "High", "Low", "Volume")):
        return {"uluslararasi_faktor_puani": 0, "faktor_notu": "Yeterli OHLCV verisi yok"}
    work = df.copy()
    close = pd.to_numeric(work["Close"], errors="coerce")
    high = pd.to_numeric(work["High"], errors="coerce")
    low = pd.to_numeric(work["Low"], errors="coerce")
    volume = pd.to_numeric(work["Volume"], errors="coerce").fillna(0)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    delta = close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    rsi = (100 - 100 / (1 + gain.ewm(alpha=1 / 14, adjust=False).mean() / loss.ewm(alpha=1 / 14, adjust=False).mean().replace(0, math.nan))).fillna(50)
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    mid = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0).replace(0, math.nan)
    bollinger_z = ((close - mid) / std).fillna(0)
    typical = (high + low + close) / 3
    vwap = (typical * volume).rolling(20).sum() / volume.rolling(20).sum().replace(0, math.nan)
    obv = (volume * close.diff().fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
    stochastic = ((close - low.rolling(14).min()) / (high.rolling(14).max() - low.rolling(14).min()).replace(0, math.nan) * 100).fillna(50)
    score, notes = 50.0, []
    if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]: score += 18; notes.append("EMA trend uyumu")
    elif close.iloc[-1] < ema20.iloc[-1] < ema50.iloc[-1]: score -= 18; notes.append("EMA trend zayıf")
    if macd.iloc[-1] > macd_signal.iloc[-1]: score += 10; notes.append("MACD pozitif")
    if 45 <= rsi.iloc[-1] <= 68: score += 8; notes.append("RSI dengeli")
    elif rsi.iloc[-1] >= 75: score -= 10; notes.append("RSI aşırı alım")
    if close.iloc[-1] > vwap.iloc[-1]: score += 7; notes.append("VWAP üstü")
    if obv.iloc[-1] > obv.rolling(20).mean().iloc[-1]: score += 5; notes.append("OBV destekli")
    if 20 <= stochastic.iloc[-1] <= 80: score += 2
    if bollinger_z.iloc[-1] > 2.2: score -= 8; notes.append("Bollinger aşırılığı")
    return {"uluslararasi_faktor_puani": round(max(0, min(100, score)), 1), "faktor_rsi": round(_f(rsi.iloc[-1], 50), 2), "faktor_macd": round(_f(macd.iloc[-1]), 4), "faktor_vwap": round(_f(vwap.iloc[-1]), 2), "faktor_stochastic": round(_f(stochastic.iloc[-1], 50), 2), "faktor_bollinger_z": round(_f(bollinger_z.iloc[-1]), 2), "faktor_notu": " | ".join(notes) if notes else "Faktörler nötr"}
