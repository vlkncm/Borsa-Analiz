import yfinance as yf
from formasyon_motoru import formasyonlari_tespit_et
import pandas as pd
import time
from datetime import datetime

# Favori hisselerin
WATCHLIST = [

    "MEGMT.IS",   # Mega Metal
    "COSMO.IS",    # Cosmos Yatırım Holding
    "ASELS.IS",
    "KCHOL.IS",
    "EREGL.IS",
    "TUPRS.IS",
]

# Sürpriz aday tarama listesi
SURPRISE_LIST = [
    "AKBNK.IS", "GARAN.IS", "YKBNK.IS", "ISCTR.IS",
    "SISE.IS", "FROTO.IS", "TOASO.IS", "BIMAS.IS",
    "MAVI.IS", "SAHOL.IS", "ENKAI.IS", "PETKM.IS",
    "KRDMD.IS", "PGSUS.IS", "HEKTS.IS",
    "ALARK.IS", "ASTOR.IS", "ODAS.IS", "SASA.IS",
    "OYAKC.IS", "TAVHL.IS", "DOAS.IS", "MGROS.IS",
    "BRSAN.IS", "ENJSA.IS", "KCAER.IS","EKGYO.IS",
    "CIMSA.IS", "CCOLA.IS"
]


def rsi_hesapla(df, period=14):
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def macd_hesapla(df):
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal



def guvenli_sayi(value, default=0.0):
    try:
        number = float(value)
        if pd.isna(number):
            return default
        return number
    except Exception:
        return default


def atr_hesapla(df, period=14):
    onceki_kapanis = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - onceki_kapanis).abs(),
        (df["Low"] - onceki_kapanis).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def adx_hesapla(df, period=14):
    yukari = df["High"].diff()
    asagi = -df["Low"].diff()
    plus_dm = yukari.where((yukari > asagi) & (yukari > 0), 0.0)
    minus_dm = asagi.where((asagi > yukari) & (asagi > 0), 0.0)
    onceki_kapanis = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - onceki_kapanis).abs(),
        (df["Low"] - onceki_kapanis).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().replace(0, pd.NA)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100
    return dx.rolling(period).mean()


def teknik_gelecek_gorunumu(price, ema20, ema50, ema200, rsi, macd,
                            macd_signal, atr, adx, ret20, ret60,
                            destek, direnc, score):
    atr = max(guvenli_sayi(atr), price * 0.008)
    adx = guvenli_sayi(adx)
    puan = 0
    olumlu = []
    riskler = []

    if price > ema20:
        puan += 1; olumlu.append("fiyat EMA20 üzerinde")
    else:
        puan -= 1; riskler.append("fiyat EMA20 altında")

    if ema20 > ema50:
        puan += 1; olumlu.append("kısa trend pozitif")
    else:
        puan -= 1; riskler.append("kısa trend zayıf")

    if ema200 > 0 and price > ema200:
        puan += 1; olumlu.append("fiyat EMA200 üzerinde")
    elif ema200 > 0:
        puan -= 1; riskler.append("uzun trend altında")

    if macd > macd_signal:
        puan += 1; olumlu.append("MACD pozitif")
    else:
        puan -= 1; riskler.append("MACD negatif")

    if 45 <= rsi <= 65:
        puan += 1; olumlu.append("RSI dengeli")
    elif rsi >= 70:
        puan -= 1; riskler.append("RSI yüksek")
    elif rsi < 35:
        riskler.append("RSI zayıf bölgede")

    if ret20 > 0:
        puan += 1; olumlu.append("20 günlük momentum pozitif")
    elif ret20 < -8:
        puan -= 1; riskler.append("20 günlük momentum negatif")

    if adx >= 25:
        olumlu.append("trend gücü yüksek")
    elif adx > 0:
        riskler.append("trend gücü sınırlı")

    yon_katsayi = max(-1.0, min(1.0, puan / 6))
    merkez = price * (1 + yon_katsayi * min(abs(ret20) / 100, 0.08) * 0.45)
    bant = atr * (15 ** 0.5) * 1.25
    alt = max(0.01, merkez - bant)
    ust = merkez + bant

    if destek > 0:
        alt = max(min(alt, price), destek * 0.98)
    if direnc > price:
        ust = min(max(ust, price), direnc * 1.03)

    if puan >= 4:
        yon = "POZİTİF"
    elif puan <= -3:
        yon = "NEGATİF"
    else:
        yon = "YATAY / TEMKİNLİ"

    oran = atr / price if price else 0
    risk_seviyesi = "YÜKSEK" if oran > 0.04 else ("ORTA" if oran > 0.02 else "DÜŞÜK")
    tahmin = (
        f"{yon} görünüm | Olası teknik bant: {alt:.2f}-{ust:.2f} TL | "
        f"Risk: {risk_seviyesi} | Kesin fiyat tahmini değildir"
    )
    yorum = (
        f"Algoritmik değerlendirme: {', '.join(olumlu[:5]) if olumlu else 'belirgin olumlu sinyal yok'}. "
        f"Dikkat: {', '.join(riskler[:4]) if riskler else 'belirgin teknik risk yok'}. "
        f"Teknik puan {score}/100, RSI {rsi:.1f}, ADX {adx:.1f}. "
        f"Bu çıktı yatırım tavsiyesi değildir."
    )
    trend_olasiligi = int(max(5, min(95, 50 + puan * 7 + (score - 50) * 0.18)))
    return {
        "tahmin_15gun": tahmin,
        "ai_yorum": yorum,
        "trend_yonu": yon,
        "trend_olasiligi": trend_olasiligi,
        "tahmin_alt": round(alt, 2),
        "tahmin_ust": round(ust, 2),
        "risk_seviyesi": risk_seviyesi,
    }


def guvenli_yf_download(symbol, period="9mo", interval="1d", retries=3):
    son_hata = None
    for deneme in range(1, retries + 1):
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
                timeout=20
            )
            if df is not None and not df.empty:
                return df
        except Exception as exc:
            son_hata = exc

        if deneme < retries:
            time.sleep(deneme * 1.5)

    if son_hata:
        print(f"{symbol}: Yahoo verisi alınamadı, atlandı: {son_hata}")
    else:
        print(f"{symbol}: Yahoo verisi boş döndü, atlandı.")
    return None

def teknik_analiz(symbol, kategori):
    try:
        df = guvenli_yf_download(
            symbol,
            period="9mo",
            interval="1d",
            retries=3
        )
        if df is None:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 60:
            print(f"{symbol}: Veri yok veya yetersiz.")
            return None

        df["RSI"] = rsi_hesapla(df)
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()
        df["VOLUME_MA20"] = df["Volume"].rolling(20).mean()
        df["MACD"], df["MACD_SIGNAL"] = macd_hesapla(df)
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
        df["ATR"] = atr_hesapla(df)
        df["ADX"] = adx_hesapla(df)
        df["RET20"] = df["Close"].pct_change(20) * 100
        df["RET60"] = df["Close"].pct_change(60) * 100

        last = df.iloc[-1]
        prev = df.iloc[-2]

        price = float(last["Close"])
        rsi = float(last["RSI"])
        ema20 = float(last["EMA20"])
        ema50 = float(last["EMA50"])
        volume = float(last["Volume"])
        volume_ma20 = float(last["VOLUME_MA20"])
        volume_ratio = (volume / volume_ma20) if volume_ma20 > 0 else 1.0
        macd = float(last["MACD"])
        macd_signal = float(last["MACD_SIGNAL"])
        ema200 = guvenli_sayi(last.get("EMA200"), 0)
        atr = guvenli_sayi(last.get("ATR"), price * 0.02)
        adx = guvenli_sayi(last.get("ADX"), 0)
        ret20 = guvenli_sayi(last.get("RET20"), 0)
        ret60 = guvenli_sayi(last.get("RET60"), 0)

        score = 0
        reasons = []
        risk_notes = []

        # RSI toparlanma
        if float(prev["RSI"]) < 30 and rsi > 30:
            score += 20
            reasons.append("RSI 30 altından yukarı döndü")

        elif 30 <= rsi <= 45:
            score += 10
            reasons.append("RSI düşük bölgede, toparlanma potansiyeli var")

        elif 45 < rsi < 65:
            score += 15
            reasons.append("RSI sağlıklı bölgede")

        elif rsi >= 70:
            score -= 10
            risk_notes.append("RSI 70 üstünde, kısa vadede şişmiş olabilir")

        # Fiyat EMA20 üstünde mi?
        if price > ema20:
            score += 15
            reasons.append("Fiyat EMA20 üzerinde")

        # EMA20 EMA50 üzerinde mi?
        if ema20 > ema50:
            score += 15
            reasons.append("EMA20, EMA50 üzerinde")

        # EMA kesişimi
        if float(prev["EMA20"]) < float(prev["EMA50"]) and ema20 > ema50:
            score += 25
            reasons.append("EMA20, EMA50'yi yukarı kesti")

        # MACD pozitif sinyal
        if macd > macd_signal:
            score += 15
            reasons.append("MACD sinyali pozitif")

        # MACD yeni kesişim
        if float(prev["MACD"]) < float(prev["MACD_SIGNAL"]) and macd > macd_signal:
            score += 20
            reasons.append("MACD yukarı kesişim yaptı")

        # Hacim artışı
        if volume_ma20 > 0 and volume > volume_ma20 * 1.5:
            score += 20
            reasons.append("Hacim ortalamanın %50 üzerinde")

        elif volume_ma20 > 0 and volume > volume_ma20 * 1.2:
            score += 10
            reasons.append("Hacim ortalamanın üzerinde")

        # Fiyat çok zayıfsa
        if price < ema20 and ema20 < ema50:
            risk_notes.append("Fiyat EMA20 altında ve kısa trend zayıf")

        if score > 100:
            score = 100

        if score < 0:
            score = 0

        # ==========================
        # AL / SAT hesaplaması
        # ==========================
        if price > ema20 and ema20 > ema50 and macd > macd_signal and 45 <= rsi <= 68:
            aksiyon = "AL"
        elif price < ema20 and macd < macd_signal:
            aksiyon = "SAT"
        else:
            aksiyon = "BEKLE"

        son_60 = df.tail(60)
        son_20 = df.tail(20)
        ana_destek = guvenli_sayi(son_20["Low"].min(), price * 0.95)
        ana_direnc = guvenli_sayi(son_60["High"].max(), price * 1.08)

        stop_loss = max(0.01, price - max(atr * 1.5, price * 0.03))
        if 0 < ana_destek < price:
            stop_loss = max(stop_loss, ana_destek * 0.98)
        stop_loss = min(stop_loss, price * 0.985)

        hedef_1 = max(price + max(atr * 2.0, price * 0.06),
                      ana_direnc if ana_direnc > price else price * 1.06)
        hedef_2 = max(price + max(atr * 3.5, price * 0.12), hedef_1 * 1.06)
        alis_araligi_alt = max(0.01, min(price * 0.98, ema20 if ema20 < price else price * 0.98))
        alis_araligi_ust = price * 1.01

        risk_miktari = max(price - stop_loss, price * 0.01)
        risk_getiri_1 = max(0, (hedef_1 - price) / risk_miktari)
        risk_getiri_2 = max(0, (hedef_2 - price) / risk_miktari)
        destek_mesafe_yuzde = ((price - ana_destek) / price * 100) if ana_destek > 0 else 0
        direnc_mesafe_yuzde = ((ana_direnc - price) / price * 100) if ana_direnc > price else 0

        gelecek = teknik_gelecek_gorunumu(
            price, ema20, ema50, ema200, rsi, macd, macd_signal,
            atr, adx, ret20, ret60, ana_destek, ana_direnc, score
        )
        formasyon = formasyonlari_tespit_et(df)

        # ==========================
        # Mevcut karar sistemi
        # ==========================
        if score >= 75:
            karar = "GÜÇLÜ TAKİP"
        elif score >= 55:
            karar = "TAKİP EDİLEBİLİR"
        elif score >= 40:
            karar = "ZAYIF SİNYAL"
        else:
            karar = "BEKLE"
        # AL / SAT / TUT kararı
        if score >= 70 and price > ema20 and ema20 > ema50 and macd > macd_signal and rsi < 70:
            aksiyon = "AL"
        elif price < ema20 and macd < macd_signal and rsi < 45:
            aksiyon = "SAT"
        else:
            aksiyon = "TUT"
        return {
            "symbol": symbol,
            "kategori": kategori,
            "price": price,
            "rsi": rsi,
            "ema20": ema20,
            "ema50": ema50,
            "macd": macd,
            "macd_signal": macd_signal,
            "score": score,
            "karar": karar,
            "aksiyon": aksiyon,
            "alis_araligi_alt": alis_araligi_alt,
            "alis_araligi_ust": alis_araligi_ust,
            "stop_loss": stop_loss,
            "hedef_1": hedef_1,
            "hedef_2": hedef_2,
            "risk_getiri_1": risk_getiri_1,
            "risk_getiri_2": risk_getiri_2,
            "ana_destek": ana_destek,
            "ana_direnc": ana_direnc,
            "destek_gucu": 50,
            "direnc_gucu": 50,
            "destek_mesafe_yuzde": destek_mesafe_yuzde,
            "direnc_mesafe_yuzde": direnc_mesafe_yuzde,
            "ema200": ema200,
            "atr": atr,
            "adx": adx,
            "ret_20": ret20,
            "ret_60": ret60,
            "guven": score,
            "genel_skor": score,
            "formasyon": formasyon["formasyon"],
            "formasyon_puani": formasyon["formasyon_puani"],
            "formasyon_notu": formasyon["formasyon_notu"],
            "formasyon_yonu": formasyon["formasyon_yonu"],
            "formasyon_teyit": formasyon["formasyon_teyit"],
            "formasyon_kirilim": formasyon["formasyon_kirilim"],
            "formasyon_hedef": formasyon["formasyon_hedef"],
            "formasyon_stop": formasyon["formasyon_stop"],
            "formasyon_adaylari": formasyon["formasyon_adaylari"],
            "tahmini_sure": "2-6 hafta",
            "tahmin_15gun": gelecek["tahmin_15gun"],
            "ai_yorum": gelecek["ai_yorum"],
            "trend_yonu": gelecek["trend_yonu"],
            "trend_olasiligi": gelecek["trend_olasiligi"],
            "tahmin_alt": gelecek["tahmin_alt"],
            "tahmin_ust": gelecek["tahmin_ust"],
            "risk_seviyesi": gelecek["risk_seviyesi"],
            "volume_ratio": volume_ratio,
            "reasons": reasons or ["Belirgin teknik üstünlük bulunamadı"],
            "risk_notes": risk_notes or ["Belirgin ek teknik risk notu bulunamadı"]
        }

    except Exception as e:
        print(f"{symbol} hata: {e}")
        return None


def rapor_yazdir(results, limit=30):
    if not results:
        print("Bugün anlamlı teknik sinyal bulunamadı.")
        return

    results = sorted(results, key=lambda x: x["score"], reverse=True)

    print("\n==============================")
    print(" BORSA TEKNİK TARAMA RAPORU")
    print("==============================\n")

    for item in results[:limit]:
        if item["score"] < 40:
            continue

        print("--------------------------------")
        print(f"Hisse: {item['symbol']}")
        print(f"Kategori: {item['kategori']}")
        print(f"Fiyat: {item['price']:.2f} TL")
        print(f"RSI: {item['rsi']:.2f}")
        print(f"EMA20: {item['ema20']:.2f}")
        print(f"EMA50: {item['ema50']:.2f}")
        print(f"MACD: {item['macd']:.2f}")
        print(f"MACD Signal: {item['macd_signal']:.2f}")
        print(f"Puan: {item['score']}/100")
        print(f"Karar: {item['karar']}")
        print(f"Aksiyon: {item.get('aksiyon', 'TUT')}")
        print("Nedenler:")
        for reason in item["reasons"]:
            print(f"- {reason}")

        if item["risk_notes"]:
            print("Risk Notları:")
            for risk in item["risk_notes"]:
                print(f"- {risk}")

    print("\nTarama tamamlandı.")


def main():
    print("Borsa taraması başladı:", datetime.now().strftime("%d.%m.%Y %H:%M"))

    results = []

    for symbol in WATCHLIST:
        sonuc = teknik_analiz(symbol, "FAVORİ")
        if sonuc:
            results.append(sonuc)

    for symbol in SURPRISE_LIST:
        if symbol not in WATCHLIST:
            sonuc = teknik_analiz(symbol, "SÜRPRİZ ADAY")
            if sonuc:
                results.append(sonuc)

    rapor_yazdir(results)


if __name__ == "__main__":
    main()