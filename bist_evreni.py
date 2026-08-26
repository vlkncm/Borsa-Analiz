"""Aktif BIST pay evreni ve likidite ön elemesi."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


KAP_URL = "https://kap.org.tr/tr/bist-sirketler"


def _yerel_liste() -> list[str]:
    """Kaynak kodda ve PyInstaller paketinde gelen sabit geri dönüş evrenini oku."""
    roots = [Path(__file__).resolve().parent]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.insert(0, Path(bundle_root))
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys.executable).resolve().parent)
    for root in dict.fromkeys(roots):
        source = root / "bist_hisseleri_613_aktif.txt"
        if source.is_file():
            return sorted({
                line.strip().upper()
                for line in source.read_text(encoding="utf-8").splitlines()
                if re.fullmatch(r"[A-Z0-9]{2,12}\.IS", line.strip().upper())
            })
    return []


def tum_bist_hisseleri(cache_dir: str | Path | None = None, refresh=False) -> list[str]:
    """KAP'tan günlük yeniler; ağ sorusunda son cache veya paketli aktif listeyi döndürür."""
    folder = Path(cache_dir) if cache_dir else Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "piyasa_verileri"
    cache = folder / "tum_bist_evreni.json"
    if cache.exists() and not refresh:
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            when = datetime.fromisoformat(payload["updated_at"])
            if datetime.now() - when < timedelta(hours=24) and payload.get("symbols"):
                return payload["symbols"]
        except (ValueError, KeyError, OSError):
            pass
    try:
        import requests
        response = requests.get(KAP_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        # Sayfadaki şirket kodu bağlantıları. Fon/pazar kodları kabul edilmez.
        codes = re.findall(r'(?:member|company|sirket)[^>"\']*[/>=\"\']+([A-Z0-9]{2,12})(?:[\"\'/<])', response.text, flags=re.I)
        symbols = sorted({f"{code.upper()}.IS" for code in codes if re.fullmatch(r"[A-Z0-9]{2,12}", code.upper())})
        if len(symbols) < 400:
            raise ValueError("Resmi sayfadan yeterli hisse kodu ayıklanamadı")
        folder.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"updated_at": datetime.now().isoformat(), "symbols": symbols}, ensure_ascii=False), encoding="utf-8")
        return symbols
    except Exception:
        if cache.exists():
            try:
                symbols = json.loads(cache.read_text(encoding="utf-8")).get("symbols", [])
                if symbols:
                    return symbols
            except (ValueError, OSError):
                pass
        return _yerel_liste()


def likit_120_sec(frame: pd.DataFrame, limit=120) -> pd.DataFrame:
    """Mevcut analiz sonuçlarından günlük işlem tutarı en yüksek evreni seçer."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    column = next((c for c in ("Ortalama Günlük İşlem Tutarı", "20 Günlük İşlem Tutarı", "Likidite") if c in work), None)
    if column is None:
        return work.head(limit).reset_index(drop=True)
    work["_likidite"] = pd.to_numeric(work[column], errors="coerce").fillna(0)
    return work.sort_values("_likidite", ascending=False).head(limit).drop(columns="_likidite").reset_index(drop=True)
