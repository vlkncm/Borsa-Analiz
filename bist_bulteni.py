"""Borsa İstanbul Pay Piyasası günlük bülten istemcisi."""
from __future__ import annotations

import io
import json
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

_LOCK = threading.RLock()
_BELLEK: dict[str, object] = {}
_URL = "https://www.borsaistanbul.com/data/thb/{yil}/{ay}/thb{tarih}1.zip"
_CACHE_FILE = "bist_son_bulten.json"


def _sembol_duzelt(symbol: str) -> str:
    return symbol.upper().removesuffix(".IS").removesuffix(".E")


def bulten_zip_coz(icerik: bytes) -> tuple[date, dict[str, dict[str, float]]]:
    """Resmî THB ZIP/CSV içeriğini sade OHLCV sözlüğüne dönüştürür."""
    with zipfile.ZipFile(io.BytesIO(icerik)) as arsiv:
        csv_adlari = [ad for ad in arsiv.namelist() if ad.lower().endswith(".csv")]
        if not csv_adlari:
            raise ValueError("Bültende CSV dosyası bulunamadı")
        ham = arsiv.read(csv_adlari[0])

    metin = ham.decode("utf-8-sig")
    tablo = pd.read_csv(io.StringIO(metin), sep=";", dtype=str)
    if tablo.empty:
        raise ValueError("Bülten tablosu boş")

    # İlk veri satırı, aynı sütunların İngilizce açıklamasıdır.
    tablo = tablo[pd.to_datetime(tablo["TARIH"], format="%Y-%m-%d", errors="coerce").notna()].copy()
    if tablo.empty:
        raise ValueError("Bültende tarihli işlem satırı bulunamadı")

    bulten_tarihi = pd.to_datetime(tablo["TARIH"].iloc[0]).date()
    sonuc: dict[str, dict[str, float]] = {}
    alanlar = {
        "ACILIS FIYATI": "Open",
        "EN YUKSEK FIYAT": "High",
        "EN DUSUK FIYAT": "Low",
        "KAPANIS FIYATI": "Close",
        "TOPLAM ISLEM ADEDI": "Volume",
    }
    for _, satir in tablo.iterrows():
        kod = str(satir.get("ISLEM  KODU", "")).strip().upper()
        if not kod.endswith(".E"):
            continue
        degerler: dict[str, float] = {}
        for kaynak, hedef in alanlar.items():
            deger = pd.to_numeric(satir.get(kaynak), errors="coerce")
            if pd.isna(deger):
                break
            degerler[hedef] = float(deger)
        if len(degerler) == len(alanlar) and all(degerler[a] > 0 for a in ("Open", "High", "Low", "Close")):
            sonuc[_sembol_duzelt(kod)] = degerler
    if not sonuc:
        raise ValueError("Bültende geçerli hisse OHLCV verisi bulunamadı")
    return bulten_tarihi, sonuc


def _cache_yaz(cache_dir: Path, bulten_tarihi: date, hisseler: dict[str, dict[str, float]]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    gecici = cache_dir / f"{_CACHE_FILE}.tmp"
    gecici.write_text(
        json.dumps({"tarih": bulten_tarihi.isoformat(), "hisseler": hisseler}, ensure_ascii=False),
        encoding="utf-8",
    )
    gecici.replace(cache_dir / _CACHE_FILE)


def _cache_oku(cache_dir: Path) -> tuple[date, dict[str, dict[str, float]]] | None:
    try:
        veri = json.loads((cache_dir / _CACHE_FILE).read_text(encoding="utf-8"))
        return date.fromisoformat(veri["tarih"]), veri["hisseler"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def son_bulten(cache_dir: Path, bugun: date | None = None, timeout: int = 10) -> tuple[date, dict[str, dict[str, float]]]:
    """Son erişilebilir resmî bülteni indirir; ağ yoksa yerel son bülteni döndürür."""
    referans = bugun or datetime.now().date()
    # Uygulama gece boyunca açık kalırsa yeni günün bültenini yeniden dene.
    bellek_anahtari = f"{cache_dir.resolve()}|{referans.isoformat()}"
    with _LOCK:
        bellek = _BELLEK.get(bellek_anahtari)
        if bellek:
            return bellek  # type: ignore[return-value]

        yerel = _cache_oku(cache_dir)
        # Bugünün veya en yakın önceki işlem gününün bültenini bul.
        son_hata: Exception | None = None
        for gun_farki in range(0, 11):
            aday = referans - timedelta(days=gun_farki)
            if aday.weekday() >= 5:
                continue
            url = _URL.format(yil=aday.strftime("%Y"), ay=aday.strftime("%m"), tarih=aday.strftime("%Y%m%d"))
            try:
                yanit = requests.get(url, timeout=timeout)
                if yanit.status_code == 404:
                    continue
                yanit.raise_for_status()
                veri = bulten_zip_coz(yanit.content)
                _cache_yaz(cache_dir, *veri)
                _BELLEK[bellek_anahtari] = veri
                return veri
            except (requests.RequestException, ValueError, zipfile.BadZipFile) as exc:
                son_hata = exc
                break

        if yerel:
            _BELLEK[bellek_anahtari] = yerel
            return yerel
        raise RuntimeError(f"Borsa İstanbul günlük bülteni alınamadı: {son_hata or 'dosya bulunamadı'}")


def resmi_gunluk_satir(symbol: str, cache_dir: Path) -> pd.DataFrame:
    """Sembolün son resmî günlük OHLCV satırını yfinance biçiminde döndürür."""
    bulten_tarihi, hisseler = son_bulten(cache_dir)
    degerler = hisseler.get(_sembol_duzelt(symbol))
    if not degerler:
        return pd.DataFrame()
    satir = pd.DataFrame([degerler], index=pd.DatetimeIndex([pd.Timestamp(bulten_tarihi)]))
    satir["Adj Close"] = satir["Close"]
    satir.attrs["veri_kaynagi"] = "Borsa İstanbul resmî günlük bülteni"
    return satir
