from dataclasses import replace
import sqlite3

import pandas as pd

from karar_deposu import KararDeposu
from merkezi_karar_motoru import DecisionEngine, Kalibrasyon, KararGirdisi, Pozisyon
from trade_kanitlari import Outcome, label_trade_outcome


def calibrated(p=.70):
    return Kalibrasyon(kalibre=True, ornek_sayisi=120, hedef_once_stop=p,
                       stop_once_hedef=1-p, kari_geri_verme=.60, brier=.16)


def base(**changes):
    row = KararGirdisi(sembol="TEST", fiyat=100, veri_zamani="2026-08-27T15:00:00+03:00",
        atr=2, destek=98, direnc=106, piyasa_rejimi="POZITIF", sektor_destekliyor=True,
        veri_guncel=True, ohlcv_guvenilir=True, likit=True, kalibrasyon=calibrated())
    return replace(row, **changes)


def test_al_tum_kapilarla_tek_karardir():
    out = DecisionEngine().karar_ver(base())
    assert out.karar == "AL" and out.yeni_alim_karari == "AL"
    assert out.karar in {"AL", "ALMA", "BEKLE", "KAR AL", "SAT", "KARAR YOK"}


def test_pozisyonu_olan_ile_olmayan_farkli_karar_alir():
    engine = DecisionEngine()
    assert engine.karar_ver(base()).karar == "AL"
    quiet_calibration = replace(calibrated(), kari_geri_verme=.20)
    held = engine.karar_ver(base(pozisyon=Pozisyon(100, 80, vade="KISA"), kalibrasyon=quiet_calibration))
    assert held.karar == "BEKLE" and held.yeni_alim_karari == "AL"


def test_kalibrasyonsuz_yuzde_ve_al_yok():
    out = DecisionEngine().karar_ver(base(kalibrasyon=Kalibrasyon()))
    assert out.olasilik is None and "%" not in out.olasilik_metni and out.karar != "AL"


def test_negatif_ev_al_vermez_ve_maliyetler_dahildir():
    out = DecisionEngine().karar_ver(base(kalibrasyon=calibrated(.15), tahmini_kayma_pct=2))
    assert out.net_ev_pct < 0 and out.karar != "AL"


def test_seviyeler_fiyat_adimina_uygun():
    out = DecisionEngine().karar_ver(base())
    for value in (out.giris_alt, out.giris_ust, out.hedef_1, out.stop):
        assert round(value * 20) == value * 20


def test_ayni_mum_hedef_stop_stop_sayilir():
    bars = pd.DataFrame({"High": [110], "Low": [90]})
    assert label_trade_outcome(bars, 108, 94)[0] == Outcome.STOP_ONCE


def test_tavanda_ve_hareket_kacmissa_al_yok():
    assert DecisionEngine().karar_ver(base(tavanda=True)).karar == "ALMA"
    assert DecisionEngine().karar_ver(base(hareket_kacti=True, yeni_halka_arz=True)).karar == "ALMA"


def test_tknka_benzeri_kisa_gecmis_kaybolmaz_ama_sahte_olasilik_almaz():
    out = DecisionEngine().karar_ver(base(sembol="TKNKA", yeni_halka_arz=True,
        kalibrasyon=Kalibrasyon(), tavanda=True, hareket_kacti=True))
    assert out.sembol == "TKNKA" and out.karar == "ALMA" and out.olasilik is None


def test_kar_al_miktari_pozisyona_gore_hesaplanir():
    out = DecisionEngine().karar_ver(base(fiyat=115, pozisyon=Pozisyon(137, 80),
                                          ilk_hedef_goruldu=True, momentum_zayifliyor=True))
    assert out.karar == "KAR AL" and 0 < out.kar_alma_adet <= 137
    assert out.kalan_adet + out.kar_alma_adet == 137


def test_stop_gerceklesince_sat():
    out = DecisionEngine().karar_ver(base(pozisyon=Pozisyon(10, 105), stop_gerceklesti=True))
    assert out.karar == "SAT"


def test_eski_veride_karar_yok():
    out = DecisionEngine().karar_ver(base(veri_guncel=False))
    assert out.karar == "KARAR YOK"


def test_sqlite_karar_degistirilemez_gerceklesme_ayridir(tmp_path):
    repo = KararDeposu(tmp_path / "decisions.db")
    result = DecisionEngine().karar_ver(base()).as_dict()
    ok, row_id = repo.karar_ekle("TEST:1", result)
    assert ok
    db = sqlite3.connect(repo.path)
    try:
        try:
            db.execute("UPDATE decision_snapshots SET decision='SAT' WHERE id=?", (row_id,))
            assert False
        except sqlite3.IntegrityError:
            pass
    finally:
        db.close()
    assert repo.gerceklesme_ekle(row_id, "2026-08-28", {"net_getiri": 0.03})[0]


def test_sqlite_hatasi_taramayi_cokertmez(tmp_path):
    repo = KararDeposu(tmp_path / "d.db")
    ok, _ = repo.karar_ekle("x", {"sembol": "X", "karar": "AL"})
    assert ok
    ok, message = repo.karar_ekle("x", {"sembol": "X", "karar": "SAT"})
    assert not ok and message
