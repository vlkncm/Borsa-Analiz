import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app_qt import DailyTradeWorker, MainWindow
from tarama_evreni import (
    ALL_BIST, BIST30_ONLY, filter_frame_for_strategy, get_scan_universe, report_cache_key,
    report_metadata, report_scope_is_compatible, scan_scope_for_strategy,
)
from vade_motoru import vade_listeleri_uret


BIST30_SYMBOL = "ASELS.IS"
OUTSIDE_SYMBOL = "MEGMT.IS"


def metadata_sheet(scope=ALL_BIST):
    values = report_metadata("general_scan", scope, 2, 2)
    return pd.DataFrame({"Alan": list(values), "Değer": list(values.values())})


def horizon_candidate(symbol):
    return {
        "Hisse": symbol, "Veri Yaşı (Gün)": 0, "Yatırım Kararı": "BUGÜN AL",
        "Fiyat": 100, "Önerilen Alış Alt": 98, "Önerilen Alış Üst": 101,
        "Önerilen Satış": 120, "Önerilen Stop": 94, "Beklenen Getiri %": 25,
        "Model Olasılığı %": 75, "Karar Risk/Getiri": 2.2, "v4 Güven Puanı": 80,
        "Fibonacci Puanı": 70, "Formasyon Puanı": 65, "RSI": 58,
        "Son 20 Gün %": 8, "Son 60 Gün %": 15, "Son 252 Gün %": 30,
        "ADX": 35, "Hacim Oranı": 2.0, "Faaliyet Puanı": 68,
        "Profesyonel Kanıt Puanı": 72, "Kısa Güvenli Olasılık %": 55,
        "Orta Güvenli Olasılık %": 52, "Uzun Güvenli Olasılık %": 48,
    }


class ScanUniverseUnitTests(unittest.TestCase):
    def test_central_strategy_mapping(self):
        self.assertEqual(scan_scope_for_strategy("short_term"), BIST30_ONLY)
        self.assertEqual(scan_scope_for_strategy("medium_term"), BIST30_ONLY)
        for strategy in ("daily_trade", "under_50_tl", "ceiling_potential", "general_scan", "technical", "patterns", "future_page"):
            self.assertEqual(scan_scope_for_strategy(strategy), ALL_BIST)

    def test_all_bist_is_normalized_deduplicated_and_keeps_outside_symbol(self):
        symbols = get_scan_universe(
            "daily_trade", all_provider=lambda: [BIST30_SYMBOL, OUTSIDE_SYMBOL, "megmt", "../bad"],
        )
        self.assertEqual(symbols, [BIST30_SYMBOL, OUTSIDE_SYMBOL])

    def test_short_and_medium_use_only_bist30(self):
        providers = {"all_provider": lambda: [BIST30_SYMBOL, OUTSIDE_SYMBOL],
                     "bist30_provider": lambda: [BIST30_SYMBOL]}
        self.assertEqual(get_scan_universe("short_term", **providers), [BIST30_SYMBOL])
        self.assertEqual(get_scan_universe("medium_term", **providers), [BIST30_SYMBOL])

    def test_ceiling_and_under50_use_all_active_bist(self):
        provider = lambda: [BIST30_SYMBOL, OUTSIDE_SYMBOL]
        self.assertEqual(get_scan_universe("ceiling_potential", all_provider=provider), [BIST30_SYMBOL, OUTSIDE_SYMBOL])
        self.assertEqual(get_scan_universe("under_50_tl", all_provider=provider), [BIST30_SYMBOL, OUTSIDE_SYMBOL])

    def test_cache_key_separates_strategy_scope_and_date(self):
        day = date(2026, 8, 26)
        all_key = report_cache_key("daily_trade", ALL_BIST, day)
        b30_key = report_cache_key("daily_trade", BIST30_ONLY, day)
        other_strategy = report_cache_key("ceiling_potential", ALL_BIST, day)
        self.assertEqual(len({all_key, b30_key, other_strategy}), 3)

    def test_metadata_less_and_bist30_report_are_not_all_bist_compatible(self):
        self.assertFalse(report_scope_is_compatible({}, "daily_trade"))
        self.assertFalse(report_scope_is_compatible({"Hisse Evreni": BIST30_ONLY}, "daily_trade"))
        self.assertTrue(report_scope_is_compatible({"Hisse Evreni": ALL_BIST}, "daily_trade"))

    def test_horizon_outputs_filter_short_and_medium(self):
        frames = vade_listeleri_uret(pd.DataFrame([horizon_candidate(BIST30_SYMBOL), horizon_candidate(OUTSIDE_SYMBOL)]))
        short, medium, long = frames
        self.assertEqual(short["Hisse"].tolist(), [BIST30_SYMBOL])
        self.assertEqual(medium["Hisse"].tolist(), [BIST30_SYMBOL])
        self.assertIn(OUTSIDE_SYMBOL, long["Hisse"].tolist())

    def test_short_term_report_fallback_cannot_leak_non_bist30(self):
        source = pd.DataFrame({"Hisse": [BIST30_SYMBOL, OUTSIDE_SYMBOL]})
        self.assertEqual(filter_frame_for_strategy(source, "short_term")["Hisse"].tolist(), [BIST30_SYMBOL])
        self.assertEqual(filter_frame_for_strategy(source, "daily_trade")["Hisse"].tolist(), [BIST30_SYMBOL, OUTSIDE_SYMBOL])


class DailyTradeUniverseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_manual_daily_trade_keeps_bist30_and_non_bist30_candidates(self):
        captured = []
        worker = DailyTradeWorker("15m", 100000, 0.5, 1.8, True)
        worker.finished.connect(lambda request, strategy, universe, ok, frame, message: captured.append((ok, frame, message)))

        def eligible(symbol, **_kwargs):
            return {"Hisse": symbol, "Sonuç": "AL ADAYI", "Hedef": 110, "Stop": 95}

        with patch("bist_evreni.tum_bist_hisseleri", return_value=[BIST30_SYMBOL, OUTSIDE_SYMBOL]), patch(
            "gunluk_trade_motoru.gunluk_trade_analiz", side_effect=eligible
        ):
            worker.run()
        self.assertTrue(captured[0][0])
        self.assertEqual(captured[0][1]["Hisse"].tolist(), [BIST30_SYMBOL, OUTSIDE_SYMBOL])
        self.assertIn("Tüm Aktif BIST", captured[0][2])

    def test_startup_report_can_show_non_bist30_candidate(self):
        candidates = pd.DataFrame({"Hisse": [BIST30_SYMBOL, OUTSIDE_SYMBOL], "Karar": ["Uygun", "Uygun"]})
        sheets = {"Rapor Bilgisi": metadata_sheet(), "Tum Sonuclar": candidates}
        window = MainWindow()
        try:
            with patch("app_qt.rapor_yolu", return_value=Path(__file__)), patch(
                "app_qt.pd.read_excel", return_value=sheets
            ), patch("app_qt.sade_firsatlar", return_value=candidates):
                self.assertTrue(window.load_report())
            self.assertEqual(window.daily_trade.table._data["Hisse"].tolist(), [BIST30_SYMBOL, OUTSIDE_SYMBOL])
        finally:
            window.close()

    def test_legacy_report_is_not_presented_as_all_bist_daily_trade(self):
        old = pd.DataFrame({"Hisse": [BIST30_SYMBOL], "Karar": ["Uygun"]})
        window = MainWindow()
        try:
            with patch("app_qt.rapor_yolu", return_value=Path(__file__)), patch(
                "app_qt.pd.read_excel", return_value={"Tum Sonuclar": old}
            ), patch("app_qt.sade_firsatlar", return_value=old):
                self.assertTrue(window.load_report())
            self.assertTrue(window.daily_trade.table._data.empty)
            self.assertIn("yeniden", window.daily_trade.status.text().casefold())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
