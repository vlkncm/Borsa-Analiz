"""Sayfa bazlı analiz anlık görüntülerini güvenli biçimde SQLite'ta saklar."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

TABLES = {
    "Tum Sonuclar": "tum_sonuclar", "Kisa Vade": "kisa_vade", "Orta Vade": "orta_vade",
    "Backtest Ozet": "backtest_ozet", "Sinyal Gecmisi": "sinyal_gecmisi",
    "Sinyal Performansi": "sinyal_performansi",
}
REQUIRED_COLUMNS = {"Tum Sonuclar": {"Hisse"}}


@dataclass
class SnapshotWriteResult:
    success: bool = False
    written: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    path: Path | None = None

    def __bool__(self) -> bool:
        return self.success


def _unique_columns(columns) -> list[str]:
    seen: dict[str, int] = {}; result = []
    for index, raw in enumerate(columns, 1):
        base = str(raw).strip() or f"kolon_{index}"
        count = seen.get(base, 0) + 1; seen[base] = count
        result.append(base if count == 1 else f"{base}__{count}")
    return result


def _sqlite_value(value: Any):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (dict, list, tuple, set)):
        serializable = sorted(value, key=str) if isinstance(value, set) else value
        return json.dumps(serializable, ensure_ascii=False, default=str)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, bytes, int, float, bool)):
        return value
    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp) or value.__class__.__module__ == "datetime":
        return value
    return str(value)


def dataframe_dogrula(logical: str, frame: pd.DataFrame | None) -> tuple[pd.DataFrame | None, str | None]:
    if frame is None:
        return None, "DataFrame None"
    if not isinstance(frame, pd.DataFrame):
        return None, f"DataFrame beklenirken {type(frame).__name__} alındı"
    if len(frame.columns) == 0:
        return None, "DataFrame hiç sütun içermiyor"
    if frame.empty:
        return None, "Tarama sonucu boş; önceki geçerli tablo korunuyor"
    normalized = frame.copy(); normalized.columns = _unique_columns(normalized.columns)
    missing = REQUIRED_COLUMNS.get(logical, set()).difference(normalized.columns)
    if missing:
        return None, "Zorunlu sütunlar eksik: " + ", ".join(sorted(missing))
    for column in normalized.columns:
        dtype = str(normalized[column].dtype)
        if dtype == "object" or dtype.startswith("str"):
            normalized[column] = normalized[column].map(_sqlite_value)
    return normalized, None


def _existing_database_to_temp(path: Path, temp_path: Path) -> None:
    if not path.exists():
        return
    with closing(sqlite3.connect(path, timeout=30)) as source, closing(sqlite3.connect(temp_path, timeout=30)) as target:
        source.backup(target)


def anlik_goruntu_yaz(path: str | Path, frames: dict[str, pd.DataFrame | None], *, if_exists: str = "replace") -> SnapshotWriteResult:
    """Geçerli tabloları geçici DB'de yazıp canlı snapshot'ı atomik değiştirir."""
    result = SnapshotWriteResult(path=Path(path))
    if if_exists not in {"replace", "append"}:
        result.errors["snapshot"] = f"Desteklenmeyen if_exists: {if_exists}"; return result
    path = Path(path); temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp.sqlite3", dir=path.parent)
        os.close(handle); temp_path = Path(temp_name)
        _existing_database_to_temp(path, temp_path)
        with closing(sqlite3.connect(temp_path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=DELETE")
            for logical, frame in frames.items():
                table = TABLES.get(logical)
                if table is None:
                    result.skipped[logical] = "Tanımsız tablo adı"
                    logger.warning("SQLite tablosu atlandı: logical=%s reason=%s", logical, result.skipped[logical]); continue
                shape = None if frame is None else getattr(frame, "shape", None)
                columns = [] if frame is None else [str(c) for c in getattr(frame, "columns", [])]
                logger.debug("SQLite kaydı hazırlanıyor: table=%s, shape=%s, columns=%s", table, shape, columns)
                safe_frame, reason = dataframe_dogrula(logical, frame)
                if reason:
                    result.skipped[logical] = reason
                    logger.warning("SQLite tablosu atlandı: table=%s shape=%s reason=%s", table, shape, reason); continue
                try:
                    safe_frame.to_sql(table, db, if_exists=if_exists, index=False)
                    result.written.append(logical)
                except (sqlite3.Error, ValueError, TypeError) as exc:
                    result.errors[logical] = str(exc)
                    logger.exception("SQLite tablo kaydı başarısız: table=%s shape=%s", table, safe_frame.shape)
            if "Tum Sonuclar" in frames and "Tum Sonuclar" not in result.written:
                result.errors.setdefault("Tum Sonuclar", result.skipped.get("Tum Sonuclar", "Ana sonuç tablosu yazılamadı")); return result
            if not result.written:
                result.errors.setdefault("snapshot", "Yazılabilir geçerli tablo bulunamadı"); return result
            db.execute("CREATE TABLE IF NOT EXISTS snapshot_meta(schema_version INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            db.execute("DELETE FROM snapshot_meta"); db.execute("INSERT INTO snapshot_meta(schema_version) VALUES(2)"); db.commit()
        os.replace(temp_path, path); temp_path = None
        result.success = "Tum Sonuclar" in result.written if "Tum Sonuclar" in frames else bool(result.written)
        return result
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        result.errors["snapshot"] = str(exc)
        logger.exception("SQLite anlık görüntü kaydı başarısız: path=%s", path); return result
    finally:
        if temp_path is not None:
            try: temp_path.unlink(missing_ok=True)
            except OSError: logger.exception("Geçici SQLite dosyası temizlenemedi: %s", temp_path)


def anlik_goruntu_oku(path: str | Path) -> dict[str, pd.DataFrame]:
    if not Path(path).exists(): return {}
    result = {}
    with closing(sqlite3.connect(path)) as db:
        existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for logical, table in TABLES.items():
            if table in existing:
                try: result[logical] = pd.read_sql_query(f'SELECT * FROM "{table}"', db)
                except (sqlite3.Error, pd.errors.DatabaseError):
                    logger.exception("SQLite tablosu okunamadı: %s", table); result[logical] = pd.DataFrame()
    return result
