"""Sosyal medya reklam/metinlerini yatırım kararı yerine risk işareti olarak sınıflar."""
from __future__ import annotations

import re

KIRMIZI_BAYRAKLAR = {
    "kesin kazanç": 30, "garanti": 30, "risksiz": 25, "%100": 25,
    "tavan": 12, "roket": 10, "kaçırma": 10, "son fırsat": 12,
    "vip grup": 20, "telegram": 15, "whatsapp": 15, "özel sinyal": 18,
    "hemen al": 18, "şimdi al": 18,
}


def sosyal_medya_risk_analizi(metin: str) -> dict[str, object]:
    clean = str(metin or "").casefold()
    found = [phrase for phrase in KIRMIZI_BAYRAKLAR if phrase in clean]
    score = min(100, sum(KIRMIZI_BAYRAKLAR[x] for x in found))
    urls = len(re.findall(r"https?://|t\.me/|wa\.me/", clean))
    score = min(100, score + urls * 10)
    return {
        "sosyal_medya_risk_puani": score,
        "sosyal_medya_bayraklari": ", ".join(found) or "Belirgin riskli vaat bulunmadı",
        "sosyal_medya_sonuc": "KULLANMA — bağımsız resmî veriyle doğrula" if score >= 30 else "Yalnızca ek bilgi; işlem sinyali değildir",
    }
