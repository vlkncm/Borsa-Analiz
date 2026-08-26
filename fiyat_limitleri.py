"""Borsa İstanbul pay fiyat limitleri için tek merkezî hesaplama noktası.

Fiyat adımları tarihsel olarak değişebildiğinden tablo sürümlüdür. Bilinmeyen bir
tarih veya ürün kuralı sessizce varsayılmaz; çağıran kod açıkça ürün ve oran verir.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


@dataclass(frozen=True)
class FiyatLimiti:
    onceki_kapanis: Decimal
    alt_limit: Decimal
    ust_limit: Decimal
    fiyat_adimi: Decimal
    oran: Decimal
    kural_surumu: str


# Pay Piyasası fiyat adımı tablosu. Üst sınır hariçtir.
_PAY_ADIMLARI = (
    (Decimal("20"), Decimal("0.01")),
    (Decimal("50"), Decimal("0.02")),
    (Decimal("100"), Decimal("0.05")),
    (Decimal("250"), Decimal("0.10")),
    (Decimal("500"), Decimal("0.25")),
    (Decimal("1000"), Decimal("0.50")),
    (Decimal("Infinity"), Decimal("1.00")),
)


def fiyat_adimi(fiyat: float | Decimal, tarih: date | None = None, urun: str = "PAY") -> Decimal:
    """İlgili fiyat seviyesindeki geçerli kotasyon adımını döndürür."""
    value = Decimal(str(fiyat))
    if urun.upper() != "PAY":
        raise ValueError(f"Desteklenmeyen ürün türü: {urun}")
    if value <= 0:
        raise ValueError("Fiyat sıfırdan büyük olmalıdır")
    for upper, step in _PAY_ADIMLARI:
        if value < upper:
            return step
    raise AssertionError("Fiyat adımı bulunamadı")


def _adima_yuvarla(value: Decimal, step: Decimal, direction: str) -> Decimal:
    rounding = ROUND_FLOOR if direction == "down" else ROUND_CEILING
    return (value / step).to_integral_value(rounding=rounding) * step


def pay_fiyat_limitleri(
    onceki_kapanis: float | Decimal,
    tarih: date | None = None,
    limit_orani: float | Decimal = Decimal("0.10"),
) -> FiyatLimiti:
    """Önceki kapanış, pay limit oranı ve fiyat adımıyla alt/üst limiti hesaplar."""
    close = Decimal(str(onceki_kapanis))
    ratio = Decimal(str(limit_orani))
    if close <= 0 or not (Decimal("0") < ratio < Decimal("1")):
        raise ValueError("Geçerli kapanış ve 0-1 arasında limit oranı gerekir")
    raw_upper, raw_lower = close * (1 + ratio), close * (1 - ratio)
    upper_step = fiyat_adimi(raw_upper, tarih)
    lower_step = fiyat_adimi(raw_lower, tarih)
    upper = _adima_yuvarla(raw_upper, upper_step, "down")
    lower = _adima_yuvarla(raw_lower, lower_step, "up")
    return FiyatLimiti(close, lower, upper, upper_step, ratio, "BIST-PAY-2026.1")

