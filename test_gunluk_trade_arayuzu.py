import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_qt import MainWindow


class DailyTradeUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_page_exists_and_routes_without_index_dependency(self):
        window = MainWindow()
        self.assertGreaterEqual(window.pages.indexOf(window.daily_trade), 0)
        window.pages.setCurrentWidget(window.daily_trade)
        self.assertIs(window.pages.currentWidget(), window.daily_trade)
        self.assertEqual(window.daily_trade.interval.count(), 2)
        self.assertLessEqual(window.daily_trade.risk.maximum(), 1.0)
        window.close()


if __name__ == "__main__":
    unittest.main()
