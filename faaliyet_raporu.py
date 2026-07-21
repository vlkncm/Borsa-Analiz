from __future__ import annotations

import re
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from veri_saglayici import veri as yf
from bs4 import BeautifulSoup
from pypdf import PdfReader


POZITIF_KELIMELER = {
    "satış gelirleri arttı": 8,
    "satışlar arttı": 7,
    "hasılat arttı": 7,
    "net kar arttı": 8,
    "net kâr arttı": 8,
    "favök arttı": 7,
    "faaliyet karı arttı": 6,
    "faaliyet kârı arttı": 6,
    "kapasite artışı": 7,
    "kapasite yatırımı": 7,
    "yeni yatırım": 6,
    "yeni tesis": 7,
    "yeni fabrika": 8,
    "ihracat arttı": 7,
    "yeni sipariş": 7,
    "sipariş bakiyesi": 6,
    "sözleşme imzalandı": 7,
    "pazar payı arttı": 6,
    "nakit akışı güçlü": 6,
    "borç azaldı": 7,
    "borçluluk azaldı": 7,
    "ar-ge yatırımı": 4,
    "verimlilik artışı": 5,
    "olumlu beklenti": 5,
    "büyüme beklentisi": 5,
    "karlılık artışı": 6,
    "kârlılık artışı": 6,
}

OLUMSUZ_KELIMELER = {
    "satış gelirleri azaldı": -8,
    "satışlar azaldı": -7,
    "hasılat azaldı": -7,
    "net zarar": -9,
    "net kar azaldı": -8,
    "net kâr azaldı": -8,
    "favök azaldı": -7,
    "faaliyet zararı": -8,
    "borç arttı": -7,
    "borçluluk arttı": -7,
    "negatif nakit akışı": -7,
    "üretim durdu": -10,
    "faaliyet durduruldu": -10,
    "dava": -4,
    "ceza": -6,
    "soruşturma": -6,
    "kur riski": -4,
    "likidite riski": -5,
    "finansman riski": -5,
    "şüpheli alacak": -5,
    "denetçi görüşü": -3,
    "sınırlı olumlu görüş": -6,
    "şartlı görüş": -8,
    "belirsizlik": -4,
    "olumsuz beklenti": -6,
    "daralma beklentisi": -6,
}

YONETIM_KELIMELERI = [
    "gelecek döneme ilişkin beklentiler",
    "yönetimin değerlendirmesi",
    "yönetim kurulu değerlendirmesi",
    "önümüzdeki dönem",
    "gelecek dönem",
    "beklentiler",
]

RISK_KELIMELERI = [
    "riskler",
    "risk yönetimi",
    "kur riski",
    "faiz riski",
    "likidite riski",
    "kredi riski",
    "operasyonel risk",
]


def guvenli_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if pd.isna(number):
            return default
        return number
    except Exception:
        return default


def sembol_temizle(symbol: str) -> str:
    return symbol.replace(".IS", "").strip().upper()


def cache_klasoru() -> Path:
    belgeler = Path.home() / "Documents"
    if not belgeler.exists():
        belgeler = Path.home()
    klasor = belgeler / "Borsa Analiz Pro MAX" / "faaliyet_raporlari"
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def kap_faaliyet_raporu_bul(symbol: str) -> Dict[str, Any]:
    """
    KAP arama sayfasında faaliyet raporu ve PDF bağlantısı arar.
    KAP sayfa yapısı değişirse veri bulunamayabilir; bu durumda nötr sonuç döner.
    """
    kod = sembol_temizle(symbol)
    url = f"https://www.kap.org.tr/tr/ara/{kod}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
    }

    try:
        response = requests.get(url, headers=headers, timeout=18)
        if response.status_code != 200:
            return {
                "bulundu": False,
                "rapor_url": "",
                "rapor_basligi": "",
                "rapor_notu": f"KAP erişimi HTTP {response.status_code}",
            }

        soup = BeautifulSoup(response.text, "html.parser")
        adaylar = []

        for a in soup.find_all("a", href=True):
            metin = " ".join(a.get_text(" ", strip=True).split())
            href = a.get("href", "")
            birlesik = f"{metin} {href}".lower()

            if (
                "faaliyet raporu" in birlesik
                or "annual report" in birlesik
                or "activity report" in birlesik
            ):
                tam_url = urljoin("https://www.kap.org.tr", href)
                adaylar.append((metin or "Faaliyet Raporu", tam_url))

        # PDF bağlantısını veya bildirim sayfasını tercih et
        if adaylar:
            adaylar.sort(key=lambda x: (".pdf" not in x[1].lower(), len(x[0])))
            baslik, rapor_url = adaylar[0]
            return {
                "bulundu": True,
                "rapor_url": rapor_url,
                "rapor_basligi": baslik,
                "rapor_notu": "KAP arama sayfasından bağlantı bulundu",
            }

        # HTML içinde çıplak PDF bağlantısı ihtimali
        pdf_eslesmeler = re.findall(r'https?://[^"\']+\.pdf(?:\?[^"\']*)?', response.text, flags=re.I)
        for pdf_url in pdf_eslesmeler:
            if kod.lower() in pdf_url.lower() or "faaliyet" in pdf_url.lower():
                return {
                    "bulundu": True,
                    "rapor_url": pdf_url,
                    "rapor_basligi": f"{kod} Faaliyet Raporu",
                    "rapor_notu": "HTML içinde PDF bağlantısı bulundu",
                }

        return {
            "bulundu": False,
            "rapor_url": "",
            "rapor_basligi": "",
            "rapor_notu": "Faaliyet raporu bağlantısı bulunamadı",
        }

    except Exception as exc:
        return {
            "bulundu": False,
            "rapor_url": "",
            "rapor_basligi": "",
            "rapor_notu": f"KAP arama hatası: {exc}",
        }


def _pdf_url_coz(url: str) -> str:
    """
    URL doğrudan PDF değilse sayfa içindeki ilk PDF bağlantısını bulmayı dener.
    """
    if ".pdf" in url.lower():
        return url

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=18)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    if "application/pdf" in content_type:
        return url

    soup = BeautifulSoup(response.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower():
            return urljoin(url, href)

    for tag in soup.find_all(["iframe", "embed"], src=True):
        src = tag.get("src", "")
        if ".pdf" in src.lower():
            return urljoin(url, src)

    raise ValueError("Bildirim sayfasında PDF bağlantısı bulunamadı")


def pdf_indir(url: str, symbol: str) -> Path:
    pdf_url = _pdf_url_coz(url)
    dosya_adi = f"{sembol_temizle(symbol)}_{hashlib.md5(pdf_url.encode()).hexdigest()[:10]}.pdf"
    hedef = cache_klasoru() / dosya_adi

    if hedef.exists() and hedef.stat().st_size > 10_000:
        return hedef

    response = requests.get(
        pdf_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=45,
        stream=True,
    )
    response.raise_for_status()

    with hedef.open("wb") as f:
        for parca in response.iter_content(chunk_size=1024 * 128):
            if parca:
                f.write(parca)

    if hedef.stat().st_size < 1_000:
        hedef.unlink(missing_ok=True)
        raise ValueError("İndirilen dosya geçerli PDF görünmüyor")

    return hedef


def pdf_metni_cikar(pdf_path: Path, max_sayfa: int = 220) -> Dict[str, Any]:
    reader = PdfReader(str(pdf_path))
    toplam_sayfa = len(reader.pages)
    metinler = []
    okunan = 0

    for sayfa in reader.pages[:max_sayfa]:
        try:
            metin = sayfa.extract_text() or ""
            if metin.strip():
                metinler.append(metin)
            okunan += 1
        except Exception:
            continue

    metin = "\n".join(metinler)
    metin = re.sub(r"\s+", " ", metin)

    return {
        "metin": metin,
        "toplam_sayfa": toplam_sayfa,
        "okunan_sayfa": okunan,
        "karakter": len(metin),
    }


def finansal_egilim_yfinance(symbol: str) -> Dict[str, Any]:
    """
    Faaliyet raporuna destek olarak Yahoo finansal tablolarındaki son dönem eğilimlerini dener.
    """
    puan = 50
    notlar = []
    riskler = []

    try:
        ticker = yf.Ticker(symbol)
        gelir = ticker.quarterly_financials
        bilanço = ticker.quarterly_balance_sheet

        if isinstance(gelir, pd.DataFrame) and gelir.shape[1] >= 2:
            def satir_bul(adlar):
                for ad in adlar:
                    if ad in gelir.index:
                        return gelir.loc[ad]
                return None

            toplam_gelir = satir_bul(["Total Revenue", "Operating Revenue"])
            net_kar = satir_bul(["Net Income", "Net Income Common Stockholders"])
            faaliyet_kari = satir_bul(["Operating Income"])

            for seri, isim, agirlik in [
                (toplam_gelir, "Ciro", 7),
                (net_kar, "Net kâr", 8),
                (faaliyet_kari, "Faaliyet kârı", 6),
            ]:
                if seri is not None and len(seri.dropna()) >= 2:
                    son = guvenli_float(seri.dropna().iloc[0])
                    onceki = guvenli_float(seri.dropna().iloc[1])
                    if onceki != 0:
                        degisim = ((son / abs(onceki)) - 1) * 100
                        if son > onceki:
                            puan += agirlik
                            notlar.append(f"{isim} önceki döneme göre güçlü")
                        else:
                            puan -= agirlik
                            riskler.append(f"{isim} önceki döneme göre zayıf")

        if isinstance(bilanço, pd.DataFrame) and bilanço.shape[1] >= 2:
            borc_satiri = None
            for ad in ["Total Debt", "Long Term Debt And Capital Lease Obligation"]:
                if ad in bilanço.index:
                    borc_satiri = bilanço.loc[ad]
                    break

            if borc_satiri is not None and len(borc_satiri.dropna()) >= 2:
                son = guvenli_float(borc_satiri.dropna().iloc[0])
                onceki = guvenli_float(borc_satiri.dropna().iloc[1])
                if son < onceki:
                    puan += 6
                    notlar.append("Toplam borç azalmış")
                elif son > onceki:
                    puan -= 6
                    riskler.append("Toplam borç artmış")

        puan = max(0, min(100, int(round(puan))))
        return {
            "finansal_egilim_puani": puan,
            "finansal_egilim_notu": " | ".join(notlar),
            "finansal_egilim_riski": " | ".join(riskler),
        }

    except Exception as exc:
        return {
            "finansal_egilim_puani": 50,
            "finansal_egilim_notu": "Finansal eğilim verisi alınamadı",
            "finansal_egilim_riski": str(exc),
        }


def faaliyet_metni_puanla(metin: str) -> Dict[str, Any]:
    metin_kucuk = metin.lower()
    puan = 50
    guclu = []
    riskler = []

    for kelime, deger in POZITIF_KELIMELER.items():
        adet = metin_kucuk.count(kelime)
        if adet:
            katkı = min(abs(deger) * adet, abs(deger) * 3)
            puan += katkı
            guclu.append(f"{kelime} (+{katkı})")

    for kelime, deger in OLUMSUZ_KELIMELER.items():
        adet = metin_kucuk.count(kelime)
        if adet:
            etki = max(deger * adet, deger * 3)
            puan += etki
            riskler.append(f"{kelime} ({etki})")

    yonetim_var = any(k in metin_kucuk for k in YONETIM_KELIMELERI)
    risk_bolumu_var = any(k in metin_kucuk for k in RISK_KELIMELERI)

    if yonetim_var:
        puan += 3
        guclu.append("Yönetim beklentileri bölümü bulundu")

    if risk_bolumu_var:
        riskler.append("Risk yönetimi bölümü bulundu; ayrıntılı insan kontrolü önerilir")

    puan = max(0, min(100, int(round(puan))))

    if puan >= 75:
        gorunum = "OLUMLU"
    elif puan <= 40:
        gorunum = "OLUMSUZ"
    else:
        gorunum = "NÖTR"

    return {
        "metin_puani": puan,
        "faaliyet_gorunumu": gorunum,
        "faaliyet_guclu_noktalar": " | ".join(guclu[:12]),
        "faaliyet_riskleri": " | ".join(riskler[:12]),
    }


def faaliyet_raporu_analiz(symbol: str) -> Dict[str, Any]:
    finansal = finansal_egilim_yfinance(symbol)
    kap = kap_faaliyet_raporu_bul(symbol)

    temel_sonuc = {
        "faaliyet_raporu_bulundu": "Hayır",
        "faaliyet_raporu_basligi": kap.get("rapor_basligi", ""),
        "faaliyet_raporu_url": kap.get("rapor_url", ""),
        "faaliyet_raporu_dosya": "",
        "faaliyet_raporu_sayfa": 0,
        "faaliyet_raporu_karakter": 0,
        "faaliyet_metin_puani": 50,
        "faaliyet_puani": finansal.get("finansal_egilim_puani", 50),
        "faaliyet_gorunumu": "NÖTR",
        "faaliyet_guclu_noktalar": finansal.get("finansal_egilim_notu", ""),
        "faaliyet_riskleri": finansal.get("finansal_egilim_riski", ""),
        "faaliyet_notu": kap.get("rapor_notu", ""),
    }

    if not kap.get("bulundu"):
        return temel_sonuc

    try:
        pdf_path = pdf_indir(kap["rapor_url"], symbol)
        pdf_info = pdf_metni_cikar(pdf_path)

        if pdf_info["karakter"] < 1_000:
            temel_sonuc["faaliyet_notu"] = (
                "PDF bulundu ancak okunabilir metin çok az. Rapor taranmış görüntü olabilir."
            )
            temel_sonuc["faaliyet_raporu_bulundu"] = "Kısmen"
            temel_sonuc["faaliyet_raporu_dosya"] = str(pdf_path)
            return temel_sonuc

        metin_sonuc = faaliyet_metni_puanla(pdf_info["metin"])
        final_puan = int(round(
            metin_sonuc["metin_puani"] * 0.65
            + finansal.get("finansal_egilim_puani", 50) * 0.35
        ))
        final_puan = max(0, min(100, final_puan))

        if final_puan >= 75:
            final_gorunum = "OLUMLU"
        elif final_puan <= 40:
            final_gorunum = "OLUMSUZ"
        else:
            final_gorunum = "NÖTR"

        return {
            "faaliyet_raporu_bulundu": "Evet",
            "faaliyet_raporu_basligi": kap.get("rapor_basligi", ""),
            "faaliyet_raporu_url": kap.get("rapor_url", ""),
            "faaliyet_raporu_dosya": str(pdf_path),
            "faaliyet_raporu_sayfa": pdf_info["toplam_sayfa"],
            "faaliyet_raporu_karakter": pdf_info["karakter"],
            "faaliyet_metin_puani": metin_sonuc["metin_puani"],
            "faaliyet_puani": final_puan,
            "faaliyet_gorunumu": final_gorunum,
            "faaliyet_guclu_noktalar": " | ".join(filter(None, [
                metin_sonuc["faaliyet_guclu_noktalar"],
                finansal.get("finansal_egilim_notu", ""),
            ])),
            "faaliyet_riskleri": " | ".join(filter(None, [
                metin_sonuc["faaliyet_riskleri"],
                finansal.get("finansal_egilim_riski", ""),
            ])),
            "faaliyet_notu": (
                f"PDF metni ve finansal eğilim birlikte puanlandı. "
                f"Okunan {pdf_info['okunan_sayfa']}/{pdf_info['toplam_sayfa']} sayfa."
            ),
        }

    except Exception as exc:
        temel_sonuc["faaliyet_raporu_bulundu"] = "Hata"
        temel_sonuc["faaliyet_notu"] = f"Faaliyet raporu işlenemedi: {exc}"
        return temel_sonuc


def faaliyet_toplu_analiz(symbols: List[str], bekleme: float = 0.4) -> Dict[str, Dict[str, Any]]:
    sonuclar = {}

    for index, symbol in enumerate(symbols, start=1):
        print(f"Faaliyet raporu {index}/{len(symbols)}: {symbol}")
        sonuclar[symbol] = faaliyet_raporu_analiz(symbol)
        time.sleep(bekleme)

    return sonuclar


def faaliyet_dataframe(results: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []

    for item in results:
        if "faaliyet_puani" not in item:
            continue

        rows.append({
            "Hisse": item.get("symbol", ""),
            "Faaliyet Puanı": item.get("faaliyet_puani", 50),
            "Faaliyet Görünümü": item.get("faaliyet_gorunumu", "NÖTR"),
            "Rapor Bulundu": item.get("faaliyet_raporu_bulundu", "Hayır"),
            "Rapor Başlığı": item.get("faaliyet_raporu_basligi", ""),
            "Rapor Sayfa": item.get("faaliyet_raporu_sayfa", 0),
            "Güçlü Noktalar": item.get("faaliyet_guclu_noktalar", ""),
            "Riskler": item.get("faaliyet_riskleri", ""),
            "Not": item.get("faaliyet_notu", ""),
            "Rapor URL": item.get("faaliyet_raporu_url", ""),
            "Yerel PDF": item.get("faaliyet_raporu_dosya", ""),
            "Broker Aksiyon": item.get("broker_aksiyon", ""),
            "Broker Skor": item.get("broker_skor", 0),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            ["Faaliyet Puanı", "Broker Skor"],
            ascending=[False, False]
        )

    return df
