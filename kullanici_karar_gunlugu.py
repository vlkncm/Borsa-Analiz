"""Kullanıcının sinyale uyup uymadığını denetlenebilir biçimde kaydeder."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


COLUMNS = ["Zaman", "Hisse", "Karar", "Neden", "Giriş Fiyatı", "Not"]


def _path(path: Path | None = None) -> Path:
    result = path or (Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "performans" / "kullanici_kararlari.csv")
    result.parent.mkdir(parents=True, exist_ok=True)
    return result


def karar_kaydet(hisse: str, karar: str, neden: str = "", giris_fiyati: float = 0.0, not_: str = "", path: Path | None = None) -> Path:
    """ALDI, ALMADI veya İZLEMEDE kararını yerel günlüğe ekler."""
    output = _path(path)
    new_file = not output.exists()
    with output.open("a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow({"Zaman": datetime.now().isoformat(timespec="minutes"), "Hisse": hisse.upper(), "Karar": karar.upper(), "Neden": neden, "Giriş Fiyatı": round(float(giris_fiyati or 0), 2), "Not": not_})
    return output


def kararlari_oku(path: Path | None = None) -> List[Dict[str, str]]:
    source = _path(path)
    if not source.exists():
        return []
    with source.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))
