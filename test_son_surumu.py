import unittest
import numpy as np
import pandas as pd
from uluslararasi_faktorler import faktorleri_hesapla
from veri_kalite_kapisi import veri_kalite_kapisi


class SonSurumTests(unittest.TestCase):
    def test_factor_engine_returns_bounded_score(self):
        close = np.linspace(50, 100, 100)
        df = pd.DataFrame({"Close": close, "High": close + 1, "Low": close - 1, "Volume": np.full(100, 1_000_000)})
        result = faktorleri_hesapla(df)
        self.assertGreaterEqual(result["uluslararasi_faktor_puani"], 0)
        self.assertLessEqual(result["uluslararasi_faktor_puani"], 100)

    def test_stale_or_non_official_data_is_not_approved(self):
        result = veri_kalite_kapisi({"veri_islem_gunu_gecikmesi": 1, "veri_guven_puani": 90, "veri_kaynagi": "Yahoo Finance"})
        self.assertFalse(result["veri_kalite_onayli"])


if __name__ == "__main__":
    unittest.main()
