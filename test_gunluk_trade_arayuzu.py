import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_qt import MainWindow


class DailyTradeUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_old_terminal_view_is_kept_without_separate_trade_page(self):
        window = MainWindow()
        self.assertIs(window.pages.widget(0), window.terminal)
        self.assertFalse(hasattr(window, "daily_trade"))
        window.close()


if __name__ == "__main__":
    unittest.main()
