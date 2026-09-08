"""Deterministic regressions; these verify accounting, not future profitability."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from tahmin_defteri import (sonucu_hesapla, sinyal_kaydet, sonucu_kaydet,
    aktif_sinyaller, performans_ozeti, kalibrasyon_gecmisi, acik_tahminleri_sonuclandir)
from profesyonel_karar_sistemi import net_ev_hesapla, CostModel, pozisyon_hesapla, kalibrasyon_ozeti
from veri_saglayici import _normalize, _istanbul_index, YahooPiyasaVeriAdapteri, download
from saglam_backtest import performans_metrikleri, veri_butunlugu_kontrolu
from karar_motoru import karar_uret


def bars(rows):
    return pd.DataFrame(rows, columns=['Open', 'High', 'Low', 'Close'])


def signal(**kwargs):
    return dict(entry_low=99, entry_high=100, stop=95, target_2=110, duration_high=3, **kwargs)


class IntegrityTests(unittest.TestCase):
    def test_never_entered_is_not_a_loss(self):
        result = sonucu_hesapla(signal(), bars([[90,94,85,91]]*3))
        self.assertEqual(result['status'], 'GİRİŞ OLMADI')
        self.assertNotIn('net_return_pct', result)

    def test_pending_trade_stays_open(self):
        self.assertEqual(sonucu_hesapla(signal(), bars([[100,104,98,102]]))['status'], 'AÇIK')

    def test_late_target_does_not_change_expiry(self):
        data = bars([[100,104,98,102]]*3 + [[102,120,101,115]])
        result = sonucu_hesapla(signal(), data)
        self.assertEqual(result['status'], 'SÜRESİ DOLDU')
        self.assertAlmostEqual(result['net_return_pct'], 1.66)

    def test_stop_gap_uses_actual_open(self):
        result = sonucu_hesapla(signal(), bars([[100,104,98,102],[90,96,85,92]]))
        self.assertEqual(result['exit_price'], 90)
        self.assertAlmostEqual(result['net_return_pct'], -10.34)

    def test_same_bar_is_stop_first(self):
        self.assertEqual(sonucu_hesapla(signal(), bars([[100,112,94,105]]))['status'], 'STOP ÖNCE')

    def test_intrabar_entry_cannot_claim_earlier_target(self):
        self.assertEqual(sonucu_hesapla(signal(), bars([[112,115,99,102]]))['status'], 'AÇIK')

    def test_post_exit_prices_do_not_change_excursions(self):
        first = bars([[100,104,98,102],[102,111,101,110]])
        extended = pd.concat([first, bars([[110,200,1,100]])], ignore_index=True)
        self.assertEqual(sonucu_hesapla(signal(), first), sonucu_hesapla(signal(), extended))

    def test_missing_open_is_not_scored(self):
        self.assertEqual(sonucu_hesapla(signal(), bars([[100,104,98,102]]).drop(columns='Open'))['status'], 'BELİRSİZ')

    def test_loss_uses_entry_denominator(self):
        result = net_ev_hesapla(50,100,110,90,CostModel(0,0,0))
        self.assertEqual(result['net_ev_pct'],0)

    def test_position_is_cash_capped(self):
        self.assertLessEqual(pozisyon_hesapla(1000,100,99.99)['position_qty']*100,1000)

    def test_first_loss_counts_in_drawdown(self):
        self.assertEqual(performans_metrikleri(pd.DataFrame({'Getiri %':[-10]}))['max_drawdown'],-10)

    def test_future_news_fails_validation(self):
        frame = pd.DataFrame([dict(symbol='X', date='2026-01-01', was_listed=True,
            adjusted_for_splits=True, dividend_adjusted=True, kap_published_at='2026-01-03', decision_time='2026-01-02')])
        self.assertFalse(veri_butunlugu_kontrolu(frame)['safe_for_model_selection'])

    def test_timezone_round_trip(self):
        data = bars([[100,104,98,102]])
        data.index = pd.DatetimeIndex(['2026-01-05 07:00'], tz='UTC')
        self.assertEqual(_istanbul_index(_normalize(data)).index[0].hour,10)

    def test_cache_is_separated_by_adjustment(self):
        data = bars([[100,104,98,102]])
        with patch('veri_saglayici._oku', return_value=data) as read, patch('veri_saglayici._bist_ile_birlestir', return_value=data):
            download('TEST.IS',auto_adjust=True)
            download('TEST.IS',auto_adjust=False)
        self.assertNotEqual(read.call_args_list[0].args[0],read.call_args_list[1].args[0])

    def test_old_risk_reward_does_not_override_plan(self):
        item = dict(price=100, atr=2, risk_getiri_1=99, fib_direnc=103, stop_loss=95,
                    veri_guven_puani=90, v4_guven_puani=80)
        result = karar_uret(item)
        self.assertEqual(result['onerilen_satis'],103)
        expected=(result['onerilen_satis']-result['onerilen_alis_ust'])/(result['onerilen_alis_ust']-result['onerilen_stop'])
        self.assertAlmostEqual(result['karar_risk_getiri'],expected,places=2)

    def test_calibration_excludes_unfilled_and_invalid(self):
        history=pd.DataFrame({'Strateji':['general_scan']*40, 'Durum':['GİRİŞ OLMADI']*35+['HEDEF ÖNCE']*5})
        result=kalibrasyon_ozeti(history,'general_scan')
        self.assertEqual(result['samples'],5)
        self.assertIsNone(result['probability'])

    def test_missing_probabilities_are_not_imputed(self):
        history=pd.DataFrame({'Strateji':['general_scan']*30, 'Durum':['HEDEF ÖNCE']*30})
        self.assertIsNone(kalibrasyon_ozeti(history,'general_scan')['brier'])

    def test_repeat_scan_and_resolution_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            item=dict(symbol='X',veri_tarihi='2026-01-01',onerilen_alis_alt=99,onerilen_alis_ust=100,
                      onerilen_stop=95,onerilen_satis=110,beklenen_sure_ust=3)
            a=sinyal_kaydet(item,'general_scan',path)
            b=sinyal_kaydet(item,'general_scan',path)
            self.assertEqual(a['signal_id'],b['signal_id'])
            quiet=bars([[100,104,98,102]])
            sonucu_kaydet(a,quiet,path)
            self.assertEqual(len(aktif_sinyaller(path)),1)
            hit=bars([[100,111,98,110]])
            sonucu_kaydet(a,hit,path);sonucu_kaydet(a,hit,path)
            self.assertEqual(performans_ozeti(path)[0].iloc[0]['Örnek'],1)
            self.assertEqual(kalibrasyon_gecmisi(path).iloc[0]['Strateji'],'general_scan')

    def test_creation_date_prevents_backdated_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            item=dict(symbol='X',veri_tarihi='2020-01-01',onerilen_alis_alt=99,onerilen_alis_ust=100,
                      onerilen_stop=95,onerilen_satis=110,beklenen_sure_ust=3)
            sinyal_kaydet(item,'general_scan',path)
            hit=bars([[100,111,98,110]])
            hit.index=pd.DatetimeIndex(['2020-01-02'])
            self.assertEqual(acik_tahminleri_sonuclandir(path,lambda _:hit),[])

class DailyCompletionTests(unittest.TestCase):
    def test_current_daily_bar_is_not_available_before_close(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from veri_saglayici import tamamlanmis_gunluk_barlar
        data=bars([[100,104,98,102],[102,106,100,104]])
        data.index=pd.DatetimeIndex(['2026-01-05','2026-01-06'])
        self.assertEqual(len(tamamlanmis_gunluk_barlar(data, datetime(2026,1,6,12,tzinfo=ZoneInfo('Europe/Istanbul')))),1)
        self.assertEqual(len(tamamlanmis_gunluk_barlar(data, datetime(2026,1,6,19,tzinfo=ZoneInfo('Europe/Istanbul')))),2)

    def test_bad_ohlc_is_removed(self):
        data=bars([[100,90,98,102]])
        self.assertTrue(_normalize(data).empty)

    def test_invalid_bar_after_exit_does_not_rewrite_outcome(self):
        data=bars([[100,111,98,110],[100,50,120,90]])
        self.assertEqual(sonucu_hesapla(signal(),data)['status'],'HEDEF ÖNCE')
