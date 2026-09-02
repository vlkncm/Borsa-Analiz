"""v10.3.3 canlı veri ve kanonik gösterge bağımsız doğrulaması."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import yfinance as yf

from teknik_gostergeler import adx, atr, ema, macd, rsi, wilder_rma


SYMBOLS = ("THYAO.IS", "ASELS.IS", "TUPRS.IS", "EREGL.IS", "BIMAS.IS")


def independent(frame: pd.DataFrame) -> dict[str, float]:
    close, high, low = frame["Close"], frame["High"], frame["Low"]
    delta = close.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss
    rsi14 = (100 - 100 / (1 + rs)).where(avg_loss.ne(0), 100).where(avg_gain.ne(0), 0)
    ema12 = close.ewm(span=12, adjust=False).mean(); ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    previous = close.shift(1)
    tr = pd.concat([(high-low).abs(), (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
    atr14 = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    up = high.diff(); down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr14
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False, min_periods=14).mean() / atr14
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    return {
        "Close": float(close.iloc[-1]), "Volume": float(frame["Volume"].iloc[-1]),
        "RSI14": float(rsi14.iloc[-1]), "EMA20": float(close.ewm(span=20, adjust=False).mean().iloc[-1]),
        "EMA50": float(close.ewm(span=50, adjust=False).mean().iloc[-1]),
        "EMA200": float(close.ewm(span=200, adjust=False).mean().iloc[-1]),
        "MACD": float(macd_line.iloc[-1]), "ATR14": float(atr14.iloc[-1]),
        "ADX14": float(dx.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1]),
    }


def canonical(frame: pd.DataFrame) -> dict[str, float]:
    close = frame["Close"]
    return {
        "Close": float(close.iloc[-1]), "Volume": float(frame["Volume"].iloc[-1]),
        "RSI14": float(rsi(close, 14).iloc[-1]), "EMA20": float(ema(close, 20).iloc[-1]),
        "EMA50": float(ema(close, 50).iloc[-1]), "EMA200": float(ema(close, 200).iloc[-1]),
        "MACD": float(macd(close)["MACD"].iloc[-1]), "ATR14": float(atr(frame, 14).iloc[-1]),
        "ADX14": float(adx(frame, 14)["ADX"].iloc[-1]),
    }


def main() -> int:
    fingerprints = set()
    for symbol in SYMBOLS:
        frame = yf.download(symbol, period="2y", interval="1d", auto_adjust=False, progress=False)
        if isinstance(frame.columns, pd.MultiIndex): frame.columns = frame.columns.get_level_values(0)
        frame = frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
        if len(frame) < 200: raise AssertionError(f"{symbol}: yetersiz satır {len(frame)}")
        fingerprint = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()
        if fingerprint in fingerprints: raise AssertionError(f"{symbol}: başka sembolle aynı veri/cache")
        fingerprints.add(fingerprint)
        expected, actual = independent(frame), canonical(frame)
        for name in expected:
            if not np.isclose(expected[name], actual[name], rtol=1e-9, atol=1e-9, equal_nan=False):
                raise AssertionError(f"{symbol} {name}: bağımsız={expected[name]} kanonik={actual[name]}")
        print(symbol, len(frame), fingerprint[:12], {k: round(v, 4) for k, v in actual.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
