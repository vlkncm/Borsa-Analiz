from __future__ import annotations

import importlib
import sys
from pathlib import Path


REQUIRED_MODULES = [
    "pandas",
    "numpy",
    "yfinance",
    "openpyxl",
    "requests",
    "matplotlib",
    "PIL",
    "pypdf",
    "bs4",
    "PySide6",
]


def calistir() -> tuple[bool, list[str]]:
    hatalar = []

    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            hatalar.append(f"{mod}: {exc}")

    base = Path(__file__).parent
    for dosya in [
        "main.py",
        "borsa_tarayici.py",
        "pro_moduller.py",
        "kap_modulu.py",
        "backtest.py",
        "mtf_grafik.py",
        "olasilik_temettu.py",
        "faaliyet_raporu.py",
        "piyasa_guncelleme.py",
        "bist_hisseleri_613_aktif.txt",
        "logo.png",
        "logo.ico",
    ]:
        if not (base / dosya).exists() and not getattr(sys, "frozen", False):
            hatalar.append(f"Eksik dosya: {dosya}")

    return (len(hatalar) == 0, hatalar)
