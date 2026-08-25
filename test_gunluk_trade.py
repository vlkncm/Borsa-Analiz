import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from gunluk_trade_motoru import adaylari_tara, gunluk_trade_analiz, kagit_islem_kaydet
from intraday_backtest import ampirik_kanit, islem_sonucu, walk_forward_tahminleri
from intraday_gostergeler import klasik_pivot, pivot_serisi, pozisyon_boyutu, seans_vwap, wilder_atr
from mum_formasyonlari import doji_baglam_ve_teyit, doji_siniflandir
from veri_saglayici import VeriMetadatasi
from borsa_tarayici import gun_ici_yukselis_hesapla


TZ = ZoneInfo("Europe/Istanbul")


class DojiTests(unittest.TestCase):
    def test_doji_types_are_exclusive(self):
        cases = [
            ((10, 11, 9.95, 10.02), "MEZAR TAŞI DOJİ"),
            ((10, 10.05, 9, 9.98), "YUSUFÇUK DOJİ"),
            ((10, 11, 9, 10.02), "UZUN BACAKLI DOJİ"),
            ((10, 11, 9, 10.8), "DOJI DEĞİL"),
        ]
        for values, expected in cases:
            with self.subTest(expected=expected):
                result = doji_siniflandir(*values)
                self.assertEqual(result["tur"], expected)

    def test_invalid_and_boundary_candles(self):
        self.assertFalse(doji_siniflandir(10, 10, 10, 10)["gecerli"])
        self.assertFalse(doji_siniflandir(np.nan, 11, 9, 10)["gecerli"])
        self.assertFalse(doji_siniflandir(-1, 11, 9, 10)["gecerli"])
        boundary = doji_siniflandir(10, 11, 9, 10.2)
        self.assertIn("DOJİ", boundary["tur"])

    def test_context_and_completed_confirmation_required(self):
        doji = doji_siniflandir(10, 10.05, 9, 9.98)
        no_trend = doji_baglam_ve_teyit(doji, [10, 10], 10.05, 9, {"Close": 10.2, "is_complete_bar": True})
        self.assertFalse(no_trend["teyit"])
        incomplete = doji_baglam_ve_teyit(doji, [11, 10], 10.05, 9, {"Close": 10.2, "is_complete_bar": False})
        self.assertEqual(incomplete["durum"], "TEYİT BEKLE")
        confirmed = doji_baglam_ve_teyit(doji, [11, 10], 10.05, 9, {"Close": 10.2, "is_complete_bar": True})
        self.assertTrue(confirmed["teyit"])


class IndicatorTests(unittest.TestCase):
    def test_open_to_intraday_target_growth_percentage(self):
        target, growth = gun_ici_yukselis_hesapla(35, 36, 38, 2)
        self.assertEqual(target, 37.5)
        self.assertAlmostEqual(growth, (37.5 / 35 - 1) * 100)

    def test_pivot_known_example_and_previous_day_shift(self):
        p = klasik_pivot(110, 90, 100)
        self.assertEqual(p, {"P": 100, "R1": 110, "S1": 90, "R2": 120, "S2": 80})
        daily = pd.DataFrame({"High": [110, 120], "Low": [90, 100], "Close": [100, 110]})
        shifted = pivot_serisi(daily)
        self.assertTrue(pd.isna(shifted.iloc[0]["P"]))
        self.assertEqual(shifted.iloc[1]["P"], 100)

    def test_vwap_resets_and_rejects_zero_volume(self):
        idx = pd.to_datetime(["2026-08-24 10:00", "2026-08-24 10:05", "2026-08-25 10:00"])
        frame = pd.DataFrame({"High": [12, 14, 22], "Low": [8, 10, 18], "Close": [10, 12, 20], "Volume": [1, 3, 2]}, index=idx)
        out = seans_vwap(frame)
        self.assertAlmostEqual(out.iloc[1], 11.5)
        self.assertAlmostEqual(out.iloc[2], 20)
        frame["Volume"] = 0
        self.assertTrue(seans_vwap(frame).isna().all())

    def test_atr_and_position_limits(self):
        daily = pd.DataFrame({"High": np.arange(20)+11, "Low": np.arange(20)+9, "Close": np.arange(20)+10})
        self.assertAlmostEqual(wilder_atr(daily).iloc[-1], 2.0)
        size = pozisyon_boyutu(100_000, 0.5, 100, 98, max_portfoy_yuzdesi=10, likidite_adet_limiti=80, komisyon_orani=0)
        self.assertEqual(size["adet"], 80)
        self.assertLessEqual(size["risk_tutari"], 500)


class BacktestTests(unittest.TestCase):
    def test_same_bar_is_pessimistic_and_costs_reduce_return(self):
        bars = pd.DataFrame([{"High": 105, "Low": 95, "Close": 102}])
        result = islem_sonucu(bars, 100, 104, 96, commission_rate=.001, slippage_rate=.001)
        self.assertTrue(result["belirsiz"])
        self.assertTrue(result["sonuc"].startswith("STOP"))
        self.assertLess(result["net_getiri"], result["brut_getiri"])

    def test_low_sample_probability_hidden_and_walk_forward_no_leak(self):
        rows = pd.DataFrame({"sinyal_zamani": pd.date_range("2026-01-01", periods=31),
                             "net_getiri": [0.01]*31, "hedef_once": [1]*31})
        self.assertIsNone(ampirik_kanit(rows.iloc[:29])["olasilik"])
        out = walk_forward_tahminleri(rows, min_train=30)
        self.assertTrue(pd.isna(out.iloc[29]["tahmin_olasiligi"]))
        self.assertIsNotNone(out.iloc[30]["tahmin_olasiligi"])


class FakeAdapter:
    def __init__(self, stale=False):
        daily_idx = pd.date_range("2026-07-01", periods=40, freq="B", tz=TZ)
        close = np.linspace(90, 100, 40)
        self.daily = pd.DataFrame({"Open": close-.2, "High": close+1, "Low": close-1, "Close": close, "Volume": 1_000_000}, index=daily_idx)
        idx = pd.date_range("2026-08-25 10:00", periods=12, freq="15min", tz=TZ)
        prices = np.linspace(99, 101, 12)
        self.intra = pd.DataFrame({"Open": prices-.1, "High": prices+.3, "Low": prices-.3, "Close": prices, "Volume": 1000}, index=idx)
        self.meta = VeriMetadatasi("fixture", datetime(2026,8,25,13,tzinfo=TZ), idx[-1].to_pydatetime(),
                                    is_delayed=False, delay_minutes=0, is_stale=stale, is_complete_bar=True)
    def get_daily_ohlcv(self, symbol, period="6mo"):
        return self.daily, self.meta
    def get_intraday_ohlcv(self, symbol, interval="15m", period="5d"):
        return self.intra, self.meta


class EngineTests(unittest.TestCase):
    def test_stale_data_never_produces_buy_candidate(self):
        row = gunluk_trade_analiz("TEST.IS", adapter=FakeAdapter(stale=True))
        self.assertEqual(row["Sonuç"], "VERİ YETERSİZ")

    def test_probability_fields_and_math_are_distinct(self):
        history = pd.DataFrame({"net_getiri": [0.01]*35, "hedef_once": [1]*20+[0]*15})
        row = gunluk_trade_analiz("TEST.IS", adapter=FakeAdapter(), historical_outcomes=history)
        expected = (row["Hedef"]/row["Referans Fiyat"]-1)*100
        self.assertAlmostEqual(row["Hedef Potansiyeli %"], expected)
        self.assertNotEqual(row["Beklenen Gün Sonu Hareketi %"], row["Hedef Önce Olasılığı %"])

    def test_empty_candidate_list_and_audit_chain(self):
        frame = adaylari_tara(["TEST.IS"], adapter=FakeAdapter(stale=True), sadece_teyitli=True)
        self.assertTrue(frame.empty)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"paper.jsonl"
            first = kagit_islem_kaydet({"Hisse": "TEST"}, path)
            kagit_islem_kaydet({"Hisse": "TEST2"}, path)
            self.assertIn(first, path.read_text(encoding="utf-8").splitlines()[1])


if __name__ == "__main__":
    unittest.main()
