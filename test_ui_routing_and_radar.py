import os
import unittest

import pandas as pd
from PySide6.QtWidgets import QApplication

from app_qt import DecisionPage, HomePage
from dashboard_ui import radar_movement_candidates, strongest_five_candidates
from sade_karar_modeli import sade_firsatlar


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class UiRoutingAndRadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _candidates():
        raw = pd.DataFrame({
            "Hisse": ["AAA", "BBB", "CCC"],
            "Fiyat": [100.0, 80.0, 60.0],
            "Önerilen Alış Alt": [99.0, 79.0, 59.0],
            "Önerilen Alış Üst": [101.0, 81.0, 61.0],
            "Önerilen Satış": [112.0, 90.0, 68.0],
            "Önerilen Stop": [95.0, 75.0, 56.0],
            "v4 Güven Puanı": [78.0, 70.0, 62.0],
            "Veri Durumu": ["GÜVENİLİR"] * 3,
            "Profesyonel Karar": ["UYGUN ADAY", "TEYİT BEKLİYOR", "İZLE"],
        })
        return sade_firsatlar(raw, "kisa", limit=5)

    def test_home_short_result_is_not_lost_on_side_page(self):
        frame = self._candidates()
        home = HomePage()
        page = DecisionPage("KISA VADE", "Tüm Aktif BIST")
        home.update_state(pd.DataFrame(), frame, pd.DataFrame(), "YATAY")
        page.load(frame)
        self.assertEqual(len(frame), home.preview_tables["short"].rowCount())
        self.assertEqual(len(frame), len(page._data))

    def test_home_medium_result_is_not_lost_on_side_page(self):
        frame = self._candidates()
        home = HomePage()
        page = DecisionPage("ORTA VADE", "Tüm Aktif BIST")
        home.update_state(pd.DataFrame(), pd.DataFrame(), frame, "YATAY")
        page.load(frame)
        self.assertEqual(len(frame), home.preview_tables["medium"].rowCount())
        self.assertEqual(len(frame), len(page._data))

    def test_radar_calculates_change_from_previous_close(self):
        frame = pd.DataFrame({"Hisse": ["AAA"], "Önceki Kapanış": [100.0], "Güncel Fiyat": [109.5]})
        result = radar_movement_candidates(frame)
        self.assertAlmostEqual(9.5, float(result.iloc[0]["Günlük Değişim %"]), places=6)

    def test_stale_intraday_row_is_not_presented_as_current_radar(self):
        frame = pd.DataFrame({
            "Hisse": ["AAA"], "Önceki Kapanış": [100.0], "Güncel Fiyat": [109.5], "Tazelik": ["STALE"]
        })
        self.assertTrue(radar_movement_candidates(frame).empty)

    def test_strongest_five_does_not_require_buy_decision(self):
        frame = pd.DataFrame({
            "Hisse": [f"H{i}" for i in range(10)],
            "Güncel Fiyat": [100.0 + i for i in range(10)],
            "T+1 Güç Skoru": list(range(10)),
            "T+1 Kararı": ["ALMA"] * 10,
        })
        result = strongest_five_candidates(frame)
        self.assertEqual(["H9", "H8", "H7", "H6", "H5"], result["Hisse"].tolist())
        self.assertTrue(result["Karar"].eq("TAKİP").all())


if __name__ == "__main__":
    unittest.main()
