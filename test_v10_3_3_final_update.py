import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest

from trade_adaylari import (RADAR_COLUMNS, TomorrowTradeStore, opening_confirmation,
                            t1_listeleri, tomorrow_trade_top10)


def sample_frame(n=40):
    rows=[]
    for i in range(n):
        rows.append({"Hisse":f"H{i:02}","Movement Score":95-i,"Referans Skor":95-i,
          "Günlük Değişim %":2 if i%4 else -2,"relative_volume":1.8-i*.01,
          "price_acceleration_2":.02-i*.0002,"volume_acceleration_2":.4,
          "resistance20_distance":.005+i*.001,"close_location":.8 if i%4 else .2,
          "turnover20":200_000_000-i*2_000_000,"Durum":"GÜÇLÜ ERTESİ GÜN ADAYI",
          "Menkul Türü":"NORMAL_PAY","T+1 Seviye Doğrulandı":i%3==1,
          "T+1 Giriş":100,"T+1 Hedef":107,"T+1 Stop":96,"T+1 Risk/Getiri":1.75,
          "Veri Kaynağı":"Yahoo"})
    return pd.DataFrame(rows)


def test_production_provider_is_yahoo_and_fintables_is_not_instantiated(monkeypatch):
    import veri_saglayici
    assert isinstance(veri_saglayici._VARSAYILAN_ADAPTER, veri_saglayici.YahooProvider)
    assert veri_saglayici._VARSAYILAN_ADAPTER.__class__.__module__ == "veri_saglayici"
    assert "fintables" not in veri_saglayici._VARSAYILAN_ADAPTER.__class__.__name__.lower()


def test_wide_radar_and_elite_are_independent():
    groups=t1_listeleri(sample_frame())
    assert len(groups["wide"])==30
    assert len(groups["radar"])<=10
    assert set(groups["radar"].Hisse)<=set(groups["wide"].Hisse)
    assert list(groups["radar"].columns)==RADAR_COLUMNS
    assert set(groups["elite"].Hisse)!=set(groups["radar"].Hisse)


def test_weak_liquidity_and_distribution_do_not_win_raw_score():
    frame=sample_frame(12)
    frame.loc[0,"turnover20"]=100_000
    frame.loc[0,"Günlük Değişim %"]=-8
    frame.loc[0,"close_location"]=.05
    radar=t1_listeleri(frame)["radar"]
    assert radar.iloc[0].Hisse != "H00"


def test_tomorrow_top10_and_multi_confirmation():
    groups=t1_listeleri(sample_frame())
    daily=groups["wide"].head(5).copy(); daily["Daily Score"]=80
    result=tomorrow_trade_top10(daily,groups["wide"],groups["radar"],groups["elite"])
    assert len(result)<=10
    expected=set(daily.Hisse)&set(groups["radar"].Hisse)
    assert result[result.Hisse.isin(expected)]["Çoklu Teyit"].str.contains("ÇOKLU TEYİT").all()
    assert set(result["Açılış Teyidi"])=={"BEKLENİYOR"}


def test_opening_confirmation_rejects_blind_and_failed_gap():
    assert opening_confirmation(100,105,pd.DataFrame())=="BEKLENİYOR"
    bad=pd.DataFrame([{"Open":108,"High":109,"Low":102,"Close":103,"Volume":1000}])
    assert opening_confirmation(100,105,bad,106)=="OLUMSUZ"
    good=pd.DataFrame([{"Open":103,"High":107,"Low":102,"Close":106,"Volume":2000}])
    assert opening_confirmation(100,105,good,104)=="OLUMLU"


def test_snapshot_is_deduplicated_and_history_preserved(tmp_path):
    groups=t1_listeleri(sample_frame())
    result=tomorrow_trade_top10(groups["wide"].head(5),groups["wide"],groups["radar"],groups["elite"])
    store=TomorrowTradeStore(tmp_path/"history.sqlite3")
    store.save(result,"2026-09-02"); store.save(result,"2026-09-02")
    with store._db() as db:
        assert db.execute("select count(*) from tomorrow_trade_snapshots").fetchone()[0]==len(result)
    first=result.iloc[0]
    assert store.settle("2026-09-02",first.Hisse,{"Open":100,"High":108,"Low":95,"Close":104})
    metrics=store.metrics()
    assert metrics["count"]==1 and "HitRate@5" in metrics and "Profit Factor" in metrics


def test_trade_performance_dpi_layout_and_tooltips(qtbot, tmp_path):
    from dashboard_ui import TradePerformanceDashboard
    page=TradePerformanceDashboard(tmp_path/"p.sqlite3"); qtbot.addWidget(page)
    assert page.table.horizontalScrollBarPolicy().name=="ScrollBarAsNeeded"
    assert page.table.horizontalHeader().minimumHeight()>=42
    assert page.table.verticalHeader().defaultSectionSize()>=34
    names=[page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    for metric in ("Hit Rate","Precision","Recall","EV","MFE","MAE","Profit Factor","Target Hit Rate","Stop Hit Rate"):
        item=page.table.horizontalHeaderItem(names.index(metric)); assert item.toolTip()


def test_performance_exception_isolated(monkeypatch, qtbot, tmp_path):
    from dashboard_ui import TradePerformanceDashboard
    import t1t2_tahmin_sistemi
    page=TradePerformanceDashboard(tmp_path/"p.sqlite3"); qtbot.addWidget(page)
    monkeypatch.setattr(t1t2_tahmin_sistemi.EveningSnapshotStore,"performance_summary",lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    page.refresh()
    assert "okunamadı" in page.summary.text()
