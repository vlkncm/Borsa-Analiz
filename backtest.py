from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import yfinance as yf


def rsi_hesapla(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def macd_hesapla(df):
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def atr_hesapla(df, period=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return atr


def backtest_hisse(
    symbol: str,
    period: str = "5y",
    holding_days: int = 20,
    hedef_katsayi: float = 2.0,
    stop_katsayi: float = 1.5
):
    """
    Basit sinyal testi:
    AL sinyali = fiyat EMA20 > EMA50, MACD pozitif, RSI 45-68 arası.
    Çıkış = önce hedef veya stop tetiklenirse oradan çıkar; yoksa holding_days sonunda çıkar.
    """
    try:
        df = yf.download(
            symbol,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 260:
            return None

        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()

        df["RSI"] = rsi_hesapla(df)
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["MACD"], df["MACD_SIGNAL"] = macd_hesapla(df)
        df["ATR"] = atr_hesapla(df)

        islemler = []
        i = 60

        while i < len(df) - holding_days - 1:
            row = df.iloc[i]
            prev = df.iloc[i - 1]

            price = float(row["Close"])
            rsi = float(row["RSI"])
            ema20 = float(row["EMA20"])
            ema50 = float(row["EMA50"])
            macd = float(row["MACD"])
            macd_signal = float(row["MACD_SIGNAL"])
            atr = float(row["ATR"]) if not math.isnan(float(row["ATR"])) else price * 0.03

            sinyal = (
                price > ema20 > ema50 and
                macd > macd_signal and
                45 <= rsi <= 68
            )

            yeni_macd_kesisim = (
                float(prev["MACD"]) <= float(prev["MACD_SIGNAL"]) and
                macd > macd_signal
            )

            if sinyal and yeni_macd_kesisim:
                giris_tarih = df.index[i]
                giris = price
                stop = giris - (atr * stop_katsayi)
                hedef = giris + ((giris - stop) * hedef_katsayi)

                cikis = None
                cikis_tarih = None
                sonuc = "SÜRE SONU"

                for j in range(i + 1, min(i + holding_days + 1, len(df))):
                    high = float(df.iloc[j]["High"])
                    low = float(df.iloc[j]["Low"])
                    close = float(df.iloc[j]["Close"])

                    if low <= stop:
                        cikis = stop
                        cikis_tarih = df.index[j]
                        sonuc = "STOP"
                        break

                    if high >= hedef:
                        cikis = hedef
                        cikis_tarih = df.index[j]
                        sonuc = "HEDEF"
                        break

                    cikis = close
                    cikis_tarih = df.index[j]

                getiri = ((cikis - giris) / giris) * 100 if giris > 0 else 0

                islemler.append({
                    "Hisse": symbol,
                    "Giriş Tarihi": giris_tarih.strftime("%Y-%m-%d"),
                    "Çıkış Tarihi": cikis_tarih.strftime("%Y-%m-%d") if cikis_tarih is not None else "",
                    "Giriş": round(giris, 2),
                    "Çıkış": round(cikis, 2),
                    "Stop": round(stop, 2),
                    "Hedef": round(hedef, 2),
                    "Sonuç": sonuc,
                    "Getiri %": round(getiri, 2),
                    "Holding Gün": holding_days
                })

                # Aynı sinyal üst üste işlem açmasın diye çıkış sonrasına atla
                i += holding_days
            else:
                i += 1

        if not islemler:
            return {
                "ozet": {
                    "Hisse": symbol,
                    "İşlem Sayısı": 0,
                    "Başarı %": 0,
                    "Ortalama Getiri %": 0,
                    "Toplam Getiri %": 0,
                    "En İyi İşlem %": 0,
                    "En Kötü İşlem %": 0,
                    "Hedef Sayısı": 0,
                    "Stop Sayısı": 0
                },
                "islemler": []
            }

        islem_df = pd.DataFrame(islemler)
        hedef_sayisi = int((islem_df["Sonuç"] == "HEDEF").sum())
        stop_sayisi = int((islem_df["Sonuç"] == "STOP").sum())
        kazanan = int((islem_df["Getiri %"] > 0).sum())
        toplam = len(islem_df)

        ozet = {
            "Hisse": symbol,
            "İşlem Sayısı": toplam,
            "Başarı %": round((kazanan / toplam) * 100, 2) if toplam else 0,
            "Ortalama Getiri %": round(float(islem_df["Getiri %"].mean()), 2),
            "Toplam Getiri %": round(float(islem_df["Getiri %"].sum()), 2),
            "En İyi İşlem %": round(float(islem_df["Getiri %"].max()), 2),
            "En Kötü İşlem %": round(float(islem_df["Getiri %"].min()), 2),
            "Hedef Sayısı": hedef_sayisi,
            "Stop Sayısı": stop_sayisi
        }

        return {
            "ozet": ozet,
            "islemler": islemler
        }

    except Exception as e:
        return {
            "ozet": {
                "Hisse": symbol,
                "İşlem Sayısı": 0,
                "Başarı %": 0,
                "Ortalama Getiri %": 0,
                "Toplam Getiri %": 0,
                "En İyi İşlem %": 0,
                "En Kötü İşlem %": 0,
                "Hedef Sayısı": 0,
                "Stop Sayısı": 0,
                "Hata": str(e)
            },
            "islemler": []
        }


def backtest_toplu(hisseler, max_hisse=40):
    """
    Performans için ilk etapta en fazla max_hisse test edilir.
    Daha sonra istersen bunu 613'e çıkarabiliriz ama uzun sürer.
    """
    ozetler = []
    tum_islemler = []

    for i, symbol in enumerate(hisseler[:max_hisse], start=1):
        print(f"Backtest {i}/{min(len(hisseler), max_hisse)}: {symbol}")
        sonuc = backtest_hisse(symbol)

        if sonuc:
            ozetler.append(sonuc["ozet"])
            tum_islemler.extend(sonuc["islemler"])

    ozet_df = pd.DataFrame(ozetler)
    islem_df = pd.DataFrame(tum_islemler)

    if not ozet_df.empty:
        ozet_df = ozet_df.sort_values(
            ["Başarı %", "Ortalama Getiri %", "İşlem Sayısı"],
            ascending=[False, False, False]
        )

    return ozet_df, islem_df
