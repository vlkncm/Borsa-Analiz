import json
import unittest
from unittest.mock import patch

import pandas as pd

from fon_analizi import (
    _embedded_object, en_iyi_fonlari_sec, fon_kurumunu_bul, fonlari_puanla,
    tefas_liste_verisini_ayikla,
)


class FonAnaliziTest(unittest.TestCase):
    def test_tefas_embedded_list_parser(self):
        data = [{"fonKodu": "AAA", "fonUnvan": "İçinde ] işareti olan fon", "tefasDurum": True}]
        html = "x initialFundListingData\\\":" + json.dumps(data).replace('"', '\\"') + ",\\\"next\\\":1"
        self.assertEqual(tefas_liste_verisini_ayikla(html)[0]["fonKodu"], "AAA")

    def test_serbest_olmayan_ve_eksik_fonlari_dislar(self):
        records = [
            {"fonKodu": "AAA", "fonUnvan": "A", "fonTurAciklama": "Hisse Senedi Şemsiye Fonu", "tefasDurum": True,
             "riskDegeri": "6", "getiri1a": 12, "getiri3a": 30, "getiri6a": 50, "getiri1y": 80},
            {"fonKodu": "BBB", "fonUnvan": "B", "fonTurAciklama": "Serbest Fon", "tefasDurum": False,
             "riskDegeri": "7", "getiri1a": 40, "getiri3a": 80, "getiri6a": 100},
            {"fonKodu": "CCC", "fonUnvan": "C", "fonTurAciklama": "Hisse", "tefasDurum": True,
             "riskDegeri": None, "getiri1a": 20, "getiri3a": 30, "getiri6a": 40},
        ]
        result = fonlari_puanla(records)
        self.assertEqual(result["Fon Kodu"].tolist(), ["AAA"])
        self.assertIn("garanti değildir", result.iloc[0]["Uyarı"])

    def test_detay_json_nesnesini_ayiklar(self):
        html = 'x bilgiData\\":{\\"fonKodu\\":\\"AAA\\",\\"sonFiyat\\":1.25},\\"next\\":1'
        result = _embedded_object(html, 'bilgiData\\":')
        self.assertEqual(result["fonKodu"], "AAA")
        self.assertEqual(result["sonFiyat"], 1.25)

    def test_kurucu_kurum_oncelikli_alanlardan_bulunur(self):
        self.assertEqual(
            fon_kurumunu_bul({"kurucuUnvan": "ABC PORTFÖY YÖNETİMİ A.Ş."}),
            "ABC PORTFÖY YÖNETİMİ A.Ş.",
        )

    def test_kurum_yoksa_fon_adindan_tahmin_edilmez(self):
        self.assertEqual(
            fon_kurumunu_bul({}, "AKBANK BİRİNCİ FON"),
            "TEFAS detayında kurum bilgisi yok",
        )

    @patch("fon_analizi.tefas_fon_detayi")
    @patch("fon_analizi.fon_taramasi")
    def test_en_fazla_uc_fon_secer_ve_kurumu_yazar(self, scan, detail):
        scan.return_value = (pd.DataFrame([
            {
                "Fon Kodu": f"F{i}", "Fon Adı": f"Fon {i}", "Karar": "GÜÇLÜ İZLE",
                "Momentum Puanı": 90 - i, "Risk": 4, "1 Ay %": 4 + i,
                "3 Ay %": 12 + i, "6 Ay %": 20 + i,
                "Çıkış Koşulu": "momentum zayıflarsa azalt",
            }
            for i in range(5)
        ]), "test")
        detail.return_value = {
            "sonFiyat": 1.25, "kurucuUnvan": "TEST PORTFÖY",
            "fonSatisValor": 1, "fonGeriAlisValor": 2,
        }
        _frame, _source, result = en_iyi_fonlari_sec(sermaye=30000, adet=3)
        self.assertEqual(len(result["fonlar"]), 3)
        self.assertIn("TEST PORTFÖY", result["rapor"])
        self.assertIn("2 ay", result["rapor"])


if __name__ == "__main__":
    unittest.main()
