import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BORSA_VISUAL_TEST", "1")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

import app_qt
import main
from app_qt import MainWindow, NextDayPage, tarama_alt_sureci_komutu
from scan_progress import COMPONENTS, ScanCoordinator, parse_progress_line


class ScanProgressTests(unittest.TestCase):
    def test_structured_25_of_100_and_legacy_errors_are_real_work(self):
        state = ScanCoordinator("abc")
        state.start_component("core")
        self.assertTrue(state.accept_line("PROGRESS|abc|stocks|25|100|Hisseler analiz ediliyor"))
        self.assertEqual((state.stock_completed, state.stock_total), (25, 100))
        self.assertGreater(state.percent, 0)
        self.assertTrue(state.accept_line("26/100 hata: TEST.IS -> veri yok"))
        self.assertEqual(state.stock_completed, 26)

    def test_progress_never_moves_back_and_stale_scan_is_ignored(self):
        state = ScanCoordinator("new")
        state.accept_line("PROGRESS|new|stocks|80|100|Hisseler analiz ediliyor")
        percent = state.percent
        state.accept_line("PROGRESS|new|stocks|20|100|Hisseler analiz ediliyor")
        self.assertEqual(state.percent, percent)
        self.assertFalse(state.accept_line("PROGRESS|old|stocks|100|100|Eski tarama"))
        self.assertEqual(state.stock_completed, 80)

    def test_core_end_cannot_reach_100_until_every_component_terminal(self):
        state = ScanCoordinator("x")
        state.accept_line("PROGRESS|x|stocks|100|100|Hisseler analiz ediliyor")
        state.finish_component("core")
        for name in COMPONENTS:
            if name not in {"core", "high_movement"}:
                state.finish_component(name)
        self.assertLess(state.percent, 100)
        state.finish_component("high_movement")
        self.assertEqual(state.percent, 100)

    def test_core_complete_message_is_not_global_completion(self):
        state = ScanCoordinator("x")
        state.start_component("core")
        state.start_component("high_movement")
        self.assertTrue(state.accept_line("PROGRESS|x|core_complete|1|1|Tarama tamamlandı"))
        self.assertNotEqual(state.message, "Tarama tamamlandı")
        self.assertIn("bölümler hazırlanıyor", state.message)

    def test_successful_core_exit_closes_missing_stock_progress(self):
        state = ScanCoordinator("x")
        state.accept_line("PROGRESS|x|universe|100|100|Aktif BIST evreni yükleniyor")
        state.accept_line("PROGRESS|x|stocks|97|100|Hisseler analiz ediliyor")
        state.finish_stock_work()
        self.assertEqual((state.stock_completed, state.stock_total), (100, 100))

    def test_malformed_progress_is_rejected(self):
        self.assertIsNone(parse_progress_line("PROGRESS|x|stocks|bad|10|Mesaj"))


class ScanCommandAndUniverseTests(unittest.TestCase):
    def test_all_console_writes_survive_closed_qprocess_pipe(self):
        class ClosedPipe:
            encoding = "utf-8"

            def write(self, _text):
                raise OSError(22, "closed pipe")

            def flush(self):
                raise OSError(22, "closed pipe")

        stream = main.SafeConsoleStream(ClosedPipe())
        self.assertEqual(stream.write("normal print output"), len("normal print output"))
        self.assertIsNone(stream.flush())

    def test_closed_stdout_pipe_never_crashes_progress_protocol(self):
        with patch("builtins.print", side_effect=OSError(22, "closed pipe")):
            self.assertFalse(main.safe_console_print("PROGRESS|x|stocks|1|1|ok", flush=True))

    def test_source_and_frozen_commands(self):
        with patch.object(sys, "frozen", False, create=True):
            program, args = tarama_alt_sureci_komutu()
            self.assertEqual(Path(args[0]).name, "scan_runner.py")
            self.assertEqual(program, sys.executable)
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", r"C:\Program\BorsaAnalizProMAX.exe"):
            program, args = tarama_alt_sureci_komutu()
            self.assertEqual(program, str(Path(r"C:\Program\BorsaAnalizProMAX.exe").resolve()))
            self.assertEqual(args, ["--headless-scan"])

    def test_all_universe_and_test_limit(self):
        symbols = [f"S{i}.IS" for i in range(10)]
        with patch.dict(os.environ, {"BORSA_TARAMA_EVRENI": "ALL", "BORSA_TEST_SYMBOLS": "5"}, clear=False), \
             patch.object(main, "tum_bist_hisseleri", return_value=symbols):
            self.assertEqual(main.hisseleri_txt_oku(), symbols[:5])

    def test_non_bist30_symbol_is_actually_analyzed(self):
        with patch.object(main, "teknik_analiz", return_value={"symbol": "TEST.IS"}) as analyze:
            self.assertEqual(main.hisse_tara("TEST.IS")["symbol"], "TEST.IS")
            analyze.assert_called_once_with("TEST.IS", "Aktif BIST")


class MainWindowScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        load = patch.object(MainWindow, "load_report", return_value=True)
        load.start(); self.addCleanup(load.stop)
        window = MainWindow(); self.addCleanup(window.close)
        return window

    def test_button_signal_starts_once_sets_all_and_shows_progress(self):
        window = self.make_window()
        with patch.object(QProcess, "start"), patch.object(NextDayPage, "start_scan") as radar, \
             patch.object(window.daily_trade, "start_scan") as daily, patch.object(window.under_50, "start_scan") as under:
            window.scan_button.click(); self.app.processEvents()
            first = window.scan_process
            self.assertIsNotNone(first)
            self.assertTrue(window.scan_progress.isVisible() or not window.isVisible())
            self.assertEqual(first.processEnvironment().value("BORSA_TARAMA_EVRENI"), "ALL")
            self.assertEqual(first.processEnvironment().value("BORSA_SCAN_ID"), window.scan_coordinator.scan_id)
            self.assertEqual(radar.call_count, 0)
            window._start_analysis_workers(["AAA.IS", "BBB.IS", "CCC.IS", "DDD.IS"])
            self.assertEqual(daily.call_args.args[1], ["AAA.IS", "BBB.IS", "CCC.IS", "DDD.IS"])
            self.assertEqual(under.call_count, 0); self.assertEqual(radar.call_count, 0)
            run_id = window.scan_coordinator.scan_id
            window._analysis_worker_finished("daily_trade", run_id, True, pd.DataFrame(), "ok")
            self.assertEqual(under.call_args.args[1], ["AAA.IS", "BBB.IS", "CCC.IS", "DDD.IS"])
            self.assertEqual(radar.call_count, 0)
            window._analysis_worker_finished("under_50", run_id, True, pd.DataFrame(), "ok")
            self.assertEqual(radar.call_args.args[1], ["AAA.IS", "BBB.IS", "CCC.IS", "DDD.IS"])
            self.assertFalse(window.scan())
            self.assertIs(window.scan_process, first)
            self.assertEqual(radar.call_count, 1)

    def test_failed_to_start_unlocks_button_and_preserves_error_panel(self):
        window = self.make_window()
        with patch.object(QProcess, "start"), patch.object(NextDayPage, "start_scan"):
            window.scan()
            window._scan_process_error(QProcess.FailedToStart)
        self.assertTrue(window.scan_button.isEnabled())
        self.assertIsNone(window.scan_process)
        self.assertIn("başlatılamadı", window.scan_progress.status.text().lower())

    def test_normal_finish_refreshes_pages_but_waits_for_radar(self):
        window = self.make_window()
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "analiz_sonuclari.sqlite3"
            report.write_bytes(b"old")
            with patch.object(app_qt, "rapor_yolu", return_value=report), patch.object(QProcess, "start"), \
                 patch.object(NextDayPage, "start_scan"), patch.object(window, "load_report", return_value=True) as load, \
                 patch.object(window, "_refresh_portfolio_from_report") as portfolio:
                window.scan(); time.sleep(0.002); report.write_bytes(b"new-result")
                window.scan_coordinator.accept_line(f"PROGRESS|{window.scan_coordinator.scan_id}|stocks|5|5|Hisseler analiz ediliyor")
                window._scan_process_finished(0, QProcess.NormalExit)
                self.assertEqual((window.scan_coordinator.stock_completed, window.scan_coordinator.stock_total), (5, 5))
                self.assertLess(window.scan_coordinator.percent, 100)
                self.assertEqual(window.scan_coordinator.components["high_movement"], "CALISIYOR")
                self.assertEqual(window.scan_progress.status.text(), "Yüksek Hareket sonuçları hazırlanıyor")
                load.assert_called_once(); portfolio.assert_called_once()
                run_id = window.scan_coordinator.scan_id
                window._analysis_worker_finished("daily_trade", run_id, True, pd.DataFrame(), "ok")
                window._analysis_worker_finished("under_50", run_id, True, pd.DataFrame(), "ok")
                window._high_movement_finished(run_id, True, "ok")
                self.assertEqual(window.scan_coordinator.percent, 100)
                self.assertTrue(window.scan_button.isEnabled())
                self.assertIn("Toplam süre", window.scan_progress.phase.text())

    def test_abnormal_exit_does_not_reload_old_result(self):
        window = self.make_window()
        with patch.object(QProcess, "start"), patch.object(NextDayPage, "start_scan"), \
             patch.object(window, "load_report", return_value=True) as load:
            window.scan(); run_id = window.scan_coordinator.scan_id
            window._scan_process_finished(7, QProcess.CrashExit)
            window._high_movement_finished(run_id, False, "worker failed")
            load.assert_not_called()
        self.assertIn("Önceki geçerli sonuçlar korundu", window.scan_progress.phase.text())

    def test_progress_panel_fits_1366_by_768_and_fund_button_stays_independent(self):
        window = self.make_window(); window.resize(1366, 768); window.show(); window.scan_progress.show(); self.app.processEvents()
        self.assertLessEqual(window.scan_progress.width(), window.centralWidget().width())
        self.assertLess(window.scan_progress.sizeHint().height(), 80)
        self.assertFalse(window.funds.button.isHidden())
        self.assertTrue(window.funds.button.isEnabled())


if __name__ == "__main__":
    unittest.main()
