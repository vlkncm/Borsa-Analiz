"""Degistirilemez merkezi karar anlik goruntuleri ve ayri gerceklesmeler."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping


class KararDeposu:
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
            CREATE TABLE IF NOT EXISTS decision_snapshots(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              decision_key TEXT NOT NULL UNIQUE,
              symbol TEXT NOT NULL, decision TEXT NOT NULL,
              previous_decision TEXT, changed_at TEXT, change_reason TEXT,
              model_version TEXT NOT NULL, cutoff_at TEXT NOT NULL,
              payload_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS decision_outcomes(
              decision_id INTEGER PRIMARY KEY REFERENCES decision_snapshots(id),
              evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decision_snapshots
              BEGIN SELECT RAISE(ABORT, 'Karar kayitlari degistirilemez'); END;
            CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decision_snapshots
              BEGIN SELECT RAISE(ABORT, 'Karar kayitlari silinemez'); END;
            """)
            db.commit()

    def karar_ekle(self, decision_key: str, result: Mapping[str, Any],
                   previous_decision: str | None = None,
                   change_reason: str | None = None) -> tuple[bool, int | str]:
        """SQLite hatasini taramaya yaymadan (basarili, id/hata) dondurur."""
        try:
            payload = dict(result)
            with closing(self._connect()) as db:
                cur = db.execute("""INSERT INTO decision_snapshots(
                    decision_key,symbol,decision,previous_decision,changed_at,change_reason,
                    model_version,cutoff_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?)""", (
                    decision_key, payload.get("sembol", ""), payload.get("karar", "KARAR YOK"),
                    previous_decision, payload.get("kayit_zamani"), change_reason,
                    payload.get("model_surumu", "unknown"), payload.get("veri_zamani") or "unknown",
                    json.dumps(payload, ensure_ascii=False, default=str),
                ))
                db.commit()
                return True, int(cur.lastrowid)
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            return False, str(exc)

    def gerceklesme_ekle(self, decision_id: int, evaluated_at: str,
                         outcome: Mapping[str, Any]) -> tuple[bool, str | None]:
        try:
            with closing(self._connect()) as db:
                db.execute("INSERT INTO decision_outcomes VALUES(?,?,?)", (
                    decision_id, evaluated_at, json.dumps(dict(outcome), ensure_ascii=False, default=str)))
                db.commit()
            return True, None
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            return False, str(exc)

    def son_karar(self, symbol: str) -> dict[str, Any] | None:
        try:
            with closing(self._connect()) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("""SELECT decision, created_at, payload_json
                    FROM decision_snapshots WHERE symbol=? ORDER BY id DESC LIMIT 1""", (symbol,)).fetchone()
            return dict(row) if row else None
        except sqlite3.Error:
            return None
