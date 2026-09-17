"""Point-in-time intraday signal outcomes; future bars are labels only."""
from __future__ import annotations

from typing import Any, Mapping
from pathlib import Path
import json
import sqlite3

import pandas as pd


def evaluate_intraday_signal(signal: Mapping[str, Any], future_bars: pd.DataFrame) -> dict[str, Any]:
    """Evaluate completed bars beginning after the recorded signal price.

    Bar indices are start times. A bar is usable once its end time has passed.
    The signal itself must be a completed-bar close; its bar is excluded.
    """
    try:
        timestamp = pd.Timestamp(signal["signal_timestamp"])
        price = float(signal["signal_price"])
        minutes = int(signal.get("bar_minutes", 15))
        if price <= 0 or minutes <= 0:
            raise ValueError("invalid signal price or interval")
    except (KeyError, TypeError, ValueError):
        return {"status": "SIGNAL_PRICE_MISSING"}
    if future_bars is None or future_bars.empty:
        return {"status": "FUTURE_BARS_MISSING"}
    bars = future_bars.sort_index().copy()
    idx = pd.DatetimeIndex(bars.index)
    if idx.tz is None or timestamp.tz is None:
        return {"status": "TIMEZONE_MISSING"}
    bars = bars.loc[(idx >= timestamp) & (idx.date == timestamp.date())]
    if bars.empty:
        return {"status": "FUTURE_BARS_MISSING"}
    if any(col not in bars for col in ("High", "Low", "Close")):
        return {"status": "FUTURE_BARS_INVALID"}
    outcome: dict[str, Any] = {"status": "PARTIAL", "signal_timestamp": timestamp.isoformat(),
                               "signal_price": price}
    for horizon in (30, 60, 120):
        cutoff = timestamp + pd.Timedelta(minutes=horizon)
        eligible = bars.loc[bars.index + pd.Timedelta(minutes=minutes) <= cutoff]
        # Require a completed bar reaching the horizon; missing intervals stay unknown.
        reaches = (not eligible.empty and
                   eligible.index[-1] + pd.Timedelta(minutes=minutes) >= cutoff)
        outcome[f"Return_{horizon}m"] = (float(eligible.Close.iloc[-1]/price-1)*100
                                           if reaches else None)
    close_available = (bars.index[-1].hour, bars.index[-1].minute) >= (18, 0)
    outcome["Return_Close"] = float(bars.Close.iloc[-1]/price-1)*100 if close_available else None
    outcome["MFE"] = float(bars.High.max()/price-1)*100
    outcome["MAE"] = float(bars.Low.min()/price-1)*100
    outcome["hit_3"] = int(outcome["MFE"] >= 3)
    outcome["hit_5"] = int(outcome["MFE"] >= 5)
    outcome["hit_7"] = int(outcome["MFE"] >= 7)
    outcome["status"] = "COMPLETE" if outcome["Return_Close"] is not None and all(
        outcome[f"Return_{h}m"] is not None for h in (30, 60, 120)) else "PARTIAL"
    return outcome


class RadarSignalStore:
    """Immutable signal facts and separately attached realised outcomes."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS radar_signals(
                    id INTEGER PRIMARY KEY, signal_timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL, signal_price REAL NOT NULL,
                    movement_score REAL NOT NULL, confidence REAL NOT NULL,
                    market_regime TEXT NOT NULL, rank INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(signal_timestamp,symbol));
                CREATE TABLE IF NOT EXISTS radar_outcomes(
                    signal_id INTEGER PRIMARY KEY REFERENCES radar_signals(id),
                    evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL);
            """)

    def save(self, signal: Mapping[str, Any]) -> bool:
        required = ("signal_timestamp", "symbol", "signal_price", "movement_score",
                    "confidence", "market_regime", "rank")
        if any(signal.get(field) is None for field in required):
            return False
        try:
            with sqlite3.connect(self.path) as db:
                cursor = db.execute("""INSERT OR IGNORE INTO radar_signals
                    (signal_timestamp,symbol,signal_price,movement_score,confidence,
                     market_regime,rank,payload_json) VALUES(?,?,?,?,?,?,?,?)""",
                    tuple(signal[key] for key in required) +
                    (json.dumps(dict(signal), ensure_ascii=False, default=str),))
                return cursor.rowcount == 1
        except (sqlite3.Error, TypeError, ValueError):
            return False

    def pending(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("""SELECT s.id,s.payload_json FROM radar_signals s
                LEFT JOIN radar_outcomes o ON o.signal_id=s.id
                WHERE o.signal_id IS NULL ORDER BY s.signal_timestamp,s.rank""").fetchall()
        return [{"id": row_id, **json.loads(payload)} for row_id, payload in rows]

    def attach_outcome(self, signal_id: int, outcome: Mapping[str, Any], evaluated_at: str) -> bool:
        if outcome.get("status") != "COMPLETE":
            return False
        with sqlite3.connect(self.path) as db:
            cursor = db.execute("INSERT OR IGNORE INTO radar_outcomes VALUES(?,?,?)",
                                (signal_id, evaluated_at, json.dumps(dict(outcome), ensure_ascii=False)))
            return cursor.rowcount == 1

    def performance_summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("""SELECT s.signal_timestamp,s.rank,o.payload_json
                FROM radar_signals s JOIN radar_outcomes o ON o.signal_id=s.id""").fetchall()
        if not rows:
            return {"status": "INSUFFICIENT_POST_SIGNAL_LABELS", "count": 0}
        records = []
        for timestamp, rank, payload in rows:
            outcome = json.loads(payload)
            records.append({"day": pd.Timestamp(timestamp).date(), "rank": rank,
                            "close": outcome["Return_Close"], "mfe": outcome["MFE"],
                            "mae": outcome["MAE"],
                            **{f"hit_{n}": outcome[f"hit_{n}"] for n in (3, 5, 7)}})
        frame = pd.DataFrame(records)
        result: dict[str, Any] = {"status": "OK", "count": len(frame),
                                  "days": int(frame.day.nunique())}
        for k in (3, 5, 10):
            top = frame[frame["rank"] <= k]
            result[f"Precision@{k}"] = float(top.hit_3.mean()) if len(top) else None
        for threshold in (3, 5, 7):
            result[f"Post-Signal +{threshold}% Hit"] = float(frame[f"hit_{threshold}"].mean())
        # FPR needs outcomes for the rejected universe (true negatives).
        result["False Positive Rate"] = None
        result["Average Post-Signal Return"] = float(frame.close.mean())
        result["Median Post-Signal Return"] = float(frame.close.median())
        result["Average MFE"] = float(frame.mfe.mean())
        result["Average MAE"] = float(frame.mae.mean())
        adverse = abs(result["Average MAE"])
        result["MFE/MAE ratio"] = result["Average MFE"]/adverse if adverse else None
        return result
