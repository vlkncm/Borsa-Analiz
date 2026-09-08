import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_qt import MainWindow
from ui_components import PageHeader, ResponsiveResultTable


class CommonUiSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.load_patch = patch.object(MainWindow, "load_report", lambda _self: None)
        self.load_patch.start()
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.load_patch.stop()

    def test_all_required_pages_exist_and_use_common_headers(self):
        required = [
            self.window.home, self.window.daily_trade, self.window.short_term,
            self.window.medium_term, self.window.single, self.window.sale,
            self.window.track, self.window.under_50, self.window.ceiling_potential,
            self.window.funds, self.window.history, self.window.prediction_performance,
        ]
        self.assertEqual(len(self.window.sidebar._buttons), 12)
        for page in required:
            self.assertIsInstance(page.page_header, PageHeader)
            self.window.pages.setCurrentWidget(page)
            self.app.processEvents()
            self.assertTrue(self.window.sidebar._buttons[page].isChecked())

    def test_prediction_performance_page_is_separate_and_refreshable(self):
        page = self.window.prediction_performance
        self.assertEqual(page.page_id, "prediction_performance")
        page.refresh()
        self.assertIn("Kayıt zinciri", page.summary.text())

    def test_supported_resolutions_keep_horizontal_scroll_disabled(self):
        pages = list(self.window.sidebar._buttons)
        for width, height in ((1920, 1080), (1366, 768), (1280, 720), (1024, 768)):
            self.window.resize(width, height)
            for page in pages:
                self.window.pages.setCurrentWidget(page)
                self.app.processEvents()
                self.assertLessEqual(page.width(), self.window.pages.width())
                for table in page.findChildren(ResponsiveResultTable):
                    self.assertEqual(table.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
                    self.assertLessEqual(table.width(), page.width())

    def test_narrow_table_hides_secondary_columns_and_keeps_detail(self):
        frame = pd.DataFrame([{
            "Hisse": "TEST", "Karar": "Uygun", "Alış Bandı": "10–11",
            "Hedef": 13, "Stop": 9, "Potansiyel %": 18,
            "Olasılık / Süre": "%67\n3 gün içinde", "RVOL": 1.8,
            "OOS Örnek": 126, "Güven Aralığı": "%58–75",
        }])
        page = self.window.short_term
        page.load(frame)
        self.window.pages.setCurrentWidget(page)
        self.window.resize(1024, 768)
        self.app.processEvents()
        headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
        probability_index = headers.index("Olasılık / Süre")
        rvol_index = headers.index("RVOL")
        self.assertFalse(page.table.isColumnHidden(probability_index))
        self.assertTrue(page.table.isColumnHidden(rvol_index))
        self.assertIn("RVOL: 1.8", page.detail_panel.content.text())

    def test_empty_state_and_daily_probability_horizon(self):
        self.window.short_term.load(pd.DataFrame())
        self.window.pages.setCurrentWidget(self.window.short_term)
        self.app.processEvents()
        self.assertTrue(self.window.short_term.empty_state.isVisible())
        formatted = self.window.daily_trade.format_display(pd.DataFrame([{
            "Hisse": "TEST", "Sonuç": "TEYİT BEKLE", "Alış Alt": 10,
            "Alış Üst": 11, "Hedef": 13, "Stop": 9,
            "Hedef Önce Olasılığı %": "%67", "Örnek": 126,
        }]))
        self.assertEqual(formatted.iloc[0]["Olasılık / Süre"], "%67\nGün içi")
        self.assertIn("Örnek", formatted.columns)


if __name__ == "__main__":
    unittest.main()
