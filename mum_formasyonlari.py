"""Ölçülebilir doji sınıflandırması, bağlamı ve teyidi."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import pandas as pd


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


def _mum_oranlari(row) -> dict[str, float] | None:
    o, h, l, c = map(_sayi, (row["Open"], row["High"], row["Low"], row["Close"]))
    if None in (o, h, l, c) or l <= 0 or h <= l or h < max(o, c) or l > min(o, c):
        return None
    size = h-l
    body = abs(c-o)
    return {"open": o, "high": h, "low": l, "close": c, "range": size, "body": body,
            "body_ratio": body/size, "upper": h-max(o, c), "lower": min(o, c)-l,
            "green": c > o, "red": c < o}


def mum_formasyonu_tespit(frame: pd.DataFrame, trend_bars: int = 5) -> dict[str, Any]:
    """Son tamamlanmış mumlarda tek/çok mumlu formasyonları öncelikli olarak bulur.

    Formasyon tek başına işlem kararı değildir. Trend bağlamı zorunludur ve sonuç
    günlük trade birleşik puanına sınırlı katkı verir.
    """
    empty = {"mum_formasyonu": "YOK", "mum_formasyon_yonu": "NÖTR",
             "mum_formasyon_teyit": False, "mum_formasyon_puani": 0, "mum_formasyon_nedeni": ""}
    if frame is None or len(frame) < trend_bars + 3:
        return {**empty, "mum_formasyon_nedeni": "Yetersiz mum"}
    data = frame[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < trend_bars + 3:
        return {**empty, "mum_formasyon_nedeni": "Geçersiz OHLCV"}
    a, b, c = (_mum_oranlari(data.iloc[-i]) for i in (3, 2, 1))
    if None in (a, b, c):
        return {**empty, "mum_formasyon_nedeni": "Geçersiz son mum"}
    prior = data["Close"].iloc[-(trend_bars+3):-3]
    trend_return = float(prior.iloc[-1]/prior.iloc[0]-1) if len(prior) >= 2 and prior.iloc[0] else 0.0
    downtrend, uptrend = trend_return <= -0.01, trend_return >= 0.01
    body_floor = max(c["body"], c["range"]*.02)
    hammer_shape = c["body_ratio"] <= .35 and c["lower"] >= 2*body_floor and c["upper"] <= body_floor

    def result(name, direction, score, reason, confirmed=True):
        return {"mum_formasyonu": name, "mum_formasyon_yonu": direction,
                "mum_formasyon_teyit": bool(confirmed), "mum_formasyon_puani": score,
                "mum_formasyon_nedeni": reason}

    # Üç mumlu ve iki mumlu formasyonlar daha özgül olduğu için önce değerlendirilir.
    midpoint_a = (a["open"]+a["close"])/2
    if downtrend and a["red"] and a["body_ratio"] >= .5 and b["body_ratio"] <= .35 and c["green"] \
            and c["body_ratio"] >= .5 and c["close"] > midpoint_a:
        return result("MORNING STAR (SABAH YILDIZI)", "YUKARI", 100, "Düşüş + kararsızlık + güçlü yükseliş")
    if downtrend and b["red"] and c["green"] and c["open"] <= b["close"] and c["close"] >= b["open"] \
            and c["body"] > b["body"]:
        return result("BULLISH ENGULFING (YÜKSELİŞ YUTMA)", "YUKARI", 90, "Yeşil gövde önceki kırmızı gövdeyi yuttu")
    if uptrend and b["green"] and c["red"] and c["open"] >= b["close"] and c["close"] <= b["open"] \
            and c["body"] > b["body"]:
        return result("BEARISH ENGULFING (DÜŞÜŞ YUTMA)", "AŞAĞI", -90, "Kırmızı gövde önceki yeşil gövdeyi yuttu")
    if hammer_shape and downtrend:
        return result("HAMMER (ÇEKİÇ)", "YUKARI", 70, "Düşüş sonunda küçük gövde ve en az 2× alt fitil", c["green"])
    if hammer_shape and uptrend:
        return result("HANGING MAN (ASILI ADAM)", "AŞAĞI", -70, "Yükseliş sonunda çekiç geometrisi", c["red"])
    doji = doji_siniflandir(c["open"], c["high"], c["low"], c["close"])
    if doji["tur"] == "MEZAR TAŞI DOJİ" and uptrend:
        return result("GRAVESTONE DOJI (MEZAR TAŞI DOJİ)", "AŞAĞI", -65, "Yükseliş sonrası uzun üst fitil", False)

    recent = data.tail(10)
    recent_width = float((recent["High"].max()-recent["Low"].min())/recent["Close"].mean())
    prior_widths = ((data["High"].rolling(10).max()-data["Low"].rolling(10).min()) /
                    data["Close"].rolling(10).mean()).dropna()
    threshold = float(prior_widths.quantile(.25)) if len(prior_widths) >= 20 else .04
    volume_ratio = float(data["Volume"].iloc[-1]/data["Volume"].iloc[-21:-1].median()) if len(data) >= 21 else 1.0
    if recent_width <= threshold:
        breakout = c["close"] >= float(recent["High"].iloc[:-1].max()) and volume_ratio >= 1.5
        return result("CORNERING (SIKIŞMA)", "YUKARI" if breakout else "NÖTR", 60 if breakout else 25,
                      f"10 bar bant %{recent_width*100:.2f}; hacim oranı {volume_ratio:.2f}", breakout)
    return empty
