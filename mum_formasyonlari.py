"""Ölçülebilir doji sınıflandırması, bağlamı ve teyidi."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True)
class DojiAyarlari:
    body_max: float = 0.10
    uzun_golge_min: float = 0.60
    kisa_golge_max: float = 0.10
    cift_golge_min: float = 0.30
    trend_min_hareket: float = 0.005


def _sayi(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def doji_siniflandir(open_: Any, high: Any, low: Any, close: Any,
                      ayarlar: DojiAyarlari | None = None) -> dict[str, Any]:
    """Bir mumu tek bir doji türüne atar; geçersiz mumda güvenli sonuç döndürür."""
    cfg = ayarlar or DojiAyarlari()
    o, h, l, c = map(_sayi, (open_, high, low, close))
    temel = {
        "tur": "DOJI DEĞİL", "gecerli": False, "body_ratio": None,
        "upper_ratio": None, "lower_ratio": None, "esikler": asdict(cfg), "neden": "",
    }
    if None in (o, h, l, c) or min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c) or h <= l:
        temel["neden"] = "Eksik, sıfır aralıklı veya geçersiz OHLC"
        return temel
    candle_range = h - l
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    body_ratio, upper_ratio, lower_ratio = body / candle_range, upper / candle_range, lower / candle_range
    temel.update(gecerli=True, body_ratio=body_ratio, upper_ratio=upper_ratio, lower_ratio=lower_ratio)
    if body_ratio > cfg.body_max:
        temel["neden"] = f"Gövde oranı {body_ratio:.3f}, doji eşiği {cfg.body_max:.3f} üzerinde"
        return temel
    # En özgül türlerden genel türe doğru sabit öncelik.
    if upper_ratio >= cfg.uzun_golge_min and lower_ratio <= cfg.kisa_golge_max:
        tur = "MEZAR TAŞI DOJİ"
    elif lower_ratio >= cfg.uzun_golge_min and upper_ratio <= cfg.kisa_golge_max:
        tur = "YUSUFÇUK DOJİ"
    elif upper_ratio >= cfg.cift_golge_min and lower_ratio >= cfg.cift_golge_min:
        tur = "UZUN BACAKLI DOJİ"
    else:
        tur = "STANDART DOJİ"
    temel.update(tur=tur, neden=(
        f"Gövde={body_ratio:.3f}, üst gölge={upper_ratio:.3f}, alt gölge={lower_ratio:.3f}"
    ))
    return temel


def doji_baglam_ve_teyit(doji: dict[str, Any], onceki_kapanislar,
                         doji_high: Any, doji_low: Any, sonraki_mum: dict[str, Any] | None,
                         ayarlar: DojiAyarlari | None = None) -> dict[str, Any]:
    """Dojiye trend bağlamı ve yalnızca tamamlanmış sonraki mumla yön teyidi ekler."""
    cfg = ayarlar or DojiAyarlari()
    tur = doji.get("tur", "DOJI DEĞİL")
    sonuc = {"baglam": "YOK", "teyit": False, "yon": "NÖTR", "durum": "İŞLEM YOK"}
    if "DOJİ" not in tur or tur == "DOJI DEĞİL":
        return sonuc
    kapanislar = [_sayi(x) for x in list(onceki_kapanislar or [])]
    kapanislar = [x for x in kapanislar if x is not None]
    trend = 0.0 if len(kapanislar) < 2 or kapanislar[0] == 0 else kapanislar[-1] / kapanislar[0] - 1
    if trend >= cfg.trend_min_hareket:
        sonuc["baglam"] = "YÜKSELİŞ"
    elif trend <= -cfg.trend_min_hareket:
        sonuc["baglam"] = "DÜŞÜŞ"
    if tur == "UZUN BACAKLI DOJİ":
        sonuc["baglam"] = "KARARSIZLIK"
    beklenen = ((tur == "YUSUFÇUK DOJİ" and sonuc["baglam"] == "DÜŞÜŞ") or
                (tur == "MEZAR TAŞI DOJİ" and sonuc["baglam"] == "YÜKSELİŞ") or
                tur == "UZUN BACAKLI DOJİ")
    if not beklenen:
        return sonuc
    sonuc["durum"] = "TEYİT BEKLE"
    if not sonraki_mum or not bool(sonraki_mum.get("is_complete_bar", False)):
        return sonuc
    close = _sayi(sonraki_mum.get("Close"))
    high, low = _sayi(doji_high), _sayi(doji_low)
    if None in (close, high, low):
        return sonuc
    if tur == "YUSUFÇUK DOJİ" and close > high:
        sonuc.update(teyit=True, yon="YUKARI", durum="TEYİTLİ")
    elif tur == "MEZAR TAŞI DOJİ" and close < low:
        sonuc.update(teyit=True, yon="AŞAĞI", durum="TEYİTLİ")
    elif tur == "UZUN BACAKLI DOJİ" and (close > high or close < low):
        sonuc.update(teyit=True, yon="YUKARI" if close > high else "AŞAĞI", durum="TEYİTLİ")
    return sonuc
