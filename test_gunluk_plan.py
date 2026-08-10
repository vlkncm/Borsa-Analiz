import unittest
from gunluk_islem_plani import gun_sonu_plani, sabah_fiyat_kontrolu
from sosyal_medya_risk import sosyal_medya_risk_analizi


class GunlukPlanTests(unittest.TestCase):
    def test_morning_check_rejects_chasing_price(self):
        plan = gun_sonu_plani([{"symbol": "TEST.IS", "price": 10, "yatirim_karari": "BUGÜN AL", "onerilen_alis_alt": 9, "onerilen_alis_ust": 10, "onerilen_satis": 12, "onerilen_stop": 8, "model_olasiligi": 70, "karar_risk_getiri": 2}])
        out = sabah_fiyat_kontrolu(plan, {"TEST": 11})
        self.assertIn("kovalanmamalı", out.iloc[0]["Sabah Kararı"])

    def test_social_media_guarantee_is_flagged(self):
        out = sosyal_medya_risk_analizi("Kesin kazanç, VIP Telegram grubu; hemen al")
        self.assertGreaterEqual(out["sosyal_medya_risk_puani"], 30)


if __name__ == "__main__":
    unittest.main()
