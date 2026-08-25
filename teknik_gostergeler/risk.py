import math
import pandas as pd


def sharpe(returns: pd.Series, periods: int = 252) -> float:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    volatility = values.std(ddof=0)
    return float(values.mean()/volatility*math.sqrt(periods)) if volatility > 0 else 0.0


def sortino(returns: pd.Series, periods: int = 252) -> float:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    downside = values.where(values < 0, 0).std(ddof=0)
    return float(values.mean()/downside*math.sqrt(periods)) if downside > 0 else 0.0


def beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    aligned = pd.concat([stock_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 2:
        return None
    variance = aligned.iloc[:, 1].var()
    return float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1])/variance) if variance > 0 else None
