"""Tüm BIST için açıklanabilir, iki aşamalı T+1 aday motoru.

Referans skor olasılık değildir. Kalibre edilmiş örnek-dışı model artefaktı yoksa
yüzde alanları boş bırakılır; bu, sahte kesinlik üretilmesini engeller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from fiyat_limitleri import pay_fiyat_limitleri
from yeni_halka_arz import AYARLAR as IPO_AYARLARI, NEDEN_ACIKLAMALARI, model_yolu, yeni_halka_arz_analizi
from sinyal_pipeline import daily_features
from momentum_baslangici import evaluate_momentum_start


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
    enriched = daily_features(frame)
    close, high, low, volume = (_series(enriched, c) for c in ("Close", "High", "Low", "Volume"))
    last = float(close.iloc[-1]); rng = float(high.iloc[-1]-low.iloc[-1])
    momentum = evaluate_momentum_start(enriched)
    return {
        "price": last, "ret_1": float(close.pct_change(1).iloc[-1]), "ret_3": float(close.pct_change(3).iloc[-1]),
        "ret_5": float(close.pct_change(5).iloc[-1]), "ret_10": float(close.pct_change(10).iloc[-1]), "ret_20": float(close.pct_change(20).iloc[-1]),
        "ema20_distance": float(enriched["EMA20_DISTANCE"].iloc[-1]), "ema50_distance": last/float(enriched["EMA50"].iloc[-1])-1,
        "ema200_distance": last/float(enriched["EMA200"].iloc[-1])-1 if len(frame) >= 200 else np.nan,
        "macd": float(enriched["MACD"].iloc[-1]), "macd_hist": float(enriched["MACD_HIST"].iloc[-1]),
        "rsi": float(enriched["RSI"].iloc[-1]), "atr_pct": float(enriched["ATR"].iloc[-1]/last),
        "bb_width": float(enriched["BBW"].iloc[-1]), "bb_compression": float(enriched["BBW"].iloc[-1]/enriched["BBW"].rolling(60).median().iloc[-1]),
        "resistance20_distance": float(high.iloc[-20:].max()/last-1), "resistance60_distance": float(high.iloc[-60:].max()/last-1),
        "close_location": float((last-low.iloc[-1])/rng) if rng > 0 else .5,
        "relative_volume": float(enriched["RVOL_COMPLETED20"].iloc[-1]),
        "volume_persistence": float((volume.iloc[-5:] > volume.iloc[-20:].median()).mean()),
        "obv_slope": float(enriched["OBV"].diff(5).iloc[-1]/max(volume.iloc[-20:].mean(), 1)), "cmf": float(enriched["CMF"].iloc[-1]), "mfi": float(enriched["MFI"].iloc[-1]),
        "turnover": float(last*volume.iloc[-20:].mean()),
        "momentum_setup": momentum.get("momentum_setup"), "momentum_score": momentum.get("momentum_score"),
        "momentum_reasons": momentum.get("momentum_reasons", []), "momentum_risks": momentum.get("momentum_risks", []),
    }


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
    if 0 < f["ema20_distance"] < .06 and f["ema50_distance"] > 0: score += 14; reasons.append("Trend üzerinde, EMA20'den kopmamış")
    if f["macd_hist"] > 0 and 48 <= f["rsi"] <= 68: score += 12; reasons.append("Dengeli pozitif momentum")
    if f["bb_compression"] < .8: score += 12; reasons.append("Bollinger/oynaklık sıkışması")
    if f["relative_volume"] >= 1.2 and f["volume_persistence"] >= .6: score += 16; reasons.append("Sürekli göreceli hacim")
    if f["cmf"] > .05 and f["obv_slope"] > 0: score += 13; reasons.append("Para akışı ve OBV birikimi")
    if .01 <= f["resistance20_distance"] <= .08: score += 8; reasons.append("Kırılabilir yakın direnç")
    if f["close_location"] >= .7: score += 7; reasons.append("Güçlü günlük kapanış konumu")
    if sector_score is not None and sector_score > 0: score += min(8, sector_score); reasons.append("Sektör göreceli gücü pozitif")
    if kap.get("kap_etiket") == "Olumlu": score += min(10, max(0, float(kap.get("kap_skor", 0)))); reasons.append("Doğrulanmış olumlu KAP katalizörü")
    if kap.get("kap_etiket") in {None, "Veri Yok", "Hata"}:
        # Baglanti/eksik veri olumsuz haber degildir; belirsizlik olarak gorunur.
        risks.append("KAP doğrulaması yapılamadı; olumsuz haber varsayılmadı.")
    if kap.get("kap_etiket") == "Olumsuz": risks.append("Negatif KAP riski"); score -= 25
    if f["ema20_distance"] > .10 or f["ret_5"] > .15: risks.append("Hareket başladı – geri çekilme/teyit bekle."); score -= 30
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
            "Aday Nedenleri": reasons, "Riskler": risks, "Piyasa Rejimi": regime,
            "Sektör Puanı": sector_score, "Veri Zamanı": str(frame.index[-1]),
            "Olasılık Güvenilir": calibration.guvenilir, "Model Sürümü": calibration.model_version,
            "Model Yolu": "STANDART", "Neden Kodu": "INCLUDED_STANDARD",
            "Eleme Nedeni": NEDEN_ACIKLAMALARI["INCLUDED_STANDARD"],
            "Momentum Kurulumu": f.get("momentum_setup"),
            "Momentum Başlangıç Skoru": f.get("momentum_score"),
            "Momentum Nedenleri": f.get("momentum_reasons", []),
            "Momentum Riskleri": f.get("momentum_risks", []),
            "Aşırı İlerleme Durumu": "GEÇ GİRİŞ RİSKİ" if f.get("momentum_setup") == "HAREKET_ILERLEMIS" else "AŞIRI İLERLEMEMİŞ",
            "Hacim Teyidi": bool(f.get("relative_volume", 0) >= 1.2),
            "Takas Durumu": "Takas/kurumsal dağılım doğrulanamadı",
            "momentum_setup": f.get("momentum_setup"),
            "momentum_score": f.get("momentum_score"),
            "momentum_reasons": f.get("momentum_reasons", []),
            "momentum_risks": f.get("momentum_risks", []),
            "overextension_status": "GEÇ GİRİŞ RİSKİ" if f.get("momentum_setup") == "HAREKET_ILERLEMIS" else "AŞIRI İLERLEMEMİŞ",
            "volume_confirmation": bool(f.get("relative_volume", 0) >= 1.2),
            "trend_confirmation": f.get("momentum_setup") in {"YENI_MOMENTUM_BASLANGICI", "GUCLU_MOMENTUM_TEYIDI"},
            "momentum_trigger_date": str(frame.index[-1]) if f.get("momentum_score") is not None else None,
            "momentum_age_bars": None}


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
