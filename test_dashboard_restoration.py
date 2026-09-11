import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pandas as pd
from PySide6.QtWidgets import QApplication
from app_qt import MainWindow, NextDayWorker
from test_ertesi_gun_sistemi import sample_frame


class DashboardRestorationTests(unittest.TestCase):
    def test_trade_store_releases_windows_file_handle(self):
        from trade_adaylari import TomorrowTradeStore
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            store = TomorrowTradeStore(path)
            store.metrics()
            path.rename(path.with_suffix(".bak"))

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_old_navigation_and_new_strategy_pages_coexist(self):
        with tempfile.TemporaryDirectory() as directory, patch("app_qt.veri_klasoru", return_value=Path(directory)):
            window = MainWindow()
            for key in window._page_map:
                window._show_page(key)
                self.assertIs(window.pages.currentWidget(), window._page_map[key])
                self.assertTrue(window.sidebar.buttons[key].isChecked())
            self.assertEqual(set(window.home.preview_tables), {"trade", "short", "medium"})
            self.assertIn("BIST30", window.sidebar.buttons["short"].text())
            self.assertIn("BIST30", window.sidebar.buttons["medium"].text())
            window._dashboard_search("ASELS")
            self.assertEqual(window.single.symbol.text(), "ASELS")
            window.close()

    def test_restored_radar_uses_provider_and_rejects_stale_prices(self):
        for stale in (False, True):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as directory, \
                 patch("app_qt.veri_klasoru", return_value=Path(directory)), \
                 patch("bist_evreni.tum_bist_hisseleri", return_value=["TEST.IS"]), \
                 patch("radar_menkul.kap_menkul_turleri", return_value={}), \
                 patch("veri_saglayici.get_daily_ohlcv", return_value=(sample_frame(), SimpleNamespace(is_stale=stale, source="fixture"))):
                worker = NextDayWorker()
                outputs = []
                worker.finished.connect(lambda *args: outputs.append(args))
                worker.run()
                self.assertTrue(outputs[0][0], outputs[0][2])
                frame = outputs[0][1]
                if stale:
                    self.assertEqual(frame.iloc[0]["Durum"], "VERİ ALINAMADI")
                else:
                    self.assertIn("T+1 Sırası", frame.columns)
                    self.assertIn("T+2 Sırası", frame.columns)


if __name__ == "__main__":
    unittest.main()
