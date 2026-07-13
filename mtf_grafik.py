from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Any, List, Tuple

import pandas as pd
import yfinance as yf

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def guvenli_float(x, default=0.0):
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def rsi_hesapla(close: pd.Series, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def macd_hesapla(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def timeframe_analiz(symbol: str, period: str, interval: str) -> Dict[str, Any]:
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 60:
            return {
                "yon": "Veri Yok",
                "skor": 50,
                "not": "Veri yetersiz"
            }

        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()

        close = df["Close"]
        price = guvenli_float(close.iloc[-1])
        ema20 = guvenli_float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = guvenli_float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        ema100 = guvenli_float(close.ewm(span=100, adjust=False).mean().iloc[-1]) if len(df) >= 100 else ema50

        rsi = guvenli_float(rsi_hesapla(close).iloc[-1], 50)
        macd, signal = macd_hesapla(close)
        macd_last = guvenli_float(macd.iloc[-1])
        signal_last = guvenli_float(signal.iloc[-1])
        ret_10 = guvenli_float(close.pct_change(10).iloc[-1] * 100)
        ret_30 = guvenli_float(close.pct_change(30).iloc[-1] * 100)

        skor = 50
        notlar = []

        if price > ema20:
            skor += 8
            notlar.append("Fiyat EMA20 üzerinde")
        else:
            skor -= 8
            notlar.append("Fiyat EMA20 altında")

        if ema20 > ema50:
            skor += 10
            notlar.append("EMA20 EMA50 üzerinde")
        else:
            skor -= 10
            notlar.append("EMA20 EMA50 altında")

        if price > ema100:
            skor += 6
            notlar.append("Fiyat uzun ortalama üzerinde")
        else:
            skor -= 6
            notlar.append("Fiyat uzun ortalama altında")

        if macd_last > signal_last:
            skor += 10
            notlar.append("MACD pozitif")
        else:
            skor -= 10
            notlar.append("MACD negatif")

        if 45 <= rsi <= 68:
            skor += 6
            notlar.append("RSI sağlıklı")
        elif rsi >= 72:
            skor -= 8
            notlar.append("RSI aşırı alım")
        elif rsi < 40:
            skor -= 6
            notlar.append("RSI zayıf")

        if ret_10 > 0:
            skor += 4
        else:
            skor -= 4

        if ret_30 > 0:
            skor += 6
        else:
            skor -= 6

        skor = max(0, min(100, int(round(skor))))

        if skor >= 65:
            yon = "AL"
        elif skor <= 40:
            yon = "SAT"
        else:
            yon = "TUT"

        return {
            "yon": yon,
            "skor": skor,
            "rsi": round(rsi, 2),
            "ret_10": round(ret_10, 2),
            "ret_30": round(ret_30, 2),
            "not": " | ".join(notlar)
        }

    except Exception as e:
        return {
            "yon": "Hata",
            "skor": 50,
            "not": str(e)
        }


def coklu_zaman_dilimi_analizi(symbol: str) -> Dict[str, Any]:
    """
    Ücretsiz ve hızlı olması için günlük + haftalık analiz yapar.
    İleride 1s/4s veri desteği de eklenebilir.
    """
    gunluk = timeframe_analiz(symbol, period="18mo", interval="1d")
    haftalik = timeframe_analiz(symbol, period="5y", interval="1wk")

    # Ağırlıklandırma: günlük %60, haftalık %40
    mtf_skor = int(round((gunluk.get("skor", 50) * 0.60) + (haftalik.get("skor", 50) * 0.40)))

    g_yon = gunluk.get("yon", "TUT")
    h_yon = haftalik.get("yon", "TUT")

    if g_yon == "AL" and h_yon == "AL":
        uyum = "Güçlü Uyum"
        mtf_karar = "AL"
    elif g_yon == "SAT" and h_yon == "SAT":
        uyum = "Negatif Uyum"
        mtf_karar = "SAT"
    elif g_yon == h_yon:
        uyum = "Orta Uyum"
        mtf_karar = g_yon
    else:
        uyum = "Zayıf Uyum"
        mtf_karar = "TUT"

    return {
        "mtf_skor": mtf_skor,
        "mtf_karar": mtf_karar,
        "mtf_uyum": uyum,
        "gunluk_yon": g_yon,
        "gunluk_skor": gunluk.get("skor", 50),
        "gunluk_not": gunluk.get("not", ""),
        "haftalik_yon": h_yon,
        "haftalik_skor": haftalik.get("skor", 50),
        "haftalik_not": haftalik.get("not", "")
    }


def grafik_olustur(symbol: str, item: Dict[str, Any], output_dir: str = "output/grafikler") -> str:
    """
    Fiyat + EMA + destek/direnç + stop/hedef grafiği üretir.
    """
    try:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        df = yf.download(
            symbol,
            period="9mo",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 60:
            return ""

        df = df.dropna(subset=["Close"]).copy()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        son = df.tail(140).copy()

        fiyat = guvenli_float(item.get("price", son["Close"].iloc[-1]))
        destek = guvenli_float(item.get("ana_destek", item.get("destek", 0)))
        direnc = guvenli_float(item.get("ana_direnc", item.get("direnc", 0)))
        stop = guvenli_float(item.get("stop_loss", 0))
        hedef1 = guvenli_float(item.get("hedef_1", 0))
        hedef2 = guvenli_float(item.get("hedef_2", 0))

        plt.figure(figsize=(13, 7))
        ax = plt.gca()

        ax.plot(son.index, son["Close"], label="Kapanış", linewidth=1.8)
        ax.plot(son.index, son["EMA20"], label="EMA20", linewidth=1.2)
        ax.plot(son.index, son["EMA50"], label="EMA50", linewidth=1.2)
        ax.plot(son.index, son["EMA200"], label="EMA200", linewidth=1.0)

        if destek > 0:
            ax.axhline(destek, linestyle="--", linewidth=1.2, label=f"Destek {destek:.2f}")
        if direnc > 0:
            ax.axhline(direnc, linestyle="--", linewidth=1.2, label=f"Direnç {direnc:.2f}")
        if stop > 0:
            ax.axhline(stop, linestyle=":", linewidth=1.4, label=f"Stop {stop:.2f}")
        if hedef1 > 0:
            ax.axhline(hedef1, linestyle=":", linewidth=1.4, label=f"Hedef 1 {hedef1:.2f}")
        if hedef2 > 0:
            ax.axhline(hedef2, linestyle=":", linewidth=1.4, label=f"Hedef 2 {hedef2:.2f}")

        baslik = (
            f"{symbol} | {item.get('broker_aksiyon', item.get('aksiyon', ''))} | "
            f"Broker Skor: {item.get('broker_skor', item.get('genel_skor', item.get('guven', 0)))} | "
            f"MTF: {item.get('mtf_karar', '')} {item.get('mtf_skor', '')}"
        )

        ax.set_title(baslik)
        ax.set_xlabel("Tarih")
        ax.set_ylabel("Fiyat")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.25)

        plt.tight_layout()

        path = out_dir / f"{symbol.replace('.', '_')}_grafik.png"
        plt.savefig(path, dpi=140)
        plt.close()

        return str(path)

    except Exception:
        try:
            plt.close()
        except Exception:
            pass
        return ""


def grafik_toplu_olustur(results: List[Dict[str, Any]], limit: int = 20, output_dir: str = "output/grafikler") -> Dict[str, str]:
    grafikler = {}

    for i, item in enumerate(results[:limit], start=1):
        symbol = item.get("symbol", "")
        print(f"Grafik oluşturuluyor {i}/{min(len(results), limit)}: {symbol}")
        path = grafik_olustur(symbol, item, output_dir=output_dir)
        grafikler[symbol] = path

    return grafikler
