import pandas as pd


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def sma(series: pd.Series, period: int) -> pd.Series:
    return _numeric(series).rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int, *, warmup: bool = False) -> pd.Series:
    minimum = period if warmup else 0
    return _numeric(series).ewm(span=period, adjust=False, min_periods=minimum).mean()


def wilder_rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder RMA; ilk değer period gözlemlik SMA tohumudur."""
    values = _numeric(series)
    out = pd.Series(float("nan"), index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < period:
        return out
    seed_position = values.index.get_loc(valid.index[period - 1])
    seed_window = values.iloc[: seed_position + 1].dropna().iloc[-period:]
    previous = float(seed_window.mean())
    out.iloc[seed_position] = previous
    for position in range(seed_position + 1, len(values)):
        value = values.iloc[position]
        if pd.isna(value):
            continue
        previous = ((previous * (period - 1)) + float(value)) / period
        out.iloc[position] = previous
    return out
