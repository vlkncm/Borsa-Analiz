from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class Pattern:
    name: str
    direction: str
    confidence: int
    confirmed: bool
    breakout: float
    target: float
    stop: float
    note: str


def _safe_float(value, default=0.0) -> float:
    try:
        number = float(value)
        return default if np.isnan(number) or np.isinf(number) else number
    except Exception:
        return default


def _local_extrema(series: pd.Series, order: int = 3) -> Tuple[List[int], List[int]]:
    values = series.to_numpy(dtype=float)
    peaks, troughs = [], []
    if len(values) < order * 2 + 1:
        return peaks, troughs

    for i in range(order, len(values) - order):
        window = values[i - order:i + order + 1]
        if values[i] == np.max(window) and np.sum(window == values[i]) == 1:
            peaks.append(i)
        if values[i] == np.min(window) and np.sum(window == values[i]) == 1:
            troughs.append(i)
    return peaks, troughs


def _similar(a: float, b: float, tolerance: float = 0.04) -> bool:
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base <= tolerance


def _volume_confirm(df: pd.DataFrame, lookback: int = 20, ratio: float = 1.15) -> bool:
    if "Volume" not in df.columns or len(df) < lookback + 1:
        return False
    current = _safe_float(df["Volume"].iloc[-1])
    average = _safe_float(df["Volume"].iloc[-lookback-1:-1].mean())
    return average > 0 and current >= average * ratio


def _pattern(
    name: str, direction: str, base_conf: int, confirmed: bool,
    breakout: float, target: float, stop: float, note: str,
    volume_ok: bool = False
) -> Pattern:
    confidence = base_conf + (12 if confirmed else 0) + (8 if volume_ok else 0)
    return Pattern(
        name=name,
        direction=direction,
        confidence=int(max(0, min(95, confidence))),
        confirmed=confirmed,
        breakout=round(breakout, 2),
        target=round(target, 2),
        stop=round(stop, 2),
        note=note,
    )


def _double_bottom(df: pd.DataFrame, troughs: List[int]) -> Optional[Pattern]:
    if len(troughs) < 2:
        return None
    close = df["Close"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    t1, t2 = troughs[-2], troughs[-1]
    if t2 - t1 < 8 or not _similar(low[t1], low[t2], 0.045):
        return None
    neckline = float(np.max(close[t1:t2 + 1]))
    price = float(close[-1])
    confirmed = price > neckline
    height = neckline - min(low[t1], low[t2])
    target = neckline + height
    stop = min(low[t1], low[t2]) * 0.98
    return _pattern(
        "İkili Dip", "YUKARI", 58, confirmed, neckline, target, stop,
        "Aynı destek bölgesi iki kez test edildi; boyun çizgisi kırılımı teyit sayılır.",
        _volume_confirm(df)
    )


def _double_top(df: pd.DataFrame, peaks: List[int]) -> Optional[Pattern]:
    if len(peaks) < 2:
        return None
    close = df["Close"].to_numpy(dtype=float)
    high = df["High"].to_numpy(dtype=float)
    p1, p2 = peaks[-2], peaks[-1]
    if p2 - p1 < 8 or not _similar(high[p1], high[p2], 0.045):
        return None
    neckline = float(np.min(close[p1:p2 + 1]))
    price = float(close[-1])
    confirmed = price < neckline
    height = max(high[p1], high[p2]) - neckline
    target = max(0.01, neckline - height)
    stop = max(high[p1], high[p2]) * 1.02
    return _pattern(
        "İkili Tepe", "AŞAĞI", 58, confirmed, neckline, target, stop,
        "Benzer seviyede iki tepe oluştu; boyun çizgisi aşağı kırılırsa teyit edilir.",
        _volume_confirm(df)
    )


def _triple(df: pd.DataFrame, extrema: List[int], kind: str) -> Optional[Pattern]:
    if len(extrema) < 3:
        return None
    close = df["Close"].to_numpy(dtype=float)
    source = df["Low"].to_numpy(dtype=float) if kind == "bottom" else df["High"].to_numpy(dtype=float)
    a, b, c = extrema[-3:]
    if min(b - a, c - b) < 6:
        return None
    vals = [source[a], source[b], source[c]]
    if not (_similar(vals[0], vals[1], 0.05) and _similar(vals[1], vals[2], 0.05)):
        return None

    if kind == "bottom":
        neckline = float(max(np.max(close[a:b + 1]), np.max(close[b:c + 1])))
        confirmed = float(close[-1]) > neckline
        height = neckline - min(vals)
        return _pattern(
            "Üçlü Dip", "YUKARI", 64, confirmed, neckline,
            neckline + height, min(vals) * 0.98,
            "Aynı destek bölgesi üç kez test edildi.", _volume_confirm(df)
        )

    neckline = float(min(np.min(close[a:b + 1]), np.min(close[b:c + 1])))
    confirmed = float(close[-1]) < neckline
    height = max(vals) - neckline
    return _pattern(
        "Üçlü Tepe", "AŞAĞI", 64, confirmed, neckline,
        max(0.01, neckline - height), max(vals) * 1.02,
        "Aynı direnç bölgesi üç kez test edildi.", _volume_confirm(df)
    )


def _head_shoulders(df: pd.DataFrame, extrema: List[int], inverse: bool = False) -> Optional[Pattern]:
    if len(extrema) < 3:
        return None
    close = df["Close"].to_numpy(dtype=float)
    source = df["Low"].to_numpy(dtype=float) if inverse else df["High"].to_numpy(dtype=float)
    a, b, c = extrema[-3:]
    if min(b - a, c - b) < 6:
        return None

    left, head, right = source[a], source[b], source[c]
    shoulders_ok = _similar(left, right, 0.07)
    head_ok = head < min(left, right) * 0.94 if inverse else head > max(left, right) * 1.06
    if not shoulders_ok or not head_ok:
        return None

    if inverse:
        neckline = float(max(np.max(close[a:b + 1]), np.max(close[b:c + 1])))
        confirmed = float(close[-1]) > neckline
        height = neckline - head
        return _pattern(
            "Ters Omuz Baş Omuz (TOBO)", "YUKARI", 68, confirmed,
            neckline, neckline + height, head * 0.98,
            "Ortadaki dip baş, iki yandaki benzer dipler omuz görünümünde.",
            _volume_confirm(df)
        )

    neckline = float(min(np.min(close[a:b + 1]), np.min(close[b:c + 1])))
    confirmed = float(close[-1]) < neckline
    height = head - neckline
    return _pattern(
        "Omuz Baş Omuz (OBO)", "AŞAĞI", 68, confirmed,
        neckline, max(0.01, neckline - height), head * 1.02,
        "Ortadaki zirve baş, iki yandaki benzer zirveler omuz görünümünde.",
        _volume_confirm(df)
    )


def _cup_handle(df: pd.DataFrame) -> Optional[Pattern]:
    part = df.tail(100).copy()
    if len(part) < 60:
        return None
    close = part["Close"].to_numpy(dtype=float)
    left_high = float(np.max(close[:20]))
    right_high = float(np.max(close[-25:]))
    bottom_idx = int(np.argmin(close[15:-20])) + 15
    bottom = float(close[bottom_idx])

    if not _similar(left_high, right_high, 0.07):
        return None
    depth = (left_high - bottom) / max(left_high, 1e-9)
    if not 0.08 <= depth <= 0.40:
        return None

    handle = close[-15:]
    handle_low = float(np.min(handle))
    if handle_low < right_high * 0.88:
        return None

    breakout = max(left_high, right_high)
    confirmed = float(close[-1]) > breakout
    target = breakout + (breakout - bottom)
    return _pattern(
        "Fincan Kulp", "YUKARI", 62, confirmed, breakout, target,
        handle_low * 0.98,
        "U biçimli taban ve sağ tarafta sınırlı geri çekilme tespit edildi.",
        _volume_confirm(part)
    )


def _rounded(df: pd.DataFrame, inverse: bool = False) -> Optional[Pattern]:
    part = df.tail(100)
    if len(part) < 80:
        return None
    y = part["Close"].to_numpy(dtype=float)
    x = np.linspace(-1, 1, len(y))
    coef = np.polyfit(x, y, 2)
    fit = np.polyval(coef, x)
    ss_res = np.sum((y - fit) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    curvature = coef[0] / max(np.mean(y), 1e-9)

    if r2 < 0.45:
        return None
    if inverse and curvature >= -0.04:
        return None
    if not inverse and curvature <= 0.04:
        return None

    breakout = float(np.max(y[:15])) if not inverse else float(np.min(y[:15]))
    price = float(y[-1])
    confirmed = price > breakout if not inverse else price < breakout
    amplitude = float(np.max(y) - np.min(y))
    target = breakout + amplitude if not inverse else max(0.01, breakout - amplitude)
    stop = float(np.min(y)) * 0.98 if not inverse else float(np.max(y)) * 1.02
    return _pattern(
        "Ters Çanak" if inverse else "Çanak",
        "AŞAĞI" if inverse else "YUKARI",
        48, confirmed, breakout, target, stop,
        "Fiyat eğrisi uzun dönemli yuvarlak dönüş yapısına benziyor.",
        _volume_confirm(part)
    )


def _wedge_or_flag(df: pd.DataFrame) -> List[Pattern]:
    results: List[Pattern] = []
    part = df.tail(35)
    if len(part) < 25:
        return results

    x = np.arange(len(part), dtype=float)
    high = part["High"].to_numpy(dtype=float)
    low = part["Low"].to_numpy(dtype=float)
    close = part["Close"].to_numpy(dtype=float)
    hs, hi = np.polyfit(x, high, 1)
    ls, li = np.polyfit(x, low, 1)
    width_start = (hs * x[0] + hi) - (ls * x[0] + li)
    width_end = (hs * x[-1] + hi) - (ls * x[-1] + li)
    narrowing = width_start > 0 and width_end < width_start * 0.72
    price = float(close[-1])
    upper = float(hs * x[-1] + hi)
    lower = float(ls * x[-1] + li)
    volume_ok = _volume_confirm(part)

    if narrowing and hs < 0 and ls < 0:
        confirmed = price > upper
        results.append(_pattern(
            "Düşen Kama", "YUKARI", 56, confirmed, upper,
            price + max(width_start, 0), lower * 0.98,
            "Aşağı yönlü daralan fiyat kanalı tespit edildi.", volume_ok
        ))
    elif narrowing and hs > 0 and ls > 0:
        confirmed = price < lower
        results.append(_pattern(
            "Yükselen Kama", "AŞAĞI", 56, confirmed, lower,
            max(0.01, price - max(width_start, 0)), upper * 1.02,
            "Yukarı yönlü daralan fiyat kanalı tespit edildi.", volume_ok
        ))

    # Bayrak / flama için önceki 15 günde güçlü direk, son 20 günde konsolidasyon.
    if len(df) >= 45:
        pole = df["Close"].iloc[-45:-20]
        pole_return = _safe_float(pole.iloc[-1] / pole.iloc[0] - 1)
        recent_range = (np.max(close) - np.min(close)) / max(np.mean(close), 1e-9)

        if abs(pole_return) >= 0.12 and recent_range <= 0.14:
            direction = "YUKARI" if pole_return > 0 else "AŞAĞI"
            if narrowing:
                name = "Flama"
            elif abs(hs - ls) <= max(abs(hs), abs(ls), 1e-9) * 0.35:
                name = "Bayrak"
            else:
                name = ""

            if name:
                confirmed = price > upper if direction == "YUKARI" else price < lower
                pole_size = abs(float(pole.iloc[-1] - pole.iloc[0]))
                target = price + pole_size if direction == "YUKARI" else max(0.01, price - pole_size)
                stop = lower * 0.98 if direction == "YUKARI" else upper * 1.02
                results.append(_pattern(
                    name, direction, 54, confirmed,
                    upper if direction == "YUKARI" else lower,
                    target, stop,
                    "Güçlü fiyat hareketi sonrası kısa konsolidasyon tespit edildi.",
                    volume_ok
                ))
    return results


def formasyonlari_tespit_et(df: pd.DataFrame) -> Dict[str, object]:
    required = {"Open", "High", "Low", "Close", "Volume"}
    if df is None or df.empty or not required.issubset(df.columns) or len(df) < 60:
        return {
            "formasyon": "Belirgin formasyon yok",
            "formasyon_puani": 0,
            "formasyon_notu": "Formasyon analizi için yeterli veri bulunamadı.",
            "formasyon_yonu": "NÖTR",
            "formasyon_teyit": "Hayır",
            "formasyon_kirilim": 0.0,
            "formasyon_hedef": 0.0,
            "formasyon_stop": 0.0,
            "formasyon_adaylari": "",
        }

    data = df.tail(140).copy().dropna(subset=["High", "Low", "Close"])
    peaks, troughs = _local_extrema(data["Close"], order=3)
    candidates: List[Pattern] = []

    detectors = [
        _double_bottom(data, troughs),
        _double_top(data, peaks),
        _triple(data, troughs, "bottom"),
        _triple(data, peaks, "top"),
        _head_shoulders(data, peaks, inverse=False),
        _head_shoulders(data, troughs, inverse=True),
        _cup_handle(data),
        _rounded(data, inverse=False),
        _rounded(data, inverse=True),
    ]
    candidates.extend([p for p in detectors if p is not None])
    candidates.extend(_wedge_or_flag(data))

    if not candidates:
        return {
            "formasyon": "Belirgin formasyon yok",
            "formasyon_puani": 0,
            "formasyon_notu": "Tanımlı formasyon eşikleri karşılanmadı.",
            "formasyon_yonu": "NÖTR",
            "formasyon_teyit": "Hayır",
            "formasyon_kirilim": 0.0,
            "formasyon_hedef": 0.0,
            "formasyon_stop": 0.0,
            "formasyon_adaylari": "",
        }

    candidates.sort(key=lambda p: (p.confirmed, p.confidence), reverse=True)
    best = candidates[0]
    others = ", ".join(
        f"{p.name} %{p.confidence}" for p in candidates[1:4]
    )

    return {
        "formasyon": best.name,
        "formasyon_puani": best.confidence,
        "formasyon_notu": best.note,
        "formasyon_yonu": best.direction,
        "formasyon_teyit": "Evet" if best.confirmed else "Bekleniyor",
        "formasyon_kirilim": best.breakout,
        "formasyon_hedef": best.target,
        "formasyon_stop": best.stop,
        "formasyon_adaylari": others,
    }
