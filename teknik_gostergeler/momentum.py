import pandas as pd
from .ortak import ema, sma, wilder_rma
from .oynaklik import atr


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = pd.to_numeric(close, errors="coerce").diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    avg_gain, avg_loss = wilder_rma(gains, period), wilder_rma(losses, period)
    ratio = avg_gain / avg_loss.mask(avg_loss == 0)
    result = 100 - 100/(1+ratio)
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    result = result.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return result.astype(float).rename("RSI")


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    signal_line = ema(line, signal)
    return pd.DataFrame({"MACD": line, "MACD_SIGNAL": signal_line, "MACD_HIST": line-signal_line}, index=close.index)


def macd_v(frame: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, atr_period: int = 26) -> pd.DataFrame:
    close = pd.to_numeric(frame["Close"], errors="coerce")
    volatility = atr(frame, atr_period).mask(lambda value: value == 0)
    value = 100*(ema(close, fast)-ema(close, slow))/volatility
    signal_line = ema(value, signal)
    return pd.DataFrame({"MACD_V": value, "MACD_V_SIGNAL": signal_line, "MACD_V_HIST": value-signal_line}, index=frame.index)


def roc(close: pd.Series, period: int = 12) -> pd.Series:
    return pd.to_numeric(close, errors="coerce").pct_change(period, fill_method=None).mul(100).rename("ROC")


def stochastic_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    values = rsi(close, period)
    low, high = values.rolling(period).min(), values.rolling(period).max()
    return (100*(values-low)/(high-low).mask((high-low) == 0)).rename("STOCH_RSI")


def cci(frame: pd.DataFrame, period: int = 20) -> pd.Series:
    typical = (frame["High"]+frame["Low"]+frame["Close"])/3
    mean = sma(typical, period)
    deviation = typical.rolling(period).apply(lambda values: abs(values-values.mean()).mean(), raw=True)
    return ((typical-mean)/(0.015*deviation.mask(deviation == 0))).rename("CCI")
