import unittest
import numpy as np
import pandas as pd

from sinyal_pipeline import daily_features
from momentum_baslangici import evaluate_momentum_start


def _frame(close=None, volume=None):
    n = 120
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    close = np.asarray(close if close is not None else np.linspace(10, 12, n), dtype=float)
    volume = np.asarray(volume if volume is not None else np.full(n, 1000.), dtype=float)
    return pd.DataFrame({"Open": close-.1, "High": close+.3, "Low": close-.3,
                         "Close": close, "Volume": volume}, index=idx)


class MomentumBaslangiciTests(unittest.TestCase):
    def test_common_pipeline_exposes_completed_volume_and_indicators(self):
        result = daily_features(_frame())
        self.assertIn("RVOL_COMPLETED20", result)
        self.assertIn("MACD_HIST", result)
        self.assertIn("CLV", result)
        self.assertIn("CMF", result)

    def test_insufficient_data_is_explicit(self):
        self.assertEqual(evaluate_momentum_start(daily_features(_frame()[:40]))["momentum_setup"], "VERI_YETERSIZ")

    def test_score_is_not_probability_and_never_al(self):
        result = evaluate_momentum_start(daily_features(_frame()))
        self.assertIsInstance(result["momentum_score"], (int, float))
        self.assertGreaterEqual(result["momentum_score"], 0)
        self.assertLessEqual(result["momentum_score"], 100)
        self.assertEqual(result["decision_hint"], "BEKLE")

    def test_overextension_is_not_new_entry(self):
        close = np.r_[np.linspace(10, 11, 115), np.linspace(11, 15, 5)]
        result = evaluate_momentum_start(daily_features(_frame(close=close)))
        self.assertIn(result["momentum_setup"], {"HAREKET_ILERLEMIS", "MOMENTUM_HAZIRLIK", "MOMENTUM_YOK"})
        self.assertNotEqual(result["decision_hint"], "AL")

    def test_completed_volume_does_not_include_current_bar(self):
        volumes = np.full(120, 1000.)
        volumes[-1] = 5000.
        result = daily_features(_frame(volume=volumes))
        self.assertAlmostEqual(result["RVOL_COMPLETED20"].iloc[-1], 5.0)


if __name__ == "__main__":
    unittest.main()
