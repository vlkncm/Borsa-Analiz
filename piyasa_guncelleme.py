from __future__ import annotations

import json
import re
import time
from io import StringIO
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests


KAP_BIST_URL = "https://kap.org.tr/tr/bist-sirketler"
SPK_IPO_APPLICATIONS_URL = "https://spk.gov.tr/istatistikler/basvurular/ilk-halka-arz-basvurusu"
SPK_IPO_DATA_URL = "https://spk.gov.tr/ihrac-verileri/ilk-halka-arz-verileri"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
}

MIN_VALID_SYMBOLS = 350
MAX_VALID_SYMBOLS = 900
MAX_DAILY_CHANGE_RATIO = 0.20
REQUEST_RETRIES = 3
REQUEST_TIMEOUT = 30


def veri_ana_klasoru() -> Path:
    belgeler = Path.home() / "Documents"
    if not belgeler.exists():
        belgeler = Path.home()

    klasor = belgeler / "Borsa Analiz Pro MAX" / "piyasa_verileri"
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def guncel_hisse_dosyasi() -> Path:
    return veri_ana_klasoru() / "bist_hisseleri_guncel.txt"


def halka_arz_csv_dosyasi() -> Path:
    return veri_ana_klasoru() / "halka_arzlar_guncel.csv"


def metadata_dosyasi() -> Path:
    return veri_ana_klasoru() / "guncelleme_bilgisi.json"


def hata_log_dosyasi() -> Path:
    return veri_ana_klasoru() / "guncelleme_hatalari.log"


def _log_hata(mesaj: str) -> None:
    try:
        with hata_log_dosyasi().open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {mesaj}\n")
    except Exception:
        pass


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def _atomic_write_csv(path: Path, df: pd.DataFrame) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(path)


def _request(url: str) -> requests.Response:
    last_error = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(attempt * 1.5)
    raise RuntimeError(f"{url} alınamadı: {last_error}")


def _html_tablolari(url: str) -> List[pd.DataFrame]:
    """
    pandas'a ham HTML metni doğrudan verilmez; aksi halde yeni pandas
    sürümlerinde metin dosya yolu sanılabilir.
    """
    response = _request(url)
    try:
        tablolar = pd.read_html(StringIO(response.text))
    except Exception as exc:
        raise ValueError(f"HTML tablo okunamadı: {exc}") from exc
    if not tablolar:
        raise ValueError("Sayfada okunabilir tablo bulunamadı.")
    return tablolar


def _kolon_duzlestir(df: pd.DataFrame) -> pd.DataFrame:
    sonuc = df.copy()
    if isinstance(sonuc.columns, pd.MultiIndex):
        sonuc.columns = [
            " ".join(str(x) for x in col if str(x) != "nan").strip()
            for col in sonuc.columns
        ]
    else:
        sonuc.columns = [str(c).strip() for c in sonuc.columns]
    return sonuc


def _metin_sadelestir(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _eslestirme_metni(value: Any) -> str:
    text = _metin_sadelestir(value).upper().replace("İ", "I")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9]", "", text)
    for ek in [
        "ANONIMSIRKETI", "ANONIMSIRKET", "AS",
        "SANAYIVETICARET", "TICARETVESANAYI"
    ]:
        text = text.replace(ek, "")
    return text


def _sembol_cikar(value: Any) -> str:
    text = _metin_sadelestir(value).upper().replace(".E", "").replace(".IS", "")
    adaylar = re.findall(r"(?<![A-Z0-9])[A-Z0-9]{3,6}(?![A-Z0-9])", text)

    yasak = {
        "ISTANBUL", "ANKARA", "IZMIR", "TURKIYE", "SIRKET",
        "SANAYI", "TICARET", "DENETIM", "BAGIMSIZ",
        "YATIRIM", "MENKUL", "PAZAR"
    }

    for aday in adaylar:
        if aday not in yasak and any(ch.isalpha() for ch in aday):
            return aday
    return ""


def _liste_dogrula(yeni: List[str], eski: List[str]) -> Tuple[bool, str]:
    temiz = [s for s in yeni if re.fullmatch(r"[A-Z0-9]{3,6}\.IS", s)]
    if len(temiz) != len(set(temiz)):
        return False, "Yeni listede tekrar eden semboller var."

    if not (MIN_VALID_SYMBOLS <= len(temiz) <= MAX_VALID_SYMBOLS):
        return False, f"Sembol sayısı güvenli aralık dışında: {len(temiz)}"

    if eski and len(eski) >= MIN_VALID_SYMBOLS:
        fark = len(set(yeni).symmetric_difference(set(eski)))
        oran = fark / max(len(eski), 1)
        if oran > MAX_DAILY_CHANGE_RATIO:
            return False, f"Liste değişimi olağandışı yüksek: %{oran*100:.1f}"

    return True, "Liste doğrulandı."


def aktif_bist_hisselerini_getir() -> Tuple[List[str], pd.DataFrame]:
    """
    KAP'ın yeni Next.js sayfasında şirket kodları klasik HTML tablosunda değil,
    gömülü React verisinde stockCode alanlarıyla bulunuyor.
    Önce bu alanlar okunur; eski tablo yapısı varsa yedek yöntem kullanılır.
    """
    response = _request(KAP_BIST_URL)
    html = response.text

    # Yeni KAP yapısı: \"stockCode\":\"ACSEL\"
    kodlar = re.findall(
        r'\\?"stockCode\\?"\s*:\s*\\?"([A-Z0-9]{3,6})\\?"',
        html
    )

    # Bazı yanıtlar kaçışsız JSON içerebilir.
    if not kodlar:
        kodlar = re.findall(
            r'"stockCode"\s*:\s*"([A-Z0-9]{3,6})"',
            html
        )

    kodlar = sorted(set(kodlar))
    if len(kodlar) >= MIN_VALID_SYMBOLS:
        return [f"{kod}.IS" for kod in kodlar], pd.DataFrame(
            {"Hisse Kodu": kodlar}
        )

    # Eski KAP tablo biçimi için yedek yöntem
    try:
        tablolar = pd.read_html(StringIO(html))
    except Exception:
        tablolar = []

    en_iyi = pd.DataFrame()
    semboller: List[str] = []

    for tablo in tablolar:
        tablo = _kolon_duzlestir(tablo)
        bulunan = []

        for _, row in tablo.iterrows():
            for value in row.iloc[:3].tolist():
                sembol = _sembol_cikar(value)
                if sembol:
                    bulunan.append(sembol)
                    break

        bulunan = list(dict.fromkeys(bulunan))
        if len(bulunan) > len(semboller):
            semboller = bulunan
            en_iyi = tablo

    yahoo_semboller = sorted({f"{s}.IS" for s in semboller})
    if len(yahoo_semboller) < MIN_VALID_SYMBOLS:
        raise ValueError(
            f"KAP sayfasından yeterli hisse kodu çıkarılamadı: "
            f"{len(yahoo_semboller)} kod"
        )

    return yahoo_semboller, en_iyi

def _uygun_tabloyu_bul(tablolar: List[pd.DataFrame], anahtarlar: List[str]) -> pd.DataFrame:
    en_iyi = pd.DataFrame()
    en_iyi_skor = -1

    for tablo in tablolar:
        tablo = _kolon_duzlestir(tablo)
        kolon_metni = " ".join(tablo.columns).lower()
        skor = sum(1 for key in anahtarlar if key.lower() in kolon_metni)

        if skor > en_iyi_skor or (skor == en_iyi_skor and len(tablo) > len(en_iyi)):
            en_iyi = tablo
            en_iyi_skor = skor

    return en_iyi


def _kolon_bul(df: pd.DataFrame, kelimeler: List[str]) -> str | None:
    for kolon in df.columns:
        kucuk = str(kolon).lower()
        if any(k in kucuk for k in kelimeler):
            return kolon
    return None


def halka_arz_basvurularini_getir() -> pd.DataFrame:
    tablolar = _html_tablolari(SPK_IPO_APPLICATIONS_URL)
    df = _uygun_tabloyu_bul(tablolar, ["şirket", "başvuru", "tarih"])

    if df.empty:
        raise ValueError("SPK halka arz başvuru tablosu bulunamadı.")

    sirket_col = _kolon_bul(df, ["şirket", "ortaklık", "unvan", "ünvan"])
    tarih_col = _kolon_bul(df, ["tarih", "başvuru"])

    if sirket_col is None:
        adaylar = [
            c for c in df.columns
            if not any(k in str(c).lower() for k in ["sıra", "no", "tarih"])
        ]
        if not adaylar:
            raise ValueError("Şirket sütunu tespit edilemedi.")
        sirket_col = adaylar[0]

    if tarih_col is None:
        tarih_col = df.columns[-1]

    sonuc = pd.DataFrame({
        "Şirket": df[sirket_col].map(_metin_sadelestir),
        "Başvuru Tarihi": df[tarih_col].map(_metin_sadelestir),
    })

    sonuc = sonuc[
        sonuc["Şirket"].str.len().gt(3)
        & ~sonuc["Şirket"].str.lower().isin(["nan", "şirket", "ortaklık"])
    ].drop_duplicates("Şirket")

    if len(sonuc) == 0:
        raise ValueError("SPK başvuru listesi boş döndü.")

    return sonuc


def tamamlanan_halka_arzlari_getir() -> pd.DataFrame:
    tablolar = _html_tablolari(SPK_IPO_DATA_URL)
    df = _uygun_tabloyu_bul(
        tablolar,
        ["kod", "şirket", "fiyat", "halka arz", "sermaye"]
    )

    if df.empty:
        return pd.DataFrame()

    kod_col = _kolon_bul(df, ["kod", "işlem"])
    sirket_col = _kolon_bul(df, ["şirket", "ortaklık", "unvan", "ünvan"])
    fiyat_col = _kolon_bul(df, ["fiyat"])
    tarih_col = _kolon_bul(df, ["tarih"])

    rows = []
    for _, row in df.iterrows():
        sirket = _metin_sadelestir(row.get(sirket_col, "")) if sirket_col else ""
        kod = _sembol_cikar(row.get(kod_col, "")) if kod_col else ""

        if not kod:
            for value in row.iloc[:3].tolist():
                kod = _sembol_cikar(value)
                if kod:
                    break

        if not sirket:
            values = [_metin_sadelestir(v) for v in row.tolist()]
            sirket = max(values, key=len, default="")

        if len(sirket) < 4:
            continue

        rows.append({
            "Şirket": sirket,
            "İşlem Kodu": kod,
            "Halka Arz Fiyatı": _metin_sadelestir(row.get(fiyat_col, "")) if fiyat_col else "",
            "Halka Arz / İşlem Tarihi": _metin_sadelestir(row.get(tarih_col, "")) if tarih_col else "",
        })

    return pd.DataFrame(rows).drop_duplicates(subset=["Şirket", "İşlem Kodu"])


def halka_arz_listesini_olustur() -> pd.DataFrame:
    basvurular = halka_arz_basvurularini_getir()

    try:
        tamamlanan = tamamlanan_halka_arzlari_getir()
    except Exception as exc:
        _log_hata(f"Tamamlanan halka arz listesi okunamadı: {exc}")
        tamamlanan = pd.DataFrame()

    tamamlanan_map: Dict[str, Dict[str, Any]] = {}
    if not tamamlanan.empty:
        for _, row in tamamlanan.iterrows():
            tamamlanan_map[_eslestirme_metni(row["Şirket"])] = row.to_dict()

    rows = []
    for _, row in basvurular.iterrows():
        anahtar = _eslestirme_metni(row["Şirket"])
        tamam = tamamlanan_map.get(anahtar)

        if tamam:
            durum = "HALKA ARZ TAMAMLANDI / İŞLEM GÖRÜYOR"
            kod = tamam.get("İşlem Kodu", "")
            fiyat = tamam.get("Halka Arz Fiyatı", "")
            islem_tarihi = tamam.get("Halka Arz / İşlem Tarihi", "")
        else:
            durum = "SPK BAŞVURUSU YAPILDI / ONAY BEKLENİYOR"
            kod = ""
            fiyat = ""
            islem_tarihi = ""

        rows.append({
            "Şirket": row["Şirket"],
            "Durum": durum,
            "SPK Başvuru Tarihi": row["Başvuru Tarihi"],
            "Planlanan / İşlem Kodu": kod,
            "Halka Arz Fiyatı": fiyat,
            "İşlem Tarihi": islem_tarihi,
            "Resmî Başvuru Kaynağı": SPK_IPO_APPLICATIONS_URL,
            "Resmî Halka Arz Kaynağı": SPK_IPO_DATA_URL,
            "Son Güncelleme": datetime.now().strftime("%d.%m.%Y %H:%M"),
        })

    sonuc = pd.DataFrame(rows)

    if not sonuc.empty:
        durum_sirasi = {
            "SPK BAŞVURUSU YAPILDI / ONAY BEKLENİYOR": 0,
            "HALKA ARZ TAMAMLANDI / İŞLEM GÖRÜYOR": 1,
        }
        sonuc["_sira"] = sonuc["Durum"].map(durum_sirasi).fillna(9)
        sonuc = sonuc.sort_values(
            ["_sira", "SPK Başvuru Tarihi"],
            ascending=[True, False]
        ).drop(columns="_sira")

    return sonuc


def cache_halka_arz_oku() -> pd.DataFrame:
    dosya = halka_arz_csv_dosyasi()
    if not dosya.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(dosya, encoding="utf-8-sig")
    except Exception as exc:
        _log_hata(f"Halka arz önbelleği okunamadı: {exc}")
        return pd.DataFrame()


def cache_hisse_listesi_oku() -> List[str]:
    dosya = guncel_hisse_dosyasi()
    if not dosya.exists():
        return []
    try:
        return [
            line.strip()
            for line in dosya.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception as exc:
        _log_hata(f"Hisse listesi önbelleği okunamadı: {exc}")
        return []


def metadata_oku() -> Dict[str, Any]:
    dosya = metadata_dosyasi()
    if not dosya.exists():
        return {}
    try:
        return json.loads(dosya.read_text(encoding="utf-8"))
    except Exception:
        return {}


def veri_yasi_gun() -> int | None:
    meta = metadata_oku()
    tarih = meta.get("son_basarili_guncelleme")
    if not tarih:
        return None
    try:
        dt = datetime.fromisoformat(tarih)
        return max(0, (datetime.now() - dt).days)
    except Exception:
        return None


def tum_listeleri_guncelle() -> Dict[str, Any]:
    mesajlar = []
    hisse_basarili = False
    halka_basarili = False

    eski_hisseler = cache_hisse_listesi_oku()
    hisse_listesi = eski_hisseler

    try:
        yeni_hisseler, _ = aktif_bist_hisselerini_getir()
        gecerli, neden = _liste_dogrula(yeni_hisseler, eski_hisseler)

        if not gecerli:
            raise ValueError(neden)

        _atomic_write_text(
            guncel_hisse_dosyasi(),
            "\n".join(yeni_hisseler) + "\n"
        )
        hisse_listesi = yeni_hisseler
        hisse_basarili = True

        yeni = sorted(set(yeni_hisseler) - set(eski_hisseler))
        cikan = sorted(set(eski_hisseler) - set(yeni_hisseler))
        mesajlar.append(
            f"BIST listesi doğrulandı: {len(yeni_hisseler)} kod, "
            f"{len(yeni)} yeni, {len(cikan)} listeden çıkan."
        )
    except Exception as exc:
        _log_hata(f"BIST güncelleme hatası: {exc}")
        mesajlar.append(
            f"BIST listesi güncellenemedi. Son güvenilir liste kullanılacak: {exc}"
        )

    try:
        halka_df = halka_arz_listesini_olustur()

        # Boş/çok küçük sonuç bozuk sayfa belirtisi olabilir.
        if len(halka_df) < 1:
            raise ValueError("Halka arz listesi boş döndü.")

        _atomic_write_csv(halka_arz_csv_dosyasi(), halka_df)
        halka_basarili = True
        bekleyen = (
            halka_df["Durum"].str.contains("ONAY BEKLENİYOR", na=False).sum()
            if not halka_df.empty else 0
        )
        mesajlar.append(
            f"Halka arz listesi güncellendi: {len(halka_df)} kayıt, "
            f"{bekleyen} başvuru/onay bekleyen."
        )
    except Exception as exc:
        _log_hata(f"Halka arz güncelleme hatası: {exc}")
        halka_df = cache_halka_arz_oku()
        mesajlar.append(
            f"Halka arz listesi güncellenemedi. Son güvenilir kayıt kullanılacak: {exc}"
        )

    eski_meta = metadata_oku()
    son_basarili = eski_meta.get("son_basarili_guncelleme")

    if hisse_basarili or halka_basarili:
        son_basarili = datetime.now().isoformat(timespec="seconds")

    metadata = {
        "son_kontrol": datetime.now().isoformat(timespec="seconds"),
        "son_basarili_guncelleme": son_basarili,
        "bist_basarili": hisse_basarili,
        "halka_arz_basarili": halka_basarili,
        "hisse_sayisi": len(hisse_listesi),
        "halka_arz_kayit_sayisi": len(halka_df),
        "mesaj": " ".join(mesajlar),
    }

    _atomic_write_text(
        metadata_dosyasi(),
        json.dumps(metadata, ensure_ascii=False, indent=2)
    )

    return {
        "hisseler": hisse_listesi,
        "halka_arz_df": halka_df,
        "metadata": metadata,
        "mesaj": "\n".join(mesajlar),
        "veri_yasi_gun": veri_yasi_gun(),
    }
