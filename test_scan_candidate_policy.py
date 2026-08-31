import unittest

import pandas as pd
import numpy as np

from scan_candidate_policy import (
    ScanDiagnostics,
    normalize_data_status,
    normalize_professional_class,
    safe_trade_plan,
)
from sade_karar_modeli import sade_firsatlar
from sinyal_pipeline import daily_features


class ScanCandidatePolicyTests(unittest.TestCase):
    def _frame(self, **overrides):
        row = {
            "Hisse": "TEST.IS", "Fiyat": 100.0,
            "Önerilen Alış Alt": 99.0, "Önerilen Alış Üst": 101.0,
            "Önerilen Satış": 115.0, "Önerilen Stop": 92.0,
            "v4 Güven Puanı": 72.0, "Veri Durumu": "Güvenilir ",
            "Profesyonel Karar": " uygun aday ", "ATR": 4.0,
            "Veri Tarihi": "2026-08-31",
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_professional_class_normalization(self):
        self.assertEqual(normalize_professional_class(" uygun aday "), "SUITABLE")
        self.assertEqual(normalize_professional_class("Teyit Bekliyor"), "WAIT_CONFIRMATION")
        self.assertEqual(normalize_professional_class("İZLE"), "WATCH")

    def test_data_status_normalization(self):
        self.assertEqual(normalize_data_status(" Güvenilir "), "RELIABLE")
        self.assertEqual(normalize_data_status("gecikmeli"), "PARTIAL")
        self.assertEqual(normalize_data_status("ESKİ VERİ - KARAR YOK"), "STALE")

    def test_scan_does_not_go_empty_due_to_one_optional_field(self):
        result = sade_firsatlar(self._frame(**{"Profesyonel Karar": None}), "kisa")
        self.assertEqual(len(result), 1)

    def test_strong_candidates(self):
        result = sade_firsatlar(self._frame(), "kisa")
        self.assertEqual(result.iloc[0]["Karar"], "AL")
        self.assertEqual(result.iloc[0]["Aday Seviyesi"], "A")

    def test_watch_fallback(self):
        frame = self._frame(**{"v4 Güven Puanı": 49, "Önerilen Satış": 108, "Önerilen Stop": 94})
        result = sade_firsatlar(frame, "kisa")
        self.assertEqual(result.iloc[0]["Karar"], "TAKİP")
        self.assertEqual(result.iloc[0]["Aday Seviyesi"], "C")

    def test_invalid_data_not_recommended(self):
        result = sade_firsatlar(self._frame(Fiyat=0, **{"Veri Durumu": "bozuk"}), "kisa")
        self.assertTrue(result.empty)

    def test_target_stop_fallback(self):
        frame = self._frame(**{"Önerilen Satış": None, "Önerilen Stop": None, "Direnç": 114, "Destek": 94})
        result = sade_firsatlar(frame, "kisa")
        self.assertEqual(len(result), 1)
        self.assertIn("fallback", result.iloc[0]["Plan Kaynağı"].lower())

    def test_scan_diagnostics_counts(self):
        diagnostics = ScanDiagnostics(strategy="short_term", symbols_total=3)
        diagnostics.data_ok = 2
        diagnostics.errors = 1
        diagnostics.strong_candidates = 1
        diagnostics.watch_candidates = 1
        self.assertTrue(diagnostics.is_consistent())
        self.assertEqual(diagnostics.to_dict()["symbols_total"], 3)

    def test_symbol_independence(self):
        first = safe_trade_plan(100, None, None, 4, 94, 114, "short_term")
        second = safe_trade_plan(50, None, None, 1, 48, 55, "short_term")
        self.assertIsNot(first, second)
        self.assertNotEqual(first.target, second.target)
        self.assertNotEqual(first.stop, second.stop)

    def test_flat_price_bar_does_not_crash_feature_pipeline(self):
        close = pd.Series(np.linspace(10, 20, 220))
        frame = pd.DataFrame({"Open": close, "High": close, "Low": close,
                              "Close": close, "Volume": 1_000_000})
        result = daily_features(frame)
        self.assertEqual(len(result), 220)
        self.assertIn("CLV", result)


if __name__ == "__main__":
    unittest.main()
