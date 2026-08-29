import unittest

import pandas as pd

from analysis_orchestration import (
    ANALYSIS_UNIVERSES, AnalysisCacheKey, build_analysis_universes,
    filter_frame_to_symbols, tag_analysis_result, valid_under_50,
)
from scan_progress import COMPONENTS, ScanCoordinator


BIST30 = ["AAA.IS", "BBB.IS"]
ALL_BIST = ["AAA.IS", "BBB.IS", "CCC.IS", "DDD.IS"]


class AnalysisUniverseContractTests(unittest.TestCase):
    def setUp(self):
        self.universes = build_analysis_universes(ALL_BIST, BIST30)

    def test_01_daily_trade_gets_all_active_bist(self):
        self.assertEqual(self.universes["daily_trade"], ALL_BIST)

    def test_02_short_term_gets_only_bist30(self):
        self.assertEqual(self.universes["short_term"], BIST30)

    def test_03_medium_term_gets_only_bist30(self):
        self.assertEqual(self.universes["medium_term"], BIST30)

    def test_04_under_50_starts_from_all_active_bist(self):
        self.assertEqual(self.universes["under_50"], ALL_BIST)

    def test_05_under_50_accepts_only_valid_positive_prices(self):
        frame = pd.DataFrame({"Hisse": ["AAA", "BBB", "CCC", "DDD", "EEE"],
                              "Fiyat": [50.0, 50.01, None, -2, "12,5"]})
        self.assertEqual(valid_under_50(frame)["Hisse"].tolist(), ["AAA"])

    def test_06_high_movement_gets_all_active_bist(self):
        self.assertEqual(self.universes["high_movement"], ALL_BIST)

    def test_07_non_bist30_can_reach_daily_trade(self):
        self.assertIn("CCC.IS", self.universes["daily_trade"])

    def test_08_non_bist30_can_reach_high_movement(self):
        self.assertIn("DDD.IS", self.universes["high_movement"])

    def test_09_non_bist30_under_50_can_pass_price_filter(self):
        frame = pd.DataFrame({"Hisse": ["CCC"], "Fiyat": [25.0]})
        self.assertEqual(valid_under_50(frame)["Hisse"].tolist(), ["CCC"])

    def test_10_non_bist30_never_reaches_short_frame(self):
        frame = pd.DataFrame({"Hisse": ALL_BIST, "Fiyat": [1, 2, 3, 4]})
        self.assertEqual(filter_frame_to_symbols(frame, self.universes["short_term"])["Hisse"].tolist(), BIST30)

    def test_11_non_bist30_never_reaches_medium_frame(self):
        frame = pd.DataFrame({"Hisse": ALL_BIST, "Fiyat": [1, 2, 3, 4]})
        self.assertEqual(filter_frame_to_symbols(frame, self.universes["medium_term"])["Hisse"].tolist(), BIST30)

    def test_12_short_and_medium_have_separate_results(self):
        source = pd.DataFrame({"Hisse": ["AAA"], "Skor": [70]})
        short = tag_analysis_result(source, "short_term", "scan")
        medium = tag_analysis_result(source, "medium_term", "scan")
        self.assertNotEqual(short.loc[0, "Analiz Türü"], medium.loc[0, "Analiz Türü"])
        self.assertNotEqual(short.loc[0, "Cache Anahtarı"], medium.loc[0, "Cache Anahtarı"])

    def test_13_page_results_are_independent_frames(self):
        source = pd.DataFrame({"Hisse": ["AAA"]})
        daily = tag_analysis_result(source, "daily_trade", "scan")
        short = tag_analysis_result(source, "short_term", "scan")
        daily.loc[0, "Hisse"] = "DDD"
        self.assertEqual(short.loc[0, "Hisse"], "AAA")

    def test_14_cache_key_contains_analysis_type(self):
        first = AnalysisCacheKey("AAA", "daily_trade", "ALL_ACTIVE_BIST", "t", "v", "s")
        second = AnalysisCacheKey("AAA", "short_term", "BIST30", "t", "v", "s")
        self.assertNotEqual(first.value(), second.value())
        self.assertEqual(first.analysis_type, "daily_trade")

    def test_15_contract_contains_all_main_stock_tasks(self):
        self.assertEqual(set(ANALYSIS_UNIVERSES),
                         {"daily_trade", "short_term", "medium_term", "under_50", "high_movement"})

    def test_16_fund_analysis_is_not_in_stock_contract(self):
        self.assertNotIn("fund_analysis", ANALYSIS_UNIVERSES)

    def test_17_progress_waits_for_every_task(self):
        state = ScanCoordinator("scan")
        for name in COMPONENTS:
            state.start_component(name)
        state.stock_total = state.stock_completed = 4
        for name in COMPONENTS:
            if name != "high_movement":
                state.finish_component(name)
        self.assertLess(state.percent, 100)
        state.finish_component("high_movement")
        self.assertEqual(state.percent, 100)

    def test_18_universe_builder_never_fills_missing_symbols(self):
        result = build_analysis_universes(["AAA"], ["AAA", "BBB"])
        self.assertEqual(result["short_term"], ["AAA.IS"])

    def test_19_new_ipo_is_not_removed_from_all_bist_radar_input(self):
        result = build_analysis_universes(ALL_BIST + ["IPO1.IS"], BIST30)
        self.assertIn("IPO1.IS", result["high_movement"])

    def test_20_symbols_are_normalized_and_deduplicated(self):
        result = build_analysis_universes(["aaa", "AAA.IS", "bbb"], ["aaa", "bbb"])
        self.assertEqual(result["daily_trade"], ["AAA.IS", "BBB.IS"])


if __name__ == "__main__":
    unittest.main()
