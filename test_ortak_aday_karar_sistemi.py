import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from aday_karar_sistemi import build_candidate_decisions, duplicate_feature_hashes, net_ev_audit
from t1t2_tahmin_sistemi import (CacheIdentity, EveningSnapshotStore, feature_hash,
                                  point_in_time_features, predict_symbol, snapshot_is_timely)
from veri_saglayici import completed_daily_frame


def series(seed: int, flat_last: bool = False) -> pd.DataFrame:
    rng=np.random.default_rng(seed); n=90
    close=20+seed+np.cumsum(rng.normal(.03*seed,.2+seed*.02,n))
    high=close+rng.uniform(.1,.5,n); low=close-rng.uniform(.1,.5,n)
    if flat_last: high[-1]=low[-1]=close[-1]
    return pd.DataFrame({"Open":close-rng.normal(0,.1,n),"High":high,"Low":low,
                         "Close":close,"Volume":rng.integers(100_000,2_000_000,n)*(seed+1)},
                        index=pd.date_range("2026-04-01",periods=n,freq="B"))


def ranked(symbol="AAA.IS", security="NORMAL_PAY", rank=1, ev=-1.0, risks=(), status="KALIBRE TAHMIN"):
    return {"symbol":symbol,"horizon":"T+1","rank":rank,"percentile":99.0,
            "probabilities":{"max_7":35.0,"max_8":25.0,"limit_up":8.0},
            "ranking_score":27.0,"raw_score":1.2,"status":status,"reasons":("Sembole ozel neden",),
            "risks":tuple(risks),"missing_features":(),"levels_valid":True,"net_ev_pct":ev,
            "security_type":security,"model_version":"m1","feature_hash":symbol+"-hash",
            "as_of_timestamp":"2026-08-27T00:00:00","cache_key":symbol+"-key","data_version":"d1",
            "entry_high":10.1,"target_7":10.7,"stop":9.7,"risk_reward":1.5,"current_price":10.0}


class OrtakKararTests(unittest.TestCase):
    def test_five_different_ohlcv_series_have_different_hashes(self):
        hashes=[]
        for seed in range(1,6):
            frame=series(seed); hashes.append(feature_hash(point_in_time_features(frame,frame.index[-1])))
        self.assertEqual(5,len(set(hashes)))

    def test_symbol_reasons_and_risks_are_not_shared_state(self):
        rows=[]
        for seed in range(1,6):
            frame=series(seed); rows.append(predict_symbol(f"S{seed}.IS",frame,frame.index[-1],"T+1",{}))
        self.assertEqual(5,len({item.feature_hash for item in rows}))
        self.assertEqual(5,len({id(item.reasons) for item in rows}))
        self.assertGreater(len({(item.reasons,item.risks) for item in rows}),1)

    def test_bist100_relative_strength_is_in_feature_vector(self):
        frame=series(2); benchmark=series(5)
        values=point_in_time_features(frame,frame.index[-1],benchmark=benchmark)
        self.assertIn("relative_strength_bist_5",values)

    def test_flat_limit_bar_does_not_remove_cmf_and_mfi(self):
        frame=series(3,flat_last=True); values=point_in_time_features(frame,frame.index[-1])
        self.assertIn("cmf20",values); self.assertIn("mfi14",values)

    def test_cache_keys_are_split_by_symbol_and_horizon(self):
        base=("2026-08-27T00:00:00","T1T2_AKSAM","m1")
        keys={CacheIdentity(s,base[0],h,base[1],base[2]).key for s in ("A.IS","B.IS") for h in ("T+1","T+2")}
        self.assertEqual(4,len(keys))

    def test_security_unknown_stays_wide_but_is_never_buy(self):
        item=build_candidate_decisions([ranked(security="BELIRSIZ",ev=1)],market_regime="POZİTİF",
            contexts={"AAA.IS":{"data_freshness":"GUNCEL","kap_status":None}})[0]
        self.assertTrue(item.eligible_wide); self.assertFalse(item.eligible_elite)
        self.assertNotIn("AL ADAYI",item.final_decision); self.assertIn("SECURITY_TYPE_UNVERIFIED",item.gate_codes)

    def test_missing_kap_is_neutral_but_verified_negative_is_risk(self):
        neutral=build_candidate_decisions([ranked(ev=1)],market_regime="POZİTİF",
            contexts={"AAA.IS":{"data_freshness":"GUNCEL","kap_status":None}})[0]
        negative=build_candidate_decisions([ranked(ev=1)],market_regime="POZİTİF",
            contexts={"AAA.IS":{"data_freshness":"GUNCEL","kap_status":"NEGATIF"}})[0]
        self.assertTrue(neutral.eligible_elite); self.assertNotIn("NEGATIVE_KAP",neutral.gate_codes)
        self.assertFalse(negative.eligible_elite); self.assertIn("NEGATIVE_KAP",negative.gate_codes)

    def test_negative_ev_is_visible_watch_not_silent_rejection(self):
        item=build_candidate_decisions([ranked(ev=-2)],market_regime="POZİTİF",
            contexts={"AAA.IS":{"data_freshness":"GUNCEL"}})[0]
        self.assertTrue(item.eligible_elite); self.assertEqual("İZLE – RİSK/GETİRİ TEYİDİ",item.final_decision)
        self.assertEqual(1,net_ev_audit([item])["rejected_only_by_ev"])

    def test_every_non_included_result_has_a_gate(self):
        row=ranked(rank=70); row["percentile"]=40
        item=build_candidate_decisions([row],market_regime="POZİTİF",
            contexts={"AAA.IS":{"data_freshness":"GUNCEL"}})[0]
        self.assertTrue(item.gate_codes); self.assertEqual("OUTSIDE_TOP_PERCENTILE",item.rejected_by)

    def test_ipo_stays_in_separate_radar_without_probability(self):
        row=ranked(status="YENI HALKA ARZ IZLEME - KALIBRE EDILMEMIS")
        row["probabilities"]={"max_7":None,"max_8":None,"limit_up":None}; row["security_type"]="BELIRSIZ"
        item=build_candidate_decisions([row],market_regime="POZİTİF",
            contexts={"AAA.IS":{"data_freshness":"GUNCEL"}})[0]
        self.assertTrue(item.eligible_wide); self.assertIn("INCLUDED_IPO_RADAR",item.gate_codes)
        self.assertFalse(item.probability_reliable)

    def test_future_bar_cannot_change_t_features(self):
        frame=series(2); cutoff=frame.index[-2]
        before=point_in_time_features(frame,cutoff)
        changed=frame.copy(); changed.iloc[-1]=[999,999,1,900,999999999]
        self.assertEqual(feature_hash(before),feature_hash(point_in_time_features(changed,cutoff)))

    def test_incomplete_today_bar_is_removed(self):
        frame=pd.DataFrame({"Close":[10,11]},index=pd.to_datetime(["2026-08-27","2026-08-28"]))
        now=datetime(2026,8,28,11,0,tzinfo=ZoneInfo("Europe/Istanbul"))
        self.assertEqual(pd.Timestamp("2026-08-27"),completed_daily_frame(frame,now).index[-1])

    def test_intraday_reconstruction_cannot_be_saved_as_prior_prediction(self):
        self.assertFalse(snapshot_is_timely("2026-08-27T00:00:00+03:00","2026-08-28T07:50:12Z"))
        self.assertTrue(snapshot_is_timely("2026-08-27T00:00:00+03:00","2026-08-27T18:30:00+03:00"))

    def test_snapshot_is_immutable_and_outcome_is_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=EveningSnapshotStore(Path(tmp)/"x.sqlite3"); row=ranked(); row["as_of_timestamp"]="2026-08-27"
            ok,sid=store.save(row); self.assertTrue(ok)
            again,_=store.save({**row,"rank":99}); self.assertFalse(again)
            self.assertTrue(store.attach_outcome(sid,{"hit_7":1},"2026-08-28T18:20:00")[0])
            self.assertEqual(1,store.audit("2026-08-27")[0]["rank"])

    def test_duplicate_hash_warning_identifies_symbols(self):
        rows=[ranked("A.IS"),ranked("B.IS")]; rows[1]["feature_hash"]=rows[0]["feature_hash"]
        decisions=build_candidate_decisions(rows,market_regime="POZİTİF",
            contexts={s:{"data_freshness":"GUNCEL"} for s in ("A.IS","B.IS")})
        groups=duplicate_feature_hashes(decisions); self.assertEqual(("A.IS","B.IS"),next(iter(groups.values())))


if __name__ == "__main__": unittest.main()
