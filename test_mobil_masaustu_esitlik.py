import json
import subprocess
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from sade_karar_modeli import elli_tl_ohlcv_adayi


ROOT = Path(__file__).resolve().parent


class MobilMasaustuEsitlikTesti(unittest.TestCase):
    def test_elli_tl_adayi_worker_ile_birebir_eslesir(self):
        index = pd.date_range("2025-01-02", periods=240, freq="B", tz="Europe/Istanbul")
        trend = np.linspace(18.0, 29.0, len(index))
        wave = np.sin(np.arange(len(index)) / 5.0) * 0.45
        close = trend + wave
        frame = pd.DataFrame({
            "Open": close - 0.12,
            "High": close + 0.55,
            "Low": close - 0.60,
            "Close": close,
            "Volume": np.full(len(index), 1_500_000.0),
        }, index=index)
        desktop = elli_tl_ohlcv_adayi("TEST.IS", frame)
        self.assertIsNotNone(desktop)

        rows = [
            {"t": int(ts.timestamp()), "c": float(row.Close), "h": float(row.High),
             "l": float(row.Low), "v": float(row.Volume)}
            for ts, row in frame.iterrows()
        ]
        script = (
            "import fs from 'node:fs';"
            "let source=fs.readFileSync('./worker.js','utf8');"
            "const symbols=fs.readFileSync('./bist_hisseleri_613_aktif.txt','utf8');"
            "source=source.replace('import bistSymbolsText from \"./bist_hisseleri_613_aktif.txt\";',"
            "`const bistSymbolsText=${JSON.stringify(symbols)};`);"
            "const module=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));"
            "let s=''; process.stdin.on('data',c=>s+=c);"
            "process.stdin.on('end',()=>console.log(JSON.stringify({candidate:module.scoreCandidate('TEST',JSON.parse(s)),total:module.SCAN_SYMBOLS.length})));"
        )
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script], input=json.dumps(rows), text=True,
            cwd=ROOT, capture_output=True, check=True,
        )
        payload = json.loads(completed.stdout)
        mobile = payload["candidate"]
        expected_symbols = {line.strip().replace(".IS", "") for line in
                            (ROOT / "bist_hisseleri_613_aktif.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
        self.assertEqual(payload["total"], len(expected_symbols))

        self.assertEqual(desktop["Formül Sürümü"], mobile["formulaVersion"])
        self.assertEqual(desktop["Strateji Sürümü"], mobile["strategyVersion"])
        self.assertEqual(desktop["Skor"], mobile["score"])
        self.assertAlmostEqual(desktop["Mevcut Fiyat"], round(mobile["price"], 2), places=2)
        self.assertAlmostEqual(desktop["Hedef"], round(mobile["target"], 2), places=2)
        self.assertAlmostEqual(desktop["Stop"], round(mobile["stop"], 2), places=2)
        self.assertAlmostEqual(desktop["Risk/Getiri"], round(mobile["rr"], 2), places=2)


if __name__ == "__main__":
    unittest.main()
