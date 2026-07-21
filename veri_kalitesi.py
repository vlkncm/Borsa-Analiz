from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


def _state_path() -> Path:
    path = Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "piyasa_verileri" / "sembol_saglik.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def karantinadaki_semboller(esik: int = 2, gun: int = 30) -> set[str]:
    state = _load()
    cutoff = datetime.now() - timedelta(days=gun)
    result = set()
    for symbol, info in state.items():
        try:
            last_failure = datetime.fromisoformat(info.get("son_hata", ""))
        except Exception:
            continue
        if int(info.get("ardisik_hata", 0)) >= esik and last_failure >= cutoff:
            result.add(symbol)
    return result


def tarama_sagligini_kaydet(successful: Iterable[str], failed: Iterable[str]) -> None:
    state = _load()
    now = datetime.now().isoformat(timespec="seconds")
    for symbol in set(successful):
        info = state.setdefault(symbol, {})
        info.update({"ardisik_hata": 0, "son_basarili": now, "durum": "aktif"})
    for symbol in set(failed):
        info = state.setdefault(symbol, {})
        info["ardisik_hata"] = int(info.get("ardisik_hata", 0)) + 1
        info["son_hata"] = now
        info["durum"] = "karantina" if info["ardisik_hata"] >= 2 else "yeniden_dene"
    tmp = _state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_state_path())
