import unittest
import pandas as pd
import tempfile
from pathlib import Path
from strateji_kalibrasyon import korelasyon_ve_sektor_kontrolu, maliyet_simulasyonu, olasilik_kalibrasyonu, strateji_sec
from kap_modulu import kap_olayi_sinifla
from kisisel_portfoy import portfoy_csv_oku, portfoyu_eslestir


class StratejiKalibrasyonTests(unittest.TestCase):
    def test_falling_regime_is_defensive(self):
        self.assertEqual(strateji_sec({"piyasa_rejimi": "DÜŞÜŞ"})["strateji"], "SAVUNMACI")

    def test_low_liquidity_increases_slippage(self):
        low = maliyet_simulasyonu(100, 1000, 200_000)
        high = maliyet_simulasyonu(100, 1000, 100_000_000)
        self.assertGreater(low["tahmini_kayma_bps"], high["tahmini_kayma_bps"])

    def test_calibration_compares_prediction_to_outcome(self):
        history = pd.DataFrame({"Model Olasılığı %": [70, 70], "Durum": ["HEDEF (KAPANIŞ)", "STOP (KAPANIŞ)"]})
        self.assertEqual(int(olasilik_kalibrasyonu(history)["Kapanan Sinyal"].sum()), 2)

    def test_sector_concentration_is_detected(self):
        result = korelasyon_ve_sektor_kontrolu(pd.DataFrame(), [{"sektor": "Banka"}] * 3)
        self.assertFalse(result["sektor_uygun"])

    def test_kap_events_are_classified_separately(self):
        self.assertIn("SOZLESME/IHALE", kap_olayi_sinifla("Yeni ihale sözleşmesi imzalandı"))

    def test_local_portfolio_can_be_matched_without_broker_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfoy.csv"
            path.write_text("Hisse,Adet,Maliyet\nTEST,10,100\n", encoding="utf-8")
            result = portfoyu_eslestir(portfoy_csv_oku(path), [{"symbol": "TEST.IS", "price": 110}])
            self.assertEqual(float(result.iloc[0]["Gerçekleşmemiş Getiri %"]), 10.0)


if __name__ == "__main__":
    unittest.main()
