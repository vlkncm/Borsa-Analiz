import numpy as np
import pandas as pd
import unittest
from rsi_supertrend_stratejisi import RsiSupertrendAyarlar, hesapla


def _fiyatlar(adet=140):
    x = np.arange(adet); close = 100 + x * .12 + np.sin(x / 4) * 7
    return pd.DataFrame({"Open": close-.2, "High": close+1, "Low": close-1, "Close": close, "Volume": 1_000_000}, index=pd.date_range("2025-01-01", periods=adet, freq="D"))


class RsiSupertrendTest(unittest.TestCase):
    def test_gosterge_girdiyi_degistirmez_ve_karar_uretmez(self):
        df = _fiyatlar(); original = df.copy(deep=True); result = hesapla(df)
        pd.testing.assert_frame_equal(df, original)
        self.assertIn(result["rsi_st_durum"], {"YENİ TEYİTLİ DİP", "YUKARI TREND / SİNYAL BEKLENİYOR", "TEYİT YOK"})
        self.assertNotIn("aksiyon", result); self.assertNotIn("score", result)
        self.assertIn("%80 başarı garantisi değildir", result["rsi_st_not"])

    def test_yetersiz_veri_null_olarak_isaretlenir(self):
        result = hesapla(_fiyatlar(8), RsiSupertrendAyarlar())
        self.assertEqual(result["rsi_st_durum"], "VERİ YOK"); self.assertIsNone(result["rsi_st_rsi"])
