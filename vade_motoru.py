from __future__ import annotations

import pandas as pd


GORUNEN_KOLONLAR = [
    "Hisse",
    "Veri Tarihi",
    "Veri Yaşı (Gün)",
    "İşlem Durumu",
    "Sinyal Güveni",
    "Risk %",
    "Yatırım Kararı",
    "Önerilen Alış Alt",
    "Önerilen Alış Üst",
    "Önerilen Satış",
    "Önerilen Stop",
    "Beklenen Getiri %",
    "Beklenen Süre",
    "Model Olasılığı %",
    "Karar Risk/Getiri",
    "Karar Nedenleri",
]


def _num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def vade_listeleri_uret(df: pd.DataFrame):
    """
    Aynı teknik veriyi üç farklı yatırım süresine göre puanlar.
    Kullanıcıya yalnızca en güçlü 5 aday gösterilir.
    """
    if df is None or df.empty:
        bos = pd.DataFrame(columns=GORUNEN_KOLONLAR)
        return bos, bos.copy(), bos.copy()

    work = df.copy()

    guven = _num(work, "v4 Güven Puanı", 50)
    olasilik = _num(work, "Model Olasılığı %", 50)
    getiri = _num(work, "Beklenen Getiri %", 0)
    rr = _num(work, "Karar Risk/Getiri", 0)
    fib = _num(work, "Fibonacci Puanı", 50)
    form = _num(work, "Formasyon Puanı", 0)
    rsi = _num(work, "RSI", 50)
    ret20 = _num(work, "Son 20 Gün %", 0)
    ret60 = _num(work, "Son 60 Gün %", 0)
    ret252 = _num(work, "Son 252 Gün %", 0)
    adx = _num(work, "ADX", 20)
    hacim = _num(work, "Hacim Oranı", 1)
    faaliyet = _num(work, "Faaliyet Puanı", 50)
    kanit = _num(work, "Profesyonel Kanıt Puanı", 0)
    kisa_guvenli = _num(work, "Kısa Güvenli Olasılık %", 0)
    orta_guvenli = _num(work, "Orta Güvenli Olasılık %", 0)
    uzun_guvenli = _num(work, "Uzun Güvenli Olasılık %", 0)

    karar = work.get("Yatırım Kararı", pd.Series("", index=work.index)).astype(str)
    uygun = karar.isin(["BUGÜN AL", "ALIM BÖLGESİNİ BEKLE", "İZLE"])

    fiyat = _num(work, "Fiyat")
    alis_alt = _num(work, "Önerilen Alış Alt")
    alis_ust = _num(work, "Önerilen Alış Üst")
    hedef = _num(work, "Önerilen Satış")
    stop = _num(work, "Önerilen Stop")
    veri_yasi = _num(work, "Veri Yaşı (Gün)", 999)
    risk_pct = ((alis_ust - stop) / alis_ust.mask(alis_ust == 0) * 100).fillna(0)
    temel_kalite = (
        uygun & (fiyat > 0) & (alis_alt > 0) & (alis_ust >= alis_alt) &
        (hedef > alis_ust) & (stop < alis_alt) & (rr >= 1.2) &
        (olasilik >= 55) & (veri_yasi <= 4) & risk_pct.between(0.5, 15)
    )

    work["_kisa"] = (
        guven * 0.22 + olasilik * 0.18 + fib * 0.13 + form * 0.13 +
        adx.clip(0, 50) * 0.10 + hacim.clip(0, 3) / 3 * 100 * 0.10 +
        getiri.clip(0, 35) / 35 * 100 * 0.09 +
        rr.clip(0, 4) / 4 * 100 * 0.05 + kanit * 0.10
    )
    # Aşırı RSI ve negatif kısa momentum cezaları.
    work.loc[rsi > 78, "_kisa"] -= 8
    work.loc[ret20 < -5, "_kisa"] -= 8

    work["_orta"] = (
        guven * 0.25 + olasilik * 0.18 + fib * 0.12 + form * 0.10 +
        ret20.clip(-20, 30).add(20) / 50 * 100 * 0.10 +
        ret60.clip(-30, 50).add(30) / 80 * 100 * 0.10 +
        rr.clip(0, 4) / 4 * 100 * 0.08 +
        faaliyet * 0.07 + kanit * 0.10
    )

    work["_uzun"] = (
        guven * 0.21 + olasilik * 0.12 + faaliyet * 0.22 +
        ret60.clip(-30, 60).add(30) / 90 * 100 * 0.10 +
        ret252.clip(-50, 100).add(50) / 150 * 100 * 0.08 +
        fib * 0.08 + rr.clip(0, 4) / 4 * 100 * 0.07 +
        adx.clip(0, 50) / 50 * 100 * 0.06 +
        getiri.clip(0, 50) / 50 * 100 * 0.06 + kanit * 0.10
    )

    def sec(score_col: str, sure: str, min_score: float, min_rr: float) -> pd.DataFrame:
        vade_kaniti = {"_kisa": kisa_guvenli, "_orta": orta_guvenli, "_uzun": uzun_guvenli}[score_col]
        kalite = temel_kalite & (work[score_col] >= min_score) & (rr >= min_rr) & (kanit >= 50) & (vade_kaniti >= 35)
        aday = work[kalite].copy()
        if aday.empty:
            return pd.DataFrame(columns=["Hisse", "Vade", "Vade Skoru"] + GORUNEN_KOLONLAR[1:])

        aday_fiyat = fiyat.loc[aday.index]
        aday_alt = alis_alt.loc[aday.index]
        aday_ust = alis_ust.loc[aday.index]
        durum = pd.Series("TEYİT BEKLE", index=aday.index, dtype=object)
        durum.loc[aday_fiyat.between(aday_alt, aday_ust)] = "ALIM BÖLGESİNDE"
        durum.loc[aday_fiyat > aday_ust] = "GERİ ÇEKİLME BEKLE"
        durum.loc[aday_fiyat < aday_alt] = "KIRILIM/TEYİT BEKLE"
        aday["İşlem Durumu"] = durum
        aday["Risk %"] = risk_pct.loc[aday.index].round(2)
        aday["Sinyal Güveni"] = pd.cut(
            aday[score_col], bins=[-float("inf"), 68, 78, float("inf")],
            labels=["ORTA", "YÜKSEK", "ÇOK YÜKSEK"], right=False,
        ).astype(str)

        aday = aday.sort_values(
            [score_col, "Model Olasılığı %", "Beklenen Getiri %"],
            ascending=[False, False, False],
        ).head(5)
        cols = [c for c in GORUNEN_KOLONLAR if c in aday.columns]
        sonuc = aday[cols].copy()
        sonuc.insert(1, "Vade", sure)
        sonuc.insert(2, "Vade Skoru", aday[score_col].round(1).values)
        return sonuc.reset_index(drop=True)

    return (
        sec("_kisa", "5-20 iş günü", 65, 1.4),
        sec("_orta", "1-3 ay", 62, 1.3),
        sec("_uzun", "3-12 ay", 60, 1.2),
    )
