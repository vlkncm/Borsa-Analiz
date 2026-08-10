import unittest

from canli_dogrulama import canli_sinyal_dogrula, wilson_alt_sinir
from karar_motoru import karar_uret


class CanliDogrulamaTests(unittest.TestCase):
    def test_wilson_lower_bound_penalizes_small_samples(self):
        self.assertLess(wilson_alt_sinir(70, 10), wilson_alt_sinir(70, 100))

    def test_weak_evidence_never_passes_validation(self):
        result = canli_sinyal_dogrula(
            {"kisa_ornek": 12, "kisa_tarihsel_olasilik": 80,
             "kisa_guvenli_olasilik": 70, "veri_guven_puani": 90,
             "profesyonel_kanit_puani": 90, "piyasa_rejimi": "YÜKSELİŞ"},
            beklenen_getiri=6, olasi_kayip=3, risk_getiri=2,
        )
        self.assertFalse(result["onayli"])
        self.assertIn("tarihsel örnek", result["dogrulama_notu"])

    def test_strong_and_sufficiently_sampled_signal_can_pass(self):
        result = canli_sinyal_dogrula(
            {"kisa_ornek": 300, "kisa_tarihsel_olasilik": 66,
             "kisa_guvenli_olasilik": 55, "veri_guven_puani": 90,
             "profesyonel_kanit_puani": 80, "piyasa_rejimi": "YÜKSELİŞ"},
            beklenen_getiri=7, olasi_kayip=3, risk_getiri=2.3,
        )
        self.assertTrue(result["onayli"])
        self.assertGreaterEqual(result["dogrulanmis_olasilik"], 50)

    def test_decision_engine_blocks_unvalidated_buy(self):
        result = karar_uret({
            "price": 100, "atr": 2, "v4_guven_puani": 90,
            "fib_puani": 85, "formasyon_puani": 80, "mtf_skor": 85,
            "risk_getiri_1": 2.5, "veri_guven_puani": 90,
            "profesyonel_kanit_puani": 80, "kisa_ornek": 45,
            "kisa_tarihsel_olasilik": 52, "kisa_guvenli_olasilik": 70,
            "piyasa_rejimi": "YÜKSELİŞ",
        })
        self.assertIn(result["yatirim_karari"], {"İZLE - DOĞRULAMA YETERSİZ", "VERİ KALİTESİ YETERSİZ"})
        self.assertIn("güven alt sınır", result["dogrulama_notu"])


if __name__ == "__main__":
    unittest.main()
