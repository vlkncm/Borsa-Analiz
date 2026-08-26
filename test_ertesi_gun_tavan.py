import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from ertesi_gun_tavan import (
    PROBABILITY_UNAVAILABLE, acik_tavan_tahminlerini_sonuclandir, aday_degerlendir, adaylari_tabloya_cevir,
    ertesi_gun_etiketi, ertesi_seans_sonucu, gunluk_ozellikleri_hesapla,
    tavan_fiyati_hesapla, tavan_performans_ozeti, tavan_tahminlerini_kaydet, walk_forward_degerlendir,
)
from tahmin_defteri import olaylari_oku, zinciri_dogrula


def prices(n=100):
    index = pd.bdate_range("2025-01-02", periods=n)
    close = pd.Series(np.linspace(20, 25, n)+np.sin(np.arange(n)/5)*.2, index=index)
    volume = pd.Series(np.linspace(1_000_000, 1_500_000, n), index=index)
    return pd.DataFrame({"Open": close*.995, "High": close*1.015, "Low": close*.985,
                         "Close": close, "Volume": volume}, index=index)


class ErtesiGunTavanTests(unittest.TestCase):
    def test_features_do_not_see_next_day(self):
        frame = prices(101)
        cutoff = frame.index[-2]
        before = gunluk_ozellikleri_hesapla(frame, cutoff)
        changed = frame.copy()
        changed.loc[frame.index[-1], ["Open", "High", "Low", "Close", "Volume"]] = [50, 55, 49, 54, 99_000_000]
        after = gunluk_ozellikleri_hesapla(changed, cutoff)
        self.assertEqual(before, after)
        self.assertEqual(before["veri_zamani"], str(cutoff))

    def test_historical_limit_and_tick_are_required_and_not_fixed_at_ten(self):
        self.assertIsNone(tavan_fiyati_hesapla(12.34, None, None))
        self.assertEqual(tavan_fiyati_hesapla(12.34, 7.5, .01), 13.26)
        label = ertesi_gun_etiketi(pd.Series({"Close": 12.34}),
                                  pd.Series({"High": 13.26, "Close": 13.00}), 7.5, .01)
        self.assertTrue(label["tavana_ulasti"])
        self.assertTrue(label["tavan_gorup_geri_dondu"])
        self.assertNotEqual(label["t1_yuksek_getiri_yuzde"], label["t1_kapanis_getiri_yuzde"])

    def test_uncalibrated_score_is_not_presented_as_probability(self):
        features = gunluk_ozellikleri_hesapla(prices())
        result = aday_degerlendir(features, {"piyasa_rejim_puani": 60, "sektor_puani": 60})
        self.assertIsNone(result["ertesi_gun_tavan_olasiligi"])
        self.assertEqual(result["olasilik_notu"], PROBABILITY_UNAVAILABLE)
        calibrated = aday_degerlendir(features, {}, {"samples": 30, "ceiling_probability": 100,
                                                      "eight_plus_probability": 64})
        self.assertEqual(calibrated["ertesi_gun_tavan_olasiligi"], 99)

    def test_already_eight_plus_stock_is_not_listed_as_early_candidate(self):
        frame = prices()
        frame.iloc[-1, frame.columns.get_loc("Close")] = frame.iloc[-2]["Close"]*1.09
        frame.iloc[-1, frame.columns.get_loc("High")] = frame.iloc[-1]["Close"]*1.01
        features = gunluk_ozellikleri_hesapla(frame)
        self.assertTrue(features["mevcut_gunde_tavan_benzeri"])
        self.assertTrue(adaylari_tabloya_cevir([{"symbol": "TEST.IS", "ertesi_gun_ozellikleri": features}]).empty)

    def test_table_exposes_data_gaps_instead_of_inventing_limit_or_kap(self):
        features = gunluk_ozellikleri_hesapla(prices())
        table = adaylari_tabloya_cevir([{"symbol": "TEST.IS", "ertesi_gun_ozellikleri": features,
                                         "piyasa_rejimi_v2": "YATAY", "sektor_gucu": "Nötr"}])
        self.assertEqual(table.iloc[0]["Tavan Fiyatı"], "Tarihsel limit/adım verisi yok")
        self.assertEqual(table.iloc[0]["KAP Katalizörü"], "Doğrulanamadı")
        self.assertIn(PROBABILITY_UNAVAILABLE, str(table.iloc[0]["Ertesi Gün Tavan Olasılığı"]))

    def test_forecasts_are_append_only_and_deduplicated_for_same_data_time(self):
        features = gunluk_ozellikleri_hesapla(prices())
        table = adaylari_tabloya_cevir([{"symbol": "TEST.IS", "ertesi_gun_ozellikleri": features}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"events.jsonl"
            self.assertEqual(len(tavan_tahminlerini_kaydet(table, path)), 1)
            self.assertEqual(tavan_tahminlerini_kaydet(table, path), [])
            self.assertEqual(len(olaylari_oku(path)), 1)
            self.assertTrue(zinciri_dogrula(path)[0])

    def test_next_session_outcome_separates_high_and_close_and_marks_missing_intraday_time(self):
        outcome = ertesi_seans_sonucu({"previous_close": 10, "ceiling_price": 10.8},
                                      pd.Series({"High": 10.8, "Low": 9.9, "Close": 10.3}))
        self.assertTrue(outcome["reached_ceiling"])
        self.assertEqual(outcome["max_rise_pct"], 8)
        self.assertEqual(outcome["close_return_pct"], 3)
        self.assertTrue(outcome["reversed_after_ceiling"])
        self.assertEqual(outcome["ceiling_hit_time"], "Intraday veri yok")

    def test_next_session_is_automatically_resolved_and_reported(self):
        features = gunluk_ozellikleri_hesapla(prices())
        table = adaylari_tabloya_cevir([{"symbol": "TEST.IS", "ertesi_gun_ozellikleri": features,
                                         "fiyat_limit_yuzdesi": 8, "fiyat_adimi": .01}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"events.jsonl"
            tavan_tahminlerini_kaydet(table, path)
            next_date = pd.Timestamp(features["veri_zamani"])+pd.offsets.BDay(1)
            next_bar = pd.DataFrame({"Open": [25], "High": [27], "Low": [24.8], "Close": [26]}, index=[next_date])
            self.assertEqual(len(acik_tavan_tahminlerini_sonuclandir(path, lambda _: next_bar)), 1)
            summary, detail = tavan_performans_ozeti(path)
            self.assertEqual(summary.iloc[0]["Tamamlanan"], 1)
            self.assertEqual(len(detail), 1)

    def test_walk_forward_uses_untouched_last_period_and_costs(self):
        n = 100
        data = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=n), "score": [71]*n,
                             "tavana_ulasti": [i%2 == 0 for i in range(n)],
                             "sekiz_plus": [i%2 == 0 for i in range(n)],
                             "t1_yuksek_getiri_yuzde": [9 if i%2 == 0 else 1 for i in range(n)],
                             "t1_kapanis_getiri_yuzde": [7 if i%2 == 0 else -1 for i in range(n)]})
        result = walk_forward_degerlendir(data, min_train=60, commission_bps=10, slippage_bps=10)
        self.assertEqual(result["status"], "ÖRNEK DIŞI / HOLDOUT")
        self.assertEqual(result["samples"], 20)
        self.assertLess(result["average_net_return_pct"], result["average_close_return_pct"])


if __name__ == "__main__":
    unittest.main()
