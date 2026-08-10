import unittest
from usta_yatirimci_modeli import usta_model_portfoyu
class UstaModelTests(unittest.TestCase):
 def test_portfolio_is_equal_weighted(self):
  rows=[{"symbol":f"X{i}.IS","fk":8,"pddd":1.2,"roe":.25,"kar_marji":.15,"borc_ozsermaye":60,"kar_buyume":.2,"ortalama_gunluk_islem_tutari":100_000_000+i,"v4_momentum_puani":70,"piyasa_rejimi":"YATAY","kap_etiket":"Nötr","sector":f"S{i%5}"} for i in range(12)]
  out=usta_model_portfoyu(rows,8); self.assertEqual(len(out),8); self.assertAlmostEqual(out["Portföy Ağırlığı %"].sum(),100,places=1)
