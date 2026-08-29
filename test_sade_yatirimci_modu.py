import tempfile
import unittest
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import QApplication

from portfoy_kayitlari import (PortfolioPosition,load_positions,portfolio_decision,
                                upsert_position)
from sade_yatirimci_modu import (MAIN_COLUMNS,confidence_evidence,expected_duration,
                                  independent_evidence,main_columns_are_simple,
                                  simple_investor_frame,simplify_record)


def candidate(symbol="AAA",decision="AL ADAYI – CANLI TEYİT BEKLE",probability=72,samples=126):
    return {"Hisse":symbol,"T+1 Kararı":decision,"Güncel Fiyat":10.0,"T+1 Giriş":10.1,
            "T+1 Hedef":11.0,"T+1 Stop":9.5,"T+1 Seçkin Aday":True,
            "Olasılık Güvenilir":True,"Geçmiş Örnek Sayısı":samples,
            "T+1 %7+ Olasılığı":probability,"data_freshness":"GUNCEL",
            "Piyasa Rejimi":"POZİTİF","EMA20":9.8,"EMA50":9.4,"RSI":58,"Hacim Oranı":1.4}


class SadeYatirimciModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def test_every_analysis_shows_at_most_five(self):
        frame=pd.DataFrame([candidate(f"S{i}") for i in range(9)])
        for analysis in ("high_movement_radar","daily_trade","short","medium","under50","fund_analysis"):
            self.assertLessEqual(len(simple_investor_frame(frame,analysis)),5)

    def test_list_is_not_filled_with_failed_thresholds(self):
        rows=[candidate("OK")]+[candidate(f"NO{i}","ALMA") for i in range(8)]
        result=simple_investor_frame(pd.DataFrame(rows),"high_movement_radar")
        self.assertEqual(1,len(result)); self.assertEqual("OK",result.iloc[0]["Hisse"])

    def test_non_portfolio_stock_never_says_sell(self):
        row=candidate(decision="SAT")
        self.assertNotEqual("SAT",simplify_record(row,"short",held=False)["Karar"])

    def test_held_stock_profit_take_and_sell_work(self):
        position=PortfolioPosition("AAA",100,10,"2026-08-01",target=12,stop=9)
        self.assertEqual("KÂR AL",portfolio_decision(position,11.8)["decision"])
        self.assertEqual("SAT",portfolio_decision(position,8.9)["decision"])
        self.assertEqual("BEKLE",portfolio_decision(position,12.2,momentum_weak=False)["decision"])

    def test_duration_uses_horizon_and_historical_median(self):
        row=candidate(); row.update({"Başarılılarda Medyan Süre":2,"OOS Örnek Sayısı":80})
        self.assertEqual("1–3 işlem günü",expected_duration(row,"high_movement_radar")[0])
        self.assertEqual("1–2 ay",expected_duration({},"medium")[0])

    def test_insufficient_sample_never_invents_percentage(self):
        level,text,probability,_=confidence_evidence({"Doğrulanmış Olasılık %":99,"Doğrulama Örnek Sayısı":5},"short")
        self.assertEqual("Ölçülemedi",level); self.assertIsNone(probability); self.assertNotIn("%99",text)

    def test_different_symbols_can_produce_different_plain_explanations(self):
        trend=candidate("TREND"); weak=candidate("WEAK"); weak.update({"EMA20":11,"EMA50":12,"RSI":80,"Hacim Oranı":.5,"Piyasa Rejimi":"NEGATİF"})
        a=simplify_record(trend,"short"); b=simplify_record(weak,"short")
        self.assertNotEqual(a["Neden AL?"],b["Neden AL?"])

    def test_correlated_trend_indicators_count_as_one_group(self):
        base={"Fiyat":10,"EMA20":9,"EMA50":8}
        duplicated={**base,"EMA5":9.9,"EMA10":9.7,"EMA200":5,"SMA200":5,"SuperTrend":"AL"}
        self.assertEqual(independent_evidence(base)[0],independent_evidence(duplicated)[0])

    def test_main_table_has_only_plain_columns(self):
        result=simple_investor_frame(pd.DataFrame([candidate()]),"high_movement_radar")
        self.assertTrue(main_columns_are_simple(MAIN_COLUMNS)); self.assertTrue(set(MAIN_COLUMNS).issubset(result.columns))

    def test_plain_detail_contains_reason_risk_and_change_condition(self):
        row=simplify_record(candidate(),"high_movement_radar")
        self.assertTrue(row["Neden AL?"]); self.assertTrue(row["Ana Risk"]); self.assertTrue(row["Karar Ne Zaman Değişir?"])

    def test_stale_data_cannot_produce_buy(self):
        row=candidate(); row["data_freshness"]="ESKI"
        self.assertNotEqual("AL",simplify_record(row,"high_movement_radar")["Karar"])
        self.assertTrue(simple_investor_frame(pd.DataFrame([row]),"high_movement_radar").empty)

    def test_no_candidate_returns_empty_frame(self):
        result=simple_investor_frame(pd.DataFrame([candidate(decision="ALMA")]),"short")
        self.assertTrue(result.empty)

    def test_portfolio_buy_price_and_date_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"portfolio.json"; position=PortfolioPosition("AAA",20,12.5,"2026-08-20",14,11)
            upsert_position(path,position); loaded=load_positions(path)
            self.assertEqual(position,loaded[0])

    def test_simple_pages_render_only_eight_plain_columns_and_five_rows(self):
        from app_qt import SimpleTable
        frame=pd.DataFrame([candidate(f"S{i}") for i in range(8)])
        for title in ("KISA VADE FIRSATLARI","ORTA VADE FIRSATLARI","50 TL ALTI HİSSE FIRSATLARI","Fon Karar Merkezi","Adaylar"):
            page=SimpleTable(title); page.load(frame)
            self.assertEqual(5,page.table.rowCount()); self.assertEqual(MAIN_COLUMNS,[page.table.horizontalHeaderItem(i).text() for i in range(8)])
            page.deleteLater()

    def test_empty_page_explains_that_thresholds_were_not_lowered(self):
        from app_qt import SimpleTable
        page=SimpleTable("KISA VADE FIRSATLARI"); page.load(pd.DataFrame([candidate(decision="ALMA")]))
        self.assertEqual(0,page.table.rowCount()); self.assertIn("yeterince güvenilir aday bulunamadı",page.info.text())
        page.deleteLater()


if __name__=="__main__": unittest.main()
