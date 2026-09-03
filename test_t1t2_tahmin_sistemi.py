from dataclasses import replace
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from merkezi_karar_motoru import DecisionEngine, Kalibrasyon, KararGirdisi
from t1t2_tahmin_sistemi import (CacheIdentity, EveningSnapshotStore, ModelArtifact,
    build_point_in_time_dataset, cross_sectional_rank, feature_hash, point_in_time_features,
    load_artifacts, predict_symbol, radar_lists, ranking_metrics, settle_pending_snapshots,
    tick_price, t1t2_labels)
from veri_saglayici import DelayedDataProvider, HistoricalDataProvider, RealtimeDataProvider
from app_qt import paket_kaynak_klasoru


def frame(seed=1, n=80, end="2026-08-27"):
    rng=np.random.default_rng(seed); idx=pd.bdate_range(end=end,periods=n)
    close=100*np.cumprod(1+rng.normal(.001,.015,n)); op=close*(1+rng.normal(0,.004,n))
    high=np.maximum(op,close)*(1+rng.uniform(.002,.02,n)); low=np.minimum(op,close)*(1-rng.uniform(.002,.02,n))
    return pd.DataFrame({"Open":op,"High":high,"Low":low,"Close":close,"Volume":rng.integers(100000,5000000,n)},index=idx)


def test_bes_hisse_bes_hash():
    hashes={feature_hash(point_in_time_features(frame(i),"2026-08-27")) for i in range(1,6)}
    assert len(hashes)==5


def test_cache_tum_kimlik_alanlarini_icerir():
    a=CacheIdentity("AAA","2026-08-27","T+1","AKSAM","v1"); b=replace(a,symbol="BBB")
    assert a.key!=b.key and a.symbol in str(a)


def test_neden_listeleri_paylasilmaz():
    a=predict_symbol("A",frame(1),"2026-08-27","T+1",security_type="NORMAL_PAY")
    b=predict_symbol("B",frame(2),"2026-08-27","T+1",security_type="NORMAL_PAY")
    assert a.reasons is not b.reasons and a.feature_hash!=b.feature_hash


def test_vade_cacheleri_ve_tahminleri_ayridir():
    f=frame(1); a=predict_symbol("A",f,"2026-08-27","T+1",security_type="NORMAL_PAY")
    b=predict_symbol("A",f,"2026-08-27","T+2",security_type="NORMAL_PAY")
    assert a.cache_key!=b.cache_key and a.horizon!=b.horizon


def test_model_yokken_alma_bekle_degil_on_degerlendirme():
    p=predict_symbol("A",frame(),"2026-08-27","T+1",security_type="NORMAL_PAY")
    assert p.status=="ON DEGERLENDIRME - KALIBRE EDILMEMIS" and set(p.probabilities.values())=={None}


def test_merkezi_motor_kalibrasyonsuz_yatirim_karari_uretmez():
    g=KararGirdisi("A",100,"2026-08-27",vade="T+1",atr=2,veri_guncel=True,ohlcv_guvenilir=True,
                   piyasa_rejimi="POZITIF",sektor_destekliyor=True,kalibrasyon=Kalibrasyon())
    out=DecisionEngine().karar_ver(g)
    assert out.karar=="KARAR YOK" and out.on_degerlendirme and out.olasilik is None


def test_t1_ve_t2_ozelliklerine_gelecek_fiyat_sizmaz():
    f=frame(); cutoff=f.index[-3]; before=point_in_time_features(f,cutoff)
    f2=f.copy(); f2.iloc[-2:,f2.columns.get_loc("Close")]*=10
    assert before==point_in_time_features(f2,cutoff)


def test_dataset_kazanan_ve_kaybedenleri_birlikte_alir():
    up=frame(1); down=frame(2); up.iloc[-2:,up.columns.get_loc("High")]=up.iloc[-3].Close*1.1
    ds=build_point_in_time_dataset({"UP":up,"DOWN":down})
    assert set(ds.symbol)=={"UP","DOWN"} and ds["y_t1_max_return_5"].nunique()==2


def test_tavan_fiyat_adimiyla_etiketlenir():
    f=frame(); pos=len(f)-3; close=float(f.iloc[pos].Close)
    from fiyat_limitleri import pay_fiyat_limitleri
    f.iloc[pos+1,f.columns.get_loc("High")]=float(pay_fiyat_limitleri(close).ust_limit)
    assert t1t2_labels(f,pos)["y_t1_limit_up_hit"]==1


def test_giris_hedef_stop_fiyat_adimina_yuvarlanir():
    from decimal import Decimal
    from fiyat_limitleri import fiyat_adimi
    for value,direction in ((137.237,"down"),(137.237,"up")):
        rounded=tick_price(value,direction)
        assert Decimal(str(rounded))%fiyat_adimi(rounded)==0


def test_gun_ici_yuzde7_ile_kapanis_yuzde5_ayridir():
    f=frame(); pos=len(f)-3; close=float(f.iloc[pos].Close)
    f.iloc[pos+1,f.columns.get_loc("High")]=close*1.075
    f.iloc[pos+1,f.columns.get_loc("Close")]=close*1.01
    labels=t1t2_labels(f,pos)
    assert labels["y_t1_max_return_7"]==1 and labels["y_t1_close_return_5"]==0


def test_ayni_mum_hedef_stop_lehe_yazilmaz():
    f=frame(); pos=len(f)-3; f.iloc[pos+1,f.columns.get_loc("High")]=120; f.iloc[pos+1,f.columns.get_loc("Low")]=80
    assert t1t2_labels(f,pos,target=110,stop=90)["y_t1_target_before_stop"]==0


def test_seviye_matematigi_ve_rr_uygun():
    g=KararGirdisi("A",100,"2026-08-27",vade="T+1",atr=2,veri_guncel=True,ohlcv_guvenilir=True,
      piyasa_rejimi="POZITIF",sektor_destekliyor=True,kalibrasyon=Kalibrasyon(True,100,.7,.3))
    o=DecisionEngine().karar_ver(g); assert o.stop<o.giris_ust<o.hedef_1 and o.seviye_dogrulandi
    assert abs(o.risk_getiri-(o.hedef_1/o.giris_ust-1)/(1-o.stop/o.giris_alt))<1e-9


def test_asiri_genis_eski_destek_kullanilmaz():
    g=KararGirdisi("A",100,"2026-08-27",vade="T+1",atr=2,destek=60,direnc=180,veri_guncel=True,
      ohlcv_guvenilir=True,piyasa_rejimi="POZITIF",sektor_destekliyor=True,kalibrasyon=Kalibrasyon(True,100,.7,.3))
    o=DecisionEngine().karar_ver(g); assert (o.giris_ust-o.giris_alt)/100<=.035 and o.hedef_1<=108


def test_yeni_halka_arz_bayragi_korunur():
    g=KararGirdisi("IPO",100,"2026-08-27",vade="T+1",atr=2,yeni_halka_arz=True,veri_guncel=True,ohlcv_guvenilir=True)
    assert g.yeni_halka_arz


def test_alti_seanslik_hisse_ipo_yolunda_hash_ve_acik_durum_uretir():
    short=frame(8,n=6)
    prediction=predict_symbol("YENI.IS",short,short.index[-1],"T+1",security_type="NORMAL_PAY")
    assert prediction.feature_count>0
    assert prediction.current_price is not None
    assert prediction.status in {"YENI HALKA ARZ IZLEME - KALIBRE EDILMEMIS","HAREKET KACTI - YENI HALKA ARZ"}
    assert all(value is None for value in prediction.probabilities.values())


def test_tavani_yapmis_kisa_gecmisli_hisseye_gec_giris_uyarisi_verilir():
    short=frame(9,n=6); short.iloc[-1,short.columns.get_loc("Close")]=short.iloc[-2].Close*1.10
    short.iloc[-1,short.columns.get_loc("High")]=short.iloc[-1].Close
    prediction=predict_symbol("YENI.IS",short,short.index[-1],"T+1",security_type="NORMAL_PAY")
    assert prediction.status=="HAREKET KACTI - YENI HALKA ARZ"
    assert any("gec giris" in risk for risk in prediction.risks)


def test_menkul_turleri_ayri_tutulur():
    p=predict_symbol("FON",frame(),"2026-08-27","T+1",security_type="BYF")
    assert "MENKUL TURU" in p.status


def test_snapshot_degistirilemez_ve_outcome_ayri(tmp_path):
    store=EveningSnapshotStore(tmp_path/"x.db"); row=predict_symbol("A",frame(),"2026-08-27","T+1",security_type="NORMAL_PAY").dict()
    ok,row_id=store.save(row); assert ok
    db=sqlite3.connect(store.path)
    try:
      try: db.execute("UPDATE t1t2_snapshots SET score=999 WHERE id=?",(row_id,)); assert False
      except sqlite3.IntegrityError: pass
    finally: db.close()
    assert store.attach_outcome(row_id,{"return":.1},"2026-08-28")[0]


def test_bugunku_sonuc_snapshot_payloadunu_degistirmez(tmp_path):
    store=EveningSnapshotStore(tmp_path/"x.db"); row=predict_symbol("A",frame(),"2026-08-27","T+1",security_type="NORMAL_PAY").dict()
    ok,row_id=store.save(row); store.attach_outcome(row_id,{"return":.1},"2026-08-28")
    audit=store.audit(row["as_of_timestamp"]); assert json_load(audit[0]["payload_json"])["status"]==row["status"]


def test_bekleyen_t1_gerceklesmesi_otomatik_ve_ayri_kaydedilir(tmp_path):
    source=frame(4); cutoff=source.index[-3]
    prediction=predict_symbol("A.IS",source.loc[:cutoff],cutoff,"T+1",security_type="NORMAL_PAY")
    store=EveningSnapshotStore(tmp_path/"x.db"); assert store.save(prediction.dict())[0]
    result=settle_pending_snapshots(store,lambda _symbol:source,evaluated_at="2026-08-28")
    assert result["settled"]==1 and store.pending()==[]
    assert store.performance_summary()["horizons"]["T+1"]["total"]==1


def test_t2_iki_tamamlanmis_seans_olmadan_sonuclanmaz(tmp_path):
    source=frame(5); cutoff=source.index[-2]
    prediction=predict_symbol("A.IS",source.loc[:cutoff],cutoff,"T+2",security_type="NORMAL_PAY")
    store=EveningSnapshotStore(tmp_path/"x.db"); store.save(prediction.dict())
    result=settle_pending_snapshots(store,lambda _symbol:source)
    assert result["settled"]==0 and result["not_ready"]==1 and len(store.pending())==1


def test_performans_ozeti_ve_gercek_yukselen_denetimi(tmp_path):
    source=frame(6); cutoff=source.index[-3]; future=source.copy()
    base=float(source.loc[cutoff,"Close"]); future.iloc[-2,future.columns.get_loc("High")]=base*1.08
    prediction=predict_symbol("A.IS",source.loc[:cutoff],cutoff,"T+1",security_type="NORMAL_PAY")
    store=EveningSnapshotStore(tmp_path/"x.db"); row=prediction.dict(); row["rank"]=1
    ok,row_id=store.save(row); assert ok
    outcome={"status":"TAMAMLANDI","max_return_pct":8.,"close_return_pct":1.,
             "max_adverse_excursion_pct":-2.,"hit_5":1,"hit_7":1,"hit_8":1,
             "hit_limit_up":0,"closed_at_limit_up":0,"target_before_stop":1}
    assert store.attach_outcome(row_id,outcome,"2026-08-28")[0]
    summary=store.performance_summary()["horizons"]["T+1"]
    assert summary["precision_at_1"]==1 and summary["recall_at_20"]==1
    assert store.winner_audit()[0]["Hisse"]=="A" and store.winner_audit()[0]["Geniş Radarda"]


def json_load(value):
    import json; return json.loads(value)


def test_precision_ve_recall_metrikleri():
    rows=pd.DataFrame({"score":[.9,.8,.7,.6,.5],"y":[1,0,1,0,0]})
    m=ranking_metrics(rows,"score","y",ks=(1,3,5,10,20))
    assert m["precision_at_3"]==2/3 and m["recall_at_20"]==1


def test_kesitsel_sira_ve_yuzdelik():
    ps=[predict_symbol(str(i),frame(i),"2026-08-27","T+1",security_type="NORMAL_PAY") for i in range(1,6)]
    rows=cross_sectional_rank(ps); assert [r["rank"] for r in rows]==list(range(1,6)) and rows[0]["percentile"]==100


def test_kalibrasyonsuz_kural_skoru_kalibre_sirayla_karistirilmaz():
    uncalibrated=predict_symbol("IPO",frame(1,n=6),"2026-08-27","T+1",security_type="NORMAL_PAY")
    artifact=ModelArtifact("T+1","max_7",("ret_5",),(1,),0,"sigmoid",1,0,300,"2025","2026",.1)
    # Bir hedefli artefakt bütün olasılıkları tamamlamadığı için henüz kalibre sıra değildir.
    partial=predict_symbol("NORMAL",frame(2),"2026-08-27","T+1",{"T+1:max_7":artifact},"NORMAL_PAY")
    rows=cross_sectional_rank([uncalibrated,partial])
    assert all(not row["calibrated"] for row in rows)
    # Geniş 30 recall havuzu kalibrasyon yokken açıklanabilir Movement Score ile
    # çalışır; kalibrasyonsuz satırlar yalnız Seçkin listeye giremez.
    lists=radar_lists([uncalibrated,partial])
    assert len(lists["wide"])==2
    assert lists["elite"]==[]


def test_guvenilir_artefakt_olmadan_yuzde_yok():
    bad=ModelArtifact("T+1","max_5",("ret_5",),(1,),0,"sigmoid",1,0,10,"2025","2026",.2)
    p=predict_symbol("A",frame(),"2026-08-27","T+1",{"T+1:max_5":bad},"NORMAL_PAY")
    assert all(v is None for v in p.probabilities.values())


def test_esikler_sonuc_dolsun_diye_dusmez():
    ps=[predict_symbol(str(i),frame(i),"2026-08-27","T+1",security_type="NORMAL_PAY") for i in range(1,4)]
    assert all(p.status!="KALIBRE TAHMIN" for p in ps)
    assert radar_lists(ps)["elite"]==[]


def test_paketlenecek_model_dosyasi_on_iki_guvenilir_artefakt_icerir():
    artifacts, metrics=load_artifacts(Path(__file__).parent/"models"/"t1t2_reference.json")
    assert len(artifacts)==12 and all(item.reliable for item in artifacts.values())
    assert metrics["symbols"]>=500 and metrics["rows"]>=50000


def test_kaynak_calismada_model_kok_klasoru_cozulur():
    assert (paket_kaynak_klasoru()/"models"/"t1t2_reference.json").is_file()


def test_canli_veri_yokken_teyit_uydurulmaz():
    assert isinstance(HistoricalDataProvider(), HistoricalDataProvider)
    assert isinstance(DelayedDataProvider(), DelayedDataProvider)
    try:
        RealtimeDataProvider().get_intraday_ohlcv("ASELS.IS")
        assert False
    except RuntimeError as exc:
        assert "canli teyit kapali" in str(exc)
