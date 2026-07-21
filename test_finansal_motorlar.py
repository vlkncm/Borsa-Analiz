import unittest
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from backtest import atr_hesapla, macd_hesapla, rsi_hesapla
from karar_motoru import karar_uret
from satis_karar_motoru import satis_karari_uret
from vade_motoru import vade_listeleri_uret
from kap_modulu import metin_puanla
from borsa_tarayici import temiz_fiyat_verisi, veri_islem_gunu_gecikmesi
from pro_moduller import portfoy_onerisi_uret
from profesyonel_analiz import profesyonel_analiz
from gecelik_momentum import gecelik_aday_puanla, tek_gecelik_aday
import veri_saglayici


class VeriSaglayiciTests(unittest.TestCase):
    def test_invalid_ohlc_is_removed(self):
        idx = pd.date_range("2026-01-01", periods=3)
        raw = pd.DataFrame({"Open": [10, 0, 12], "High": [11, 12, 13],
                            "Low": [9, 10, 11], "Close": [10.5, 11, 12.5],
                            "Volume": [100, 200, 300]}, index=idx)
        clean = veri_saglayici._normalize(raw)
        self.assertEqual(len(clean), 2)

    def test_download_uses_sqlite_cache(self):
        idx = pd.date_range("2026-01-01", periods=2)
        raw = pd.DataFrame({"Open": [10, 11], "High": [11, 12], "Low": [9, 10],
                            "Close": [10.5, 11.5], "Volume": [100, 200]}, index=idx)
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"LOCALAPPDATA": tmp}):
            with patch.object(veri_saglayici.yf, "download", return_value=raw) as mocked:
                first = veri_saglayici.download("TEST.IS", period="1mo", interval="1d")
                second = veri_saglayici.download("TEST.IS", period="1mo", interval="1d")
            self.assertEqual(mocked.call_count, 1)
            pd.testing.assert_frame_equal(first, second)


class IndicatorTests(unittest.TestCase):
    def _frame(self, close):
        close = pd.Series(close, dtype=float)
        return pd.DataFrame({"Close": close, "High": close + 1, "Low": close - 1})

    def test_rsi_rising_series_is_100_and_numeric(self):
        rsi = rsi_hesapla(self._frame(np.arange(1, 101)))
        self.assertEqual(rsi.dtype, np.dtype("float64"))
        self.assertAlmostEqual(rsi.iloc[-1], 100.0)

    def test_rsi_falling_series_is_zero(self):
        rsi = rsi_hesapla(self._frame(np.arange(100, 0, -1)))
        self.assertAlmostEqual(rsi.iloc[-1], 0.0)

    def test_rsi_flat_series_is_neutral(self):
        rsi = rsi_hesapla(self._frame(np.full(100, 50.0)))
        self.assertAlmostEqual(rsi.iloc[-1], 50.0)

    def test_indicators_preserve_length_and_are_finite(self):
        frame = self._frame(np.linspace(10, 30, 100))
        macd, signal = macd_hesapla(frame)
        atr = atr_hesapla(frame)
        for series in (rsi_hesapla(frame), macd, signal, atr):
            self.assertEqual(len(series), len(frame))
            self.assertTrue(np.isfinite(series.astype(float)).all())

    def test_incomplete_latest_bar_is_removed(self):
        frame = pd.DataFrame({
            "Open": [10.0, 11.0], "High": [11.0, 12.0],
            "Low": [9.0, 10.0], "Close": [10.5, np.nan],
            "Volume": [1000, 1500],
        })
        clean = temiz_fiyat_verisi(frame)
        self.assertEqual(len(clean), 1)
        self.assertEqual(float(clean.iloc[-1]["Close"]), 10.5)

    def test_stale_completed_session_is_detected(self):
        delay = veri_islem_gunu_gecikmesi("2026-07-17", "2026-07-21 01:00:00")
        self.assertEqual(delay, 1)

    def test_previous_session_is_current_before_market_close(self):
        delay = veri_islem_gunu_gecikmesi("2026-07-20", "2026-07-21 12:00:00")
        self.assertEqual(delay, 0)

    def test_professional_evidence_is_bounded_and_lookahead_safe(self):
        rng = np.random.default_rng(42)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, 500)))
        frame = pd.DataFrame({
            "Open": close, "High": close * 1.01, "Low": close * 0.99,
            "Close": close, "Volume": rng.integers(100_000, 500_000, 500),
        })
        full = profesyonel_analiz(frame)
        truncated = profesyonel_analiz(frame.iloc[:-10])
        for result in (full, truncated):
            self.assertGreaterEqual(result["profesyonel_kanit_puani"], 0)
            self.assertLessEqual(result["profesyonel_kanit_puani"], 100)
            self.assertLessEqual(result["kisa_guvenli_olasilik"], result["kisa_tarihsel_olasilik"])
            self.assertIn(result["supertrend_yonu"], ("POZİTİF", "NEGATİF"))
            self.assertIn(result["ichimoku_durumu"], ("BULUT ÜSTÜ", "BULUT ALTI", "BULUT İÇİ"))
            self.assertGreaterEqual(result["mc_1a_yukselis"], 0)
            self.assertLessEqual(result["mc_1a_yukselis"], 100)

    def test_relative_strength_uses_benchmark_return(self):
        close = np.linspace(100, 160, 300)
        benchmark = np.linspace(100, 120, 300)
        frame = pd.DataFrame({
            "Open": close, "High": close * 1.01, "Low": close * 0.99,
            "Close": close, "Volume": np.full(300, 200_000),
        })
        bench = pd.DataFrame({
            "Open": benchmark, "High": benchmark * 1.01, "Low": benchmark * 0.99,
            "Close": benchmark, "Volume": np.full(300, 1_000_000),
        })
        result = profesyonel_analiz(frame, bench)
        self.assertGreater(result["goreceli_guc_1y"], 0)

    def test_overnight_scanner_never_fabricates_candidate_from_bad_data(self):
        self.assertFalse(gecelik_aday_puanla(pd.DataFrame(), "YOK.IS")["uygun"])
        self.assertEqual(tek_gecelik_aday([])["karar"], "BUGÜN ADAY YOK")

    def test_overnight_levels_are_coherent(self):
        rng = np.random.default_rng(7)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0008, 0.025, 400)))
        frame = pd.DataFrame({
            "Open": close * 0.995, "High": close * 1.03, "Low": close * 0.98,
            "Close": close, "Volume": rng.integers(500_000, 2_000_000, 400),
        })
        result = gecelik_aday_puanla(frame, "TEST.IS")
        self.assertGreater(result["hedef"], result["referans_alis"])
        self.assertLess(result["acilis_risk_stop"], result["referans_alis"])
        self.assertLessEqual(result["ertesi_gun_yuzde10_guvenli_olasilik"], result["ertesi_gun_yuzde10_ham_olasilik"])


class DecisionTests(unittest.TestCase):
    def test_buy_scenario_has_coherent_levels(self):
        result = karar_uret({
            "price": 100, "atr": 2, "v4_guven_puani": 82,
            "fib_puani": 70, "formasyon_puani": 70,
            "mtf_skor": 72, "risk_getiri_1": 2,
        })
        self.assertLess(result["onerilen_stop"], result["onerilen_alis_alt"])
        self.assertLessEqual(result["onerilen_alis_alt"], result["onerilen_alis_ust"])
        self.assertLess(result["onerilen_alis_ust"], result["onerilen_satis"])
        self.assertLessEqual(result["model_olasiligi"], 88)

    def test_profitable_position_never_moves_trailing_stop_below_cost(self):
        result = satis_karari_uret({"price": 110, "atr": 2, "onerilen_satis": 125}, 100)
        self.assertGreaterEqual(result["yeni_stop"], 100)

    def test_falling_market_downgrades_buy_decision(self):
        base = {
            "price": 100, "atr": 2, "v4_guven_puani": 90,
            "fib_puani": 85, "formasyon_puani": 80, "mtf_skor": 85,
            "risk_getiri_1": 2.5, "veri_guven_puani": 90,
        }
        rising = karar_uret({**base, "piyasa_rejimi": "YÜKSELİŞ"})
        falling = karar_uret({**base, "piyasa_rejimi": "DÜŞÜŞ"})
        self.assertGreater(rising["model_olasiligi"], falling["model_olasiligi"])
        self.assertNotEqual(falling["yatirim_karari"], "BUGÜN AL")

    def test_low_data_confidence_blocks_trade_decision(self):
        result = karar_uret({
            "price": 100, "atr": 2, "v4_guven_puani": 90,
            "fib_puani": 85, "formasyon_puani": 80, "mtf_skor": 85,
            "risk_getiri_1": 2.5, "veri_guven_puani": 45,
        })
        self.assertEqual(result["yatirim_karari"], "VERİ KONTROLÜ GEREKLİ")
        self.assertLessEqual(result["model_olasiligi"], 50)


class PortfolioRiskTests(unittest.TestCase):
    def test_lot_is_limited_by_risk_and_position_cap(self):
        frame = pd.DataFrame([{
            "Hisse": "TEST.IS", "Broker Aksiyon": "GÜÇLÜ AL", "Broker Skor": 90,
            "Yatırım Kararı": "BUGÜN AL", "Veri Güven Puanı": 90,
            "Fiyat": 100, "Önerilen Alış Üst": 100, "Önerilen Stop": 95,
            "Önerilen Satış": 115,
        }])
        plan = portfoy_onerisi_uret(frame, sermaye=100000, islem_riski_yuzde=1, max_pozisyon_yuzde=20)
        self.assertEqual(int(plan.iloc[0]["Önerilen Lot"]), 200)
        self.assertAlmostEqual(float(plan.iloc[0]["Maksimum Zarar"]), 1000)
        self.assertLessEqual(float(plan.iloc[0]["Pozisyon %"]), 20)


class HorizonSelectionTests(unittest.TestCase):
    def _candidate(self, **overrides):
        item = {
            "Hisse": "TEST.IS", "Veri Tarihi": "2026-07-20", "Veri Yaşı (Gün)": 0,
            "Yatırım Kararı": "BUGÜN AL", "Fiyat": 100,
            "Önerilen Alış Alt": 98, "Önerilen Alış Üst": 101,
            "Önerilen Satış": 120, "Önerilen Stop": 94,
            "Beklenen Getiri %": 25, "Beklenen Süre": "10-20 iş günü",
            "Model Olasılığı %": 75, "Karar Risk/Getiri": 2.2,
            "Karar Nedenleri": "Trend ve risk/getiri uygun", "v4 Güven Puanı": 80,
            "Fibonacci Puanı": 70, "Formasyon Puanı": 65, "RSI": 58,
            "Son 20 Gün %": 8, "Son 60 Gün %": 15, "Son 252 Gün %": 30, "ADX": 35,
            "Hacim Oranı": 2.0, "Faaliyet Puanı": 68,
            "Profesyonel Kanıt Puanı": 72,
            "Kısa Güvenli Olasılık %": 55,
            "Orta Güvenli Olasılık %": 52,
            "Uzun Güvenli Olasılık %": 48,
        }
        item.update(overrides)
        return item

    def test_quality_candidate_is_visible_in_all_horizons(self):
        result = vade_listeleri_uret(pd.DataFrame([self._candidate()]))
        self.assertTrue(all(len(frame) == 1 for frame in result))
        self.assertTrue(all(frame.iloc[0]["İşlem Durumu"] == "ALIM BÖLGESİNDE" for frame in result))

    def test_stale_or_bad_risk_candidate_is_not_recommended(self):
        stale = self._candidate(**{"Veri Yaşı (Gün)": 8})
        bad_rr = self._candidate(Hisse="BAD.IS", **{"Karar Risk/Getiri": 0.7})
        result = vade_listeleri_uret(pd.DataFrame([stale, bad_rr]))
        self.assertTrue(all(frame.empty for frame in result))


class KapScoringTests(unittest.TestCase):
    def test_positive_and_negative_disclosures_are_distinguished(self):
        positive = metin_puanla("Yeni iş sözleşmesi ve ihracat anlaşması imzalandı")
        negative = metin_puanla("Faaliyet durdurma ve zarar açıklaması")
        self.assertGreater(positive["kap_skor"], 0)
        self.assertLess(negative["kap_skor"], 0)


if __name__ == "__main__":
    unittest.main()
