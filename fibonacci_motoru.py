from __future__ import annotations

from typing import Dict
import numpy as np
import pandas as pd


ORANLAR = {
    "23.6": 0.236,
    "38.2": 0.382,
    "50.0": 0.500,
    "61.8": 0.618,
    "78.6": 0.786,
}


def _f(value, default=0.0) -> float:
    try:
        number = float(value)
        return default if np.isnan(number) or np.isinf(number) else number
    except Exception:
        return default


def fibonacci_analizi(df: pd.DataFrame, lookback: int = 120) -> Dict[str, object]:
    """
    Son anlamlı fiyat salınımından Fibonacci geri çekilme seviyeleri üretir.
    Bu bir tahmin değil, teknik seviye hesaplamasıdır.
    """
    if df is None or df.empty or len(df) < 40:
        return _bos("Yeterli fiyat geçmişi bulunamadı.")

    data = df.tail(min(lookback, len(df))).copy()
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    close = data["Close"].astype(float)
    price = _f(close.iloc[-1])

    high_pos = int(np.argmax(high.to_numpy()))
    low_pos = int(np.argmin(low.to_numpy()))
    swing_high = _f(high.iloc[high_pos])
    swing_low = _f(low.iloc[low_pos])

    if swing_high <= swing_low or price <= 0:
        return _bos("Geçerli swing tepe/dip bulunamadı.")

    uptrend = low_pos < high_pos
    span = swing_high - swing_low

    if uptrend:
        levels = {k: swing_high - span * ratio for k, ratio in ORANLAR.items()}
        trend = "YÜKSELİŞ"
    else:
        levels = {k: swing_low + span * ratio for k, ratio in ORANLAR.items()}
        trend = "DÜŞÜŞ"

    ordered = sorted(levels.items(), key=lambda x: x[1])
    below = [(name, level) for name, level in ordered if level <= price]
    above = [(name, level) for name, level in ordered if level > price]

    support_name, support = below[-1] if below else ("Swing Dip", swing_low)
    resistance_name, resistance = above[0] if above else ("Swing Tepe", swing_high)

    # Seviyeye yakınlık ATR yerine salınımın yüzdesiyle normalize edilir.
    tolerance = max(span * 0.018, price * 0.006)
    touches = {}
    for name, level in levels.items():
        distances = (close - level).abs()
        touches[name] = int((distances <= tolerance).sum())

    nearest_name, nearest_level = min(levels.items(), key=lambda x: abs(price - x[1]))
    nearest_distance = abs(price - nearest_level) / price * 100

    score = 50
    note_parts = []
    if trend == "YÜKSELİŞ":
        score += 8
    if support_name in {"38.2", "50.0", "61.8"} and price >= support:
        score += 12
        note_parts.append(f"Fiyat %{support_name} Fibonacci desteğinin üzerinde.")
    if nearest_distance <= 1.5:
        score += 8
        note_parts.append(f"Fiyat %{nearest_name} seviyesine yakın.")
    if touches.get(nearest_name, 0) >= 3:
        score += 7
        note_parts.append(f"%{nearest_name} seviyesi geçmişte {touches[nearest_name]} kez test edilmiş.")
    if price > swing_high:
        score += 10
        note_parts.append("Swing tepe üzerinde kırılım var.")
    if price < swing_low:
        score -= 20
        note_parts.append("Swing dip aşağı kırılmış.")

    score = int(max(0, min(95, score)))
    status = "POZİTİF" if score >= 68 else "NÖTR" if score >= 48 else "NEGATİF"

    return {
        "fib_trend": trend,
        "fib_swing_dip": round(swing_low, 2),
        "fib_swing_tepe": round(swing_high, 2),
        "fib_23_6": round(levels["23.6"], 2),
        "fib_38_2": round(levels["38.2"], 2),
        "fib_50": round(levels["50.0"], 2),
        "fib_61_8": round(levels["61.8"], 2),
        "fib_78_6": round(levels["78.6"], 2),
        "fib_destek": round(support, 2),
        "fib_destek_adi": support_name,
        "fib_direnc": round(resistance, 2),
        "fib_direnc_adi": resistance_name,
        "fib_en_yakin": nearest_name,
        "fib_en_yakin_fiyat": round(nearest_level, 2),
        "fib_test_sayisi": touches.get(nearest_name, 0),
        "fib_puani": score,
        "fib_durum": status,
        "fib_yorum": " ".join(note_parts) if note_parts else "Fibonacci seviyelerinde belirgin ek teyit yok.",
    }


def _bos(note: str) -> Dict[str, object]:
    return {
        "fib_trend": "VERİ YOK",
        "fib_swing_dip": 0.0,
        "fib_swing_tepe": 0.0,
        "fib_23_6": 0.0,
        "fib_38_2": 0.0,
        "fib_50": 0.0,
        "fib_61_8": 0.0,
        "fib_78_6": 0.0,
        "fib_destek": 0.0,
        "fib_destek_adi": "",
        "fib_direnc": 0.0,
        "fib_direnc_adi": "",
        "fib_en_yakin": "",
        "fib_en_yakin_fiyat": 0.0,
        "fib_test_sayisi": 0,
        "fib_puani": 0,
        "fib_durum": "VERİ YOK",
        "fib_yorum": note,
    }
