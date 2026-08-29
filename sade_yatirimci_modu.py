"""Profesyonel motor ciktilarini sade yatirimci sunumuna donusturur.

Bu modul yeni bir tahmin modeli degildir. Kaynak motorun guvenlik kapilarini
gevsetmez; yalniz karar adlarini, sureyi, guveni ve gorunen kolonlari ortaklastirir.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping

import pandas as pd


MAIN_COLUMNS = [
    "Hisse", "Karar", "Beklenen süre", "Güven düzeyi", "Güncel fiyat",
    "Alım bölgesi", "Hedef", "Stop",
]

TECHNICAL_MAIN_TOKENS = (
    "T+1", "T+2", "FEATURE HASH", "ARTEFAKT", "KALİBRASYON YÖNTEMİ",
    "BRIER", "HAM SKOR", "CACHE", "EMA", "RSI", "MACD", "ADX", "ATR",
)


def _value(row: Mapping[str, Any], names: Iterable[str], default=None):
    for name in names:
        value=row.get(name)
        if value is None: continue
        try:
            if pd.isna(value): continue
        except (TypeError,ValueError): pass
        if str(value).strip() not in {"","None","nan","—"}: return value
    return default


def _number(row: Mapping[str, Any], names: Iterable[str]) -> float | None:
    value=_value(row,names)
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError):
        return None


def _truth(row: Mapping[str, Any], names: Iterable[str]) -> bool:
    value=_value(row,names,False)
    if isinstance(value,str): return value.strip().casefold() in {"true","1","evet","yes","güvenilir","guvenilir"}
    return bool(value)


def confidence_evidence(row: Mapping[str, Any], analysis_id: str) -> tuple[str,str,float|None,int]:
    """Yalniz ayni vade/karara ait yeterli OOS kanit varsa guven sinifi verir."""
    sample_names=("Geçmiş Örnek Sayısı","OOS Örnek Sayısı","Doğrulama Örnek Sayısı",
                  "Kısa Kanıt Örneği","Orta Kanıt Örneği","Uzun Kanıt Örneği","Örnek Sayısı")
    probability_names=("Geçmiş Başarı %","Doğrulanmış Olasılık %","Hedef Önce Olasılığı %",
                       "T+1 %7+ Olasılığı","Model Olasılığı %","Başarı %")
    n=int(_number(row,sample_names) or 0); probability=_number(row,probability_names)
    explicitly_reliable=_truth(row,("Olasılık Güvenilir","probability_reliable","Kalibre Olasılık"))
    if probability is not None and probability <= 1: probability*=100
    if n<30 or probability is None or not (explicitly_reliable or n>=30):
        return "Ölçülemedi","Yeterli geçmiş sonuç bulunmuyor",None,n
    if probability>=75 and n>=100: level="Çok yüksek"
    elif probability>=65: level="Yüksek"
    elif probability>=55: level="Orta"
    else: level="Düşük"
    return level,f"Geçmiş benzer {n} sinyalde başarı: %{probability:.0f}. Garanti değildir.",probability,n


def _duration_bucket(days: float) -> str:
    if days<=1: return "Bugün"
    if days<=3: return "1–3 işlem günü"
    if days<=7: return "Yaklaşık 1 hafta"
    if days<=10: return "1–2 hafta"
    if days<=20: return "2–4 hafta"
    if days<=45: return "1–2 ay"
    return "2–3 ay"


def expected_duration(row: Mapping[str, Any], analysis_id: str) -> tuple[str,str]:
    sample=int(_number(row,("Geçmiş Örnek Sayısı","OOS Örnek Sayısı","Doğrulama Örnek Sayısı")) or 0)
    median=_number(row,("Başarılılarda Medyan Süre","Geçmiş Medyan Süre","Hedefe Ulaşma Medyanı"))
    if median is not None and sample>=30:
        day=max(1,int(round(median)))
        return _duration_bucket(day),f"Geçmiş benzer sinyallerin çoğu yaklaşık {day}. işlem gününde sonuçlandı."
    defaults={
        "daily_trade":"Bugün", "high_movement_radar":"1–3 işlem günü",
        "short":"1–2 hafta", "medium":"1–2 ay", "under50":"1–2 hafta",
        "fund_analysis":"2–3 ay", "portfolio":"2–4 hafta",
    }
    key=next((name for name in defaults if name in analysis_id.casefold()),"")
    if key:
        return defaults[key],"Süre bu analiz sayfasının yatırım vadesine dayanır; geçmiş medyan için yeterli örnek yok."
    return "Güvenilir şekilde hesaplanamadı","Yeterli geçmiş sonuç bulunmuyor."


def independent_evidence(row: Mapping[str, Any]) -> tuple[int,tuple[str,...]]:
    """Korelasyonlu indikatorleri degil, en fazla dört bagimsiz kanit grubunu sayar."""
    price=_number(row,("Güncel fiyat","Güncel Fiyat","Fiyat","Referans Fiyat","Mevcut Fiyat"))
    ema20=_number(row,("EMA20",)); ema50=_number(row,("EMA50",)); rsi=_number(row,("RSI",))
    rvol=_number(row,("Göreceli Hacim","RVOL","Hacim Oranı")); cmf=_number(row,("CMF","CMF 20"))
    market=str(_value(row,("Piyasa Rejimi",),"")).upper(); sector=_number(row,("Sektör Puanı",))
    trend=bool(price and ema20 and price>ema20 and (ema50 is None or ema20>ema50))
    momentum=bool(rsi is not None and 48<=rsi<=70)
    flow=bool((rvol is not None and rvol>=1.15) or (cmf is not None and cmf>.05))
    context=bool(market in {"POZİTİF","GÜÇLÜ POZİTİF","YATAY","OLUMLU"} and (sector is None or sector>=0))
    reasons=[]
    if flow: reasons.append("Hacim ve alım ilgisi belirgin biçimde güçleniyor.")
    if trend: reasons.append("Fiyat ana yükseliş eğilimini koruyor.")
    if momentum: reasons.append("Fiyat gücü aşırıya kaçmadan olumlu kalıyor.")
    if context: reasons.append("Genel piyasa koşulları hisse aleyhine görünmüyor.")
    return sum((trend,momentum,flow,context)),tuple(reasons)


def _data_is_current(row: Mapping[str, Any]) -> bool:
    freshness=str(_value(row,("data_freshness","Tazelik","Veri Durumu"),"GUNCEL")).upper()
    return not any(token in freshness for token in ("ESKİ","ESKI","STALE","YETERSİZ","YETERSIZ","HATA","MISSING"))


def _levels(row: Mapping[str, Any]):
    price=_number(row,("Güncel fiyat","Güncel Fiyat","Güncel","Fiyat","Referans Fiyat","Mevcut Fiyat","Güncel Değer"))
    low=_number(row,("Alım Alt","Önerilen Alış Alt","T+1 Giriş","Giriş","entry"))
    high=_number(row,("Alım Üst","Önerilen Alış Üst","T+1 Giriş","Giriş","entry"))
    target=_number(row,("Hedef","Önerilen Satış","Hedef 1","T+1 Hedef","target"))
    stop=_number(row,("Stop","Önerilen Stop","Stop Loss","T+1 Stop"))
    band=_value(row,("Alım bölgesi","Alım Bölgesi","Alış Bandı"))
    if band is None and low is not None and high is not None: band=f"{low:.2f}–{high:.2f} TL"
    valid=bool(price and target and stop and stop<price<target)
    return price,band,target,stop,valid


def _source_decision(row: Mapping[str, Any]) -> str:
    return str(_value(row,("Karar","T+1 Kararı","Ana Karar","Yatırım Kararı","Durum","Sonuç"),"")).upper()


def simplify_record(row: Mapping[str, Any], analysis_id: str, held: bool=False) -> dict[str,Any]:
    source=dict(row); raw=_source_decision(row); price,band,target,stop,levels_ok=_levels(row)
    confidence,confidence_text,probability,samples=confidence_evidence(row,analysis_id)
    duration,duration_text=expected_duration(row,analysis_id)
    evidence_score,evidence_reasons=independent_evidence(row)
    gates=str(_value(row,("T+1 Neden Kodları","Neden Kodu","gate_codes"),""))
    hard=any(code in gates for code in ("STALE_PRICE_DATA","MISSING_PRICE_DATA","MODEL_NOT_CALIBRATED",
             "MISSING_MODEL_FEATURES","LOW_LIQUIDITY","SLIPPAGE_RISK","MOVE_ALREADY_EXTENDED","NEGATIVE_KAP"))
    current=_data_is_current(row)
    reliable=confidence!="Ölçülemedi" or _truth(row,("Olasılık Güvenilir","probability_reliable"))
    elite=_truth(row,("T+1 Seçkin Aday","T+2 Seçkin Aday","eligible_elite"))
    strong=any(token in raw for token in ("AL ADAYI","BUGÜN AL","UYGUN BÖLGEDE AL","ALIM BÖLGESİNDE","GÜÇLÜ ADAY"))
    watch=strong or any(token in raw for token in ("BEKLE","İZLE","IZLE","TAKİP","TEYİT")) or elite

    if held:
        if "SAT" in raw: decision="SAT"
        elif "KÂR AL" in raw or "KAR AL" in raw: decision="KÂR AL"
        else: decision="BEKLE"
    elif not current:
        decision="VERİ YETERSİZ"
    elif "VERİ YETERSİZ" in raw or "KARAR YOK" in raw:
        decision="VERİ YETERSİZ"
    elif hard or any(token in raw for token in ("ALMA","FİYAT KOVALAMA","HAREKET KAÇTI","YÜKSEK RİSK")):
        decision="ALMA"
    elif strong and reliable and levels_ok and (elite or "high_movement" not in analysis_id):
        decision="AL"
    elif watch:
        decision="BEKLE"
    else:
        decision="ALMA"

    risks=[]
    if not current: risks.append("Fiyat verisi güncel değil; yeni işlem kararı verilmez.")
    if hard: risks.append("Zorunlu güvenlik kontrollerinden en az biri geçilmedi.")
    if stop is not None: risks.append(f"{stop:.2f} TL altında olumlu senaryo bozulur.")
    if not reliable: risks.append("Geçmiş başarı düzeyi güvenilir biçimde ölçülemedi.")
    changes=[]
    if target is not None: changes.append(f"{target:.2f} TL hedef bölgesine yaklaşırsa kâr alma değerlendirilir.")
    if stop is not None: changes.append(f"{stop:.2f} TL stop seviyesi kırılırsa eldeki pozisyon için SAT değerlendirilir.")
    changes.append("Hacim ve fiyat gücü zayıflarsa karar BEKLE/ALMA yönüne döner.")
    reason_list=list(evidence_reasons)
    if not reason_list:
        supplied=_value(row,("Kısa Neden","Gerekçe","Karar Nedenleri","Hisseye Özel Nedenler"))
        if supplied: reason_list.append(str(supplied).split("|")[0].strip())
    if not reason_list: reason_list.append("Kaynak analizde yeterli bağımsız olumlu kanıt oluşmadı.")
    symbol=str(_value(row,("Hisse","Sembol","Fon","Fon Kodu"),"—")).replace(".IS","")
    result={**source,"Hisse":symbol,"Karar":decision,"Beklenen süre":duration,"Güven düzeyi":confidence,
            "Güncel fiyat":price,"Alım bölgesi":band or "—","Hedef":target,"Stop":stop,
            "Kısa Neden":reason_list[0],"Neden AL?":tuple(reason_list[:4]),
            "Ana Risk":risks[0] if risks else "Belirgin ek risk kaydı yok; canlı fiyat yine doğrulanmalı.",
            "Karar Ne Zaman Değişir?":tuple(changes[:3]),"Güven Açıklaması":confidence_text,
            "Süre Açıklaması":duration_text,"Bağımsız Kanıt Grubu":evidence_score,
            "_main_eligible":bool(decision in ({"AL","BEKLE"} if not held else {"BEKLE","KÂR AL","SAT"}) and
                                  current and (watch or held) and (levels_ok or held or "fund_analysis" in analysis_id)),
            "_confidence_probability":probability,"_confidence_samples":samples}
    return result


def simple_investor_frame(frame: pd.DataFrame | None, analysis_id: str, max_results: int=5,
                          held_symbols: Iterable[str]=()) -> pd.DataFrame:
    if frame is None or frame.empty: return pd.DataFrame(columns=MAIN_COLUMNS)
    held={str(x).replace(".IS","").upper() for x in held_symbols}; rows=[]
    for raw in frame.to_dict("records"):
        symbol=str(_value(raw,("Hisse","Sembol","Fon","Fon Kodu"),"")).replace(".IS","").upper()
        rows.append(simplify_record(raw,analysis_id,symbol in held))
    work=pd.DataFrame(rows)
    work=work[work["_main_eligible"].fillna(False).astype(bool)].copy()
    if work.empty: return pd.DataFrame(columns=MAIN_COLUMNS)
    decision_priority=work["Karar"].map({"SAT":5,"KÂR AL":4,"AL":3,"BEKLE":2}).fillna(0)
    confidence_priority=work["Güven düzeyi"].map({"Çok yüksek":5,"Yüksek":4,"Orta":3,"Düşük":2,"Ölçülemedi":1}).fillna(0)
    evidence=pd.to_numeric(work.get("Bağımsız Kanıt Grubu"),errors="coerce").fillna(0)
    work["_simple_rank"]=decision_priority*100+confidence_priority*10+evidence
    return work.sort_values("_simple_rank",ascending=False).head(max_results).drop(columns="_simple_rank").reset_index(drop=True)


def main_columns_are_simple(columns: Iterable[str]) -> bool:
    return list(columns)==MAIN_COLUMNS and not any(token in " ".join(columns).upper() for token in TECHNICAL_MAIN_TOKENS)
