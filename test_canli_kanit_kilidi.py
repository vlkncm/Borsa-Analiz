import unittest
import pandas as pd
from canli_kanit_kilidi import strateji_kilidi_uygula, strateji_performansi


class CanliKanitKilidiTests(unittest.TestCase):
    def test_small_sample_locks_strategy(self):
        report = strateji_performansi(pd.DataFrame({"Strateji": ["TREND TAKİBİ"], "Durum": ["HEDEF (KAPANIŞ)"], "Gerçekleşen Getiri %": [4]}), "TREND TAKİBİ")
        self.assertFalse(report["Strateji Aktif"])

    def test_proven_strategy_can_pass(self):
        history = pd.DataFrame({"Strateji": ["TREND TAKİBİ"] * 30, "Durum": ["HEDEF (KAPANIŞ)"] * 18 + ["STOP (KAPANIŞ)"] * 12, "Gerçekleşen Getiri %": [3] * 18 + [-2] * 12})
        self.assertTrue(strateji_performansi(history, "TREND TAKİBİ")["Strateji Aktif"])

    def test_buy_is_downgraded_when_not_proven(self):
        result, _ = strateji_kilidi_uygula([{"strateji": "TREND TAKİBİ", "yatirim_karari": "BUGÜN AL"}], pd.DataFrame())
        self.assertEqual(result[0]["yatirim_karari"], "İZLE - CANLI KANIT YETERSİZ")


if __name__ == "__main__":
    unittest.main()
