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
from mum_formasyonlari import doji_baglam_ve_teyit, doji_siniflandir, mum_formasyonu_tespit
from veri_saglayici import VeriMetadatasi
from borsa_tarayici import gun_ici_yukselis_hesapla
from gunluk_trade_gostergeleri import en_iyi_gunluk_trade_adaylari, gunluk_trade_teyitleri, macd_v


TZ = ZoneInfo("Europe/Istanbul")


class DojiTests(unittest.TestCase):
    @staticmethod
    def pattern_frame(trend="down", last=None, count=10):
        base = np.linspace(12, 9, count) if trend == "down" else np.linspace(9, 12, count)
        frame = pd.DataFrame({"Open": base+.1, "High": base+.4, "Low": base-.4,
                              "Close": base, "Volume": 1000.0})
        for offset, candle in enumerate(last or []):
            for key, value in candle.items():
                frame.loc[len(frame)-len(last)+offset, key] = value
        return frame

    def test_hammer_and_hanging_man_use_trend_context(self):
        hammer = {"Open": 9.5, "High": 9.65, "Low": 8.5, "Close": 9.6, "Volume": 1200}
        self.assertIn("HAMMER", mum_formasyonu_tespit(self.pattern_frame("down", [hammer]))["mum_formasyonu"])
        hanging = {"Open": 12.1, "High": 12.2, "Low": 11.0, "Close": 11.95, "Volume": 1200}
        self.assertIn("HANGING MAN", mum_formasyonu_tespit(self.pattern_frame("up", [hanging]))["mum_formasyonu"])

    def test_bullish_and_bearish_engulfing(self):
        bull = [{"Open": 10.0, "High": 10.1, "Low": 9.5, "Close": 9.6},
                {"Open": 9.5, "High": 10.3, "Low": 9.4, "Close": 10.2}]
        self.assertIn("BULLISH ENGULFING", mum_formasyonu_tespit(self.pattern_frame("down", bull))["mum_formasyonu"])
        bear = [{"Open": 11.8, "High": 12.3, "Low": 11.7, "Close": 12.2},
                {"Open": 12.3, "High": 12.4, "Low": 11.5, "Close": 11.6}]
        self.assertIn("BEARISH ENGULFING", mum_formasyonu_tespit(self.pattern_frame("up", bear))["mum_formasyonu"])

    def test_morning_star_gravestone_and_cornering(self):
        star = [{"Open": 10.3, "High": 10.4, "Low": 9.5, "Close": 9.6},
                {"Open": 9.55, "High": 9.7, "Low": 9.45, "Close": 9.58},
                {"Open": 9.6, "High": 10.4, "Low": 9.55, "Close": 10.3}]
        self.assertIn("MORNING STAR", mum_formasyonu_tespit(self.pattern_frame("down", star))["mum_formasyonu"])
        grave = {"Open": 12.0, "High": 13.0, "Low": 11.95, "Close": 12.02, "Volume": 1000}
        self.assertIn("GRAVESTONE", mum_formasyonu_tespit(self.pattern_frame("up", [grave]))["mum_formasyonu"])
        flat = self.pattern_frame("up", count=30)
        flat.loc[:, "Open"] = 10.0; flat.loc[:, "Close"] = 10.0
        flat.loc[:, "High"] = 10.1; flat.loc[:, "Low"] = 9.9; flat.loc[:, "Volume"] = 1000
        self.assertIn("CORNERING", mum_formasyonu_tespit(flat)["mum_formasyonu"])

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
    def test_daily_trade_returns_only_top_five_valid_candidates(self):
        frame = pd.DataFrame({"Hisse": list("ABCDEFG"), "Günlük Trade Skoru": [10,90,80,70,60,50,100],
                              "Gün İçi Yükseliş %": [1,2,3,4,5,6,7],
                              "Veri Durumu": ["GÜVENİLİR"]*6+["ESKİ VERİ - KARAR YOK"]})
        result = en_iyi_gunluk_trade_adaylari(frame)
        self.assertEqual(len(result), 5)
        self.assertEqual(result.iloc[0]["Hisse"], "B")
        self.assertNotIn("G", result["Hisse"].tolist())

    def test_macd_v_is_atr_normalized_and_trade_confirmation_has_four_filters(self):
        idx = pd.date_range("2025-01-01", periods=180, freq="B")
        close = pd.Series(np.linspace(50, 90, len(idx)) + np.sin(np.arange(len(idx))/4), index=idx)
        frame = pd.DataFrame({"Open": close-.2, "High": close+1, "Low": close-1,
                              "Close": close, "Volume": 1_000_000}, index=idx)
        mv = macd_v(frame)
        self.assertTrue(np.isfinite(mv.iloc[-1]["MACD_V"]))
        result = gunluk_trade_teyitleri(frame)
        self.assertIn(result["gunluk_trade_teyit"], {"4/4 TEYİTLİ", "TEYİT BEKLE"})
        self.assertIn(result["bbw_durumu"], {"HAREKETLİ", "YATAY / SIKIŞIK"})

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
