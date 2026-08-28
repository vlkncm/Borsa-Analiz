"""Yerel fiyat cache'inden T+1/T+2 referans artefakti uretme komutu."""
from __future__ import annotations

import argparse
import io
import os
import sqlite3
from pathlib import Path

import pandas as pd

from t1t2_tahmin_sistemi import (HORIZONS, TARGETS_BY_HORIZON, build_point_in_time_dataset,
                                  save_artifacts, train_reference_artifact)

FEATURES=("ret_1","ret_2","ret_3","ret_5","ret_10","ret_20","price_acceleration_2",
          "volume_acceleration_2","open_close_return","close_location","higher_high_2",
          "higher_low_2","resistance20_distance","compression20","atr_pct","atr_change_5",
          "realized_vol20","relative_volume","volume_persistence","obv_slope_5","cmf20",
          "mfi14","estimated_slippage","move_realized_5_atr")

def cached_frames(db_path: Path) -> dict[str,pd.DataFrame]:
    db=sqlite3.connect(db_path)
    try:
        rows=db.execute("""SELECT sembol,veri_json FROM fiyat_cache WHERE aralik='1d' AND periyot IN ('2y','5y')
                           ORDER BY CASE periyot WHEN '5y' THEN 2 ELSE 1 END DESC, alis_zamani DESC""").fetchall()
    finally: db.close()
    result={}
    for symbol,payload in rows:
        if symbol in result: continue
        try:
            frame=pd.read_json(io.StringIO(payload),orient="table").sort_index()
            if len(frame)>=100: result[symbol]=frame
        except Exception: continue
    return result

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default="models/t1t2_reference.json")
    parser.add_argument("--stride",type=int,default=5); args=parser.parse_args()
    db=Path(os.getenv("LOCALAPPDATA",str(Path.home()/"AppData"/"Local")))/"BorsaAnalizProMAX"/"piyasa_verisi.sqlite3"
    frames=cached_frames(db)
    from bist_evreni import kap_menkul_turleri
    security_types=kap_menkul_turleri(); frames={symbol:frame for symbol,frame in frames.items() if security_types.get(symbol)=="NORMAL_PAY"}
    dataset=build_point_in_time_dataset(frames)
    dataset=dataset.sort_values(["as_of","symbol"]).iloc[::max(1,args.stride)].reset_index(drop=True)
    metrics={"symbols":len(frames),"rows":len(dataset),
             "start":str(pd.to_datetime(dataset.as_of).min().date()) if not dataset.empty else None,
             "end":str(pd.to_datetime(dataset.as_of).max().date()) if not dataset.empty else None}
    artifacts={}
    for horizon in HORIZONS:
        for target in TARGETS_BY_HORIZON[horizon]:
            key=f"{horizon}:{target}"; artifact,report=train_reference_artifact(dataset,horizon,target,FEATURES)
            metrics[key]=report
            if artifact and artifact.reliable: artifacts[key]=artifact
            print(key,report)
    save_artifacts(args.output,artifacts,metrics)
    print({"output":args.output,"symbols":len(frames),"rows":len(dataset),"active_artifacts":len(artifacts)})

if __name__=="__main__": main()
