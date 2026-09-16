"""Offline paired replay. Input cache is read-only; outcomes never enter scoring.

Run with --cache PATH --snapshots PATH --git PATH. Baseline comes exclusively
from the verified GitHub commit, not an installed application's source files.
"""
import argparse
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
import pandas as pd

from ertesi_gun_motoru import erken_aday
from trade_adaylari import t1_listeleri

BASE_COMMIT = "7abcfaa924e762436cfa3d76023d28316d9565de"


def load_baseline(git, name, output):
    path = output / (name + ".py")
    path.write_bytes(subprocess.check_output([git, "show", f"{BASE_COMMIT}:{name}.py"]))
    alias = "baseline_" + name
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec); sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def read_frame(payload):
    content = json.loads(payload)
    frame = pd.DataFrame(content["data"]).set_index("index")
    frame.index = pd.to_datetime(frame.index, utc=True).tz_localize(None).normalize()
    return frame.sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


def metrics(order, labels, recall_order):
    symbols = list(order)
    y = labels.loc[symbols]
    positive_count = int(labels.hit7.sum()); negatives = int((labels.hit7 == 0).sum())
    top = y.head(10)
    return {**{f"Precision@{k}": float(y.head(k).hit7.mean()) for k in (3,5,10)},
            "Recall@20": float(labels.loc[list(recall_order)[:20]].hit7.sum()/positive_count) if positive_count else None,
            "%7+ Hit Rate": float(top.hit7.mean()),
            "False Positive Rate": float((top.hit7 == 0).sum()/negatives) if negatives else None,
            "Average Forward Return": float(top.forward_return.mean()),
            "Median Forward Return": float(top.forward_return.median())}


def run(args):
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    old_engine = load_baseline(args.git, "ertesi_gun_motoru", output)
    old_radar = load_baseline(args.git, "trade_adaylari", output)
    old_features = load_baseline(args.git, "t1t2_tahmin_sistemi", output)
    with sqlite3.connect(Path(args.cache).resolve().as_uri()+"?mode=ro", uri=True) as db:
        cache = db.execute("SELECT sembol,alis_zamani,son_veri_tarihi,veri_json FROM fiyat_cache WHERE periyot='2y' AND aralik='1d' ORDER BY alis_zamani").fetchall()
    by_symbol = {}
    for symbol, fetched, last, payload in cache:
        by_symbol.setdefault(symbol, []).append((pd.Timestamp(fetched, unit="s"), last, payload))
    with sqlite3.connect(Path(args.snapshots).resolve().as_uri()+"?mode=ro", uri=True) as db:
        snapshots = db.execute("SELECT symbol,as_of,created_at,payload_json FROM t1t2_snapshots WHERE horizon='T+1' ORDER BY as_of,created_at").fetchall()
    pairs = {}; exclusions = {}; latest = {}; used = set()
    for symbol, asof, created, payload in snapshots:
        day = pd.Timestamp(asof).tz_localize(None).normalize()
        # Existing artifact's last test date is 2026-08-25. Only later sessions.
        if day <= pd.Timestamp("2026-08-25"): continue
        timestamp = pd.Timestamp(created)
        key = (str(day.date()), symbol)
        if key in used: continue
        # SQLite created_at is UTC. Exclude unfinished daily bars and delayed scans.
        if timestamp < day + pd.Timedelta(hours=15, minutes=15) or timestamp >= day + pd.Timedelta(days=1):
            exclusions["not_same_day_completed_session"] = exclusions.get("not_same_day_completed_session", 0)+1
            continue
        original = json.loads(payload)
        if original.get("security_type") != "NORMAL_PAY": continue
        versions = [x for x in by_symbol.get(symbol, []) if x[0] <= timestamp and str(x[1])[:10] == str(day.date())]
        if not versions:
            exclusions["no_contemporaneous_cache"] = exclusions.get("no_contemporaneous_cache", 0)+1
            continue
        frame = read_frame(versions[-1][2]).loc[:day]
        if len(frame) < 60: continue
        if symbol not in latest: latest[symbol] = read_frame(by_symbol[symbol][-1][2])
        future = latest[symbol].loc[lambda x: x.index > day].head(2)
        if len(future) < 2:
            exclusions["unresolved_forward_window"] = exclusions.get("unresolved_forward_window", 0)+1
            continue
        # Feature data remains the immutable contemporaneous cache; later data is label-only.
        benchmark_versions = [x for x in by_symbol.get("XU100.IS", []) if x[0] <= timestamp and str(x[1])[:10] == str(day.date())]
        benchmark = read_frame(benchmark_versions[-1][2]).loc[:day] if benchmark_versions else None
        old = old_engine.erken_aday(symbol, frame, "VERİ YETERSİZ")
        f = old_features.point_in_time_features(frame, day)
        old.update({k:f.get(k) for k in ("price_acceleration_2", "volume_acceleration_2", "relative_volume",
                                       "resistance20_distance", "relative_strength_bist_5", "close_location", "turnover20")})
        new = erken_aday(symbol, frame, "VERİ YETERSİZ", as_of=day, benchmark=benchmark)
        close = float(frame.iloc[-1].Close)
        labels = {h: {"hit7": int(float(future.iloc[:h].High.max())/close-1 >= .07),
                      "forward_return": (float(future.iloc[h-1].Close)/close-1)*100}
                  for h in (1,2)}
        pairs.setdefault(str(day.date()), []).append((symbol.replace(".IS", ""), old, new, labels))
        used.add(key)
    reports = []; records = []
    for day, pairs_day in pairs.items():
        if len(pairs_day) < 30: continue
        old_frame = pd.DataFrame([p[1] for p in pairs_day]); new_frame = pd.DataFrame([p[2] for p in pairs_day])
        old_groups = old_radar.t1_listeleri(old_frame); new_groups = t1_listeleri(new_frame)
        # Match full radar order (top 10) and wide candidates (up to 30) for Recall@20.
        def ordered(groups):
            radar = list(groups["radar"].Hisse)
            return radar + [s for s in groups["wide"].Hisse if s not in radar]
        for h in (1,2):
            labels = pd.DataFrame([dict(symbol=p[0], **p[3][h]) for p in pairs_day]).set_index("symbol")
            reports.append({"day": day, "horizon": f"T+{h}", "universe": len(labels),
                            "positives": int(labels.hit7.sum()),
                            "old": metrics(ordered(old_groups), labels, old_groups["wide"].Hisse),
                            "new": metrics(ordered(new_groups), labels, new_groups["wide"].Hisse),
                            "selected": {side: labels.loc[list(groups["radar"].Hisse)].reset_index().to_dict("records")
                                         for side,groups in (("old",old_groups),("new",new_groups))},
                            "old_saturated_top10": int((old_groups["radar"]["Movement Score"] >= 99.95).sum()),
                            "new_saturated_top10": int((new_groups["radar"]["Movement Score"] >= 99.95).sum())})
        records.extend({"day": day, "symbol": p[0], "old_score": p[1]["Movement Score"],
                        "new_score": p[2]["Movement Score"], "labels": p[3]} for p in pairs_day)
    aggregate = {}
    for horizon in ("T+1", "T+2"):
        subset = [r for r in reports if r["horizon"] == horizon]
        if not subset: continue
        aggregate[horizon] = {side: {k: float(np.mean([r[side][k] for r in subset if r[side][k] is not None]))
                                    if any(r[side][k] is not None for r in subset) else None
                                    for k in subset[0][side]} for side in ("old", "new")}
        for side in ("old", "new"):
            returns = [row["forward_return"] for r in subset for row in r["selected"][side]]
            aggregate[horizon][side]["Median Forward Return"] = float(np.median(returns))
    result = {"base_commit": BASE_COMMIT, "method": "paired frozen cache replay; daily macro rates; pooled mean/median returns in percent; positive label=max forward high >=7%; selection=radar top10; Recall@20=wide top20; FPR=FP/all negatives",
              "limitations": ["Small local replay, not independent prospective validation", "Cached historical data vendor revisions cannot be ruled out before capture", "Only reconstructable snapshot intersection; not the entire BIST universe", "No 2026-09-15 completed outcome window available"],
              "aggregate": aggregate, "sessions": reports, "exclusions": exclusions}
    (output/"comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output/"paired_scores.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True); parser.add_argument("--snapshots", required=True)
    parser.add_argument("--git", required=True); parser.add_argument("--output", default=".validation/replay")
    run(parser.parse_args())
