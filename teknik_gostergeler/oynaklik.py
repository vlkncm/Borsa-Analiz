import pandas as pd
from .ortak import sma, wilder_rma


def true_range(frame: pd.DataFrame) -> pd.Series:
    high = pd.to_numeric(frame["High"], errors="coerce")
    low = pd.to_numeric(frame["Low"], errors="coerce")
    previous_close = pd.to_numeric(frame["Close"], errors="coerce").shift()
    return pd.concat([high-low, (high-previous_close).abs(), (low-previous_close).abs()], axis=1).max(axis=1)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    return wilder_rma(true_range(frame), period).rename("ATR")


def bollinger_bands(close: pd.Series, period: int = 20, std_multiplier: float = 2.0, ddof: int = 0) -> pd.DataFrame:
    basis = sma(close, period)
    deviation = pd.to_numeric(close, errors="coerce").rolling(period, min_periods=period).std(ddof=ddof)
    upper, lower = basis + std_multiplier*deviation, basis - std_multiplier*deviation
    bbw = 100*(upper-lower)/basis.mask(basis == 0)
    return pd.DataFrame({"BB_MIDDLE": basis, "BB_UPPER": upper, "BB_LOWER": lower, "BBW": bbw}, index=close.index)
