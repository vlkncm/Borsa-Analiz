import unittest
from faktor_model_portfoy import faktor_model_portfoyu


class FaktorModelTests(unittest.TestCase):
    def test_selects_equal_weighted_liquid_candidates(self):
        data = [{"symbol": f"T{i}.IS", "fk": 5+i, "pddd": 1+i/10, "roe": .2, "kar_marji": .1, "borc_ozsermaye": 50, "ortalama_gunluk_islem_tutari": 1_000_000+i, "v4_momentum_puani": 70, "kap_etiket": "Nötr", "sector": f"S{i%5}"} for i in range(12)]
        out = faktor_model_portfoyu(data, adet=8)
        self.assertEqual(len(out), 8)
        self.assertAlmostEqual(out["Portföy Ağırlığı %"].sum(), 100, places=1)
