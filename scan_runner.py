from __future__ import annotations

import faulthandler
import sys
import warnings
from pathlib import Path


def main() -> int:
    warnings.filterwarnings(
        "ignore",
        message=r"Downcasting object dtype arrays.*",
        category=FutureWarning,
    )
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    data_root = Path.home() / "Documents" / "Borsa Analiz Pro MAX"
    data_root.mkdir(parents=True, exist_ok=True)
    with (data_root / "tarama_cokme.log").open("a", encoding="utf-8") as crash_stream:
        faulthandler.enable(file=crash_stream, all_threads=True)
        import main as analiz_main

        analiz_main.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
