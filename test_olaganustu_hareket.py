import unittest

from olaganustu_hareket import olaganustu_hareket_degerlendir


class OlaganustuHareketTests(unittest.TestCase):
    def test_unsupported_low_liquidity_surge_is_blocked(self):
        result = olaganustu_hareket_degerlendir({"price": 10, "ret_20": 35, "volume_ratio": 3.5, "ortalama_gunluk_islem_tutari": 500_000, "kap_skor": 0})
        self.assertTrue(result["kovalama_engeli"])
        self.assertEqual(result["resmi_kap_destegi"], "YOK / DOĞRULANAMADI")

    def test_normal_movement_is_not_labeled_extraordinary(self):
        result = olaganustu_hareket_degerlendir({"price": 100, "ret_20": 4, "volume_ratio": 1.1, "ortalama_gunluk_islem_tutari": 50_000_000})
        self.assertFalse(result["olaganustu_hareket"])
        self.assertFalse(result["kovalama_engeli"])


if __name__ == "__main__":
    unittest.main()
