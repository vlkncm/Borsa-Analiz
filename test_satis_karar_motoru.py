import unittest

from satis_karar_motoru import satis_karari_uret


class SatisKararMotoruTests(unittest.TestCase):
    def test_gecersiz_fiyat_programi_dusurmeden_veri_yok_dondurur(self):
        result = satis_karari_uret({"price": None}, 100)
        self.assertEqual(result["satis_karari"], "VERİ YOK")
        self.assertEqual(result["yeni_stop"], 0.0)

    def test_stop_altinda_acil_cikis_uretir(self):
        result = satis_karari_uret(
            {"price": 89, "onerilen_stop": 90, "onerilen_satis": 120}, 100
        )
        self.assertEqual(result["satis_karari"], "ACİL ÇIK")
        self.assertEqual(result["kar_realizasyon_orani"], 100)

    def test_karda_stop_maliyetin_altina_inmez(self):
        result = satis_karari_uret(
            {"price": 110, "onerilen_stop": 90, "onerilen_satis": 130, "atr": 5},
            100,
        )
        self.assertGreaterEqual(result["yeni_stop"], 100.2)

    def test_metin_ve_nan_girdiler_guvenle_islenir(self):
        result = satis_karari_uret(
            {"price": "110", "onerilen_satis": float("nan"), "atr": "bozuk"},
            100,
        )
        self.assertEqual(result["satis_karari"], "TUT")
        self.assertAlmostEqual(result["kar_zarar_yuzde"], 10.0)


if __name__ == "__main__":
    unittest.main()
