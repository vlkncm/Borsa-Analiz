"""Gercek Qt sayfalarini farkli ekran/DPI profillerinde PNG olarak render eder."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BORSA_VISUAL_TEST", "1")

import pandas as pd
from PySide6.QtWidgets import QApplication

from app_qt import MainWindow


def radar_fixture() -> pd.DataFrame:
    common = {
        "Önceki Kapanış": 100.0, "Güncel Fiyat": 102.4, "Günlük Değişim %": 2.4,
        "Tavan Fiyatı": 110.0, "Tavana Kalan %": 7.4, "T+1 Sırası": 3,
        "T+2 Sırası": 8, "T+1 %7+ Olasılığı": 42.0, "T+1 %8+ Olasılığı": 31.0,
        "T+1 Tavan Olasılığı": 12.0, "T+2 %7+ Olasılığı": 48.0,
        "T+2 %8+ Olasılığı": 35.0, "T+2 Tavan Olasılığı": 15.0,
        "T+1 Giriş": 102.5, "T+1 Hedef": 109.2, "T+1 Stop": 99.8,
        "T+2 Giriş": 102.6, "T+2 Hedef": 110.1, "T+2 Stop": 99.4,
        "T+1 Risk/Getiri": 2.4, "T+2 Risk/Getiri": 2.3,
        "T+1/T+2 Durumu": "TEYİT BEKLİYOR", "Durum": "ERKEN ADAY",
        "Model Yolu": "STANDART", "Menkul Türü": "NORMAL_PAY",
        "T+1 Seviye Doğrulandı": True, "T+2 Seviye Doğrulandı": True,
        "T+1 Net EV": 1.2, "T+2 Net EV": 1.5, "Model Sürümü": "visual-test",
        "Veri Zamanı": "2026-08-28 18:10", "Piyasa Rejimi": "POZİTİF",
        "Aday Nedenleri": ["Göreceli hacim güçlü", "Fiyat sıkışması korunuyor"],
        "Riskler": ["Canlı açılış teyidi henüz yok"],
    }
    rows = []
    for index, symbol in enumerate(("ASELS", "THYAO", "TUPRS", "SISE", "KCHOL"), 1):
        row = dict(common); row["Hisse"] = symbol; row["T+1 Sırası"] = index; row["T+2 Sırası"] = index + 3
        row["Güncel Fiyat"] += index; rows.append(row)
    ipo = dict(common); ipo.update({
        "Hisse": "YENI", "Model Yolu": "YENI_HALKA_ARZ", "Durum": "YENİ HALKA ARZ – İZLE",
        "Kotasyon Tarihi": "20.08.2026", "İşlem Günü Sayısı": 6, "Halka Arz Fiyatı": 85.4,
        "Halka Arzdan Beri Getiri %": 19.9, "Ardışık Tavan Sayısı": 2,
        "Göreceli Hacim": 1.8, "Momentum Durumu": "GÜÇLÜ", "Risk Durumu": "YÜKSEK RİSK",
        "Veri Yeterlilik Seviyesi": "YENİ HALKA ARZ", "Son Değerlendirme Zamanı": "28.08.2026 18:10",
    }); rows.append(ipo)
    return pd.DataFrame(rows)


def decision_fixture() -> pd.DataFrame:
    return pd.DataFrame([
        {"Hisse": symbol, "Güncel Fiyat": 42.0 + index, "Alım Bölgesi": "41,80–42,30",
         "Hedef": 46.2, "Stop": 40.5, "Beklenen Süre": "5–10 işlem günü",
         "Model Olasılığı %": 61.0, "Yatırım Kararı": "İZLE", "Risk %": 3.5,
         "Karar Nedenleri": "Trend ve hacim birlikte güçleniyor", "Veri Tarihi": "28.08.2026"}
        for index, symbol in enumerate(("ASELS", "THYAO", "TUPRS"))
    ])


def daily_fixture() -> pd.DataFrame:
    return pd.DataFrame([{
        "Hisse": "ASELS", "Sonuç": "TEYİT BEKLE", "Alış Alt": 181.2, "Alış Üst": 183.0,
        "Hedef": 192.5, "Stop": 177.8, "Hedef Potansiyeli %": 5.2,
        "Hedef Önce Olasılığı %": "Yetersiz örnek", "Olasılık Ufku — İşlem Günü": 1,
        "Piyasa Rejimi": "POZİTİF", "Tazelik": "GÜNCEL", "Veri Zamanı": "2026-08-28 18:10",
        "Gerekçe": "Normalden güçlü hacim; açılış teyidi bekleniyor.",
    }])


def prepare(window: MainWindow):
    radar = radar_fixture(); decisions = decision_fixture()
    window.next_day.load_results(radar, "548 hisse tarandı · test görünümü")
    window.daily_trade.scan_done(True, daily_fixture(), "Test görünümü")
    window.short_term.load(decisions); window.medium_term.load(decisions)
    under = decisions.copy(); under["Güncel Fiyat"] = [18.2, 24.5, 39.8]; window.under_50.load(under)
    funds = pd.DataFrame([
        {"Fon": "Örnek Değişken Fon", "Fon Kodu": "ODF", "Güncel Değer": 4.251,
         "Günlük Getiri %": 0.6, "Aylık Getiri %": 7.8, "Risk": 5,
         "Fon Türü": "Değişken", "Karar": "İZLE"}
    ]); window.funds.table.load(funds)
    window.track.load(pd.DataFrame([{"Hisse": "ASELS", "Adet": 100, "Maliyet": 170.0,
        "Güncel": 184.2, "Kâr/Zarar": 1420.0, "Ana Karar": "BEKLE", "Kâr Alma Miktarı": 25}]))
    window.home.update_state(decisions, decisions, decisions, "POZİTİF", growth_count=2)
    performance = pd.DataFrame([{"Tarih": "28.08.2026", "Hisse": "ASELS", "Vade": "T+1",
        "Gerçekleşen Maksimum %": 7.4, "Tavan Gördü": False, "Önceki Sıra": 3,
        "Geniş Radarda": True, "Seçkin Aday": True}])
    window.history.table.load_frame(performance, window.history.COLUMNS, window.history.COLUMNS)
    return radar


def render(output: Path, width: int, height: int):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(); radar = prepare(window); window.resize(width, height); window.show(); app.processEvents()
    captures = [
        ("ana_sayfa", "home", None), ("radar_t1", "next", 0), ("radar_t1_seckin", "next", 1),
        ("radar_t2", "next", 2), ("radar_tavan", "next", 4), ("yeni_halka_arz", "next", 5),
        ("gunluk_trade", "daily", None), ("kisa_vade", "short", None),
        ("orta_vade", "medium", None), ("elli_tl_alti", "under50", None),
        ("fon_analizi", "funds", None), ("portfoy", "portfolio", None),
        ("tahmin_performansi", "performance", None), ("ayarlar", "settings", None),
    ]
    output.mkdir(parents=True, exist_ok=True)
    for name, page, tab in captures:
        window._show_page(page)
        if tab is not None: window.next_day.tabs.setCurrentIndex(tab)
        app.processEvents(); window.grab().save(str(output / f"{name}.png"))
    record = radar.iloc[0].to_dict(); table = window.next_day.tables["t1wide"]
    window.next_day._detail_window.show_record(record, table.analysis_context.with_record(record))
    app.processEvents(); window.next_day._detail_window.grab().save(str(output / "analiz_detayi.png"))
    window.next_day._detail_window.close(); window.close(); app.processEvents()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, required=True); parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args(); render(Path(args.output), args.width, args.height)
