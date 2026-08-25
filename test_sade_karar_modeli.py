import unittest

import pandas as pd

from sade_karar_modeli import buyume_adaylari, en_iyi_vade, on_x_senaryosu, sade_firsatlar
from main import sade_ana_rapor


class SadeKararModeliTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "Hisse": [f"H{i}" for i in range(7)], "Fiyat": [100, 90, 80, 70, 40, 30, 20],
            "Önerilen Alış Alt": [98, 88, 78, 68, 39, 29, 19], "Önerilen Alış Üst": [101, 91, 81, 71, 41, 31, 21],
            "Önerilen Satış": [110, 100, 90, 80, 46, 36, 25], "Önerilen Stop": [95, 85, 75, 65, 37, 27, 18],
            "v4 Güven Puanı": [90, 85, 80, 75, 74, 70, 30], "Veri Durumu": ["GÜVENİLİR"] * 7,
            "Temel Puan": [90, 88, 86, 84, 82, 80, 20], "Broker Skor": [90, 88, 86, 84, 82, 80, 20],
            "Ciro Büyüme": [.30] * 7, "Kâr Büyüme": [.25] * 7, "ROE": [.22] * 7,
            "Borç/Özsermaye": [.5] * 7, "F/K": [12] * 7, "Piyasa Değeri": [1_000_000_000] * 7,
        })

    def test_firsatlar_en_fazla_bes_ve_sade(self):
        result = sade_firsatlar(self.frame, "kisa", limit=5)
        self.assertEqual(5, len(result))
        self.assertNotIn("RSI", result.columns)
        self.assertIn("Alım Bölgesi", result.columns)

    def test_zayif_veride_liste_bos(self):
        frame = self.frame.copy(); frame["v4 Güven Puanı"] = 20
        self.assertTrue(sade_firsatlar(frame, "gunluk").empty)

    def test_vade_out_of_sample_sonucundan_secilir(self):
        backtest = pd.DataFrame({"Tutma Süresi": [5, 10, 20], "Ortalama Getiri %": [2, 4, 8], "Max Drawdown %": [4, 3, 3], "Başarı %": [52, 60, 65], "İşlem Sayısı": [30, 30, 30]})
        self.assertEqual(20, en_iyi_vade(backtest, "kisa")[0])

    def test_buyume_fiyat_limiti_sadece_filtredir(self):
        result = buyume_adaylari(self.frame, fiyat_limiti=50, limit=20, min_score=45)
        self.assertTrue((result["Mevcut Fiyat"] < 50).all())
        self.assertIn("Büyüme Skoru", result)

    def test_10x_market_cap_senaryosu_var(self):
        result = on_x_senaryosu(self.frame)
        self.assertIn("Gerekli 10X Piyasa Değeri", result.columns)
        if not result.empty:
            self.assertTrue((result["Belirsizlik"] == "ÇOK YÜKSEK").all())

    def test_excel_ana_raporu_teknik_jargon_gostermez(self):
        report = sade_ana_rapor(self.frame)
        self.assertEqual(["Hisse", "Analiz Tarihi", "Karar", "Alım Bölgesi", "Referans Fiyat", "Hedef", "Stop", "Potansiyel %", "Tahmini Süre", "Güven Skoru", "Sonuç / Durum"], list(report.columns))
        self.assertNotIn("RSI", report.columns)


if __name__ == "__main__":
    unittest.main()
