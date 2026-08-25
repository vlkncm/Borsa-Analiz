import pandas as pd


def classic_pivot(previous_high: float, previous_low: float, previous_close: float) -> dict[str, float]:
    pivot = (float(previous_high)+float(previous_low)+float(previous_close))/3
    return {"P": pivot, "R1": 2*pivot-float(previous_low), "S1": 2*pivot-float(previous_high), "R2": pivot+float(previous_high)-float(previous_low), "S2": pivot-float(previous_high)+float(previous_low)}


def pivot_series(daily: pd.DataFrame) -> pd.DataFrame:
    previous = daily[["High", "Low", "Close"]].shift(1)
    pivot = (previous.High+previous.Low+previous.Close)/3
    return pd.DataFrame({"P": pivot, "R1": 2*pivot-previous.Low, "S1": 2*pivot-previous.High, "R2": pivot+previous.High-previous.Low, "S2": pivot-previous.High+previous.Low}, index=daily.index)


def session_vwap(intraday: pd.DataFrame) -> pd.Series:
    if intraday is None or intraday.empty:
        return pd.Series(index=getattr(intraday, "index", None), dtype=float, name="VWAP")
    volume = pd.to_numeric(intraday["Volume"], errors="coerce")
    typical = (intraday["High"]+intraday["Low"]+intraday["Close"])/3
    sessions = pd.Series(intraday.index.date, index=intraday.index)
    numerator = (typical*volume).groupby(sessions).cumsum()
    denominator = volume.groupby(sessions).cumsum().mask(lambda value: value <= 0)
    return (numerator/denominator).rename("VWAP")
