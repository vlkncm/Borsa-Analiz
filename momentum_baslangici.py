"""Açıklanabilir *Yeni Momentum Başlangıcı* kanıt katmanı.

Bu modül karar motorunun yerine geçmez. ``sinyal_pipeline.daily_features``
tarafından üretilen kanonik göstergeleri kullanır ve yalnızca geçmişte mevcut
olan mumlarla bir momentum kurulumu sınıflandırır.
"""
from __future__ import annotations

from typing import Any
import math
import pandas as pd


CLASSES = {
    "MOMENTUM_YOK", "MOMENTUM_HAZIRLIK", "YENI_MOMENTUM_BASLANGICI",
    "GUCLU_MOMENTUM_TEYIDI", "HAREKET_ILERLEMIS", "VERI_YETERSIZ",
}


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _crossed_up(series: pd.Series, level: float = 0.0, bars: int = 3) -> tuple[bool, int | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < bars + 1:
        return False, None
    recent = values.iloc[-(bars + 1):]
    for offset in range(1, len(recent)):
        if recent.iloc[offset - 1] <= level < recent.iloc[offset]:
            return True, len(recent) - 1 - offset
    return False, None


def evaluate_momentum_start(features: pd.DataFrame) -> dict[str, Any]:
    """Evaluate the latest completed bar without producing an AL decision."""
    if features is None or len(features) < 60:
        return {"momentum_setup": "VERI_YETERSIZ", "momentum_score": None,
                "momentum_reasons": [], "momentum_risks": ["En az 60 tamamlanmış mum gerekli."],
                "decision_hint": "VERİ YETERSİZ"}
    row = features.iloc[-1]
    required = ("Close", "EMA20", "EMA50", "MACD", "MACD_SIGNAL", "MACD_HIST", "ADX", "PLUS_DI", "MINUS_DI", "RSI", "ATR")
    if any(_num(row.get(name)) is None for name in required):
        return {"momentum_setup": "VERI_YETERSIZ", "momentum_score": None,
                "momentum_reasons": [], "momentum_risks": ["Temel göstergeler eksik."],
                "decision_hint": "VERİ YETERSİZ"}

    close, ema20, ema50 = map(lambda n: _num(row[n]), ("Close", "EMA20", "EMA50"))
    rsi, adx, atr = map(lambda n: _num(row[n]), ("RSI", "ADX", "ATR"))
    macd, signal, hist = map(lambda n: _num(row[n]), ("MACD", "MACD_SIGNAL", "MACD_HIST"))
    plus_di, minus_di = _num(row["PLUS_DI"]), _num(row["MINUS_DI"])
    reasons: list[str] = []; risks: list[str] = []
    trend_points = 0; trigger_points = 0; strength_points = 0
    flow_points = 0; quality_points = 0; context_points = 0
    if close > ema20 and ema20 > ema50:
        trend_points = 25; reasons.append("Fiyat EMA20 üzerinde ve kısa trend hazırlanıyor.")
    elif close > ema20 or ema20 > ema50:
        trend_points = 12; reasons.append("Trend hazırlığı kısmi.")
    else:
        risks.append("Fiyat/EMA trend hazırlığı yok.")

    zero_cross, age = _crossed_up(features["MACD"], 0.0, 3)
    hist_cross, hist_age = _crossed_up(features["MACD_HIST"], 0.0, 3)
    hist_rising = len(features) >= 2 and _num(features["MACD_HIST"].iloc[-2]) is not None and hist > _num(features["MACD_HIST"].iloc[-2])
    if zero_cross or (hist_cross and hist_rising):
        trigger_points = 20; reasons.append("MACD son 1–3 tamamlanmış mumda yeni yukarı tetik verdi.")
    elif macd > signal and hist_rising:
        trigger_points = 8; reasons.append("MACD olumlu ve histogram güçleniyor; yeni kesişim teyidi bekleniyor.")
    else:
        risks.append("Yeni MACD tetikleyicisi yok.")

    adx_prev = _num(features["ADX"].iloc[-2]) if len(features) >= 2 else None
    adx_rising = adx_prev is not None and adx > adx_prev
    if adx > 18:
        strength_points = 15 if adx_rising and plus_di > minus_di else 10
        reasons.append("Trend gücü 18 eşiğinin üzerinde.")
    else:
        risks.append("ADX 18 altında; trend gücü yetersiz.")
    if not adx_rising and adx > 18:
        risks.append("ADX yüksek ancak yükselmiyor.")

    if 50 <= rsi <= 68:
        quality_points += 5; reasons.append("RSI yeni hareket için sağlıklı aralıkta.")
    elif 68 < rsi <= 75:
        risks.append("RSI yükseldi; geç giriş riski artıyor.")
    elif rsi > 75:
        risks.append("RSI aşırı yüksek; hareket ilerlemiş olabilir.")
    else:
        risks.append("RSI yeni momentum aralığında değil.")

    rvol = _num(row.get("RVOL_COMPLETED20"))
    if rvol is not None and rvol >= 1.2:
        flow_points += 12; reasons.append("Hacim, önceki tamamlanmış 20 mum ortalamasının üzerinde.")
    else:
        risks.append("Göreceli hacim teyidi zayıf veya eksik.")
    clv = _num(row.get("CLV")); cmf = _num(row.get("CMF")); obv_now = _num(row.get("OBV")); obv_prev = _num(features["OBV"].iloc[-3]) if "OBV" in features and len(features) >= 3 else None
    if clv is not None and clv >= .65: quality_points += 3; reasons.append("Kapanış günlük aralığın üst bölümünde.")
    if cmf is not None and cmf > 0: flow_points += 4; reasons.append("Para akışı pozitif.")
    if obv_now is not None and obv_prev is not None and obv_now > obv_prev: flow_points += 4
    if plus_di > minus_di: strength_points = min(15, strength_points + 2)

    distance = _num(row.get("EMA20_DISTANCE")); ret5 = _num(row.get("RET5")); move_atr = _num(row.get("MOVE_REALIZED_ATR"))
    overextended = ((distance is not None and distance > .08) or (ret5 is not None and ret5 > 15) or
                    (rsi > 75) or (move_atr is not None and move_atr > 3))
    if overextended:
        risks.append("Hareket EMA20/son 5 gün/ATR ölçüsünde ilerlemiş.")
    else:
        quality_points += 2
    score = max(0, min(100, trend_points + trigger_points + strength_points + flow_points + quality_points + context_points))
    if overextended:
        setup = "HAREKET_ILERLEMIS"
    elif trigger_points >= 20 and trend_points == 25 and strength_points >= 10 and flow_points >= 12:
        setup = "GUCLU_MOMENTUM_TEYIDI"
    elif trigger_points >= 20 and trend_points >= 12:
        setup = "YENI_MOMENTUM_BASLANGICI"
    elif trend_points or trigger_points or flow_points:
        setup = "MOMENTUM_HAZIRLIK"
    else:
        setup = "MOMENTUM_YOK"
    return {
        "momentum_setup": setup, "momentum_score": score,
        "momentum_trigger_date": str(features.index[-1]) if trigger_points else None,
        "momentum_age_bars": age if zero_cross else hist_age if hist_cross else None,
        "momentum_reasons": reasons, "momentum_risks": risks,
        "overextension_status": "GEÇ GİRİŞ RİSKİ" if overextended else "AŞIRI İLERLEMEMİŞ",
        "volume_confirmation": bool(rvol is not None and rvol >= 1.2),
        "trend_confirmation": bool(close > ema20 and ema20 > ema50 and adx > 18 and plus_di > minus_di),
        "decision_hint": "BEKLE", "takas_durumu": "Takas/kurumsal dağılım doğrulanamadı",
    }


def momentum_for_frame(features: pd.DataFrame) -> pd.DataFrame:
    """Attach one independent, explainable result per symbol row/frame."""
    result = evaluate_momentum_start(features)
    out = features.copy()
    for key, value in result.items():
        out[key] = value
    return out

