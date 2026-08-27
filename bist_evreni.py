"""Aktif BIST pay evreni ve likidite ön elemesi."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from bist30 import normalize_bist_sembolu


KAP_URL = "https://kap.org.tr/tr/bist-sirketler"
EVREN_TTL_SAAT = 24
MIN_GECERLI_EVREN = 400
_LOGGER = logging.getLogger(__name__)
_LOCK = threading.RLock()
_SON_DURUM: dict = {}


@dataclass(frozen=True)
class EvrenDurumu:
    source: str
    created_at: str
    last_used_at: str
    symbol_count: int
    refreshed: bool
    stale: bool
    warning: str = ""
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


def son_evren_durumu() -> dict:
    return dict(_SON_DURUM)


def _atomik_json_yaz(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=path.parent)
    os.close(handle)
    temp = Path(name)
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _cache_payload(cache: Path) -> dict:
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        symbols = sorted({normalize_bist_sembolu(x) for x in payload.get("symbols", []) if normalize_bist_sembolu(x)})
        if not symbols:
            return {}
        return {**payload, "symbols": symbols}
    except (ValueError, TypeError, OSError):
        return {}


def _bulten_sembolleri() -> list[str]:
    """Son resmi bultendeki islem goren paylari evren kesif kaynagi olarak kullan."""
    from sembol_esleme import saglayici_sembolu
    path = Path(os.getenv("LOCALAPPDATA") or (Path.home()/"AppData"/"Local")) / "BorsaAnalizProMAX" / "bist_son_bulten.json"
    try:
        from bist_bulteni import son_bulten
        _date, rows = son_bulten(path.parent)
        if rows:
            return sorted({saglayici_sembolu(code, "yahoo") for code in rows})
    except Exception:
        pass
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return sorted({saglayici_sembolu(code, "yahoo") for code in payload.get("hisseler", {})})
    except Exception:
        return []


def _kap_sembolleri(timeout: int = 20) -> list[str]:
    import requests
    response = requests.get(KAP_URL, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    codes = re.findall(r'(?:member|company|sirket)[^>"\']*[/>="\']+([A-Z0-9]{2,12})(?:["\'/<])', response.text, flags=re.I)
    symbols = sorted({normalize_bist_sembolu(code) for code in codes if normalize_bist_sembolu(code)})
    if len(symbols) < MIN_GECERLI_EVREN:
        raise ValueError("Resmi sayfadan yeterli hisse kodu ayiklanamadi")
    return symbols


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
    """Guncel resmi kaynaklari birlestir; hata halinde son gecerli evreni koru."""
    global _SON_DURUM
    folder = Path(cache_dir) if cache_dir else Path.home() / "Documents" / "Borsa Analiz Pro MAX" / "piyasa_verileri"
    cache = folder / "tum_bist_evreni.json"
    now = datetime.now()
    with _LOCK:
        previous = _cache_payload(cache) if cache.exists() else {}
    if previous and not refresh:
        try:
            when = datetime.fromisoformat(previous.get("created_at", previous.get("updated_at")))
            if now - when < timedelta(hours=EVREN_TTL_SAAT):
                previous["last_used_at"] = now.isoformat(timespec="seconds")
                with _LOCK:
                    _atomik_json_yaz(cache, previous)
                _SON_DURUM = asdict(EvrenDurumu(
                    previous.get("source", "Gecerli evren onbellegi"), str(when), previous["last_used_at"],
                    len(previous["symbols"]), False, False,
                ))
                return previous["symbols"]
        except (ValueError, KeyError, OSError):
            pass
    try:
        source_errors = []
        try:
            kap_symbols = _kap_sembolleri()
        except Exception as exc:
            kap_symbols = []
            source_errors.append(f"KAP: {exc}")
        try:
            bulletin_symbols = _bulten_sembolleri()
        except Exception as exc:
            bulletin_symbols = []
            source_errors.append(f"BIST bulteni: {exc}")
        symbols = sorted(set(kap_symbols) | set(bulletin_symbols))
        if len(symbols) < MIN_GECERLI_EVREN:
            raise ValueError("Birlestirilmis resmi evren gecersiz derecede kucuk; " + "; ".join(source_errors))
        source_names = []
        if kap_symbols: source_names.append("KAP aktif sirketler")
        if bulletin_symbols: source_names.append("Borsa Istanbul son resmi bulten")
        old = set(previous.get("symbols", _yerel_liste()))
        added, removed = tuple(sorted(set(symbols)-old)), tuple(sorted(old-set(symbols)))
        payload = {
            "schema_version": 2, "created_at": now.isoformat(timespec="seconds"),
            "updated_at": now.isoformat(timespec="seconds"), "last_used_at": now.isoformat(timespec="seconds"),
            "expires_at": (now+timedelta(hours=EVREN_TTL_SAAT)).isoformat(timespec="seconds"),
            "source": " + ".join(source_names), "source_warnings": source_errors, "symbols": symbols,
            "added": list(added), "removed": list(removed),
        }
        with _LOCK:
            _atomik_json_yaz(cache, payload)
        if added or removed:
            _LOGGER.info("Aktif BIST evreni yenilendi: +%s -%s", ",".join(added) or "-", ",".join(removed) or "-")
        warning = "; ".join(source_errors)
        _SON_DURUM = asdict(EvrenDurumu(payload["source"], payload["created_at"], payload["last_used_at"], len(symbols), True, False, warning, added, removed))
        return symbols
    except Exception as exc:
        fallback = sorted(set(previous.get("symbols", [])) | set(_yerel_liste()) | set(_bulten_sembolleri()))
        warning = f"Aktif BIST evreni yenilenemedi; son gecerli kaynak kullanildi: {exc}"
        _LOGGER.warning(warning)
        created = previous.get("created_at", previous.get("updated_at", "bilinmiyor"))
        _SON_DURUM = asdict(EvrenDurumu("Son gecerli cache/paket/resmi bulten", created, now.isoformat(timespec="seconds"), len(fallback), False, True, warning))
        return fallback


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
