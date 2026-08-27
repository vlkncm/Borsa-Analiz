"""Kisa fiyat gecmisine sahip yeni paylar icin aciklanabilir momentum yolu."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd

from fiyat_limitleri import pay_fiyat_limitleri
from sembol_esleme import bist_sembolu


@dataclass(frozen=True)
class YeniHalkaArzAyarlari:
    cok_yeni_son: int = 5
    yeni_son: int = 20
    sinirli_son: int = 60
    min_likit_islem_tutari: float = 5_000_000
    aday_puani: float = 55


AYARLAR = YeniHalkaArzAyarlari()

NEDEN_ACIKLAMALARI = {
    "INCLUDED_STANDARD": "Standart teknik modelle degerlendirildi",
    "INCLUDED_IPO": "Yeni halka arz/kisa gecmis modeliyle degerlendirildi",
    "REJECTED_LOW_SCORE": "Momentum puani aday esiginin altinda",
    "REJECTED_LIQUIDITY": "Islem tutari/likidite yetersiz",
    "REJECTED_HIGH_RISK": "Asiri hareket veya geri donus riski yuksek",
    "INSUFFICIENT_HISTORY": "Fiyat gecmisi sinirli",
    "MISSING_PRICE_DATA": "Gecerli fiyat verisi alinamadi",
    "SYMBOL_MAPPING_FAILED": "Veri alinamadi - sembol eslestirmesi kontrol edilmeli",
    "UNIVERSE_NOT_UPDATED": "Aktif BIST evreni guncellenemedi",
    "STALE_DATA": "Fiyat verisi guncel degil",
}


def model_yolu(session_count: int, settings: YeniHalkaArzAyarlari = AYARLAR) -> tuple[str, str]:
    if session_count <= settings.cok_yeni_son:
        return "YENI_HALKA_ARZ", "Cok yeni halka arz"
    if session_count <= settings.yeni_son:
        return "YENI_HALKA_ARZ", "Yeni halka arz"
    if session_count < settings.sinirli_son:
        return "YENI_HALKA_ARZ", "Sinirli gecmis"
    return "STANDART", "Standart analiz"


def _number(value, default=None):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _ipo_metadata(symbol: str, supplied: dict[str, Any] | None) -> dict[str, Any]:
    if supplied:
        return dict(supplied)
    try:
        from piyasa_guncelleme import cache_halka_arz_oku
        frame = cache_halka_arz_oku()
        if frame.empty:
            return {}
        code = bist_sembolu(symbol).kod
        symbol_col = next((c for c in frame if str(c).casefold() in {"kod", "hisse", "sembol", "borsa kodu"}), None)
        if not symbol_col:
            return {}
        normalized = frame[symbol_col].astype(str).str.upper().str.replace(".E", "", regex=False).str.replace(".IS", "", regex=False)
        rows = frame[normalized.eq(code)]
        return {} if rows.empty else rows.iloc[-1].to_dict()
    except Exception:
        return {}


def _meta_value(meta: dict, *names):
    lowered = {str(key).casefold(): value for key, value in meta.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value is not None and str(value).strip() not in {"", "nan", "None"}:
            return value
    return None


def yeni_halka_arz_analizi(
    symbol: str, frame: pd.DataFrame, regime: str = "VERI YETERSIZ",
    ipo_info: dict[str, Any] | None = None, kap: dict[str, Any] | None = None, as_of=None,
    settings: YeniHalkaArzAyarlari = AYARLAR,
) -> dict[str, Any]:
    """Yalniz karar anina kadar tamamlanmis OHLCV ile kisa-gecmis degerlendirmesi."""
    code = bist_sembolu(symbol).kod
    required = ["Open", "High", "Low", "Close", "Volume"]
    if frame is None or frame.empty or not set(required).issubset(frame.columns):
        return {"Hisse": code, "Model Yolu": "YENI_HALKA_ARZ", "Durum": "VERI ALINAMADI",
                "Neden Kodu": "MISSING_PRICE_DATA", "Eleme Nedeni": NEDEN_ACIKLAMALARI["MISSING_PRICE_DATA"]}
    work = frame.copy().sort_index()
    if as_of is not None:
        work = work.loc[work.index <= pd.Timestamp(as_of)]
    work = work[required].apply(pd.to_numeric, errors="coerce")
    work = work.dropna(subset=["Open", "High", "Low", "Close"])
    work = work[(work[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
    work = work[(work["High"] >= work[["Open", "Close"]].max(axis=1)) &
                (work["Low"] <= work[["Open", "Close"]].min(axis=1))]
    if work.empty:
        return {"Hisse": code, "Model Yolu": "YENI_HALKA_ARZ", "Durum": "VERI ALINAMADI",
                "Neden Kodu": "MISSING_PRICE_DATA", "Eleme Nedeni": NEDEN_ACIKLAMALARI["MISSING_PRICE_DATA"]}

    sessions = len(work)
    path, level = model_yolu(sessions, settings)
    if path == "STANDART":
        raise ValueError("60+ seans standart analiz yoluna gonderilmelidir")
    meta = _ipo_metadata(symbol, ipo_info)
    kap = kap or {}
    listing_raw = _meta_value(meta, "kotasyon_tarihi", "Kotasyon Tarihi", "Islem Tarihi", "İşlem Tarihi")
    listing_date = pd.to_datetime(listing_raw, errors="coerce")
    if pd.isna(listing_date):
        listing_date = pd.Timestamp(work.index[0])
    offer_price = _number(_meta_value(meta, "halka_arz_fiyati", "Halka Arz Fiyati", "Halka Arz Fiyatı"))

    close, high, low, opening = (work[c].astype(float) for c in ("Close", "High", "Low", "Open"))
    volume = work["Volume"].fillna(0).clip(lower=0).astype(float)
    price, previous = float(close.iloc[-1]), float(close.iloc[-2]) if sessions >= 2 else None
    day_return = None if previous is None else (price/previous-1)*100
    total_return = None if offer_price is None else (price/offer_price-1)*100
    close_location = float((price-low.iloc[-1])/(high.iloc[-1]-low.iloc[-1])) if high.iloc[-1] > low.iloc[-1] else .5
    opening_gap = None if previous is None else (opening.iloc[-1]/previous-1)*100
    prior_volume = volume.iloc[:-1]
    relative_volume = None if prior_volume.empty or prior_volume.mean() <= 0 else float(volume.iloc[-1]/prior_volume.mean())
    volume_trend = None if sessions < 3 else float(np.polyfit(np.arange(sessions), volume.to_numpy(), 1)[0])
    turnover = float((close*volume).mean())

    ceiling_hits, consecutive = [], 0
    for index in range(1, sessions):
        ceiling = float(pay_fiyat_limitleri(close.iloc[index-1]).ust_limit)
        hit = high.iloc[index] >= ceiling - 1e-8
        ceiling_hits.append(hit)
        consecutive = consecutive + 1 if hit else 0
    last_ceiling = float(pay_fiyat_limitleri(previous or price).ust_limit)
    hit_last = bool(sessions >= 2 and high.iloc[-1] >= last_ceiling-1e-8)
    ceiling_released = bool(hit_last and price < last_ceiling)
    intraday_reversal = float((high.iloc[-1]-price)/high.iloc[-1]*100) if high.iloc[-1] else None
    first_behavior = (price/close.iloc[0]-1)*100 if sessions > 1 else 0.0

    score, reasons, risks = 0.0, [], []
    if day_return is not None and day_return > 0: score += min(22, day_return*2); reasons.append("Pozitif son seans momentumu")
    if first_behavior > 0: score += min(18, first_behavior*.35); reasons.append("Ilk islem gununden beri pozitif fiyat davranisi")
    if close_location >= .75: score += 14; reasons.append("Kapanis gunluk araligin ust bolgesinde")
    if relative_volume is not None and relative_volume >= 1.15: score += min(16, 10+(relative_volume-1)*10); reasons.append("Kullanilabilir gecmise gore hacim artisi")
    if volume_trend is not None and volume_trend > 0: score += 8; reasons.append("Hacim egilimi pozitif")
    if turnover >= settings.min_likit_islem_tutari: score += 12
    else: risks.append("Cok dusuk likidite")
    if consecutive >= 3: risks.append("Tavan serisi sonrasi cozulme/giris riski")
    if ceiling_released or (intraday_reversal or 0) >= 3: risks.append("Gun icinde tavandan/zirveden geri donus")
    if day_return is not None and day_return >= 8: risks.append("Hareket baslamis; giris icin gec kalinmis olabilir")
    if sessions >= 3 and close.pct_change().dropna().std()*100 >= 7: risks.append("Yuksek oynaklik")
    if regime in {"RISKTEN KACIS", "RİSKTEN KAÇIŞ"}: risks.append("Piyasa riskten kacis rejiminde")
    if kap.get("kap_etiket") == "Olumlu": score += min(8, max(0, _number(kap.get("kap_skor"), 0))); reasons.append("Dogrulanmis olumlu KAP katalizoru")
    elif kap.get("kap_etiket") == "Olumsuz": score -= 20; risks.append("Negatif KAP aciklamasi")

    if turnover < settings.min_likit_islem_tutari:
        status, reason_code = "YUKSEK RISK", "REJECTED_LIQUIDITY"
    elif ceiling_released or consecutive >= 3 or (day_return or 0) >= 8:
        status, reason_code = "HAREKET KACTI - YUKSEK RISK", "REJECTED_HIGH_RISK"
    elif score >= settings.aday_puani:
        status, reason_code = "YENI HALKA ARZ MOMENTUM ADAYI", "INCLUDED_IPO"
    elif sessions <= settings.cok_yeni_son:
        status, reason_code = "CANLI TEYIT BEKLIYOR", "INSUFFICIENT_HISTORY"
    else:
        status, reason_code = "YENI HALKA ARZ - IZLE", "REJECTED_LOW_SCORE"

    missing = []
    if offer_price is None: missing.append("Halka arz fiyati")
    for label, names in (("Serbest dolasim", ("serbest_dolasim",)), ("Halka arz buyuklugu", ("halka_arz_buyuklugu",)),
                         ("Talep", ("talep",)), ("Yatirimci sayisi", ("yatirimci_sayisi",))):
        if _meta_value(meta, *names) is None: missing.append(label)
    missing.extend(["Canli emir dengesi", "Tavan alis miktari", "Tavana ulasma zamani", "Tavanda kalma suresi"])
    if kap.get("kap_etiket") in {None, "Veri Yok", "Hata"}: missing.append("Dogrulanmis KAP aciklamalari")
    limit = pay_fiyat_limitleri(price)
    return {
        "Hisse": code, "Kotasyon Tarihi": pd.Timestamp(listing_date).date().isoformat(),
        "İşlem Günü Sayısı": sessions, "Halka Arz Fiyatı": offer_price, "Güncel Fiyat": round(price, 2),
        "Halka Arzdan Beri Getiri %": None if total_return is None else round(total_return, 2),
        "Ardışık Tavan Sayısı": consecutive, "Günlük Değişim %": None if day_return is None else round(day_return, 2),
        "Göreceli Hacim": None if relative_volume is None else round(relative_volume, 2),
        "Tavan Fiyatı": float(limit.ust_limit), "Tavana Kalan %": round((float(limit.ust_limit)/price-1)*100, 2),
        "Momentum Durumu": status, "Risk Durumu": " | ".join(risks) if risks else "Belirgin ek risk yok",
        "Veri Yeterlilik Seviyesi": level, "Son Değerlendirme Zamanı": str(work.index[-1]),
        "Model Yolu": path, "Durum": status, "Neden Kodu": reason_code,
        "Eleme Nedeni": NEDEN_ACIKLAMALARI[reason_code], "Momentum Puani": round(min(100, score), 1),
        "Olasilik Notu": "Olasilik kalibre edilmedi - sinirli gecmis", "Olasilik Guvenilir": False,
        "Ozellik Kullanilabilirligi": {
            "ema20": sessions >= 20, "ema50": False, "ema200": False, "rsi14": sessions >= 14,
            "macd": sessions >= 26, "halka_arz_fiyati": offer_price is not None,
        },
        "Aday Nedenleri": reasons, "Riskler": risks, "Eksik Veriler": missing,
        "Önceki Kapanış": previous, "Kapanış Konumu": round(close_location, 3),
        "Açılış Boşluğu %": None if opening_gap is None else round(opening_gap, 2),
        "Tavan Çözüldü": ceiling_released, "Gün İçi Tavandan Geri Dönüş %": round(intraday_reversal or 0, 2),
        "Ortalama İşlem Tutarı": round(turnover, 2), "Piyasa Rejimi": regime,
        "Veri Zamanı": str(work.index[-1]),
    }
