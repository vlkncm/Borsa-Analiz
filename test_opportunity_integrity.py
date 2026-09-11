"""Adversarial regressions; fixtures are not investment performance evidence."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from test_ertesi_gun_tavan import prices
from ertesi_gun_tavan import gunluk_ozellikleri_hesapla, aday_degerlendir
from saglam_backtest import performans_metrikleri, veri_butunlugu_kontrolu
from test_gunluk_trade import FakeAdapter
from gunluk_trade_motoru import gunluk_trade_analiz


class OpportunityIntegrityTests(unittest.TestCase):
    def test_overlapping_outcomes_are_not_known_at_signal_time(self):
        from intraday_backtest import walk_forward_tahminleri
        rows = pd.DataFrame({"sinyal_zamani": pd.date_range("2025-01-01", periods=40),
                             "sonuc_zamani": ["2025-03-01"]*40, "net_getiri": [.01]*40, "hedef_once": [1]*40})
        self.assertTrue(walk_forward_tahminleri(rows).tahmin_olasiligi.isna().all())

    def test_unverified_calibration_is_not_probability(self):
        result = aday_degerlendir(gunluk_ozellikleri_hesapla(prices()), calibration={"samples": 500, "ceiling_probability": 90})
        self.assertIsNone(result["ertesi_gun_tavan_olasiligi"])
        invalid = aday_degerlendir(gunluk_ozellikleri_hesapla(prices()), calibration={
            "samples": 500, "out_of_sample": True, "calibration_end": "2024-01-01", "ceiling_probability": np.nan})
        self.assertIsNone(invalid["ertesi_gun_tavan_olasiligi"])

    def test_intraday_rejects_undated_or_future_evidence(self):
        history = pd.DataFrame({"net_getiri": [.01]*40, "hedef_once": [1]*40})
        self.assertEqual(gunluk_trade_analiz("TEST", adapter=FakeAdapter(), historical_outcomes=history)["Örnek"], 0)
        history = history.assign(sinyal_zamani="2026-08-01", sonuc_zamani="2099-01-01", strategy_id="intraday_vwap", out_of_sample=True)
        self.assertEqual(gunluk_trade_analiz("TEST", adapter=FakeAdapter(), historical_outcomes=history)["Örnek"], 0)

    def test_low_confidence_high_score_cannot_outrank_verified_candidate(self):
        from ertesi_gun_tavan import adaylari_tabloya_cevir
        features = gunluk_ozellikleri_hesapla(prices(), benchmark=prices())
        common = {"ertesi_gun_ozellikleri": features, "veri_guven_puani": 90,
                  "veri_islem_gunu_gecikmesi": 0, "veri_kaynagi": "Borsa İstanbul"}
        rows = [{**common, "symbol": "LOW", "piyasa_rejim_puani": 100, "cache_fallback": True},
                {**common, "symbol": "HIGH", "piyasa_rejim_puani": 1}]
        result = adaylari_tabloya_cevir(rows)
        self.assertEqual(result.iloc[0].Hisse, "HIGH")

    def test_confidence_gaps_and_stale_data(self):
        from veri_kalite_kapisi import data_confidence
        features = gunluk_ozellikleri_hesapla(prices(), benchmark=prices())
        item = {"veri_guven_puani": 90, "veri_islem_gunu_gecikmesi": 0, "veri_kaynagi": "Borsa İstanbul"}
        self.assertEqual(data_confidence(item, features)["DATA_CONFIDENCE"], "HIGH")
        self.assertEqual(data_confidence(item, {**features, "benchmark_mevcut": False})["DATA_CONFIDENCE"], "MEDIUM")
        self.assertEqual(data_confidence({**item, "cache_fallback": True}, features)["DATA_CONFIDENCE"], "LOW")
        self.assertEqual(data_confidence({**item, "veri_islem_gunu_gecikmesi": 1}, features)["DATA_CONFIDENCE"], "LOW")
        self.assertEqual(data_confidence(item, features, require_financial=True)["DATA_CONFIDENCE"], "MEDIUM")

    def test_distribution_volume_does_not_raise_accumulation(self):
        frame = prices()
        frame.loc[frame.index[-1], ["Open", "High", "Low", "Close"]] = [25, 28, 24, 24.1]
        low = aday_degerlendir(gunluk_ozellikleri_hesapla(frame))
        frame.loc[frame.index[-1], "Volume"] *= 10
        high = aday_degerlendir(gunluk_ozellikleri_hesapla(frame))
        self.assertLess(high["para_akisi"], 20)
        self.assertLessEqual(high["para_akisi"], low["para_akisi"])
        self.assertIn("dağıtım", high["riskler"])

    def test_clv_breakout_and_relative_strength_are_causal(self):
        frame, benchmark = prices(101), prices(101)
        cutoff = frame.index[-2]
        before = gunluk_ozellikleri_hesapla(frame, cutoff, benchmark)
        benchmark.iloc[-1] *= 50
        self.assertEqual(before, gunluk_ozellikleri_hesapla(frame, cutoff, benchmark))
        self.assertEqual(before["relative_strength_20d"], 0)
        self.assertGreaterEqual(before["kapanis_zirve_konumu"], 0)
        self.assertLessEqual(before["kapanis_zirve_konumu"], 1)
        self.assertAlmostEqual(before["direnc20"], frame.High.iloc[-22:-2].max())

    def test_score_buckets_and_missing_returns(self):
        from saglam_backtest import skor_grubu_performansi
        trades = pd.DataFrame({"score": [60, 70, 80, 90, 100], "Getiri %": [-2, 0, 2, 4, np.nan]})
        result = skor_grubu_performansi(trades)
        self.assertEqual(result.samples.tolist(), [1, 1, 1, 1])
        self.assertEqual(result.net_ev.tolist(), [-2, 0, 2, 4])

    def test_under50_rejects_unverified_and_stale_prices(self):
        from sade_karar_modeli import elli_tl_ohlcv_adayi
        frame = prices(220)
        decision = frame.index[-1] + pd.Timedelta(hours=20)
        self.assertIsNone(elli_tl_ohlcv_adayi("TEST", frame, now=decision))
        frame.attrs["veri_kaynagi"] = "Borsa İstanbul"
        self.assertIsNotNone(elli_tl_ohlcv_adayi("TEST", frame, now=decision))
        self.assertIsNone(elli_tl_ohlcv_adayi("TEST", frame, now=decision+pd.Timedelta(days=7)))
        frame.iloc[-1, frame.columns.get_loc("Close")] = np.nan
        self.assertIsNone(elli_tl_ohlcv_adayi("TEST", frame, now=decision))

    def test_official_source_does_not_certify_a_later_bar(self):
        import veri_saglayici as provider
        frame = prices()
        official = frame.iloc[[-2]].copy()
        with patch.object(provider, "resmi_gunluk_satir", return_value=official), patch.object(provider, "uygulama_klasoru", return_value=None):
            result = provider._bist_ile_birlestir("TEST.IS", "1d", frame)
        self.assertEqual(result.index[-1], official.index[-1])

    def test_invalid_latest_bar_must_not_reuse_previous_close(self):
        for bad in (np.nan, np.inf, None, -1):
            with self.subTest(bad=bad):
                frame = prices()
                frame.loc[frame.index[-1], "Close"] = bad
                self.assertFalse(gunluk_ozellikleri_hesapla(frame)["veri_yeterli"])

    def test_invalid_ohlc_and_zero_volume_are_rejected(self):
        for column, value in (("High", 1), ("Volume", 0), ("Volume", -1)):
            frame = prices()
            frame.loc[frame.index[-1], column] = value
            self.assertFalse(gunluk_ozellikleri_hesapla(frame)["veri_yeterli"])

    def test_rvol_uses_previous_twenty_bars(self):
        frame = prices()
        frame["Volume"] = 1_000_000
        frame.loc[frame.index[-1], "Volume"] = 5_000_000
        self.assertEqual(gunluk_ozellikleri_hesapla(frame)["rvol"], 5)

    def test_future_catalyst_cannot_raise_score(self):
        features = gunluk_ozellikleri_hesapla(prices())
        plain = aday_degerlendir(features)
        future = aday_degerlendir(features, {"kap_yayin_zamani": "2099-01-01", "kap_url": "https://kap.org.tr", "kap_skor": 25})
        self.assertEqual(plain["tavan_aday_puani"], future["tavan_aday_puani"])

    def test_first_trade_loss_counts_in_drawdown(self):
        result = performans_metrikleri(pd.DataFrame({"Getiri %": [-10, 0]}))
        self.assertEqual(result["max_drawdown"], -10)

    def test_future_disclosure_fails_model_selection_gate(self):
        frame = pd.DataFrame({"symbol": ["TEST"], "date": ["2025-01-01"], "was_listed": [True],
                              "adjusted_for_splits": [True], "dividend_adjusted": [True],
                              "kap_published_at": ["2025-01-03"], "decision_time": ["2025-01-01"]})
        self.assertFalse(veri_butunlugu_kontrolu(frame)["safe_for_model_selection"])

    def test_intraday_atr_does_not_see_future_daily_bar(self):
        adapter = FakeAdapter()
        before = gunluk_trade_analiz("TEST.IS", adapter=adapter)
        adapter.daily.loc[adapter.daily.index[-1], "High"] = 10000
        after = gunluk_trade_analiz("TEST.IS", adapter=adapter)
        self.assertEqual(before["ATR"], after["ATR"])

    def test_bist100_loader_requests_bist100(self):
        import borsa_tarayici as scanner
        with patch.object(scanner, "_BENCHMARK_CACHE", None), patch.object(scanner, "guvenli_yf_download", return_value=prices()) as download:
            scanner.bist100_verisi()
        self.assertEqual(download.call_args.args[0], "XU100.IS")
