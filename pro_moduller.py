from __future__ import annotations

import math
import time
from typing import Dict, List, Any

import pandas as pd
from veri_saglayici import veri as yf


OLUMLU_KELIMELER = {
    "contract": 5, "agreement": 5, "partnership": 4, "investment": 4,
    "growth": 4, "profit": 4, "record": 4, "upgrade": 4, "dividend": 3,
    "buyback": 5, "export": 4, "order": 5,
    "sözleşme": 5, "anlaşma": 5, "ortaklık": 4, "yatırım": 4,
    "büyüme": 4, "kar": 4, "kâr": 4, "temettü": 3, "geri alım": 5,
    "ihracat": 4, "sipariş": 5, "ihale": 4
}

OLUMSUZ_KELIMELER = {
    "loss": -5, "lawsuit": -4, "fine": -5, "debt": -3, "downgrade": -4,
    "bankruptcy": -10, "investigation": -5, "risk": -2,
    "zarar": -5, "dava": -4, "ceza": -5, "borç": -3, "iflas": -10,
    "soruşturma": -5, "tedbir": -5, "risk": -2
}


def guvenli_float(x, default=0.0):
    try:
        if x is None:
            return default
        val = float(x)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def sinirla(x, alt=0, ust=100):
    return max(alt, min(ust, x))


def temel_analiz_yfinance(symbol: str) -> Dict[str, Any]:
    """
    Ücretsiz yfinance temel veri denemesi.
    Her hisse için veri gelmeyebilir. Eksik veri varsa sistem nötr kalır.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        trailing_pe = guvenli_float(info.get("trailingPE"))
        forward_pe = guvenli_float(info.get("forwardPE"))
        price_to_book = guvenli_float(info.get("priceToBook"))
        debt_to_equity = guvenli_float(info.get("debtToEquity"))
        roe = guvenli_float(info.get("returnOnEquity"))
        profit_margin = guvenli_float(info.get("profitMargins"))
        revenue_growth = guvenli_float(info.get("revenueGrowth"))
        earnings_growth = guvenli_float(info.get("earningsGrowth"))
        dividend_yield = guvenli_float(info.get("dividendYield"))

        puan = 50
        notlar = []
        riskler = []

        if 0 < trailing_pe <= 12:
            puan += 8
            notlar.append("F/K makul")
        elif trailing_pe > 25:
            puan -= 6
            riskler.append("F/K yüksek")
        elif trailing_pe == 0:
            notlar.append("F/K verisi yok")

        if 0 < price_to_book <= 2:
            puan += 6
            notlar.append("PD/DD makul")
        elif price_to_book > 5:
            puan -= 6
            riskler.append("PD/DD yüksek")

        if roe > 0.15:
            puan += 8
            notlar.append("ROE güçlü")
        elif 0 < roe < 0.05:
            puan -= 4
            riskler.append("ROE zayıf")

        if profit_margin > 0.10:
            puan += 6
            notlar.append("Kâr marjı iyi")
        elif profit_margin < 0:
            puan -= 8
            riskler.append("Kâr marjı negatif")

        if revenue_growth > 0.15:
            puan += 6
            notlar.append("Ciro büyümesi güçlü")
        elif revenue_growth < -0.05:
            puan -= 5
            riskler.append("Ciro büyümesi negatif")

        if earnings_growth > 0.15:
            puan += 6
            notlar.append("Kâr büyümesi güçlü")
        elif earnings_growth < -0.05:
            puan -= 6
            riskler.append("Kâr büyümesi negatif")

        if debt_to_equity > 250:
            puan -= 8
            riskler.append("Borçluluk yüksek")
        elif 0 < debt_to_equity < 100:
            puan += 4
            notlar.append("Borçluluk makul")

        if dividend_yield > 0.02:
            puan += 3
            notlar.append("Temettü verimi mevcut")

        veri_var = any([
            trailing_pe, forward_pe, price_to_book, debt_to_equity,
            roe, profit_margin, revenue_growth, earnings_growth, dividend_yield
        ])

        if not veri_var:
            puan = 50
            notlar.append("Temel veri bulunamadı, nötr kabul edildi")

        return {
            "temel_puan": int(round(sinirla(puan))),
            "fk": trailing_pe,
            "ileri_fk": forward_pe,
            "pddd": price_to_book,
            "borc_ozsermaye": debt_to_equity,
            "roe": roe,
            "kar_marji": profit_margin,
            "ciro_buyume": revenue_growth,
            "kar_buyume": earnings_growth,
            "temettu_verimi": dividend_yield,
            "temel_not": " | ".join(notlar),
            "temel_risk": " | ".join(riskler)
        }

    except Exception as e:
        return {
            "temel_puan": 50,
            "fk": 0,
            "ileri_fk": 0,
            "pddd": 0,
            "borc_ozsermaye": 0,
            "roe": 0,
            "kar_marji": 0,
            "ciro_buyume": 0,
            "kar_buyume": 0,
            "temettu_verimi": 0,
            "temel_not": "Temel analiz verisi alınamadı",
            "temel_risk": str(e)
        }


def haber_analizi_yfinance(symbol: str) -> Dict[str, Any]:
    """
    yfinance haber akışından basit anahtar kelime analizi.
    Bazı BIST hisselerinde haber gelmeyebilir.
    """
    try:
        ticker = yf.Ticker(symbol)
        haberler = getattr(ticker, "news", []) or []

        puan = 0
        basliklar = []
        bulunan = []

        for haber in haberler[:8]:
            title = str(haber.get("title", ""))
            publisher = str(haber.get("publisher", ""))
            metin = f"{title} {publisher}".lower()
            if title:
                basliklar.append(title)

            for kelime, deger in OLUMLU_KELIMELER.items():
                if kelime in metin:
                    puan += deger
                    bulunan.append(f"+{deger} {kelime}")

            for kelime, deger in OLUMSUZ_KELIMELER.items():
                if kelime in metin:
                    puan += deger
                    bulunan.append(f"{deger} {kelime}")

        puan = max(-20, min(20, puan))

        if puan >= 6:
            etiket = "Olumlu"
        elif puan <= -6:
            etiket = "Olumsuz"
        else:
            etiket = "Nötr"

        if not haberler:
            etiket = "Veri Yok"
            notu = "Haber bulunamadı"
        else:
            notu = " | ".join(bulunan) if bulunan else "Önemli anahtar kelime bulunmadı"

        return {
            "haber_puani": puan,
            "haber_etiket": etiket,
            "haber_notu": notu,
            "haber_basliklari": " || ".join(basliklar[:5])
        }

    except Exception as e:
        return {
            "haber_puani": 0,
            "haber_etiket": "Hata",
            "haber_notu": str(e),
            "haber_basliklari": ""
        }


def makro_analiz_yfinance() -> Dict[str, Any]:
    """
    BIST100, USD/TRY ve global risk göstergeleriyle genel piyasa filtresi.
    Tüm hisselere aynı makro puan uygulanır.
    """
    semboller = {
        "bist100": "XU100.IS",
        "usdtry": "USDTRY=X",
        "altin": "GC=F",
        "petrol": "CL=F"
    }

    sonuc = {}
    puan = 50
    notlar = []

    piyasa_rejimi = "YATAY / BELİRSİZ"
    for isim, sembol in semboller.items():
        try:
            period = "2y" if isim == "bist100" else "3mo"
            df = yf.download(sembol, period=period, interval="1d", progress=False, auto_adjust=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty or len(df) < 25:
                continue

            close = pd.to_numeric(df["Close"], errors="coerce").dropna()
            close = close[close > 0]
            if len(close) < 25:
                continue
            son = guvenli_float(close.iloc[-1])
            ema20 = guvenli_float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = guvenli_float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = guvenli_float(close.ewm(span=200, adjust=False).mean().iloc[-1])
            ret20 = guvenli_float(close.pct_change(20).iloc[-1] * 100)

            sonuc[f"{isim}_son"] = son
            sonuc[f"{isim}_ret20"] = ret20

            if isim == "bist100":
                sonuc["bist100_ema20"] = ema20
                sonuc["bist100_ema50"] = ema50
                sonuc["bist100_ema200"] = ema200
                if son > ema20 > ema50 > ema200 and ret20 > 0:
                    puan += 15
                    piyasa_rejimi = "YÜKSELİŞ"
                    notlar.append("BIST100 trendi pozitif")
                elif son < ema20 < ema50 and son < ema200 and ret20 < 0:
                    puan -= 15
                    piyasa_rejimi = "DÜŞÜŞ"
                    notlar.append("BIST100 trendi zayıf")
                else:
                    piyasa_rejimi = "YATAY / GEÇİŞ"

            if isim == "usdtry":
                if ret20 > 5:
                    puan -= 5
                    notlar.append("USD/TRY hızlı yükseliyor, piyasa riski artabilir")

            if isim == "petrol":
                if ret20 > 8:
                    notlar.append("Petrol yükselişi havacılık/ulaştırma için risk olabilir")

        except Exception:
            continue

    puan = int(round(sinirla(puan)))

    if puan >= 65:
        etiket = "Pozitif"
    elif puan <= 40:
        etiket = "Negatif"
    else:
        etiket = "Nötr"

    sonuc.update({
        "makro_puan": puan,
        "makro_etiket": etiket,
        "piyasa_rejimi": piyasa_rejimi,
        "makro_notu": " | ".join(notlar) if notlar else "Makro görünüm nötr"
    })

    return sonuc


def broker_karar_motoru(item: Dict[str, Any], makro: Dict[str, Any]) -> Dict[str, Any]:
    """
    Seviye 10: Teknik + temel + haber + makro + risk/getiri birleştirme.
    """
    teknik = guvenli_float(item.get("guven", item.get("score", 50)))
    temel = guvenli_float(item.get("temel_puan", 50))
    haber = guvenli_float(item.get("haber_puani", 0))
    makro_puan = guvenli_float(makro.get("makro_puan", 50))
    risk_getiri = guvenli_float(item.get("risk_getiri_1", 0))
    trend_olasiligi = guvenli_float(item.get("trend_olasiligi", 50))
    formasyon_puani = guvenli_float(item.get("formasyon_puani", 0))

    # 100 üstünden birleşik skor
    genel = (
        teknik * 0.42 +
        temel * 0.22 +
        (50 + haber) * 0.13 +
        makro_puan * 0.10 +
        trend_olasiligi * 0.08 +
        (50 + formasyon_puani) * 0.05
    )

    # Risk/getiri filtresi
    if risk_getiri >= 2:
        genel += 4
    elif risk_getiri < 1.2:
        genel -= 8

    # Çok yakın direnç varsa düşür
    if guvenli_float(item.get("direnc_mesafe_yuzde", 100)) <= 3:
        genel -= 5

    genel = int(round(sinirla(genel)))

    if genel >= 78 and item.get("aksiyon") == "AL" and risk_getiri >= 1.5:
        broker_aksiyon = "GÜÇLÜ AL"
    elif genel >= 68 and item.get("aksiyon") in ["AL", "TUT"]:
        broker_aksiyon = "AL"
    elif genel <= 38 or item.get("aksiyon") == "SAT":
        broker_aksiyon = "SAT"
    else:
        broker_aksiyon = "TUT"

    pozisyon_orani = 0
    if broker_aksiyon == "GÜÇLÜ AL":
        pozisyon_orani = 8
    elif broker_aksiyon == "AL":
        pozisyon_orani = 5
    elif broker_aksiyon == "TUT":
        pozisyon_orani = 0
    else:
        pozisyon_orani = 0

    yorum = (
        f"Broker motoru {item.get('symbol')} için {broker_aksiyon} sonucuna ulaştı. "
        f"Teknik {teknik:.0f}/100, temel {temel:.0f}/100, haber etkisi {haber:+.0f}, "
        f"makro {makro_puan:.0f}/100. Risk/getiri {risk_getiri:.2f}. "
        f"Stop seviyesi altında günlük kapanışta karar gözden geçirilmeli."
    )

    return {
        "broker_skor": genel,
        "broker_aksiyon": broker_aksiyon,
        "pozisyon_orani_oneri": pozisyon_orani,
        "broker_yorum": yorum
    }


def portfoy_onerisi_uret(
    df: pd.DataFrame,
    sermaye: float = 100000,
    islem_riski_yuzde: float = 1.0,
    max_pozisyon_yuzde: float = 20.0,
) -> pd.DataFrame:
    """Stop mesafesine göre risk bütçeli örnek pozisyon planı üretir."""
    if df.empty or "Broker Aksiyon" not in df.columns:
        return pd.DataFrame()

    aday = df[df["Broker Aksiyon"].isin(["GÜÇLÜ AL", "AL"])].copy()
    if "Yatırım Kararı" in aday.columns:
        aday = aday[aday["Yatırım Kararı"].isin(["BUGÜN AL", "ALIM BÖLGESİNİ BEKLE"])]
    if "Veri Güven Puanı" in aday.columns:
        guven = pd.to_numeric(aday["Veri Güven Puanı"], errors="coerce").fillna(0)
        aday = aday[guven >= 60]
    if aday.empty:
        return pd.DataFrame()

    sort_columns = [c for c in ["Broker Skor", "v4 Güven Puanı", "Güven"] if c in aday.columns]
    if sort_columns:
        aday = aday.sort_values(sort_columns, ascending=False)
    aday = aday.head(8)

    sermaye = max(0.0, guvenli_float(sermaye))
    islem_riski_yuzde = min(5.0, max(0.1, guvenli_float(islem_riski_yuzde, 1.0)))
    max_pozisyon_yuzde = min(50.0, max(1.0, guvenli_float(max_pozisyon_yuzde, 20.0)))
    risk_butcesi = sermaye * islem_riski_yuzde / 100.0
    pozisyon_limiti = sermaye * max_pozisyon_yuzde / 100.0

    rows = []
    for _, row in aday.iterrows():
        fiyat = guvenli_float(row.get("Önerilen Alış Üst", row.get("Fiyat", 0)))
        stop = guvenli_float(row.get("Önerilen Stop", row.get("Stop Loss", 0)))
        hedef = guvenli_float(row.get("Önerilen Satış", row.get("Hedef 1", 0)))
        hisse_basi_risk = fiyat - stop
        if fiyat <= 0 or stop <= 0 or hisse_basi_risk <= 0:
            continue
        risk_lotu = int(risk_butcesi // hisse_basi_risk)
        sermaye_lotu = int(pozisyon_limiti // fiyat)
        lot = max(0, min(risk_lotu, sermaye_lotu))
        if lot <= 0:
            continue
        tutar = lot * fiyat
        maksimum_zarar = lot * hisse_basi_risk
        potansiyel_kazanc = lot * max(0.0, hedef - fiyat)
        rr = (hedef - fiyat) / hisse_basi_risk if hedef > fiyat else 0.0

        rows.append({
            "Hisse": row["Hisse"],
            "Broker Aksiyon": row["Broker Aksiyon"],
            "Broker Skor": guvenli_float(row.get("Broker Skor", 0)),
            "Planlanan Giriş": round(fiyat, 2),
            "Önerilen Lot": lot,
            "Pozisyon Tutarı": round(tutar, 2),
            "Pozisyon %": round((tutar / sermaye * 100) if sermaye else 0, 2),
            "Stop": round(stop, 2),
            "Hedef": round(hedef, 2),
            "Maksimum Zarar": round(maksimum_zarar, 2),
            "Portföy Risk %": round((maksimum_zarar / sermaye * 100) if sermaye else 0, 2),
            "Potansiyel Kazanç": round(potansiyel_kazanc, 2),
            "Risk/Getiri": round(rr, 2),
        })

    return pd.DataFrame(rows)
