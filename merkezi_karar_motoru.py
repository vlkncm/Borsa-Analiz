"""Tek ve ihtiyatli son kullanici karar motoru.

Bu modul gostergeleri karar gibi sunmaz. Kalibre edilmis ornek disi kanit,
islem ekonomisi, pozisyon ve uygulanabilirlik kapilarini tek sozlesmede toplar.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any, Mapping

from fiyat_limitleri import fiyat_adimi
from trade_kanitlari import CostConfig, expected_value


KARARLAR = {"AL", "ALMA", "BEKLE", "KAR AL", "SAT", "KARAR YOK"}
VADELER = {"GUNLUK", "T+1", "KISA", "ORTA"}


@dataclass(frozen=True)
class Pozisyon:
    adet: int = 0
    ortalama_maliyet: float | None = None
    alis_tarihi: str | None = None
    daha_once_satilan: int = 0
    vade: str = "KISA"
    azami_kayip_pct: float | None = None

    @property
    def var(self) -> bool:
        return self.adet > 0 and self.ortalama_maliyet is not None and self.ortalama_maliyet > 0


@dataclass(frozen=True)
class Kalibrasyon:
    kalibre: bool = False
    ornek_sayisi: int = 0
    hedef_once_stop: float | None = None
    stop_once_hedef: float | None = None
    pozitif_getiri: float | None = None
    getiri_3: float | None = None
    getiri_5: float | None = None
    getiri_8: float | None = None
    tavan: float | None = None
    kari_geri_verme: float | None = None
    brier: float | None = None
    yontem: str | None = None
    kesim_zamani: str | None = None

    def guvenilir(self, minimum: int = 30) -> bool:
        probs = (self.hedef_once_stop, self.stop_once_hedef)
        return self.kalibre and self.ornek_sayisi >= minimum and all(
            value is not None and 0 <= value <= 1 for value in probs
        ) and math.isclose(sum(probs), 1.0, abs_tol=.08)


@dataclass(frozen=True)
class KararGirdisi:
    sembol: str
    fiyat: float
    veri_zamani: str | None
    vade: str = "KISA"
    atr: float | None = None
    destek: float | None = None
    direnc: float | None = None
    piyasa_rejimi: str = "BILINMIYOR"
    sektor_destekliyor: bool | None = None
    veri_guncel: bool = False
    ohlcv_guvenilir: bool = False
    likit: bool = True
    tahmini_kayma_pct: float = .10
    likidite_maliyeti_pct: float = 0.0
    tavanda: bool = False
    asiri_uzamis: bool = False
    trend_bozuldu: bool = False
    stop_gerceklesti: bool = False
    kritik_negatif_haber: bool = False
    momentum_zayifliyor: bool = False
    ilk_hedef_goruldu: bool = False
    yeni_halka_arz: bool = False
    hareket_kacti: bool = False
    kalibrasyon: Kalibrasyon = field(default_factory=Kalibrasyon)
    pozisyon: Pozisyon = field(default_factory=Pozisyon)
    model_surumu: str = "decision-engine-1.0"
    ozellikler: Mapping[str, Any] = field(default_factory=dict)
    eksik_ozellikler: tuple[str, ...] = ()


@dataclass(frozen=True)
class KararSonucu:
    sembol: str
    karar: str
    yeni_alim_karari: str
    elde_olan_karari: str
    sunum_karari: str
    olasilik: float | None
    olasilik_metni: str
    kalibrasyon_durumu: str
    net_ev_pct: float | None
    risk_getiri: float | None
    giris_alt: float | None
    giris_ust: float | None
    hedef_1: float | None
    hedef_2: float | None
    stop: float | None
    kapanis_stop: float | None
    hareketli_stop: float | None
    kar_koruma: float | None
    kar_alma_pct: int
    kar_alma_adet: int
    kalan_adet: int
    beklenen_sure: str
    nedenler: tuple[str, ...]
    riskler: tuple[str, ...]
    degisim_kosullari: tuple[str, ...]
    veri_zamani: str | None
    model_surumu: str
    kullanilan_ozellikler: tuple[str, ...]
    eksik_ozellikler: tuple[str, ...]
    kayit_zamani: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round_tick(value: float | None) -> float | None:
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    step = fiyat_adimi(value)
    rounded = (Decimal(str(value)) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
    return float(rounded)


class DecisionEngine:
    """AL/ALMA/BEKLE/KAR AL/SAT kararlarinin tek sahibi."""

    def __init__(self, minimum_ornek: int = 30, min_rr: float = 1.5,
                 costs: CostConfig | None = None):
        self.minimum_ornek = minimum_ornek
        self.min_rr = min_rr
        self.costs = costs or CostConfig()

    def karar_ver(self, g: KararGirdisi) -> KararSonucu:
        vade = g.vade.upper()
        temel_veri = g.fiyat > 0 and g.veri_zamani is not None and g.veri_guncel and g.ohlcv_guvenilir
        atr = g.atr if g.atr and math.isfinite(g.atr) and g.atr > 0 else None
        seviyeler_var = temel_veri and atr is not None
        levels = self._seviyeler(g, atr) if seviyeler_var else (None,) * 8
        giris_alt, giris_ust, hedef1, hedef2, stop, kapanis_stop, trail, koruma = levels
        rr = None
        if levels[0] and hedef1 and stop and giris_ust and giris_alt:
            rr = (hedef1 / giris_ust - 1) / max(1e-9, 1 - stop / giris_alt)

        k = g.kalibrasyon
        calibrated = k.guvenilir(self.minimum_ornek)
        net_ev = None
        if calibrated and hedef1 and stop and giris_ust:
            ev = expected_value(
                {"HEDEF_ONCE": k.hedef_once_stop, "STOP_ONCE": k.stop_once_hedef, "SURE_DOLDU": 0.0},
                (hedef1 / giris_ust - 1) * 100,
                (1 - stop / giris_ust) * 100,
                0.0,
                self.costs,
            )
            net_ev = ev["net_beklenti_pct"] - g.tahmini_kayma_pct - g.likidite_maliyeti_pct

        critical = g.tavanda or not g.likit or g.kritik_negatif_haber or g.hareket_kacti
        market_ok = g.piyasa_rejimi.upper() not in {"RISK_OFF", "RISKten KACIS", "BILINMIYOR"}
        regime_ok = market_ok and g.sektor_destekliyor is not False
        al_ok = all((temel_veri, seviyeler_var, calibrated, net_ev is not None and net_ev > 0,
                     rr is not None and rr >= self.min_rr, regime_ok, not critical,
                     not g.asiri_uzamis, not g.trend_bozuldu))

        if not temel_veri or not seviyeler_var:
            yeni = "KARAR YOK"
        elif al_ok:
            yeni = "AL"
        else:
            yeni = "ALMA"

        holder = self._holder_decision(g, calibrated, net_ev, hedef1, stop)
        main = holder if g.pozisyon.var else yeni
        profit_pct, profit_qty = self._profit_take(g, holder, hedef1, atr)
        reasons, risks, changes = self._explain(g, main, calibrated, net_ev, rr, hedef1, stop)
        if main == "ALMA" and not critical and temel_veri and (not calibrated or (net_ev is not None and net_ev >= 0)):
            presentation = "IZLE - uygun giris/teyit bekle"
        elif main == "KARAR YOK":
            presentation = "KARAR YOK - GUVENILIR VERI YETERSIZ"
        else:
            presentation = main
        probability = k.hedef_once_stop * 100 if calibrated else None
        return KararSonucu(
            sembol=g.sembol, karar=main, yeni_alim_karari=yeni, elde_olan_karari=holder,
            sunum_karari=presentation, olasilik=probability,
            olasilik_metni=(f"%{probability:.0f}" if probability is not None else
                            "Guvenilir olasilik icin yeterli gecmis sonuc bulunmuyor."),
            kalibrasyon_durumu=("KALIBRE" if calibrated else "YETERSIZ"), net_ev_pct=net_ev,
            risk_getiri=rr, giris_alt=giris_alt, giris_ust=giris_ust, hedef_1=hedef1,
            hedef_2=hedef2, stop=stop, kapanis_stop=kapanis_stop, hareketli_stop=trail,
            kar_koruma=koruma, kar_alma_pct=profit_pct, kar_alma_adet=profit_qty,
            kalan_adet=max(0, g.pozisyon.adet-profit_qty), beklenen_sure=self._duration(vade),
            nedenler=reasons[:3], riskler=risks[:3], degisim_kosullari=changes[:3],
            veri_zamani=g.veri_zamani, model_surumu=g.model_surumu,
            kullanilan_ozellikler=tuple(sorted(g.ozellikler)), eksik_ozellikler=g.eksik_ozellikler,
            kayit_zamani=datetime.now(timezone.utc).isoformat(),
        )

    def _seviyeler(self, g: KararGirdisi, atr: float):
        price = g.fiyat
        support = g.destek if g.destek and 0 < g.destek <= price * 1.03 else price - atr
        resistance = g.direnc if g.direnc and g.direnc > price else price + 2.2 * atr
        entry_low = max(.01, min(price, support + .15 * atr))
        entry_high = min(price + .25 * atr, max(price, support + .45 * atr))
        stop = min(entry_low - .2 * atr, support - .65 * atr)
        target1 = max(resistance, entry_high + 1.8 * (entry_high - stop))
        target2 = target1 + 1.5 * atr
        return tuple(_round_tick(x) for x in (
            entry_low, entry_high, target1, target2, stop, stop + .25 * atr,
            price - 1.8 * atr, price - 1.2 * atr,
        ))

    def _holder_decision(self, g, calibrated, net_ev, target, stop):
        p = g.pozisyon
        if not p.var:
            return "BEKLE" if g.fiyat > 0 else "KARAR YOK"
        if g.stop_gerceklesti or g.kritik_negatif_haber or (g.trend_bozuldu and net_ev is not None and net_ev < 0):
            return "SAT"
        profitable = g.fiyat > float(p.ortalama_maliyet)
        if profitable and (g.ilk_hedef_goruldu or g.momentum_zayifliyor or
                           (calibrated and g.kalibrasyon.kari_geri_verme is not None and g.kalibrasyon.kari_geri_verme >= .55)):
            return "KAR AL"
        if not calibrated or net_ev is None:
            return "KARAR YOK"
        return "BEKLE" if net_ev >= 0 and not g.trend_bozuldu else "SAT"

    def _profit_take(self, g, decision, target, atr):
        if decision != "KAR AL" or not g.pozisyon.var or not atr:
            return 0, 0
        cost = float(g.pozisyon.ortalama_maliyet)
        profit_at_risk = max(0.0, (g.fiyat / cost - 1) / max(atr / g.fiyat, .01))
        giveback = g.kalibrasyon.kari_geri_verme or 0.0
        target_progress = 1.0 if g.ilk_hedef_goruldu else min(1.0, g.fiyat / target) if target else 0.0
        raw = 15 + 18 * min(profit_at_risk / 4, 1) + 22 * giveback + 15 * target_progress + (10 if g.momentum_zayifliyor else 0)
        pct = int(min(75, max(10, round(raw / 5) * 5)))
        qty = min(g.pozisyon.adet, max(1, round(g.pozisyon.adet * pct / 100)))
        return pct, qty

    @staticmethod
    def _duration(vade):
        return {"GUNLUK": "Ayni seans", "T+1": "1 islem gunu", "KISA": "5-20 islem gunu", "ORTA": "20-90 islem gunu"}.get(vade, "Belirsiz")

    @staticmethod
    def _explain(g, decision, calibrated, net_ev, rr, target, stop):
        reasons, risks, changes = [], [], []
        if decision == "AL": reasons += ["Kalibre edilmis kanit ve pozitif masraf sonrasi beklenti.", "Risk/getiri ve giris bolgesi uygun."]
        elif decision == "KAR AL": reasons += ["Mevcut kar geri verilme riski artiyor.", "Kademeli azaltim toplam riski dusuruyor."]
        elif decision == "SAT": reasons += ["Pozisyonun ana risk veya stop kosulu dogrulandi."]
        elif decision == "KARAR YOK": reasons += ["Guvenilir karar icin zorunlu veri veya kalibrasyon eksik."]
        else: reasons += ["Yeni alim icin tum zorunlu kapilar gecilmedi."]
        if not calibrated: risks.append("Olasilik kalibre degil; yuzde gosterilmez.")
        if g.tavanda: risks.append("Hisse tavanda; emrin gerceklesmesi dusuk olabilir.")
        if g.asiri_uzamis or g.hareket_kacti: risks.append("Hareket baslamis; gec giris riski yuksek.")
        if not g.likit: risks.append("Likidite veya fiyat kaymasi riski yuksek.")
        if target: changes.append(f"{target:.2f} TL hedef davranisi yeniden degerlendirilir.")
        if stop: changes.append(f"{stop:.2f} TL altinda risk senaryosu guclenir.")
        if not calibrated: changes.append("Yeterli ornek disi kalibrasyon olusursa karar yeniden hesaplanir.")
        return tuple(reasons), tuple(risks), tuple(changes)


def karar_girdisi_sozlukten(item: Mapping[str, Any], pozisyon: Pozisyon | None = None) -> KararGirdisi:
    """Mevcut analiz sozlugunu yeni motora guvenli, geriye uyumlu tasir."""
    evidence_n = int(item.get("karar_kanit_ornegi") or item.get("kisa_ornek") or 0)
    p = item.get("dogrulanmis_olasilik")
    p = float(p) / (100 if p is not None and float(p) > 1 else 1) if p is not None else None
    calibrated = bool(p is not None and evidence_n >= 30)
    cal = Kalibrasyon(kalibre=calibrated, ornek_sayisi=evidence_n,
                      hedef_once_stop=p, stop_once_hedef=(1-p if calibrated else None))
    return KararGirdisi(
        sembol=str(item.get("symbol") or item.get("Hisse") or ""), fiyat=float(item.get("price") or 0),
        veri_zamani=item.get("veri_zamani") or item.get("son_veri_zamani"),
        vade=(pozisyon.vade if pozisyon else "KISA"), atr=item.get("atr"),
        destek=item.get("ana_destek") or item.get("fib_destek"), direnc=item.get("fib_direnc"),
        piyasa_rejimi=str(item.get("piyasa_rejimi") or "BILINMIYOR"),
        sektor_destekliyor=item.get("sektor_destekliyor"), veri_guncel=bool(item.get("veri_guncel", False)),
        ohlcv_guvenilir=bool(item.get("veri_kalite_onayli", False)), likit=bool(item.get("likidite_uygun", True)),
        tavanda=bool(item.get("tavanda", False)), asiri_uzamis=bool(item.get("kovalama_engeli", False)),
        yeni_halka_arz=bool(item.get("yeni_halka_arz", False)), hareket_kacti="KACTI" in str(item.get("durum", "")).upper(),
        kalibrasyon=cal, pozisyon=pozisyon or Pozisyon(), ozellikler=item,
    )
