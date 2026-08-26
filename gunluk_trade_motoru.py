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
from teknik_gostergeler import adx as canonical_adx, ema as canonical_ema, macd as canonical_macd, rsi as canonical_rsi
from teknik_gostergeler.ayarlar import StrategyConfig
from sinyal_pipeline import FORMULA_VERSION
from trade_kanitlari import (CostConfig, classify_market_regime, decision_gates,
                             expected_value, horizon_probability_evidence, mfe_mae_summary, relative_strength,
                             ranking_score, same_time_rvol)

STRATEGY_CONFIG = StrategyConfig()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return canonical_ema(series, period)


def _rsi(series: pd.Series, period: int = 14) -> float:
    return float(canonical_rsi(series, period).iloc[-1])


def _adx(frame: pd.DataFrame, period: int = 14) -> float:
    return float(canonical_adx(frame, period)["ADX"].iloc[-1])


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
                        historical_outcomes=None, now: datetime | None = None,
                        benchmark_close: pd.Series | None = None,
                        sector_close: pd.Series | None = None,
                        market_context: dict[str, Any] | None = None,
                        cost_config: CostConfig | None = None) -> dict[str, Any]:
    try:
        daily, daily_meta = get_daily_ohlcv(symbol, "6mo", adapter)
        intra, meta = get_intraday_ohlcv(symbol, interval, "5d", adapter)
    except Exception as exc:
        return _bos_sonuc(symbol, f"Veri alınamadı: {exc}")
    if len(daily) < 16 or len(intra) < 3:
        return _bos_sonuc(symbol, "Gösterge hesabı için yetersiz veri", meta)
    if meta.is_stale or intra["Volume"].fillna(0).le(0).all():
        return _bos_sonuc(symbol, "Eski/gecikmeli veya hacimsiz intraday veri; canlı teyit yok", meta)
    if getattr(meta, "corporate_action_warning", False) or getattr(daily_meta, "corporate_action_warning", False):
        return _bos_sonuc(symbol, "Bölünme/kurumsal işlem ölçek değişimi şüphesi; karar üretilmedi", meta)
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
    macd_values = canonical_macd(daily_close)
    macd_series, macd_signal = macd_values["MACD"], macd_values["MACD_SIGNAL"]
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
    horizon_evidence = horizon_probability_evidence(
        [] if historical_outcomes is None else historical_outcomes,
        horizons=STRATEGY_CONFIG.probability_horizons_days,
        primary_horizon=STRATEGY_CONFIG.primary_probability_horizon_days, min_samples=30,
        strategy_version=STRATEGY_CONFIG.version, formula_version=FORMULA_VERSION,
    )
    stop_loss_pct = (price-stop)/price*100
    expectancy = None
    if evidence.get("yeterli"):
        expectancy = expected_value(evidence["olasiliklar"], target_potential, stop_loss_pct,
                                    evidence["sure_doldu_medyan_getiri_pct"], cost_config or CostConfig())
    rvol = same_time_rvol(intra)
    rs = relative_strength(daily_close, benchmark_close, sector_close) if benchmark_close is not None else {
        "sektor_verisi_var": False, "rs_bist_5": None, "rs_bist_20": None,
        "rs_sektor_5": None, "rs_sektor_20": None, "uyari": "BIST/sektör verisi yok"}
    regime = market_context or classify_market_regime(benchmark_close, data_fresh=not meta.is_stale)
    rs_ok = (rs.get("rs_bist_5") is not None and rs.get("rs_bist_20") is not None
             and rs["rs_bist_5"] > 0 and rs["rs_bist_20"] > 0
             and rs.get("rs_sektor_5") is not None and rs.get("rs_sektor_20") is not None
             and rs["rs_sektor_5"] > 0 and rs["rs_sektor_20"] > 0)
    rvol_ok = rvol["rvol"] is not None and rvol["rvol"] >= .8
    net_expectancy = None if expectancy is None else expectancy["net_beklenti_pct"]
    probability_gate_evidence = {"yeterli": horizon_evidence["probability_target_before_stop"] is not None}
    gates = decision_gates(data_ok=not meta.is_stale, evidence=probability_gate_evidence, regime=regime,
                           liquid=bool(session["Volume"].median() > 0),
                           net_expectancy_pct=net_expectancy, risk_reward=rr,
                           relative_strength_ok=rs_ok,
                           volume_confirmation=rvol_ok and above_vwap,
                           min_risk_reward=min_risk_getiri)
    probability_lower = horizon_evidence["probability_ci_low"] or 0.0
    rank = (ranking_score(net_expectancy_pct=net_expectancy, probability_lower_pct=probability_lower,
                          relative_strength_pct=min(rs["rs_bist_5"], rs["rs_sektor_5"]),
                          rvol=rvol["rvol"], risk_reward=rr, reliability_pct=100)
            if gates["uygun"] else None)
    excursions = mfe_mae_summary([] if historical_outcomes is None else historical_outcomes)
    move_capacity = 3.0 <= target_potential <= 5.0
    confirmed = combo_count >= 4 and above_vwap and momentum and adx14 >= 20 and move_capacity and not negative_doji
    warnings = []
    if meta.is_delayed:
        warnings.append("Ücretsiz/gecikmeli veri; gerçek zaman garantisi yok")
    if horizon_evidence["probability_target_before_stop"] is None:
        warnings.append(f"{STRATEGY_CONFIG.primary_probability_horizon_days} işlem günlük hedef olasılığı için yetersiz olgunlaşmış out-of-sample örnek "
                        f"(n={horizon_evidence['probability_sample_size']})")
    if rvol["rvol"] is None:
        warnings.append(rvol["durum"])
    if rs.get("uyari"):
        warnings.append(rs["uyari"])
    if not regime.get("islem_uygun"):
        warnings.append(f"Piyasa rejimi yeni işleme uygun değil: {regime.get('rejim', 'UNKNOWN')}")
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
    elif not gates["uygun"]:
        result = "İŞLEM YOK"
    else:
        result = "AL ADAYI"
    size = pozisyon_boyutu(hesap_buyuklugu, risk_yuzdesi, price, stop)
    delay = "bilinmiyor" if meta.delay_minutes is None else f"{meta.delay_minutes:.0f} dk"
    horizon_probability = horizon_evidence["probability_target_before_stop"]
    probability = "Yetersiz örnek" if horizon_probability is None else f"%{horizon_probability:.0f}"
    confidence_interval = ("Yetersiz örnek" if horizon_evidence["probability_ci_low"] is None
                           else f"%{horizon_evidence['probability_ci_low']:.0f} – %{horizon_evidence['probability_ci_high']:.0f}")
    expected = "Bilinmiyor" if evidence["medyan_hareket"] is None else f"%{evidence['medyan_hareket']:.2f}"
    interval_range = "Bilinmiyor" if evidence["p10"] is None else f"%{evidence['p10']:.2f} – %{evidence['p90']:.2f}"
    summary = (f"{symbol.replace('.IS','')} — {entry_low:.2f}–{entry_high:.2f} TL alış; {target:.2f} TL hedef; "
               f"{stop:.2f} TL stop; hedef potansiyeli %{target_potential:.2f}; geçmiş medyan hareket {expected}; "
               f"{STRATEGY_CONFIG.primary_probability_horizon_days} işlem günü içinde hedefe stop'tan önce ulaşma olasılığı {probability} "
               f"(n={horizon_evidence['probability_sample_size']})")
    return {
        "Hisse": symbol.replace(".IS", ""), "Sonuç": result, "Sinyal": "VWAP+momentum" + ("+doji" if positive_doji else ""),
        "Veri Zamanı": _fmt_time(meta.last_bar_at), "Veri Kaynağı": meta.source, "Veri Gecikmesi": delay,
        "Tazelik": "GÜNCEL" if not meta.is_stale else "ESKİ", "Referans Fiyat": price,
        "Alış Alt": entry_low, "Alış Üst": entry_high, "Hedef": target, "Stop": stop,
        "Hedef Potansiyeli %": target_potential, "Beklenen Gün Sonu Hareketi %": expected,
        "Tahmin Aralığı %": interval_range, "Hedef Önce Olasılığı %": probability,
        "Olasılık Ufku — İşlem Günü": horizon_evidence["probability_horizon_days"],
        "OOS Örnek Sayısı": horizon_evidence["probability_sample_size"],
        "Başarılılarda Medyan Süre": horizon_evidence["median_target_time_success_days"],
        "Olasılık Tarihi": horizon_evidence["probability_as_of"],
        "Ufuk Olasılıkları": horizon_evidence["probability_by_horizon"],
        "Formül Sürümü": FORMULA_VERSION,
        "Olasılık %95 Güven Aralığı": confidence_interval,
        "Örnek": evidence["n"], "Kalibrasyon": evidence["kalibrasyon"],
        "Kalibrasyon Başlangıcı": evidence.get("baslangic"), "Kalibrasyon Bitişi": evidence.get("bitis"),
        "Brier Skoru": evidence.get("brier_skoru"), "Log Loss": evidence.get("log_loss"), "Risk/Getiri": rr,
        "Brüt Beklenti %": None if expectancy is None else expectancy["brut_beklenti_pct"],
        "Net Beklenti %": net_expectancy,
        "Maliyet Bileşenleri": {} if expectancy is None else expectancy["maliyetler"],
        "Piyasa Rejimi": regime.get("rejim", "UNKNOWN"), "Rejim Nedenleri": regime.get("nedenler", []),
        "RVOL": rvol["rvol"], "RVOL Durumu": rvol["durum"], "RVOL Geçmiş Gün": rvol["gecmis_gun"],
        "RS BIST 5": rs.get("rs_bist_5"), "RS BIST 20": rs.get("rs_bist_20"),
        "RS Sektör 5": rs.get("rs_sektor_5"), "RS Sektör 20": rs.get("rs_sektor_20"),
        "MFE/MAE Özeti": excursions, "Karar Kapıları": gates["kapilar"],
        "Geçmeyen Kapılar": gates["kalan_kapilar"], "Sıralama Skoru": rank,
        "Azami Adet": size["adet"], "Pozisyon Tutarı": size["pozisyon_tutari"], "Risk Tutarı": size["risk_tutari"],
        "Doji": doji["tur"], "Doji Bağlamı": context["baglam"], "Doji Teyidi": "EVET" if context["teyit"] else "HAYIR",
        "VWAP": vwap, "VWAP Konumu": "ÜSTÜNDE" if above_vwap else "ALTINDA", **piv,
        "ATR": atr, "Stop Katsayısı": 1.5, "Hacim Oranı": volume_ratio, "ADX": adx14,
        "Strateji Kimliği": STRATEGY_CONFIG.strategy_id, "Strateji Sürümü": STRATEGY_CONFIG.version,
        "EMA21": ema21, "EMA50": ema50, "RSI": rsi14, "MACD": float(macd_series.iloc[-1]),
        "MACD Signal": float(macd_signal.iloc[-1]), "5'li Kombo": f"{combo_count}/5",
        "Gerekçe": f"{gates['aciklama']}; 5'li kombo={combo_count}/5, ADX={adx14:.1f}, VWAP={'üstü' if above_vwap else 'altı'}",
        "Uyarılar": "; ".join(warnings), "Kısa Özet": summary,
    }


def adaylari_tara(symbols, **kwargs) -> pd.DataFrame:
    rows = [gunluk_trade_analiz(symbol, **kwargs) for symbol in symbols]
    frame = pd.DataFrame(rows)
    if kwargs.get("sadece_teyitli"):
        frame = frame[frame["Sonuç"].isin(["AL ADAYI"])]
    if "Sıralama Skoru" in frame:
        frame = frame.sort_values("Sıralama Skoru", ascending=False, na_position="last")
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
