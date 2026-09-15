from datetime import datetime
from unittest.mock import patch
import subprocess
import types
import pytest

import numpy as np
import pandas as pd

import backtest
from intraday_backtest import walk_forward_tahminleri, performans_ozeti
from karar_motoru import karar_uret
from veri_kalite_kapisi import veri_kalite_kapisi
from veri_saglayici import _normalize, tamamlanmis_gunluk_barlar, ISTANBUL


def prices(n=520):
    rng = np.random.default_rng(42)
    close = 100 * np.exp(np.cumsum(rng.normal(.0005, .015, n)))
    return pd.DataFrame({'Open': close, 'High': close * 1.02,
                         'Low': close * .98, 'Close': close,
                         'Volume': np.full(n, 1000000)},
                        index=pd.date_range('2023-01-01', periods=n, freq='B'))


def test_timezone_future_and_incomplete_bars():
    frame = prices(3)
    frame.index = pd.date_range('2026-09-14', periods=3, tz=ISTANBUL)
    clean = _normalize(frame)
    assert clean.index[0].hour == 0
    morning = tamamlanmis_gunluk_barlar(clean, datetime(2026, 9, 15, 12, tzinfo=ISTANBUL))
    evening = tamamlanmis_gunluk_barlar(clean, datetime(2026, 9, 15, 19, tzinfo=ISTANBUL))
    assert len(morning) == 1 and len(evening) == 2


def test_invalid_prices_and_duplicates():
    frame = prices(4)
    frame.iloc[0, frame.columns.get_loc('High')] = np.inf
    frame = pd.concat([frame, frame.iloc[[3]]]).iloc[::-1]
    clean = _normalize(frame)
    assert len(clean) == 3
    assert clean.index.is_monotonic_increasing and clean.index.is_unique


def test_adjusted_and_raw_caches_are_isolated(tmp_path):
    import veri_saglayici as provider
    raw = prices(4)
    with patch.object(provider, 'uygulama_klasoru', return_value=tmp_path), \
         patch.object(provider, '_bist_ile_birlestir', side_effect=lambda *args: args[-1]) as official, \
         patch.object(provider.yf, 'download', return_value=raw) as fetch:
        provider.download('TEST.IS', auto_adjust=False)
        provider.download('TEST.IS', auto_adjust=True)
        provider.download('TEST.IS', auto_adjust=True)
        assert fetch.call_count == 2 and official.call_count == 1


def test_unknown_or_unresolved_labels_are_excluded():
    rows = pd.DataFrame({'sinyal_zamani': pd.date_range('2026-01-01', periods=40),
                         'sonuc_zamani': pd.Timestamp('2026-04-01'),
                         'net_getiri': .01, 'hedef_once': 1})
    assert walk_forward_tahminleri(rows)['tahmin_olasiligi'].isna().all()
    assert walk_forward_tahminleri(rows.drop(columns='sonuc_zamani'))['tahmin_olasiligi'].isna().all()


def test_initial_capital_is_included_in_drawdown():
    result = performans_ozeti(pd.DataFrame({'net_getiri': [-.1, .02], 'sonuc': ['STOP', 'SÜRE']}))
    assert np.isclose(result['maksimum_dusus'], -.1)


def test_risk_reward_does_not_reuse_optimistic_input():
    item = {'price': 100, 'atr': 2, 'hedef_1': 103, 'risk_getiri_1': 99}
    result = karar_uret(item)
    assert result['onerilen_satis'] == 103
    reward = result['onerilen_satis'] / result['onerilen_alis_ust'] - 1
    risk = 1 - result['onerilen_stop'] / result['onerilen_alis_ust']
    assert abs(result['karar_risk_getiri'] - reward / risk) < .03


def test_bad_volume_and_stale_cache_veto():
    base = {'veri_islem_gunu_gecikmesi': 0, 'veri_guven_puani': 90,
            'veri_kaynagi': 'Borsa İstanbul', 'veri_satir_sayisi': 200}
    assert veri_kalite_kapisi(base)['veri_kalite_onayli']
    for extras in ({'cache_fallback': True}, {'hacim_verisi_gecerli': False},
                   {'kurumsal_aksiyon_riski': 1}, {'veri_satir_sayisi': 30},
                   {'resmi_kapanis_dogrulandi': False}):
        assert not veri_kalite_kapisi({**base, **extras})['veri_kalite_onayli']


def test_baseline_backtest_and_date_integrity():
    try:
        source = subprocess.check_output(['git', 'show', 'eb04eb9:backtest.py'], stderr=subprocess.DEVNULL).decode('utf-8')
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip('Historical baseline requires a full Git clone')
    baseline = types.ModuleType('baseline_backtest')
    exec(compile(source, 'baseline_backtest.py', 'exec'), baseline.__dict__)
    frame = prices()
    with patch.object(backtest.yf, 'download', return_value=frame):
        before = baseline.backtest_hisse('TEST.IS')
        after = backtest.backtest_hisse('TEST.IS')
    assert before['islemler'] == after['islemler']
    assert len(after['islemler']) > 0
    shuffled = pd.concat([frame, frame.iloc[[100]]]).sample(frac=1, random_state=4)
    with patch.object(backtest.yf, 'download', return_value=shuffled):
        assert backtest.backtest_hisse('TEST.IS')['islemler'] == after['islemler']


def test_atr_has_no_future_fill():
    full = prices(100)
    short = backtest.atr_hesapla(full.iloc[:8])
    assert short.isna().all()
    pd.testing.assert_series_equal(backtest.atr_hesapla(full).iloc[:8], short)
