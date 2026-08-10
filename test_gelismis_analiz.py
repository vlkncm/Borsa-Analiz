import unittest
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path

from gelismis_analiz import gelismis_sinyal_degerlendir, likidite_degerlendir, portfoy_risk_ozeti, yuruyen_donem_raporu
from kullanici_karar_gunlugu import karar_kaydet, kararlari_oku


class GelismisAnalizTests(unittest.TestCase):
    def test_low_liquidity_is_rejected(self):
        self.assertFalse(likidite_degerlendir(10, 10_000)["likidite_uygun"])

    def test_alerts_include_stale_data_and_stop(self):
        result = gelismis_sinyal_degerlendir({"price": 100, "atr": 2, "onerilen_satis": 110, "onerilen_stop": 99, "veri_yasi_gun": 2, "ortalama_hacim_20": 20_000})
        self.assertGreaterEqual(result["canli_uyari_sayisi"], 2)

    def test_walk_forward_has_no_future_dependency_in_result_shape(self):
        report = yuruyen_donem_raporu(pd.DataFrame({"Close": np.linspace(100, 160, 220)}), min_train=120)
        self.assertIn("walk_forward_basari", report)

    def test_portfolio_risk_limit_is_enforced(self):
        self.assertFalse(portfoy_risk_ozeti([{"Maksimum Zarar": 6000}], 100000)["portfoy_risk_uygun"])

    def test_user_decision_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kararlar.csv"
            karar_kaydet("TEST.IS", "ALMADI", "risk yüksek", 100, path=path)
            self.assertEqual(kararlari_oku(path)[0]["Karar"], "ALMADI")


if __name__ == "__main__":
    unittest.main()
