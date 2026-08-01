"""Merkezi, onbellekli piyasa verisi katmani."""
from __future__ import annotations

import io
import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import pandas as pd
import yfinance as yf

from bist_bulteni import resmi_gunluk_satir

_LOCK = threading.RLock()


def uygulama_klasoru() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    path = root / "BorsaAnalizProMAX"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _baglanti() -> sqlite3.Connection:
    db = sqlite3.connect(uygulama_klasoru() / "piyasa_verisi.sqlite3", timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS fiyat_cache (
        cache_key TEXT PRIMARY KEY, sembol TEXT NOT NULL, periyot TEXT NOT NULL,
        aralik TEXT NOT NULL, kaynak TEXT NOT NULL, alis_zamani INTEGER NOT NULL,
        son_veri_tarihi TEXT, veri_json TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS veri_olaylari (
        id INTEGER PRIMARY KEY AUTOINCREMENT, zaman INTEGER NOT NULL,
        sembol TEXT, kaynak TEXT, durum TEXT NOT NULL, detay TEXT)""")
    return db


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    gerekli = ["Open", "High", "Low", "Close"]
    if any(c not in out.columns for c in gerekli):
        return pd.DataFrame()
    if "Volume" not in out.columns:
        out["Volume"] = 0.0
    for c in gerekli + ["Volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.DatetimeIndex(out.index.as_unit("ns").values)
    out = out.dropna(subset=gerekli)
    out = out[(out[gerekli] > 0).all(axis=1)]
    return out[~out.index.duplicated(keep="last")].sort_index()


def _ttl(interval: str) -> int:
    return 300 if interval not in {"1d", "1wk", "1mo"} else 1800


def _oku(key: str, max_age: int | None) -> pd.DataFrame:
    with _LOCK, closing(_baglanti()) as db:
        row = db.execute("SELECT alis_zamani, veri_json, kaynak FROM fiyat_cache WHERE cache_key=?", (key,)).fetchone()
    if not row or (max_age is not None and time.time() - row[0] > max_age):
        return pd.DataFrame()
    try:
        df = _normalize(pd.read_json(io.StringIO(row[1]), orient="table"))
        df.attrs["veri_kaynagi"] = row[2]
        return df
    except Exception:
        return pd.DataFrame()


def _kaydet(key: str, symbol: str, period: str, interval: str, df: pd.DataFrame, kaynak: str) -> None:
    with _LOCK, closing(_baglanti()) as db:
        db.execute("INSERT OR REPLACE INTO fiyat_cache VALUES (?,?,?,?,?,?,?,?)", (
            key, symbol, period, interval, kaynak, int(time.time()),
            str(df.index[-1]), df.to_json(orient="table", date_format="iso")))
        db.commit()


def _olay(symbol: str, durum: str, detay: str = "") -> None:
    try:
        with _LOCK, closing(_baglanti()) as db:
            db.execute("INSERT INTO veri_olaylari(zaman,sembol,kaynak,durum,detay) VALUES(?,?,?,?,?)",
                       (int(time.time()), symbol, "yahoo", durum, detay[:1000]))
            db.commit()
    except Exception:
        pass


def _bist_ile_birlestir(symbol: str, interval: str, df: pd.DataFrame) -> pd.DataFrame:
    """Günlük Yahoo serisini son resmî BIST bülteniyle tamamlar veya düzeltir."""
    if interval != "1d" or not symbol.upper().endswith(".IS") or df.empty:
        return df
    try:
        resmi = resmi_gunluk_satir(symbol, uygulama_klasoru())
        if resmi.empty:
            return df
        sonuc = df.copy()
        tarih = resmi.index[-1]
        onceki = None
        yeni_tarih = tarih not in sonuc.index
        if tarih in sonuc.index:
            onceki = float(sonuc.loc[tarih, "Close"])
        for sutun in resmi.columns:
            sonuc.loc[tarih, sutun] = resmi.iloc[-1][sutun]
        sonuc = _normalize(sonuc)
        sonuc.attrs["veri_kaynagi"] = "Yahoo tarihsel + Borsa İstanbul resmî kapanış"
        sonuc.attrs["bist_bulten_tarihi"] = tarih.strftime("%Y-%m-%d")
        uyusmazlik = onceki is not None and abs(onceki - float(resmi.iloc[-1]["Close"])) > 0.001
        if uyusmazlik:
            sonuc.attrs["veri_uyusmazligi"] = f"Yahoo {onceki:.2f} / BIST {float(resmi.iloc[-1]['Close']):.2f}"
        if yeni_tarih or uyusmazlik:
            _olay(symbol, "BIST_DOGRULANDI", f"{tarih:%Y-%m-%d} kapanış={float(resmi.iloc[-1]['Close']):.2f}")
        return sonuc
    except Exception as exc:
        df.attrs["veri_kaynagi"] = df.attrs.get("veri_kaynagi", "Yahoo Finance (BIST bülteni alınamadı)")
        _olay(symbol, "BIST_BULTEN_HATA", str(exc))
        return df


def download(symbol: str, period: str = "1mo", interval: str = "1d", **kwargs) -> pd.DataFrame:
    """yfinance.download uyumlu, kalite kontrollu ve onbellekli indirme."""
    key = json.dumps([symbol, period, interval], ensure_ascii=False)
    cached = _oku(key, _ttl(interval))
    if not cached.empty:
        birlesik = _bist_ile_birlestir(symbol, interval, cached)
        if len(birlesik) != len(cached) or birlesik.attrs.get("veri_kaynagi") != cached.attrs.get("veri_kaynagi"):
            _kaydet(key, symbol, period, interval, birlesik, birlesik.attrs.get("veri_kaynagi", "yahoo+bist"))
        return birlesik.copy()
    try:
        raw = yf.download(symbol, period=period, interval=interval,
                          progress=kwargs.get("progress", False),
                          auto_adjust=kwargs.get("auto_adjust", False),
                          threads=kwargs.get("threads", False),
                          timeout=kwargs.get("timeout", 20))
        df = _normalize(raw)
        if df.empty:
            raise ValueError("Saglayici bos veya gecersiz OHLC verisi dondurdu")
        df.attrs["veri_kaynagi"] = "Yahoo Finance"
        df = _bist_ile_birlestir(symbol, interval, df)
        _kaydet(key, symbol, period, interval, df, df.attrs.get("veri_kaynagi", "yahoo"))
        _olay(symbol, "BASARILI", f"{len(df)} satir")
        return df.copy()
    except Exception as exc:
        stale = _oku(key, None)
        _olay(symbol, "YEDEK_CACHE" if not stale.empty else "HATA", str(exc))
        if not stale.empty:
            return stale.copy()
        raise


class _YahooUyumlu:
    download = staticmethod(download)
    Ticker = yf.Ticker  # fiyat disi temel/haber verileri gecici olarak Yahoo'da


veri = _YahooUyumlu()


def cache_bilgisi() -> dict:
    with _LOCK, closing(_baglanti()) as db:
        adet, son = db.execute("SELECT COUNT(*), MAX(alis_zamani) FROM fiyat_cache").fetchone()
    return {"kaynak": "Yahoo tarihsel + Borsa İstanbul resmî kapanış", "kayit": adet, "son_guncelleme": son}
