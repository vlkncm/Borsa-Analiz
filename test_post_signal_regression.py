"""Post-signal labels and entry gates; future bars never enter scoring."""
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from ertesi_gun_motoru import t1_movement_trade_scores
from post_signal_performance import RadarSignalStore, evaluate_intraday_signal
from trade_adaylari import intraday_entry_evidence, t1_listeleri


def signal_bars():
    idx = pd.date_range("2026-09-16 10:00", periods=34, freq="15min", tz="Europe/Istanbul")
    bars = pd.DataFrame({"Open": 100., "High": 101., "Low": 99.,
                         "Close": 100., "Volume": 1000.}, index=idx)
    bars.loc[idx[4], ["Open", "High", "Low", "Close"]] = [108, 110, 104, 105]
    bars.loc[idx[5], ["Open", "High", "Low", "Close"]] = [105, 106, 98, 99]
    bars.loc[idx[6]:, ["Open", "High", "Low", "Close"]] = [99, 100, 94, 95]
    return bars


def test_post_signal_return_uses_signal_price_and_pre_signal_gain_not_counted_as_success():
    bars = signal_bars()
    signal = {"signal_timestamp": "2026-09-16T11:15:00+03:00", "signal_price": 105.}
    result = evaluate_intraday_signal(signal, bars)
    assert result["Return_30m"] == pytest.approx((95/105-1)*100)
    assert result["Return_Close"] < 0
    assert result["MFE"] < 3
    assert result["hit_3"] == result["hit_5"] == result["hit_7"] == 0


def test_no_lookahead_and_partial_horizons_stay_unknown():
    bars = signal_bars().iloc[:6]
    result = evaluate_intraday_signal(
        {"signal_timestamp": "2026-09-16T11:15:00+03:00", "signal_price": 105.}, bars)
    assert result["status"] == "PARTIAL"
    assert result["Return_120m"] is None
    assert result["Return_Close"] is None
    assert evaluate_intraday_signal({"signal_price": 105}, bars)["status"] == "SIGNAL_PRICE_MISSING"


@pytest.mark.parametrize("change", [
    {"intraday_return": .12, "distance_intraday_high": .04},
    {"vwap_distance": .09}, {"failed_breakout": .05},
    {"cmf20": -.2}, {"relative_strength_bist_5": -.05},
])
def test_entry_penalties(change):
    base = {"ret_1": .03, "ret_5": .05, "relative_volume": 2.,
            "close_location": .8, "cmf20": .15, "obv_slope_5": 2.,
            "turnover20": 200_000_000, "relative_strength_bist_5": .05,
            "risk_reward": 2., "vwap_distance": .01}
    assert t1_movement_trade_scores({**base, **change})[0] < t1_movement_trade_scores(base)[0]


def test_stale_price_not_verified_and_unknown_regime_fallback_safe():
    bars = signal_bars().iloc[:5]
    meta = SimpleNamespace(is_stale=True, is_delayed=False,
                           fetched_at=datetime.fromisoformat("2026-09-16T11:15:00+03:00"))
    assert intraday_entry_evidence(bars, meta)["live_confirmed"] is False
    meta.is_stale = False
    meta.is_delayed = True
    assert intraday_entry_evidence(bars, meta)["live_confirmed"] is False
    meta.is_delayed = False
    meta.fetched_at = datetime.fromisoformat("2026-09-16T13:00:00+03:00")
    assert intraday_entry_evidence(bars, meta)["live_confirmed"] is False
    from trade_kanitlari import classify_market_regime
    assert classify_market_regime(None)["rejim"] == "UNKNOWN"


def test_elite_list_not_forced_to_10_and_low_confidence_requires_stronger_evidence():
    rows = pd.DataFrame([{"Hisse": f"S{i}", "ret_1": .03, "ret_5": .05,
                          "relative_volume": 2., "close_location": .8,
                          "cmf20": .15, "obv_slope_5": 2., "turnover20": 200_000_000,
                          "relative_strength_bist_5": .05, "risk_reward": 2.,
                          "Menkul Türü": "NORMAL_PAY", "T+1 Seviye Doğrulandı": True,
                          "Günlük Değişim %": 3., "live_confirmed": False}
                         for i in range(12)])
    assert t1_listeleri(rows)["radar"].empty
    assert len(t1_listeleri(rows)["wide"]) == 12


def test_snapshot_is_immutable_and_outcome_is_separate(tmp_path):
    store = RadarSignalStore(tmp_path / "signals.sqlite3")
    signal = {"signal_timestamp": "2026-09-16T11:15:00+03:00", "symbol": "TDGYO",
              "signal_price": 105., "movement_score": 87., "confidence": 70.,
              "market_regime": "RANGE", "rank": 1}
    assert store.save(signal)
    assert not store.save({**signal, "signal_price": 100.})
    assert store.pending()[0]["signal_price"] == 105.
    assert not store.attach_outcome(store.pending()[0]["id"], {"status": "PARTIAL"}, "later")
    assert store.attach_outcome(store.pending()[0]["id"],
        {"status": "COMPLETE", "MFE": 0., "MAE": -2., "Return_Close": -1.,
         "hit_3": 0, "hit_5": 0, "hit_7": 0}, "later")
    assert not store.pending()
    summary = store.performance_summary()
    assert summary["Precision@3"] == 0
    assert summary["Average Post-Signal Return"] == -1
    assert summary["False Positive Rate"] is None


def test_t1_outcome_uses_issued_price_and_excludes_signal_day():
    from t1t2_tahmin_sistemi import evaluate_prediction
    bars = pd.DataFrame({"Open": [110., 111.], "High": [115., 116.],
                         "Low": [100., 105.], "Close": [112., 114.]},
                        index=pd.date_range("2026-09-16", periods=2, freq="D",
                                            tz="Europe/Istanbul"))
    signal = {"horizon": "T+1", "current_price": 100., "signal_price": 120.,
              "signal_timestamp": "2026-09-16T11:00:00+03:00"}
    result = evaluate_prediction(signal, bars)
    assert result["max_return_pct"] == pytest.approx((116/120-1)*100)
    assert result["hit_7"] == 0
    assert evaluate_prediction({**signal, "signal_price": None}, bars)["status"] == "SIGNAL_PRICE_MISSING"
