import unittest
from unittest.mock import patch

import borsa_tarayici
import main
from app_qt import normalize_symbol
from bist30 import BIST30_DONEMI, BIST30_KUMESI, BIST30_SEMBOLLERI, normalize_bist_sembolu


class Bist30EvreniTests(unittest.TestCase):
    def test_evren_tam_30_benzersiz_gecerli_sembolden_olusur(self):
        self.assertEqual(len(BIST30_SEMBOLLERI), 30)
        self.assertEqual(len(BIST30_KUMESI), 30)
        self.assertTrue(all(symbol.endswith(".IS") for symbol in BIST30_SEMBOLLERI))
        self.assertIn("2026-Q3", BIST30_DONEMI)

    def test_eski_genis_liste_artik_kullanilmaz(self):
        with patch("main.karantinadaki_semboller", return_value=set()):
            self.assertEqual(main.hisseleri_txt_oku("bist_hisseleri_613_aktif.txt"), list(BIST30_SEMBOLLERI))

    def test_bist30_disi_tek_hisse_kabul_edilir(self):
        self.assertEqual(normalize_symbol("MEGMT"), "MEGMT.IS")
        self.assertEqual(normalize_symbol("ASELS"), "ASELS.IS")
        self.assertEqual(normalize_bist_sembolu("../bad"), "")

    def test_tarama_listesi_ve_benchmark_bist30dur(self):
        self.assertEqual(tuple(borsa_tarayici.WATCHLIST), BIST30_SEMBOLLERI)
        self.assertEqual(borsa_tarayici.SURPRISE_LIST, [])
        with patch("borsa_tarayici.guvenli_yf_download", return_value=None) as download:
            borsa_tarayici._BENCHMARK_CACHE = None
            borsa_tarayici.bist100_verisi()
        download.assert_called_once_with("XU030.IS", period="2y", interval="1d", retries=1)


if __name__ == "__main__":
    unittest.main()
