"""BIST pay kodlarini veri saglayicilarina gore tek noktadan esle."""
from __future__ import annotations

from dataclasses import dataclass
import re


_BASE_PATTERN = re.compile(r"[A-Z0-9]{2,12}")


class SembolEslemeHatasi(ValueError):
    """Gecersiz veya desteklenmeyen bir pay kodu verildi."""


@dataclass(frozen=True)
class BistSembol:
    kod: str

    @property
    def yahoo(self) -> str:
        return f"{self.kod}.IS"

    @property
    def kap(self) -> str:
        return f"{self.kod}.E"

    @property
    def borsa(self) -> str:
        return f"{self.kod}.E"


def bist_sembolu(value: object) -> BistSembol:
    text = str(value or "").strip().upper()
    for suffix in (".IS", ".E"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    if not _BASE_PATTERN.fullmatch(text):
        raise SembolEslemeHatasi(
            f"Veri alinamadi - sembol eslestirmesi kontrol edilmeli: {value!r}"
        )
    return BistSembol(text)


def normalize_bist_kodu(value: object) -> str:
    try:
        return bist_sembolu(value).kod
    except SembolEslemeHatasi:
        return ""


def saglayici_sembolu(value: object, provider: str = "yahoo") -> str:
    symbol = bist_sembolu(value)
    key = str(provider or "").strip().casefold()
    if key in {"yahoo", "yfinance"}:
        return symbol.yahoo
    if key in {"kap", "borsa", "borsa_istanbul", "bist_bulteni"}:
        return symbol.kap
    if key in {"base", "kod", "bare"}:
        return symbol.kod
    raise SembolEslemeHatasi(f"Bilinmeyen veri saglayici: {provider!r}")
