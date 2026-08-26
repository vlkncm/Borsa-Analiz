import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_qt import MainWindow
from tarama_evreni import ALL_BIST


class DailyTradeUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_simple_trade_page_exists_and_activity_page_is_removed(self):
        window = MainWindow()
        self.assertIs(window.pages.widget(0), window.home)
        self.assertGreaterEqual(window.pages.indexOf(window.daily_trade), 0)
        self.assertEqual(window.daily_trade.table.table.horizontalScrollBarPolicy().value, 1)
        self.assertLessEqual(window.daily_trade.table.table.columnCount(), 10)
        self.assertFalse(hasattr(window, "early_growth"))
        self.assertFalse(hasattr(window, "long_growth"))
        self.assertFalse(hasattr(window, "settings"))
        self.assertFalse(hasattr(window, "help_page"))
        self.assertFalse(hasattr(window, "kap"))
        self.assertTrue(hasattr(window.daily_trade, "scan_button"))
        self.assertFalse(hasattr(window, "activity"))
        window.close()

    def test_daily_trade_scans_the_active_bist_universe(self):
        window = MainWindow()
        with patch.object(window, "scan") as scan:
            window.scan_daily_trade()
        self.assertIs(window._scan_target, window.daily_trade)
        self.assertEqual(window._scan_universe, ALL_BIST)
        scan.assert_called_once_with()
        window.close()


if __name__ == "__main__":
    unittest.main()
