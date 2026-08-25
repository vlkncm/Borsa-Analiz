import pandas as pd


def obv(frame: pd.DataFrame) -> pd.Series:
    direction = frame["Close"].diff().fillna(0).apply(lambda value: 1 if value > 0 else (-1 if value < 0 else 0))
    return (direction*frame["Volume"].fillna(0)).cumsum().rename("OBV")


def cmf(frame: pd.DataFrame, period: int = 20) -> pd.Series:
    spread = (frame["High"]-frame["Low"]).mask(lambda value: value == 0)
    multiplier = ((frame["Close"]-frame["Low"])-(frame["High"]-frame["Close"]))/spread
    return ((multiplier*frame["Volume"]).rolling(period).sum()/frame["Volume"].rolling(period).sum().mask(lambda value: value == 0)).rename("CMF")


def mfi(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    typical = (frame["High"]+frame["Low"]+frame["Close"])/3
    flow = typical*frame["Volume"]
    positive = flow.where(typical.diff() > 0, 0).rolling(period).sum()
    negative = flow.where(typical.diff() < 0, 0).rolling(period).sum()
    ratio = positive/negative.mask(negative == 0)
    result = 100-100/(1+ratio)
    return result.mask((negative == 0) & (positive > 0), 100.0).rename("MFI")
