import unittest
import numpy as np
import pandas as pd
from pathlib import Path

import backtest
import borsa_tarayici
import mtf_grafik
from teknik_gostergeler import adx, atr, bollinger_bands, classic_pivot, macd, macd_v, rsi, session_vwap


def fixture(count=80):
    close = pd.Series(np.linspace(10, 30, count), dtype=float)
    return pd.DataFrame({"Open": close-.1, "High": close+.5, "Low": close-.5, "Close": close, "Volume": np.arange(count)+100.0})


class CanonicalIndicatorTests(unittest.TestCase):
    def test_rsi_edges_and_warmup(self):
        self.assertTrue(rsi(pd.Series(range(30), dtype=float)).iloc[:14].isna().all())
        self.assertEqual(rsi(pd.Series(range(30), dtype=float)).iloc[-1], 100.0)
        self.assertEqual(rsi(pd.Series(range(30, 0, -1), dtype=float)).iloc[-1], 0.0)
        self.assertEqual(rsi(pd.Series([5.0]*30)).iloc[-1], 50.0)

    def test_atr_gap_and_adx(self):
        data = fixture()
        data.loc[40:, ["Open", "High", "Low", "Close"]] += 10
        self.assertGreater(atr(data).iloc[40], atr(data).iloc[39])
        self.assertTrue(np.isfinite(adx(data)["ADX"].dropna()).all())

    def test_macd_macdv_bollinger(self):
        data = fixture()
        self.assertGreater(macd(data.Close)["MACD"].iloc[-1], 0)
        self.assertTrue(np.isfinite(macd_v(data).dropna()).all().all())
        self.assertGreater(bollinger_bands(data.Close)["BBW"].iloc[-1], 0)

    def test_vwap_resets_and_pivot(self):
        index = pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:15", "2026-01-05 10:00"])
        data = pd.DataFrame({"High": [11, 13, 21], "Low": [9, 11, 19], "Close": [10, 12, 20], "Volume": [1, 1, 2]}, index=index)
        self.assertEqual(session_vwap(data).iloc[-1], 20)
        self.assertAlmostEqual(classic_pivot(12, 8, 10)["P"], 10)

    def test_live_backtest_chart_wrappers_are_equal(self):
        data = fixture()
        expected_rsi = rsi(data.Close)
        pd.testing.assert_series_equal(borsa_tarayici.rsi_hesapla(data), expected_rsi)
        pd.testing.assert_series_equal(backtest.rsi_hesapla(data).iloc[14:], expected_rsi.iloc[14:])
        pd.testing.assert_series_equal(mtf_grafik.rsi_hesapla(data.Close), expected_rsi)
        expected_macd = macd(data.Close)
        for module in (borsa_tarayici, backtest):
            line, signal = module.macd_hesapla(data)
            pd.testing.assert_series_equal(line, expected_macd["MACD"])
            pd.testing.assert_series_equal(signal, expected_macd["MACD_SIGNAL"])

    def test_consumers_do_not_reimplement_ema(self):
        root = Path(__file__).parent
        consumers = ["borsa_tarayici.py", "backtest.py", "gunluk_trade_motoru.py",
                     "gunluk_trade_gostergeleri.py", "intraday_gostergeler.py",
                     "profesyonel_analiz.py", "mtf_grafik.py", "pro_moduller.py"]
        for filename in consumers:
            source = (root/filename).read_text(encoding="utf-8")
            self.assertNotIn(".ewm(", source, f"Kopya EMA/RMA hesabı: {filename}")


if __name__ == "__main__":
    unittest.main()
