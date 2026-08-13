"""BIST 30 tarama evreni ve tek-hisse sembol doğrulama yardımcıları."""

import re

BIST30_DONEMI = "2026-Q3 (01.07.2026-30.09.2026)"
BIST30_KAYNAK = "https://www.borsaistanbul.com/duyuru/15483/"

BIST30_KODLARI = (
    "AEFES", "AKBNK", "ASELS", "ASTOR", "BIMAS", "DSTKF",
    "EKGYO", "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF",
    "ISCTR", "KCHOL", "KRDMD", "MGROS", "PETKM", "PGSUS",
    "SAHOL", "SASA", "SISE", "TAVHL", "TCELL", "THYAO",
    "TOASO", "TRALT", "TTKOM", "TUPRS", "VAKBN", "YKBNK",
)

BIST30_SEMBOLLERI = tuple(f"{kod}.IS" for kod in BIST30_KODLARI)
BIST30_KUMESI = frozenset(BIST30_SEMBOLLERI)


def normalize_bist30_sembolu(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if symbol and not symbol.endswith(".IS"):
        symbol += ".IS"
    return symbol if symbol in BIST30_KUMESI else ""


def normalize_bist_sembolu(value: str) -> str:
    """Tek hisse analizinde BIST 30 dışındaki geçerli BIST kodlarını da kabul eder."""
    symbol = str(value or "").strip().upper()
    if symbol.endswith(".IS"):
        symbol = symbol[:-3]
    if not re.fullmatch(r"[A-Z0-9]{2,12}", symbol):
        return ""
    return f"{symbol}.IS"


def bist30_hisseleri() -> list[str]:
    return list(BIST30_SEMBOLLERI)
