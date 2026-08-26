import unittest

from profesyonel_karar_sistemi import (
    REGIMES, birinci_asama_uygula, piyasa_rejimi_hesapla, sektor_profilleri_hesapla,
)


def market_rows(count=40, positive=True, sector="BANKA"):
    rows = []
    for i in range(count):
        price = 120 if positive else 70
        rows.append({
            "symbol": f"T{i}.IS", "price": price,
            "ema20": 110 if positive else 80, "ema50": 100 if positive else 90,
            "ema200": 90 if positive else 100, "adx": 28,
            "atr": 2.0, "ret_20": 8 if positive else -12, "ret_60": 18 if positive else -22,
            "volume_ratio": 1.3 if positive else .8, "sektor": sector,
            "veri_guven_puani": 90, "veri_yasi_gun": 1,
            "veri_kalite_onayli": True, "veri_kalite_notu": "Uygun",
        })
    return rows


class ProfesyonelKararAsama1Tests(unittest.TestCase):
    def test_empty_market_is_uncertain_not_risk_on(self):
        result = piyasa_rejimi_hesapla([])
        self.assertEqual(result["regime"], "YATAY")
        self.assertGreater(result["uncertainty_penalty"], 0)

    def test_positive_breadth_produces_valid_risk_on_regime(self):
        result = piyasa_rejimi_hesapla(market_rows())
        self.assertIn(result["regime"], {"RISK_ON", "GUCLU_RISK_ON"})
        self.assertIn(result["regime"], REGIMES)
        self.assertGreater(result["breadth_above_ema50"], 60)

    def test_negative_breadth_produces_risk_off(self):
        result = piyasa_rejimi_hesapla(market_rows(positive=False))
        self.assertEqual(result["regime"], "RISK_OFF")

    def test_high_atr_produces_high_volatility(self):
        rows = market_rows()
        for row in rows:
            row["atr"] = row["price"] * .06
        self.assertEqual(piyasa_rejimi_hesapla(rows)["regime"], "YUKSEK_OYNAKLIK")

    def test_sector_strength_is_relative_to_market(self):
        rows = market_rows(20, True, "GUCLU") + market_rows(20, False, "ZAYIF")
        market = piyasa_rejimi_hesapla(rows)
        sectors = sektor_profilleri_hesapla(rows, market)
        self.assertGreater(sectors["GUCLU"]["score"], sectors["ZAYIF"]["score"])
        self.assertTrue(sectors["GUCLU"]["verified"])

    def test_unknown_sector_is_not_treated_as_positive(self):
        rows = market_rows(10, True, "")
        sectors = sektor_profilleri_hesapla(rows, piyasa_rejimi_hesapla(rows))
        self.assertFalse(sectors["BİLİNMİYOR"]["verified"])
        self.assertLess(sectors["BİLİNMİYOR"]["score"], 45)

    def test_stage_one_does_not_change_existing_score(self):
        rows = market_rows()
        for row in rows:
            row["v4_guven_puani"] = 77
        output, market, sectors = birinci_asama_uygula(rows)
        self.assertTrue(all(row["v4_guven_puani"] == 77 for row in output))
        self.assertTrue(all("piyasa_rejimi_v2" in row for row in output))
        self.assertTrue(all("sektor_puani" in row for row in output))

    def test_bad_data_cannot_pass_stage_one(self):
        rows = market_rows()
        rows[0]["price"] = 0
        output, _, _ = birinci_asama_uygula(rows)
        self.assertFalse(output[0]["veri_kalite_onayli"])
        self.assertFalse(output[0]["birinci_asama_onayli"])


if __name__ == "__main__":
    unittest.main()
