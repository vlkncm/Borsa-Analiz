import json
import unittest

from fon_analizi import _embedded_object, fonlari_puanla, tefas_liste_verisini_ayikla


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


if __name__ == "__main__":
    unittest.main()
