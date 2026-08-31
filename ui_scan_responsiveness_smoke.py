"""Gerçek tek-tuş taramasında Qt olay döngüsünün canlı kaldığını doğrular."""
from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BORSA_TEST_SYMBOLS", "20")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app_qt import MainWindow


app = QApplication([])
window = MainWindow()
started = time.monotonic()
last_tick = started
max_gap = 0.0
runs_target = int(os.getenv("BORSA_SMOKE_RUNS", "1"))
runs_completed = 0
run_started = started
restart_due = None
run_results = []


def heartbeat():
    global last_tick, max_gap, runs_completed, run_started, restart_due
    now = time.monotonic()
    max_gap = max(max_gap, now - last_tick)
    last_tick = now
    coordinator = window.scan_coordinator
    if coordinator and coordinator.all_terminal:
        if restart_due is None:
            window._show_page("short"); window._show_page("home")
            runs_completed += 1
            run_results.append(now - run_started)
            restart_due = now + 1.0
        elif now >= restart_due and window._active_worker_count() == 0:
            if runs_completed >= runs_target:
                print(f"SMOKE_OK runs={runs_completed} durations={run_results} elapsed={now-started:.1f}s max_ui_gap={max_gap:.3f}s apply_count={window._scan_apply_count} active_threads={window._active_worker_count()}", flush=True)
                window.close()
                app.quit()
            else:
                restart_due = None; run_started = now
                window.scan()
    elif now - started > 600:
        print(f"SMOKE_TIMEOUT max_ui_gap={max_gap:.3f}s", flush=True)
        window.cancel_scan()
        window.close()
        app.exit(2)


timer = QTimer()
timer.timeout.connect(heartbeat)
timer.start(100)
QTimer.singleShot(100, window.scan)
exit_code = app.exec()
sys.exit(exit_code if max_gap < 5.0 else 3)
