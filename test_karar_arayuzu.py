import unittest

import pandas as pd

from app_qt import karar_gruplarina_ayir, tarama_alt_sureci_komutu


class KararArayuzuTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
