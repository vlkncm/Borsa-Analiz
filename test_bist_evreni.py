import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from bist_evreni import likit_120_sec, tum_bist_hisseleri


class BistEvreniTests(unittest.TestCase):
    def test_resmi_kaynak_yoksa_613_aktif_liste_kullanilir(self):
        with tempfile.TemporaryDirectory() as folder, patch("requests.get", side_effect=RuntimeError("offline")):
            symbols = tum_bist_hisseleri(folder, refresh=True)
        self.assertGreaterEqual(len(symbols), 600)
        self.assertTrue(all(x.endswith(".IS") for x in symbols))

    def test_likit_on_eleme_en_fazla_120_hisse_secer(self):
        frame = pd.DataFrame({"Hisse": [f"H{i}" for i in range(150)], "Ortalama Günlük İşlem Tutarı": range(150)})
        result = likit_120_sec(frame)
        self.assertEqual(120, len(result))
        self.assertEqual("H149", result.iloc[0]["Hisse"])


if __name__ == "__main__":
    unittest.main()
