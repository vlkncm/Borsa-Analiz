"""Ham OHLCV ile motor göstergelerini bağımsız olarak karşılaştıran denetim aracı."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from scan_candidate_policy import safe_risk_reward, safe_trade_plan
from sinyal_pipeline import daily_features
from veri_saglayici import completed_daily_frame, get_daily_ohlcv


AUDIT_COLUMNS = ("RSI", "EMA20", "EMA50", "EMA200", "MACD", "MACD_SIGNAL", "ATR", "ADX", "RET20", "RET60", "RET252", "RVOL_COMPLETED20")


def _rma(values: pd.Series, period: int) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < period:
        return result
    position = values.index.get_loc(valid.index[period - 1])
    previous = float(values.iloc[:position + 1].dropna().iloc[-period:].mean())
    result.iloc[position] = previous
    for index in range(position + 1, len(values)):
        if pd.isna(values.iloc[index]):
            continue
        previous = (previous * (period - 1) + float(values.iloc[index])) / period
        result.iloc[index] = previous
    return result


def independent_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Independent reference implementation; imports no indicator functions."""
    out = frame.copy()
    close = pd.to_numeric(out["Close"], errors="coerce")
    high = pd.to_numeric(out["High"], errors="coerce")
    low = pd.to_numeric(out["Low"], errors="coerce")
    volume = pd.to_numeric(out["Volume"], errors="coerce")
    delta = close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    avg_gain, avg_loss = _rma(gain, 14), _rma(loss, 14)
    ratio = avg_gain / avg_loss.mask(avg_loss.eq(0))
    out["RSI"] = (100 - 100 / (1 + ratio)).mask(avg_loss.eq(0) & avg_gain.gt(0), 100.0)
    for period in (20, 50, 200):
        out[f"EMA{period}"] = close.ewm(span=period, adjust=False, min_periods=0).mean()
    fast = close.ewm(span=12, adjust=False, min_periods=0).mean()
    slow = close.ewm(span=26, adjust=False, min_periods=0).mean()
    out["MACD"] = fast - slow
    out["MACD_SIGNAL"] = out["MACD"].ewm(span=9, adjust=False, min_periods=0).mean()
    previous = close.shift(1)
    tr = pd.concat((high - low, (high - previous).abs(), (low - previous).abs()), axis=1).max(axis=1)
    out["ATR"] = _rma(tr, 14)
    up, down = high.diff(), -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    smoothed_tr = _rma(tr, 14).mask(lambda value: value == 0)
    plus_di = 100 * _rma(plus_dm, 14) / smoothed_tr
    minus_di = 100 * _rma(minus_dm, 14) / smoothed_tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).mask(lambda value: value == 0)
    out["ADX"] = _rma(dx, 14)
    for period in (20, 60, 252):
        out[f"RET{period}"] = close.pct_change(period, fill_method=None) * 100
    out["RVOL_COMPLETED20"] = volume / volume.shift(1).rolling(20, min_periods=20).mean()
    return out


def _score_components(row: pd.Series) -> dict[str, float]:
    trend = 20.0 if row.Close > row.EMA20 > row.EMA50 else (10.0 if row.Close > row.EMA20 else 0.0)
    momentum = 15.0 if 45 <= row.RSI <= 68 else (7.0 if 35 <= row.RSI < 45 else 0.0)
    macd = 15.0 if row.MACD > row.MACD_SIGNAL else 0.0
    volume = min(15.0, max(0.0, (row.RVOL_COMPLETED20 - 1.0) * 15.0)) if pd.notna(row.RVOL_COMPLETED20) else 0.0
    adx = 10.0 if row.ADX >= 25 else (5.0 if row.ADX >= 18 else 0.0)
    returns = 10.0 if row.RET20 > 0 and row.RET60 > 0 else (5.0 if row.RET20 > 0 else 0.0)
    return {"trend": trend, "momentum": momentum, "macd": macd, "volume": volume, "adx": adx, "returns": returns}


def audit_symbol(symbol: str) -> dict:
    raw, metadata = get_daily_ohlcv(symbol, period="2y")
    complete = completed_daily_frame(raw, metadata.fetched_at)
    if complete.empty or len(complete) < 253:
        raise ValueError(f"{symbol}: bağımsız denetim için en az 253 tamamlanmış bar gerekli")
    motor = daily_features(complete)
    reference = independent_features(complete)
    actual, expected = motor.iloc[-1], reference.iloc[-1]
    differences = {name: abs(float(actual[name]) - float(expected[name])) for name in AUDIT_COLUMNS}
    support = float(complete["Low"].tail(20).min())
    resistance = float(complete["High"].tail(60).max())
    price, atr = float(expected["Close"]), float(expected["ATR"])
    plan = safe_trade_plan(price, np.nan, np.nan, atr=atr, support=support, resistance=resistance, strategy="short_term")
    rr = safe_risk_reward(price, plan.target, plan.stop)
    components = _score_components(expected)
    meta = asdict(metadata)
    return {
        "Hisse": symbol.replace(".IS", ""), "Son Veri": str(complete.index[-1]),
        "Open": float(expected.Open), "High": float(expected.High), "Low": float(expected.Low),
        "Fiyat": price, "Volume": float(expected.Volume), "Önceki Kapanış": float(complete.Close.iloc[-2]),
        "Günlük Değişim %": (price / float(complete.Close.iloc[-2]) - 1) * 100,
        **{name: float(expected[name]) for name in AUDIT_COLUMNS},
        "Destek": support, "Direnç": resistance, "Hedef": plan.target, "Stop": plan.stop,
        "Risk/Getiri": rr, "Plan Kaynağı": plan.source,
        "Skor Bileşenleri": " | ".join(f"{key}:{value:.1f}" for key, value in components.items()),
        "Toplam Skor": sum(components.values()), "Maks Gösterge Farkı": max(differences.values()),
        "Gösterge Sonucu": "UYUMLU" if max(differences.values()) < 1e-8 else "FARK VAR",
        "Veri Sağlayıcı": meta["source"], "fetched_at": str(meta["fetched_at"]),
        "last_bar_at": str(meta["last_bar_at"]), "delay_minutes": meta["delay_minutes"],
        "is_stale": meta["is_stale"], "is_complete_bar": meta["is_complete_bar"],
        "price_basis": meta["price_basis"], "corporate_action_warning": meta["corporate_action_warning"],
    }


def run_accuracy_audit(symbols: Iterable[str], output_dir: Path | None = None) -> pd.DataFrame:
    rows = []
    for symbol in symbols:
        try:
            rows.append(audit_symbol(symbol))
        except Exception as exc:
            rows.append({"Hisse": symbol.replace(".IS", ""), "Gösterge Sonucu": "HATA", "Hata": str(exc)})
    report = pd.DataFrame(rows)
    root = output_dir or Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "logs"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report.to_csv(root / f"data_accuracy_audit_{stamp}.csv", index=False, encoding="utf-8-sig")
    return report


if __name__ == "__main__":
    print(run_accuracy_audit(("ASELS.IS", "THYAO.IS", "AKBNK.IS", "EREGL.IS", "TUPRS.IS")).to_string(index=False))
