from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Dict, Any, List

import pandas as pd
import requests
from bs4 import BeautifulSoup


OLUMLU_KAP_KELIMELER = {
    "sözleşme": 8,
    "sozlesme": 8,
    "anlaşma": 8,
    "anlasma": 8,
    "ihale": 7,
    "yeni iş": 8,
    "yeni is": 8,
    "sipariş": 7,
    "siparis": 7,
    "yatırım": 6,
    "yatirim": 6,
    "kapasite artışı": 7,
    "kapasite artisi": 7,
    "geri alım": 7,
    "geri alim": 7,
    "temettü": 5,
    "temettu": 5,
    "bedelsiz": 6,
    "ihracat": 6,
    "ortaklık": 5,
    "ortaklik": 5,
    "kar payı": 5,
    "kar payi": 5,
    "pay geri alım": 7,
    "pay geri alim": 7
}

OLUMSUZ_KAP_KELIMELER = {
    "ceza": -8,
    "dava": -6,
    "soruşturma": -7,
    "sorusturma": -7,
    "tedbir": -7,
    "zarar": -6,
    "faaliyet durdurma": -10,
    "üretim durdu": -10,
    "uretim durdu": -10,
    "iflas": -15,
    "konkordato": -15,
    "sermaye azaltımı": -8,
    "sermaye azaltimi": -8,
    "borç yapılandırma": -6,
    "borc yapilandirma": -6,
    "pay satışı": -5,
    "pay satisi": -5
}


def sembol_temizle(symbol: str) -> str:
    return symbol.replace(".IS", "").replace("'", "").strip().upper()


def metin_puanla(metin: str) -> Dict[str, Any]:
    if not metin:
        return {
            "kap_skor": 0,
            "kap_etiket": "Nötr",
            "kap_notu": "KAP metni bulunamadı"
        }

    m = metin.lower()
    skor = 0
    bulunan = []

    for kelime, puan in OLUMLU_KAP_KELIMELER.items():
        if kelime in m:
            skor += puan
            bulunan.append(f"+{puan} {kelime}")

    for kelime, puan in OLUMSUZ_KAP_KELIMELER.items():
        if kelime in m:
            skor += puan
            bulunan.append(f"{puan} {kelime}")

    skor = max(-30, min(30, skor))

    if skor >= 8:
        etiket = "Olumlu"
    elif skor <= -8:
        etiket = "Olumsuz"
    else:
        etiket = "Nötr"

    return {
        "kap_skor": skor,
        "kap_etiket": etiket,
        "kap_olaylari": kap_olayi_sinifla(metin),
        "kap_notu": " | ".join(bulunan) if bulunan else "Önemli KAP anahtar kelimesi bulunmadı"
    }


def kap_olayi_sinifla(metin: str) -> str:
    """KAP metnini puandan bağımsız, denetlenebilir olay etiketlerine ayırır."""
    text = (metin or "").lower()
    events = []
    categories = {
        "BILANCO/KARLILIK": ("finansal", "kâr", "kar", "zarar", "hasılat"),
        "SERMAYE ISLEMI": ("bedelsiz", "sermaye artır", "sermaye azalt"),
        "TEMETTU": ("temettü", "temettu", "kâr payı", "kar payi"),
        "SOZLESME/IHALE": ("sözleşme", "sozlesme", "ihale", "sipariş", "siparis"),
        "HUKUKI/RISK": ("dava", "soruşturma", "sorusturma", "ceza", "iflas", "konkordato"),
        "FAALIYET": ("faaliyet durdur", "üretim durdu", "uretim durdu", "kapasite"),
        "YATIRIM": ("yeni yatırım", "yatırım kararı", "tesis yatırımı"),
        "ORTAKLIK/SATIN ALMA": ("ortaklık", "satın alma", "devralma", "birleşme"),
        "PAY GERI ALIMI/TEKLIFI": ("pay geri al", "geri alım", "pay alım teklifi"),
        "IZIN/RESMI ONAY": ("izin", "ruhsat", "resmi onay", "kurul onayı"),
        "IHRACAT/YENI PAZAR": ("ihracat", "yeni pazar", "yurt dışı satış"),
        "ORTAK SATISI": ("ortak satışı", "pay satışı", "hisse satışı"),
        "BORC/NAKIT": ("borç azalış", "borç azal", "nakit artış"),
    }
    for label, terms in categories.items():
        if any(term in text for term in terms):
            events.append(label)
    return " | ".join(events) if events else "SINIFLANDIRILACAK OLAY YOK"


def yayin_anina_gore_aciklamalar(aciklamalar: list[dict], cutoff: datetime) -> list[dict]:
    """Yalnızca gerçekten yayımlandığı anda bilinen KAP kayıtlarını döndürür."""
    result = []
    for item in aciklamalar:
        raw = item.get("published_at")
        if not raw:
            continue
        try:
            published = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
            comparable_cutoff = cutoff
            if published.tzinfo is not None and comparable_cutoff.tzinfo is None:
                comparable_cutoff = comparable_cutoff.replace(tzinfo=published.tzinfo)
            if published <= comparable_cutoff:
                result.append({**item, "olay_sinifi": kap_olayi_sinifla(str(item.get("text", "")))})
        except (TypeError, ValueError):
            continue
    return sorted(result, key=lambda x: str(x["published_at"]))


def kap_web_deneme(symbol: str, gun: int = 14) -> Dict[str, Any]:
    """
    Ücretsiz KAP web denemesi.
    KAP tarafı zaman zaman bot koruması / dinamik içerik kullandığı için veri gelmeyebilir.
    Veri gelmezse nötr döner ve programı bozmaz.
    """
    kod = sembol_temizle(symbol)

    try:
        # KAP'ın arama/sorgu sayfası sembolün geçtiği içerikleri döndürebilirse metinden puanlanır.
        # Bu ücretsiz yöntem resmi API değildir.
        url = f"https://www.kap.org.tr/tr/search/{kod}/1"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        r = requests.get(url, headers=headers, timeout=12)

        if r.status_code != 200 or not r.text:
            return {
                "kap_skor": 0,
                "kap_etiket": "Veri Yok",
                "kap_notu": f"KAP web erişimi başarısız veya boş cevap: HTTP {r.status_code}",
                "kap_basliklari": ""
            }

        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        temiz = soup.get_text(" ", strip=True)
        temiz = re.sub(r"\s+", " ", temiz)

        if kod.lower() not in temiz.lower():
            return {
                "kap_skor": 0,
                "kap_etiket": "Veri Yok",
                "kap_notu": "KAP aramasında sembole ait içerik bulunamadı",
                "kap_basliklari": "",
                "kap_url": url,
            }

        # Sembol geçen kısa parçaları çıkar
        parcalar = []
        for match in re.finditer(kod, temiz, flags=re.IGNORECASE):
            start = max(0, match.start() - 180)
            end = min(len(temiz), match.end() + 260)
            parcalar.append(temiz[start:end])

        # Arama sayfasındaki menü, fon ve genel şirket metinleri yanlış pozitif
        # üretmemeli. Yalnızca gerçek bildirim işaretleri taşıyan sembol bağlamı
        # otomatik puana katılır.
        bildirim_parcalari = [
            p for p in parcalar
            if "gönderim tarihi" in p.lower() and "bildirim" in p.lower()
        ]
        metin = " ".join(bildirim_parcalari[:8])
        puan = metin_puanla(metin) if metin else {
            "kap_skor": 0,
            "kap_etiket": "Nötr",
            "kap_notu": "Doğrulanabilir güncel bildirim metni bulunamadı; otomatik puan verilmedi",
        }

        basliklar = []
        for p in bildirim_parcalari[:5]:
            basliklar.append(p[:180].strip())

        return {
            "kap_skor": puan["kap_skor"],
            "kap_etiket": puan["kap_etiket"],
            "kap_notu": puan["kap_notu"],
            "kap_basliklari": " || ".join(basliklar),
            "kap_url": url,
            "kap_kaynak": "KAP herkese açık arama sayfası",
        }

    except Exception as e:
        return {
            "kap_skor": 0,
            "kap_etiket": "Hata",
            "kap_notu": f"KAP kontrol hatası: {e}",
            "kap_basliklari": "",
            "kap_url": f"https://www.kap.org.tr/tr/search/{kod}/1",
        }


def kap_toplu_analiz(symbols: List[str], bekleme: float = 0.2) -> Dict[str, Dict[str, Any]]:
    """
    Sembol listesi için KAP analizi.
    Performans için sadece seçilen adaylara uygulanması önerilir.
    """
    sonuc = {}

    for i, symbol in enumerate(symbols, start=1):
        print(f"KAP kontrol {i}/{len(symbols)}: {symbol}")
        sonuc[symbol] = kap_web_deneme(symbol)
        time.sleep(bekleme)

    return sonuc
