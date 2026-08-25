import unittest
import numpy as np
import pandas as pd

from trade_kanitlari import (CostConfig, MarketRegime, Outcome, classify_market_regime,
    decision_gates, expected_value, label_trade_outcome, mfe_mae, relative_strength,
    grouped_mfe_mae_summary, ranking_score, same_time_rvol, three_way_oos_evidence, wilson_interval)
from sinyal_pipeline import daily_features, daily_raw_signal
from veri_saglayici import _normalize


class TradeEvidenceTests(unittest.TestCase):
    def test_expected_value_costs_and_probability_invariant(self):
        probabilities = {"HEDEF_ONCE": .5, "STOP_ONCE": .3, "SURE_DOLDU": .2}
        out = expected_value(probabilities, 4, 2, .5, CostConfig())
        self.assertAlmostEqual(out["brut_beklenti_pct"], 1.5)
        self.assertAlmostEqual(out["maliyetler"]["toplam_maliyet_pct"], .4)
        self.assertAlmostEqual(out["net_beklenti_pct"], 1.1)
        with self.assertRaises(ValueError):
            expected_value({"HEDEF_ONCE": .7, "STOP_ONCE": .4, "SURE_DOLDU": 0}, 4, 2, 0)

    def test_same_bar_is_stop_and_mfe_mae_excludes_signal_bar(self):
        future = pd.DataFrame({"High": [105, 103], "Low": [95, 98], "Close": [101, 100]})
        outcome, bars = label_trade_outcome(future, 104, 96)
        self.assertEqual(outcome, Outcome.STOP_ONCE)
        self.assertEqual(bars, 1)
        excursion = mfe_mae(future, 100)
        self.assertEqual(excursion, {"mfe_pct": 5.000000000000004, "mae_pct": -5.000000000000004})

    def test_three_way_oos_wilson_and_metrics(self):
        events = [Outcome.HEDEF_ONCE.value]*18+[Outcome.STOP_ONCE.value]*8+[Outcome.SURE_DOLDU.value]*4
        rows = pd.DataFrame({"olay": events, "net_getiri": [.03]*18+[-.02]*8+[.001]*4,
                             "tahmin_olasiligi": [60]*30,
                             "sinyal_zamani": pd.date_range("2026-01-01", periods=30)})
        evidence = three_way_oos_evidence(rows)
        self.assertTrue(evidence["yeterli"])
        self.assertAlmostEqual(sum(evidence["olasiliklar"].values()), 1)
        low, high = evidence["hedef_guven_araligi_pct"]
        self.assertLess(low, 60); self.assertGreater(high, 60)
        self.assertIsNotNone(evidence["brier_skoru"]); self.assertIsNotNone(evidence["log_loss"])
        self.assertFalse(three_way_oos_evidence(rows.iloc[:29])["yeterli"])

    def test_relative_strength_aligns_timestamps_and_missing_sector(self):
        index = pd.date_range("2026-01-01", periods=70)
        stock = pd.Series(np.linspace(100, 130, 70), index=index)
        benchmark = pd.Series(np.linspace(100, 110, 69), index=index[1:])
        result = relative_strength(stock, benchmark)
        self.assertEqual(result["ortak_bar"], 69)
        self.assertGreater(result["rs_bist_20"], 0)
        self.assertIsNone(result["rs_sektor_20"])

    def test_same_time_rvol_uses_only_previous_completed_days(self):
        rows = []
        for day in pd.date_range("2026-08-10", periods=6, freq="B"):
            for minute, volume in [("10:00", 100), ("10:15", 100)]:
                rows.append((pd.Timestamp(f"{day.date()} {minute}"), volume))
        for minute, volume in [("10:00", 200), ("10:15", 200)]:
            rows.append((pd.Timestamp(f"2026-08-18 {minute}"), volume))
        frame = pd.DataFrame({"Volume": [v for _, v in rows]}, index=[d for d, _ in rows])
        result = same_time_rvol(frame, min_history_days=5)
        self.assertEqual(result["gecmis_gun"], 6)
        self.assertAlmostEqual(result["rvol"], 2)

    def test_regime_and_do_not_trade_gates(self):
        falling = pd.Series(np.linspace(120, 80, 80))
        regime = classify_market_regime(falling, breadth_ratio=.2)
        self.assertEqual(regime["rejim"], MarketRegime.RISK_OFF.value)
        evidence = {"yeterli": True}
        gates = decision_gates(data_ok=True, evidence=evidence, regime=regime, liquid=True,
                               net_expectancy_pct=1, risk_reward=2, relative_strength_ok=True,
                               volume_confirmation=True)
        self.assertFalse(gates["uygun"])
        self.assertIn("rejim", gates["kalan_kapilar"])

    def test_data_quality_rejects_invalid_and_reports_duplicates(self):
        index = pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-03"])
        frame = pd.DataFrame({"Open": [10, 10, 10, 10], "High": [11, 11, 9, 11],
                              "Low": [9, 9, 9, 9], "Close": [10, 10, 10, 10],
                              "Volume": [100, 100, 100, -1]}, index=index)
        clean = _normalize(frame)
        self.assertEqual(len(clean), 1)
        report = clean.attrs["quality_report"]
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertEqual(report["invalid_ohlc_rows"], 1)
        self.assertEqual(report["invalid_volume_rows"], 1)

    def test_shared_signal_pipeline_is_deterministic(self):
        close = pd.Series(np.linspace(100, 140, 100))
        frame = pd.DataFrame({"Open": close, "High": close+1, "Low": close-1,
                              "Close": close, "Volume": 1000})
        first, second = daily_features(frame), daily_features(frame.copy())
        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_series_equal(daily_raw_signal(first), daily_raw_signal(second))

    def test_ranking_and_grouped_excursions(self):
        strong = ranking_score(net_expectancy_pct=2, probability_lower_pct=60,
                               relative_strength_pct=5, rvol=1.8, risk_reward=2.5, reliability_pct=90)
        weak = ranking_score(net_expectancy_pct=.1, probability_lower_pct=35,
                             relative_strength_pct=0, rvol=.8, risk_reward=1.8, reliability_pct=60)
        self.assertGreater(strong, weak)
        rows = pd.DataFrame({"rejim": ["TREND_UP"]*3, "mfe_pct": [1, 2, 3], "mae_pct": [-1, -2, -3]})
        summary = grouped_mfe_mae_summary(rows, ("rejim",))
        self.assertEqual(summary.iloc[0]["ornek"], 3)
        self.assertEqual(summary.iloc[0]["mfe_medyan"], 2)


if __name__ == "__main__":
    unittest.main()
