import unittest
import pandas as pd

from fintables_provider import fintables_symbol
from veri_saglayici import PrimaryFallbackAdapter, VeriMetadatasi


class _Fake:
    def __init__(self, fail=False): self.fail = fail
    def get_daily_ohlcv(self, symbol, period="6mo"):
        if self.fail: raise RuntimeError("offline")
        frame = pd.DataFrame({"Open":[10.],"High":[11.],"Low":[9.],"Close":[10.5],"Volume":[1000.]}, index=pd.date_range("2026-01-01", periods=1))
        return frame, VeriMetadatasi("Fintables", pd.Timestamp.now().to_pydatetime(), frame.index[-1].to_pydatetime(), symbol)

    get_intraday_ohlcv = get_daily_ohlcv


class FintablesProviderTests(unittest.TestCase):
    def test_symbol_normalize(self):
        self.assertEqual(fintables_symbol("thyao.IS"), "THYAO")

    def test_fallback_metadata(self):
        adapter = PrimaryFallbackAdapter(); adapter.primary = _Fake(True); adapter.fallback = _Fake(False)
        _, meta = adapter.get_daily_ohlcv("THYAO")
        self.assertTrue(meta.fallback_used)
        self.assertIn("Fallback", meta.source)

    def test_primary_metadata(self):
        adapter = PrimaryFallbackAdapter(); adapter.primary = _Fake(False)
        _, meta = adapter.get_daily_ohlcv("ASELS.IS")
        self.assertFalse(meta.fallback_used)
        self.assertEqual(meta.source, "Fintables")


if __name__ == "__main__": unittest.main()
