"""Mevcut yatırım kararlarından bağımsız, güvenli günlük trade karar motoru."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from intraday_backtest import ampirik_kanit
from intraday_gostergeler import klasik_pivot, pozisyon_boyutu, seans_vwap, wilder_atr
from mum_formasyonlari import doji_baglam_ve_teyit, doji_siniflandir
from veri_saglayici import PiyasaVeriAdapteri, get_daily_ohlcv, get_intraday_ohlcv


def _ema(series: pd.Series, period: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = pd.to_numeric(series, errors="coerce").diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return float((100 - 100 / (1 + gain / loss.replace(0, pd.NA))).fillna(100).iloc[-1])


def _adx(frame: pd.DataFrame, period: int = 14) -> float:
    high, low, close = frame["High"], frame["Low"], frame["Close"]
    plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0.0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0.0)
    tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean().replace(0, pd.NA)
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    return float((100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, pd.NA)).fillna(0).ewm(alpha=1/period, adjust=False).mean().iloc[-1])


def _fmt_time(value) -> str:
    return value.isoformat(timespec="minutes") if value else "bilinmiyor"


def _bos_sonuc(symbol: str, reason: str, metadata=None) -> dict[str, Any]:
    return {"Hisse": symbol.replace(".IS", ""), "Sonuç": "VERİ YETERSİZ", "Uyarılar": reason,
            "Veri Kaynağı": getattr(metadata, "source", "bilinmiyor"),
            "Veri Zamanı": _fmt_time(getattr(metadata, "last_bar_at", None)),
            "Veri Gecikmesi": "bilinmiyor", "Kısa Özet": f"{symbol}: {reason}"}


def gunluk_trade_analiz(symbol: str, interval: str = "15m", hesap_buyuklugu: float | None = None,
                        risk_yuzdesi: float = 0.5, min_risk_getiri: float = 1.8,
                        sadece_teyitli: bool = False, adapter: PiyasaVeriAdapteri | None = None,
                        historical_outcomes=None, now: datetime | None = None) -> dict[str, Any]:
    try:
        daily, daily_meta = get_daily_ohlcv(symbol, "6mo", adapter)
        intra, meta = get_intraday_ohlcv(symbol, interval, "5d", adapter)
    except Exception as exc:
        return _bos_sonuc(symbol, f"Veri alınamadı: {exc}")
    if len(daily) < 16 or len(intra) < 3:
        return _bos_sonuc(symbol, "Gösterge hesabı için yetersiz veri", meta)
    if meta.is_stale or intra["Volume"].fillna(0).le(0).all():
        return _bos_sonuc(symbol, "Eski/gecikmeli veya hacimsiz intraday veri; canlı teyit yok", meta)
    session_date = intra.index[-1].date()
    session = intra[intra.index.date == session_date].copy()
    if len(session) < 3:
        return _bos_sonuc(symbol, "Tamamlanmış seans mumu yetersiz", meta)
    completed_daily = daily[daily.index.date < session_date]
    if completed_daily.empty:
        return _bos_sonuc(symbol, "Önceki tamamlanmış işlem günü bulunamadı", meta)
    previous_day = completed_daily.iloc[-1]
    piv = klasik_pivot(previous_day["High"], previous_day["Low"], previous_day["Close"])
    atr = float(wilder_atr(daily).iloc[-1])
    if not math.isfinite(atr) or atr <= 0:
        return _bos_sonuc(symbol, "ATR hesaplanamadı", meta)
    vwap_series = seans_vwap(session)
    vwap = float(vwap_series.iloc[-1]) if not vwap_series.empty else math.nan
    if not math.isfinite(vwap):
        return _bos_sonuc(symbol, "Geçerli hacim olmadığı için VWAP hesaplanamadı", meta)
    signal_bar, confirmation_bar = session.iloc[-2], session.iloc[-1]
    doji = doji_siniflandir(signal_bar.Open, signal_bar.High, signal_bar.Low, signal_bar.Close)
    context = doji_baglam_ve_teyit(
        doji, session["Close"].iloc[-7:-2].tolist(), signal_bar.High, signal_bar.Low,
        {**confirmation_bar.to_dict(), "is_complete_bar": True},
    )
    price = float(confirmation_bar.Close)
    volume_ratio = float(confirmation_bar.Volume / session["Volume"].iloc[:-1].tail(10).median())
    above_vwap = price > vwap
    positive_doji = context["teyit"] and context["yon"] == "YUKARI"
    negative_doji = context["teyit"] and context["yon"] == "AŞAĞI"
    momentum = price > float(session["Close"].iloc[-3])
    daily_close = pd.to_numeric(completed_daily["Close"], errors="coerce")
    ema21, ema50 = float(_ema(daily_close, 21).iloc[-1]), float(_ema(daily_close, 50).iloc[-1])
    rsi14 = _rsi(daily_close)
    macd_series = _ema(daily_close, 12) - _ema(daily_close, 26)
    macd_signal = _ema(macd_series, 9)
    macd_up = bool(macd_series.iloc[-1] > macd_signal.iloc[-1] and macd_series.iloc[-1] >= macd_series.iloc[-2])
    adx14 = _adx(completed_daily)
    combo = {
        "EMA21 > EMA50": ema21 > ema50, "RSI > 50": 50 < rsi14 < 70,
        "MACD yukarı": macd_up, "Hacim artışı": volume_ratio >= 1.20,
        "VWAP üstü": above_vwap,
    }
    combo_count = sum(combo.values())
    entry_low, entry_high = price - atr*0.08, price + atr*0.04
    structural = min(float(signal_bar.Low), piv["P"], piv["S1"])
    stop_atr = price - atr*1.5
    stop = max(0.01, min(float(signal_bar.Low)-atr*0.05, structural-atr*0.05, stop_atr))
    risk = price-stop
    target_floor = price + risk*min_risk_getiri
    resistance = min((x for x in (piv["R1"], piv["R2"]) if x > price), default=target_floor)
    target = max(target_floor, min(resistance, price+atr*2.5, price*1.05))
    rr = (target-price)/risk if risk > 0 else 0.0
    target_potential = (target/price-1)*100
    evidence = ampirik_kanit([] if historical_outcomes is None else historical_outcomes)
    move_capacity = 3.0 <= target_potential <= 5.0
    confirmed = combo_count >= 4 and above_vwap and momentum and adx14 >= 20 and move_capacity and not negative_doji
    warnings = []
    if meta.is_delayed:
        warnings.append("Ücretsiz/gecikmeli veri; gerçek zaman garantisi yok")
    if evidence["olasilik"] is None:
        warnings.append(f"Hedef olasılığı için yetersiz out-of-sample örnek (n={evidence['n']})")
    if doji["tur"] == "UZUN BACAKLI DOJİ" and not context["teyit"]:
        warnings.append("Uzun bacaklı doji yön teyidi bekliyor")
    if negative_doji:
        warnings.append("Teyitli aşağı yönlü doji long işlemi engelledi")
    if rr < min_risk_getiri or risk <= price*0.001:
        result = "İŞLEM YOK"
    elif price > entry_high*1.005:
        result = "FİYAT KOVALAMA"
    elif not confirmed or (sadece_teyitli and not positive_doji):
        result = "TEYİT BEKLE"
    elif evidence["olasilik"] is None:
        result = "TEYİT BEKLE"  # Deneysel kanıt, AL ADAYI seviyesine yükselmez.
    else:
        result = "AL ADAYI"
    size = pozisyon_boyutu(hesap_buyuklugu, risk_yuzdesi, price, stop)
    delay = "bilinmiyor" if meta.delay_minutes is None else f"{meta.delay_minutes:.0f} dk"
    probability = "Yetersiz örnek" if evidence["olasilik"] is None else f"%{evidence['olasilik']:.1f}"
    expected = "Bilinmiyor" if evidence["medyan_hareket"] is None else f"%{evidence['medyan_hareket']:.2f}"
    interval_range = "Bilinmiyor" if evidence["p10"] is None else f"%{evidence['p10']:.2f} – %{evidence['p90']:.2f}"
    summary = (f"{symbol.replace('.IS','')} — {entry_low:.2f}–{entry_high:.2f} TL alış; {target:.2f} TL hedef; "
               f"{stop:.2f} TL stop; hedef potansiyeli %{target_potential:.2f}; geçmiş medyan hareket {expected}; "
               f"hedefe stop'tan önce ulaşma olasılığı {probability} (n={evidence['n']})")
    return {
        "Hisse": symbol.replace(".IS", ""), "Sonuç": result, "Sinyal": "VWAP+momentum" + ("+doji" if positive_doji else ""),
        "Veri Zamanı": _fmt_time(meta.last_bar_at), "Veri Kaynağı": meta.source, "Veri Gecikmesi": delay,
        "Tazelik": "GÜNCEL" if not meta.is_stale else "ESKİ", "Referans Fiyat": price,
        "Alış Alt": entry_low, "Alış Üst": entry_high, "Hedef": target, "Stop": stop,
        "Hedef Potansiyeli %": target_potential, "Beklenen Gün Sonu Hareketi %": expected,
        "Tahmin Aralığı %": interval_range, "Hedef Önce Olasılığı %": probability,
        "Örnek": evidence["n"], "Kalibrasyon": evidence["kalibrasyon"], "Risk/Getiri": rr,
        "Azami Adet": size["adet"], "Pozisyon Tutarı": size["pozisyon_tutari"], "Risk Tutarı": size["risk_tutari"],
        "Doji": doji["tur"], "Doji Bağlamı": context["baglam"], "Doji Teyidi": "EVET" if context["teyit"] else "HAYIR",
        "VWAP": vwap, "VWAP Konumu": "ÜSTÜNDE" if above_vwap else "ALTINDA", **piv,
        "ATR": atr, "Stop Katsayısı": 1.5, "Hacim Oranı": volume_ratio, "ADX": adx14,
        "EMA21": ema21, "EMA50": ema50, "RSI": rsi14, "MACD": float(macd_series.iloc[-1]),
        "MACD Signal": float(macd_signal.iloc[-1]), "5'li Kombo": f"{combo_count}/5",
        "Gerekçe": f"5'li kombo={combo_count}/5, ADX={adx14:.1f}, VWAP={'üstü' if above_vwap else 'altı'}, hacim oranı={volume_ratio:.2f}",
        "Uyarılar": "; ".join(warnings), "Kısa Özet": summary,
    }


def adaylari_tara(symbols, **kwargs) -> pd.DataFrame:
    rows = [gunluk_trade_analiz(symbol, **kwargs) for symbol in symbols]
    frame = pd.DataFrame(rows)
    if kwargs.get("sadece_teyitli"):
        frame = frame[frame["Sonuç"].isin(["AL ADAYI"])]
    return frame.reset_index(drop=True)


def kagit_islem_kaydet(record: dict[str, Any], path: str | Path) -> str:
    """Tahmini hash zincirli JSONL kaydına ekler; geçmiş satırları değiştirmez."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = "GENESIS"
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()
        if lines:
            previous_hash = json.loads(lines[-1])["kayit_hash"]
    payload = {"kayit_zamani": datetime.now().astimezone().isoformat(), "onceki_hash": previous_hash,
               "tahmin": record}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload["kayit_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return payload["kayit_hash"]
