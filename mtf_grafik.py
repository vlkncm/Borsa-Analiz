from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Any, List, Tuple

import pandas as pd
from veri_saglayici import veri as yf

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


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

        for column in ["Open", "High", "Low", "Close", "Volume"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
        df["RSI"] = rsi_hesapla(df["Close"])
        df["MACD"], df["MACD_SINYAL"] = macd_hesapla(df["Close"])

        son = df.tail(120).copy()

        fiyat = guvenli_float(item.get("price", son["Close"].iloc[-1]))
        destek = guvenli_float(item.get("ana_destek", item.get("destek", 0)))
        direnc = guvenli_float(item.get("ana_direnc", item.get("direnc", 0)))
        stop = guvenli_float(item.get("stop_loss", 0))
        hedef1 = guvenli_float(item.get("hedef_1", 0))
        hedef2 = guvenli_float(item.get("hedef_2", 0))

        plt.style.use("dark_background")
        fig = plt.figure(figsize=(15, 10), facecolor="#020617")
        grid = fig.add_gridspec(5, 1, height_ratios=[5, 1.2, 1.5, 1.5, 0.15], hspace=0.08)
        ax = fig.add_subplot(grid[0])
        ax_volume = fig.add_subplot(grid[1], sharex=ax)
        ax_rsi = fig.add_subplot(grid[2], sharex=ax)
        ax_macd = fig.add_subplot(grid[3], sharex=ax)
        x = list(range(len(son)))

        for i, (_, candle) in enumerate(son.iterrows()):
            up = candle["Close"] >= candle["Open"]
            color = "#22c55e" if up else "#ef4444"
            ax.vlines(i, candle["Low"], candle["High"], color=color, linewidth=0.8)
            bottom = min(candle["Open"], candle["Close"])
            height = max(abs(candle["Close"] - candle["Open"]), max(candle["Close"] * 0.0005, 0.001))
            ax.add_patch(Rectangle((i - 0.32, bottom), 0.64, height, facecolor=color, edgecolor=color, linewidth=0.5))

        ax.plot(x, son["EMA20"], label="EMA20", linewidth=1.2, color="#38bdf8")
        ax.plot(x, son["EMA50"], label="EMA50", linewidth=1.2, color="#f59e0b")
        ax.plot(x, son["EMA200"], label="EMA200", linewidth=1.0, color="#a78bfa")

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
        ax.set_ylabel("Fiyat (TL)")
        ax.legend(loc="upper left", fontsize=8, ncol=4)
        ax.grid(True, alpha=0.15)

        volume_colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(son["Open"], son["Close"])]
        ax_volume.bar(x, son["Volume"].fillna(0), color=volume_colors, width=0.7, alpha=0.75)
        ax_volume.set_ylabel("Hacim", fontsize=8)
        ax_volume.grid(True, alpha=0.1)

        ax_rsi.plot(x, son["RSI"], color="#38bdf8", linewidth=1.1, label="RSI(14)")
        ax_rsi.axhline(70, color="#ef4444", linestyle="--", linewidth=0.8)
        ax_rsi.axhline(30, color="#22c55e", linestyle="--", linewidth=0.8)
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_ylabel("RSI")
        ax_rsi.grid(True, alpha=0.1)

        histogram = son["MACD"] - son["MACD_SINYAL"]
        macd_colors = ["#22c55e" if value >= 0 else "#ef4444" for value in histogram]
        ax_macd.bar(x, histogram, color=macd_colors, width=0.7, alpha=0.7)
        ax_macd.plot(x, son["MACD"], color="#38bdf8", linewidth=1.0, label="MACD")
        ax_macd.plot(x, son["MACD_SINYAL"], color="#f59e0b", linewidth=1.0, label="Sinyal")
        ax_macd.axhline(0, color="#64748b", linewidth=0.7)
        ax_macd.set_ylabel("MACD")
        ax_macd.legend(loc="upper left", fontsize=7, ncol=2)
        ax_macd.grid(True, alpha=0.1)

        tick_step = max(1, len(son) // 10)
        ticks = x[::tick_step]
        labels = [son.index[i].strftime("%d.%m.%y") for i in ticks]
        ax_macd.set_xticks(ticks)
        ax_macd.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        plt.setp(ax.get_xticklabels(), visible=False)
        plt.setp(ax_volume.get_xticklabels(), visible=False)
        plt.setp(ax_rsi.get_xticklabels(), visible=False)
        fig.tight_layout()

        path = out_dir / f"{symbol.replace('.', '_')}_grafik.png"
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

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
