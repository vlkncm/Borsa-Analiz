"""Merkezi, onbellekli piyasa verisi katmani."""
from __future__ import annotations

import io
import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from bist_bulteni import resmi_gunluk_satir
from sembol_esleme import saglayici_sembolu

_LOCK = threading.RLock()
ISTANBUL = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class VeriMetadatasi:
    source: str
    fetched_at: datetime
    last_bar_at: datetime | None
    symbol: str = ""
    first_bar_at: datetime | None = None
    exchange_timezone: str = "Europe/Istanbul"
    interval: str = "1d"
    is_delayed: bool | None = None
    delay_minutes: float | None = None
    is_stale: bool = True
    is_complete_bar: bool = False
    price_basis: str = "raw"
    official_close_verified: bool = False
    corporate_action_warning: bool = False

    def dict(self) -> dict:
        return asdict(self)


class PiyasaVeriAdapteri(Protocol):
    def get_daily_ohlcv(self, symbol: str, period: str = "6mo") -> tuple[pd.DataFrame, VeriMetadatasi]: ...
    def get_intraday_ohlcv(self, symbol: str, interval: str = "15m", period: str = "5d") -> tuple[pd.DataFrame, VeriMetadatasi]: ...


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
    input_rows = len(out)
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
    nan_rows = int(out[gerekli].isna().any(axis=1).sum())
    out = out.dropna(subset=gerekli)
    invalid_price = ~(out[gerekli] > 0).all(axis=1)
    invalid_volume = out["Volume"].notna() & out["Volume"].lt(0)
    invalid_ohlc = ((out["High"] < out[["Open", "Close"]].max(axis=1))
                    | (out["Low"] > out[["Open", "Close"]].min(axis=1))
                    | (out["High"] < out["Low"]))
    out = out[~(invalid_price | invalid_volume | invalid_ohlc)]
    duplicates = int(out.index.duplicated(keep="last").sum())
    out = out[~out.index.duplicated(keep="last")].sort_index()
    ratios = out["Close"].pct_change(fill_method=None).add(1).replace([float("inf"), float("-inf")], pd.NA)
    corporate_warning = bool(((ratios > 3) | (ratios < 1/3)).fillna(False).any())
    out.attrs["quality_report"] = {"input_rows": input_rows, "output_rows": len(out),
                                   "nan_rows": nan_rows, "invalid_price_rows": int(invalid_price.sum()),
                                   "invalid_volume_rows": int(invalid_volume.sum()),
                                   "invalid_ohlc_rows": int(invalid_ohlc.sum()), "duplicate_rows": duplicates}
    out.attrs["corporate_action_warning"] = corporate_warning
    return out


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
    symbol = saglayici_sembolu(symbol, "yahoo")
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


def _istanbul_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
        out = out[~out.index.isna()]
    if out.index.tz is None:
        out.index = out.index.tz_localize(ISTANBUL)
    else:
        out.index = out.index.tz_convert(ISTANBUL)
    return out


def _interval_dakika(interval: str) -> int:
    return {"5m": 5, "15m": 15}.get(interval, 15)


class YahooPiyasaVeriAdapteri:
    """Ücretsiz Yahoo verisini gecikmeli/bilinmeyen gecikmeli olarak açıkça etiketler."""

    source = "Yahoo Finance (ücretsiz; gecikme garantisi yok)"

    def get_daily_ohlcv(self, symbol: str, period: str = "6mo") -> tuple[pd.DataFrame, VeriMetadatasi]:
        symbol = saglayici_sembolu(symbol, "yahoo")
        fetched = datetime.now(ISTANBUL)
        frame = download(symbol, period=period, interval="1d", progress=False, auto_adjust=False)
        frame = _istanbul_index(frame)
        last = frame.index[-1].to_pydatetime() if not frame.empty else None
        meta = VeriMetadatasi(
            source=frame.attrs.get("veri_kaynagi", self.source), fetched_at=fetched,
            last_bar_at=last, symbol=symbol, first_bar_at=(frame.index[0].to_pydatetime() if not frame.empty else None),
            interval="1d", is_delayed=True, delay_minutes=None,
            is_stale=frame.empty or last is None or (fetched.date() - last.date()).days > 4,
            is_complete_bar=True, price_basis="raw",
            official_close_verified="Borsa" in frame.attrs.get("veri_kaynagi", ""),
            corporate_action_warning=bool(frame.attrs.get("corporate_action_warning", False)),
        )
        return frame, meta

    def get_intraday_ohlcv(self, symbol: str, interval: str = "15m", period: str = "5d") -> tuple[pd.DataFrame, VeriMetadatasi]:
        symbol = saglayici_sembolu(symbol, "yahoo")
        if interval not in {"5m", "15m"}:
            raise ValueError("Intraday aralık yalnızca 5m veya 15m olabilir")
        fetched = datetime.now(ISTANBUL)
        # Intraday işlem adayı eski cache'den üretilmez; kaynak hatası doğrudan üst katmana taşınır.
        raw = yf.download(symbol, period=period, interval=interval, progress=False,
                          auto_adjust=False, threads=False, timeout=20)
        frame = _istanbul_index(_normalize(raw))
        if frame.empty:
            raise ValueError("Intraday sağlayıcı boş veya geçersiz OHLCV döndürdü")
        minutes = _interval_dakika(interval)
        last = frame.index[-1].to_pydatetime()
        last_complete = fetched >= last + timedelta(minutes=minutes)
        frame["is_complete_bar"] = True
        if not last_complete:
            frame.iloc[-1, frame.columns.get_loc("is_complete_bar")] = False
        completed = frame[frame["is_complete_bar"]].copy()
        last_completed = completed.index[-1].to_pydatetime() if not completed.empty else None
        delay = None if last_completed is None else max(0.0, (fetched-last_completed).total_seconds()/60.0-minutes)
        same_session = last_completed is not None and last_completed.date() == fetched.date()
        # Seans sırasında 2 barı aşan yaş eskidir. Seans dışında son işlem günü verisi plan amaçlıdır.
        in_session = fetched.weekday() < 5 and ((10, 0) <= (fetched.hour, fetched.minute) <= (18, 15))
        stale = not same_session if in_session else completed.empty
        if in_session and delay is not None:
            stale = stale or delay > minutes * 2
        meta = VeriMetadatasi(
            source=self.source, fetched_at=fetched, last_bar_at=last_completed,
            symbol=symbol, first_bar_at=(completed.index[0].to_pydatetime() if not completed.empty else None),
            interval=interval,
            is_delayed=True, delay_minutes=delay, is_stale=stale,
            is_complete_bar=last_complete, price_basis="raw",
            corporate_action_warning=bool(frame.attrs.get("corporate_action_warning", False)),
        )
        return completed, meta


class HistoricalDataProvider(YahooPiyasaVeriAdapteri):
    """Gecmis/aksam analizi; canli teyit yetkisi yoktur."""


class DelayedDataProvider(YahooPiyasaVeriAdapteri):
    """Gecikmesi garanti edilemeyen ucretsiz intraday saglayici."""


class RealtimeDataProvider:
    """Lisansli gercek zamanli saglayicilar icin degistirilebilir adaptör sözlesmesi."""
    source = "YAPILANDIRILMADI"

    def get_daily_ohlcv(self, symbol: str, period: str = "6mo"):
        raise RuntimeError("Lisansli RealtimeDataProvider yapilandirilmadi")

    def get_intraday_ohlcv(self, symbol: str, interval: str = "15m", period: str = "5d"):
        raise RuntimeError("Gercek zamanli veri yok; canli teyit kapali")


_VARSAYILAN_ADAPTER: PiyasaVeriAdapteri = YahooPiyasaVeriAdapteri()


def get_daily_ohlcv(symbol: str, period: str = "6mo", adapter: PiyasaVeriAdapteri | None = None):
    return (adapter or _VARSAYILAN_ADAPTER).get_daily_ohlcv(symbol, period)


def get_intraday_ohlcv(symbol: str, interval: str = "15m", period: str = "5d",
                       adapter: PiyasaVeriAdapteri | None = None):
    return (adapter or _VARSAYILAN_ADAPTER).get_intraday_ohlcv(symbol, interval, period)
