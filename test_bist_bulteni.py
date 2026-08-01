import io
import unittest
import zipfile
from datetime import date

import pandas as pd

from bist_bulteni import bulten_zip_coz
from veri_saglayici import _bist_ile_birlestir


def ornek_zip() -> bytes:
    baslik = (
        "TARIH;ISLEM  KODU;ACILIS FIYATI;EN DUSUK FIYAT;EN YUKSEK FIYAT;"
        "KAPANIS FIYATI;TOPLAM ISLEM ADEDI\n"
    )
    ingilizce = (
        "TRADE DATE;INSTRUMENT SERIES CODE;OPENING PRICE;LOWEST PRICE;HIGHEST PRICE;"
        "CLOSING PRICE;TOTAL TRADED VOLUME\n"
    )
    satir = "2026-07-31;MEGMT.E;71.6;68.15;72.1;68.15;4239976\n"
    cikti = io.BytesIO()
    with zipfile.ZipFile(cikti, "w") as arsiv:
        arsiv.writestr("thb202607311.csv", baslik + ingilizce + satir)
    return cikti.getvalue()


class BistBulteniTesti(unittest.TestCase):
    def test_resmi_zip_megmt_satirini_cozer(self):
        tarih, hisseler = bulten_zip_coz(ornek_zip())
        self.assertEqual(tarih, date(2026, 7, 31))
        self.assertEqual(hisseler["MEGMT"]["Close"], 68.15)
        self.assertEqual(hisseler["MEGMT"]["Volume"], 4239976)

    def test_resmi_satir_seriye_eklenir(self):
        eski = pd.DataFrame(
            [{"Open": 74.75, "High": 76.8, "Low": 71.4, "Close": 71.6, "Adj Close": 71.6, "Volume": 9737003}],
            index=pd.DatetimeIndex(["2026-07-30"]),
        )
        from unittest.mock import patch

        resmi = pd.DataFrame(
            [{"Open": 71.6, "High": 72.1, "Low": 68.15, "Close": 68.15, "Adj Close": 68.15, "Volume": 4239976}],
            index=pd.DatetimeIndex(["2026-07-31"]),
        )
        with patch("veri_saglayici.resmi_gunluk_satir", return_value=resmi):
            sonuc = _bist_ile_birlestir("MEGMT.IS", "1d", eski)
        self.assertEqual(len(sonuc), 2)
        self.assertEqual(float(sonuc.iloc[-1]["Close"]), 68.15)
        self.assertIn("Borsa İstanbul", sonuc.attrs["veri_kaynagi"])


if __name__ == "__main__":
    unittest.main()
