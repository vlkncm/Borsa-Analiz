import unittest
from unittest.mock import patch

import pandas as pd

import sirket_arastirmasi as module


class FakeTicker:
    financials = pd.DataFrame(
        {pd.Timestamp("2024-12-31"): [100, 10], pd.Timestamp("2025-12-31"): [125, 14]},
        index=["Total Revenue", "Net Income"],
    )
    cashflow = pd.DataFrame()
    balance_sheet = pd.DataFrame()


class SirketArastirmasiTest(unittest.TestCase):
    @patch.object(module.yf, "Ticker", return_value=FakeTicker())
    @patch.object(module, "temel_analiz_yfinance")
    def test_eksik_veriyi_uydurmaz(self, temel_mock, _ticker_mock):
        temel_mock.return_value = {
            "temel_puan": 60, "fk": 10, "ileri_fk": 0, "pddd": 1.5, "borc_ozsermaye": 0,
            "roe": 0.2, "kar_marji": 0.1, "ciro_buyume": 0.15, "kar_buyume": 0,
            "temettu_verimi": 0, "piyasa_degeri": 1_000_000_000, "sector": "Test",
            "temel_not": "ROE güçlü", "temel_risk": "",
        }
        result = module.sirket_arastirmasi("ASELS")
        self.assertEqual(result["symbol"], "ASELS.IS")
        self.assertIn("Ciro: 2 raporlama döneminde %25.0 arttı", result["report"])
        self.assertIn("İleri F/K: Veri yok", result["report"])
        self.assertIn("yatırım tavsiyesi değildir", result["report"])


if __name__ == "__main__":
    unittest.main()
