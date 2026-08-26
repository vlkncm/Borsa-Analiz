import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtWidgets import QApplication

from app_qt import MainWindow
from dashboard_ui import MarketCard, Sidebar


class DashboardUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_order_and_removed_links(self):
        window = MainWindow()
        labels = [text for _key, _icon, text in Sidebar.ITEMS]
        self.assertEqual(labels, ["Ana Sayfa", "Ertesi Gün Tavan Adayları", "Günlük Trade",
            "Kısa Vade · BIST 30", "Orta Vade · BIST 30", "50 TL Altı", "Fon Analizi",
            "Portföy", "Tahmin Performansı", "Ayarlar"])
        self.assertNotIn("10X", " ".join(labels)); self.assertNotIn("Excel", " ".join(labels))
        window.close()

    def test_every_menu_page_opens_and_active_state_changes(self):
        window = MainWindow()
        for key, page in window._page_map.items():
            window._show_page(key); self.app.processEvents()
            self.assertIs(window.pages.currentWidget(), page)
            self.assertTrue(window.sidebar.buttons[key].isChecked())
        window.close()

    def test_next_day_selection_updates_detail_and_tabs_do_not_mix(self):
        window = MainWindow(); page = window.next_day
        frame = pd.DataFrame([
            {"Hisse":"GUCLU", "Önceki Kapanış":10.0, "Güncel Fiyat":10.2, "Günlük Değişim %":2.0,
             "Tavan Fiyatı":11.0, "Tavana Kalan %":7.8, "%8+ Olasılığı":None, "Tavan Olasılığı":None,
             "Tahmini En Yüksek Fiyat":None, "Durum":"GÜÇLÜ ERTESİ GÜN ADAYI", "Aday Nedenleri":["Hacim"], "Riskler":[]},
            {"Hisse":"RISK", "Önceki Kapanış":5.0, "Güncel Fiyat":5.0, "Günlük Değişim %":0.0,
             "Tavan Fiyatı":5.5, "Tavana Kalan %":10.0, "%8+ Olasılığı":None, "Tavan Olasılığı":None,
             "Tahmini En Yüksek Fiyat":None, "Durum":"YÜKSEK RİSK", "Aday Nedenleri":[], "Riskler":["Likidite"]},
        ])
        page.load_results(frame, "2 hisse tarandı")
        self.assertEqual(page.tables["strong"].rowCount(), 1); self.assertEqual(page.tables["risk"].rowCount(), 1)
        page._selected(page.tables["risk"], 0); self.assertIn("RISK", page.detail.title.text())
        window.close()

    def test_supported_sizes_have_no_horizontal_table_scroll(self):
        window = MainWindow(); window._show_page("next")
        for width, height in ((1366,768),(1600,900),(1920,1080)):
            window.resize(width,height); window.show(); self.app.processEvents()
            self.assertEqual(window.next_day.tables["strong"].horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(window.next_day.geometry().right(), window.pages.geometry().width())
        window.close()

    def test_market_card_never_invents_missing_value(self):
        widget = MarketCard("BIST 100"); widget.update_data(None)
        self.assertEqual(widget.value.text(), "Veri bekleniyor")


if __name__ == "__main__":
    unittest.main()
