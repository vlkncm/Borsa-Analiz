import os
import unittest

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_qt import MainWindow, Under50Page
from sade_karar_modeli import elli_tl_adaylari


def under_50_result(symbol="UCUZ", price=25.0):
    return pd.DataFrame({
        "Hisse": [symbol], "Durum": ["TEYİT BEKLE"], "Mevcut Fiyat": [price],
        "Alım Bölgesi": ["24.50 – 25.25 TL"], "Hedef": [28.0], "Stop": [23.0],
        "Potansiyel %": [12.0], "Skor": [75], "Risk/Getiri": [1.5],
    })


class PageScanIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_under_50_model_only_returns_prices_at_or_below_50(self):
        frame = pd.DataFrame({
            "Hisse": ["LOW.IS", "HIGH.IS"], "Fiyat": [25.0, 75.0],
            "Ortalama Günlük İşlem Tutarı": [10_000_000, 10_000_000],
            "EMA20": [24.0, 70.0], "EMA50": [23.0, 65.0], "EMA200": [20.0, 60.0],
            "RSI": [55.0, 55.0], "MACD": [2.0, 2.0], "MACD Signal": [1.0, 1.0],
            "Hacim Oranı": [1.3, 1.3], "Son 20 Gün %": [5.0, 5.0], "Son 60 Gün %": [10.0, 10.0],
            "Önerilen Stop": [23.0, 70.0], "Önerilen Satış": [30.0, 85.0],
        })
        result = elli_tl_adaylari(frame)
        self.assertFalse(result.empty)
        self.assertTrue(pd.to_numeric(result["Mevcut Fiyat"]).between(1, 50).all())

    def test_under50_short_under50_navigation_preserves_first_result(self):
        page = self.window.under_50
        request_id = page.begin_request("under-first")
        page._scan_identity = {"request_id": request_id, "strategy_id": "under_50_tl", "universe_id": "all_bist"}
        page.done(request_id, page.page_id, "under_50_tl", "all_bist", True, under_50_result(), "tamam")
        expected = page._data.copy(deep=True)
        self.window.pages.setCurrentWidget(page)
        self.window.short_term.load(pd.DataFrame({"Hisse": ["SHORT"]}))
        self.window.pages.setCurrentWidget(self.window.short_term)
        self.window.pages.setCurrentWidget(page)
        pd.testing.assert_frame_equal(page._data, expected)

    def test_short_term_result_cannot_write_to_under50_page(self):
        page = self.window.under_50
        expected = page._data.copy(deep=True)
        request_id = page.begin_request("under-current")
        accepted = page.apply_scan_result(
            request_id, self.window.short_term.page_id, True,
            pd.DataFrame({"Hisse": ["SHORT"]}), "yanlış sayfa",
        )
        self.assertFalse(accepted)
        pd.testing.assert_frame_equal(page._data, expected)

    def test_late_worker_result_is_ignored(self):
        page = self.window.under_50
        expected = page._data.copy(deep=True)
        old_id = page.begin_request("old")
        new_id = page.begin_request("new")
        page._scan_identity = {"request_id": new_id, "strategy_id": "under_50_tl", "universe_id": "all_bist"}
        page.done(old_id, page.page_id, "under_50_tl", "all_bist", True, under_50_result("OLD"), "eski")
        pd.testing.assert_frame_equal(page._data, expected)
        page.done(new_id, page.page_id, "under_50_tl", "all_bist", True, under_50_result("NEW"), "yeni")
        self.assertEqual(page.table.item(0, 0).text(), "NEW")

    def test_page_models_state_and_cache_are_independent(self):
        pages = (self.window.ceiling_potential, self.window.under_50, self.window.short_term)
        self.assertEqual(len({id(page._data) for page in pages}), 3)
        self.assertEqual(len({id(page.result_cache) for page in pages}), 3)
        self.assertEqual(len({page.page_id for page in pages}), 3)

    def test_running_under50_scan_does_not_create_duplicate_worker(self):
        page = Under50Page()

        class RunningThread:
            @staticmethod
            def isRunning():
                return True

        marker = object()
        page.thread = RunningThread()
        page.worker = marker
        page.start_scan()
        self.assertIs(page.worker, marker)
        self.assertIsNone(page._active_request_id)
        page.close()

if __name__ == "__main__":
    unittest.main()
