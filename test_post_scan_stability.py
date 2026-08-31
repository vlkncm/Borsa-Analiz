import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from PySide6.QtWidgets import QApplication

import app_qt
from app_qt import MainWindow


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class PostScanStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _large_snapshot():
        rows = 600
        frame = pd.DataFrame({
            "Hisse": [f"H{i:04d}" for i in range(rows)],
            "Fiyat": [50.0 + i / 100 for i in range(rows)],
            "Önerilen Alış Alt": [49.0 + i / 100 for i in range(rows)],
            "Önerilen Alış Üst": [50.5 + i / 100 for i in range(rows)],
            "Önerilen Satış": [58.0 + i / 100 for i in range(rows)],
            "Önerilen Stop": [46.0 + i / 100 for i in range(rows)],
            "v4 Güven Puanı": [40 + i % 50 for i in range(rows)],
            "Veri Durumu": ["GÜVENİLİR"] * rows,
            "Profesyonel Karar": ["İZLE"] * rows,
            "Yatırım Kararı": ["BEKLE"] * rows,
        })
        for index in range(50):
            frame[f"Ek Alan {index}"] = index
        return frame

    def _window_without_startup_report(self):
        with patch.object(MainWindow, "load_report", return_value=True):
            return MainWindow()

    def test_600x60_snapshot_only_renders_home_eagerly(self):
        window = self._window_without_startup_report(); self.addCleanup(window.close)
        frame = self._large_snapshot()
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "analiz_sonuclari.sqlite3"; report.touch()
            with patch.object(app_qt, "rapor_yolu", return_value=report), \
                 patch("analiz_deposu.anlik_goruntu_oku", return_value={"Tum Sonuclar": frame}), \
                 patch.object(window.home, "update_state", wraps=window.home.update_state) as home, \
                 patch.object(window.short_term, "load", wraps=window.short_term.load) as short, \
                 patch.object(window.medium_term, "load", wraps=window.medium_term.load) as medium, \
                 patch.object(window.daily_trade.table, "load", wraps=window.daily_trade.table.load) as daily, \
                 patch.object(window.under_50, "load", wraps=window.under_50.load) as under, \
                 patch.object(window.tum, "load", wraps=window.tum.load) as full:
                started = time.perf_counter()
                self.assertTrue(MainWindow.load_report(window))
                elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 1.0)
        self.assertEqual(home.call_count, 1)
        self.assertEqual(short.call_count, 0); self.assertEqual(medium.call_count, 0)
        self.assertEqual(daily.call_count, 0); self.assertEqual(under.call_count, 0)
        self.assertEqual(full.call_count, 0)
        self.assertGreaterEqual(len(window._lazy_page_renderers), 5)

    def test_reentrant_apply_is_rejected_and_state_is_released(self):
        window = self._window_without_startup_report(); self.addCleanup(window.close)
        window._applying_scan_result = True
        self.assertFalse(MainWindow.load_report(window))
        window._applying_scan_result = False
        self.assertFalse(window._applying_scan_result)

    def test_duplicate_symbol_diagnostics_are_countable(self):
        frame = self._large_snapshot()
        duplicated = pd.concat([frame, frame.iloc[:3]], ignore_index=True)
        self.assertEqual(3, len(duplicated) - duplicated["Hisse"].nunique())


if __name__ == "__main__":
    unittest.main()
