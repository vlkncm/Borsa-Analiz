"""Point-in-time T+1/T+2 ozellik, etiket, siralama ve snapshot altyapisi.

Skor olasilik degildir. Yalniz egitim disi kalibrasyon metrikleri tasiyan bir model
artefakti yuzde uretebilir. Tum fonksiyonlar verilen T kesiminden sonrasini ozellige
dahil etmez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from fiyat_limitleri import fiyat_adimi, pay_fiyat_limitleri


DATA_VERSION = "t1t2-pit-v3"
MODEL_VERSION = "t1t2-reference-v2"
HORIZONS = ("T+1", "T+2")
TARGETS_BY_HORIZON = {
    "T+1": ("max_5", "max_7", "max_8", "limit_up", "close_5", "target_before_stop"),
    "T+2": ("max_5", "max_7", "max_8", "limit_up", "close_positive", "target_before_stop"),
}
TARGETS = tuple(sorted({target for values in TARGETS_BY_HORIZON.values() for target in values}))
NORMAL_SECURITY_TYPES = {"NORMAL_PAY"}
ISTANBUL = ZoneInfo("Europe/Istanbul")


def snapshot_is_timely(as_of: Any, created_at: Any | None = None) -> bool:
    """Snapshot'in sonucu gorerek uretilmedigini seans penceresiyle denetler."""
    cutoff=pd.Timestamp(as_of)
    cutoff_date=cutoff.date()
    created=pd.Timestamp(created_at or datetime.now(timezone.utc))
    if created.tzinfo is None:
        created=created.tz_localize("UTC")
    local=created.tz_convert(ISTANBUL)
    if local.date()==cutoff_date:
        return (local.hour,local.minute)>=(18,15)
    if local.date()>cutoff_date:
        if local.weekday() >= 5:
            return True
        # Ertesi islem seansi acildiktan sonra T kapanis tahmini uretilemez.
        return (local.hour,local.minute)<(10,0)
    return False


@dataclass(frozen=True)
class CacheIdentity:
    symbol: str
    as_of_timestamp: str
    horizon: str
    analysis_type: str
    model_version: str
    data_version: str = DATA_VERSION

    @property
    def key(self) -> str:
        payload = asdict(self)
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class ModelArtifact:
    horizon: str
    target: str
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    calibration_method: str
    calibration_a: float
    calibration_b: float
    calibration_samples: int
    untouched_test_start: str
    untouched_test_end: str
    brier_score: float
    model_version: str = MODEL_VERSION
    isotonic_x: tuple[float, ...] = ()
    isotonic_y: tuple[float, ...] = ()

    @property
    def reliable(self) -> bool:
        return (self.horizon in HORIZONS and self.target in TARGETS and
                self.calibration_method in {"sigmoid","isotonic"} and self.calibration_samples >= 200 and
                bool(self.untouched_test_start and self.untouched_test_end) and
                len(self.feature_names) == len(self.coefficients) and
                (self.calibration_method!="isotonic" or len(self.isotonic_x)==len(self.isotonic_y)>1))


@dataclass(frozen=True)
class Prediction:
    symbol: str
    as_of_timestamp: str
    horizon: str
    security_type: str
    feature_hash: str
    feature_count: int
    missing_features: tuple[str, ...]
    raw_score: float | None
    probabilities: Mapping[str, float | None]
    status: str
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    cache_key: str
    model_version: str
    data_version: str = DATA_VERSION
    current_price: float | None = None
    ceiling_price: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    target_7: float | None = None
    target_8: float | None = None
    stop: float | None = None
    risk_reward: float | None = None
    net_ev_pct: float | None = None
    levels_valid: bool = False

    def dict(self):
        return asdict(self)


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce")


def point_in_time_features(frame: pd.DataFrame, as_of: Any,
                           benchmark: pd.DataFrame | None = None,
                           sector: pd.DataFrame | None = None) -> dict[str, float]:
    """Yalniz ``as_of`` dahil tamamlanmis barlardan sembole ozel ozellik cikarir."""
    if frame is None or frame.empty:
        return {}
    cutoff = pd.Timestamp(as_of)
    work = frame.loc[frame.index <= cutoff].copy().sort_index()
    required = {"Open", "High", "Low", "Close", "Volume"}
    if len(work) < 21 or not required.issubset(work.columns):
        return {}
    o, h, l, c, v = (_series(work, name) for name in ("Open", "High", "Low", "Close", "Volume"))
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    typical = (h+l+c)/3
    mf = typical*v
    positive = mf.where(typical.diff() > 0, 0).rolling(14).sum()
    negative = mf.where(typical.diff() < 0, 0).rolling(14).sum()
    ratio = positive/negative.replace(0, np.nan)
    mfi = (100-100/(1+ratio)).where(negative.ne(0), 100.0).where((positive+negative).ne(0), 50.0)
    # Tavan kilitli gibi High=Low barlar tum model girdisini NaN yapmamali.
    multiplier = (((c-l)-(h-c))/(h-l).replace(0, np.nan)).fillna(0.0)
    cmf = (multiplier*v).rolling(20).sum()/v.rolling(20).sum().replace(0, np.nan)
    obv = (np.sign(c.diff()).fillna(0)*v).cumsum()
    last = float(c.iloc[-1]); day_range = float(h.iloc[-1]-l.iloc[-1])
    average_volume=float(v.iloc[-20:].mean())
    result: dict[str, float] = {
        "price": last,
        **{f"ret_{n}": float(c.pct_change(n).iloc[-1]) for n in (1, 2, 3, 5, 10, 20)},
        "price_acceleration_2": float(c.pct_change().diff().iloc[-2:].mean()),
        "volume_acceleration_2": float(v.pct_change().replace([np.inf, -np.inf], np.nan).iloc[-2:].mean()),
        "open_close_return": float(c.iloc[-1]/o.iloc[-1]-1),
        "close_location": float((last-l.iloc[-1])/day_range) if day_range > 0 else .5,
        "higher_high_2": float(h.iloc[-1] > h.iloc[-2]),
        "higher_low_2": float(l.iloc[-1] > l.iloc[-2]),
        "resistance20_distance": float(h.iloc[-20:].max()/last-1),
        "compression20": float((h.iloc[-20:].max()-l.iloc[-20:].min())/last),
        "atr_pct": float(atr.iloc[-1]/last),
        "atr_change_5": float(atr.iloc[-1]/atr.iloc[-6]-1) if atr.iloc[-6] else np.nan,
        "realized_vol20": float(c.pct_change().iloc[-20:].std(ddof=0)*math.sqrt(252)),
        "relative_volume": float(v.iloc[-1]/average_volume) if average_volume>0 else np.nan,
        "volume_persistence": float((v.iloc[-5:] > v.iloc[-20:].median()).mean()),
        "obv_slope_5": float((obv.iloc[-1]-obv.iloc[-6])/max(v.iloc[-20:].mean(), 1)),
        "cmf20": float(cmf.iloc[-1]), "mfi14": float(mfi.iloc[-1]),
        "turnover20": float(last*v.iloc[-20:].mean()),
        "estimated_slippage": float(min(.03, max(.0002, 2_000_000/max(last*v.iloc[-20:].mean(), 1)))),
        "move_realized_5_atr": float((last-c.iloc[-6])/max(float(atr.iloc[-1]), .01)),
    }
    for prefix, other in (("bist", benchmark), ("sector", sector)):
        if other is not None and not other.empty and "Close" in other:
            oc = _series(other.loc[other.index <= cutoff], "Close")
            aligned = pd.concat([c, oc], axis=1, join="inner").dropna()
            result[f"relative_strength_{prefix}_5"] = (float(aligned.iloc[-1, 0]/aligned.iloc[-6, 0] -
                                                                   aligned.iloc[-1, 1]/aligned.iloc[-6, 1])
                                                         if len(aligned) >= 6 else np.nan)
        else:
            result[f"relative_strength_{prefix}_5"] = np.nan
    return {key: float(value) for key, value in result.items()
            if isinstance(value, (int, float, np.number)) and math.isfinite(float(value))}


def short_history_features(frame: pd.DataFrame, as_of: Any) -> dict[str, float]:
    """3–20 seanslik payi kaybetmeden yalniz mevcut kisa momentumunu tanimlar."""
    if frame is None or frame.empty:
        return {}
    work=frame.loc[frame.index<=pd.Timestamp(as_of)].copy().sort_index()
    if len(work)<3 or not {"Open","High","Low","Close","Volume"}.issubset(work):
        return {}
    o,h,l,c,v=(_series(work,name) for name in ("Open","High","Low","Close","Volume"))
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    price=float(c.iloc[-1]); day_range=float(h.iloc[-1]-l.iloc[-1]); features={
        "price":price,
        "session_count":float(len(work)),
        "ret_1":float(c.pct_change(1).iloc[-1]),
        "ret_2":float(c.pct_change(2).iloc[-1]),
        "ret_3":float(c.pct_change(min(3,len(work)-1)).iloc[-1]),
        "open_close_return":float(c.iloc[-1]/o.iloc[-1]-1),
        "close_location":float((price-l.iloc[-1])/day_range) if day_range>0 else .5,
        "relative_volume":float(v.iloc[-1]/v.iloc[:-1].mean()) if v.iloc[:-1].mean()>0 else 1.,
        "volume_persistence":float((v>v.median()).mean()),
        "turnover20":float(price*v.mean()),
        "atr_pct":float(tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1]/price),
        "move_realized_5_atr":float((price-c.iloc[0])/max(float(tr.mean()),.01)),
    }
    return {key:float(value) for key,value in features.items() if math.isfinite(float(value))}


def feature_hash(features: Mapping[str, float]) -> str:
    canonical = json.dumps({k: round(float(v), 10) for k, v in sorted(features.items())}, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def t1t2_labels(frame: pd.DataFrame, position: int, target: float | None = None,
                stop: float | None = None) -> dict[str, int | None]:
    """T kapanisindan sonraki iki barla etiketler; bu fonksiyon ozellik uretmez."""
    if position < 0 or position+2 >= len(frame):
        return {}
    t, t1, t2 = frame.iloc[position], frame.iloc[position+1], frame.iloc[position+2]
    close = float(t.Close)
    limit_t1 = float(pay_fiyat_limitleri(close).ust_limit)
    limit_t2 = float(pay_fiyat_limitleri(float(t1.Close)).ust_limit)
    t1_max = float(t1.High/close-1); t2_max = float(max(t1.High, t2.High)/close-1)

    def target_before_stop(rows) -> int | None:
        if target is None or stop is None:
            return None
        for row in rows:
            hit_target, hit_stop = float(row.High) >= target, float(row.Low) <= stop
            if hit_target and hit_stop:
                return 0  # dakika verisi yok: lehe yazma
            if hit_stop: return 0
            if hit_target: return 1
        return 0

    return {
        "y_t1_close_positive": int(float(t1.Close) > close),
        "y_t1_max_return_3": int(t1_max >= .03), "y_t1_max_return_5": int(t1_max >= .05),
        "y_t1_max_return_7": int(t1_max >= .07),
        "y_t1_max_return_8": int(t1_max >= .08), "y_t1_limit_up_hit": int(float(t1.High) >= limit_t1),
        "y_t1_close_return_5": int(float(t1.Close)/close-1 >= .05),
        "y_t1_target_before_stop": target_before_stop([t1]),
        "y_t2_close_positive": int(float(t2.Close) > close),
        "y_t2_max_return_3": int(t2_max >= .03), "y_t2_max_return_5": int(t2_max >= .05),
        "y_t2_max_return_7": int(t2_max >= .07),
        "y_t2_max_return_8": int(t2_max >= .08), "y_t2_any_limit_up_hit": int(float(t1.High) >= limit_t1 or float(t2.High) >= limit_t2),
        "y_t2_target_before_stop": target_before_stop([t1, t2]),
    }


def build_point_in_time_dataset(frames: Mapping[str, pd.DataFrame], minimum_history: int = 60) -> pd.DataFrame:
    """Kazanan/kaybeden ayrimi yapmadan tum uygun T gunlerini veri setine alir."""
    rows = []
    for symbol, frame in frames.items():
        work = frame.sort_index().copy()
        if len(work)<minimum_history+2 or not {"Open","High","Low","Close","Volume"}.issubset(work): continue
        ff=_vectorized_feature_frame(work)
        for pos in range(minimum_history-1,len(work)-2):
            values=ff.iloc[pos].dropna().to_dict()
            close=float(work.iloc[pos].Close); atr_value=values.get("atr_pct",0)*close
            labels=t1t2_labels(work,pos,target=close*1.07,stop=close-1.2*atr_value) if atr_value>0 else t1t2_labels(work,pos)
            if values and labels: rows.append({"symbol":symbol,"as_of":str(work.index[pos]),**values,**labels})
    return pd.DataFrame(rows)


def _vectorized_feature_frame(work: pd.DataFrame) -> pd.DataFrame:
    """Veri seti olustururken ayni rolling serileri her T icin yeniden hesaplamaz."""
    o,h,l,c,v=(_series(work,name) for name in ("Open","High","Low","Close","Volume"))
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1); atr=tr.ewm(alpha=1/14,adjust=False).mean()
    typical=(h+l+c)/3; mf=typical*v
    positive=mf.where(typical.diff()>0,0).rolling(14).sum(); negative=mf.where(typical.diff()<0,0).rolling(14).sum()
    multiplier=(((c-l)-(h-c))/(h-l).replace(0,np.nan)).fillna(0.0); obv=(np.sign(c.diff()).fillna(0)*v).cumsum()
    result=pd.DataFrame(index=work.index); result["price"]=c
    for n in (1,2,3,5,10,20): result[f"ret_{n}"]=c.pct_change(n)
    result["price_acceleration_2"]=c.pct_change().diff().rolling(2).mean()
    result["volume_acceleration_2"]=v.pct_change().replace([np.inf,-np.inf],np.nan).rolling(2).mean()
    result["open_close_return"]=c/o-1; result["close_location"]=(c-l)/(h-l).replace(0,np.nan)
    result["higher_high_2"]=(h>h.shift()).astype(float); result["higher_low_2"]=(l>l.shift()).astype(float)
    result["resistance20_distance"]=h.rolling(20).max()/c-1
    result["compression20"]=(h.rolling(20).max()-l.rolling(20).min())/c
    result["atr_pct"]=atr/c; result["atr_change_5"]=atr/atr.shift(5)-1
    result["realized_vol20"]=c.pct_change().rolling(20).std(ddof=0)*math.sqrt(252)
    result["relative_volume"]=v/v.rolling(20).mean(); result["volume_persistence"]=(v>v.rolling(20).median()).rolling(5).mean()
    result["obv_slope_5"]=(obv-obv.shift(5))/v.rolling(20).mean().clip(lower=1)
    result["cmf20"]=(multiplier*v).rolling(20).sum()/v.rolling(20).sum().replace(0,np.nan)
    ratio=positive/negative.replace(0,np.nan)
    result["mfi14"]=(100-100/(1+ratio)).where(negative.ne(0),100.0).where((positive+negative).ne(0),50.0)
    result["turnover20"]=c*v.rolling(20).mean()
    result["estimated_slippage"]=(2_000_000/result["turnover20"].clip(lower=1)).clip(.0002,.03)
    result["move_realized_5_atr"]=(c-c.shift(5))/atr.clip(lower=.01)
    return result


def _sigmoid(value: float) -> float:
    return 1/(1+math.exp(-max(-35, min(35, value))))


def tick_price(value: float, direction: str = "nearest") -> float:
    """Pay fiyatini gecerli BIST adimina, hedef/stop icin muhafazakar yuvarlar."""
    step=fiyat_adimi(value); ratio=Decimal(str(value))/step
    rounding=ROUND_FLOOR if direction=="down" else ROUND_CEILING if direction=="up" else None
    units=ratio.to_integral_value(rounding=rounding) if rounding else ratio.to_integral_value()
    return float(units*step)


def predict_symbol(symbol: str, frame: pd.DataFrame, as_of: Any, horizon: str,
                   artifacts: Mapping[str, ModelArtifact] | None = None,
                   security_type: str = "BELIRSIZ", benchmark=None, sector=None) -> Prediction:
    work=frame.loc[frame.index<=pd.Timestamp(as_of)] if frame is not None and not frame.empty else pd.DataFrame()
    short_history=len(work)<60
    features = (short_history_features(work,as_of) if len(work)<21 else
                point_in_time_features(work, as_of, benchmark, sector))
    analysis_type="YENI_HALKA_ARZ" if short_history else "T1T2_AKSAM"
    identity = CacheIdentity(symbol, pd.Timestamp(as_of).isoformat(), horizon, analysis_type, MODEL_VERSION)
    required_features={name for item in (artifacts or {}).values() if item.horizon==horizon for name in item.feature_names}
    # Benchmark/sektor yoklugu ortak karar katmaninda ayri belirsizliktir.
    # Burada sadece aktif artefaktin gercek girdileri modeli kapatabilir.
    missing = tuple(sorted(required_features-set(features)))
    reasons, risks = _feature_reasons(features)
    artifacts = artifacts or {}
    probabilities: dict[str, float | None] = {}
    raw_scores = []
    for target in TARGETS_BY_HORIZON[horizon]:
        artifact = None if short_history else artifacts.get(f"{horizon}:{target}")
        if artifact is None or not artifact.reliable:
            probabilities[target] = None
            continue
        vector = [features.get(name) for name in artifact.feature_names]
        if any(value is None for value in vector):
            probabilities[target] = None
            continue
        raw = artifact.intercept+sum(float(c)*float(v) for c, v in zip(artifact.coefficients, vector))
        raw_scores.append(raw)
        probabilities[target] = (_sigmoid(artifact.calibration_a*raw+artifact.calibration_b)*100
                                 if artifact.calibration_method=="sigmoid" else
                                 float(np.interp(raw,artifact.isotonic_x,artifact.isotonic_y))*100)
    calibrated = bool(probabilities) and all(value is not None for value in probabilities.values())
    if short_history:
        moved=features.get("ret_1",0)>=.08 or features.get("move_realized_5_atr",0)>=3
        status = ("HAREKET KACTI - YENI HALKA ARZ" if moved else
                  "YENI HALKA ARZ IZLEME - KALIBRE EDILMEMIS")
        risks = (*risks, f"Yalniz {len(work)} seans var; standart model uygulanmadi")
        if moved: risks=(*risks,"Hareket baslamis; yeni alim icin gec giris riski")
    elif security_type not in NORMAL_SECURITY_TYPES:
        status = "MENKUL TURU DOGRULANMADI - GENIS RADARDA IZLE"
        risks = (*risks, f"Menkul turu ayrica dogrulanmali: {security_type}")
    elif not calibrated:
        status = "ON DEGERLENDIRME - KALIBRE EDILMEMIS"
        risks = (*risks, "T+1/T+2 modeli hazir veya kalibre degil")
    else:
        status = "KALIBRE TAHMIN"
    score = _rule_score(features)
    price=features.get("price"); atr=(features.get("atr_pct",0)*price if price else None)
    entry_low=entry_high=target7=target8=stop=rr=net_ev=None; levels_valid=False
    if price and atr and atr>0:
        entry_low=tick_price(price-.35*atr,"down"); entry_high=tick_price(price+.15*atr,"up")
        target7=tick_price(price*1.07,"down"); target8=tick_price(price*1.08,"down")
        stop=tick_price(price-1.2*atr,"up")
        risk=entry_high-stop; reward=target7-entry_high
        rr=reward/risk if risk>0 else None
        levels_valid=bool(entry_low<=entry_high and stop<entry_high<target7 and
                          (entry_high-entry_low)/price<=.035 and rr is not None and .5<=rr<=8)
        p=probabilities.get("target_before_stop")
        if p is not None:
            net_ev=(p/100)*(target7/entry_high-1)*100-(1-p/100)*(1-stop/entry_high)*100-.4
    return Prediction(symbol, pd.Timestamp(as_of).isoformat(), horizon, security_type,
                      feature_hash(features), len(features), missing,
                      float(np.mean(raw_scores)) if raw_scores else score,
                      dict(probabilities), status, tuple(reasons[:3]), tuple(risks[:3]),
                      identity.key, MODEL_VERSION, DATA_VERSION, price,
                      (float(pay_fiyat_limitleri(price).ust_limit) if price else None),
                      entry_low,entry_high,target7,target8,stop,rr,net_ev,levels_valid)


def _rule_score(f):
    if not f: return None
    score = 50 + 12*np.tanh(f.get("ret_5", 0)*10) + 10*np.tanh((f.get("relative_volume", 1)-1))
    score += 8*(f.get("close_location", .5)-.5) + 6*np.tanh(f.get("obv_slope_5", 0))
    score -= 10*max(0, f.get("move_realized_5_atr", 0)-3)/3
    return float(max(0, min(100, score)))


def _rule_scores_frame(rows: pd.DataFrame) -> np.ndarray:
    """Ayni ozelliklerden egitimsiz, aciklanabilir kural tabanli referans skor."""
    ret5=pd.to_numeric(rows.get("ret_5",0),errors="coerce").fillna(0).to_numpy(float)
    rvol=pd.to_numeric(rows.get("relative_volume",1),errors="coerce").fillna(1).to_numpy(float)
    location=pd.to_numeric(rows.get("close_location",.5),errors="coerce").fillna(.5).to_numpy(float)
    obv=pd.to_numeric(rows.get("obv_slope_5",0),errors="coerce").fillna(0).to_numpy(float)
    moved=pd.to_numeric(rows.get("move_realized_5_atr",0),errors="coerce").fillna(0).to_numpy(float)
    score=50+12*np.tanh(ret5*10)+10*np.tanh(rvol-1)+8*(location-.5)+6*np.tanh(obv)
    score-=10*np.maximum(0,moved-3)/3
    return np.clip(score,0,100)


def _feature_reasons(f):
    if not f: return ["Gecerli point-in-time ozellik vektoru olusmadi"], ["OHLCV yetersiz"]
    candidates = [
        (abs(f.get("relative_volume", 1)-1), f"Goreceli hacim {f.get('relative_volume', 0):.2f}x"),
        (abs(f.get("ret_5", 0)), f"5 gunluk getiri %{f.get('ret_5', 0)*100:.2f}"),
        (abs(f.get("close_location", .5)-.5), f"Kapanis gunluk araligin %{f.get('close_location', 0)*100:.0f} seviyesinde"),
        (abs(f.get("cmf20", 0)), f"CMF para akisi {f.get('cmf20', 0):.2f}"),
    ]
    reasons = [text for _, text in sorted(candidates, reverse=True)[:3]]
    risks = []
    if f.get("move_realized_5_atr", 0) > 3: risks.append(f"Hareket {f['move_realized_5_atr']:.1f} ATR ilerlemis")
    if f.get("estimated_slippage", 0) > .01: risks.append(f"Tahmini kayma %{f['estimated_slippage']*100:.2f}")
    if f.get("relative_volume", 1) < .7: risks.append("Hacim teyidi zayif")
    return reasons, risks


def cross_sectional_rank(predictions: Iterable[Prediction]) -> list[dict[str, Any]]:
    rows = [p.dict() for p in predictions]
    if not rows: return []
    frame = pd.DataFrame(rows)
    frame["raw_score"] = pd.to_numeric(frame["raw_score"], errors="coerce")
    def ranking_score(probabilities):
        values=[probabilities.get(name) for name in ("max_7","max_8","limit_up")]
        return None if any(value is None for value in values) else .45*values[0]+.40*values[1]+.15*values[2]
    frame["ranking_score"]=frame["probabilities"].map(ranking_score)
    frame["calibrated"]=frame["ranking_score"].notna()
    frame = frame.sort_values(["calibrated","ranking_score","raw_score","symbol"],
                              ascending=[False,False,False,True],na_position="last").reset_index(drop=True)
    total = len(frame)
    frame["rank"] = np.arange(1, total+1)
    frame["percentile"] = (total-frame["rank"]+1)/total*100
    frame["universe_size"] = total
    return frame.to_dict("records")


def radar_lists(predictions: Iterable[Prediction], wide_limit: int = 30) -> dict[str,list[dict[str,Any]]]:
    """Geriye uyumlu API; karar formulu ortak CandidateDecision motorundadir."""
    from aday_karar_sistemi import build_candidate_decisions
    ranked=cross_sectional_rank(predictions)
    contexts={row["symbol"]:{"data_freshness":"GUNCEL"} for row in ranked}
    decisions=build_candidate_decisions(ranked,market_regime="YATAY",contexts=contexts,wide_limit=wide_limit)
    return {"wide":[item.dict() for item in decisions if item.eligible_wide],
            "elite":[item.dict() for item in decisions if item.eligible_elite][:5]}


def ranking_metrics(rows: pd.DataFrame, score_column: str, label_column: str,
                    ks=(1, 3, 5, 10, 20)) -> dict[str, float | None]:
    if rows.empty or not {score_column, label_column}.issubset(rows): return {}
    ordered = rows.dropna(subset=[score_column, label_column]).sort_values(score_column, ascending=False)
    positives = int(ordered[label_column].sum())
    result = {}
    for k in ks:
        top = ordered.head(k)
        hits = int(top[label_column].sum())
        result[f"precision_at_{k}"] = hits/len(top) if len(top) else None
        result[f"recall_at_{k}"] = hits/positives if positives else None
    result["false_positive_rate_at_10"] = (int((ordered.head(10)[label_column] == 0).sum())/len(ordered.head(10))
                                            if len(ordered.head(10)) else None)
    return result


def daily_ranking_metrics(rows: pd.DataFrame, date_column: str, score_column: str,
                          label_column: str, ks=(1,3,5,10,20)) -> dict[str,float|None]:
    """Precision/recall'i her gunun tum hisseleri icindeki kesitsel siradan olcer."""
    reports=[]
    for _date,group in rows.groupby(date_column):
        if group[label_column].sum()>0: reports.append(ranking_metrics(group,score_column,label_column,ks))
    keys={key for report in reports for key in report}
    return {key:(float(np.mean([r[key] for r in reports if r.get(key) is not None]))
                 if any(r.get(key) is not None for r in reports) else None) for key in keys}


def _fit_logistic(x: np.ndarray, y: np.ndarray, iterations: int = 800,
                  learning_rate: float = .05, l2: float = .01) -> tuple[np.ndarray, float]:
    """Harici ML bagimliligi olmadan aciklanabilir lojistik referans."""
    weights=np.zeros(x.shape[1],dtype=float); intercept=0.0
    for _ in range(iterations):
        logits=np.clip(x@weights+intercept,-30,30); probs=1/(1+np.exp(-logits))
        error=probs-y
        weights-=learning_rate*((x.T@error)/len(x)+l2*weights)
        intercept-=learning_rate*float(error.mean())
    return weights, intercept


def _fit_isotonic(scores: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    """Pool-adjacent-violators ile tek boyutlu isotonic kalibrasyon."""
    order=np.argsort(scores); x=np.asarray(scores,dtype=float)[order]; y=np.asarray(labels,dtype=float)[order]
    blocks=[[float(xi),float(xi),float(yi),1] for xi,yi in zip(x,y)]
    index=0
    while index<len(blocks)-1:
        left=blocks[index]; right=blocks[index+1]
        if left[2]/left[3] > right[2]/right[3]:
            blocks[index:index+2]=[[left[0],right[1],left[2]+right[2],left[3]+right[3]]]
            index=max(0,index-1)
        else: index+=1
    points=np.array([(b[0]+b[1])/2 for b in blocks]); values=np.array([b[2]/b[3] for b in blocks])
    return points,values


def train_reference_artifact(dataset: pd.DataFrame, horizon: str, target: str,
                             feature_names: Iterable[str], minimum_calibration: int = 200,
                             purge_days: int = 2, embargo_days: int = 2) -> tuple[ModelArtifact | None, dict[str, Any]]:
    """Zaman sirali train/kalibrasyon/dokunulmamis test ayrimiyla artefakt uretir.

    Sinif dengesi, tarih kapsami veya kalibrasyon ornegi yetersizse artefakt aktif
    edilmez. Son test donemi model/kalibrasyon egitiminde kullanilmaz.
    """
    label={
        ("T+1","max_5"):"y_t1_max_return_5", ("T+1","max_7"):"y_t1_max_return_7", ("T+1","max_8"):"y_t1_max_return_8",
        ("T+1","limit_up"):"y_t1_limit_up_hit", ("T+1","target_before_stop"):"y_t1_target_before_stop",
        ("T+1","close_5"):"y_t1_close_return_5",
        ("T+2","max_5"):"y_t2_max_return_5", ("T+2","max_7"):"y_t2_max_return_7", ("T+2","max_8"):"y_t2_max_return_8",
        ("T+2","limit_up"):"y_t2_any_limit_up_hit", ("T+2","target_before_stop"):"y_t2_target_before_stop",
        ("T+2","close_positive"):"y_t2_close_positive",
    }.get((horizon,target))
    names=tuple(feature_names)
    if label is None or not names or dataset.empty or not {label,"as_of",*names}.issubset(dataset):
        return None,{"status":"YETERSIZ_VERI"}
    rows=dataset.dropna(subset=[label,"as_of",*names]).copy(); rows["as_of"]=pd.to_datetime(rows["as_of"])
    rows=rows.sort_values(["as_of","symbol"]); n=len(rows)
    if n<1000 or rows[label].nunique()<2:
        return None,{"status":"YETERSIZ_ORNEK","n":n,"pozitif":int(rows[label].sum())}
    dates=np.array(sorted(rows.as_of.dt.normalize().unique()))
    train_date_end=max(1,int(len(dates)*.60)); cal_date_end=max(train_date_end+1,int(len(dates)*.80))
    train_dates=set(dates[:max(1,train_date_end-purge_days)])
    cal_dates=set(dates[min(len(dates),train_date_end+embargo_days):max(train_date_end+embargo_days,cal_date_end-purge_days)])
    test_dates=set(dates[min(len(dates),cal_date_end+embargo_days):])
    train=rows[rows.as_of.dt.normalize().isin(train_dates)]
    cal=rows[rows.as_of.dt.normalize().isin(cal_dates)]
    test=rows[rows.as_of.dt.normalize().isin(test_dates)]
    if len(cal)<minimum_calibration or len(test)<minimum_calibration or cal[label].nunique()<2 or test[label].nunique()<2:
        return None,{"status":"KALIBRASYON_YETERSIZ","train":len(train),"calibration":len(cal),"test":len(test)}
    mean=train[list(names)].mean(); std=train[list(names)].std(ddof=0).replace(0,1)
    # Standardizasyon parametreleri artefakt ozelliklerine gomulmedigi icin katsayilar ham olcege donusturulur.
    weights_z,intercept_z=_fit_logistic(((train[list(names)]-mean)/std).to_numpy(float),train[label].to_numpy(float),iterations=180)
    weights=weights_z/std.to_numpy(float); intercept=float(intercept_z-(weights_z*mean.to_numpy(float)/std.to_numpy(float)).sum())
    cal_raw=cal[list(names)].to_numpy(float)@weights+intercept; cal_y=cal[label].to_numpy(float)
    split=max(1,int(len(cal)*.7)); fit_raw,select_raw=cal_raw[:split],cal_raw[split:]
    fit_y,select_y=cal_y[:split],cal_y[split:]
    candidate_w,candidate_b=_fit_logistic(fit_raw.reshape(-1,1),fit_y,iterations=180,learning_rate=.02,l2=.001)
    iso_x,iso_y=_fit_isotonic(fit_raw,fit_y)
    sigmoid_select=1/(1+np.exp(-np.clip(candidate_w[0]*select_raw+candidate_b,-30,30)))
    isotonic_select=np.interp(select_raw,iso_x,iso_y)
    selection_brier={"sigmoid":float(np.mean((sigmoid_select-select_y)**2)),
                     "isotonic":float(np.mean((isotonic_select-select_y)**2))}
    method=min(selection_brier,key=selection_brier.get)
    if method=="sigmoid":
        platt_w,platt_b=_fit_logistic(cal_raw.reshape(-1,1),cal_y,iterations=180,learning_rate=.02,l2=.001)
        final_iso_x=np.array([]); final_iso_y=np.array([])
    else:
        final_iso_x,final_iso_y=_fit_isotonic(cal_raw,cal_y); platt_w=np.array([0.]); platt_b=0.
    test_raw=test[list(names)].to_numpy(float)@weights+intercept
    test_prob=(1/(1+np.exp(-np.clip(platt_w[0]*test_raw+platt_b,-30,30))) if method=="sigmoid"
               else np.interp(test_raw,final_iso_x,final_iso_y))
    actual=test[label].to_numpy(float); brier=float(np.mean((test_prob-actual)**2))
    artifact=ModelArtifact(horizon,target,names,tuple(float(x) for x in weights),intercept,method,
                           float(platt_w[0]),float(platt_b),len(cal),str(test.as_of.min().date()),
                           str(test.as_of.max().date()),brier,MODEL_VERSION,
                           tuple(float(x) for x in final_iso_x),tuple(float(x) for x in final_iso_y))
    rank_report=daily_ranking_metrics(pd.DataFrame({"as_of":test.as_of.to_numpy(),"probability":test_prob,"actual":actual}),
                                      "as_of","probability","actual")
    # Egitimsiz kural tabanli skor ayni calibration/test kesiminde adil referans olarak olculur.
    rule_cal=_rule_scores_frame(cal); rule_test=_rule_scores_frame(test)
    rule_x,rule_y=_fit_isotonic(rule_cal,cal_y); rule_prob=np.interp(rule_test,rule_x,rule_y)
    rule_brier=float(np.mean((rule_prob-actual)**2))
    rule_rank=daily_ranking_metrics(pd.DataFrame({"as_of":test.as_of.to_numpy(),"probability":rule_prob,"actual":actual}),
                                    "as_of","probability","actual")
    metrics={"status":"OK","train":len(train),"calibration":len(cal),"test":len(test),"brier":brier,
             "positive_rate_test":float(actual.mean()),"test_start":artifact.untouched_test_start,
             "test_end":artifact.untouched_test_end,"calibration_method":method,
             "calibration_selection_brier":selection_brier,
             "model_comparison":{"logistic":{"brier":brier,"precision_at_10":rank_report.get("precision_at_10")},
                                 "rule_baseline":{"brier":rule_brier,"precision_at_10":rule_rank.get("precision_at_10")},
                                 "hist_gradient_boosting":"SKLEARN_BAGIMLILIGI_YOK",
                                 "active_model":"logistic"},**rank_report}
    return artifact,metrics


def save_artifacts(path: str | Path, artifacts: Mapping[str, ModelArtifact], metrics: Mapping[str, Any]):
    payload={"data_version":DATA_VERSION,"model_version":MODEL_VERSION,
             "created_at":datetime.now(timezone.utc).isoformat(),
             "artifacts":{key:asdict(value) for key,value in artifacts.items()},"metrics":dict(metrics)}
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(target.suffix+".tmp")
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(target)


def load_artifacts(path: str | Path) -> tuple[dict[str, ModelArtifact],dict[str, Any]]:
    target=Path(path)
    if not target.exists(): return {},{"status":"MODEL_DOSYASI_YOK"}
    try:
        payload=json.loads(target.read_text(encoding="utf-8"))
        if payload.get("data_version")!=DATA_VERSION: return {},{"status":"DATA_VERSION_UYUSMAZ"}
        artifacts={key:ModelArtifact(**{**value,"feature_names":tuple(value["feature_names"]),
                                        "coefficients":tuple(value["coefficients"]),
                                        "isotonic_x":tuple(value.get("isotonic_x",())),
                                        "isotonic_y":tuple(value.get("isotonic_y",()))})
                   for key,value in payload.get("artifacts",{}).items()}
        return artifacts,payload.get("metrics",{})
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        return {},{"status":"MODEL_DOSYASI_BOZUK","error":str(exc)}


class EveningSnapshotStore:
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._migrate()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=20); db.execute("PRAGMA journal_mode=WAL"); return db

    def _migrate(self):
        with closing(self._connect()) as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS t1t2_snapshots(
              id INTEGER PRIMARY KEY, snapshot_key TEXT UNIQUE NOT NULL, symbol TEXT NOT NULL,
              as_of TEXT NOT NULL, horizon TEXT NOT NULL, rank INTEGER, score REAL,
              payload_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS t1t2_outcomes(
              snapshot_id INTEGER PRIMARY KEY REFERENCES t1t2_snapshots(id), evaluated_at TEXT NOT NULL,
              payload_json TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS t1t2_snapshot_no_update BEFORE UPDATE ON t1t2_snapshots
              BEGIN SELECT RAISE(ABORT,'T1T2 snapshot degistirilemez'); END;
            CREATE TRIGGER IF NOT EXISTS t1t2_snapshot_no_delete BEFORE DELETE ON t1t2_snapshots
              BEGIN SELECT RAISE(ABORT,'T1T2 snapshot silinemez'); END;
            """); db.commit()

    def save(self, row: Mapping[str, Any]) -> tuple[bool, str | int]:
        try:
            key = row.get("cache_key") or CacheIdentity(row["symbol"], row["as_of_timestamp"], row["horizon"], "T1T2_AKSAM", row.get("model_version", MODEL_VERSION)).key
            with closing(self._connect()) as db:
                cur = db.execute("INSERT INTO t1t2_snapshots(snapshot_key,symbol,as_of,horizon,rank,score,payload_json) VALUES(?,?,?,?,?,?,?)",
                                 (key,row["symbol"],row["as_of_timestamp"],row["horizon"],row.get("rank"),
                                  row.get("reference_score",row.get("raw_score")),json.dumps(dict(row),ensure_ascii=False,default=str)))
                db.commit(); return True, int(cur.lastrowid)
        except (sqlite3.Error, OSError, KeyError, TypeError) as exc: return False, str(exc)

    def attach_outcome(self, snapshot_id: int, outcome: Mapping[str, Any], evaluated_at: str):
        try:
            with closing(self._connect()) as db:
                db.execute("INSERT INTO t1t2_outcomes VALUES(?,?,?)",(snapshot_id,evaluated_at,json.dumps(dict(outcome),ensure_ascii=False,default=str))); db.commit()
            return True, None
        except sqlite3.Error as exc: return False, str(exc)

    def audit(self, as_of: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as db:
            db.row_factory=sqlite3.Row
            rows=db.execute("SELECT s.*,o.evaluated_at,o.payload_json outcome_json FROM t1t2_snapshots s LEFT JOIN t1t2_outcomes o ON o.snapshot_id=s.id WHERE s.as_of=? ORDER BY s.horizon,s.rank",(as_of,)).fetchall()
        return [dict(row) for row in rows]

    def pending(self) -> list[dict[str, Any]]:
        """Gerceklesmesi henuz eklenmemis snapshotlari payload ile dondurur."""
        try:
            with closing(self._connect()) as db:
                db.row_factory=sqlite3.Row
                rows=db.execute("""SELECT s.* FROM t1t2_snapshots s
                    LEFT JOIN t1t2_outcomes o ON o.snapshot_id=s.id
                    WHERE o.snapshot_id IS NULL ORDER BY s.as_of,s.horizon,s.rank""").fetchall()
            result=[]
            for row in rows:
                item=dict(row); payload=json.loads(item.pop("payload_json")); result.append({**item,**payload})
            return result
        except (sqlite3.Error,OSError,ValueError,TypeError,json.JSONDecodeError):
            return []

    def performance_summary(self) -> dict[str,Any]:
        """Kayitli tahmin/gerceklesmelerden T+1 ve T+2 siralama performansi."""
        try:
            with closing(self._connect()) as db:
                rows=db.execute("""SELECT s.as_of,s.horizon,s.rank,s.payload_json,o.payload_json,s.created_at
                    FROM t1t2_snapshots s JOIN t1t2_outcomes o ON o.snapshot_id=s.id
                    ORDER BY s.as_of,s.horizon,s.rank""").fetchall()
        except sqlite3.Error:
            return {"status":"SQLITE_HATASI","total":0,"horizons":{}}
        records=[]
        for as_of,horizon,rank,prediction_json,outcome_json,created_at in rows:
            try:
                if not snapshot_is_timely(as_of,created_at):
                    continue
                prediction=json.loads(prediction_json); outcome=json.loads(outcome_json)
                records.append({"as_of":as_of,"horizon":horizon,"rank":rank,
                                "p7":prediction.get("probabilities",{}).get("max_7"),
                                "p8":prediction.get("probabilities",{}).get("max_8"),
                                "plimit":prediction.get("probabilities",{}).get("limit_up"),**outcome})
            except (ValueError,TypeError,json.JSONDecodeError):
                continue
        summaries={}
        for horizon in HORIZONS:
            group=pd.DataFrame([row for row in records if row["horizon"]==horizon])
            if group.empty: summaries[horizon]={"total":0}; continue
            summary={"total":len(group),"dates":int(group["as_of"].nunique()),
                     "hit_7":int(group["hit_7"].sum()),"hit_8":int(group["hit_8"].sum()),
                     "hit_limit_up":int(group["hit_limit_up"].sum()),
                     "avg_max_return_pct":float(group["max_return_pct"].mean()),
                     "avg_close_return_pct":float(group["close_return_pct"].mean()),
                     "avg_mae_pct":float(group["max_adverse_excursion_pct"].mean())}
            for k in (1,3,5,10,20):
                top=group[pd.to_numeric(group["rank"],errors="coerce")<=k]
                summary[f"precision_at_{k}"]=float(top["hit_7"].mean()) if len(top) else None
                summary[f"recall_at_{k}"]=float(top["hit_7"].sum()/group["hit_7"].sum()) if group["hit_7"].sum() else None
            for probability,label,name in (("p7","hit_7","brier_7"),("p8","hit_8","brier_8"),("plimit","hit_limit_up","brier_limit")):
                valid=group.dropna(subset=[probability,label])
                summary[name]=(float(np.mean((valid[probability].astype(float)/100-valid[label].astype(float))**2))
                               if len(valid) else None)
            summaries[horizon]=summary
        return {"status":"OK","total":len(records),"horizons":summaries}

    def winner_audit(self, minimum_return: float = 7.0) -> list[dict[str,Any]]:
        """Yalniz gercek snapshotlardan, sonradan tahmin uydurmadan guclu hareket denetimi."""
        try:
            with closing(self._connect()) as db:
                rows=db.execute("""SELECT s.symbol,s.as_of,s.horizon,s.rank,s.payload_json,o.payload_json,s.created_at
                    FROM t1t2_snapshots s JOIN t1t2_outcomes o ON o.snapshot_id=s.id
                    ORDER BY s.as_of DESC,s.horizon,s.rank""").fetchall()
        except sqlite3.Error: return []
        result=[]
        for symbol,as_of,horizon,rank,payload_json,outcome_json,created_at in rows:
            try:
                if not snapshot_is_timely(as_of,created_at): continue
                prediction=json.loads(payload_json); outcome=json.loads(outcome_json)
                if float(outcome.get("max_return_pct",-999))<minimum_return: continue
                result.append({"Tarih":as_of,"Hisse":symbol.replace(".IS",""),"Vade":horizon,
                               "Gerçekleşen Maksimum %":round(float(outcome["max_return_pct"]),2),
                               "Tavan Gördü":bool(outcome.get("hit_limit_up")),"Önceki Sıra":rank,
                               "Geniş Radarda":bool(prediction.get("eligible_wide",rank is not None and int(rank)<=50)),
                               "Seçkin Aday":bool(prediction.get("eligible_elite",False))})
            except (ValueError,TypeError,json.JSONDecodeError): continue
        return result

    def missed_moves_report(self, as_of: str | None = None, horizon: str = "T+1") -> dict[str, Any]:
        """Snapshot ile ayri gerceklesme tablosundan gunluk kacirma raporu."""
        try:
            with closing(self._connect()) as db:
                query="""SELECT s.symbol,s.as_of,s.rank,s.payload_json,o.payload_json,s.created_at
                         FROM t1t2_snapshots s JOIN t1t2_outcomes o ON o.snapshot_id=s.id
                         WHERE s.horizon=?"""
                args: list[Any]=[horizon]
                if as_of is not None:
                    query += " AND s.as_of=?"; args.append(as_of)
                query += " ORDER BY s.as_of,s.rank"
                rows=db.execute(query,args).fetchall()
        except sqlite3.Error as exc:
            return {"status":"SQLITE_HATASI","error":str(exc),"metrics":{},"missed":[]}
        records=[]
        invalid_snapshots=0
        for symbol,date,rank,prediction_json,outcome_json,created_at in rows:
            try:
                if not snapshot_is_timely(date,created_at):
                    invalid_snapshots+=1; continue
                pred=json.loads(prediction_json); outcome=json.loads(outcome_json)
                records.append({"symbol":symbol,"as_of":date,"rank":rank,
                                "wide":bool(pred.get("eligible_wide",False)),
                                "elite":bool(pred.get("eligible_elite",False)),
                                "decision":pred.get("final_decision"),
                                "gate_codes":pred.get("gate_codes",[]),**outcome})
            except (ValueError,TypeError,json.JSONDecodeError):
                continue
        frame=pd.DataFrame(records)
        if frame.empty:
            return {"status":"VERI_YOK","metrics":{},"missed":[],"rows":[],"invalid_snapshots":invalid_snapshots}
        metrics={"scanned":len(frame),"actual_7":int(frame.hit_7.sum()),"actual_8":int(frame.hit_8.sum()),
                 "actual_limit_up":int(frame.hit_limit_up.sum()),
                 "closed_limit_up":int(frame.get("closed_at_limit_up",pd.Series(dtype=float)).sum())}
        for k in (1,3,5,10,20):
            top=frame[pd.to_numeric(frame["rank"],errors="coerce")<=k]
            metrics[f"precision_at_{k}"]=float(top.hit_7.mean()) if len(top) else None
            metrics[f"recall_at_{k}"]=float(top.hit_7.sum()/frame.hit_7.sum()) if frame.hit_7.sum() else None
        top20=frame[pd.to_numeric(frame["rank"],errors="coerce")<=20]
        metrics["limit_recall_at_20"]=(float(top20.hit_limit_up.sum()/frame.hit_limit_up.sum())
                                        if frame.hit_limit_up.sum() else None)
        metrics["seven_recall_at_20"]=metrics.get("recall_at_20")
        top5=frame[pd.to_numeric(frame["rank"],errors="coerce")<=5]
        metrics["false_positive_rate"]=(float((top5.hit_7==0).mean()) if len(top5) else None)
        winners=frame[frame.hit_7.astype(bool)]
        missed=[]
        for row in winners[~winners.wide.astype(bool)].to_dict("records"):
            missed.append({"symbol":row["symbol"],"as_of":row["as_of"],"rank":row["rank"],
                           "max_return_pct":row.get("max_return_pct"),"hit_limit_up":row.get("hit_limit_up"),
                           "gate_codes":row.get("gate_codes") or ["OUTSIDE_TOP_PERCENTILE"],
                           "miss_type":"MODEL_OR_DATA" if row.get("rank") is None or int(row.get("rank") or 999)>50 else "FILTER"})
        return {"status":"OK","metrics":metrics,"missed":missed,"rows":records,"invalid_snapshots":invalid_snapshots}

    def write_daily_missed_moves_reports(self, folder: str | Path) -> dict[str, int]:
        """Sonuclanmis her kesim/vade icin degistirilemez JSON denetimi yaz."""
        target=Path(folder); target.mkdir(parents=True,exist_ok=True)
        try:
            with closing(self._connect()) as db:
                pairs=db.execute("""SELECT DISTINCT s.as_of,s.horizon FROM t1t2_snapshots s
                    JOIN t1t2_outcomes o ON o.snapshot_id=s.id ORDER BY s.as_of,s.horizon""").fetchall()
        except sqlite3.Error:
            return {"written":0,"existing":0,"skipped":0}
        result={"written":0,"existing":0,"skipped":0}
        for as_of,horizon in pairs:
            report=self.missed_moves_report(as_of,horizon)
            if report.get("status")!="OK":
                result["skipped"]+=1; continue
            date=str(as_of)[:10]; path=target/f"kacirilan_hareketler_{date}_{horizon.replace('+','plus')}.json"
            try:
                # x modu daha once uretilmis gunluk denetimi degistirmez.
                with path.open("x",encoding="utf-8") as handle:
                    json.dump({"as_of":as_of,"horizon":horizon,**report},handle,ensure_ascii=False,indent=2,default=str)
                result["written"]+=1
            except FileExistsError:
                result["existing"]+=1
            except OSError:
                result["skipped"]+=1
        return result


def settle_pending_snapshots(store: EveningSnapshotStore, history_loader,
                             evaluated_at: str | None = None) -> dict[str,int]:
    """Tamamlanan T+1/T+2 seanslarini idempotent biçimde outcomes tablosuna ekler."""
    result={"pending":0,"settled":0,"not_ready":0,"errors":0}
    for snapshot in store.pending():
        result["pending"]+=1
        try:
            history=history_loader(snapshot["symbol"])
            if isinstance(history,tuple): history=history[0]
            if history is None or history.empty:
                result["not_ready"]+=1; continue
            cutoff=pd.Timestamp(snapshot["as_of_timestamp"])
            future=history[pd.DatetimeIndex(history.index).date>cutoff.date()]
            required=1 if snapshot["horizon"]=="T+1" else 2
            if len(future)<required:
                result["not_ready"]+=1; continue
            outcome=evaluate_prediction(snapshot,future.head(required))
            ok,_error=store.attach_outcome(int(snapshot["id"]),outcome,evaluated_at or datetime.now(timezone.utc).isoformat())
            result["settled" if ok else "errors"]+=1
        except Exception:
            result["errors"]+=1
    return result


def evaluate_prediction(snapshot: Mapping[str,Any], future_bars: pd.DataFrame) -> dict[str,Any]:
    """Kayitli tahmini degistirmeden T+1/T+2 gerceklesmesini ayri hesaplar."""
    if future_bars is None or future_bars.empty or snapshot.get("current_price") in (None,0):
        return {"status":"GERCEKLESME_VERISI_YOK"}
    horizon=1 if snapshot.get("horizon")=="T+1" else 2
    bars=future_bars.sort_index().head(horizon); base=float(snapshot["current_price"])
    max_return=float(bars.High.max()/base-1); close_return=float(bars.Close.iloc[-1]/base-1)
    mae=float(bars.Low.min()/base-1); ceiling_hits=[]
    prior=base; last_ceiling=None
    for row in bars.itertuples():
        ceiling=float(pay_fiyat_limitleri(prior).ust_limit); last_ceiling=ceiling
        ceiling_hits.append(float(row.High)>=ceiling); prior=float(row.Close)
    target=snapshot.get("target",snapshot.get("target_7")); stop=snapshot.get("stop"); target_first=None
    if target and stop:
        target_first=0
        for row in bars.itertuples():
            hit_target=float(row.High)>=float(target); hit_stop=float(row.Low)<=float(stop)
            if hit_target and hit_stop: target_first=0; break
            if hit_stop: target_first=0; break
            if hit_target: target_first=1; break
    return {"status":"TAMAMLANDI","max_return_pct":max_return*100,"close_return_pct":close_return*100,
            "max_adverse_excursion_pct":mae*100,"hit_5":int(max_return>=.05),"hit_7":int(max_return>=.07),
            "hit_8":int(max_return>=.08),"hit_limit_up":int(any(ceiling_hits)),
            "closed_at_limit_up":int(bool(ceiling_hits[-1]) and last_ceiling is not None and float(bars.Close.iloc[-1])>=last_ceiling),
            "target_before_stop":target_first}
