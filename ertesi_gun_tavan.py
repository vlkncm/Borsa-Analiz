"""Ertesi işlem günü fiyat limitine yaklaşma adayları.

Bu modül yalnız karar anına kadar kapanmış günlük barları kullanır. Tarihsel fiyat
limiti ve fiyat adımı dışarıdan verilmedikçe tavan fiyatı/etiketi uydurulmaz.
Gösterilen skor olasılık değildir; olasılık ancak yeterli örnek dışı tahminlerden
kalibre edilebilir.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


MIN_CALIBRATION_SAMPLES = 30
PROBABILITY_UNAVAILABLE = "Olasılık için yeterli geçmiş örnek bulunmuyor."


def _number(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _series(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(frame[name], errors="coerce").astype(float)


def fiyat_adimina_yuvarla(price: float, tick_size: float, direction: str = "down") -> float:
    """Fiyatı verilen, tarih için geçerli adıma yuvarlar.

    Adım tablosu bu modülde tahmin edilmez; çağıran resmî tarihsel kuralı sağlar.
    """
    if price <= 0 or tick_size <= 0:
        raise ValueError("Pozitif fiyat ve tarihsel fiyat adımı gerekli")
    units = price / tick_size
    rounded = math.floor(units + 1e-10) if direction == "down" else math.ceil(units - 1e-10)
    return round(rounded * tick_size, 8)


def tavan_fiyati_hesapla(previous_close: float, limit_pct: float | None,
                         tick_size: float | None) -> float | None:
    """İlgili tarih/pay için dışarıdan sağlanan limit ve adımla tavanı hesaplar."""
    if previous_close <= 0 or limit_pct is None or tick_size is None:
        return None
    if not 0 < float(limit_pct) < 100:
        raise ValueError("Geçerli tarihsel fiyat limiti gerekli")
    return fiyat_adimina_yuvarla(previous_close * (1 + float(limit_pct) / 100), float(tick_size), "down")


def gunluk_ozellikleri_hesapla(frame: pd.DataFrame, as_of=None) -> dict[str, Any]:
    """Yalnız ``as_of`` ve öncesindeki tamamlanmış barlardan özellik üretir."""
    required = {"Open", "High", "Low", "Close", "Volume"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return {"veri_yeterli": False, "veri_notu": "Günlük OHLCV eksik"}
    work = frame.copy().sort_index()
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if isinstance(work.index, pd.DatetimeIndex) and work.index.tz is not None and cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(work.index.tz)
        work = work.loc[work.index <= cutoff]
    work = work[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce").dropna()
    work = work[(work[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    if len(work) < 60:
        return {"veri_yeterli": False, "veri_notu": f"En az 60 bar gerekli; mevcut {len(work)}"}

    close, high, low, volume = (_series(work, x) for x in ("Close", "High", "Low", "Volume"))
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    prev_close = close.shift(1)
    tr = pd.concat([(high-low), (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    middle = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    bb_width = (4 * std / middle.replace(0, np.nan))
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean().replace(0, np.nan)
    rsi = 100 - 100/(1 + gain/loss)
    plus_dm = high.diff().where((high.diff() > -low.diff()) & (high.diff() > 0), 0.0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0.0)
    plus_di = 100 * plus_dm.rolling(14).mean()/atr14.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).mean()/atr14.replace(0, np.nan)
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0, np.nan)
    adx = dx.rolling(14).mean()
    typical = (high+low+close)/3
    raw_mf = typical*volume
    pos_mf = raw_mf.where(typical.diff() > 0, 0).rolling(14).sum()
    neg_mf = raw_mf.where(typical.diff() < 0, 0).rolling(14).sum().replace(0, np.nan)
    mfi = 100-100/(1+pos_mf/neg_mf)
    mf_multiplier = ((close-low)-(high-close))/(high-low).replace(0, np.nan)
    ad_line = (mf_multiplier.fillna(0)*volume).cumsum()
    cmf = (mf_multiplier.fillna(0)*volume).rolling(20).sum()/volume.rolling(20).sum().replace(0, np.nan)
    obv = (np.sign(delta).fillna(0)*volume).cumsum()

    price = float(close.iloc[-1])
    previous = float(close.iloc[-2])
    day_return = (price/previous-1)*100
    resistance20 = float(high.shift(1).rolling(20).max().iloc[-1])
    resistance60 = float(high.shift(1).rolling(60).max().iloc[-1])
    resistance = min(x for x in (resistance20, resistance60) if math.isfinite(x) and x > 0)
    distance_to_resistance = (resistance/price-1)*100
    ema_distance = (price/float(ema20.iloc[-1])-1)*100
    volume_ma20 = float(volume.rolling(20).mean().iloc[-1])
    rvol = float(volume.iloc[-1]/volume_ma20) if volume_ma20 > 0 else 0
    up = close.diff() > 0
    up_volume = float(volume.where(up).tail(10).mean())
    down_volume = float(volume.where(~up).tail(10).mean())
    accumulation_days = int(((volume > volume.rolling(20).mean()) & (close >= close.shift(1))).tail(10).sum())
    recent_lows = low.tail(5).to_numpy()
    higher_lows = bool(sum(np.diff(recent_lows) > 0) >= 3)
    close_near_high = float((price-low.iloc[-1])/(high.iloc[-1]-low.iloc[-1])) if high.iloc[-1] > low.iloc[-1] else .5

    return {
        "veri_yeterli": True, "veri_zamani": str(pd.Timestamp(work.index[-1])),
        "onceki_kapanis": round(price, 4), "onceki_gun_getiri_yuzde": round(day_return, 3),
        "mevcut_gunde_tavan_benzeri": bool(day_return >= 7.95),
        "ema20": round(float(ema20.iloc[-1]), 4), "ema50": round(float(ema50.iloc[-1]), 4),
        "ema20_egimi": round(float(ema20.iloc[-1]-ema20.iloc[-5]), 5),
        "ema20_uzaklik_yuzde": round(ema_distance, 3), "rsi14": round(_number(rsi.iloc[-1], 50), 2),
        "macd": round(float(macd.iloc[-1]), 5), "macd_signal": round(float(macd_signal.iloc[-1]), 5),
        "macd_ivme": round(float((macd-macd_signal).diff().iloc[-1]), 5),
        "adx14": round(_number(adx.iloc[-1]), 2), "plus_di": round(_number(plus_di.iloc[-1]), 2),
        "minus_di": round(_number(minus_di.iloc[-1]), 2), "roc10": round(float(close.pct_change(10).iloc[-1]*100), 3),
        "direnc": round(resistance, 4), "dirence_uzaklik_yuzde": round(distance_to_resistance, 3),
        "bb_genislik": round(_number(bb_width.iloc[-1]), 5),
        "bb_sikisma_orani": round(_number(bb_width.iloc[-1]/bb_width.rolling(60).median().iloc[-1], 1), 3),
        "atr_yuzde": round(float(atr14.iloc[-1]/price*100), 3),
        "atr_sikisma_orani": round(_number(atr14.iloc[-1]/atr14.rolling(60).median().iloc[-1], 1), 3),
        "kapanis_zirve_konumu": round(close_near_high, 3), "yukselen_dipler": higher_lows,
        "rvol": round(rvol, 3), "hacim_5_20": round(_number(volume.tail(5).mean()/volume_ma20), 3),
        "hacim_10_20": round(_number(volume.tail(10).mean()/volume_ma20), 3),
        "hacim_birikim_gunleri": accumulation_days,
        "yukselis_dusus_hacim_orani": round(_number(up_volume/down_volume) if down_volume > 0 else 0, 3),
        "obv_egimi": round(float(obv.iloc[-1]-obv.iloc[-10]), 2), "cmf20": round(_number(cmf.iloc[-1]), 4),
        "mfi14": round(_number(mfi.iloc[-1], 50), 2), "ad_egimi": round(float(ad_line.iloc[-1]-ad_line.iloc[-10]), 2),
        "ortalama_islem_tutari": round(price*volume_ma20, 2),
    }


def _family_scores(features: dict, context: dict) -> tuple[dict[str, float], list[str], list[str]]:
    reasons, risks = [], []
    accumulation = np.mean([
        np.clip(50+(features["rvol"]-1)*35, 0, 100),
        75 if features["obv_egimi"] > 0 else 25,
        np.clip(50+features["cmf20"]*180, 0, 100),
        np.clip(features["mfi14"], 0, 100),
        75 if features["ad_egimi"] > 0 else 25,
        min(100, features["hacim_birikim_gunleri"]*12.5),
    ])
    compression = np.mean([
        np.clip(100-(features["bb_sikisma_orani"]-0.5)*100, 0, 100),
        np.clip(100-(features["atr_sikisma_orani"]-0.5)*100, 0, 100),
        np.clip(100-abs(features["dirence_uzaklik_yuzde"])*16, 0, 100),
        features["kapanis_zirve_konumu"]*100,
        75 if features["yukselen_dipler"] else 35,
    ])
    trend = np.mean([
        80 if features["onceki_kapanis"] > features["ema20"] > features["ema50"] else 25,
        75 if features["ema20_egimi"] > 0 else 30,
        75 if features["macd"] > features["macd_signal"] or features["macd_ivme"] > 0 else 30,
        75 if features["plus_di"] > features["minus_di"] else 30,
        80 if 50 <= features["rsi14"] <= 70 else 35,
        70 if features["roc10"] > 0 else 30,
    ])
    market_score = _number(context.get("piyasa_rejim_puani"), 50)
    sector_score = _number(context.get("sektor_puani"), 35)
    relative = np.clip(0.55*market_score+0.45*sector_score, 0, 100)
    liquidity = np.clip((math.log10(max(features["ortalama_islem_tutari"], 1))-6)*30, 0, 100)
    kap_verified = bool(context.get("kap_yayin_zamani")) and bool(context.get("kap_url") or context.get("kap_basliklari"))
    kap_score_raw = _number(context.get("kap_skor"))
    catalyst = np.clip(50+kap_score_raw*2, 0, 100) if kap_verified else 0
    if not kap_verified:
        risks.append("KAP/katalizör zaman damgasıyla doğrulanamadı")
    elif kap_score_raw < 0:
        risks.append("Negatif KAP/katalizör")
    if accumulation >= 60: reasons.append("Çok günlük para ve hacim birikimi")
    if compression >= 60: reasons.append("Sıkışma ve kırılım seviyesine yakınlık")
    if trend >= 60: reasons.append("Trend ve momentum hazırlığı")
    if features["ema20_uzaklik_yuzde"] > 8: risks.append("Fiyat EMA20'den aşırı uzak")
    if context.get("piyasa_rejimi_v2") == "RISK_OFF": risks.append("Piyasa rejimi RISK_OFF")
    if features["mevcut_gunde_tavan_benzeri"]: risks.append("Hisse karar gününde zaten %8+ yükselmiş")
    return {
        "para_akisi": round(float(accumulation), 1), "sikisma_kirilim": round(float(compression), 1),
        "katalizor": round(float(catalyst), 1), "goreceli_guc": round(float(relative), 1),
        "trend_momentum": round(float(trend), 1), "likidite": round(float(liquidity), 1),
        "tarihsel_benzerlik": 0.0,
    }, reasons, risks


def aday_degerlendir(features: dict, context: dict | None = None,
                     calibration: dict | None = None) -> dict[str, Any]:
    context, calibration = context or {}, calibration or {}
    if not features.get("veri_yeterli"):
        return {"aday_grubu": "VERİ YETERSİZ", "tavan_aday_puani": 0,
                "riskler": features.get("veri_notu", "Veri yetersiz")}
    scores, reasons, risks = _family_scores(features, context)
    weights = {"para_akisi": .25, "sikisma_kirilim": .20, "katalizor": .20,
               "goreceli_guc": .15, "trend_momentum": .10, "likidite": .05,
               "tarihsel_benzerlik": .05}
    score = sum(scores[key]*weight for key, weight in weights.items())
    if context.get("piyasa_rejimi_v2") == "RISK_OFF":
        score -= 10
    if _number(context.get("kap_skor")) < 0:
        score -= 20
    ineligible = features["mevcut_gunde_tavan_benzeri"] or features["ema20_uzaklik_yuzde"] > 12
    if ineligible:
        group = "Yüksek Riskli/Spekülatif Aday"
    elif score >= 70 and not risks:
        group = "Güçlü Ertesi Gün Adayı"
    elif score >= 45:
        group = "Teyit Bekleyen Aday"
    else:
        group = "Yüksek Riskli/Spekülatif Aday"
    samples = int(calibration.get("samples", 0) or 0)
    ceiling_p = calibration.get("ceiling_probability") if samples >= MIN_CALIBRATION_SAMPLES else None
    eight_p = calibration.get("eight_plus_probability") if samples >= MIN_CALIBRATION_SAMPLES else None
    return {
        **scores, "tavan_aday_puani": round(max(0, min(95, score)), 1), "aday_grubu": group,
        "ertesi_gun_tavan_olasiligi": min(99.0, _number(ceiling_p)) if ceiling_p is not None else None,
        "ertesi_gun_8plus_olasiligi": min(99.0, _number(eight_p)) if eight_p is not None else None,
        "olasilik_notu": "Walk-forward kalibrasyon" if samples >= MIN_CALIBRATION_SAMPLES else PROBABILITY_UNAVAILABLE,
        "kalibrasyon_ornek_sayisi": samples,
        "aday_nedenleri": " | ".join(reasons) if reasons else "Güçlü ve bağımsız teyit bulunamadı",
        "riskler": " | ".join(risks) if risks else "Belirgin ek risk saptanmadı",
    }


def adaylari_tabloya_cevir(results: Iterable[dict]) -> pd.DataFrame:
    rows = []
    for item in results:
        features = item.get("ertesi_gun_ozellikleri") or {}
        result = aday_degerlendir(features, item, item.get("ertesi_gun_kalibrasyon"))
        if result["aday_grubu"] == "VERİ YETERSİZ" or features.get("mevcut_gunde_tavan_benzeri"):
            continue
        limit_pct, tick = item.get("fiyat_limit_yuzdesi"), item.get("fiyat_adimi")
        ceiling = tavan_fiyati_hesapla(features["onceki_kapanis"], limit_pct, tick)
        required = ((ceiling/features["onceki_kapanis"]-1)*100) if ceiling else None
        rows.append({
            "Hisse": str(item.get("symbol", item.get("Hisse", ""))).replace(".IS", ""),
            "Aday Grubu": result["aday_grubu"], "Önceki Kapanış": features["onceki_kapanis"],
            "Tavan Fiyatı": ceiling if ceiling is not None else "Tarihsel limit/adım verisi yok",
            "Tavan İçin Gereken %": round(required, 3) if required is not None else "Doğrulanamadı",
            "Ertesi Gün Tavan Olasılığı": result["ertesi_gun_tavan_olasiligi"] if result["ertesi_gun_tavan_olasiligi"] is not None else result["olasilik_notu"],
            "Ertesi Gün %8+ Olasılığı": result["ertesi_gun_8plus_olasiligi"] if result["ertesi_gun_8plus_olasiligi"] is not None else result["olasilik_notu"],
            "Tavan Aday Puanı": result["tavan_aday_puani"], "Para Akışı": result["para_akisi"],
            "Göreceli Hacim": features["rvol"], "Sıkışma/Kırılım": result["sikisma_kirilim"],
            "KAP Katalizörü": "Doğrulandı" if result["katalizor"] > 0 else "Doğrulanamadı",
            "Piyasa Rejimi": item.get("piyasa_rejimi_v2", "BELİRSİZ"),
            "Sektör Gücü": item.get("sektor_gucu", "Doğrulanamadı"),
            "Risk Seviyesi": "YÜKSEK" if result["aday_grubu"].startswith("Yüksek") else "ORTA" if result["aday_grubu"].startswith("Teyit") else "DÜŞÜK-ORTA",
            "Veri Zamanı": features["veri_zamani"], "Aday Olma Nedenleri": result["aday_nedenleri"],
            "Riskler": result["riskler"], "Kalibrasyon Örneği": result["kalibrasyon_ornek_sayisi"],
        })
    columns = ["Hisse", "Aday Grubu", "Önceki Kapanış", "Tavan Fiyatı", "Tavan İçin Gereken %",
               "Ertesi Gün Tavan Olasılığı", "Ertesi Gün %8+ Olasılığı", "Tavan Aday Puanı",
               "Para Akışı", "Göreceli Hacim", "Sıkışma/Kırılım", "KAP Katalizörü",
               "Piyasa Rejimi", "Sektör Gücü", "Risk Seviyesi", "Veri Zamanı",
               "Aday Olma Nedenleri", "Riskler", "Kalibrasyon Örneği"]
    frame = pd.DataFrame(rows, columns=columns)
    return frame.sort_values(["Tavan Aday Puanı", "Para Akışı"], ascending=False).reset_index(drop=True) if not frame.empty else frame


def ertesi_gun_etiketi(decision: pd.Series, next_bar: pd.Series,
                       limit_pct: float | None, tick_size: float | None) -> dict[str, Any]:
    """t satırından yalnız hedef fiyatı, t+1 satırından yalnız gerçekleşmeyi üretir."""
    previous_close = _number(decision.get("Close"))
    ceiling = tavan_fiyati_hesapla(previous_close, limit_pct, tick_size)
    if ceiling is None:
        raise ValueError("Etiket için tarih/pay bazlı fiyat limiti ve fiyat adımı zorunlu")
    high_return = (_number(next_bar.get("High"))/previous_close-1)*100
    close_return = (_number(next_bar.get("Close"))/previous_close-1)*100
    hit = _number(next_bar.get("High")) >= ceiling-1e-8
    return {"tavan_fiyati": ceiling, "tavana_ulasti": hit, "sekiz_plus": high_return >= 8,
            "t1_yuksek_getiri_yuzde": round(high_return, 4),
            "t1_kapanis_getiri_yuzde": round(close_return, 4),
            "tavan_gorup_geri_dondu": bool(hit and _number(next_bar.get("Close")) < ceiling)}


def walk_forward_degerlendir(dataset: pd.DataFrame, min_train: int = 60,
                             commission_bps: float = 10, slippage_bps: float = 7) -> dict[str, Any]:
    """Önceden üretilmiş point-in-time skor/etiketlerde son dönem holdout ölçümü."""
    required = {"date", "score", "tavana_ulasti", "sekiz_plus", "t1_yuksek_getiri_yuzde", "t1_kapanis_getiri_yuzde"}
    if dataset is None or not required.issubset(dataset.columns) or len(dataset) <= min_train:
        return {"samples": 0, "status": "YETERSİZ / DOĞRULANMAMIŞ VERİ"}
    work = dataset.sort_values("date").reset_index(drop=True)
    cutoff = max(min_train, int(len(work)*.8))
    test = work.iloc[cutoff:].copy()
    selected = test[pd.to_numeric(test["score"], errors="coerce") >= 70].copy()
    if selected.empty:
        return {"samples": 0, "status": "SON TEST DÖNEMİNDE ADAY YOK"}
    hit = selected["tavana_ulasti"].astype(bool)
    probability = selected["predicted_probability"] if "predicted_probability" in selected else pd.Series(0.0, index=selected.index)
    p = np.clip(pd.to_numeric(probability, errors="coerce").fillna(0)/100, 0, .99)
    gross = pd.to_numeric(selected["t1_kapanis_getiri_yuzde"], errors="coerce")
    net = gross-(2*commission_bps+2*slippage_bps)/100
    return {"samples": len(selected), "ceiling_hits": int(hit.sum()),
            "eight_plus": int(selected["sekiz_plus"].astype(bool).sum()),
            "false_positives": int((~hit).sum()), "precision": round(float(hit.mean()), 4),
            "average_high_return_pct": round(float(pd.to_numeric(selected["t1_yuksek_getiri_yuzde"], errors="coerce").mean()), 4),
            "average_close_return_pct": round(float(gross.mean()), 4),
            "average_net_return_pct": round(float(net.mean()), 4),
            "brier": round(float(((p-hit.astype(float))**2).mean()), 4) if p.gt(0).any() else None,
            "status": "ÖRNEK DIŞI / HOLDOUT"}


def tavan_tahminlerini_kaydet(frame: pd.DataFrame, path=None) -> list[dict]:
    """Adayları hash-zincirli olay günlüğüne ekler; aynı veri gününü çoğaltmaz."""
    if frame is None or frame.empty:
        return []
    from tahmin_defteri import olay_ekle, olaylari_oku
    existing = {
        (str(event.get("symbol")), str(event.get("data_time")))
        for event in olaylari_oku(path)
        if event.get("event_type") == "NEXT_DAY_CEILING_SIGNAL"
    }
    saved = []
    for row in frame.to_dict("records"):
        key = (str(row.get("Hisse", "")), str(row.get("Veri Zamanı", "")))
        if key in existing:
            continue
        event = {
            "event_type": "NEXT_DAY_CEILING_SIGNAL", "symbol": key[0],
            "strategy_id": "ceiling_potential", "data_time": key[1],
            "candidate_group": row.get("Aday Grubu"), "previous_close": row.get("Önceki Kapanış"),
            "ceiling_price": row.get("Tavan Fiyatı"), "required_rise_pct": row.get("Tavan İçin Gereken %"),
            "ceiling_probability": row.get("Ertesi Gün Tavan Olasılığı"),
            "eight_plus_probability": row.get("Ertesi Gün %8+ Olasılığı"),
            "candidate_score": row.get("Tavan Aday Puanı"), "market_regime": row.get("Piyasa Rejimi"),
            "sector_strength": row.get("Sektör Gücü"), "reasons": row.get("Aday Olma Nedenleri"),
            "risks": row.get("Riskler"), "forecast_horizon_sessions": 1,
        }
        saved.append(olay_ekle(event, path))
        existing.add(key)
    return saved


def ertesi_seans_sonucu(signal: dict, next_daily_bar: pd.Series,
                        intraday: pd.DataFrame | None = None) -> dict[str, Any]:
    """Tek ertesi seans sonucunu ölçer; saat yalnız intraday veri varsa verilir."""
    previous = _number(signal.get("previous_close"))
    ceiling = _number(signal.get("ceiling_price"))
    if previous <= 0:
        return {"status": "BELİRSİZ", "reason": "Önceki kapanış yok"}
    high, low, close = (_number(next_daily_bar.get(x)) for x in ("High", "Low", "Close"))
    if min(high, low, close) <= 0:
        return {"status": "BELİRSİZ", "reason": "Ertesi seans OHLC eksik"}
    hit = high >= ceiling-1e-8 if ceiling > 0 else None
    hit_time = None
    if hit is True and intraday is not None and not intraday.empty and "High" in intraday:
        matches = intraday[pd.to_numeric(intraday["High"], errors="coerce") >= ceiling]
        if not matches.empty:
            hit_time = str(matches.index[0])
    stop = _number(signal.get("stop"))
    # Günlük OHLC hedef/stop sırasını kanıtlamaz. İkisi de görüldüyse belirsizdir.
    both = bool(stop > 0 and low <= stop and hit is True)
    ordering = "BELİRSİZ (intraday veri gerekli)" if both else "HEDEF ÖNCE" if hit is True else "STOP ÖNCE" if stop > 0 and low <= stop else "HİÇBİRİ"
    return {"status": "TAVAN" if hit is True else "%8+" if (high/previous-1)*100 >= 8 else "YANLIŞ POZİTİF",
            "reached_ceiling": hit, "max_rise_pct": round((high/previous-1)*100, 4),
            "close_return_pct": round((close/previous-1)*100, 4),
            "max_decline_pct": round((low/previous-1)*100, 4),
            "ceiling_hit_time": hit_time or ("Intraday veri yok" if hit is True else None),
            "target_stop_order": ordering, "reversed_after_ceiling": bool(hit is True and close < ceiling),
            "ceiling_verification_note": "Doğrulandı" if ceiling > 0 else "Tarih/pay bazlı fiyat limiti bulunmadığı için tavan etiketi doğrulanamadı",
            "volume_prediction_verified": False,
            "volume_note": "Hacim tahmini için tanımlı ve kalibre edilmiş hedef bulunmuyor"}


def acik_tavan_tahminlerini_sonuclandir(path=None, provider=None) -> list[dict]:
    """Kapanmış ilk t+1 seansı bulur ve eski sinyali değiştirmeden sonuç olayı ekler."""
    from tahmin_defteri import olay_ekle, olaylari_oku
    if provider is None:
        from veri_saglayici import get_daily_ohlcv
        provider = lambda symbol: get_daily_ohlcv(symbol, "3mo")[0]
    events = olaylari_oku(path)
    signals = {e.get("event_id"): e for e in events if e.get("event_type") == "NEXT_DAY_CEILING_SIGNAL"}
    closed = {e.get("signal_event_id") for e in events if e.get("event_type") == "NEXT_DAY_CEILING_OUTCOME"}
    saved = []
    for event_id, signal in signals.items():
        if event_id in closed:
            continue
        try:
            frame = provider(signal.get("symbol", ""))
            if frame is None or frame.empty:
                continue
            data_time = pd.to_datetime(signal.get("data_time"), errors="coerce")
            index = pd.to_datetime(frame.index)
            if getattr(index, "tz", None) is not None and getattr(data_time, "tzinfo", None) is None:
                data_time = data_time.tz_localize(index.tz)
            future = frame.loc[index > data_time]
            if future.empty:
                continue
            outcome = ertesi_seans_sonucu(signal, future.iloc[0])
            saved.append(olay_ekle({"event_type": "NEXT_DAY_CEILING_OUTCOME",
                "signal_event_id": event_id, "symbol": signal.get("symbol"),
                "strategy_id": "ceiling_potential", **outcome}, path))
        except Exception:
            continue
    return saved


def tavan_performans_ozeti(path=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    from tahmin_defteri import olaylari_oku
    events = olaylari_oku(path)
    signals = {e.get("event_id"): e for e in events if e.get("event_type") == "NEXT_DAY_CEILING_SIGNAL"}
    outcomes = [e for e in events if e.get("event_type") == "NEXT_DAY_CEILING_OUTCOME"]
    rows = [{**signals.get(e.get("signal_event_id"), {}), **e} for e in outcomes]
    detail = pd.DataFrame(rows)
    if detail.empty:
        return pd.DataFrame([{"Toplam Tahmin": len(signals), "Tamamlanan": 0, "Tavan": 0,
            "%8+": 0, "Yanlış Pozitif": 0, "Precision": None,
            "Ortalama En Yüksek %": None, "Ortalama Kapanış %": None, "Brier": None}]), detail
    ceiling_known = detail["reached_ceiling"].notna() if "reached_ceiling" in detail else pd.Series(False, index=detail.index)
    hits = detail.loc[ceiling_known, "reached_ceiling"].astype(bool) if ceiling_known.any() else pd.Series(dtype=bool)
    probability_values = detail["ceiling_probability"] if "ceiling_probability" in detail else pd.Series(np.nan, index=detail.index)
    probabilities = pd.to_numeric(probability_values, errors="coerce")/100
    valid_p = ceiling_known & probabilities.notna()
    brier = float(((probabilities[valid_p]-detail.loc[valid_p, "reached_ceiling"].astype(float))**2).mean()) if valid_p.any() else None
    summary = pd.DataFrame([{"Toplam Tahmin": len(signals), "Tamamlanan": len(detail),
        "Tavan": int(hits.sum()), "%8+": int(detail["status"].isin(["TAVAN", "%8+"]).sum()),
        "Yanlış Pozitif": int(detail["status"].eq("YANLIŞ POZİTİF").sum()),
        "Precision": round(float(hits.mean()), 4) if len(hits) else None,
        "Ortalama En Yüksek %": round(float(pd.to_numeric(detail["max_rise_pct"], errors="coerce").mean()), 3),
        "Ortalama Kapanış %": round(float(pd.to_numeric(detail["close_return_pct"], errors="coerce").mean()), 3),
        "Brier": round(brier, 4) if brier is not None else None}])
    return summary, detail
