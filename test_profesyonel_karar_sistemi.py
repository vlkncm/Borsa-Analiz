import tempfile
import unittest
from pathlib import Path

import pandas as pd

from profesyonel_karar_sistemi import (
    CostModel, RiskLimits, karar_kapilari_uygula, karar_kapilarini_toplu_uygula, net_ev_hesapla,
    para_akisi_teyidi, pozisyon_hesapla, risk_ayarlari_kaydet, risk_ayarlari_oku,
    stop_yonetimi,
)
from tahmin_defteri import (
    acik_tahminleri_sonuclandir, aktif_sinyaller, model_sagligi, olay_ekle, performans_ozeti,
    sinyal_kaydet, sonucu_hesapla, sonucu_kaydet, zinciri_dogrula,
)
from saglam_backtest import (
    block_bootstrap, deflated_sharpe_ratio, performans_metrikleri,
    probability_of_backtest_overfitting, purged_time_series_splits,
    veri_butunlugu_kontrolu, walk_forward_splits,
)


def strong_item():
    return {"symbol": "TEST.IS", "price": 100, "ema20": 98, "ema50": 94, "ema200": 85,
        "adx": 28, "atr": 2, "ret_20": 8, "ret_60": 18, "volume_ratio": 1.5,
        "obv_trend_20": 1000, "cmf_20": .15, "mfi_14": 62, "ad_trend": 1,
        "hacim_surekliligi": 70, "vwap": 99, "veri_guven_puani": 95, "veri_yasi_gun": 0,
        "onerilen_alis_alt": 98, "onerilen_alis_ust": 101, "onerilen_satis": 112,
        "onerilen_stop": 95, "risk_getiri_1": 2, "karar_risk_getiri": 2,
        "direnc_mesafe_yuzde": 8, "rsi": 58, "ortalama_gunluk_islem_tutari": 20_000_000,
        "kap_yayin_zamani": "2026-01-01T10:00:00+03:00", "kap_url": "https://kap.org.tr/x",
        "kap_skor": 2, "kap_etiket": "Olumlu", "v4_guven_puani": 82,
        "formasyon_teyit": "Evet", "formasyon_kirilim": 102, "hedef_1": 108,
    }


class DecisionGateTests(unittest.TestCase):
    def setUp(self):
        self.market = {"regime": "RISK_ON", "score": 70, "confidence": 85,
                       "uncertainty_penalty": 0, "median_ret20": 3}
        self.sectors = {"BİLİNMİYOR": {"verified": False, "score": 35, "class": "Nötr"},
                        "BANKA": {"verified": True, "score": 78, "class": "Güçlü", "relative_strength": 8}}

    def test_money_flow_family_is_capped_and_requires_persistence(self):
        result = para_akisi_teyidi(strong_item())
        self.assertLessEqual(result["score"], 100)
        self.assertTrue(result["confirmed"])
        weak = strong_item(); weak.update(volume_ratio=3, obv_trend_20=-1, cmf_20=-.2, hacim_surekliligi=0, ret_20=-5)
        self.assertFalse(para_akisi_teyidi(weak)["confirmed"])

    def test_net_ev_includes_costs_and_rejects_invalid_levels(self):
        ev = net_ev_hesapla(65, 100, 112, 95, CostModel())
        self.assertGreater(ev["cost_pct"], 0)
        self.assertLess(ev["net_win_pct"], 12)
        self.assertLess(net_ev_hesapla(65, 100, 90, 95)["net_ev_pct"], 0)

    def test_position_size_uses_point_five_percent_risk(self):
        result = pozisyon_hesapla(100_000, 100, 95, RiskLimits())
        self.assertEqual(result["allowed_cash_risk"], 500)
        self.assertEqual(result["position_qty"], 100)

    def test_bulk_gate_accepts_and_forwards_user_risk_limits(self):
        item = strong_item(); item["sektor"] = "BANKA"
        limits = RiskLimits(trade_risk_pct=.4, portfolio_risk_pct=3, sector_risk_pct=1.5)
        output, _, _ = karar_kapilarini_toplu_uygula([item], pd.DataFrame(), limits=limits)
        self.assertEqual(output[0]["trade_risk_pct"], .4)
        self.assertEqual(output[0]["allowed_cash_risk"], 400)

    def test_risk_limits_are_user_configurable_and_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "risk.json"
            expected = RiskLimits(trade_risk_pct=.4, portfolio_risk_pct=2.5, sector_risk_pct=1.2)
            risk_ayarlari_kaydet(expected, path)
            self.assertEqual(risk_ayarlari_oku(path), expected)
            with self.assertRaises(ValueError):
                risk_ayarlari_kaydet(RiskLimits(trade_risk_pct=2, sector_risk_pct=1), path)

    def test_stop_management_preserves_cost_and_emits_time_stop(self):
        item = strong_item(); item.update(gecen_islem_gunu=25, beklenen_sure_ust=20, kalibre_olasilik=60)
        result = stop_yonetimi(item, 100, 100.5, 95)
        self.assertTrue(result["erken_cikis_gerekli"])
        self.assertIn("Zaman stopu", result["erken_cikis_uyarisi"])
        profitable = stop_yonetimi(item, 100, 110, 95)
        self.assertGreaterEqual(profitable["iz_suren_stop"], 100.2)

    def test_missing_kap_and_sector_block_candidate(self):
        item = strong_item(); item.pop("kap_yayin_zamani"); item.pop("kap_url")
        result = karar_kapilari_uygula(item, self.market, self.sectors,
            calibrated_probability=65, calibration_samples=50)
        self.assertNotEqual(result["profesyonel_karar"], "UYGUN ADAY")
        self.assertIn("KAP/haber doğrulaması yapılamadı", result["onerilmeme_nedeni"])

    def test_risk_off_blocks_daily_new_buy(self):
        item = strong_item(); item["sektor"] = "BANKA"
        market = {**self.market, "regime": "RISK_OFF"}
        result = karar_kapilari_uygula(item, market, self.sectors, "daily_trade", 65, 50)
        self.assertEqual(result["profesyonel_karar"], "İZLE")

    def test_insufficient_calibration_never_shows_candidate(self):
        item = strong_item(); item["sektor"] = "BANKA"
        result = karar_kapilari_uygula(item, self.market, self.sectors,
            calibrated_probability=None, calibration_samples=5)
        self.assertNotEqual(result["profesyonel_karar"], "UYGUN ADAY")
        self.assertIn("Yetersiz geçmiş örnek", result["onerilmeme_nedeni"])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "events.jsonl"
    def tearDown(self): self.temp.cleanup()

    def test_hash_chain_is_append_only_and_detects_tampering(self):
        olay_ekle({"event_type": "A"}, self.path); olay_ekle({"event_type": "B"}, self.path)
        self.assertTrue(zinciri_dogrula(self.path)[0])
        text = self.path.read_text(encoding="utf-8").replace('"event_type": "A"', '"event_type": "X"')
        self.path.write_text(text, encoding="utf-8")
        self.assertFalse(zinciri_dogrula(self.path)[0])

    def test_same_bar_target_and_stop_is_pessimistic(self):
        signal = {"entry_high": 100, "target_2": 110, "stop": 95, "duration_high": 5}
        frame = pd.DataFrame({"High": [111], "Low": [94], "Close": [105]})
        result = sonucu_hesapla(signal, frame)
        self.assertEqual(result["status"], "STOP ÖNCE")
        self.assertLess(result["net_return_pct"], -5)

    def test_signal_outcome_and_summary(self):
        item = strong_item(); item.update(profesyonel_karar="İZLE", sektor_adi="BANKA")
        signal = sinyal_kaydet(item, "daily_trade", self.path)
        self.assertEqual(len(aktif_sinyaller(self.path)), 1)
        frame = pd.DataFrame({"High": [105, 113], "Low": [98, 101], "Close": [103, 111]})
        sonucu_kaydet(signal, frame, self.path)
        summary, detail = performans_ozeti(self.path)
        self.assertEqual(summary.iloc[0]["Başarılı"], 1)
        self.assertEqual(len(aktif_sinyaller(self.path)), 0)

    def test_small_live_sample_enables_protection_mode(self):
        self.assertTrue(model_sagligi(self.path)["protection_mode"])

    def test_open_signal_is_automatically_resolved_but_not_expired_early(self):
        item = strong_item(); item.update(profesyonel_karar="İZLE", sektor_adi="BANKA", beklenen_sure_ust=5)
        sinyal_kaydet(item, "daily_trade", self.path)
        quiet = pd.DataFrame({"High": [103, 104], "Low": [98, 97], "Close": [101, 102]},
                             index=pd.date_range("2026-01-02", periods=2, tz="UTC"))
        self.assertEqual(acik_tahminleri_sonuclandir(self.path, lambda _: quiet), [])
        target = pd.DataFrame({"High": [103, 113], "Low": [98, 97], "Close": [101, 111]},
                              index=pd.date_range("2026-01-02", periods=2, tz="UTC"))
        self.assertEqual(len(acik_tahminleri_sonuclandir(self.path, lambda _: target)), 1)
        self.assertEqual(len(aktif_sinyaller(self.path)), 0)


class RobustBacktestTests(unittest.TestCase):
    def test_purged_and_walk_forward_splits_do_not_overlap(self):
        for split in purged_time_series_splits(120, 4, 5, 3):
            self.assertLess(split["train"].max(), split["test"].min()-4)
        for train, test in walk_forward_splits(100, 50, 10, embargo=2):
            self.assertLess(train.max(), test.min())

    def test_metrics_and_bootstrap_include_downside(self):
        trades = pd.DataFrame({"Getiri %": [5, -3, 4, -2], "Sonuç": ["HEDEF", "STOP", "HEDEF", "STOP"]})
        metrics = performans_metrikleri(trades)
        self.assertEqual(metrics["precision"], .5)
        self.assertLess(metrics["max_drawdown"], 0)
        self.assertIsNotNone(block_bootstrap([1, -1, 2, -2]*5, simulations=50)["median"])

    def test_dsr_pbo_and_point_in_time_audit(self):
        self.assertIsNotNone(deflated_sharpe_ratio([1, -1, 2, -.5]*10, trials=5))
        self.assertIsNotNone(probability_of_backtest_overfitting([1,2,3,4], [4,3,2,1]))
        unsafe = veri_butunlugu_kontrolu(pd.DataFrame({"symbol": ["A"]}))
        self.assertFalse(unsafe["safe_for_model_selection"])


if __name__ == "__main__": unittest.main()
