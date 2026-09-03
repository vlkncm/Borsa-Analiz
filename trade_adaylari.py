"""T+1 radar ve yarının trade listesi için saf, test edilebilir sıralama katmanı.

Bu modül mevcut analiz motorlarını değiştirmez. Onların ürettiği kanıtları kalite,
likidite ve yön kontrolleriyle birleştirir; listeler birbirinden bağımsızdır.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MODEL_VERSION = "v10.3.3-final-update-1"
RADAR_COLUMNS = ["Sıra", "Hisse", "Movement Score", "Güven", "Günlük %",
                 "Hacim Oranı", "Breakout Durumu", "T+1 Geniş 30 Sırası",
                 "Seçkin Aday", "Veri Kaynağı"]
TOMORROW_COLUMNS = ["Sıra", "Hisse", "Karar", "Güven", "Giriş", "Hedef",
                    "Potansiyel %", "Stop", "R/R", "Daily Score", "T+1 Score",
                    "Radar Sırası", "Çoklu Teyit", "Açılış Teyidi", "Veri Kaynağı"]


def _num(frame: pd.DataFrame, name: str, default=0.0) -> pd.Series:
    if name not in frame:
        if isinstance(default, pd.Series):
            return pd.to_numeric(default.reindex(frame.index), errors="coerce").fillna(0)
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").fillna(default)


def _text(frame: pd.DataFrame, name: str, default="") -> pd.Series:
    if name not in frame:
        return pd.Series(default, index=frame.index, dtype=object)
    return frame[name].fillna(default).astype(str)


def _normalise(series: pd.Series, low: float, high: float) -> pd.Series:
    return ((series-low)/(high-low)).clip(0, 1) * 100


def t1_listeleri(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Recall geniş 30, kalite ayarlı radar 10 ve precision Seçkin'i ayırır."""
    if frame is None or frame.empty:
        empty = pd.DataFrame()
        return {"wide": empty, "radar": pd.DataFrame(columns=RADAR_COLUMNS), "elite": empty}
    work = frame.copy()
    work["Movement Score"] = _num(work, "Movement Score", _num(work, "Referans Skor", 0))
    work["T+1 Geniş 30 Sırası"] = np.arange(1, len(work)+1)
    # Veri kalitesi ve likidite zayıf satırların ham hareket skoruyla üste çıkmasını önler.
    turnover = _num(work, "Ortalama İşlem Tutarı", _num(work, "Turnover", 0))
    if not turnover.any():
        turnover = _num(work, "turnover20", 0)
    liquidity = _normalise(np.log10(turnover.clip(lower=1)), 7.0, 9.0)
    data_ok = (~_text(work, "Durum").str.contains("VERİ ALINAMADI|YETERSİZ", case=False)).astype(float)*100
    rvol = _num(work, "Hacim Oranı", _num(work, "relative_volume", 1))
    vacc = _num(work, "Hacim İvmesi", _num(work, "volume_acceleration_2", 0))
    accel = _num(work, "Momentum İvmesi", _num(work, "price_acceleration_2", 0))
    daily = _num(work, "Günlük Değişim %", _num(work, "Günlük %", 0))
    close_strength = _num(work, "close_location", .5).clip(0, 1)*100
    resistance = _num(work, "resistance20_distance", .08)
    breakout = (100-(resistance.clip(0, .08)/.08*100)).clip(0, 100)
    relative_strength = _normalise(_num(work, "relative_strength_bist_5", 0), -.05, .08)
    # Hacim ancak fiyat/kapanış yönü pozitifse teyittir; dağıtım günleri ödüllendirilmez.
    directed_volume = _normalise(rvol, .7, 2.5) * ((daily > 0) & (close_strength >= 50)).astype(float)
    work["Radar Kalite Skoru"] = (
        work["Movement Score"]*.34 + _normalise(accel, -.02, .03)*.10 +
        directed_volume*.11 + _normalise(vacc, -.5, 1.5)*.07 + breakout*.09 +
        relative_strength*.08 + liquidity*.10 + data_ok*.07 + close_strength*.04
    ).round(2)
    weak = (liquidity < 25) | (data_ok < 100)
    work.loc[weak, "Radar Kalite Skoru"] -= 25
    wide = work.sort_values(["Movement Score", "Radar Kalite Skoru"], ascending=False).head(30).copy()
    wide["T+1 Geniş 30 Sırası"] = np.arange(1, len(wide)+1)
    radar = wide.sort_values(["Radar Kalite Skoru", "Movement Score"], ascending=False).head(10).copy()
    # Seçkin kendi precision kapılarına sahiptir; geniş/radar boolean'ını paylaşmaz.
    security = _text(wide, "Menkul Türü", "NORMAL_PAY")
    levels = wide.get("T+1 Seviye Doğrulandı", pd.Series(False, index=wide.index)).fillna(False).astype(bool)
    directional = (_num(wide, "plus_di", 1) > _num(wide, "minus_di", 0)) & (_num(wide, "Günlük Değişim %", 0) >= 0)
    elite_mask = ((wide["Movement Score"] >= 62) & (wide["Radar Kalite Skoru"] >= 60) &
                  (liquidity.reindex(wide.index) >= 35) & directional & levels & security.eq("NORMAL_PAY"))
    elite = wide[elite_mask].sort_values(["Radar Kalite Skoru", "Movement Score"], ascending=False).head(10).copy()
    elite_symbols = set(elite.get("Hisse", pd.Series(dtype=str)).astype(str))
    radar["Sıra"] = np.arange(1, len(radar)+1)
    radar["Güven"] = pd.cut(radar["Radar Kalite Skoru"], [-np.inf,55,70,np.inf], labels=["ORTA","YÜKSEK","ÇOK YÜKSEK"]).astype(str)
    radar["Günlük %"] = _num(radar, "Günlük Değişim %", 0).round(2)
    radar["Hacim Oranı"] = _num(radar, "Hacim Oranı", _num(radar, "relative_volume", 1)).round(2)
    radar["Breakout Durumu"] = np.where(_num(radar,"resistance20_distance",.08)<=.01,"KIRILIM/YAKIN",np.where(_num(radar,"resistance20_distance",.08)<=.04,"YAKLAŞIYOR","UZAK"))
    radar["Seçkin Aday"] = radar["Hisse"].astype(str).isin(elite_symbols).map({True:"EVET",False:"HAYIR"})
    radar["Veri Kaynağı"] = _text(radar, "Veri Kaynağı", "Yahoo")
    return {"wide": wide.reset_index(drop=True), "radar": radar[RADAR_COLUMNS].reset_index(drop=True), "elite": elite.reset_index(drop=True)}


def tomorrow_trade_top10(daily: pd.DataFrame, wide: pd.DataFrame, radar: pd.DataFrame,
                         elite: pd.DataFrame) -> pd.DataFrame:
    """Listeleri kopyalamadan ortak kanıtlardan en fazla 10 trade planı üretir."""
    parts = [x for x in (daily, wide) if x is not None and not x.empty and "Hisse" in x]
    if not parts: return pd.DataFrame(columns=TOMORROW_COLUMNS)
    base = pd.concat(parts, ignore_index=True).drop_duplicates("Hisse", keep="first").copy()
    daily_symbols = set(daily.get("Hisse", pd.Series(dtype=str)).astype(str)) if daily is not None else set()
    radar_map = {str(r["Hisse"]): int(r["Sıra"]) for _,r in radar.iterrows()} if radar is not None and not radar.empty else {}
    elite_symbols = set(elite.get("Hisse", pd.Series(dtype=str)).astype(str)) if elite is not None else set()
    base["Daily Score"] = _num(base,"Daily Score",_num(base,"Günlük Trade Skoru",_num(base,"v4 Güven Puanı",0)))
    base["T+1 Score"] = _num(base,"Movement Score",_num(base,"Referans Skor",0))
    base["Radar Sırası"] = base["Hisse"].astype(str).map(radar_map)
    membership = base["Hisse"].astype(str).map(lambda s: int(s in daily_symbols)+int(s in radar_map)+int(s in elite_symbols))
    base["Çoklu Teyit"] = membership.map(lambda n: "3/3 ÇOKLU TEYİT" if n==3 else "2/3 ÇOKLU TEYİT" if n==2 else "YOK")
    rvol = _num(base,"Hacim Oranı",_num(base,"relative_volume",1))
    rr = _num(base,"R/R",_num(base,"T+1 Risk/Getiri",_num(base,"Karar Risk/Getiri",0)))
    quality = _num(base,"Radar Kalite Skoru",50)
    stale = _text(base,"Veri Durumu").str.contains("ESKİ|STALE|YETERSİZ",case=False)
    base["_score"] = base["Daily Score"]*.28+base["T+1 Score"]*.28+quality*.20+_normalise(rvol,.7,2.5)*.08+_normalise(rr,.8,3)*.08+membership*4
    base.loc[(rr<1.2)|stale,"_score"] -= 25
    base = base.sort_values(["_score","T+1 Score"],ascending=False).head(10).copy()
    base["Sıra"] = np.arange(1,len(base)+1)
    base["Karar"] = pd.cut(base["_score"],[-np.inf,45,58,72,np.inf],labels=["İZLE","TEYİT BEKLE","ADAY","GÜÇLÜ ADAY"]).astype(str)
    base["Güven"] = base["_score"].round(1)
    base["Giriş"] = _num(base,"T+1 Giriş",_num(base,"Önerilen Alış Üst",_num(base,"Fiyat",0))).round(2)
    base["Hedef"] = _num(base,"T+1 Hedef",_num(base,"Önerilen Satış",0)).round(2)
    base["Stop"] = _num(base,"T+1 Stop",_num(base,"Önerilen Stop",0)).round(2)
    base["R/R"] = rr.reindex(base.index).round(2)
    base["Potansiyel %"] = ((base["Hedef"]/base["Giriş"].replace(0,np.nan)-1)*100).round(2)
    base["Açılış Teyidi"] = "BEKLENİYOR"
    base["Veri Kaynağı"] = _text(base,"Veri Kaynağı","Yahoo")
    return base[TOMORROW_COLUMNS].reset_index(drop=True)


def opening_confirmation(previous_close: float, previous_high: float, bars: pd.DataFrame,
                         vwap: float | None = None) -> str:
    """Tamamlanmış ilk 5/15 dk barları yoksa kör AL üretmez."""
    if bars is None or bars.empty or len(bars) < 1: return "BEKLENİYOR"
    first, last = bars.iloc[0], bars.iloc[-1]
    gap = float(first.Open)/previous_close-1 if previous_close else 0
    direction = float(last.Close) > float(first.Open)
    breakout = float(last.Close) >= previous_high
    above_vwap = vwap is None or not math.isfinite(vwap) or float(last.Close) >= vwap
    if gap > .06 and float(last.Close) < float(first.Open)*.98: return "OLUMSUZ"
    return "OLUMLU" if direction and breakout and above_vwap else "OLUMSUZ"


class TomorrowTradeStore:
    """Append-only/deduplicate yarın trade snapshot ve gerçekleşme deposu."""
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self._create()
    def _db(self): return sqlite3.connect(self.path)
    def _create(self):
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tomorrow_trade_snapshots(
              session_date TEXT NOT NULL,symbol TEXT NOT NULL,rank INTEGER,daily_score REAL,t1_score REAL,
              radar_rank INTEGER,elite INTEGER,multi_confirm TEXT,entry REAL,target REAL,stop REAL,
              model_version TEXT NOT NULL,created_at TEXT NOT NULL,payload_json TEXT,
              PRIMARY KEY(session_date,symbol,model_version))""")
            db.execute("""CREATE TABLE IF NOT EXISTS tomorrow_trade_outcomes(
              session_date TEXT NOT NULL,symbol TEXT NOT NULL,open_pct REAL,high_pct REAL,low_pct REAL,close_pct REAL,
              target_hit INTEGER,stop_hit INTEGER,mfe REAL,mae REAL,settled_at TEXT NOT NULL,
              PRIMARY KEY(session_date,symbol))""")
    def save(self, frame: pd.DataFrame, session_date: str | date | None=None):
        day=str(session_date or date.today())
        with self._db() as db:
            for _,r in frame.iterrows():
                symbol=str(r.get("Hisse","")); multi=str(r.get("Çoklu Teyit","YOK"))
                db.execute("INSERT OR IGNORE INTO tomorrow_trade_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (day,symbol,int(r.get("Sıra",0)),float(r.get("Daily Score",0)),float(r.get("T+1 Score",0)),
                   None if pd.isna(r.get("Radar Sırası")) else int(r.get("Radar Sırası")),int("3/3" in multi),multi,
                   float(r.get("Giriş",0)),float(r.get("Hedef",0)),float(r.get("Stop",0)),MODEL_VERSION,
                   datetime.now().isoformat(timespec="seconds"),json.dumps(r.to_dict(),ensure_ascii=False,default=str)))
    def settle(self, session_date: str, symbol: str, ohlc: dict[str,float]):
        with self._db() as db:
            snap=db.execute("SELECT entry,target,stop FROM tomorrow_trade_snapshots WHERE session_date=? AND symbol=? ORDER BY created_at LIMIT 1",(session_date,symbol)).fetchone()
            if not snap: return False
            entry,target,stop=snap; entry=entry or ohlc["Open"]
            values=[(ohlc[k]/entry-1)*100 for k in ("Open","High","Low","Close")]
            db.execute("INSERT OR IGNORE INTO tomorrow_trade_outcomes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (session_date,symbol,*values,int(ohlc["High"]>=target),int(ohlc["Low"]<=stop),values[1],values[2],datetime.now().isoformat(timespec="seconds")))
            return True
    def metrics(self):
        with self._db() as db:
            rows=db.execute("""SELECT s.rank,o.close_pct,o.mfe,o.mae,o.target_hit,o.stop_hit
              FROM tomorrow_trade_snapshots s JOIN tomorrow_trade_outcomes o USING(session_date,symbol)""").fetchall()
        if not rows: return {"count":0}
        f=pd.DataFrame(rows,columns=["rank","close","mfe","mae","target","stop"])
        def hit(n):
            x=f[f["rank"]<=n]; return float((x["close"]>0).mean()) if len(x) else None
        wins=f.loc[f.close>0,"close"].sum(); losses=-f.loc[f.close<0,"close"].sum()
        return {"count":len(f),"HitRate@5":hit(5),"HitRate@10":hit(10),"Precision@5":hit(5),
                "Average MFE":float(f.mfe.mean()),"Average MAE":float(f.mae.mean()),
                "Average Close Return":float(f.close.mean()),"Target Hit Rate":float(f.target.mean()),
                "Stop Hit Rate":float(f.stop.mean()),"Profit Factor":float(wins/losses) if losses else None,
                "EV":float(f.close.mean())}
