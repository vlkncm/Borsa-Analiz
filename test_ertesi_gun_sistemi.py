from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ertesi_gun_motoru import KalibrasyonKaniti, canli_teyit, erken_aday, purged_walk_forward_splits
from fiyat_limitleri import fiyat_adimi, pay_fiyat_limitleri
from t1_etiketleri import ozellikleri_tarih_kesiminde_kisitla, t1_etiketleri
from tahmin_deposu import TahminDeposu
from kap_modulu import yayin_anina_gore_aciklamalar
from bist_evreni import _yerel_liste


def sample_frame(n=220):
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(10, 13, n), index=idx)
    return pd.DataFrame({"Open": close*.995, "High": close*1.02, "Low": close*.99,
                         "Close": close, "Volume": np.linspace(15_000_000, 25_000_000, n)}, index=idx)


class ErtesiGunSistemiTests(unittest.TestCase):
    def test_paketli_aktif_bist_evreni_613_hisse_icerir(self):
        symbols = _yerel_liste()
        self.assertEqual(len(symbols), 613)
        self.assertTrue(all(symbol.endswith(".IS") for symbol in symbols))
        spec = Path("BorsaAnalizProMAX.spec").read_text(encoding="utf-8")
        build = Path("EXE_VE_SETUP_OLUSTUR.bat").read_text(encoding="utf-8")
        self.assertIn("bist_hisseleri_613_aktif.txt", spec)
        self.assertIn("bist_hisseleri_613_aktif.txt", build)

    def test_tavan_fiyati_fiyat_adimina_asagi_yuvarlanir(self):
        result = pay_fiyat_limitleri(49.99)
        self.assertEqual(str(result.ust_limit), "54.95")
        self.assertEqual(str(fiyat_adimi(result.ust_limit)), "0.05")

    def test_intraday_8_ve_kapanis_8_ayridir(self):
        f = pd.DataFrame({"Open": [100, 100], "High": [101, 109], "Low": [99, 98],
                          "Close": [100, 102], "Volume": [1, 1]}, index=pd.date_range("2026-01-01", periods=2))
        labels = t1_etiketleri(f)
        self.assertEqual(labels.iloc[0]["t1_intraday_8"], 1)
        self.assertEqual(labels.iloc[0]["t1_close_8"], 0)

    def test_son_satir_negatif_etiket_yapilmaz(self):
        labels = t1_etiketleri(sample_frame(3))
        self.assertTrue(pd.isna(labels.iloc[-1]["t1_intraday_8"]))

    def test_t_sonrasi_ozellik_sizintisi_reddedilir(self):
        with self.assertRaises(ValueError):
            ozellikleri_tarih_kesiminde_kisitla(sample_frame(3), "2025-01-02")

    def test_walk_forward_sirali_purge_ve_embargo(self):
        for train, test in purged_walk_forward_splits(100, 40, 10, purge=2, embargo=2):
            self.assertLess(train.max(), test.min())
            self.assertGreaterEqual(test.min()-train.max(), 5)

    def test_kalibrasyon_yokken_yuzde_uydurulmaz(self):
        row = erken_aday("TEST.IS", sample_frame(), "YATAY", kap={"kap_etiket": "Veri Yok"})
        self.assertIsNone(row["%8+ Olasılığı"])
        self.assertFalse(row["Olasılık Güvenilir"])

    def test_canli_veri_yokken_sahte_teyit_yok(self):
        meta = SimpleNamespace(is_delayed=True, is_stale=False)
        result = canli_teyit({}, sample_frame(5), meta)
        self.assertEqual(result["Canlı Durum"], "TEYİT GELMEDİ")

    def test_tahmin_degistirilemez_gerceklesme_ayridir(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"history.sqlite3"; store = TahminDeposu(path)
            record = {"prediction_key":"k", "predicted_at":datetime.now().isoformat(), "session_date":"2026-01-01",
                      "symbol":"TEST.IS", "previous_close":10, "ceiling_price":11, "p_intraday_8":None,
                      "p_ceiling":None, "p_close_8":None, "market_regime":"YATAY", "sector_score":None,
                      "status":"TEYİT BEKLİYOR", "reasons_json":[], "risks_json":[], "cutoff_at":"2026-01-01",
                      "model_version":"ref", "probability_reliable":0}
            pid = store.tahmin_ekle(record)
            with closing(sqlite3.connect(path)) as db:
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("UPDATE predictions SET status='X' WHERE id=?", (pid,))
            store.gerceklesme_ekle(pid, {"evaluated_at":datetime.now().isoformat(), "intraday_8":1, "hit_ceiling":0,
                "intraday_max_return":.09, "close_return":.02, "max_adverse_excursion":-.01,
                "target_before_stop":1, "successful":1, "duration_correct":1})
            self.assertEqual(store.performans()["toplam"], 1)

    def test_esikler_aday_yoksa_dusurulmez(self):
        f = sample_frame(); f["Volume"] = 10
        row = erken_aday("TEST.IS", f, "RİSKTEN KAÇIŞ", kap={"kap_etiket":"Olumsuz"})
        self.assertNotIn(row["Durum"], {"GÜÇLÜ ERTESİ GÜN ADAYI", "ERKEN BİRİKİM ADAYI"})

    def test_kap_yayin_saati_gelecekten_sizmaz(self):
        items = [{"published_at":"2026-01-02T17:59:00", "text":"Yeni sözleşme"},
                 {"published_at":"2026-01-02T18:01:00", "text":"Yeni yatırım"}]
        visible = yayin_anina_gore_aciklamalar(items, datetime.fromisoformat("2026-01-02T18:00:00"))
        self.assertEqual(len(visible), 1)
        self.assertIn("SOZLESME", visible[0]["olay_sinifi"])

    def test_ertesi_gun_worker_tum_bist_kaynagini_kullanir(self):
        source = Path("app_qt.py").read_text(encoding="utf-8")
        block = source[source.index("class NextDayWorker"):source.index("class NextDayPage")]
        self.assertIn("tum_bist_hisseleri()", block)
        self.assertNotIn("bist30_hisseleri", block)

    def test_excel_eylemi_arayuzde_yoktur(self):
        source = Path("app_qt.py").read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("EXCEL RAPORUNU', source)


if __name__ == "__main__": unittest.main()
