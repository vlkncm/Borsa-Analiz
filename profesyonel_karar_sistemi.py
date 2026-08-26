"""Seçici, açıklanabilir ve ölçülebilir profesyonel karar kapıları.

Bu katman mevcut teknik/temel puanları değiştirmez. Onların üzerinde veto kapıları
uygular; eksik veriyi olumlu kabul etmez ve hiçbir koşulda kesinlik üretmez.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable
import uuid

import pandas as pd
from veri_kalite_kapisi import veri_kalite_kapisi


REGIMES = {"GUCLU_RISK_ON", "RISK_ON", "YATAY", "YUKSEK_OYNAKLIK", "RISK_OFF"}
FINAL_CLASSES = {"UYGUN ADAY", "TEYİT BEKLİYOR", "İZLE", "İŞLEM YAPMA", "VERİ YETERSİZ"}


@dataclass(frozen=True)
class RiskLimits:
    trade_risk_pct: float = 0.5
    portfolio_risk_pct: float = 3.0
    sector_risk_pct: float = 1.5
    daily_loss_pct: float = 1.5
    weekly_loss_pct: float = 3.0
    max_drawdown_pct: float = 8.0


@dataclass(frozen=True)
class CostModel:
    commission_bps: float = 10.0
    spread_bps: float = 8.0
    slippage_bps: float = 7.0


def risk_ayar_yolu() -> Path:
    path = Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "ayarlar" / "risk_limitleri.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def risk_ayarlari_oku(path: Path | None = None) -> RiskLimits:
    path = path or risk_ayar_yolu()
    if not path.exists():
        return RiskLimits()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        allowed = RiskLimits.__dataclass_fields__
        values = {key: float(raw[key]) for key in allowed if key in raw}
        limits = RiskLimits(**values)
        if not (0 < limits.trade_risk_pct <= 2 and limits.trade_risk_pct <= limits.sector_risk_pct <= limits.portfolio_risk_pct <= 10):
            raise ValueError("Risk limit sıralaması geçersiz")
        return limits
    except Exception:
        return RiskLimits()


def risk_ayarlari_kaydet(limits: RiskLimits, path: Path | None = None) -> Path:
    path = path or risk_ayar_yolu()
    if not (0 < limits.trade_risk_pct <= 2 and limits.trade_risk_pct <= limits.sector_risk_pct <= limits.portfolio_risk_pct <= 10):
        raise ValueError("İşlem ≤ sektör ≤ portföy ve portföy ≤ %10 olmalıdır")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(limits.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(item: dict, *keys: str) -> str:
    for key in keys:
        value = str(item.get(key, "")).strip()
        if value and value.casefold() not in {"nan", "none", "veri yok", "analiz dışı"}:
            return value
    return ""


def piyasa_rejimi_hesapla(results: Iterable[dict]) -> dict[str, Any]:
    """BIST evreninin ileriye bakmayan son kesitinden rejim üretir.

    Endeks serisi varsa endeks alanları, yoksa tüm-evren breadth vekili kullanılır.
    Eksik veri rejim güvenini düşürür; güçlü rejim varsayılmaz.
    """
    rows = list(results)
    if not rows:
        return {"regime": "YATAY", "score": 50.0, "confidence": 0.0,
                "uncertainty_penalty": 12.0, "reason": "Piyasa verisi yok"}
    valid = [x for x in rows if _f(x.get("price")) > 0]
    if len(valid) < 10:
        return {"regime": "YATAY", "score": 50.0, "confidence": 20.0,
                "uncertainty_penalty": 10.0, "reason": "Piyasa genişliği için örnek yetersiz"}
    above20 = sum(_f(x.get("price")) > _f(x.get("ema20"), math.inf) for x in valid) / len(valid)
    above50 = sum(_f(x.get("price")) > _f(x.get("ema50"), math.inf) for x in valid) / len(valid)
    above200 = sum(_f(x.get("price")) > _f(x.get("ema200"), math.inf) for x in valid) / len(valid)
    advances = sum(_f(x.get("ret_20")) > 0 for x in valid) / len(valid)
    ret20 = pd.Series([_f(x.get("ret_20")) for x in valid]).median()
    ret60 = pd.Series([_f(x.get("ret_60")) for x in valid]).median()
    adx = pd.Series([_f(x.get("adx")) for x in valid]).median()
    atr_pct = pd.Series([100 * _f(x.get("atr")) / _f(x.get("price"), 1) for x in valid]).median()
    volume = pd.Series([_f(x.get("volume_ratio"), 1) for x in valid]).median()
    score = 50 + (above20-.5)*20 + (above50-.5)*30 + (above200-.5)*20 + (advances-.5)*20
    score += max(-10, min(10, ret20/2)) + max(-8, min(8, ret60/6))
    high_volatility = atr_pct >= 4.5 or (atr_pct >= 3.5 and adx < 18)
    if high_volatility:
        regime = "YUKSEK_OYNAKLIK"
    elif score >= 72 and above50 >= .62 and ret20 > 0 and adx >= 20:
        regime = "GUCLU_RISK_ON"
    elif score >= 58 and above50 >= .52 and ret20 >= 0:
        regime = "RISK_ON"
    elif score <= 38 or (above50 < .38 and ret20 < 0):
        regime = "RISK_OFF"
    else:
        regime = "YATAY"
    completeness = sum(any(k in x for k in ("ema20", "EMA20")) for x in valid) / len(valid)
    confidence = min(95.0, 45 + len(valid)/12 + completeness*20)
    penalty = 0.0 if confidence >= 70 else round((70-confidence)*.25, 1)
    return {
        "regime": regime, "score": round(max(0, min(100, score)), 1),
        "confidence": round(confidence, 1), "uncertainty_penalty": penalty,
        "breadth_above_ema20": round(above20*100, 1), "breadth_above_ema50": round(above50*100, 1),
        "breadth_above_ema200": round(above200*100, 1), "advance_ratio": round(advances*100, 1),
        "median_ret20": round(float(ret20), 2), "median_ret60": round(float(ret60), 2),
        "median_atr_pct": round(float(atr_pct), 2), "market_volume_ratio": round(float(volume), 2),
        "reason": f"EMA50 üstü %{above50*100:.1f}; yükselen oranı %{advances*100:.1f}; medyan 20g %{ret20:.1f}",
    }


def sektor_profilleri_hesapla(results: Iterable[dict], market: dict) -> dict[str, dict[str, Any]]:
    rows = list(results)
    groups: dict[str, list[dict]] = {}
    for item in rows:
        sector = _text(item, "sektor", "sector", "sektor_adi") or "BİLİNMİYOR"
        groups.setdefault(sector, []).append(item)
    profiles = {}
    market20 = _f(market.get("median_ret20")); market60 = _f(market.get("median_ret60"))
    for sector, members in groups.items():
        valid = [x for x in members if _f(x.get("price")) > 0]
        if sector == "BİLİNMİYOR" or len(valid) < 3:
            profiles[sector] = {"sector": sector, "score": 35.0, "class": "Nötr",
                "relative_strength": 0.0, "verified": False, "reason": "Sektör verisi doğrulanamadı"}
            continue
        r20 = float(pd.Series([_f(x.get("ret_20")) for x in valid]).median())
        r60 = float(pd.Series([_f(x.get("ret_60")) for x in valid]).median())
        above50 = sum(_f(x.get("price")) > _f(x.get("ema50"), math.inf) for x in valid)/len(valid)
        advancing = sum(_f(x.get("ret_20")) > 0 for x in valid)/len(valid)
        volume = float(pd.Series([_f(x.get("volume_ratio"), 1) for x in valid]).median())
        rs = (r20-market20)*.6 + (r60-market60)*.4
        score = max(0, min(100, 50 + rs*1.2 + (above50-.5)*30 + (advancing-.5)*20 + (volume-1)*10))
        label = "Güçlü" if score >= 75 else "Pozitif" if score >= 62 else "Nötr" if score >= 45 else "Zayıf" if score >= 30 else "Kaçınılmalı"
        profiles[sector] = {"sector": sector, "score": round(score, 1), "class": label,
            "relative_strength": round(rs, 2), "verified": True,
            "ret20": round(r20, 2), "ret60": round(r60, 2), "above_ema50": round(above50*100, 1),
            "advance_ratio": round(advancing*100, 1), "volume_ratio": round(volume, 2)}
    return profiles


def birinci_asama_uygula(results: list[dict]) -> tuple[list[dict], dict, dict]:
    """Yalnızca veri kalitesi, piyasa rejimi ve sektör gücü katmanlarını ekler.

    Sonraki karar kapılarını çalıştırmaz. Böylece aşamalar ayrı ayrı test edilip
    onaylanabilir ve mevcut puan/karar formülleri bu aşamada değişmez.
    """
    market = piyasa_rejimi_hesapla(results)
    sectors = sektor_profilleri_hesapla(results, market)
    for item in results:
        quality = veri_kalite_kapisi(item)
        sector_name = _text(item, "sektor", "sector", "sektor_adi") or "BİLİNMİYOR"
        sector = sectors.get(sector_name, sectors.get("BİLİNMİYOR", {}))
        item.update(quality)
        item.update({
            "piyasa_rejimi_v2": market["regime"],
            "piyasa_rejim_puani": market["score"],
            "piyasa_rejim_guveni": market["confidence"],
            "piyasa_rejim_nedeni": market["reason"],
            "sektor_adi": sector_name,
            "sektor_puani": sector.get("score", 35.0),
            "sektor_gucu": sector.get("class", "Nötr"),
            "sektor_goreceli_guc": sector.get("relative_strength", 0.0),
            "sektor_dogrulandi": bool(sector.get("verified", False)),
            "birinci_asama_onayli": bool(quality.get("veri_kalite_onayli")) and bool(sector.get("verified", False)),
        })
        if not quality.get("veri_kalite_onayli"):
            item["birinci_asama_notu"] = quality.get("veri_kalite_notu", "Veri kalitesi yetersiz")
        elif not sector.get("verified", False):
            item["birinci_asama_notu"] = "Sektör verisi doğrulanamadı; olumlu kabul edilmedi"
        else:
            item["birinci_asama_notu"] = f"Veri uygun; piyasa {market['regime']}; sektör {sector.get('class')}"
    return results, market, sectors


def para_akisi_teyidi(item: dict) -> dict[str, Any]:
    # Korelasyonlu hacim göstergeleri tek ailede ve en fazla 100 puanda tutulur.
    volume = _f(item.get("volume_ratio"), 1)
    obv = _f(item.get("obv_trend_20"))
    cmf = _f(item.get("cmf_20"))
    mfi = _f(item.get("mfi_14"), 50)
    ad_line = _f(item.get("ad_trend", item.get("accumulation_distribution")))
    price_volume = _f(item.get("ret_20")) > 0 and volume >= 1.05
    vwap_known = _f(item.get("vwap")) > 0
    above_vwap = vwap_known and _f(item.get("price")) > _f(item.get("vwap"))
    persistence = _f(item.get("hacim_surekliligi", item.get("volume_persistence")), 0)
    components = [
        min(100, max(0, 50+(volume-1)*45)), 70 if obv > 0 else 35,
        min(100, max(0, 50+cmf*160)), min(100, max(0, mfi)),
        65 if ad_line > 0 else 40, 70 if price_volume else 35,
        70 if above_vwap else (45 if not vwap_known else 25),
    ]
    if persistence:
        components.append(max(0, min(100, persistence)))
    score = sum(components)/len(components)
    persistent_support = price_volume and (obv > 0 or cmf > .05 or persistence >= 55)
    return {"score": round(score, 1), "confirmed": score >= 58 and persistent_support,
            "reason": f"RVOL {volume:.2f}; OBV {'+' if obv>0 else '-'}; CMF {cmf:.2f}; MFI {mfi:.1f}"}


def net_ev_hesapla(probability_pct: float, entry: float, target: float, stop: float,
                   costs: CostModel = CostModel()) -> dict[str, float]:
    if not (0 < probability_pct < 100 and 0 < stop < entry < target):
        return {"net_ev_pct": -999.0, "net_win_pct": 0.0, "net_loss_pct": 0.0, "cost_pct": 0.0}
    cost_pct = 2*costs.commission_bps/100 + costs.spread_bps/100 + 2*costs.slippage_bps/100
    win = (target/entry-1)*100-cost_pct
    loss = (entry/stop-1)*100+cost_pct
    p = probability_pct/100
    return {"net_ev_pct": round(p*win-(1-p)*loss, 3), "net_win_pct": round(win, 3),
            "net_loss_pct": round(loss, 3), "cost_pct": round(cost_pct, 3)}


def pozisyon_hesapla(capital: float, entry: float, stop: float, limits: RiskLimits = RiskLimits(),
                     volatility_multiplier: float = 1.0) -> dict[str, Any]:
    per_share = entry-stop
    allowed = max(0.0, capital)*limits.trade_risk_pct/100*max(0.0, min(1.0, volatility_multiplier))
    qty = math.floor(allowed/per_share) if per_share > 0 else 0
    return {"position_qty": qty, "cash_risk": round(qty*max(0, per_share), 2),
            "allowed_cash_risk": round(allowed, 2), "trade_risk_pct": limits.trade_risk_pct}


def stop_yonetimi(item: dict, entry: float, current: float, initial_stop: float) -> dict[str, Any]:
    atr = max(_f(item.get("atr")), current*.008)
    support = _f(item.get("ana_destek", item.get("fib_destek")))
    technical = max(x for x in (initial_stop, support*.98 if support > 0 else 0) if x > 0)
    atr_stop = current-atr*1.8
    initial = min(entry*.995, max(technical, atr_stop))
    elapsed = int(_f(item.get("gecen_islem_gunu")))
    duration = int(_f(item.get("beklenen_sure_ust"), 20))
    reasons = []
    if current <= technical: reasons.append("Teknik yapı/hacimli destek kırıldı")
    if str(item.get("piyasa_rejimi_v2", "")).upper() == "RISK_OFF": reasons.append("Piyasa rejimi RISK_OFF oldu")
    if str(item.get("sektor_gucu", "")).casefold() in {"zayıf", "kaçınılmalı"}: reasons.append("Sektör görünümü sert biçimde bozuldu")
    if _f(item.get("kap_skor")) < 0: reasons.append("Negatif KAP/haber geldi")
    if elapsed > duration and current <= entry*1.01: reasons.append("Zaman stopu: beklenen sürede hareket başlamadı")
    if _f(item.get("kalibre_olasilik"), 50) < 45: reasons.append("Model olasılığı belirgin biçimde düştü")
    trailing = initial
    if current > entry:
        trailing = max(entry*1.002, current-atr*1.6, initial)
    return {"teknik_stop": round(technical, 2), "atr_stop": round(atr_stop, 2),
        "zaman_stop_gunu": duration, "baslangic_stop": round(initial, 2),
        "iz_suren_stop": round(trailing, 2), "erken_cikis_uyarisi": " | ".join(reasons),
        "erken_cikis_gerekli": bool(reasons)}


def _kap_verified(item: dict) -> tuple[bool, str]:
    timestamp = _text(item, "kap_yayin_zamani", "kap_tarihi", "haber_tarihi")
    source = _text(item, "kap_url", "kap_basliklari", "haber_basliklari")
    negative = _f(item.get("kap_skor")) < 0 or "olumsuz" in _text(item, "kap_etiket", "haber_etiket").casefold()
    if not timestamp or not source:
        return False, "KAP/haber doğrulaması yapılamadı"
    return not negative, "Negatif KAP/haber riski" if negative else "Yayın zamanı doğrulanmış"


def karar_kapilari_uygula(item: dict, market: dict, sectors: dict[str, dict], strategy_id: str = "general_scan",
                          calibrated_probability: float | None = None, calibration_samples: int = 0,
                          protection_mode: bool = False, capital: float = 100_000,
                          limits: RiskLimits = RiskLimits(), costs: CostModel = CostModel()) -> dict[str, Any]:
    price = _f(item.get("price")); entry_low = _f(item.get("onerilen_alis_alt", item.get("alis_araligi_alt")))
    entry_high = _f(item.get("onerilen_alis_ust", item.get("alis_araligi_ust")))
    target = _f(item.get("onerilen_satis", item.get("hedef_1"))); stop = _f(item.get("onerilen_stop", item.get("stop_loss")))
    rr = _f(item.get("karar_risk_getiri", item.get("risk_getiri_1")))
    confidence = _f(item.get("v4_guven_puani", item.get("guven"))) - _f(market.get("uncertainty_penalty"))
    sector_name = _text(item, "sektor", "sector", "sektor_adi") or "BİLİNMİYOR"
    sector = sectors.get(sector_name, sectors.get("BİLİNMİYOR", {"score": 35, "class": "Nötr", "verified": False, "relative_strength": 0}))
    flow = para_akisi_teyidi(item)
    kap_ok, kap_reason = _kap_verified(item)
    probability = calibrated_probability if calibration_samples >= 30 and calibrated_probability is not None else None
    ev = net_ev_hesapla(probability or 0, max(entry_high, price), target, stop, costs)
    turnover = _f(item.get("ortalama_gunluk_islem_tutari", item.get("average_turnover")))
    data_ok = _f(item.get("veri_guven_puani")) >= 70 and _f(item.get("veri_yasi_gun", item.get("veri_yasi")), 0) <= 4
    trend_ok = price > _f(item.get("ema20")) > _f(item.get("ema50")) > 0 and _f(item.get("adx")) >= 20
    sector_ok = bool(sector.get("verified")) and (sector.get("score", 0) >= 45 or _f(item.get("ret_20"))-market.get("median_ret20", 0) >= 8)
    distance = ((price/entry_high)-1)*100 if entry_high > 0 else 999
    resistance_distance = _f(item.get("direnc_mesafe_yuzde"), 999)
    entry_ok = entry_low > 0 and entry_high >= entry_low and distance <= 2.5 and resistance_distance > 2 and _f(item.get("rsi"), 50) < 72
    liquidity_ok = turnover >= 5_000_000
    regime = market.get("regime", "YATAY")
    regime_ok = not (regime == "RISK_OFF" and strategy_id in {"daily_trade", "ceiling_potential"})
    if regime == "YATAY":
        regime_ok = flow["confirmed"] and (_text(item, "formasyon_teyit").casefold() == "evet" or _f(item.get("volume_ratio")) >= 1.2)
    ev_ok = probability is not None and ev["net_ev_pct"] > 0 and rr >= 1.4
    portfolio_ok = not protection_mode
    calibrated_ok = probability is not None and probability < 100 and calibration_samples >= 30
    gates = [
        ("Veri kalitesi", data_ok, "Veri güveni veya güncelliği yetersiz"),
        ("Piyasa rejimi", regime_ok, f"{regime} yeni alış için uygun değil"),
        ("Sektör gücü", sector_ok, "Sektör doğrulaması/göreceli gücü yetersiz"),
        ("Hisse trendi", trend_ok, "EMA/ADX trend teyidi yok"),
        ("Para ve hacim girişi", flow["confirmed"], flow["reason"]),
        ("KAP, bilanço ve haber", kap_ok, kap_reason),
        ("Giriş bölgesi", entry_ok, "Fiyat ideal girişten uzak, dirence yakın veya RSI yüksek"),
        ("Net beklenen değer", ev_ok, "Maliyet sonrası EV/olasılık/risk-getiri yetersiz"),
        ("Likidite", liquidity_ok, "Ortalama işlem tutarı yetersiz"),
        ("Portföy riski", portfolio_ok, "Koruma modu veya risk limiti aktif"),
        ("Kalibre edilmiş olasılık", calibrated_ok, "Yetersiz geçmiş örnek — olasılık güvenilir değil"),
    ]
    failed = [reason for _, ok, reason in gates if not ok]
    critical_data = not data_ok or price <= 0 or not (0 < stop < max(price, entry_high) < target)
    if critical_data:
        decision = "VERİ YETERSİZ"
    elif not failed:
        decision = "UYGUN ADAY"
    elif entry_ok is False and all(ok for name, ok, _ in gates if name not in {"Giriş bölgesi", "Kalibre edilmiş olasılık"}):
        decision = "TEYİT BEKLİYOR"
    elif sum(ok for _, ok, _ in gates) >= 7:
        decision = "İZLE"
    else:
        decision = "İŞLEM YAPMA"
    if protection_mode or (regime == "RISK_OFF" and strategy_id in {"daily_trade", "ceiling_potential"}):
        decision = "İZLE" if not critical_data else decision
    pos = pozisyon_hesapla(capital, max(entry_high, price), stop, limits, .5 if regime == "YUKSEK_OYNAKLIK" else 1)
    stops = stop_yonetimi({**item, "piyasa_rejimi_v2": regime, "sektor_gucu": sector.get("class", "Nötr"),
                           "kalibre_olasilik": probability}, max(entry_high, price), price, stop)
    return {
        "profesyonel_karar": decision, "kalibre_olasilik": round(probability, 1) if probability is not None else None,
        "kalibrasyon_ornek": calibration_samples, "piyasa_rejimi_v2": regime,
        "piyasa_rejim_puani": market.get("score", 0), "piyasa_rejim_guveni": market.get("confidence", 0),
        "sektor_adi": sector_name, "sektor_puani": sector.get("score", 0), "sektor_gucu": sector.get("class", "Nötr"),
        "sektor_goreceli_guc": sector.get("relative_strength", 0), "para_akisi_puani": flow["score"],
        "para_akisi_teyidi": "TEYİTLİ" if flow["confirmed"] else "TEYİTSİZ", "net_ev_yuzde": ev["net_ev_pct"],
        "tahmini_maliyet_yuzde": ev["cost_pct"], "giris_bolgesine_uzaklik_yuzde": round(distance, 2),
        "teyit_seviyesi": round(max(entry_high, _f(item.get("formasyon_kirilim"))), 2),
        "gecersiz_kilan_seviye": round(stop, 2), "kap_haber_dogrulama": kap_reason,
        "karar_kapilari": " | ".join(f"{name}:{'GEÇTİ' if ok else 'KALDI'}" for name, ok, _ in gates),
        "onerilmeme_nedeni": " | ".join(failed[:5]) if failed else "Bütün güvenlik kapıları geçildi",
        "koruma_modu": bool(protection_mode), "ayarlanmis_guven": round(max(0, confidence), 1), **pos, **stops,
    }


def kalibrasyon_ozeti(history: pd.DataFrame, strategy: str) -> dict[str, Any]:
    if history is None or history.empty:
        return {"samples": 0, "probability": None, "brier": None, "status": "Yetersiz geçmiş örnek — olasılık güvenilir değil."}
    work = history.copy()
    if "Strateji" in work:
        work = work[work["Strateji"].astype(str).str.casefold().eq(strategy.casefold())]
    status_col = next((c for c in ("Durum", "outcome", "Sonuç") if c in work), None)
    prob_col = next((c for c in ("Kalibre Edilmiş Olasılık", "Model Olasılığı %", "probability") if c in work), None)
    if not status_col:
        return {"samples": 0, "probability": None, "brier": None, "status": "Yetersiz geçmiş örnek — olasılık güvenilir değil."}
    closed = work[~work[status_col].astype(str).str.contains("AÇIK|ACIK", case=False, na=False)].copy()
    y = closed[status_col].astype(str).str.contains("HEDEF|BAŞARILI", case=False, na=False).astype(float)
    n = len(y)
    if n < 30:
        return {"samples": n, "probability": None, "brier": None, "status": "Yetersiz geçmiş örnek — olasılık güvenilir değil."}
    probability = float(y.mean()*100)
    if prob_col:
        p = pd.to_numeric(closed[prob_col], errors="coerce").fillna(50).clip(0, 99)/100
        brier = float(((p-y)**2).mean())
    else:
        brier = float(((probability/100-y)**2).mean())
    return {"samples": n, "probability": min(99.0, round(probability, 1)), "brier": round(brier, 4),
            "success_rate": round(probability, 1), "status": "Kalibre edildi"}


def karar_kapilarini_toplu_uygula(results: list[dict], history: pd.DataFrame | None = None,
                                  strategy_id: str = "general_scan", protection_mode: bool = False,
                                  capital: float = 100_000,
                                  limits: RiskLimits = RiskLimits(),
                                  costs: CostModel = CostModel()) -> tuple[list[dict], dict, dict]:
    market = piyasa_rejimi_hesapla(results)
    sectors = sektor_profilleri_hesapla(results, market)
    calibration = kalibrasyon_ozeti(history if history is not None else pd.DataFrame(), strategy_id)
    for item in results:
        item.update(karar_kapilari_uygula(item, market, sectors, strategy_id,
            calibration.get("probability"), calibration.get("samples", 0), protection_mode,
            capital, limits, costs))
        # Eski AL etiketinin güvenlik kapılarını aşmasını önle.
        if item["profesyonel_karar"] != "UYGUN ADAY" and item.get("yatirim_karari") == "BUGÜN AL":
            item["yatirim_karari"] = item["profesyonel_karar"]
    return results, market, calibration


def append_only_event(event: dict, path: Path) -> dict:
    """Hash zincirli JSONL olay günlüğü; mevcut kayıt asla yeniden yazılmaz."""
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = "GENESIS"
    if path.exists():
        try:
            last = path.read_text(encoding="utf-8").splitlines()[-1]
            previous_hash = json.loads(last).get("event_hash", "GENESIS")
        except Exception:
            previous_hash = "UNREADABLE_PREVIOUS"
    payload = {**event}
    payload.setdefault("event_id", uuid.uuid4().hex)
    payload.setdefault("event_time", datetime.now(timezone.utc).isoformat())
    payload["previous_hash"] = previous_hash
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload["event_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)+"\n")
    return payload


def tahminleri_kaydet(results: Iterable[dict], strategy_id: str, path: Path) -> list[dict]:
    saved = []
    for item in results:
        if item.get("profesyonel_karar") not in {"UYGUN ADAY", "TEYİT BEKLİYOR", "İZLE"}:
            continue
        saved.append(append_only_event({
            "event_type": "SIGNAL_CREATED", "signal_id": uuid.uuid4().hex,
            "symbol": item.get("symbol"), "strategy_id": strategy_id,
            "data_time": item.get("veri_zamani", item.get("veri_tarihi", "")),
            "market_regime": item.get("piyasa_rejimi_v2"), "sector_score": item.get("sektor_puani"),
            "entry_low": item.get("onerilen_alis_alt"), "entry_high": item.get("onerilen_alis_ust"),
            "target_1": item.get("hedef_1"), "target_2": item.get("onerilen_satis", item.get("hedef_2")),
            "stop": item.get("onerilen_stop"), "duration": item.get("beklenen_sure"),
            "confidence": item.get("ayarlanmis_guven"), "calibrated_probability": item.get("kalibre_olasilik"),
            "risk_reward": item.get("karar_risk_getiri"), "net_ev": item.get("net_ev_yuzde"),
            "decision": item.get("profesyonel_karar"),
        }, path))
    return saved
