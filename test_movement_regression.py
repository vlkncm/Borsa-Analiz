"""Directional radar contracts, independent of market outcome labels."""
import dataclasses
import math

import numpy as np
import pandas as pd
import pytest

from ertesi_gun_motoru import erken_aday, t1_movement_trade_scores
from trade_adaylari import t1_listeleri
from t1t2_tahmin_sistemi import daily_ranking_metrics, point_in_time_features, predict_symbol


def evidence(**changes):
    return dict(Hisse="TEST", ret_1=.025, ret_5=.06, relative_volume=2.,
                close_location=.85, cmf20=.15, obv_slope_5=2., mfi14=65.,
                turnover20=200_000_000., relative_strength_bist_5=.06,
                relative_strength_sector_5=.03, atr_pct=.025,
                volume_acceleration_2=.4, price_acceleration_2=.005,
                breakout_return=.01, risk_reward=2., **changes)


def changed(**changes):
    row = evidence(); row.update(changes); return row


@pytest.mark.parametrize("change", [
    {"relative_strength_bist_5": -.06}, {"cmf20": -.15},
    {"obv_slope_5": -2.}, {"mfi14": 30.}, {"failed_breakout": .05},
    {"stale_sessions": 2}, {"vwap_distance": -.03}, {"vwap_slope": -.01},
    {"ret_1": -.04}, {"upper_wick": .8}, {"gap_return": .1},
    {"turnover20": 100_000}, {"risk_reward": .4},
])
def test_negative_evidence_lowers_score(change):
    assert t1_movement_trade_scores(changed(**change))[0] < t1_movement_trade_scores(evidence())[0]


def test_top10_no_saturation_and_deterministic_ranking():
    rows = [changed(Hisse=f"S{i:02}", ret_5=.02+i*.006,
                    relative_strength_bist_5=.015+i*.005) for i in range(40)]
    frame = pd.DataFrame(rows)
    a = t1_listeleri(frame)["radar"]
    b = t1_listeleri(frame.sample(frac=1, random_state=8))["radar"]
    assert list(a.Hisse) == list(b.Hisse)
    assert a["Movement Score"].nunique() == 10
    assert (a["Movement Score"].round(1) < 100).all()
    tied = pd.DataFrame([changed(Hisse=s) for s in ("Z", "A", "B")])
    assert list(t1_listeleri(tied)["radar"].Hisse) == ["A", "B", "Z"]


def test_missing_and_nonfinite_are_not_positive_defaults():
    missing = changed(cmf20=np.nan, relative_strength_bist_5=np.inf)
    result = t1_movement_trade_scores(missing)
    assert math.isfinite(result[0]) and result[0] < t1_movement_trade_scores(evidence())[0]
    assert t1_movement_trade_scores({"cmf20": np.nan})[0] < 50


def test_unconfirmed_price_cannot_be_elite_or_high_confidence():
    row = changed(live_confirmed=True, **{"Karar": "GÜNCEL FİYATLA DOĞRULA",
                  "T+1 Seviye Doğrulandı": True, "Günlük Değişim %": 2.5})
    groups = t1_listeleri(pd.DataFrame([row]))
    assert groups["elite"].empty
    assert groups["radar"].iloc[0]["Güven"] == "DÜŞÜK"
    assert groups["wide"].iloc[0]["Movement Score"] > groups["wide"].iloc[0]["Confidence"]


def test_bearish_market_allows_positive_divergence():
    strong = changed(Hisse="STRONG", benchmark_ret_5=-.05)
    weak = changed(Hisse="WEAK", benchmark_ret_5=-.05, relative_strength_bist_5=-.04, ret_5=-.09, ret_1=-.02)
    groups = t1_listeleri(pd.DataFrame([weak, strong]))
    assert groups["radar"].iloc[0].Hisse == "STRONG"
    assert groups["wide"].iloc[0]["Movement Score"] > 62
    assert t1_movement_trade_scores(weak)[0] < 62


def test_future_close_never_enters_prediction():
    from test_ertesi_gun_sistemi import sample_frame
    frame = sample_frame(); cutoff = frame.index[-3]
    modified = frame.copy(); modified.loc[modified.index > cutoff, "Close"] *= 10
    for source in (frame, modified):
        assert point_in_time_features(source, cutoff) == point_in_time_features(frame, cutoff)
        row = erken_aday("X", source, "YATAY", as_of=cutoff)
        assert row["Movement Score"] == erken_aday("X", frame.loc[:cutoff], "YATAY")["Movement Score"]
    assert predict_symbol("X", frame, cutoff, "T+1").feature_hash == predict_symbol("X", modified, cutoff, "T+1").feature_hash


def test_zero_positive_days_are_included_and_fpr_uses_all_negatives():
    rows = pd.DataFrame({"day": [1]*20+[2]*20, "score": list(range(20))*2,
                         "label": [0]*19+[1]+[0]*20})
    result = daily_ranking_metrics(rows, "day", "score", "label")
    assert result["precision_at_10"] == .05
    assert result["false_positive_rate_at_10"] == pytest.approx((9/19+10/20)/2)


def test_artifact_from_future_cannot_predict_past():
    from test_ertesi_gun_sistemi import sample_frame
    from t1t2_tahmin_sistemi import ModelArtifact
    frame = sample_frame()
    artifact = ModelArtifact("T+1", "max_7", ("ret_5",), (1.,), 0.,
                             "sigmoid", 1., 0., 300, "2026-01-01", "2026-08-25", .1)
    prediction = predict_symbol("X", frame, frame.index[-1], "T+1", {"T+1:max_7": artifact})
    assert prediction.probabilities["max_7"] is None
