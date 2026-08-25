"""v10.2 işlem ekonomisi, OOS kanıtı ve zorunlu karar kapıları.

Fonksiyonlar ağ erişmez; canlı tarama ve backtest aynı saf hesapları çağırır.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd


class Outcome(str, Enum):
    HEDEF_ONCE = "HEDEF_ONCE"
    STOP_ONCE = "STOP_ONCE"
    SURE_DOLDU = "SURE_DOLDU"


class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RISK_OFF = "RISK_OFF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CostConfig:
    commission_bps_per_side: float = 10.0
    spread_bps_round_trip: float = 10.0
    slippage_bps_per_side: float = 5.0
    taxes_bps_round_trip: float = 0.0

    def components_pct(self) -> dict[str, float]:
        result = {
            "komisyon_pct": 2*self.commission_bps_per_side/100,
            "spread_pct": self.spread_bps_round_trip/100,
            "kayma_pct": 2*self.slippage_bps_per_side/100,
            "vergi_masraf_pct": self.taxes_bps_round_trip/100,
        }
        result["toplam_maliyet_pct"] = sum(result.values())
        return result


@dataclass(frozen=True)
class RankingConfig:
    net_expectancy: float = .30
    probability_lower_bound: float = .20
    relative_strength: float = .15
    rvol_vwap: float = .10
    risk_reward: float = .15
    reliability: float = .10


def ranking_score(*, net_expectancy_pct: float, probability_lower_pct: float,
                  relative_strength_pct: float, rvol: float, risk_reward: float,
                  reliability_pct: float, config: RankingConfig | None = None) -> float:
    cfg = config or RankingConfig()
    # Yalnız kapıları geçen adaylar arasında karşılaştırma; bileşenler aşırı uçlara karşı sınırlıdır.
    components = {
        "net_expectancy": min(max(net_expectancy_pct/5, 0), 1),
        "probability_lower_bound": min(max(probability_lower_pct/100, 0), 1),
        "relative_strength": min(max((relative_strength_pct+10)/20, 0), 1),
        "rvol_vwap": min(max(rvol/2, 0), 1),
        "risk_reward": min(max(risk_reward/3, 0), 1),
        "reliability": min(max(reliability_pct/100, 0), 1),
    }
    return 100*sum(components[name]*getattr(cfg, name) for name in components)


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if total <= 0 or successes < 0 or successes > total:
        return None, None
    p = successes/total
    denominator = 1+z*z/total
    centre = (p+z*z/(2*total))/denominator
    margin = z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/denominator
    return max(0.0, centre-margin), min(1.0, centre+margin)


def label_trade_outcome(bars: pd.DataFrame, target: float, stop: float) -> tuple[Outcome, int]:
    """Girişten sonraki gerçekleşebilir barlarda ilk dokunuşu etiketler; belirsizde stop önce."""
    if bars is None or bars.empty:
        return Outcome.SURE_DOLDU, 0
    for offset, row in enumerate(bars.itertuples(), start=1):
        hit_target = float(row.High) >= float(target)
        hit_stop = float(row.Low) <= float(stop)
        if hit_stop:  # aynı barda ikisi de varsa kötümser öncelik
            return Outcome.STOP_ONCE, offset
        if hit_target:
            return Outcome.HEDEF_ONCE, offset
    return Outcome.SURE_DOLDU, len(bars)


def mfe_mae(bars_after_entry: pd.DataFrame, entry: float) -> dict[str, float | None]:
    if bars_after_entry is None or bars_after_entry.empty or not math.isfinite(float(entry)) or entry <= 0:
        return {"mfe_pct": None, "mae_pct": None}
    highs = pd.to_numeric(bars_after_entry["High"], errors="coerce")
    lows = pd.to_numeric(bars_after_entry["Low"], errors="coerce")
    return {"mfe_pct": float((highs.max()/entry-1)*100), "mae_pct": float((lows.min()/entry-1)*100)}


def expected_value(probabilities: Mapping[str, float], target_return_pct: float,
                   stop_loss_pct: float, timeout_median_return_pct: float,
                   costs: CostConfig | None = None) -> dict[str, Any]:
    keys = (Outcome.HEDEF_ONCE.value, Outcome.STOP_ONCE.value, Outcome.SURE_DOLDU.value)
    values = {key: float(probabilities.get(key, 0.0)) for key in keys}
    total = sum(values.values())
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise ValueError("p_hedef + p_stop + p_sure_doldu 1 olmalıdır")
    gross = (values[keys[0]]*float(target_return_pct)
             - values[keys[1]]*abs(float(stop_loss_pct))
             + values[keys[2]]*float(timeout_median_return_pct))
    components = (costs or CostConfig()).components_pct()
    return {"brut_beklenti_pct": gross, "net_beklenti_pct": gross-components["toplam_maliyet_pct"],
            "olasiliklar": values, "maliyetler": components}


def three_way_oos_evidence(outcomes: Any, min_samples: int = 30) -> dict[str, Any]:
    rows = pd.DataFrame(outcomes).copy()
    required = {"olay", "net_getiri"}
    if rows.empty or not required.issubset(rows.columns):
        return _insufficient(0)
    rows = rows.dropna(subset=list(required))
    rows = rows[rows["olay"].isin([item.value for item in Outcome])]
    n = len(rows)
    if n < min_samples:
        return _insufficient(n)
    counts = rows["olay"].value_counts()
    probabilities = {item.value: int(counts.get(item.value, 0))/n for item in Outcome}
    intervals = {item.value: wilson_interval(int(counts.get(item.value, 0)), n) for item in Outcome}
    timeout = pd.to_numeric(rows.loc[rows["olay"].eq(Outcome.SURE_DOLDU.value), "net_getiri"], errors="coerce").dropna()
    returns = pd.to_numeric(rows["net_getiri"], errors="coerce").dropna()
    date_source = rows["sinyal_zamani"] if "sinyal_zamani" in rows else pd.Series(index=rows.index, dtype="datetime64[ns]")
    prediction_source = rows["tahmin_olasiligi"] if "tahmin_olasiligi" in rows else pd.Series(index=rows.index, dtype=float)
    date_values = pd.to_datetime(date_source, errors="coerce").dropna()
    predicted = pd.to_numeric(prediction_source, errors="coerce")/100
    actual = rows["olay"].eq(Outcome.HEDEF_ONCE.value).astype(float)
    valid = predicted.notna()
    brier = float(((predicted[valid]-actual[valid])**2).mean()) if valid.any() else None
    clipped = predicted[valid].clip(1e-12, 1-1e-12)
    log_loss = float(-(actual[valid]*np.log(clipped)+(1-actual[valid])*np.log(1-clipped)).mean()) if valid.any() else None
    return {
        "n": n, "yeterli": True, "olasiliklar": probabilities, "guven_araliklari": intervals,
        "hedef_olasiligi_pct": probabilities[Outcome.HEDEF_ONCE.value]*100,
        "hedef_guven_araligi_pct": tuple(value*100 for value in intervals[Outcome.HEDEF_ONCE.value]),
        "sure_doldu_medyan_getiri_pct": float(timeout.median()*100) if not timeout.empty else 0.0,
        "medyan_net_getiri_pct": float(returns.median()*100), "brier_skoru": brier, "log_loss": log_loss,
        "baslangic": date_values.min().isoformat() if not date_values.empty else None,
        "bitis": date_values.max().isoformat() if not date_values.empty else None,
        "kalibrasyon": "Zaman sıralı out-of-sample; Wilson %95 güven aralığı",
    }


def _insufficient(n: int) -> dict[str, Any]:
    return {"n": n, "yeterli": False, "olasiliklar": None, "guven_araliklari": None,
            "hedef_olasiligi_pct": None, "hedef_guven_araligi_pct": None,
            "sure_doldu_medyan_getiri_pct": None, "medyan_net_getiri_pct": None,
            "brier_skoru": None, "log_loss": None, "baslangic": None, "bitis": None,
            "kalibrasyon": "Yetersiz örnek"}


def relative_strength(stock_close: pd.Series, benchmark_close: pd.Series,
                      sector_close: pd.Series | None = None, periods: tuple[int, ...] = (5, 20, 60)) -> dict[str, Any]:
    stock, benchmark = pd.to_numeric(stock_close, errors="coerce"), pd.to_numeric(benchmark_close, errors="coerce")
    aligned = pd.concat({"stock": stock, "benchmark": benchmark}, axis=1, join="inner").dropna()
    result: dict[str, Any] = {"sektor_verisi_var": sector_close is not None, "ortak_bar": len(aligned)}
    for period in periods:
        if len(aligned) <= period:
            result[f"rs_bist_{period}"] = None
        else:
            result[f"rs_bist_{period}"] = float((aligned.stock.pct_change(period, fill_method=None).iloc[-1]-aligned.benchmark.pct_change(period, fill_method=None).iloc[-1])*100)
    if sector_close is None:
        result.update({f"rs_sektor_{period}": None for period in periods})
        result["uyari"] = "Sektör verisi yok"
        return result
    sector_aligned = pd.concat({"stock": stock, "sector": pd.to_numeric(sector_close, errors="coerce")}, axis=1, join="inner").dropna()
    for period in periods:
        result[f"rs_sektor_{period}"] = (float((sector_aligned.stock.pct_change(period, fill_method=None).iloc[-1]-sector_aligned.sector.pct_change(period, fill_method=None).iloc[-1])*100) if len(sector_aligned) > period else None)
    result["uyari"] = ""
    return result


def same_time_rvol(intraday: pd.DataFrame, min_history_days: int = 5, lookback_days: int = 20) -> dict[str, Any]:
    if intraday is None or intraday.empty or not isinstance(intraday.index, pd.DatetimeIndex):
        return {"rvol": None, "durum": "RVOL kullanılamıyor", "gecmis_gun": 0}
    work = intraday.sort_index().copy()
    volume = pd.to_numeric(work["Volume"], errors="coerce")
    if (volume < 0).any() or volume.notna().sum() == 0:
        return {"rvol": None, "durum": "RVOL kullanılamıyor", "gecmis_gun": 0}
    local = work.index.tz_localize("Europe/Istanbul") if work.index.tz is None else work.index.tz_convert("Europe/Istanbul")
    dates, minutes = pd.Series(local.date, index=work.index), pd.Series(local.hour*60+local.minute, index=work.index)
    cumulative = volume.fillna(0).groupby(dates).cumsum()
    current_date, current_minute = dates.iloc[-1], minutes.iloc[-1]
    previous_dates = list(pd.unique(dates[dates < current_date]))[-lookback_days:]
    historical = []
    for day in previous_dates:
        mask = (dates == day) & (minutes <= current_minute)
        if mask.any():
            historical.append(float(cumulative[mask].iloc[-1]))
    if len(historical) < min_history_days or np.median(historical) <= 0:
        return {"rvol": None, "durum": "RVOL için yetersiz tamamlanmış gün", "gecmis_gun": len(historical)}
    value = float(cumulative.iloc[-1]/np.median(historical))
    label = "zayıf" if value < .8 else ("normal" if value <= 1.2 else ("güçlü" if value <= 2 else "olağan dışı; haber/KAP kontrolü"))
    return {"rvol": value, "durum": label, "gecmis_gun": len(historical)}


def classify_market_regime(index_close: pd.Series | None, breadth_ratio: float | None = None,
                           sector_outperformance_ratio: float | None = None,
                           data_fresh: bool = True) -> dict[str, Any]:
    if not data_fresh or index_close is None:
        return {"rejim": MarketRegime.UNKNOWN.value, "islem_uygun": False, "nedenler": ["Piyasa verisi eksik/eski"]}
    close = pd.to_numeric(index_close, errors="coerce").dropna()
    if len(close) < 60:
        return {"rejim": MarketRegime.UNKNOWN.value, "islem_uygun": False, "nedenler": ["Piyasa warm-up yetersiz"]}
    ret = close.pct_change(fill_method=None).dropna()
    volatility = ret.rolling(20).std(ddof=0)*math.sqrt(252)
    history = volatility.dropna()
    # Eşit volatilite gözlemleri en yüksek yüzdelik sayılmaz; sıra bağlarında orta sıra kullanılır.
    percentile = float(((history < history.iloc[-1]).sum()+.5*(history == history.iloc[-1]).sum())/len(history)) if not history.empty else 1.0
    trend20, trend60 = close.iloc[-1]/close.iloc[-21]-1, close.iloc[-1]/close.iloc[-61]-1
    reasons = [f"XU100 20/60 getiri %{trend20*100:.2f}/%{trend60*100:.2f}", f"Volatilite yüzdeliği %{percentile*100:.1f}"]
    if trend20 < -.03 and trend60 < 0 and (breadth_ratio is None or breadth_ratio < .45):
        regime = MarketRegime.RISK_OFF
    elif percentile >= .9:
        regime = MarketRegime.HIGH_VOLATILITY
    elif trend20 > 0 and trend60 > 0 and (breadth_ratio is None or breadth_ratio >= .5) and (sector_outperformance_ratio is None or sector_outperformance_ratio >= .4):
        regime = MarketRegime.TREND_UP
    else:
        regime = MarketRegime.RANGE
    return {"rejim": regime.value, "islem_uygun": regime in {MarketRegime.TREND_UP, MarketRegime.RANGE},
            "volatilite_yuzdeligi": percentile*100, "nedenler": reasons}


def decision_gates(*, data_ok: bool, evidence: Mapping[str, Any], regime: Mapping[str, Any],
                   liquid: bool, net_expectancy_pct: float | None, risk_reward: float,
                   relative_strength_ok: bool, volume_confirmation: bool,
                   min_risk_reward: float = 1.8) -> dict[str, Any]:
    gates = {
        "veri": bool(data_ok), "oos_ornek": bool(evidence.get("yeterli")),
        "rejim": bool(regime.get("islem_uygun")), "likidite_maliyet": bool(liquid),
        "net_beklenti": net_expectancy_pct is not None and net_expectancy_pct > 0,
        "risk_getiri": math.isfinite(float(risk_reward)) and risk_reward >= min_risk_reward,
        "goreceli_guc": bool(relative_strength_ok), "hacim_vwap": bool(volume_confirmation),
    }
    failed = [name for name, passed in gates.items() if not passed]
    return {"uygun": not failed, "kapilar": gates, "kalan_kapilar": failed,
            "aciklama": "Tüm zorunlu kapılar geçti" if not failed else "Geçmeyen kapılar: "+", ".join(failed)}


def mfe_mae_summary(outcomes: Any) -> dict[str, Any]:
    rows = pd.DataFrame(outcomes)
    result: dict[str, Any] = {}
    for column in ("mfe_pct", "mae_pct"):
        source = rows[column] if column in rows else pd.Series(dtype=float)
        values = pd.to_numeric(source, errors="coerce").dropna()
        result[column] = None if values.empty else {"p25": float(values.quantile(.25)), "medyan": float(values.median()), "p70": float(values.quantile(.70)), "p75": float(values.quantile(.75))}
    return result


def grouped_mfe_mae_summary(outcomes: Any, group_columns: tuple[str, ...] = ("rejim", "likidite_sinifi", "strateji_surumu")) -> pd.DataFrame:
    rows = pd.DataFrame(outcomes)
    available = [column for column in group_columns if column in rows]
    columns = available+["ornek", "mfe_p25", "mfe_medyan", "mfe_p70", "mfe_p75", "mae_p25", "mae_medyan", "mae_p70", "mae_p75"]
    if rows.empty or not available or not {"mfe_pct", "mae_pct"}.issubset(rows.columns):
        return pd.DataFrame(columns=columns)
    records = []
    grouper = available[0] if len(available) == 1 else available
    for key, group in rows.groupby(grouper, dropna=False):
        key = (key,) if len(available) == 1 else key
        record = dict(zip(available, key)); record["ornek"] = len(group)
        for prefix in ("mfe", "mae"):
            values = pd.to_numeric(group[f"{prefix}_pct"], errors="coerce").dropna()
            for label, quantile in (("p25", .25), ("medyan", .5), ("p70", .7), ("p75", .75)):
                record[f"{prefix}_{label}"] = None if values.empty else float(values.quantile(quantile))
        records.append(record)
    return pd.DataFrame(records, columns=columns)
