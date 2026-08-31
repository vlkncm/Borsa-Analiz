import unittest

import pandas as pd

from dashboard_ui import strongest_five_candidates


class HighMovementScoreFallbackTests(unittest.TestCase):
    def test_empty_t1_score_falls_back_to_measured_reference_score(self):
        frame = pd.DataFrame(
            {
                "Hisse": ["AAA", "BBB", "CCC"],
                "Güncel Fiyat": [10.0, 20.0, 30.0],
                "T+1 Güç Skoru": [None, None, None],
                "Referans Skor": [61.0, 82.0, 74.0],
            }
        )

        result = strongest_five_candidates(frame, limit=2)

        self.assertEqual(result["Hisse"].tolist(), ["BBB", "CCC"])
        self.assertTrue(result["Karar"].eq("TAKİP").all())

    def test_rejected_or_missing_history_rows_do_not_enter_watch_radar(self):
        frame = pd.DataFrame(
            {
                "Hisse": ["VALID", "REJECTED", "MISSING"],
                "Güncel Fiyat": [10.0, 11.0, 12.0],
                "Referans Skor": [70.0, 99.0, 98.0],
                "Neden Kodu": ["INCLUDED_STANDARD", "REJECTED_LOW_SCORE", "INSUFFICIENT_HISTORY"],
            }
        )

        result = strongest_five_candidates(frame, limit=5)

        self.assertEqual(result["Hisse"].tolist(), ["VALID"])


if __name__ == "__main__":
    unittest.main()
