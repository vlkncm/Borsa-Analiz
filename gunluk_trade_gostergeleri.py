"""Günlük trade için AlphaTrend + EMA + BBW + MACD-V teyitleri.

MACD-V: Alex Spiroglou'nun oynaklığa normalize yaklaşımı:
    100 * (EMA(12) - EMA(26)) / ATR(26)
Bu modül göstergeleri karar motoruna kanıt olarak verir; tek başına AL üretmez.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from mum_formasyonlari import mum_formasyonu_tespit
from teknik_gostergeler import atr as canonical_atr, bollinger_bands, ema, macd_v as canonical_macd_v, rsi as canonical_rsi


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    return canonical_rsi(close, period)


def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    return canonical_atr(frame, period)


def macd_v(frame: pd.DataFrame, fast: int = 12, slow: int = 26,
           signal: int = 9, atr_period: int = 26) -> pd.DataFrame:
    return canonical_macd_v(frame, fast, slow, signal, atr_period)


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
                "macd_v_sinyal": None, "macd_v_durumu": "VERİ YETERSİZ", "gunluk_trade_teyit": "VERİ YETERSİZ",
                "gunluk_trade_skoru": 0, "mum_formasyonu": "YOK", "mum_formasyon_yonu": "NÖTR",
                "mum_formasyon_teyit": False, "mum_formasyon_puani": 0, "mum_formasyon_nedeni": "Yetersiz veri"}
    data = frame[["Open", "High", "Low", "Close", "Volume"]].astype(float).copy()
    alpha = alpha_trend_rsi(data)
    mv = macd_v(data)
    close = data["Close"]
    ema20 = ema(close, 20)
    bbw = bollinger_bands(close, 20, 2.0, 0)["BBW"]
    quiet_threshold = bbw.rolling(120, min_periods=30).quantile(.25)
    last_bbw, last_threshold = float(bbw.iloc[-1]), float(quiet_threshold.iloc[-1])
    bbw_status = "YATAY / SIKIŞIK" if pd.notna(last_threshold) and last_bbw <= last_threshold else "HAREKETLİ"
    alpha_up = alpha.iloc[-1]["ALPHA_YON"] == "YUKARI"
    ema_up = close.iloc[-1] > ema20.iloc[-1] and ema20.iloc[-1] >= ema20.iloc[-2]
    macd_value, macd_signal = float(mv.iloc[-1]["MACD_V"]), float(mv.iloc[-1]["MACD_V_SIGNAL"])
    macd_status = "POZİTİF" if macd_value > macd_signal and macd_value > 0 else "NEGATİF / ZAYIF"
    pattern = mum_formasyonu_tespit(data)
    bullish_pattern = pattern["mum_formasyon_yonu"] == "YUKARI" and pattern["mum_formasyon_teyit"]
    bearish_pattern = pattern["mum_formasyon_yonu"] == "AŞAĞI"
    score = (20*int(alpha_up) + 20*int(ema_up) + 15*int(bbw_status == "HAREKETLİ") +
             30*int(macd_status == "POZİTİF") + 15*int(bullish_pattern) - 25*int(bearish_pattern))
    confirmed = alpha_up and ema_up and bbw_status == "HAREKETLİ" and macd_status == "POZİTİF" and not bearish_pattern
    return {
        "alpha_trend_yonu": str(alpha.iloc[-1]["ALPHA_YON"]),
        "ema20_durumu": "ÜSTÜNDE / YÜKSELİYOR" if ema_up else "TEYİTSİZ",
        "bbw_yuzde": last_bbw, "bbw_durumu": bbw_status,
        "macd_v": macd_value, "macd_v_sinyal": macd_signal, "macd_v_durumu": macd_status,
        "gunluk_trade_teyit": "4/4 TEYİTLİ" if confirmed else "TEYİT BEKLE",
        "gunluk_trade_skoru": max(0, min(100, score)), **pattern,
    }


def en_iyi_gunluk_trade_adaylari(frame: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    """Güncel ve pozitif hedefli sonuçları birleşik skorla sıralayıp en fazla 5 döndürür."""
    required = {"Günlük Trade Skoru", "Gün İçi Yükseliş %", "Veri Durumu"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=[] if frame is None else frame.columns)
    growth = pd.to_numeric(frame["Gün İçi Yükseliş %"], errors="coerce").fillna(0)
    score = pd.to_numeric(frame["Günlük Trade Skoru"], errors="coerce").fillna(0)
    valid = frame["Veri Durumu"].astype(str).eq("GÜVENİLİR") & growth.gt(0)
    return (frame[valid].assign(_skor=score[valid], _yukselis=growth[valid])
            .sort_values(["_skor", "_yukselis"], ascending=False).head(max(0, int(limit)))
            .drop(columns=["_skor", "_yukselis"]).reset_index(drop=True))
