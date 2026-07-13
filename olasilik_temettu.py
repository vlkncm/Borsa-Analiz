from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List
import math

import pandas as pd
import yfinance as yf


def guvenli_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _indir(symbol: str, period: str = "5y") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval="1d", progress=False,
                     auto_adjust=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return pd.DataFrame()
    return df.dropna(subset=["High", "Low", "Close"]).copy()


def tarihsel_olasilik_hesapla(symbol: str, hedef_1: float = 0.0,
                              stop_loss: float = 0.0) -> Dict[str, Any]:
    """5 yıllık geçmişten ampirik gerçekleşme oranları üretir; garanti değildir."""
    try:
        df = _indir(symbol, "5y")
        if df.empty or len(df) < 260:
            raise ValueError("veri yetersiz")

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        son_fiyat = guvenli_float(close.iloc[-1])
        hedef_oran = ((hedef_1 / son_fiyat) - 1) if hedef_1 > son_fiyat > 0 else None
        stop_oran = ((stop_loss / son_fiyat) - 1) if son_fiyat > stop_loss > 0 else None

        s5 = s10 = sz = sh = ss = n = 0
        s10_20 = s20_20 = s30_20 = 0
        s10_30 = s20_30 = s30_30 = 0

        for i in range(30, len(df) - 31):
            giris = guvenli_float(close.iloc[i])
            if giris <= 0:
                continue

            h5 = guvenli_float(high.iloc[i + 1:i + 6].max())
            h10 = guvenli_float(high.iloc[i + 1:i + 11].max())
            h20 = guvenli_float(high.iloc[i + 1:i + 21].max())
            h30 = guvenli_float(high.iloc[i + 1:i + 31].max())
            l10 = guvenli_float(low.iloc[i + 1:i + 11].min())
            prev20 = guvenli_float(high.iloc[i - 20:i].max())

            s5 += int(h5 >= giris * 1.10)
            s10 += int(h10 >= giris * 1.10)
            sz += int(h10 > prev20)
            sh += int(hedef_oran is not None and h10 >= giris * (1 + hedef_oran))
            ss += int(stop_oran is not None and l10 <= giris * (1 + stop_oran))

            s10_20 += int(h10 >= giris * 1.20)
            s20_20 += int(h20 >= giris * 1.20)
            s30_20 += int(h30 >= giris * 1.20)
            s10_30 += int(h10 >= giris * 1.30)
            s20_30 += int(h20 >= giris * 1.30)
            s30_30 += int(h30 >= giris * 1.30)
            n += 1

        if n == 0:
            raise ValueError("örnek yok")

        return {
            "olasilik_5g_10yukselis": round(s5 / n * 100, 2),
            "olasilik_10g_10yukselis": round(s10 / n * 100, 2),
            "olasilik_10g_yeni_zirve": round(sz / n * 100, 2),
            "olasilik_hedef1": round(sh / n * 100, 2) if hedef_oran is not None else 0.0,
            "olasilik_stop": round(ss / n * 100, 2) if stop_oran is not None else 0.0,
            "olasilik_10g_20yukselis": round(s10_20 / n * 100, 2),
            "olasilik_20g_20yukselis": round(s20_20 / n * 100, 2),
            "olasilik_30g_20yukselis": round(s30_20 / n * 100, 2),
            "olasilik_10g_30yukselis": round(s10_30 / n * 100, 2),
            "olasilik_20g_30yukselis": round(s20_30 / n * 100, 2),
            "olasilik_30g_30yukselis": round(s30_30 / n * 100, 2),
            "olasilik_ornek_sayisi": n,
            "olasilik_notu": "5 yıllık geçmiş veriden ampirik gerçekleşme oranı"
        }
    except Exception as exc:
        return {
            "olasilik_5g_10yukselis": 0.0,
            "olasilik_10g_10yukselis": 0.0,
            "olasilik_10g_yeni_zirve": 0.0,
            "olasilik_hedef1": 0.0,
            "olasilik_stop": 0.0,
            "olasilik_10g_20yukselis": 0.0,
            "olasilik_20g_20yukselis": 0.0,
            "olasilik_30g_20yukselis": 0.0,
            "olasilik_10g_30yukselis": 0.0,
            "olasilik_20g_30yukselis": 0.0,
            "olasilik_30g_30yukselis": 0.0,
            "olasilik_ornek_sayisi": 0,
            "olasilik_notu": f"Hesaplanamadı: {exc}"
        }

def olasilik_toplu_ekle(results: List[Dict[str, Any]], limit: int = 30) -> List[Dict[str, Any]]:
    secilen = results[:limit]
    by_symbol = {x.get("symbol"): x for x in secilen if x.get("symbol")}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(tarihsel_olasilik_hesapla, s,
                            guvenli_float(item.get("hedef_1")),
                            guvenli_float(item.get("stop_loss"))): s
            for s, item in by_symbol.items()
        }
        for i, future in enumerate(as_completed(futures), 1):
            symbol = futures[future]
            print(f"Olasılık analizi {i}/{len(futures)}: {symbol}")
            by_symbol[symbol].update(future.result())

    for item in results[limit:]:
        item.update({
            "olasilik_5g_10yukselis": 0.0,
            "olasilik_10g_10yukselis": 0.0,
            "olasilik_10g_yeni_zirve": 0.0,
            "olasilik_hedef1": 0.0,
            "olasilik_stop": 0.0,
            "olasilik_10g_20yukselis": 0.0,
            "olasilik_20g_20yukselis": 0.0,
            "olasilik_30g_20yukselis": 0.0,
            "olasilik_10g_30yukselis": 0.0,
            "olasilik_20g_30yukselis": 0.0,
            "olasilik_30g_30yukselis": 0.0,
            "olasilik_ornek_sayisi": 0,
            "olasilik_notu": f"Yalnızca ilk {limit} adaya uygulandı"
        })
    return results


def _tarih(value: Any) -> str:
    if value is None:
        return ""
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else ""
    except Exception:
        return ""


def temettu_bilgisi(symbol: str) -> Dict[str, Any]:
    try:
        ticker = yf.Ticker(symbol)
        upcoming = ""
        try:
            cal = ticker.calendar
            if isinstance(cal, dict):
                upcoming = _tarih(cal.get("Ex-Dividend Date") or cal.get("Dividend Date")
                                  or cal.get("exDividendDate") or cal.get("dividendDate"))
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                for key in ["Ex-Dividend Date", "Dividend Date"]:
                    if key in cal.index:
                        upcoming = _tarih(cal.loc[key].iloc[0])
                        break
        except Exception:
            pass

        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            pass

        div_rate = guvenli_float(info.get("dividendRate"))
        div_yield = guvenli_float(info.get("dividendYield"))
        if 0 < div_yield < 1:
            div_yield *= 100

        divs = ticker.dividends
        last_date = ""
        last_amount = 0.0
        count_5y = 0
        if isinstance(divs, pd.Series) and not divs.empty:
            last_date = _tarih(divs.index[-1])
            last_amount = guvenli_float(divs.iloc[-1])
            try:
                cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.DateOffset(years=5)
                count_5y = int((divs.index >= cutoff).sum())
            except Exception:
                count_5y = int(len(divs.tail(20)))

        status = "Duyuru bulunamadı"
        if upcoming:
            parsed = pd.to_datetime(upcoming, errors="coerce")
            if pd.notna(parsed) and parsed.date() >= datetime.now().date():
                status = "Yaklaşan temettü"
            else:
                status = "Takvim tarihi geçmiş olabilir"

        return {
            "Hisse": symbol,
            "Temettü Durumu": status,
            "Yaklaşan Temettü/Ex-Date": upcoming,
            "Yıllık Temettü Tutarı": round(div_rate, 4),
            "Temettü Verimi %": round(div_yield, 2),
            "Son Temettü Tarihi": last_date,
            "Son Temettü Tutarı": round(last_amount, 4),
            "Son 5 Yıl Ödeme Sayısı": count_5y,
            "Temettü Notu": "Yaklaşan tarih varsa KAP duyurusundan doğrulayın"
        }
    except Exception as exc:
        return {"Hisse": symbol, "Temettü Durumu": "Hata", "Temettü Notu": str(exc)}


def temettu_toplu_tara(symbols: List[str], max_workers: int = 8) -> pd.DataFrame:
    rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(temettu_bilgisi, s): s for s in symbols}
        for i, future in enumerate(as_completed(futures), 1):
            symbol = futures[future]
            print(f"Temettü kontrol {i}/{len(futures)}: {symbol}")
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append({
                    "Hisse": symbol,
                    "Temettü Durumu": "Hata",
                    "Temettü Notu": str(exc)
                })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Eksik kolonların her bilgisayarda güvenli oluşmasını sağla.
    gerekli_kolonlar = {
        "Hisse": "",
        "Temettü Durumu": "Duyuru bulunamadı",
        "Yaklaşan Temettü/Ex-Date": "",
        "Yıllık Temettü Tutarı": 0.0,
        "Temettü Verimi %": 0.0,
        "Son Temettü Tarihi": "",
        "Son Temettü Tutarı": 0.0,
        "Son 5 Yıl Ödeme Sayısı": 0,
        "Temettü Notu": ""
    }
    for kolon, varsayilan in gerekli_kolonlar.items():
        if kolon not in df.columns:
            df[kolon] = varsayilan

    bugun = pd.Timestamp.now().normalize()

    # Tarihleri gerçek datetime değerine dönüştür.
    df["_yaklasan_tarih"] = pd.to_datetime(
        df["Yaklaşan Temettü/Ex-Date"],
        errors="coerce",
        dayfirst=True
    )

    # Saat dilimi bilgisi varsa kaldır.
    try:
        df["_yaklasan_tarih"] = df["_yaklasan_tarih"].dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass

    df["Kalan Gün"] = (
        df["_yaklasan_tarih"].dt.normalize() - bugun
    ).dt.days

    # Grup sırası:
    # 0 = bugün/gelecek tarih
    # 1 = geçmiş tarih
    # 2 = tarih yok
    df["_tarih_grubu"] = 2
    tarih_var = df["_yaklasan_tarih"].notna()
    df.loc[tarih_var & (df["Kalan Gün"] >= 0), "_tarih_grubu"] = 0
    df.loc[tarih_var & (df["Kalan Gün"] < 0), "_tarih_grubu"] = 1

    # Kullanıcıya daha anlaşılır durum metni.
    df.loc[df["_tarih_grubu"] == 0, "Temettü Durumu"] = "Yaklaşan temettü"
    df.loc[df["_tarih_grubu"] == 1, "Temettü Durumu"] = "Tarihi geçmiş"
    df["Kalan Gün"] = df["Kalan Gün"].astype("Int64")

    # Yaklaşanlar en yakın tarihten uzağa.
    # Geçmiş tarihler en yeniden eskiye.
    # Tarihi olmayanlar ödeme geçmişi ve verime göre.
    yaklasan = df[df["_tarih_grubu"] == 0].sort_values(
        ["_yaklasan_tarih", "Temettü Verimi %", "Hisse"],
        ascending=[True, False, True],
        na_position="last"
    )

    gecmis = df[df["_tarih_grubu"] == 1].sort_values(
        ["_yaklasan_tarih", "Hisse"],
        ascending=[False, True],
        na_position="last"
    )

    tarihsiz = df[df["_tarih_grubu"] == 2].sort_values(
        ["Son 5 Yıl Ödeme Sayısı", "Temettü Verimi %", "Hisse"],
        ascending=[False, False, True],
        na_position="last"
    )

    df = pd.concat([yaklasan, gecmis, tarihsiz], ignore_index=True)

    # Excel'de gerçek tarih olarak görünmesi ve sıralanabilmesi için tarih kolonunu koru.
    df["Yaklaşan Temettü/Ex-Date"] = df["_yaklasan_tarih"]

    # Kullanıcıya gösterilmeyecek yardımcı kolonları kaldır.
    return df.drop(columns=["_yaklasan_tarih", "_tarih_grubu"], errors="ignore")

