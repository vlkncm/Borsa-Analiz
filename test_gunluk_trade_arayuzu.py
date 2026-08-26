import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from app_qt import MainWindow
import pandas as pd


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

    def test_daily_trade_is_compact_and_responsive_at_supported_sizes(self):
        window = MainWindow()
        page = window.daily_trade
        window.pages.setCurrentWidget(page)
        sample = pd.DataFrame([{
            "Hisse": "TEST", "Sonuç": "TEYİT BEKLE", "Alış Alt": 10, "Alış Üst": 10.2,
            "Hedef": 11, "Stop": 9.5, "Hedef Potansiyeli %": 10, "Hedef Önce Olasılığı %": "%60",
            "Olasılık Ufku — İşlem Günü": 3, "OOS Örnek Sayısı": 30, "Olasılık %95 Güven Aralığı": "%42 – %75",
            "Ufuk Olasılıkları": {1: {"probability": 40, "sample_size": 35, "ci_low": 25, "ci_high": 56},
                                    3: {"probability": 60, "sample_size": 30, "ci_low": 42, "ci_high": 75},
                                    5: {"probability": None, "sample_size": 20, "ci_low": None, "ci_high": None}},
            "Başarılılarda Medyan Süre": 2, "Piyasa Rejimi": "RANGE", "Tazelik": "GÜNCEL",
            "Veri Zamanı": "2026-08-25T17:00", "Gerekçe": "Uzun bir gerekçe metni ayrıntı panelinde kelime kaydırmalıdır.",
        }])
        page.scan_done(True, sample, "Tamamlandı")
        expected = ["Hisse / Karar", "Alış Bandı", "Hedef", "Stop", "Yükseliş %", "Olasılık / Süre"]
        self.assertEqual([page.table.table.horizontalHeaderItem(i).text() for i in range(6)], expected)
        for width, height in ((1920, 1080), (1366, 768), (1280, 720), (1024, 768)):
            window.resize(width, height); window.show(); self.app.processEvents()
            self.assertTrue(all(not page.table.table.isColumnHidden(i) for i in range(6)))
            self.assertEqual(page.table.table.horizontalScrollBar().maximum(), 0)
            self.assertGreater(page.table.table.columnWidth(0), 0)
            self.assertGreater(page.table.table.columnWidth(2), 0)
            self.assertGreater(page.table.table.columnWidth(5), 0)
        page._show_inline_detail(0)
        self.assertIn("1 günde hedef olasılığı", page.detail.text())
        self.assertIn("Yetersiz örnek", page.detail.text())
        self.assertTrue(page.detail.wordWrap())
        window.close()


if __name__ == "__main__":
    unittest.main()
