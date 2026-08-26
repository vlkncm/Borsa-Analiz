import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from analiz_deposu import SnapshotWriteResult, anlik_goruntu_oku, anlik_goruntu_yaz, dataframe_dogrula
from main import analiz_ciktilarini_kaydet, sonuclari_kaydet, tabloya_cevir


class Unsupported:
    def __str__(self): return "özel-nesne"


class AnalizDeposuTests(unittest.TestCase):
    def test_none_atlanir(self):
        safe, reason = dataframe_dogrula("Kisa Vade", None)
        self.assertIsNone(safe); self.assertIn("None", reason)

    def test_sifir_satir_sifir_sutun_sql_hatasi_uretmez(self):
        with tempfile.TemporaryDirectory() as folder:
            result = anlik_goruntu_yaz(Path(folder)/"db.sqlite3", {"Backtest Ozet": pd.DataFrame()})
            self.assertFalse(result); self.assertIn("Backtest Ozet", result.skipped)

    def test_sifir_satir_gecerli_sema_onceki_tabloyu_korur(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"db.sqlite3"
            anlik_goruntu_yaz(path, {"Tum Sonuclar":pd.DataFrame([{"Hisse":"A"}]), "Kisa Vade":pd.DataFrame([{"Hisse":"ESKI"}])})
            result=anlik_goruntu_yaz(path, {"Tum Sonuclar":pd.DataFrame([{"Hisse":"B"}]), "Kisa Vade":pd.DataFrame(columns=["Hisse"])})
            self.assertTrue(result); self.assertEqual(anlik_goruntu_oku(path)["Kisa Vade"].iloc[0]["Hisse"], "ESKI")

    def test_tek_ve_birden_fazla_gecerli_sonuc(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"db.sqlite3"; frame=pd.DataFrame([{"Hisse":"A"},{"Hisse":"B"}])
            self.assertTrue(anlik_goruntu_yaz(path,{"Tum Sonuclar":frame.iloc[:1]}))
            self.assertTrue(anlik_goruntu_yaz(path,{"Tum Sonuclar":frame}))
            self.assertEqual(len(anlik_goruntu_oku(path)["Tum Sonuclar"]),2)

    def test_turkce_ozel_ve_ayni_isimli_kolonlar(self):
        with tempfile.TemporaryDirectory() as folder:
            frame=pd.DataFrame([["A",1,2]],columns=["Hisse","Güven %","Güven %"]); path=Path(folder)/"db.sqlite3"
            self.assertTrue(anlik_goruntu_yaz(path,{"Tum Sonuclar":frame}))
            columns=list(anlik_goruntu_oku(path)["Tum Sonuclar"].columns)
            self.assertEqual(columns,["Hisse","Güven %","Güven %__2"])

    def test_sqlite_uyumsuz_nesneler_donusturulur(self):
        with tempfile.TemporaryDirectory() as folder:
            frame=pd.DataFrame([{"Hisse":"A","Liste":[1,2],"Sozluk":{"x":1},"Nesne":Unsupported()}]); path=Path(folder)/"db.sqlite3"
            self.assertTrue(anlik_goruntu_yaz(path,{"Tum Sonuclar":frame}))
            row=anlik_goruntu_oku(path)["Tum Sonuclar"].iloc[0]
            self.assertEqual(row["Liste"],"[1, 2]"); self.assertEqual(row["Nesne"],"özel-nesne")

    def test_append_ve_ilk_olusturma(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"db.sqlite3"
            self.assertTrue(anlik_goruntu_yaz(path,{"Tum Sonuclar":pd.DataFrame([{"Hisse":"A"}])}))
            self.assertTrue(anlik_goruntu_yaz(path,{"Tum Sonuclar":pd.DataFrame([{"Hisse":"B"}])},if_exists="append"))
            self.assertEqual(anlik_goruntu_oku(path)["Tum Sonuclar"]["Hisse"].tolist(),["A","B"])

    def test_yazilamayan_yol_acik_basarisizlik_dondurur(self):
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder)/"dosya"; parent.write_text("x")
            result=anlik_goruntu_yaz(parent/"db.sqlite3",{"Tum Sonuclar":pd.DataFrame([{"Hisse":"A"}])})
            self.assertFalse(result); self.assertIn("snapshot",result.errors)

    def test_hatali_yeni_kayit_eski_gecerli_snapshotu_silmez(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"db.sqlite3"; anlik_goruntu_yaz(path,{"Tum Sonuclar":pd.DataFrame([{"Hisse":"ESKI"}])})
            result=anlik_goruntu_yaz(path,{"Tum Sonuclar":pd.DataFrame([{"Fiyat":10}])})
            self.assertFalse(result); self.assertEqual(anlik_goruntu_oku(path)["Tum Sonuclar"].iloc[0]["Hisse"],"ESKI")

    def test_bir_opsiyonel_tablo_hatasi_ana_kaydi_kaybettirmez(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"db.sqlite3"; original=pd.DataFrame.to_sql
            def selective(frame,name,con,*args,**kwargs):
                if name=="kisa_vade": raise sqlite3.OperationalError("test hatası")
                return original(frame,name,con,*args,**kwargs)
            with patch.object(pd.DataFrame,"to_sql",selective):
                result=anlik_goruntu_yaz(path,{"Tum Sonuclar":pd.DataFrame([{"Hisse":"A"}]),"Kisa Vade":pd.DataFrame([{"Hisse":"K"}])})
            self.assertTrue(result); self.assertIn("Kisa Vade",result.errors); self.assertEqual(anlik_goruntu_oku(path)["Tum Sonuclar"].iloc[0]["Hisse"],"A")

    def test_sqlite_hatasinda_csv_yedegi_korunur_ve_exception_yoktur(self):
        with tempfile.TemporaryDirectory() as folder:
            frame=pd.DataFrame([{"Hisse":"A","Fiyat":10}]); failed=SnapshotWriteResult(errors={"snapshot":"disk hatası"})
            with patch("analiz_deposu.anlik_goruntu_yaz",return_value=failed):
                report=analiz_ciktilarini_kaydet(frame,{"Tum Sonuclar":frame},Path(folder))
            self.assertTrue(report["csv_backup"].exists()); self.assertEqual(pd.read_csv(report["csv_backup"])["Hisse"].tolist(),["A"])

    def test_sonucsuz_tarama_normal_doner_ve_onceki_snapshotu_hedeflemez(self):
        report=sonuclari_kaydet([],0)
        self.assertTrue(report["skipped"]); self.assertIsNone(report["sqlite"])

    def test_gercek_tarama_donusumu_sqlite_ve_csv_ayni_temel_semayi_tasir(self):
        with tempfile.TemporaryDirectory() as folder:
            frame=tabloya_cevir([{"symbol":"TEST.IS","price":10.0}]); path=Path(folder)/"analiz.sqlite3"
            result=anlik_goruntu_yaz(path,{"Tum Sonuclar":frame,"Backtest Ozet":pd.DataFrame()})
            self.assertTrue(result); stored=anlik_goruntu_oku(path)["Tum Sonuclar"]
            csv=Path(folder)/"same.csv"; frame.to_csv(csv,index=False,encoding="utf-8-sig"); from_csv=pd.read_csv(csv)
            self.assertEqual(list(stored.columns),list(frame.columns)); self.assertEqual(list(from_csv.columns),list(frame.columns))
            with closing(sqlite3.connect(path)) as db:
                schema=[row[1] for row in db.execute('PRAGMA table_info("tum_sonuclar")')]
            self.assertEqual(schema,list(frame.columns)); self.assertEqual(stored.iloc[0]["Hisse"],"TEST.IS")


if __name__ == "__main__": unittest.main()
