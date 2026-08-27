from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from bist_evreni import tum_bist_hisseleri
from ertesi_gun_motoru import erken_aday
from fiyat_limitleri import pay_fiyat_limitleri
from sembol_esleme import bist_sembolu, saglayici_sembolu
from tarama_seffafligi import TaramaOzeti
from yeni_halka_arz import model_yolu, yeni_halka_arz_analizi


def history(n: int, start="2026-01-02", first=85.4, last=100.0) -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq="B")
    close = pd.Series(np.linspace(first, last, n), index=index)
    return pd.DataFrame({
        "Open": close*.99, "High": close*1.015, "Low": close*.985,
        "Close": close, "Volume": np.linspace(1_000_000, 2_000_000, n),
    }, index=index)


class SembolEslemeTests(unittest.TestCase):
    def test_bare_kap_ve_yahoo_ayni_hisseye_eslenir(self):
        for value in ("TKNKA", "TKNKA.E", "TKNKA.IS", " tknka.e "):
            self.assertEqual("TKNKA", bist_sembolu(value).kod)
            self.assertEqual("TKNKA.IS", saglayici_sembolu(value, "yahoo"))
            self.assertEqual("TKNKA.E", saglayici_sembolu(value, "kap"))


class EvrenYenilemeTests(unittest.TestCase):
    def test_yeni_sembol_gunluk_yenilemede_eklenir(self):
        with tempfile.TemporaryDirectory() as folder:
            old = {"created_at": (datetime.now()-timedelta(days=2)).isoformat(), "symbols": ["ASELS.IS"]*401}
            Path(folder, "tum_bist_evreni.json").write_text(json.dumps(old), encoding="utf-8")
            base = [f"X{i:03}.IS" for i in range(400)]
            with patch("bist_evreni._kap_sembolleri", return_value=base), patch("bist_evreni._bulten_sembolleri", return_value=["TKNKA.IS"]):
                symbols = tum_bist_hisseleri(folder)
            self.assertIn("TKNKA.IS", symbols)
            payload = json.loads(Path(folder, "tum_bist_evreni.json").read_text(encoding="utf-8"))
            self.assertIn("TKNKA.IS", payload["added"])
            self.assertIn("last_used_at", payload)
            self.assertIn("expires_at", payload)

    def test_bos_yenileme_son_gecerli_cacheyi_ezmez(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder, "tum_bist_evreni.json")
            cache.write_text(json.dumps({"created_at":"2026-01-01T00:00:00", "symbols":["ASELS.IS"]}), encoding="utf-8")
            with patch("bist_evreni._kap_sembolleri", side_effect=RuntimeError("offline")), patch("bist_evreni._bulten_sembolleri", return_value=[]):
                symbols = tum_bist_hisseleri(folder, refresh=True)
            self.assertIn("ASELS.IS", symbols)
            self.assertEqual(["ASELS.IS"], json.loads(cache.read_text(encoding="utf-8"))["symbols"])


class YeniHalkaArzModeliTests(unittest.TestCase):
    def test_islem_gunu_esikleri(self):
        expected = {3:"Cok yeni halka arz", 6:"Yeni halka arz", 14:"Yeni halka arz",
                    20:"Yeni halka arz", 50:"Sinirli gecmis", 200:"Standart analiz"}
        for count, level in expected.items():
            path, actual = model_yolu(count)
            self.assertEqual(level, actual)
            self.assertEqual("STANDART" if count >= 60 else "YENI_HALKA_ARZ", path)

    def test_ema200_yoklugu_hisseyi_silmez_ve_temel_veri_zorunlu_degildir(self):
        row = yeni_halka_arz_analizi("TEST.IS", history(14))
        self.assertEqual("YENI_HALKA_ARZ", row["Model Yolu"])
        self.assertFalse(row["Ozellik Kullanilabilirligi"]["ema200"])
        self.assertIn("Halka arz fiyati", row["Eksik Veriler"])
        self.assertIn(row["Neden Kodu"], {"INCLUDED_IPO", "REJECTED_LOW_SCORE", "REJECTED_HIGH_RISK", "REJECTED_LIQUIDITY"})

    def test_tknka_regresyonu_ve_t_artı_bir_sizintisi_yok(self):
        dates = pd.to_datetime(["2026-08-20","2026-08-21","2026-08-24","2026-08-25","2026-08-26","2026-08-27"])
        close = pd.Series([93.90,103.20,113.50,124.80,137.20,150.90], index=dates)
        frame = pd.DataFrame({"Open":close*.995,"High":close,"Low":close*.99,"Close":close,
                              "Volume":[10,11,12,13,14,20]}, index=dates)
        info = {"kotasyon_tarihi":"2026-08-20", "halka_arz_fiyati":85.40}
        before = erken_aday("TKNKA.E", frame, "YATAY", ipo_info=info, as_of="2026-08-26")
        after = erken_aday("TKNKA", frame, "YATAY", ipo_info=info, as_of="2026-08-27")
        self.assertEqual("TKNKA", before["Hisse"])
        self.assertEqual("YENI_HALKA_ARZ", before["Model Yolu"])
        self.assertEqual(5, before["İşlem Günü Sayısı"])
        self.assertEqual(137.20, before["Güncel Fiyat"])
        self.assertNotEqual(150.90, before["Güncel Fiyat"])
        self.assertEqual(6, after["İşlem Günü Sayısı"])
        self.assertEqual(150.90, after["Güncel Fiyat"])
        self.assertIn(after["Durum"], {"HAREKET KACTI - YUKSEK RISK", "YUKSEK RISK"})
        self.assertFalse(before["Olasılık Güvenilir"])

    def test_tknka_tavan_fiyati_adima_uygundur(self):
        self.assertEqual(150.90, float(pay_fiyat_limitleri(137.20).ust_limit))

    def test_veri_alinamadi_ile_dusuk_puan_ayridir(self):
        missing = yeni_halka_arz_analizi("TEST.IS", pd.DataFrame())
        low = yeni_halka_arz_analizi("TEST.IS", history(6, last=86))
        self.assertEqual("MISSING_PRICE_DATA", missing["Neden Kodu"])
        self.assertNotEqual("MISSING_PRICE_DATA", low["Neden Kodu"])

    def test_bos_ve_eksik_veri_cokertmez(self):
        row = yeni_halka_arz_analizi("TEST.IS", pd.DataFrame({"Close":[1]}))
        self.assertEqual("VERI ALINAMADI", row["Durum"])

    def test_uretim_kodunda_tknka_sabiti_yoktur(self):
        for name in ("yeni_halka_arz.py", "ertesi_gun_motoru.py", "bist_evreni.py", "sembol_esleme.py"):
            self.assertNotIn("TKNKA", Path(name).read_text(encoding="utf-8"))


class TaramaOzetiTests(unittest.TestCase):
    def test_sayaclar_toplamla_tutarlidir(self):
        summary = TaramaOzeti(aktif_bist_evreni=3)
        summary.kaydet({"Model Yolu":"YENI_HALKA_ARZ","Neden Kodu":"INCLUDED_IPO"}, True)
        summary.kaydet({"Model Yolu":"STANDART","Neden Kodu":"REJECTED_LOW_SCORE"}, True)
        summary.kaydet({"Model Yolu":"BELIRLENEMEDI","Neden Kodu":"MISSING_PRICE_DATA"}, False)
        result = summary.dict()
        self.assertEqual(3, result["taranmaya_calisilan"])
        self.assertEqual(2, result["basariyla_veri_alinan"])
        self.assertEqual(1, result["veri_alinamayan"])
        self.assertEqual(1, result["yeni_halka_arz_modeli"])


if __name__ == "__main__":
    unittest.main()
