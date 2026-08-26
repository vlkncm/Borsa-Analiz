"""Değiştirilemez tahminler ve ayrı gerçekleşmeler için sürümlü SQLite depo."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class TahminDeposu:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _migrate(self):
        with closing(self._connect()) as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS predictions(
              id INTEGER PRIMARY KEY AUTOINCREMENT, prediction_key TEXT NOT NULL UNIQUE,
              predicted_at TEXT NOT NULL, session_date TEXT NOT NULL, symbol TEXT NOT NULL,
              previous_close REAL NOT NULL, ceiling_price REAL NOT NULL,
              p_intraday_8 REAL, p_ceiling REAL, p_close_8 REAL,
              market_regime TEXT NOT NULL, sector_score REAL, status TEXT NOT NULL,
              reasons_json TEXT NOT NULL, risks_json TEXT NOT NULL, cutoff_at TEXT NOT NULL,
              model_version TEXT NOT NULL, probability_reliable INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS outcomes(
              prediction_id INTEGER PRIMARY KEY REFERENCES predictions(id), evaluated_at TEXT NOT NULL,
              intraday_8 INTEGER NOT NULL, hit_ceiling INTEGER NOT NULL,
              intraday_max_return REAL NOT NULL, close_return REAL NOT NULL,
              max_adverse_excursion REAL NOT NULL, target_before_stop INTEGER,
              successful INTEGER NOT NULL, duration_correct INTEGER);
            CREATE TRIGGER IF NOT EXISTS predictions_no_update
              BEFORE UPDATE ON predictions BEGIN SELECT RAISE(ABORT, 'Tahmin kayıtları değiştirilemez'); END;
            CREATE TRIGGER IF NOT EXISTS predictions_no_delete
              BEFORE DELETE ON predictions BEGIN SELECT RAISE(ABORT, 'Tahmin kayıtları silinemez'); END;
            """)
            row = db.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                db.execute("INSERT INTO schema_meta(version) VALUES(?)", (SCHEMA_VERSION,))
            db.commit()

    def tahmin_ekle(self, record: dict[str, Any]) -> int:
        columns = ("prediction_key predicted_at session_date symbol previous_close ceiling_price "
                   "p_intraday_8 p_ceiling p_close_8 market_regime sector_score status "
                   "reasons_json risks_json cutoff_at model_version probability_reliable").split()
        values = []
        for name in columns:
            value = record.get(name)
            if name in {"reasons_json", "risks_json"} and not isinstance(value, str):
                value = json.dumps(value or [], ensure_ascii=False)
            values.append(value)
        placeholders = ",".join("?" for _ in columns)
        with closing(self._connect()) as db:
            cur = db.execute(f"INSERT INTO predictions({','.join(columns)}) VALUES({placeholders})", values)
            db.commit()
            return int(cur.lastrowid)

    def gerceklesme_ekle(self, prediction_id: int, outcome: dict[str, Any]) -> None:
        columns = ("prediction_id evaluated_at intraday_8 hit_ceiling intraday_max_return close_return "
                   "max_adverse_excursion target_before_stop successful duration_correct").split()
        values = [prediction_id] + [outcome.get(c) for c in columns[1:]]
        with closing(self._connect()) as db:
            db.execute(f"INSERT INTO outcomes({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", values)
            db.commit()

    def performans(self) -> dict[str, Any]:
        with closing(self._connect()) as db:
            row = db.execute("""SELECT COUNT(*), COALESCE(SUM(successful),0),
                COALESCE(SUM(intraday_8),0), COALESCE(SUM(hit_ceiling),0),
                AVG(intraday_max_return), AVG(close_return)
                FROM outcomes""").fetchone()
        total, success, hit8, ceiling, avg_high, avg_close = row
        return {"toplam": total, "basarili": success, "basarisiz": total-success,
                "yuzde8_goren": hit8, "tavan_goren": ceiling,
                "ortalama_en_yuksek_getiri": avg_high, "ortalama_kapanis_getirisi": avg_close}

    def bekleyenler(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT p.* FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id
                               WHERE o.prediction_id IS NULL ORDER BY p.session_date, p.id""").fetchall()
        return [dict(r) for r in rows]
