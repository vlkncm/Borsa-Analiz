import os
import unittest
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_qt import MainWindow, tavan_potansiyeli_gorunumu
from tarama_evreni import ALL_BIST, BIST30_ONLY, SCAN_UNIVERSE, report_cache_key


class MerkeziTaramaMimarisiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_10x_page_navigation_and_function_are_removed(self):
        self.assertFalse(hasattr(self.window, "ten_x"))
        menu_texts = [button.text() for button in self.window.sidebar._buttons.values()]
        self.assertFalse(any("10X" in text.upper() for text in menu_texts))

    def test_main_button_registers_exactly_five_stock_analyses(self):
        self.assertEqual(self.window.home.trade_button.text(), "Tüm Hisse Analizlerini Başlat")
        with patch.object(self.window, "scan") as scan:
            self.window.start_all_stock_analyses()
        self.assertEqual(set(self.window._central_requests), set(SCAN_UNIVERSE))
        self.assertEqual(len(self.window._central_requests), 5)
        self.assertNotIn("funds", self.window._central_requests)
        scan.assert_called_once_with()

    def test_general_completion_starts_daily_and_under50_not_funds(self):
        with patch.object(self.window, "scan"):
            self.window.start_all_stock_analyses()
        with patch.object(self.window.daily_trade, "start_scan") as daily, patch.object(
            self.window.under_50, "start_scan"
        ) as under, patch.object(self.window.funds, "run") as funds:
            self.window._central_after_general(True)
        daily.assert_called_once_with(**self.window._central_requests["daily_trade"])
        under.assert_called_once_with(**self.window._central_requests["under_50_tl"])
        funds.assert_not_called()

    def test_fund_button_only_starts_fund_analysis(self):
        self.assertEqual(self.window.funds.button.text(), "Fon Analizini Başlat")
        with patch.object(self.window.funds, "run") as fund_run, patch.object(
            self.window, "start_all_stock_analyses"
        ) as stock_run:
            self.window.funds.button.click()
        fund_run.assert_called_once_with()
        stock_run.assert_not_called()

    def test_strategy_universe_contract(self):
        self.assertEqual(SCAN_UNIVERSE["short_term"], BIST30_ONLY)
        self.assertEqual(SCAN_UNIVERSE["medium_term"], BIST30_ONLY)
        for strategy in ("daily_trade", "under_50_tl", "ceiling_potential"):
            self.assertEqual(SCAN_UNIVERSE[strategy], ALL_BIST)

    def test_ceiling_view_uses_potential_language_and_keeps_outside_bist30(self):
        source = pd.DataFrame({
            "Hisse": ["MEGMT.IS"], "Fiyat": [24.0], "2-6 Hafta Potansiyel Skor": [82],
            "20 Gün %20+ Olasılık": [41], "Hedef 1 Potansiyel %": [12],
            "Hedef 2 Potansiyel %": [24], "Alış Alt": [23], "Hedef 1": [27], "Stop Loss": [21],
        })
        result = tavan_potansiyeli_gorunumu(source)
        self.assertEqual(result.iloc[0]["Hisse"], "MEGMT.IS")
        self.assertIn("Potansiyel Puanı", result.columns)
        self.assertIn("Yükseliş Olasılığı", result.columns)
        self.assertNotIn("garanti", " ".join(map(str, result.iloc[0])).casefold())

    def test_late_or_wrong_universe_worker_is_ignored_by_coordinator(self):
        with patch.object(self.window, "scan"):
            self.window.start_all_stock_analyses()
        before = set(self.window._central_pending)
        self.window._central_worker_completed({
            "request_id": "old", "strategy_id": "daily_trade", "universe_id": BIST30_ONLY,
            "ok": True, "candidates": 99,
        })
        self.assertEqual(self.window._central_pending, before)

    def test_one_worker_failure_does_not_discard_successful_results(self):
        with patch.object(self.window, "scan"):
            self.window.start_all_stock_analyses()
        self.window._central_pending = {"daily_trade", "under_50_tl"}
        daily = self.window._central_requests["daily_trade"]
        under = self.window._central_requests["under_50_tl"]
        self.window._central_worker_completed({**daily, "ok": False, "candidates": 0, "errors": 1})
        self.assertTrue(self.window._central_scan_active)
        self.window._central_worker_completed({**under, "ok": True, "candidates": 2, "errors": 0})
        self.assertFalse(self.window._central_scan_active)
        self.assertEqual(self.window._central_results["under_50_tl"]["candidates"], 2)

    def test_cache_keys_separate_all_five_strategies(self):
        keys = {report_cache_key(strategy, universe, "2026-08-26") for strategy, universe in SCAN_UNIVERSE.items()}
        self.assertEqual(len(keys), 5)


if __name__ == "__main__":
    unittest.main()
