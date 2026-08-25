import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_qt import MainWindow


class DailyTradeUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_simple_trade_page_exists_and_activity_page_is_removed(self):
        window = MainWindow()
        self.assertIs(window.pages.widget(0), window.home)
        self.assertGreaterEqual(window.pages.indexOf(window.daily_trade), 0)
        self.assertEqual(window.daily_trade.table.horizontalScrollBarPolicy().value, 1)
        self.assertLessEqual(window.daily_trade.table.columnCount(), 10)
        self.assertFalse(hasattr(window, "activity"))
        window.close()


if __name__ == "__main__":
    unittest.main()
