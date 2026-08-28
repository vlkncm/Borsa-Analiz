import os
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtWidgets import QApplication, QScrollArea

from app_qt import MainWindow
from responsive_ui import (
    AnalysisContext, AnalysisStateWidget, BaseAnalysisPage, PROFILE_COMPACT,
    PROFILE_STANDARD, PROFILE_WIDE, ResponsiveResultTable, profile_for_width,
)


class ResponsiveUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def sample():
        return pd.DataFrame([{
            "Hisse": "UZUNSIRKETADI", "Vade": "T+1", "Güncel Fiyat": 12.34,
            "T+1 %7+ Olasılığı": 41.2, "T+1 %8+ Olasılığı": 28.1,
            "T+1 Tavan Olasılığı": 11.4, "T+1 Giriş": 12.20,
            "T+1 Hedef": 13.30, "T+1 Stop": 11.80,
            "T+1/T+2 Durumu": "TEYİT BEKLİYOR",
            "Hisseye Özel Nedenler": "Hacim güçlü | Sıkışma var",
            "Hisseye Özel Riskler": "Likidite sınırlı",
            "Veri Zamanı": "2026-08-28T18:10:00", "Model Sürümü": "test-v1",
        }])

    def test_all_active_menu_pages_use_responsive_layout(self):
        window = MainWindow()
        self.assertEqual(set(window._page_map), {"home", "next", "daily", "short", "medium", "under50", "funds", "portfolio", "performance", "settings"})
        for key, page in window._page_map.items():
            self.assertTrue(getattr(page, "responsive_layout", False), key)
            window._show_page(key); self.app.processEvents()
            self.assertIs(window.pages.currentWidget(), page)
        window.close()

    def test_profiles_preserve_records_and_avoid_horizontal_scroll(self):
        page = BaseAnalysisPage("test", "Test")
        columns = list(self.sample().columns)
        page.table.configure_columns(columns[:7], columns[:9], columns)
        page.table.load_frame(self.sample())
        original = page.table.record_for_visual_row(0)
        for profile in (PROFILE_COMPACT, PROFILE_STANDARD, PROFILE_WIDE, PROFILE_COMPACT):
            page.set_view_profile(profile); page.resize(1100 if profile == PROFILE_COMPACT else 1700, 650)
            self.app.processEvents()
            self.assertEqual(original, page.table.record_for_visual_row(0))
            if profile != PROFILE_WIDE:
                self.assertEqual(0, page.table.horizontalScrollBar().maximum())
        page.close()

    def test_detail_button_and_double_click_use_exact_context(self):
        page = BaseAnalysisPage("t1_elite", "T+1 Seçkin")
        frame = self.sample(); columns = list(frame.columns)
        page.table.configure_columns(columns[:7], columns[:9], columns)
        page.table.set_context(AnalysisContext("t1_elite", horizon="T+1"))
        page.table.load_frame(frame)
        detail_column = page.table.columnCount() - 1
        page.table.cellWidget(0, detail_column).click(); self.app.processEvents()
        self.assertTrue(page._detail_window.isVisible())
        self.assertEqual("t1_elite", page._detail_window.context.analysis_id)
        self.assertEqual("UZUNSIRKETADI", page._detail_window.context.symbol)
        self.assertGreaterEqual(page._detail_window.tabs.count(), 3)
        self.assertTrue(all(isinstance(page._detail_window.tabs.widget(i), QScrollArea) for i in range(page._detail_window.tabs.count())))
        same_window = page._detail_window
        page.table._open_from_row(0, 0); self.app.processEvents()
        self.assertIs(same_window, page._detail_window)
        page.close()

    def test_detail_window_is_clamped_to_visible_screen(self):
        page = BaseAnalysisPage("geometry", "Geometri")
        record = self.sample().iloc[0].to_dict(); context = AnalysisContext("geometry").with_record(record)
        page._detail_window.move(-10000, -10000)
        page._detail_window.show_record(record, context); self.app.processEvents()
        area = QApplication.primaryScreen().availableGeometry()
        self.assertGreaterEqual(page._detail_window.frameGeometry().left(), area.left())
        self.assertGreaterEqual(page._detail_window.frameGeometry().top(), area.top())
        page.close()

    def test_sidebar_collapse_expands_table_area_without_losing_page(self):
        window = MainWindow(); window.resize(1366, 768); window.show(); self.app.processEvents()
        current = window.pages.currentWidget(); compact_width = window.sidebar.width()
        self.assertLessEqual(compact_width, 54)
        window.sidebar.set_expanded(True, remember=False); self.app.processEvents()
        self.assertGreater(window.sidebar.width(), compact_width)
        self.assertIs(current, window.pages.currentWidget())
        window.close()

    def test_loading_empty_missing_and_error_states_are_distinct(self):
        state = AnalysisStateWidget()
        state.set_loading(287, 548); self.assertEqual("loading", state.state); self.assertIn("287 / 548", state.text())
        state.set_empty(); self.assertEqual("empty", state.state); self.assertIn("Eşikler", state.text())
        state.set_missing("5/15 dakika canlı fiyat"); self.assertEqual("missing", state.state); self.assertIn("canlı fiyat", state.text())
        state.set_error(); self.assertEqual("error", state.state); self.assertIn("korunuyor", state.text())

    def test_supported_window_profiles(self):
        self.assertEqual(PROFILE_COMPACT, profile_for_width(1366))
        self.assertEqual(PROFILE_STANDARD, profile_for_width(1600))
        self.assertEqual(PROFILE_WIDE, profile_for_width(1920))

    def test_qt_scale_factors_keep_controls_readable(self):
        code = (
            "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; "
            "from PySide6.QtWidgets import QApplication; from app_qt import MainWindow; "
            "a=QApplication([]); w=MainWindow(); w.resize(1366,768); w.show(); a.processEvents(); "
            "assert w.top_header.scan.isVisible(); assert w.top_header.scan.height()>=20; "
            "assert w.fontMetrics().height()>=10; w.close()"
        )
        for factor in ("1", "1.25", "1.5"):
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=factor)
            result = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(__file__), env=env, timeout=40)
            self.assertEqual(0, result.returncode, factor)


if __name__ == "__main__":
    unittest.main()
