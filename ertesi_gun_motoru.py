"""Tüm BIST için açıklanabilir, iki aşamalı T+1 aday motoru.

Referans skor olasılık değildir. Kalibre edilmiş örnek-dışı model artefaktı yoksa
yüzde alanları boş bırakılır; bu, sahte kesinlik üretilmesini engeller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Any

import numpy as np
import pandas as pd

from fiyat_limitleri import pay_fiyat_limitleri
from yeni_halka_arz import AYARLAR as IPO_AYARLARI, NEDEN_ACIKLAMALARI, model_yolu, yeni_halka_arz_analizi


ADAY_DURUMLARI = {"ERKEN BİRİKİM ADAYI", "GÜÇLÜ ERTESİ GÜN ADAYI", "TEYİT BEKLİYOR", "YÜKSEK RİSK", "VERİ YETERSİZ"}
CANLI_DURUMLARI = {"CANLI TEYİT GELDİ", "İZLE", "TEYİT GELMEDİ", "HAREKET KAÇTI – GİRİŞ RİSKLİ"}


@dataclass
class KalibrasyonKaniti:
    model_version: str = "referans-v1"
    calibrated: bool = False
    untouched_test_start: str | None = None
    untouched_test_end: str | None = None
    sample_count: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def guvenilir(self) -> bool:
        return self.calibrated and self.sample_count >= 200 and bool(self.untouched_test_start and self.untouched_test_end)


def _series(frame, name):
    return pd.to_numeric(frame[name], errors="coerce")


def teknik_ozellikler(frame: pd.DataFrame) -> dict[str, float]:
    """Yalnızca verilen T-kesimli günlük çerçeveden özellik çıkarır."""
    if frame is None or len(frame) < 60 or not {"High", "Low", "Close", "Volume"}.issubset(frame.columns):
        return {}
    close, high, low, volume = (_series(frame, c) for c in ("Close", "High", "Low", "Volume"))
    ema20, ema50, ema200 = (close.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    delta = close.diff(); up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); down = -delta.clip(upper=0).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / down.replace(0, np.nan))
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    typical = (high+low+close)/3
    money_flow = typical*volume
    positive = money_flow.where(typical.diff() > 0, 0).rolling(14).sum()
    negative = money_flow.where(typical.diff() < 0, 0).rolling(14).sum()
    mfi = 100 - 100/(1+positive/negative.replace(0, np.nan))
    mf_multiplier = ((close-low)-(high-close))/(high-low).replace(0, np.nan)
    cmf = (mf_multiplier*volume).rolling(20).sum()/volume.rolling(20).sum().replace(0, np.nan)
    obv = (np.sign(close.diff()).fillna(0)*volume).cumsum()
    macd = close.ewm(span=12, adjust=False).mean()-close.ewm(span=26, adjust=False).mean()
    # ADX tek başına yön belirtmez; +DI/-DI ayrı tutulur.
    up_move, down_move = high.diff(), -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14.replace(0, np.nan)
    dx = (100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/14, adjust=False).mean()
    mid = close.rolling(20).mean(); std = close.rolling(20).std(); width = 4*std/mid
    last = float(close.iloc[-1]); rng = float(high.iloc[-1]-low.iloc[-1])
    return {
        "price": last, "ret_1": float(close.pct_change(1).iloc[-1]), "ret_3": float(close.pct_change(3).iloc[-1]),
        "ret_5": float(close.pct_change(5).iloc[-1]), "ret_10": float(close.pct_change(10).iloc[-1]), "ret_20": float(close.pct_change(20).iloc[-1]),
        "ema20_distance": last/float(ema20.iloc[-1])-1, "ema50_distance": last/float(ema50.iloc[-1])-1,
        "ema200_distance": last/float(ema200.iloc[-1])-1 if len(frame) >= 200 else np.nan,
        "macd": float(macd.iloc[-1]), "macd_hist": float((macd-macd.ewm(span=9, adjust=False).mean()).iloc[-1]),
        "macd_hist_slope": float((macd-macd.ewm(span=9, adjust=False).mean()).diff().iloc[-1]),
        "rsi": float(rsi.iloc[-1]), "atr_pct": float(atr.iloc[-1]/last),
        "rsi_slope": float(rsi.diff(3).iloc[-1]), "ema20_slope": float(ema20.pct_change(5).iloc[-1]),
        "ema50_slope": float(ema50.pct_change(5).iloc[-1]),
        "adx14": float(adx.iloc[-1]), "plus_di": float(plus_di.iloc[-1]), "minus_di": float(minus_di.iloc[-1]),
        "bb_width": float(width.iloc[-1]), "bb_compression": float(width.iloc[-1]/width.rolling(60).median().iloc[-1]),
        "resistance20_distance": float(high.iloc[-20:].max()/last-1), "resistance60_distance": float(high.iloc[-60:].max()/last-1),
        "close_location": float((last-low.iloc[-1])/rng) if rng > 0 else .5,
        "relative_volume": float(volume.iloc[-1]/volume.iloc[-20:].mean()),
        "volume_persistence": float((volume.iloc[-5:] > volume.iloc[-20:].median()).mean()),
        "obv_slope": float(obv.diff(5).iloc[-1]/max(volume.iloc[-20:].mean(), 1)), "cmf": float(cmf.iloc[-1]), "mfi": float(mfi.iloc[-1]),
        "turnover": float(last*volume.iloc[-20:].mean()),
    }


def t1_movement_trade_scores(features: dict[str, float]) -> tuple[float, float, dict[str, float]]:
    """Hareket ihtimali ile işlem kalitesini ayırır; sert veto kullanmaz."""
    if not features:
        return 0.0, 0.0, {}
    f = features
    directional = 1.0 if f.get("plus_di", 0) > f.get("minus_di", 0) else -1.0
    close_strength = max(0.0, min(1.0, f.get("close_location", .5)))
    movement_parts = {
        "momentum": 24 * np.tanh(max(-.2, min(.2, f.get("ret_5", 0))) * 8),
        "momentum_acceleration": 10 * np.tanh(f.get("price_acceleration_2", 0) * 80),
        "relative_volume": 10 * np.tanh(f.get("relative_volume", 1) - 1),
        "volume_acceleration": 6 * np.tanh(f.get("volume_acceleration_2", 0) * 5),
        "breakout_proximity": 10 * max(0, 1 - min(1, f.get("resistance20_distance", 1) / .08)),
        "ema_slope": 8 * np.tanh(f.get("ema20_slope", 0) * 40) + 4 * np.tanh(f.get("ema50_slope", 0) * 40),
        "rsi_slope": 5 * np.tanh(f.get("rsi_slope", 0) / 5),
        "macd_acceleration": 6 * np.tanh(f.get("macd_hist_slope", 0) / max(f.get("atr_pct", .01), .001)),
        "adx_direction": 7 * np.tanh((f.get("adx14", 0)-18) / 12) * directional,
        "close_strength": 8 * (close_strength - .5),
    }
    movement_parts = {k: (0.0 if not math.isfinite(float(v)) else float(v)) for k, v in movement_parts.items()}
    movement = float(np.clip(50 + sum(movement_parts.values()), 0, 100))
    risk_penalty = 18 * min(1, max(0, f.get("atr_pct", 0) / .06))
    resistance_penalty = 10 * max(0, 1 - min(1, f.get("resistance20_distance", 1) / .02))
    trade = float(np.clip(movement - risk_penalty - resistance_penalty + (8 if directional > 0 else -8), 0, 100))
    return movement, trade, {k: round(float(v), 2) for k, v in movement_parts.items()}


def piyasa_rejimi(index_frame: pd.DataFrame, breadth: dict[str, float] | None = None) -> str:
    f = teknik_ozellikler(index_frame)
    if not f:
        return "VERİ YETERSİZ"
    breadth = breadth or {}
    if f["ret_5"] < -.04 and f["atr_pct"] > .025:
        return "RİSKTEN KAÇIŞ"
    if f["atr_pct"] > .03:
        return "YÜKSEK OYNAKLIK"
    if f["ema20_distance"] > 0 and f["ema50_distance"] > 0 and breadth.get("ema50_ustu", .5) >= .6:
        return "GÜÇLÜ POZİTİF"
    if f["ema20_distance"] > 0 and f["ret_5"] > 0:
        return "POZİTİF"
    return "YATAY"


def erken_aday(symbol: str, frame: pd.DataFrame, regime: str, kap: dict[str, Any] | None = None,
               sector_score: float | None = None, calibration: KalibrasyonKaniti | None = None,
               ipo_info: dict[str, Any] | None = None, as_of=None) -> dict[str, Any]:
    session_count = 0 if frame is None else len(frame.loc[frame.index <= pd.Timestamp(as_of)] if as_of is not None else frame)
    path, _level = model_yolu(session_count, IPO_AYARLARI)
    if path == "YENI_HALKA_ARZ" and session_count > 0:
        row = yeni_halka_arz_analizi(symbol, frame, regime, ipo_info=ipo_info, kap=kap, as_of=as_of)
        # Ortak T+1 tablo sozlesmesi; kisa gecmis satiri aday olmasa da gorunur kalir.
        return {
            **row,
            "%8+ Olasılığı": None, "Tavan Olasılığı": None,
            "Kapanış %8+ Olasılığı": None, "Tahmini En Yüksek Fiyat": None,
            "Referans Skor": row.get("Momentum Puani", 0),
            "Olasılık Güvenilir": False, "Model Sürümü": "ipo-kisa-gecmis-v1",
        }
    f = teknik_ozellikler(frame); kap = kap or {}; calibration = calibration or KalibrasyonKaniti()
    if not f:
        return {"Hisse": symbol.replace(".IS", ""), "Durum": "VERİ ALINAMADI", "Model Yolu": "BELİRLENEMEDİ",
                "Neden Kodu": "MISSING_PRICE_DATA", "Eleme Nedeni": NEDEN_ACIKLAMALARI["MISSING_PRICE_DATA"],
                "Riskler": ["Geçerli OHLCV yok"]}
    reasons, risks, score = [], [], 0.0
    movement_score, trade_quality, contributions = t1_movement_trade_scores(f)
    score = movement_score
    if 0 < f["ema20_distance"] < .06 and f["ema50_distance"] > 0: score += 14; reasons.append("Trend üzerinde, EMA20'den kopmamış")
    if f["macd_hist"] > 0 and f.get("macd_hist_slope", 0) >= 0 and 48 <= f["rsi"] <= 68: score += 8; reasons.append("Dengeli pozitif momentum")
    if f["bb_compression"] < .8: score += 12; reasons.append("Bollinger/oynaklık sıkışması")
    if f["relative_volume"] >= 1.2 and f["volume_persistence"] >= .6 and f["close_location"] >= .55: score += 10; reasons.append("Yüksek hacim + güçlü kapanış")
    if f["cmf"] > .05 and f["obv_slope"] > 0: score += 13; reasons.append("Para akışı ve OBV birikimi")
    if .01 <= f["resistance20_distance"] <= .08: score += 8; reasons.append("Kırılabilir yakın direnç")
    if f["close_location"] >= .7: score += 7; reasons.append("Güçlü günlük kapanış konumu")
    if sector_score is not None and sector_score > 0: score += min(8, sector_score); reasons.append("Sektör göreceli gücü pozitif")
    if kap.get("kap_etiket") == "Olumlu": score += min(10, max(0, float(kap.get("kap_skor", 0)))); reasons.append("Doğrulanmış olumlu KAP katalizörü")
    if kap.get("kap_etiket") in {None, "Veri Yok", "Hata"}: risks.append("KAP doğrulaması yapılamadı."); score -= 8
    if kap.get("kap_etiket") == "Olumsuz": risks.append("Negatif KAP riski"); score -= 25
    if f["ema20_distance"] > .10 or f["ret_5"] > .15: risks.append("Hareket başladı – geri çekilme/teyit bekle."); score -= 30
    if f.get("adx14", 0) >= 25 and f.get("plus_di", 0) <= f.get("minus_di", 0): risks.append("ADX yüksek ancak yön aşağı"); score -= 15
    if f["turnover"] < 10_000_000: risks.append("Likidite yetersiz"); score -= 25
    if f["resistance20_distance"] < .005: risks.append("Önemli dirence aşırı yakın"); score -= 10
    if regime == "RİSKTEN KAÇIŞ": risks.append("Piyasa riskten kaçış rejiminde"); score -= 15
    if risks and ("Likidite yetersiz" in risks or "Negatif KAP riski" in risks): status = "YÜKSEK RİSK"
    elif score >= 62: status = "GÜÇLÜ ERTESİ GÜN ADAYI"
    elif score >= 48: status = "ERKEN BİRİKİM ADAYI"
    else: status = "TEYİT BEKLİYOR"
    limit = pay_fiyat_limitleri(f["price"])
    probability = None  # Kalibre model artefaktı yüklenmeden skor yüzdeye çevrilmez.
    return {"Hisse": symbol.replace(".IS", ""), "Önceki Kapanış": f["price"], "Güncel Fiyat": f["price"],
            "Günlük Değişim %": f["ret_1"]*100, "Tavan Fiyatı": float(limit.ust_limit),
            "Tavana Kalan %": (float(limit.ust_limit)/f["price"]-1)*100,
            "%8+ Olasılığı": probability, "Tavan Olasılığı": probability, "Kapanış %8+ Olasılığı": probability,
            "Tahmini En Yüksek Fiyat": None, "Durum": status, "Referans Skor": round(score, 1),
            "Movement Score": round(movement_score, 1), "Trade Quality Score": round(trade_quality, 1),
            "Feature Contributions": contributions,
            "Aday Nedenleri": reasons, "Riskler": risks, "Piyasa Rejimi": regime,
            "Sektör Puanı": sector_score, "Veri Zamanı": str(frame.index[-1]),
            "Olasılık Güvenilir": calibration.guvenilir, "Model Sürümü": calibration.model_version,
            "Model Yolu": "STANDART", "Neden Kodu": "INCLUDED_STANDARD",
            "Eleme Nedeni": NEDEN_ACIKLAMALARI["INCLUDED_STANDARD"]}


def canli_teyit(aday: dict[str, Any], intraday: pd.DataFrame | None, metadata: Any) -> dict[str, Any]:
    """Gecikmeli/eski kaynakla asla canlı teyit üretmez."""
    if intraday is None or intraday.empty or metadata is None or getattr(metadata, "is_delayed", True) or getattr(metadata, "is_stale", True):
        return {**aday, "Canlı Durum": "TEYİT GELMEDİ", "Canlı Veri Uyarısı":
                "Gerçek zamanlı, güncel 5/15 dakikalık BIST OHLCV verisi yok; seans içi teyit kapalı."}
    return {**aday, "Canlı Durum": "İZLE", "Canlı Veri Uyarısı": "İlk 5/15 dakika tamamlanmış barları bekleniyor."}


def purged_walk_forward_splits(n: int, train_min: int, test_size: int, purge: int = 1, embargo: int = 1):
    """Rastgele bölme yapmayan genişleyen pencere indeksleri."""
    start = train_min
    while start + test_size <= n:
        train_end = max(0, start-purge)
        test_start = min(n, start+embargo)
        test_end = min(n, test_start+test_size)
        if train_end and test_start < test_end:
            yield np.arange(train_end), np.arange(test_start, test_end)
        start = test_end
