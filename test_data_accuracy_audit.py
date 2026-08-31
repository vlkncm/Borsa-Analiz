import unittest

import numpy as np
import pandas as pd

from data_accuracy_audit import AUDIT_COLUMNS, independent_features
from sinyal_pipeline import daily_features


class DataAccuracyAuditTests(unittest.TestCase):
    def test_independent_reference_matches_canonical_indicators(self):
        rng = np.random.default_rng(20260831)
        close = 50 + np.cumsum(rng.normal(0.08, 0.7, 320))
        frame = pd.DataFrame({
            "Open": close + rng.normal(0, 0.2, 320),
            "High": close + rng.uniform(0.2, 1.2, 320),
            "Low": close - rng.uniform(0.2, 1.2, 320),
            "Close": close,
            "Volume": rng.integers(100_000, 2_000_000, 320),
        }, index=pd.date_range("2025-01-01", periods=320, freq="B"))
        reference = independent_features(frame).iloc[-1]
        motor = daily_features(frame).iloc[-1]
        for column in AUDIT_COLUMNS:
            self.assertAlmostEqual(float(reference[column]), float(motor[column]), places=9, msg=column)


if __name__ == "__main__":
    unittest.main()
