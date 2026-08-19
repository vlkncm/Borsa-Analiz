import unittest

import pandas as pd
from PySide6.QtWidgets import QApplication

from app_qt import (
    SalePage,
    SearchableTable,
    karar_gruplarina_ayir,
    tarama_alt_sureci_komutu,
)


class KararArayuzuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_kaynak_kodda_tarama_ayri_python_surecinde_baslar(self):
        program, arguments = tarama_alt_sureci_komutu()
        self.assertTrue(program)
        self.assertTrue(any(str(arg).endswith("scan_runner.py") for arg in arguments))

    def test_vade_yerine_alis_kararina_gore_gruplar(self):
        frame = pd.DataFrame({
            "Hisse": ["A", "B", "C", "D", "E"],
            "Yatırım Kararı": [
                "BUGÜN AL", "ALIM BÖLGESİNİ BEKLE", "İZLE - KANIT YETERSİZ", "ALMA", "VERİ KONTROLÜ GEREKLİ"
            ],
        })
        buy, wait, avoid = karar_gruplarina_ayir(frame)
        self.assertEqual(buy["Hisse"].tolist(), ["A"])
        self.assertEqual(wait["Hisse"].tolist(), ["B", "C"])
        self.assertEqual(avoid["Hisse"].tolist(), ["D", "E"])

    def test_satis_sonucu_eksik_sayilarda_arayuzu_dusurmez(self):
        page = SalePage()
        page.done(True, {
            "satis_karari": "VERİ YOK",
            "price": None,
            "kullanici_maliyeti": "100,00",
            "kar_zarar_yuzde": float("nan"),
            "onerilen_satis": None,
            "yeni_stop": "bozuk",
            "kar_realizasyon_orani": None,
        }, "")
        self.assertIn("KARAR: VERİ YOK", page.result.toPlainText())
        self.assertIn("GÜNCEL FİYAT: 0.00 TL", page.result.toPlainText())
        page.deleteLater()

    def test_uygulama_ici_arama_hisse_ve_karari_filtreler(self):
        table = SearchableTable("Arama")
        table.load(pd.DataFrame({
            "Hisse": ["ASELS", "THYAO"],
            "Yatırım Kararı": ["BUGÜN AL", "BEKLE"],
        }))
        table.apply_filter("asels")
        self.assertFalse(table.table.isRowHidden(0))
        self.assertTrue(table.table.isRowHidden(1))
        table.apply_filter("bekle")
        self.assertTrue(table.table.isRowHidden(0))
        self.assertFalse(table.table.isRowHidden(1))
        table.deleteLater()


if __name__ == "__main__":
    unittest.main()
