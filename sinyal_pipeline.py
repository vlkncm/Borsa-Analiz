"""Canlı tarama ve backtest için ortak, sürümlü günlük feature/sinyal pipeline'ı."""
from __future__ import annotations
import pandas as pd
from teknik_gostergeler import adx, atr, ema, macd, rsi, sma, bollinger_bands, obv, cmf, mfi
from teknik_gostergeler.ayarlar import IndicatorConfig

FORMULA_VERSION = "technical_indicators_v10_2"
STRATEGY_VERSION = "daily_trend_v10_2"


def daily_features(frame: pd.DataFrame, config: IndicatorConfig | None = None) -> pd.DataFrame:
    cfg = config or IndicatorConfig()
    out = frame.copy()
    out["RSI"] = rsi(out["Close"], cfg.rsi_period)
    out["EMA20"], out["EMA50"], out["EMA200"] = ema(out["Close"], 20), ema(out["Close"], 50), ema(out["Close"], 200)
    out["SMA200"] = sma(out["Close"], 200)
    out["VOLUME_MA20"] = sma(out["Volume"], 20)
    # Momentum başlangıcı için göreceli hacim, bugünkü hacmi önceki
    # tamamlanmış 20 mumun ortalamasıyla karşılaştırır; bugünkü mum ortalamaya
    # dahil edilmez.
    out["RVOL_COMPLETED20"] = out["Volume"] / out["Volume"].shift(1).rolling(20, min_periods=20).mean()
    macd_values = macd(out["Close"], cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    out[["MACD", "MACD_SIGNAL", "MACD_HIST"]] = macd_values
    out["ATR"] = atr(out, cfg.atr_period)
    adx_values = adx(out, cfg.adx_period)
    out[["PLUS_DI", "MINUS_DI", "ADX"]] = adx_values
    out["RET20"], out["RET60"], out["RET252"] = (out["Close"].pct_change(p, fill_method=None)*100 for p in (20, 60, 252))
    out["RET3"], out["RET5"] = (out["Close"].pct_change(p, fill_method=None)*100 for p in (3, 5))
    out["CLV"] = ((2*out["Close"]-out["High"]-out["Low"]) /
                   (out["High"]-out["Low"]).replace(0, pd.NA)).astype(float)
    out["OBV"] = obv(out)
    out["CMF"] = cmf(out)
    out["MFI"] = mfi(out)
    out = out.join(bollinger_bands(out["Close"]), how="left")
    out["EMA20_DISTANCE"] = out["Close"] / out["EMA20"] - 1
    out["MOVE_REALIZED_ATR"] = (out["Close"]-out["Close"].shift(3)).abs() / out["ATR"].replace(0, pd.NA)
    out.attrs.update({"formula_version": FORMULA_VERSION, "strategy_version": STRATEGY_VERSION})
    return out


def daily_raw_signal(features: pd.DataFrame) -> pd.Series:
    base = ((features["Close"] > features["EMA20"]) & (features["EMA20"] > features["EMA50"])
            & (features["MACD"] > features["MACD_SIGNAL"]) & features["RSI"].between(45, 68))
    crossover = (features["MACD"].shift(1) <= features["MACD_SIGNAL"].shift(1)) & (features["MACD"] > features["MACD_SIGNAL"])
    warm = features[["RSI", "EMA20", "EMA50", "MACD", "MACD_SIGNAL", "ATR"]].notna().all(axis=1)
    return (base & crossover & warm).rename("RAW_SIGNAL")
