import os
import sys
import traceback
import uuid
import time
import json
import faulthandler
from pathlib import Path
from datetime import datetime

import pandas as pd
from gunluk_trade_gostergeleri import en_iyi_gunluk_trade_adaylari
from sade_karar_modeli import (
    elli_tl_adaylari, elli_tl_ohlcv_adayi, en_iyi_vade, gunluk_rapor_adaylari,
    orta_vadeden_kisa_adaylari_cikar, sade_firsatlar, sure_metni, vade_rapor_adaylari,
)
from bist_evreni import likit_120_sec
from bist30 import bist30_hisseleri, normalize_bist_sembolu
from analysis_orchestration import (
    ANALYSIS_UNIVERSES, build_analysis_universes, tag_analysis_result,
)
from scan_candidate_policy import ScanDiagnostics, write_scan_diagnostics
from gunluk_islem_plani import gun_sonu_plani, sabah_fiyat_kontrolu
from sosyal_medya_risk import sosyal_medya_risk_analizi
from PySide6.QtCore import (
    Qt, QObject, Signal, QThread, QUrl, QTimer, QProcess, QProcessEnvironment,
)
from PySide6.QtGui import QIcon, QColor, QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QMessageBox, QFrame, QLineEdit, QAbstractItemView, QTabWidget,
    QDialog, QGridLayout, QScrollArea, QSizePolicy, QComboBox, QDoubleSpinBox,
    QCheckBox, QProgressBar
)
from dashboard_ui import (
    APP_STYLE, InvestmentGuidePage, MarketCard, MarketDataWorker, NextDayDashboard, PlaceholderPage,
    Sidebar, T1T2PerformanceDashboard, TopHeader,
)
from responsive_ui import (
    AnalysisContext, AnalysisDetailWindow, BaseAnalysisPage, PROFILE_COMPACT,
    ResponsiveResultTable, profile_for_width,
)
from scan_progress import ScanCoordinator, TERMINAL_STATES

APP_NAME = "Borsa Analiz Pro MAX"
APP_VERSION = "10.3.1"
_CRASH_STREAM = None


def uygulama_klasoru() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def paket_kaynak_klasoru() -> Path:
    """PyInstaller veri dosyalari icin _MEIPASS, kaynak calismada proje kokunu doner."""
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle).resolve() if bundle else Path(__file__).resolve().parent


def veri_klasoru() -> Path:
    base = Path.home() / "Documents" / "Borsa Analiz Pro MAX"
    base.mkdir(parents=True, exist_ok=True)
    return base


def rapor_yolu() -> Path:
    output = veri_klasoru() / "output"
    return output / "analiz_sonuclari.sqlite3"


def tarama_alt_sureci_komutu():
    """Kaynak kod ve PyInstaller EXE için güvenli tarama alt süreci komutu."""
    if getattr(sys, "frozen", False):
        # Paket kendi headless tarama girişini ayrı bir işletim sistemi sürecinde
        # çalıştırır. Böylece eksik ikinci EXE yüzünden toplu tarama başlamamazlık
        # etmez; analiz çökse bile ana arayüz süreci korunur.
        return str(Path(sys.executable).resolve()), ["--headless-scan"]
    return sys.executable, [str(Path(__file__).resolve().with_name("scan_runner.py"))]


def normalize_symbol(text: str) -> str:
    return normalize_bist_sembolu(text)


def guvenli_sayi(value, default=0.0):
    try:
        number = float(value)
        return number if pd.notna(number) else default
    except (TypeError, ValueError):
        return default


def hata_gunlugune_yaz(context: str, details: str) -> None:
    """Arayüz/worker hatalarını EXE'de de sonradan incelenebilir halde tutar."""
    try:
        log_path = veri_klasoru() / "uygulama_hatalari.log"
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(
                f"\n[{datetime.now().isoformat(timespec='seconds')}] {context}\n{details.rstrip()}\n"
            )
    except Exception:
        # Hata kaydındaki bir dosya sistemi sorunu uygulamayı kapatmamalı.
        pass


def karar_gruplarina_ayir(df):
    """BIST sonuçlarını vade yerine uygulanabilir alış kararına göre ayırır."""
    if df is None or df.empty:
        empty = pd.DataFrame(columns=[] if df is None else df.columns)
        return empty.copy(), empty.copy(), empty.copy()
    decision = df.get("Yatırım Kararı", pd.Series("", index=df.index)).astype(str).str.upper()
    buy_mask = decision.eq("BUGÜN AL")
    wait_mask = decision.str.contains("BEKLE|İZLE", regex=True, na=False)
    avoid_mask = ~(buy_mask | wait_mask)
    return df.loc[buy_mask].copy(), df.loc[wait_mask].copy(), df.loc[avoid_mask].copy()


def teknik_degerlendirme_uret(result, symbol=""):
    """Grafikte kullanılan göstergeleri çelişkisiz, açıklanabilir metne dönüştürür."""
    symbol = str(symbol or result.get("symbol", "")).replace(".IS", "").upper()
    decision = str(result.get("yatirim_karari", "İZLE"))
    price = guvenli_sayi(result.get("price"))
    ema20 = guvenli_sayi(result.get("ema20"))
    ema50 = guvenli_sayi(result.get("ema50"))
    ema200 = guvenli_sayi(result.get("ema200"))
    rsi = guvenli_sayi(result.get("rsi"), 50)
    macd = guvenli_sayi(result.get("macd"))
    macd_signal = guvenli_sayi(result.get("macd_signal"))
    adx = guvenli_sayi(result.get("adx"))
    volume_ratio = guvenli_sayi(result.get("volume_ratio"), 1)
    buy_low = guvenli_sayi(result.get("onerilen_alis_alt"))
    buy_high = guvenli_sayi(result.get("onerilen_alis_ust"))
    target = guvenli_sayi(result.get("onerilen_satis"))
    stop = guvenli_sayi(result.get("onerilen_stop"))
    probability = guvenli_sayi(result.get("model_olasiligi"))
    rr = guvenli_sayi(result.get("karar_risk_getiri"))
    expected_time = str(result.get("beklenen_sure", "Hesaplanamadı"))
    time_confidence = str(result.get("sure_tahmin_guveni", "DÜŞÜK"))
    data_confidence = guvenli_sayi(
        result.get("karar_veri_guveni", result.get("veri_guven_puani"))
    )
    evidence = guvenli_sayi(
        result.get("karar_kanit_puani", result.get("profesyonel_kanit_puani"))
    )
    samples = int(guvenli_sayi(
        result.get("karar_kanit_ornegi", result.get("kisa_ornek"))
    ))
    safe_probability = guvenli_sayi(result.get("kisa_guvenli_olasilik"))
    data_status = str(result.get("veri_durumu", "BİLİNMİYOR"))
    data_date = str(result.get("veri_tarihi", "-"))
    market_regime = str(result.get("piyasa_rejimi", "YATAY / BELİRSİZ"))

    if price > ema20 > ema50 and (ema200 <= 0 or price > ema200):
        trend_text = "Pozitif: fiyat kısa ve orta vadeli ortalamaların üzerinde."
    elif price < ema20 < ema50:
        trend_text = "Negatif: fiyat EMA20 altında ve EMA20 de EMA50 altında."
    else:
        trend_text = "Karışık: hareketli ortalamalar aynı yönde ortak teyit vermiyor."
    if ema200 > 0:
        trend_text += (
            " Uzun vadeli yapı EMA200 üzerinde korunuyor."
            if price > ema200
            else " Fiyat EMA200 altında; uzun vadeli trend baskılı."
        )

    if adx >= 25:
        adx_text = f"ADX {adx:.1f}; mevcut yön belirgin güç taşıyor."
    elif adx >= 20:
        adx_text = f"ADX {adx:.1f}; trend oluşuyor ancak henüz güçlü değil."
    else:
        adx_text = f"ADX {adx:.1f}; piyasa yatay veya yön gücü zayıf olabilir."

    if rsi >= 70:
        rsi_text = f"RSI {rsi:.1f}; aşırı alım bölgesinde, geri çekilme riski arttı."
    elif rsi >= 65:
        rsi_text = f"RSI {rsi:.1f}; momentum güçlü fakat ısınmış durumda."
    elif rsi >= 45:
        rsi_text = f"RSI {rsi:.1f}; dengeli/sağlıklı momentum bölgesinde."
    elif rsi >= 30:
        rsi_text = f"RSI {rsi:.1f}; momentum zayıf, toparlanma teyidi gerekiyor."
    else:
        rsi_text = f"RSI {rsi:.1f}; aşırı satımda ancak bu tek başına alım sinyali değildir."
    macd_text = (
        f"MACD ({macd:.2f}) sinyalin ({macd_signal:.2f}) üzerinde; momentum pozitif."
        if macd > macd_signal
        else f"MACD ({macd:.2f}) sinyalin ({macd_signal:.2f}) altında; momentum teyidi zayıf."
    )
    if volume_ratio >= 1.2:
        volume_text = f"Hacim 20 günlük ortalamanın {volume_ratio:.2f} katı; hareket hacimle destekleniyor."
    elif volume_ratio < 0.8:
        volume_text = f"Hacim ortalamanın yalnızca {volume_ratio:.2f} katı; fiyat hareketinin teyidi zayıf."
    else:
        volume_text = f"Hacim oranı {volume_ratio:.2f}; olağan bantta."

    daily = str(result.get("gunluk_yon", "TUT"))
    weekly = str(result.get("haftalik_yon", "TUT"))
    mtf_fit = str(result.get("mtf_uyum", "Veri Yok"))
    mtf_score = guvenli_sayi(result.get("mtf_skor"), 50)
    mtf_text = (
        f"Günlük yön {daily}, haftalık yön {weekly}; uyum “{mtf_fit}” ve birleşik skor {mtf_score:.0f}/100."
    )

    if buy_low > 0 and buy_high > 0 and price > 0:
        if buy_low <= price <= buy_high:
            entry_text = "Güncel fiyat hesaplanan alış bandının içinde."
        elif price > buy_high:
            distance = (price / buy_high - 1) * 100
            entry_text = f"Güncel fiyat alış bandının %{distance:.2f} üzerinde; fiyatı kovalamak riski artırır."
        else:
            distance = (buy_low / price - 1) * 100
            entry_text = f"Güncel fiyat alış bandının %{distance:.2f} altında; yeniden teyit beklenmeli."
    else:
        entry_text = "Geçerli alış bandı hesaplanamadı."

    target_gain = ((target / price) - 1) * 100 if target > 0 and price > 0 else 0
    stop_loss = (1 - stop / price) * 100 if 0 < stop < price else 0
    level_text = (
        f"Alış bandı {buy_low:.2f}–{buy_high:.2f} TL, hedef {target:.2f} TL "
        f"(güncelden potansiyel %{target_gain:.2f}), stop {stop:.2f} TL "
        f"(güncelden risk %{stop_loss:.2f}). Risk/getiri yaklaşık 1:{rr:.2f}."
    )
    time_text = (
        f"Hedefe tahmini erişim süresi: {expected_time}. Süre tahmini güveni: {time_confidence}. "
        "Bu bir son tarih değildir; hedefe bu aralıkta ulaşılmayabilir veya önce stop çalışabilir."
    )

    evidence_text = (
        f"Model olasılığı %{probability:.0f}; veri güveni %{data_confidence:.0f}, "
        f"profesyonel kanıt puanı {evidence:.1f}/100."
    )
    if samples >= 20:
        evidence_text += (
            f" Benzer geçmiş rejimde {samples} örnek var; Wilson güvenli alt olasılığı "
            f"%{safe_probability:.1f}."
        )
    else:
        evidence_text += (
            f" Benzer geçmiş rejimde yalnızca {samples} örnek var; olasılık düşük güvenle yorumlanmalı."
        )

    risks = []
    if "ESKİ" in data_status.upper() or data_confidence < 60:
        risks.append("Fiyat verisi güncel veya yeterince güvenilir değil; işlem kararı üretilmemeli.")
    if samples < 20:
        risks.append("Tarihsel benzer örnek sayısı 20'nin altında.")
    if "DÜŞÜŞ" in market_regime.upper():
        risks.append("BIST piyasa rejimi düşüş yönünde.")
    if "NEGATİF" in mtf_fit.upper():
        risks.append("Günlük ve haftalık zaman dilimleri negatif uyum gösteriyor.")
    if rsi >= 70:
        risks.append("RSI aşırı alım bölgesinde.")
    if ema200 > 0 and price < ema200:
        risks.append("Fiyat uzun vadeli EMA200 altında.")
    if macd <= macd_signal:
        risks.append("MACD pozitif teyit vermiyor.")
    if volume_ratio < 0.8:
        risks.append("Hacim hareketi yeterince desteklemiyor.")
    if rr < 1.5:
        risks.append("Risk/getiri 1:1,5 eşiğinin altında.")
    risk_text = "\n".join(f"- {risk}" for risk in risks) if risks else (
        "- Ana göstergelerde ek yüksek risk alarmı oluşmadı; yine de stop ve veri güncelliği kontrol edilmeli."
    )

    conclusion_map = {
        "BUGÜN AL": "Ortak teyitler güçlü. Yalnızca alış bandı korunuyorsa ve stop disiplini kabul ediliyorsa değerlendirilebilir.",
        "ALIM BÖLGESİNİ BEKLE": "Görünüm tamamen olumsuz değil fakat güncel seviyeden fiyatı kovalamak yerine hesaplanan alış bandı beklenmeli.",
        "İZLE - KANIT YETERSİZ": "Teknik görünüm izlemeye değer olsa da tarihsel kanıt sayısı karar vermek için yetersiz.",
        "İZLE": "Olumlu ve olumsuz göstergeler karışık; ortak teyit oluşana kadar izlemek daha tutarlı.",
        "ALMA": "Trend, momentum veya risk/getiri koşulları yeni pozisyon için yeterli değil.",
        "VERİ KONTROLÜ GEREKLİ": "Veri kalitesi karar üretmeye uygun değil; güncel veri gelmeden sonuç kullanılmamalı.",
    }
    conclusion = conclusion_map.get(
        decision,
        "Karar yalnızca hesaplanan teknik koşullar çerçevesinde ve risk sınırlarıyla değerlendirilmelidir.",
    )

    return "\n".join([
        f"{symbol} — YAZILI TEKNİK DEĞERLENDİRME",
        f"Veri tarihi: {data_date} | Veri durumu: {data_status} | Piyasa rejimi: {market_regime}",
        "",
        f"SONUÇ: {decision}",
        evidence_text,
        f"Karar gerekçesi: {result.get('karar_nedenleri', '-')}",
        "",
        "1) GRAFİK VE TREND OKUMASI",
        trend_text,
        adx_text,
        "",
        "2) MOMENTUM VE HACİM",
        rsi_text,
        macd_text,
        volume_text,
        "",
        "3) ÇOKLU ZAMAN DİLİMİ",
        mtf_text,
        "",
        "4) ALIŞ, HEDEF VE STOP",
        entry_text,
        level_text,
        time_text,
        "",
        "5) ÖNEMLİ RİSKLER",
        risk_text,
        "",
        "NİHAİ YORUM",
        conclusion,
        "",
        "Bu değerlendirme canlı fiyat akışı değildir ve yatırım garantisi vermez. "
        "Karar öncesinde güncel fiyat, KAP açıklamaları ve kişisel risk sınırı ayrıca kontrol edilmelidir.",
    ])


class ScanWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def run(self):
        try:
            import main as analiz_main

            class Stream:
                def __init__(self, signal):
                    self.signal = signal
                    self.buffer = ""
                def write(self, text):
                    self.buffer += str(text)
                    while "\n" in self.buffer:
                        line, self.buffer = self.buffer.split("\n", 1)
                        if line.strip():
                            self.signal.emit(line)
                def flush(self):
                    if self.buffer.strip():
                        self.signal.emit(self.buffer)
                        self.buffer = ""

            old_out, old_err = sys.stdout, sys.stderr
            stream = Stream(self.log)
            sys.stdout = stream
            sys.stderr = stream
            try:
                analiz_main.main()
            finally:
                stream.flush()
                sys.stdout, sys.stderr = old_out, old_err

            self.finished.emit(True, "Tarama tamamlandı.")
        except Exception:
            self.finished.emit(False, traceback.format_exc())


class SingleWorker(QObject):
    finished = Signal(bool, object, str)
    progress = Signal(str)

    def __init__(self, symbol, mode, position=None):
        super().__init__()
        self.symbol = symbol
        self.mode = mode
        self.position = position or {}

    def run(self):
        try:
            from borsa_tarayici import teknik_analiz
            from v4_puanlama import v4_puanla
            from karar_motoru import karar_uret
            from satis_karar_motoru import satis_karari_uret

            self.progress.emit("Günlük fiyat verisi ve teknik göstergeler kontrol ediliyor...")
            result = teknik_analiz(self.symbol, "TEK HİSSE")
            if not result:
                self.finished.emit(False, {}, "Yeterli fiyat verisi bulunamadı.")
                return

            if self.mode == "analysis":
                from mtf_grafik import coklu_zaman_dilimi_analizi
                from pro_moduller import makro_analiz_yfinance

                self.progress.emit("Günlük ve haftalık trend uyumu hesaplanıyor...")
                result.update(coklu_zaman_dilimi_analizi(self.symbol))
                self.progress.emit("BIST 100 piyasa rejimi kontrol ediliyor...")
                result.update(makro_analiz_yfinance(yalniz_bist100=True))

            self.progress.emit("Kanıt, veri güveni ve risk/getiri birleştiriliyor...")
            result.update(v4_puanla(result, final=False))
            result.update(karar_uret(result))
            # Tek hisse ekranı da terminalle aynı canlı kanıt kilidini uygular.
            from sinyal_gecmisi import sinyal_gecmisi_oku
            from canli_kanit_kilidi import strateji_kilidi_uygula
            locked, _ = strateji_kilidi_uygula([result], sinyal_gecmisi_oku())
            result = locked[0]

            # Son kullanici karari yalniz merkezi motor tarafindan uretilir.
            from merkezi_karar_motoru import DecisionEngine, Pozisyon, karar_girdisi_sozlukten
            position = Pozisyon(**self.position) if self.position else Pozisyon()
            result.setdefault("symbol", self.symbol.replace(".IS", ""))
            result.setdefault("veri_zamani", result.get("veri_tarihi"))
            result.setdefault("veri_guncel", result.get("veri_islem_gunu_gecikmesi") == 0)
            central = DecisionEngine().karar_ver(karar_girdisi_sozlukten(result, position))
            result["merkezi_karar"] = central.as_dict()
            try:
                from karar_deposu import KararDeposu
                repo = KararDeposu(rapor_yolu())
                previous = repo.son_karar(central.sembol)
                previous_decision = previous.get("decision") if previous else None
                change_reason = None
                if previous_decision and previous_decision != central.karar:
                    change_reason = "Yeni veri ve karar kapilari sonucu karar degisti"
                decision_key = f"{central.sembol}:{central.kayit_zamani}:{central.model_surumu}"
                saved, save_result = repo.karar_ekle(decision_key, central.as_dict(), previous_decision, change_reason)
                result["karar_kaydi"] = {"basarili": saved, "id_veya_hata": save_result}
            except Exception as exc:
                # Karar kaydi sorunu analizi/taramayi durdurmaz.
                result["karar_kaydi"] = {"basarili": False, "id_veya_hata": str(exc)}

            if self.mode == "analysis":
                from mtf_grafik import grafik_olustur

                self.progress.emit("Sonuç grafiği hazırlanıyor; lütfen bekleyin...")
                output = veri_klasoru() / "output" / "grafikler"
                path = grafik_olustur(self.symbol, result, str(output))
                if path:
                    result["grafik_dosyasi"] = path
                else:
                    result["grafik_hatasi"] = (
                        "Grafik için yeterli güncel fiyat verisi alınamadı."
                    )

            if self.mode.startswith("sale:"):
                cost = float(self.mode.split(":", 1)[1])
                result.update(satis_karari_uret(result, cost))
                result["kullanici_maliyeti"] = cost
            self.finished.emit(True, result, "Tamamlandı.")
        except Exception:
            details = traceback.format_exc()
            hata_gunlugune_yaz(f"Tek hisse worker ({self.mode}, {self.symbol})", details)
            self.finished.emit(False, {}, details)


class InfoWorker(QObject):
    finished = Signal(bool, object, str)

    def __init__(self, symbol, kind):
        super().__init__()
        self.symbol = symbol
        self.kind = kind

    def run(self):
        try:
            if self.kind == "kap":
                from kap_modulu import kap_web_deneme
                result = kap_web_deneme(self.symbol, gun=30)
            elif self.kind == "research":
                from sirket_arastirmasi import sirket_arastirmasi
                result = sirket_arastirmasi(self.symbol)
            else:
                from faaliyet_raporu import faaliyet_raporu_analiz
                result = faaliyet_raporu_analiz(self.symbol)
            self.finished.emit(True, result, "Tamamlandı.")
        except Exception:
            self.finished.emit(False, {}, traceback.format_exc())


class SimpleTable(BaseAnalysisPage):
    row_selected = Signal(object)

    def __init__(self, title, subtitle="", analysis_id=None, analysis_type="Hisse"):
        slug=analysis_id or "analysis_"+"".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_")
        super().__init__(slug,title,subtitle,analysis_type=analysis_type)
        self.info=self.state_widget; self._data=pd.DataFrame(); self._raw_data=pd.DataFrame(); self._title=title
        normalized=title.casefold().replace("ı","i")
        self.simple_investor_mode=any(token in normalized for token in ("kisa vade","orta vade","50 tl","fon karar","adaylar"))
        self.table.detail_requested.connect(lambda record,_context:self.row_selected.emit(record))

    def _emit_selected_row(self, row, _column):
        record=self.table.record_for_visual_row(row)
        if record: self.row_selected.emit(record)

    def _preferred_columns(self, columns):
        title=self._title.casefold()
        if "kısa" in title:
            preferred=["Hisse","Fiyat","Güncel Fiyat","Hedef","Stop","Beklenen Süre","Model Olasılığı %","Yatırım Kararı","Karar"]
        elif "orta" in title:
            preferred=["Hisse","Fiyat","Güncel Fiyat","Hedef","Temel Puan","Risk %","Beklenen Süre","Yatırım Kararı","Karar"]
        elif "50 tl" in title:
            preferred=["Hisse","Fiyat","Güncel Fiyat","T+1 %7+ Olasılığı","T+2 %7+ Olasılığı","Likidite","Risk %","Yatırım Kararı","Karar"]
        elif "fon" in title:
            preferred=["Fon","Fon Kodu","Güncel Değer","Günlük Getiri %","Aylık Getiri %","Risk","Fon Türü","Karar"]
        elif "trade" in title or "aday" in title:
            preferred=["Hisse","Hisse / Karar","Fiyat","Güncel Fiyat","Alış Bandı","Giriş","Hedef","Stop","Yükseliş %","Olasılık / Süre","Risk/Getiri","Karar","Sonuç"]
        else:
            preferred=["Hisse","Fon","Fiyat","Güncel Fiyat","Hedef","Stop","Risk %","Yatırım Kararı","Karar","Durum"]
        selected=[]
        for name in preferred:
            if name in columns and name not in selected: selected.append(name)
        for name in columns:
            if name not in selected and len(selected)<8: selected.append(name)
        return selected[:8]

    def load(self, df):
        if df is None:
            df = pd.DataFrame()
        self._raw_data=df.reset_index(drop=True).copy()
        if self.simple_investor_mode:
            from sade_yatirimci_modu import MAIN_COLUMNS, simple_investor_frame
            normalized_title=self._title.casefold().replace("ı","i")
            analysis=("daily_trade" if "adaylar" in normalized_title else
                      "short" if "kisa" in normalized_title else
                      "medium" if "orta" in normalized_title else
                      "under50" if "50 tl" in normalized_title else "fund_analysis")
            display=simple_investor_frame(df,analysis,max_results=5)
            self._data=display.copy(); display_columns=MAIN_COLUMNS
            self.table.configure_columns(display_columns,display_columns,display_columns)
            self.table.load_frame(display,display_columns,display_columns)
            self.summary_bar.update_metrics({"Taranan":len(df),"Gösterilen":len(display),"En Güçlü":len(display),"Veri Zamanı":datetime.now().strftime("%H:%M")})
            if display.empty:
                self.info.set_empty("Bugün bu analiz için yeterince güvenilir aday bulunamadı.")
            else:
                self.info.set_ready(f"En güçlü {len(display)} sonuç gösteriliyor. Teknik ayrıntılar Detay düğmesindedir.")
            return
        self._data = self._raw_data.copy()
        compact=self._preferred_columns(list(df.columns)); standard=compact+([c for c in df.columns if c not in compact][:1])
        display_columns=standard[:9]
        self.table.configure_columns(compact,standard,display_columns); self.table.load_frame(df,display_columns,display_columns)
        self.summary_bar.update_metrics({"Taranan":len(df),"Geniş Radar":len(df),"Seçkin":"—","Güçlü":"—","Teyit":"—","Veri Zamanı":datetime.now().strftime("%H:%M")})
        if df.empty: self.info.set_empty()
        else: self.info.set_ready(f"Gösterilen sonuç: {len(df)} · Satıra çift tıklayın veya Detay düğmesini kullanın.")


class StockDetailDialog(QDialog):
    IMPORTANT_ORDER = [
        "Hisse", "Vade", "Vade Skoru", "İşlem Durumu", "Sinyal Güveni",
        "Yatırım Kararı", "Broker Aksiyon", "Fiyat", "Önerilen Alış Alt",
        "Önerilen Alış Üst", "Önerilen Satış", "Önerilen Stop", "Risk %",
        "Beklenen Getiri %", "Karar Risk/Getiri", "Model Olasılığı %",
        "AI Güven Puanı", "v4 Güven Puanı", "MTF Uyum", "Temel Puan",
        "Faaliyet Puanı", "KAP Etiket", "Veri Tarihi", "Veri Yaşı (Gün)",
        "Veri Gecikmesi (İş Günü)", "Veri Durumu", "Veri Güven Puanı",
        "Beklenen Süre", "Karar Nedenleri",
    ]

    def __init__(self, data, parent=None, show_chart=True):
        super().__init__(parent)
        self.data = dict(data)
        self.setWindowTitle(f"{data.get('Hisse', 'Hisse')} — Profesyonel Detay")
        self.setModal(True)
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(980, int(screen.width() * 0.88)), min(760, int(screen.height() * 0.88)))

        root = QVBoxLayout(self)
        symbol = str(data.get("Hisse", "HİSSE"))
        decision = str(data.get("İşlem Durumu", data.get("Yatırım Kararı", "İZLE")))
        header = QLabel(f"{symbol}   •   {decision}")
        header.setObjectName("detailHeader")
        root.addWidget(header)

        warning = QLabel("Algoritmik karar desteğidir; kesin getiri veya alım garantisi değildir.")
        warning.setObjectName("detailWarning")
        root.addWidget(warning)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)

        ordered = [key for key in self.IMPORTANT_ORDER if key in data]
        ordered.extend(key for key in data if key not in ordered)
        row = 0
        for key in ordered:
            value = data.get(key)
            if pd.isna(value) or str(value).strip() in {"", "nan", "None", "Veri yok"}:
                continue
            label = QLabel(str(key))
            label.setObjectName("detailKey")
            text = QLabel(self._format_value(value))
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text.setWordWrap(True)
            text.setObjectName("detailValue")
            grid.addWidget(label, row, 0, alignment=Qt.AlignTop)
            grid.addWidget(text, row, 1)
            row += 1

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        if show_chart:
            chart = QPushButton("TEKNİK GRAFİĞİ AÇ")
            chart.clicked.connect(self.open_chart)
            buttons.addWidget(chart)
        buttons.addStretch()
        close = QPushButton("KAPAT")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)

        self.setStyleSheet("""
            QDialog, QWidget { background:#020617; color:#e5e7eb; font-family:Arial; font-size:13px; }
            #detailHeader { background:#0c4a6e; color:white; font-size:23px; font-weight:bold; padding:14px; border-radius:8px; }
            #detailWarning { background:#422006; color:#fde68a; padding:8px; border-radius:6px; }
            #detailKey { color:#94a3b8; font-weight:bold; min-width:180px; padding:7px; }
            #detailValue { background:#0f172a; border:1px solid #1e293b; border-radius:5px; padding:7px; }
            QPushButton { background:#0369a1; color:white; padding:9px 24px; border-radius:6px; font-weight:bold; }
            QScrollArea { border:0; }
        """)

    @staticmethod
    def _format_value(value):
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    def open_chart(self):
        symbol = normalize_symbol(self.data.get("Hisse", ""))
        if not symbol:
            return
        item = {
            "price": self.data.get("Fiyat", 0),
            "ana_destek": self.data.get("Ana Destek", self.data.get("Önerilen Alış Alt", 0)),
            "ana_direnc": self.data.get("Ana Direnç", self.data.get("Önerilen Satış", 0)),
            "stop_loss": self.data.get("Önerilen Stop", self.data.get("Stop Loss", 0)),
            "hedef_1": self.data.get("Önerilen Satış", self.data.get("Hedef 1", 0)),
            "hedef_2": self.data.get("Hedef 2", 0),
            "broker_aksiyon": self.data.get("Broker Aksiyon", self.data.get("Yatırım Kararı", "")),
            "broker_skor": self.data.get("Broker Skor", self.data.get("v4 Güven Puanı", 0)),
            "mtf_karar": self.data.get("MTF Uyum", ""),
        }
        try:
            from mtf_grafik import grafik_olustur
            output = veri_klasoru() / "output" / "grafikler"
            path = grafik_olustur(symbol, item, str(output))
            if path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))
            else:
                QMessageBox.warning(self, "Grafik", "Grafik için yeterli güncel fiyat verisi alınamadı.")
        except Exception as exc:
            QMessageBox.warning(self, "Grafik", str(exc))


class SearchableTable(SimpleTable):
    def __init__(self, title, subtitle=""):
        super().__init__(title, subtitle)
        self.search = self.filter_bar.search
        self.search.setPlaceholderText("Hisse veya karar ara... (örnek: ASELS, AL, TUT)")

    def apply_filter(self, text):
        visible=self.table.apply_filter(text)
        self.info.set_ready(f"Gösterilen / toplam: {visible} / {self.table.rowCount()}")


class InvestmentTerminalPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel("BIST 30 Alış–Satış Fırsatları")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.summary = QLabel("Son rapor yükleniyor...")
        self.summary.setObjectName("terminalSummary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        cards = QHBoxLayout()
        self.metric_labels = {}
        for key, caption in [
            ("total", "TARANAN"), ("buy", "BUGÜN ALINABİLİR"),
            ("wait", "ALIM İÇİN BEKLE"), ("avoid", "RİSKLİ / UZAK DUR"),
            ("conviction", "YÜKSEK ONAY"),
        ]:
            card = QFrame()
            card.setObjectName("metricCard")
            card_layout = QVBoxLayout(card)
            caption_label = QLabel(caption)
            caption_label.setObjectName("metricCaption")
            value_label = QLabel("0")
            value_label.setObjectName("metricValue")
            card_layout.addWidget(caption_label)
            card_layout.addWidget(value_label)
            cards.addWidget(card)
            self.metric_labels[key] = value_label
        layout.addLayout(cards)
        warning = QLabel(
            "YÜKSEK ONAY bir garanti değildir. İşlemden önce güncel fiyatı, KAP bildirimini, stop seviyesini ve portföy riskini doğrula."
        )
        warning.setObjectName("riskBanner")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.tabs = QTabWidget()
        self.buy = SimpleTable(
            "Bugün Alınabilir Adaylar",
            "Yalnızca güncel veri, uygun alış bandı ve yeterli risk/getiri koşullarını geçen hisseler.",
        )
        self.wait = SimpleTable(
            "Alım İçin Beklenecek Hisseler",
            "Fiyat alış bandına gelmediği veya teknik teyit tamamlanmadığı için hemen alınmaması gerekenler.",
        )
        self.avoid = SimpleTable(
            "Riskli / Uzak Dur",
            "ALMA, veri kontrolü gerekli veya kanıtı yetersiz sonuçlar. Veri sorunu satış sinyali anlamına gelmez.",
        )
        self.onay = SimpleTable(
            "En İyi 3 Hisse Adayı — Garanti Değildir",
            "Yalnızca güncel veri, güçlü ortak teyit ve en az 1:1,8 risk/getiri koşullarını geçen en fazla 3 aday; alış, hedef ve stop birlikte gösterilir",
        )
        self.tum = SearchableTable(
            "Tüm BIST Sonuçları",
            "Herhangi bir hisseyi ara; kolon başlığına tıklayarak sırala.",
        )
        self.tabs.addTab(self.buy, "BUGÜN ALINABİLİR")
        self.tabs.addTab(self.wait, "ALIM İÇİN BEKLE")
        self.tabs.addTab(self.avoid, "RİSKLİ / UZAK DUR")
        self.tabs.addTab(self.onay, "YÜKSEK ONAY")
        self.tabs.addTab(self.tum, "TÜM BİST / ARAMA")
        self.responsive_layout=True; self.analysis_id="investment_terminal"
        layout.addWidget(self.tabs, 1)

    def show_stock_detail(self, data):
        self.tum.open_detail(data, AnalysisContext("investment_terminal").with_record(data))

    def update_summary(self, path: Path, counts, total=0, conviction=0):
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M") if path.exists() else "-"
        self.summary.setText(
            f"Son analiz: {when}   |   Bugün alınabilir: {counts[0]}   Bekle: {counts[1]}   "
            f"Riskli/uzak dur: {counts[2]}   |   Bir listenin boş olması normaldir; sistem zorla AL üretmez."
        )
        values = {
            "total": total, "buy": counts[0], "wait": counts[1],
            "avoid": counts[2], "conviction": conviction,
        }
        for key, value in values.items():
            self.metric_labels[key].setText(str(value))


class ResponsiveChartLabel(QLabel):
    CHART_HEIGHT = 460

    def __init__(self):
        super().__init__("Bir hisse kodu yazıp analiz başlatın.")
        # QPixmap ekran sürücüsüne bağlı bir kaynaktır ve bazı Windows/Qt
        # kombinasyonlarında büyük PNG'yi tekrar ölçeklerken access violation
        # oluşturabiliyor. Kaynağı CPU tarafındaki QImage olarak sakla.
        self._source_image = QImage()
        self._last_scaled_size = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(140)
        self._resize_timer.timeout.connect(self._refresh_pixmap)
        self.setAlignment(Qt.AlignCenter)
        # QLabel'in sizeHint değeri gösterilen pixmap boyutuna göre değişir. Bu
        # değer kaydırma alanına geri beslendiğinde grafik her yenilemede biraz
        # daha büyüyebiliyordu. Pixmap boyutunu yerleşim hesabından çıkarıp
        # grafik alanını sabit yükseklikte tutuyoruz.
        self.setFixedHeight(self.CHART_HEIGHT)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setObjectName("chartCanvas")

    def show_message(self, message):
        self._resize_timer.stop()
        self._source_image = QImage()
        self._last_scaled_size = None
        self.clear()
        self.setText(message)

    def load_chart(self, path):
        image = QImage(str(path))
        if image.isNull():
            self.show_message("Grafik dosyası görüntülenemedi.")
            return False
        self._source_image = image.copy()
        self._last_scaled_size = None
        self.setText("")
        QTimer.singleShot(0, self._refresh_pixmap)
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._source_image.isNull():
            self._resize_timer.start()

    def _refresh_pixmap(self):
        if self._source_image.isNull() or self.width() < 10 or self.height() < 10:
            return
        target_size = self.contentsRect().size()
        if self._last_scaled_size == target_size:
            return
        scaled_image = self._source_image.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        if scaled_image.isNull():
            return
        self.setPixmap(QPixmap.fromImage(scaled_image.copy()))
        self._last_scaled_size = target_size


class SingleAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        self.research_thread = None
        self.research_worker = None
        self.last_result = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Hisse Karar Merkezi")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        sub = QLabel(
            "Bir hissenin ne zaman alınabileceğini, hangi durumda beklenmesi gerektiğini, hedef/stop seviyelerini "
            "ve şirketin temel araştırmasını tek ekranda birleştirir."
        )
        sub.setWordWrap(True)
        sub.setObjectName("subText")
        layout.addWidget(sub)

        top = QHBoxLayout()
        self.symbol = QLineEdit()
        self.symbol.setPlaceholderText("Örnek: ASELS")
        self.symbol.returnPressed.connect(self.run)
        top.addWidget(self.symbol, 1)
        self.button = QPushButton("ALIŞ–SATIŞ KARARI VE ŞİRKETİ İNCELE")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.run)
        top.addWidget(self.button)
        layout.addLayout(top)

        control = QHBoxLayout()
        self.open_price = QLineEdit()
        self.open_price.setPlaceholderText("Sabah aracı kurum son fiyatı (örn. 71,05)")
        compare = QPushButton("SABAH FİYATINI KONTROL ET")
        compare.clicked.connect(self.check_open_price)
        control.addWidget(self.open_price, 1)
        control.addWidget(compare)
        layout.addLayout(control)

        social = QHBoxLayout()
        self.social_text = QLineEdit()
        self.social_text.setPlaceholderText("X / Telegram reklam metnini yapıştır: risk kontrolü")
        social_check = QPushButton("REKLAM RİSKİNİ KONTROL ET")
        social_check.clicked.connect(self.check_social_text)
        social.addWidget(self.social_text, 1)
        social.addWidget(social_check)
        layout.addLayout(social)

        position = QHBoxLayout()
        self.quantity = QLineEdit(); self.quantity.setPlaceholderText("Adet (bos: pozisyon yok)")
        self.average_cost = QLineEdit(); self.average_cost.setPlaceholderText("Ortalama maliyet")
        self.purchase_date = QLineEdit(); self.purchase_date.setPlaceholderText("Alis tarihi YYYY-AA-GG")
        self.previously_sold = QLineEdit(); self.previously_sold.setPlaceholderText("Once satilan adet")
        self.horizon = QComboBox(); self.horizon.addItems(["GUNLUK", "T+1", "KISA", "ORTA"])
        self.horizon.setCurrentText("KISA")
        self.max_loss = QLineEdit(); self.max_loss.setPlaceholderText("Azami kayip % (istege bagli)")
        for widget in (self.quantity, self.average_cost, self.purchase_date, self.previously_sold,
                       self.horizon, self.max_loss):
            position.addWidget(widget)
        layout.addLayout(position)

        self.status = QLabel("")
        self.status.setObjectName("subText")
        layout.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)

        self.decision_card = QLabel("KARAR KARTI\nAnaliz icin hisse kodu girin.")
        self.decision_card.setObjectName("decisionCard")
        self.decision_card.setWordWrap(True)
        self.decision_card.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.decision_card.setStyleSheet(
            "QLabel#decisionCard {background:#111c2f; color:#f7fafc; border:2px solid #2d8cff; "
            "border-radius:12px; padding:18px; font-size:16px; font-weight:600;}"
        )
        self.decision_card.setMinimumHeight(210)
        content_layout.addWidget(self.decision_card)

        self.summary = QLabel(
            "BIST 30 dışı dahil geçerli bir BIST hisse kodu girildiğinde karar, alış bandı, hedef, stop, tahmini süre ve model güveni burada gösterilir."
        )
        self.summary.setObjectName("chartSummary")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_layout.addWidget(self.summary)

        self.chart = ResponsiveChartLabel()
        content_layout.addWidget(self.chart)

        analysis_title = QLabel("Grafiğin Yazılı Teknik Değerlendirmesi")
        analysis_title.setObjectName("analysisTitle")
        content_layout.addWidget(analysis_title)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setObjectName("analysisText")
        self.result.setMinimumHeight(410)
        self.result.setPlainText(
            "Analiz tamamlandığında trend, momentum, hacim, çoklu zaman dilimi, "
            "seviyeler, kanıt gücü ve riskler burada açıklanır."
        )
        content_layout.addWidget(self.result)

        research_title = QLabel("Şirket Araştırması ve Temel Görünüm")
        research_title.setObjectName("analysisTitle")
        content_layout.addWidget(research_title)

        self.research_result = QTextEdit()
        self.research_result.setReadOnly(True)
        self.research_result.setObjectName("analysisText")
        self.research_result.setMinimumHeight(480)
        self.research_result.setPlainText(
            "Teknik karar tamamlandıktan sonra finansal eğilimler, değerleme, güçlü yönler, riskler ve senaryolar burada gösterilir."
        )
        content_layout.addWidget(self.research_result)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)

    def run(self):
        symbol = normalize_symbol(self.symbol.text())
        if not symbol:
            QMessageBox.warning(self, "Hisse", "Bir hisse kodu yaz.")
            return
        if not self.button.isEnabled():
            return

        self.button.setEnabled(False)
        self.status.setText(
            f"{symbol.replace('.IS', '')} için günlük/haftalık analiz, piyasa kontrolü ve grafik hazırlanıyor..."
        )
        self.summary.setText("Teknik sonuç ve risk seviyeleri hesaplanıyor...")
        self.chart.show_message("Grafik hazırlanıyor...")
        self.result.setPlainText(
            "Veri güncelliği, trend, momentum, hacim, tarihsel kanıt ve risk/getiri değerlendiriliyor..."
        )
        self.research_result.setPlainText("Şirketin doğrulanabilir temel verileri hazırlanıyor...")
        try:
            qty = int(self.quantity.text() or 0)
            cost = float(self.average_cost.text().replace(",", ".")) if self.average_cost.text() else None
            sold = int(self.previously_sold.text() or 0)
            max_loss = float(self.max_loss.text().replace(",", ".")) if self.max_loss.text() else None
        except ValueError:
            self.button.setEnabled(True)
            QMessageBox.warning(self, "Pozisyon", "Adet, maliyet ve azami kayip alanlarini sayi olarak girin.")
            return
        position = {"adet": qty, "ortalama_maliyet": cost, "alis_tarihi": self.purchase_date.text() or None,
                    "daha_once_satilan": sold, "vade": self.horizon.currentText(), "azami_kayip_pct": max_loss}
        self.worker = SingleWorker(symbol, "analysis", position)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.done)
        QTimer.singleShot(0, self.worker.run)

    def done(self, ok, r, message):
        self.button.setEnabled(True)
        if not ok:
            self.status.setText("Analiz yapılamadı.")
            self.summary.setText("Sonuç üretilemedi.")
            self.chart.show_message("Grafik gösterilemiyor.")
            self.result.setPlainText(message)
            return

        self.last_result = dict(r)
        central = r.get("merkezi_karar", {})
        if central:
            probability = central.get("olasilik_metni", "")
            levels = (f"Giris {central.get('giris_alt') or '-'} - {central.get('giris_ust') or '-'} TL | "
                      f"Hedef {central.get('hedef_1') or '-'} TL | Stop {central.get('stop') or '-'} TL")
            reasons = "\n".join("- " + x for x in central.get("nedenler", [])[:3]) or "- Zorunlu karar kapilari degerlendirildi."
            risks = "\n".join("- " + x for x in central.get("riskler", [])[:3]) or "- Kritik risk saptanmadi."
            changes = "\n".join("- " + x for x in central.get("degisim_kosullari", [])[:3]) or "- Yeni veriyle yeniden hesaplanir."
            dual = ""
            if not guvenli_sayi(self.quantity.text()):
                dual = (f"\nYeni alim: {central.get('yeni_alim_karari')} | "
                        f"Elinde olan icin: {central.get('elde_olan_karari')}")
            self.decision_card.setText(
                f"{central.get('sembol')}  |  {central.get('sunum_karari')}  |  {self.horizon.currentText()}\n"
                f"Gerceklesme olasiligi: {probability}{dual}\n{levels}\n"
                f"Risk/Getiri: {central.get('risk_getiri') or '-'} | Net EV: {central.get('net_ev_pct') if central.get('net_ev_pct') is not None else '-'}\n\n"
                f"Neden?\n{reasons}\n\nRisk nedir?\n{risks}\n\nNe olursa karar degisir?\n{changes}"
            )
        decision = r.get("yatirim_karari", "İZLE")
        price = guvenli_sayi(r.get("price"))
        buy_low = guvenli_sayi(r.get("onerilen_alis_alt"))
        buy_high = guvenli_sayi(r.get("onerilen_alis_ust"))
        target = guvenli_sayi(r.get("onerilen_satis"))
        stop = guvenli_sayi(r.get("onerilen_stop"))
        probability = guvenli_sayi(r.get("model_olasiligi"))
        expected_time = str(r.get("beklenen_sure", "Hesaplanamadı"))
        self.summary.setText(
            f"KARAR: {decision}   |   GÜNCEL: {price:.2f} TL   |   "
            f"ALIŞ: {buy_low:.2f}–{buy_high:.2f} TL   |   "
            f"HEDEF: {target:.2f} TL   |   STOP: {stop:.2f} TL   |   "
            f"TAHMİNİ SÜRE: {expected_time}   |   MODEL OLASILIĞI: %{probability:.0f}"
        )

        path = Path(r.get("grafik_dosyasi", ""))
        chart_ok = path.exists() and self.chart.load_chart(path)
        if not chart_ok:
            self.chart.show_message(
                r.get("grafik_hatasi", "Grafik dosyası görüntülenemedi; yazılı analiz kullanılabilir.")
            )

        symbol = normalize_symbol(self.symbol.text())
        self.result.setPlainText(teknik_degerlendirme_uret(r, symbol))
        self.status.setText(
            f"{symbol.replace('.IS', '')} birleşik analizi tamamlandı"
            + ("." if chart_ok else "; grafik oluşturulamadı, yazılı değerlendirme hazır.")
        )
        self._load_research(symbol)
        self.scroll.verticalScrollBar().setValue(0)

    def _load_research(self, symbol):
        if self.research_worker is not None:
            return
        self.research_worker = InfoWorker(symbol, "research")
        self.research_worker.finished.connect(self._research_done)
        QTimer.singleShot(0, self.research_worker.run)

    def _research_done(self, ok, result, message):
        self.research_worker = None
        if not ok:
            self.research_result.setPlainText("Şirket araştırması alınamadı:\n" + message)
            return
        self.research_result.setPlainText(result.get("report", "Araştırma verisi bulunamadı."))
        coverage = result.get("data_completeness", 0)
        self.status.setText(self.status.text() + f" Şirket verisi kapsamı: %{coverage}.")

    def check_open_price(self):
        if not self.last_result:
            QMessageBox.information(self, "Sabah kontrolü", "Önce tek hisse analizini tamamla.")
            return
        try:
            price = float(self.open_price.text().replace(",", "."))
        except ValueError:
            QMessageBox.warning(self, "Sabah kontrolü", "Aracı kurumda gördüğün son fiyatı sayı olarak yaz.")
            return
        plan = gun_sonu_plani([self.last_result])
        if plan.empty:
            QMessageBox.information(self, "Sabah kontrolü", "Bu sonuç işlem planına uygun bir aday değil; yeni alım için izleme modunda kal.")
            return
        check = sabah_fiyat_kontrolu(plan, {str(plan.iloc[0]["Hisse"]): price})
        result = check.iloc[0]
        QMessageBox.information(
            self, "Sabah fiyat kontrolü",
            f"Kapanış: {result['Kapanış Fiyatı']:.2f} TL\nSon fiyat: {result['Sabah Son Fiyat']:.2f} TL\n\n{result['Sabah Kararı']}"
        )

    def check_social_text(self):
        result = sosyal_medya_risk_analizi(self.social_text.text())
        QMessageBox.information(
            self, "Reklam / sosyal medya risk kontrolü",
            f"Risk puanı: {result['sosyal_medya_risk_puani']}/100\n"
            f"İşaretler: {result['sosyal_medya_bayraklari']}\n\n{result['sosyal_medya_sonuc']}"
        )


class SalePage(QWidget):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Satış Kararı")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        top = QHBoxLayout()
        self.symbol = QLineEdit()
        self.symbol.setPlaceholderText("Hisse: ASELS")
        self.cost = QLineEdit()
        self.cost.setPlaceholderText("Maliyet: 178,50")
        self.button = QPushButton("HESAPLA")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.run)
        top.addWidget(self.symbol)
        top.addWidget(self.cost)
        top.addWidget(self.button)
        layout.addLayout(top)
        self.status = QLabel("")
        layout.addWidget(self.status)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, 1)

    def run(self):
        symbol = normalize_symbol(self.symbol.text())
        if not symbol:
            QMessageBox.warning(self, "Hisse", "Bir hisse kodu yaz.")
            return
        if not self.button.isEnabled():
            return
        try:
            cost = float(self.cost.text().replace(",", "."))
            if cost <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Maliyet", "Geçerli maliyet yaz.")
            return
        self.button.setEnabled(False)
        self.status.setText("Satış kararı hesaplanıyor...")
        self.worker = SingleWorker(symbol, f"sale:{cost}")
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.done)
        QTimer.singleShot(0, self.worker.run)

    def done(self, ok, r, message):
        self.button.setEnabled(True)
        if not ok:
            self.status.setText("Satış kararı hesaplanamadı; uygulama çalışmaya devam ediyor.")
            self.result.setPlainText(message)
            return
        price = guvenli_sayi(r.get("price"))
        cost = guvenli_sayi(r.get("kullanici_maliyeti"))
        pnl = guvenli_sayi(r.get("kar_zarar_yuzde"))
        target = guvenli_sayi(r.get("onerilen_satis"))
        stop = guvenli_sayi(r.get("yeni_stop"))
        realize = guvenli_sayi(r.get("kar_realizasyon_orani"))
        lines = [
            f"KARAR: {r.get('satis_karari', '-')}",
            f"GÜNCEL FİYAT: {price:.2f} TL",
            f"MALİYET: {cost:.2f} TL",
            f"KÂR/ZARAR: %{pnl:.2f}",
            f"MODEL HEDEFİ: {target:.2f} TL",
            f"YENİ STOP: {stop:.2f} TL",
            f"KÂR REALİZASYONU: %{realize:.0f}",
            "",
            f"NEDEN: {r.get('satis_nedeni', '-')}",
            "",
            "Bu sonuç teknik model senaryosudur; nihai karar kullanıcıya aittir.",
        ]
        self.result.setPlainText("\n".join(lines))
        self.status.setText("Tamamlandı.")


class SelectedInfoPage(QWidget):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.thread = None
        self.worker = None
        labels = {
            "kap": "KAP Analizi",
            "activity": "Faaliyet Raporu Analizi",
            "research": "Doğrulanmış Şirket Araştırması",
        }
        label = labels.get(kind, "Şirket Araştırması")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel(label)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        sub = QLabel("Yalnızca seçtiğin hisse incelenir; toplu taramayı yavaşlatmaz.")
        sub.setObjectName("subText")
        if kind == "research":
            sub.setText(
                "Beş yıllık finansal eğilim, değerleme, güçlü yön, risk ve senaryoları tek raporda gösterir. "
                "Eksik veri uydurulmaz ve bu rapor teknik işlem kararını değiştirmez."
            )
            sub.setWordWrap(True)
        layout.addWidget(sub)
        top = QHBoxLayout()
        self.symbol = QLineEdit()
        self.symbol.setPlaceholderText("Örnek: ASELS")
        self.button = QPushButton("İNCELE")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.run)
        top.addWidget(self.symbol, 1)
        top.addWidget(self.button)
        layout.addLayout(top)
        self.status = QLabel("")
        layout.addWidget(self.status)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        layout.addWidget(self.result, 1)

    def run(self):
        symbol = normalize_symbol(self.symbol.text())
        if not symbol:
            return
        if not self.button.isEnabled():
            return
        self.button.setEnabled(False)
        self.status.setText("İnceleniyor...")
        self.worker = InfoWorker(symbol, self.kind)
        self.worker.finished.connect(self.done)
        QTimer.singleShot(0, self.worker.run)

    def done(self, ok, result, message):
        self.button.setEnabled(True)
        if not ok:
            self.result.setPlainText(message)
            return
        if self.kind == "research" and result.get("report"):
            self.result.setPlainText(result["report"])
            self.status.setText(f"Tamamlandı. Veri kapsamı: %{result.get('data_completeness', 0)}")
            return
        lines = []
        for key, value in result.items():
            lines.append(f"{str(key).replace('_', ' ').title()}: {value}")
        self.result.setPlainText("\n".join(lines))
        self.status.setText("Tamamlandı.")


class TrackPage(QWidget):
    def __init__(self):
        super().__init__()
        self.responsive_layout=True; self.analysis_id="portfolio"; self._detail_window=AnalysisDetailWindow(self)
        from takip_modulu import takip_listesini_oku, takip_listesini_yaz, takip_fiyatlarini_getir
        self.read_list = takip_listesini_oku
        self.write_list = takip_listesini_yaz
        self.get_prices = takip_fiyatlarini_getir
        from portfoy_kayitlari import load_positions
        self.position_path=veri_klasoru()/"portfoy_kayitlari.json"; self.positions=load_positions(self.position_path)
        self.symbols = self.read_list()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Takip Listem")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        top = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Hisse ekle: ASELS")
        add = QPushButton("EKLE")
        add.clicked.connect(self.add)
        refresh = QPushButton("FİYATLARI YENİLE")
        refresh.setObjectName("primary")
        refresh.clicked.connect(self.refresh)
        top.addWidget(self.input, 1)
        top.addWidget(add)
        top.addWidget(refresh)
        layout.addLayout(top)
        position_row=QHBoxLayout()
        self.position_symbol=QLineEdit(); self.position_symbol.setPlaceholderText("Portföy hissesi: ASELS")
        self.position_quantity=QLineEdit(); self.position_quantity.setPlaceholderText("Adet")
        self.position_cost=QLineEdit(); self.position_cost.setPlaceholderText("Alış fiyatı")
        self.position_date=QLineEdit(datetime.now().strftime("%Y-%m-%d")); self.position_date.setPlaceholderText("Alış tarihi YYYY-AA-GG")
        self.position_target=QLineEdit(); self.position_target.setPlaceholderText("Hedef (isteğe bağlı)")
        self.position_stop=QLineEdit(); self.position_stop.setPlaceholderText("Stop (isteğe bağlı)")
        save_position=QPushButton("PORTFÖYE KAYDET"); save_position.clicked.connect(self.save_position)
        for widget in (self.position_symbol,self.position_quantity,self.position_cost,self.position_date,self.position_target,self.position_stop,save_position): position_row.addWidget(widget)
        layout.addLayout(position_row)
        self.table = ResponsiveResultTable("portfolio")
        self.table.set_context(AnalysisContext("portfolio",analysis_type="Hisse"))
        self.table.detail_requested.connect(self._detail_window.show_record)
        layout.addWidget(self.table, 1)
        self.show_symbols()

    def add(self):
        symbol = normalize_symbol(self.input.text())
        if symbol and symbol not in self.symbols:
            self.symbols.append(symbol)
            self.write_list(self.symbols)
        self.input.clear()
        self.show_symbols()

    def show_symbols(self):
        all_symbols=sorted(set(self.symbols)|{p.symbol+".IS" for p in self.positions})
        df = pd.DataFrame({"Hisse": [s.replace(".IS", "") for s in all_symbols]})
        self.load(df)

    def refresh(self):
        self.load(self.get_prices(self.symbols))

    def remove(self, symbol):
        symbol = normalize_symbol(symbol)
        if not symbol or symbol not in self.symbols:
            return
        self.symbols.remove(symbol)
        self.write_list(self.symbols)
        from portfoy_kayitlari import load_positions,remove_position
        remove_position(self.position_path,symbol); self.positions=load_positions(self.position_path)
        self.show_symbols()

    def save_position(self):
        from portfoy_kayitlari import PortfolioPosition,load_positions,upsert_position
        try:
            symbol=normalize_symbol(self.position_symbol.text()).replace(".IS","")
            def optional(widget):
                text=widget.text().strip().replace(",","."); return float(text) if text else None
            position=PortfolioPosition(symbol,int(self.position_quantity.text()),float(self.position_cost.text().replace(",",".")),
                                       self.position_date.text().strip(),optional(self.position_target),optional(self.position_stop))
            upsert_position(self.position_path,position); self.positions=load_positions(self.position_path)
            normalized=normalize_symbol(symbol)
            if normalized not in self.symbols: self.symbols.append(normalized); self.write_list(self.symbols)
            self.position_symbol.clear(); self.position_quantity.clear(); self.position_cost.clear(); self.position_target.clear(); self.position_stop.clear()
            self.refresh()
        except (ValueError,TypeError) as exc:
            QMessageBox.warning(self,"Portföy kaydı","Hisse, pozitif adet, alış fiyatı ve YYYY-AA-GG tarihi girin.\n"+str(exc))

    def load(self, df):
        from portfoy_kayitlari import portfolio_decision
        track_columns=["Hisse","Karar","Güncel fiyat","Günlük değişim","Alış fiyatı","Kâr/zarar","Hedef","Stop","Hedefe tahmini süre","Son fiyat zamanı"]
        source=pd.DataFrame() if df is None else df.reset_index(drop=True).copy(); by_symbol={p.symbol.upper():p for p in self.positions}; rows=[]
        for record in source.to_dict("records"):
            symbol=str(record.get("Hisse","")).replace(".IS","").upper(); position=by_symbol.get(symbol)
            current=record.get("Son Fiyat",record.get("Güncel Fiyat")); result=portfolio_decision(position,current) if position else {"decision":"BEKLE","profit_pct":None,"reason":"Takip listesinde; yeni değerlendirme bekleniyor."}
            if position:
                decision=result["decision"]; buy_price=position.buy_price; pnl=result["profit_pct"]
                target=position.target; stop=position.stop
            else:
                decision="BEKLE" if current is not None else "VERİ YETERSİZ"; buy_price=None; pnl=None; target=None; stop=None
            daily=record.get("Günlük değişim",record.get("Günlük Değişim %",record.get("Değişim %")))
            timestamp=record.get("Son fiyat zamanı",record.get("Veri Zamanı",record.get("Fiyat Zamanı","—")))
            rows.append({"Hisse":symbol,"Karar":decision,"Güncel fiyat":current if current is not None else "Fiyat alınamadı",
                         "Günlük değişim":daily if daily is not None else "—","Alış fiyatı":buy_price if buy_price is not None else "—",
                         "Kâr/zarar":f"%{pnl:.2f}" if pnl is not None else "—","Hedef":target if target is not None else "—",
                         "Stop":stop if stop is not None else "—","Hedefe tahmini süre":"2–4 hafta" if position else "Hesaplanamadı",
                         "Son fiyat zamanı":timestamp})
        display=pd.DataFrame(rows,columns=track_columns)
        self.table.configure_columns(track_columns,track_columns,track_columns); self.table.load_frame(display,track_columns,track_columns)
    def resizeEvent(self,event):
        super().resizeEvent(event); self.table.apply_profile(profile_for_width(self.width()))


class FundWorker(QObject):
    finished = Signal(bool, object, str)

    def __init__(self, max_risk=7, capital=0):
        super().__init__()
        self.max_risk = max_risk
        self.capital = capital

    def run(self):
        try:
            from fon_analizi import en_iyi_fonlari_sec
            frame, source, selection = en_iyi_fonlari_sec(self.max_risk, self.capital, adet=3)
            self.finished.emit(True, {"frame": frame, "selection": selection}, source)
        except Exception:
            self.finished.emit(False, pd.DataFrame(), traceback.format_exc())


class FundAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.responsive_layout=True; self.analysis_id="fund_analysis"
        self.thread = None
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel("Fon Karar Merkezi")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        warning = QLabel(
            "TEFAS'ta işlem gören fonları aynı kategori, çok dönemli momentum ve riskle karşılaştırır. "
            "%20–30 aylık getiri garanti edilmez; yalnızca yüksek getiri potansiyeli taşıyan riskli adaylar işaretlenir."
        )
        warning.setObjectName("riskBanner")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        controls = QHBoxLayout()
        self.max_risk = QLineEdit("7")
        self.max_risk.setPlaceholderText("Azami risk: 1–7")
        self.max_risk.setMaximumWidth(170)
        self.capital = QLineEdit("50000")
        self.capital.setPlaceholderText("Yatırılacak tutar (TL)")
        self.capital.setMaximumWidth(220)
        self.button = QPushButton("TEFAS FONLARINI TARA")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.run)
        controls.addWidget(self.max_risk)
        controls.addWidget(self.capital)
        controls.addWidget(self.button)
        controls.addStretch()
        layout.addLayout(controls)
        self.status = QLabel("Tarama başlatılmadı. Risk 7 tüm uygun fonları kapsar; daha düşük değer daha temkinlidir.")
        self.status.setObjectName("subText")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.selection = QTextEdit()
        self.selection.setReadOnly(True)
        self.selection.setObjectName("analysisText")
        self.selection.setMinimumHeight(64); self.selection.setMaximumHeight(105)
        self.selection.setPlainText(
            "Tarama sonunda şartları geçen en fazla 3 risk-ayarlı fon adayı; kurum, kademeli alım, 2-3 aylık hedef ve çıkış koşuluyla gösterilir."
        )
        layout.addWidget(self.selection)
        self.table = SearchableTable(
            "Yüksek Getiri ve Fon Karar Adayları",
            "Tablo puana göre sıralanır. Bir aylık yükselişi aşırı hızlanan fonlarda 'kovalama' uyarısı verilir.",
        )
        self.table.table.set_context(AnalysisContext("fund_analysis",analysis_type="Fon"))
        layout.addWidget(self.table, 1)

    def run(self):
        if not self.button.isEnabled():
            return
        try:
            max_risk = int(self.max_risk.text().strip())
            if not 1 <= max_risk <= 7:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Risk", "Azami risk değerini 1 ile 7 arasında yazın.")
            return
        try:
            capital = float(self.capital.text().replace(".", "").replace(",", "."))
            if capital <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Tutar", "Yatırılacak tutarı pozitif bir sayı olarak yazın.")
            return
        self.button.setEnabled(False)
        self.status.setText("TEFAS fonları alınıyor ve aynı kategoride karşılaştırılıyor...")
        self.worker = FundWorker(max_risk, capital)
        self.worker.finished.connect(self.done)
        QTimer.singleShot(0, self.worker.run)

    def done(self, ok, payload, message):
        self.button.setEnabled(True)
        if not ok:
            self.status.setText("Fon taraması yapılamadı. Eski sonuç karar olarak kullanılmadı.")
            QMessageBox.warning(self, "Fon taraması", message)
            return
        frame = payload.get("frame", pd.DataFrame())
        selection = payload.get("selection", {})
        self.table.load(frame)
        self.selection.setPlainText(selection.get("rapor", "Tek fon sonucu üretilemedi."))
        strong = 0 if frame.empty else int(frame["20%+ Uç Senaryo"].astype(str).eq("VAR").sum())
        self.status.setText(f"Kaynak: {message} | Uygun fon: {len(frame)} | 20%+ uç senaryo adayı: {strong}")

    def show_detail(self, data):
        self.table.open_detail(data, AnalysisContext("fund_analysis",analysis_type="Fon").with_record(data))


class DailyTradeWorker(QObject):
    finished = Signal(bool, object, str)
    progress = Signal(str)
    structured_progress = Signal(int, int, str)

    def __init__(self, interval, account, risk, min_rr, confirmed_only, symbols=None):
        super().__init__()
        self.interval, self.account, self.risk = interval, account, risk
        self.min_rr, self.confirmed_only = min_rr, confirmed_only
        self.symbols = list(symbols) if symbols is not None else None

    def run(self):
        try:
            from bist_evreni import kap_menkul_turleri, son_evren_durumu, tum_bist_hisseleri
            from gunluk_trade_motoru import gunluk_trade_analiz
            rows, attempted, received, unavailable = [], 0, 0, 0
            symbols = list(self.symbols) if self.symbols is not None else tum_bist_hisseleri()
            for index, symbol in enumerate(symbols, 1):
                if QThread.currentThread().isInterruptionRequested():
                    break
                if index == 1 or index == len(symbols) or index % 5 == 0:
                    self.progress.emit(f"{index}/{len(symbols)} {symbol.replace('.IS','')} inceleniyor...")
                    self.structured_progress.emit(index, len(symbols), "Günlük Trade · Tüm Aktif BIST")
                attempted += 1
                try:
                    row = gunluk_trade_analiz(
                        symbol, interval=self.interval, hesap_buyuklugu=self.account or None,
                        risk_yuzdesi=self.risk, min_risk_getiri=self.min_rr,
                        sadece_teyitli=self.confirmed_only,
                    )
                except Exception:
                    unavailable += 1
                    hata_gunlugune_yaz(f"Günlük Trade sembol hatası: {symbol}", traceback.format_exc())
                    continue
                if row.get("Neden Kodu") in {"MISSING_PRICE_DATA", "SYMBOL_MAPPING_FAILED"}: unavailable += 1
                else: received += 1
                if not self.confirmed_only or row.get("Sonuç") == "AL ADAYI":
                    rows.append(row)
                QThread.msleep(2)  # Ana Qt olay döngüsüne düzenli çalışma fırsatı ver.
            warning = son_evren_durumu().get("warning", "")
            insufficient_count = sum(str(row.get("Sonuç")) == "VERİ YETERSİZ" for row in rows)
            analysis_ok = max(0, received - insufficient_count)
            message = (f"Aktif BIST: {len(symbols)} | Denenen: {attempted} | Veri alınan: {received} | "
                       f"Analiz tamamlanan: {analysis_ok} | Veri alınamayan: {unavailable} | Gösterilen: {len(rows)}")
            strong_count = sum(str(row.get("Sonuç")) == "AL ADAYI" for row in rows)
            watch_count = sum(str(row.get("Sonuç")) not in {"AL ADAYI", "VERİ YETERSİZ"} for row in rows)
            diagnostics = ScanDiagnostics(
                strategy="daily_trade", symbols_total=len(symbols), data_ok=received,
                analysis_ok=analysis_ok, data_quality_rejected=insufficient_count,
                strong_candidates=strong_count, watch_candidates=watch_count,
                errors=unavailable,
            )
            write_scan_diagnostics(diagnostics)
            if received < max(1, len(symbols) // 2):
                message += " | Veri kaynağı problemi nedeniyle sonuç güvenilir değil"
            elif strong_count == 0 and watch_count:
                message += " | Güçlü AL adayı yok; en iyi takip adayları gösteriliyor"
            elif strong_count == 0:
                message += f" | Güçlü aday yok; {insufficient_count} sembolde intraday geçmiş yetersiz, günlük rapor fallback'i kullanılacak"
            if warning: message += " | UYARI: " + warning
            self.finished.emit(True, pd.DataFrame(rows), message)
        except Exception:
            self.finished.emit(False, pd.DataFrame(), traceback.format_exc())


class DailyTradePage(QWidget):
    """Gecikme ve kanıt durumunu gizlemeden sunan günlük trade karar-destek sayfası."""
    central_finished = Signal(str, bool, object, str)
    central_progress = Signal(str, int, int, str)

    def __init__(self):
        super().__init__()
        self.responsive_layout = True
        self.analysis_id = "daily_trade"
        self.setObjectName("dailyTradePage")
        self.thread = None
        self.worker = None
        self.results = pd.DataFrame()
        self.report_fallback = pd.DataFrame()
        self._detail_records = []
        self.setMinimumWidth(640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9); layout.setSpacing(6)
        header = QFrame(); header.setObjectName("dailyHeader")
        header_layout = QVBoxLayout(header); header_layout.setContentsMargins(16, 12, 16, 12)
        self.eyebrow = QLabel("YÜKSEK HAREKET RADARI"); self.eyebrow.setObjectName("eyebrow")
        heading = QLabel("Borsa Analiz Pro MAX"); heading.setObjectName("dailyHeading")
        subtitle = QLabel("Günlük Trade · Tüm Aktif BIST · Karar destek ve kâğıt işlem ekranı"); subtitle.setObjectName("dailySubtitle")
        header_layout.addWidget(self.eyebrow); header_layout.addWidget(heading); header_layout.addWidget(subtitle)
        nav = QHBoxLayout(); nav.addStretch(); self.nav_buttons=[]
        for caption, target in (("Günlük Trade", self), ("Kısa Vade", None), ("Orta Vade", None), ("Tek Hisse", None)):
            button = QPushButton(caption); button.setObjectName("dailyNavActive" if target is self else "dailyNav")
            if caption == "Kısa Vade": button.clicked.connect(lambda: self.window().pages.setCurrentWidget(self.window().short_term))
            elif caption == "Orta Vade": button.clicked.connect(lambda: self.window().pages.setCurrentWidget(self.window().medium_term))
            elif caption == "Tek Hisse": button.clicked.connect(lambda: self.window().pages.setCurrentWidget(self.window().single))
            nav.addWidget(button); self.nav_buttons.append(button)
        header_layout.addLayout(nav); layout.addWidget(header)
        warning = QLabel(
            "Karar-destek ve kâğıt işlem ekranıdır; gerçek emir göndermez. Yahoo intraday veri ücretsizdir, "
            "gecikmesi garanti edilmez. Geçmiş performans gelecekteki sonucu garanti etmez."
        )
        warning.setWordWrap(True)
        warning.setObjectName("riskBanner")
        layout.addWidget(warning)
        summary = QHBoxLayout(); summary.setSpacing(10)
        self.regime_summary = QLabel("PİYASA REJİMİ\nUNKNOWN")
        self.candidate_summary = QLabel("UYGUN ADAY\n0")
        self.data_summary = QLabel("VERİ DURUMU\nHenüz güncellenmedi")
        for widget in (self.regime_summary, self.candidate_summary, self.data_summary):
            card = QFrame(); card.setObjectName("dailyMetricCard")
            box = QVBoxLayout(card); box.setContentsMargins(14, 10, 14, 10)
            widget.setObjectName("dailyMetricValue"); widget.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            box.addWidget(widget); summary.addWidget(card, 1)
        layout.addLayout(summary)
        controls = QHBoxLayout()
        self.scan_button = QPushButton("TÜM BIST GÜNLÜK TRADE TARAMASINI BAŞLAT")
        self.scan_button.setObjectName("primary")
        self.interval = QComboBox()
        self.interval.addItems(["15m", "5m"])
        self.account = QDoubleSpinBox(); self.account.setRange(0, 100_000_000); self.account.setValue(100_000); self.account.setSuffix(" TL")
        self.risk = QDoubleSpinBox(); self.risk.setRange(0.1, 1.0); self.risk.setValue(0.5); self.risk.setSingleStep(0.1); self.risk.setSuffix(" % risk")
        self.min_rr = QDoubleSpinBox(); self.min_rr.setRange(1.0, 5.0); self.min_rr.setValue(1.8); self.min_rr.setSingleStep(0.1); self.min_rr.setPrefix("Min R/G ")
        self.confirmed = QCheckBox("Yalnızca teyitli sinyaller")
        self.cancel_button = QPushButton("İPTAL"); self.cancel_button.clicked.connect(self.cancel_scan)
        for widget in (self.scan_button, self.cancel_button, self.interval, self.account, self.risk, self.min_rr, self.confirmed):
            controls.addWidget(widget)
        self.scan_button.setText("Taramayı yenile")
        self.scan_button.setVisible(False)
        self.options_button = QPushButton("Filtreler")
        self.options_button.setObjectName("dailyNav")
        self.options_button.clicked.connect(self._toggle_options)
        controls.addWidget(self.options_button)
        for widget in (self.cancel_button, self.interval, self.account, self.risk, self.min_rr, self.confirmed):
            widget.setVisible(False)
        layout.addLayout(controls)
        self.status = QLabel("Henüz tarama yapılmadı.")
        self.status.setObjectName("subText")
        layout.addWidget(self.status)
        self.table = SimpleTable("Adaylar", "Uygun aday yoksa liste boş bırakılır.")
        self.table.info.hide()
        self.table.table.cellClicked.connect(self._show_inline_detail)
        layout.addWidget(self.table, 1)
        self.detail = QLabel("Bir aday seçildiğinde net beklenti, risk/getiri, göreceli güç, RVOL ve olasılık kanıtı burada gösterilir.")
        self.detail.setObjectName("analysisText")
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(52); self.detail.setMaximumHeight(72); self.detail.hide()
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.detail)
        self.paper_button = QPushButton("SEÇİLİ SATIRI KÂĞIT İŞLEM OLARAK KAYDET")
        self.paper_button.clicked.connect(self.save_selected)
        layout.addWidget(self.paper_button)
        self.scan_button.clicked.connect(self.start_scan)

    def _toggle_options(self):
        visible = not self.interval.isVisible()
        for widget in (self.cancel_button, self.interval, self.account, self.risk, self.min_rr, self.confirmed):
            widget.setVisible(visible)

    def start_scan(self, run_id=None, symbols=None):
        if self.thread and self.thread.isRunning():
            return False
        self._central_run_id = run_id
        self.scan_button.setEnabled(False)
        self.status.setText("Aktif BIST evreni tamamlanmış intraday mumlarla taranıyor...")
        self.thread = QThread(self)
        self.worker = DailyTradeWorker(self.interval.currentText(), self.account.value(), self.risk.value(),
                                       self.min_rr.value(), self.confirmed.isChecked(), symbols=symbols)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.status.setText)
        self.worker.structured_progress.connect(
            lambda done, total, message: self.central_progress.emit(run_id or "", done, total, message))
        self.worker.finished.connect(self.scan_done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        return True

    def _thread_finished(self):
        self.worker = None
        self.thread = None

    def cancel_scan(self):
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self.status.setText("Tarama güvenli biçimde durduruluyor…")

    def scan_done(self, ok, frame, message):
        self.scan_button.setEnabled(True)
        self.results = frame if ok else pd.DataFrame()
        display = self.results[self.results.get("Sonuç", pd.Series(dtype=str)).ne("VERİ YETERSİZ")].copy() if not self.results.empty else self.results
        if not display.empty:
            priority = {"AL ADAYI": 3, "TEYİT BEKLE": 2, "FİYAT KOVALAMA": 1, "İŞLEM YOK": 0}
            display["_öncelik"] = display["Sonuç"].map(priority).fillna(0)
            display["_pot"] = pd.to_numeric(display.get("Hedef Potansiyeli %", pd.Series(0, index=display.index)), errors="coerce").fillna(0)
            display["_rr"] = pd.to_numeric(display.get("Risk/Getiri", pd.Series(0, index=display.index)), errors="coerce").fillna(0)
            selected = display.sort_values(["_öncelik", "_pot", "_rr"], ascending=False).head(5)
            self._detail_records = selected.drop(columns=["_öncelik", "_pot", "_rr"], errors="ignore").to_dict("records")
            display = pd.DataFrame(self._detail_records)
        if display.empty and not self.report_fallback.empty:
            self._detail_records = self.report_fallback.head(5).to_dict("records")
            display = pd.DataFrame(self._detail_records)
        elif display.empty:
            self._detail_records = []
        self.table.load(display)
        self._detail_records=self.table._data.to_dict("records")
        self._update_summary(display)
        self._resize_trade_columns()
        if not ok:
            self.status.setText("Tarama hatası: " + message.splitlines()[-1])
        elif display.empty:
            self.status.setText("Bugün ölçütleri geçen aday bulunamadı. Veri yetersiz/gecikmeli sonuçlardan işlem üretilmedi.")
        elif "Karar" in display.columns and display["Karar"].astype(str).eq("GÜNCEL FİYATLA DOĞRULA").any():
            self.status.setText("Canlı intraday veri alınamadı. Son güvenilir günlük analiz gösteriliyor; işlem öncesinde güncel fiyatı doğrulayın.")
        else:
            counts = pd.Series([item.get("Sonuç", item.get("Karar", "—")) for item in self._detail_records]).value_counts().to_dict()
            self.status.setText(f"Tarama tamamlandı: {counts} | Satıra tıklayarak ayrıntıları inceleyin.")
        run_id = getattr(self, "_central_run_id", None)
        if run_id:
            tagged = tag_analysis_result(self.results, "daily_trade", run_id)
            self.results = tagged
            self.central_finished.emit(run_id, ok, tagged, message)
            self._central_run_id = None

    @staticmethod
    def _compact_display(records):
        def number(value):
            try:
                result = float(value)
                return result if pd.notna(result) else 0.0
            except (TypeError, ValueError):
                return 0.0
        rows = []
        for record in records:
            probability = record.get("Hedef Önce Olasılığı %", "Yetersiz örnek")
            horizon = int(record.get("Olasılık Ufku — İşlem Günü", 3) or 3)
            probability_text = str(probability) if "Yetersiz" in str(probability) else str(probability).replace(".0", "")
            rows.append({
                "Hisse / Karar": f"{record.get('Hisse', '-')}\n{record.get('Sonuç', '-')}",
                "Alış Bandı": f"{number(record.get('Alış Alt')):.2f} – {number(record.get('Alış Üst')):.2f}",
                "Hedef": f"{number(record.get('Hedef')):.2f}", "Stop": f"{number(record.get('Stop')):.2f}",
                "Yükseliş %": f"%{number(record.get('Hedef Potansiyeli %')):.1f}",
                "Olasılık / Süre": f"{probability_text}\n{horizon} gün içinde",
            })
        return pd.DataFrame(rows, columns=["Hisse / Karar", "Alış Bandı", "Hedef", "Stop", "Yükseliş %", "Olasılık / Süre"])

    def _show_inline_detail(self, row, _column=0):
        if not 0 <= row < len(self._detail_records):
            return
        record = self._detail_records[row]
        reasons = record.get("Neden AL?", ())
        if isinstance(reasons, str):
            reasons = (reasons,)
        changes = record.get("Karar Ne Zaman Değişir?", ())
        if isinstance(changes, str):
            changes = (changes,)
        reason_text = "\n".join(f"• {item}" for item in reasons) or f"• {record.get('Kısa Neden', 'Açıklama bulunamadı.')}"
        change_text = "\n".join(f"• {item}" for item in changes) or "• Yeni fiyat ve hacim verisiyle yeniden değerlendirilir."
        self.detail.setText(
            f"{record.get('Hisse', '-')} — {record.get('Karar', '—')}\n"
            f"Beklenen süre: {record.get('Beklenen süre', 'Güvenilir şekilde hesaplanamadı')}\n"
            f"Güven düzeyi: {record.get('Güven düzeyi', 'Ölçülemedi')}\n\n"
            f"Neden bu karar?\n{reason_text}\n\n"
            f"Ana risk\n• {record.get('Ana Risk', 'Canlı fiyat işlem öncesinde doğrulanmalı.')}\n\n"
            f"Karar ne zaman değişir?\n{change_text}"
        )

    def _update_summary(self, display):
        source = self._detail_records
        regimes = {str(item.get("Piyasa Rejimi", "UNKNOWN")) for item in source}
        regime = next(iter(regimes)) if len(regimes) == 1 else ("KARMA" if regimes else "UNKNOWN")
        suitable = sum(str(item.get("Sonuç")) == "AL ADAYI" for item in source)
        times = [str(item.get("Veri Zamanı")) for item in source if item.get("Veri Zamanı")]
        stale = any(str(item.get("Tazelik", "")).upper() == "ESKİ" for item in source)
        self.regime_summary.setText(f"PİYASA REJİMİ\n{regime}")
        self.candidate_summary.setText(f"UYGUN ADAY\n{suitable}")
        self.data_summary.setText(f"VERİ DURUMU\n{'ESKİ' if stale else 'GÜNCEL' if times else 'VERİ YOK'} · {max(times) if times else '—'}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact=profile_for_width(self.width())==PROFILE_COMPACT
        self.eyebrow.setVisible(not compact)
        for button in self.nav_buttons: button.setVisible(not compact)
        self.table.set_view_profile(profile_for_width(self.width()))
        self._resize_trade_columns()

    def _resize_trade_columns(self):
        table = self.table.table
        if table.columnCount() != 6:
            return
        width = max(600, table.viewport().width() - 10)
        ratios = (.20, .20, .13, .13, .14, .20)
        table.horizontalHeader().setMinimumSectionSize(40)
        for column, ratio in enumerate(ratios):
            table.setColumnHidden(column, False)
            table.setColumnWidth(column, int(width * ratio))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.setWordWrap(True)
        table.verticalHeader().setDefaultSectionSize(44)

    def _selected_record(self):
        row = self.table.table.currentRow()
        if row < 0:
            return None
        marker = self.table.table.item(row, 0)
        source_row = marker.data(Qt.UserRole) if marker else row
        return self.table._data.iloc[int(source_row)].to_dict()

    def save_selected(self):
        record = self._selected_record()
        if not record:
            QMessageBox.information(self, "Kâğıt İşlem", "Önce bir sonuç satırı seçin.")
            return
        from gunluk_trade_motoru import kagit_islem_kaydet
        path = veri_klasoru() / "gunluk_trade" / "kagit_islemler.jsonl"
        digest = kagit_islem_kaydet(record, path)
        QMessageBox.information(self, "Kâğıt İşlem", f"Değiştirilemez kayıt eklendi.\n{path}\nKayıt: {digest[:12]}")

    def show_detail(self, data):
        StockDetailDialog(data, self, show_chart=False).exec()


class HomePage(QWidget):
    trade_requested = Signal()

    def __init__(self):
        super().__init__()
        self.responsive_layout=True; self.analysis_id="daily_trade"
        self.responsive_layout=True; self.analysis_id="home"
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(10)
        top = QFrame(); top.setObjectName("topStrip"); top_box = QHBoxLayout(top)
        self.index_value = QLabel("BIST 100\nVeri bekleniyor"); self.index_value.setObjectName("topMetric")
        self.market = QLabel("PİYASA DURUMU\nVERİ BEKLENİYOR"); self.market.setObjectName("topMetric")
        self.source = QLabel("VERİ KAYNAĞI\nGecikmeli (15 dk)"); self.source.setObjectName("topMetric")
        self.clock = QLabel(datetime.now().strftime("%d.%m.%Y\n%H:%M")); self.clock.setObjectName("topMetric")
        for widget in (self.index_value, self.market, self.source): top_box.addWidget(widget, 1)
        top_box.addStretch(); top_box.addWidget(self.clock); layout.addWidget(top)
        self.scan_status = QLabel("Tarama hazır — üstteki düğmeyle tüm hisse analizlerini başlatın.")
        self.scan_status.setObjectName("subText"); self.scan_status.setWordWrap(True); layout.addWidget(self.scan_status)
        self.scan_stats = QLabel("Taranan: —  ·  Veri alınan: —  ·  Veri alınamayan: —  ·  Son tarama: —")
        self.scan_stats.setObjectName("muted"); layout.addWidget(self.scan_stats)

        summary = QFrame(); summary.setObjectName("dashboardPanel"); summary_box = QHBoxLayout(summary)
        left = QVBoxLayout(); title = QLabel("BUGÜNÜN DURUMU"); title.setObjectName("sectionTitle"); left.addWidget(title)
        cards = QHBoxLayout(); self.counts = {}
        for key, caption in (("trade", "Günlük Trade"), ("short", "Kısa Vade"), ("medium", "Orta Vade"), ("growth", "Büyüme Adayları")):
            value = QLabel(f"{caption}\n0\nuygun aday"); value.setObjectName("summaryMetric"); cards.addWidget(value); self.counts[key] = value
        left.addLayout(cards); summary_box.addLayout(left, 2)
        self.trade_button = QPushButton("BUGÜNÜN TRADE\nADAYLARINI BUL\nEn iyi 5 hisseyi analiz et"); self.trade_button.setObjectName("heroButton")
        self.trade_button.clicked.connect(self.trade_requested.emit); summary_box.addWidget(self.trade_button, 1); layout.addWidget(summary)

        content = QHBoxLayout(); self.preview_tabs=QTabWidget(); self.preview_tables = {}; self.preview_panels={}
        for key, caption in (("trade", "GÜNLÜK TRADE – EN İYİ 5"), ("short", "KISA VADE – EN İYİ 5"), ("medium", "ORTA VADE – EN İYİ 5")):
            panel = QFrame(); panel.setObjectName("dashboardPanel"); box = QVBoxLayout(panel)
            label = QLabel(caption); label.setObjectName("tableTitle"); box.addWidget(label)
            table = QTableWidget(0, 6); table.setHorizontalHeaderLabels(["Hisse", "Alım", "Hedef", "Stop", "Potansiyel", "Skor"])
            table.verticalHeader().setVisible(False); table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            box.addWidget(table); self.preview_tables[key] = table; self.preview_panels[key]=panel; self.preview_tabs.addTab(panel,caption.split(" – ")[0].title())
        content.addWidget(self.preview_tabs,4)
        self.rail = QWidget(); rail = QVBoxLayout(self.rail); rail.setContentsMargins(0,0,0,0)
        self.portfolio_summary = QLabel("TAKİP LİSTEM ÖZETİ\n\nKayıtlı hisse: 0\nGüncel değer: —"); self.portfolio_summary.setObjectName("sidePanel")
        self.performance = QLabel("SON PERFORMANS (30 İŞLEM)\n\nHenüz sonuçlanmış işlem yok"); self.performance.setObjectName("sidePanel")
        rail.addWidget(self.portfolio_summary); rail.addWidget(self.performance); rail.addStretch(); content.addWidget(self.rail, 1)
        layout.addLayout(content, 1)
        footer = QLabel("Veriler yaklaşık 15 dakika gecikmeli olabilir. Bu uygulama yatırım tavsiyesi değildir."); footer.setObjectName("footerText"); layout.addWidget(footer)

    def _load_preview(self, key, frame):
        table = self.preview_tables[key]; table.setRowCount(0)
        if frame is None: return
        for _, row in frame.head(5).iterrows():
            r = table.rowCount(); table.insertRow(r)
            values = [row.get("Hisse", "-"), row.get("Alım Bölgesi", "-"), row.get("Hedef", "-"), row.get("Stop", "-"), f"+%{float(row.get('Potansiyel %', 0)):.1f}", row.get("Güven Skoru", "-")]
            for c, value in enumerate(values): table.setItem(r, c, QTableWidgetItem(str(value)))

    def update_state(self, trade, short, medium, market: str, growth_count=0):
        self.market.setText(f"PİYASA DURUMU\n{market}")
        for key, caption, frame in (("trade", "Günlük Trade", trade), ("short", "Kısa Vade", short), ("medium", "Orta Vade", medium)):
            self.counts[key].setText(f"{caption}\n{len(frame)}\nuygun aday"); self._load_preview(key, frame)
        self.counts["growth"].setText(f"Büyüme Adayları\n{growth_count}\nuygun aday")
    def resizeEvent(self,event):
        super().resizeEvent(event); compact=profile_for_width(self.width())==PROFILE_COMPACT
        self.rail.setVisible(not compact)


class DecisionPage(SimpleTable):
    scan_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, title, subtitle=""):
        super().__init__(title, subtitle)
        self.row_selected.connect(self.show_reason)
        if title == "GÜNLÜK TRADE":
            scan = QPushButton("BUGÜNÜN TRADE TARAMASINI BAŞLAT")
            scan.setObjectName("heroButton")
            scan.clicked.connect(self.scan_requested.emit)
            self.layout().insertWidget(3, scan)
            cancel = QPushButton("TARAMAYI İPTAL ET"); cancel.clicked.connect(self.cancel_requested.emit)
            self.layout().insertWidget(4, cancel)
            controls = QHBoxLayout()
            self.live_price = QDoubleSpinBox(); self.live_price.setRange(0.01, 1_000_000); self.live_price.setDecimals(2); self.live_price.setPrefix("Güncel fiyat  "); self.live_price.setSuffix(" TL")
            check = QPushButton("SEÇİLİ ADAYI KONTROL ET"); check.clicked.connect(self.check_live_price)
            self.live_result = QLabel("Adayı seçip aracı kurumunuzdaki güncel fiyatı girebilirsiniz."); self.live_result.setObjectName("subText")
            controls.addWidget(self.live_price); controls.addWidget(check); controls.addWidget(self.live_result, 1)
            self.layout().insertLayout(5, controls)

    def show_reason(self, data):
        from sade_karar_modeli import sade_gerekce
        QMessageBox.information(self, "Neden bu hisse?", sade_gerekce(data))

    def check_live_price(self):
        row = self.table.currentRow()
        if row < 0:
            self.live_result.setText("Önce bir aday seçin."); return
        data = self._data.iloc[row].to_dict()
        parts = str(data.get("Alım bölgesi", data.get("Alım Bölgesi", ""))).replace("TL", "").replace("–", "-").split("-")
        try:
            low, high = float(parts[0].strip()), float(parts[1].strip())
            price, stop, target = self.live_price.value(), float(data.get("Stop", 0)), float(data.get("Hedef", 0))
        except (ValueError, IndexError, TypeError):
            self.live_result.setText("Fiyat seviyeleri kontrol edilemedi."); return
        if price <= stop:
            decision = "SETUP GEÇERSİZ"
        elif low <= price <= high:
            decision = "ALIM BÖLGESİNDE"
        elif price < low:
            decision = "GİRİŞ İÇİN BEKLE"
        elif price >= target:
            decision = "FİYAT KAÇTI"
        else:
            decision = "GİRİŞ İÇİN BEKLE"
        self.live_result.setText(decision)


class FullMarketPage(SimpleTable):
    scan_requested = Signal()

    def __init__(self, title, subtitle):
        super().__init__(title, subtitle)
        button = QPushButton("TÜM BIST TARAMASINI BAŞLAT")
        button.setObjectName("primary")
        button.clicked.connect(self.scan_requested.emit)
        button.setVisible(False)
        self.layout().insertWidget(3, button)


class Under50Worker(QObject):
    finished = Signal(bool, object, str)
    progress = Signal(str)
    structured_progress = Signal(int, int, str)

    def __init__(self, symbols=None):
        super().__init__()
        self.symbols = list(symbols) if symbols is not None else None

    def run(self):
        try:
            from bist_evreni import son_evren_durumu, tum_bist_hisseleri
            from veri_saglayici import get_daily_ohlcv
            symbols = list(self.symbols) if self.symbols is not None else tum_bist_hisseleri()
            rows, attempted, received, unavailable, ipo_count = [], 0, 0, 0, 0
            for index, symbol in enumerate(symbols, 1):
                if QThread.currentThread().isInterruptionRequested():
                    break
                if index == 1 or index == len(symbols) or index % 5 == 0:
                    self.progress.emit(f"{index}/{len(symbols)} hisse inceleniyor · {len(rows)} aday bulundu")
                    self.structured_progress.emit(index, len(symbols), "50 TL Altı · geçerli fiyat filtresi uygulanıyor")
                attempted += 1; got_data = False
                try:
                    history, _meta = get_daily_ohlcv(symbol, "1y")
                    got_data = not history.empty
                    received += int(got_data); unavailable += int(not got_data)
                    candidate = elli_tl_ohlcv_adayi(symbol, history)
                    if candidate:
                        ipo_count += int(candidate.get("Model Yolu") == "YENI_HALKA_ARZ")
                        rows.append(candidate)
                except Exception:
                    if not got_data: unavailable += 1
                    hata_gunlugune_yaz(f"50 TL Altı sembol hatası: {symbol}", traceback.format_exc())
                QThread.msleep(2)
            frame = pd.DataFrame(rows)
            if not frame.empty:
                frame = frame.sort_values(["Skor", "Risk/Getiri", "Ortalama İşlem Tutarı"], ascending=False).head(20)
                frame = frame.drop(columns=["Ortalama İşlem Tutarı"], errors="ignore").reset_index(drop=True)
            warning = son_evren_durumu().get("warning", "")
            message = f"Aktif BIST: {len(symbols)} | Denenen: {attempted} | Veri alınan: {received} | Yeni halka arz: {ipo_count} | Veri alınamayan: {unavailable} | Gösterilen: {len(frame)}"
            scores = pd.to_numeric(frame.get("Skor", pd.Series(dtype=float)), errors="coerce")
            strong_count = int(scores.ge(65).sum())
            diagnostics = ScanDiagnostics(
                strategy="under_50", symbols_total=len(symbols), data_ok=received,
                analysis_ok=received,
                score_rejected=max(0, received - len(frame)), strong_candidates=strong_count,
                watch_candidates=max(0, len(frame) - strong_count), errors=unavailable,
            )
            write_scan_diagnostics(diagnostics)
            if received < max(1, len(symbols) // 2):
                message += " | Veri kaynağı problemi nedeniyle sonuçlar eksik"
            if warning: message += " | UYARI: " + warning
            self.finished.emit(True, frame, message)
        except Exception:
            self.finished.emit(False, pd.DataFrame(), traceback.format_exc())


class Under50Page(FullMarketPage):
    central_finished = Signal(str, bool, object, str)
    central_progress = Signal(str, int, int, str)

    def __init__(self):
        super().__init__("50 TL ALTI HİSSE FIRSATLARI", "50 TL Altı · Tüm Aktif BIST · Geçerli güncel fiyatı 50,00 TL ve altında olan en güçlü 5 aday.")
        self.thread = None; self.worker = None
        button = self.layout().itemAt(3).widget()
        button.clicked.disconnect()
        button.setText("TÜM AKTİF BIST'İ TARA")
        button.clicked.connect(self.start_scan)

    def start_scan(self, run_id=None, symbols=None):
        if self.thread and self.thread.isRunning(): return False
        self._central_run_id = run_id
        self.info.setText("Tüm BIST 50 TL altı taraması başlatılıyor…")
        self.thread = QThread(self); self.worker = Under50Worker(symbols=symbols); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.info.setText)
        self.worker.structured_progress.connect(
            lambda done, total, message: self.central_progress.emit(run_id or "", done, total, message))
        self.worker.finished.connect(self.done); self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self._clear); self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        return True

    def done(self, ok, frame, message):
        run_id = getattr(self, "_central_run_id", None)
        tagged = tag_analysis_result(frame, "under_50", run_id) if run_id else frame
        if ok: self.load(tagged); self.info.setText(message)
        else: self.info.setText("Tarama hatası: " + message.splitlines()[-1])
        if run_id:
            self.central_finished.emit(run_id, ok, tagged, message)
            self._central_run_id = None

    def _clear(self):
        self.worker = None; self.thread = None


class NextDayWorker(QObject):
    finished = Signal(bool, object, str)
    progress = Signal(str)
    structured_progress = Signal(int, int, str)

    def __init__(self, symbols=None):
        super().__init__()
        self.symbols = list(symbols) if symbols is not None else None

    def run(self):
        try:
            from aday_karar_sistemi import (build_candidate_decisions, duplicate_feature_hashes,
                                            net_ev_audit)
            from bist_evreni import (kap_menkul_turleri, son_evren_durumu,
                                     son_kap_menkul_durumu, tum_bist_hisseleri)
            from ertesi_gun_motoru import erken_aday, piyasa_rejimi
            from tarama_seffafligi import TaramaOzeti
            from t1t2_tahmin_sistemi import (EveningSnapshotStore, cross_sectional_rank,
                                             load_artifacts, predict_symbol, settle_pending_snapshots,
                                             snapshot_is_timely)
            from veri_saglayici import completed_daily_frame, get_daily_ohlcv
            symbols = list(self.symbols) if self.symbols is not None else tum_bist_hisseleri()
            rows = []
            test_limit = os.getenv("BORSA_TEST_SYMBOLS", "").strip()
            if test_limit:
                try:
                    symbols = symbols[:max(0, int(test_limit))]
                except ValueError:
                    pass
            security_types = kap_menkul_turleri()
            security_cache = son_kap_menkul_durumu()
            t1_predictions, t2_predictions = [], []
            decision_contexts = {}
            if not symbols:
                raise RuntimeError("Aktif BIST evreni yuklenemedi.")
            summary = TaramaOzeti(aktif_bist_evreni=len(symbols))
            snapshot_store = EveningSnapshotStore(veri_klasoru() / "tahmin_gecmisi.sqlite3")
            settlement = settle_pending_snapshots(
                snapshot_store, lambda pending_symbol: get_daily_ohlcv(pending_symbol, "1mo"))
            daily_reports = snapshot_store.write_daily_missed_moves_reports(
                veri_klasoru() / "kacirilan_hareketler")
            artifacts, model_metrics = load_artifacts(paket_kaynak_klasoru() / "models" / "t1t2_reference.json")
            # Benchmark bir kez ve hisselerle ayni tamamlanmis zaman kesiminde alinir.
            try:
                benchmark_raw, benchmark_meta = get_daily_ohlcv("XU100.IS", "2y")
                benchmark = completed_daily_frame(benchmark_raw, benchmark_meta.fetched_at)
                if benchmark.empty:
                    raise ValueError("BIST 100 tamamlanmis bar verisi yok")
                common_cutoff = benchmark.index[-1]
                regime = piyasa_rejimi(benchmark)
                benchmark_warning = ""
            except Exception as exc:
                benchmark = pd.DataFrame(); common_cutoff = None
                regime = "VERİ YETERSİZ"; benchmark_warning = str(exc)
            for index, symbol in enumerate(symbols, 1):
                if QThread.currentThread().isInterruptionRequested():
                    break
                if index == 1 or index == len(symbols) or index % 5 == 0:
                    self.progress.emit(f"{index}/{len(symbols)} aktif BIST hissesi T+1 için inceleniyor · {len(rows)} güçlü/erken aday")
                    self.structured_progress.emit(index, len(symbols), "Yüksek Hareket · Tüm Aktif BIST")
                try:
                    history_raw, _meta = get_daily_ohlcv(symbol, "2y")
                    history = completed_daily_frame(history_raw, _meta.fetched_at)
                    if common_cutoff is not None:
                        history = history.loc[history.index <= common_cutoff].copy()
                    as_of = common_cutoff if common_cutoff is not None else (history.index[-1] if not history.empty else None)
                    row = erken_aday(symbol, history, regime, kap=None, sector_score=None, as_of=as_of)
                    if not history.empty:
                        # Menkul turu kaynaktan kesinlestirilmedigi surece normal pay varsayilmaz.
                        security_type = security_types.get(symbol, "BELIRSIZ")
                        freshness = ("GUNCEL" if common_cutoff is None or history.index[-1].date() == pd.Timestamp(common_cutoff).date()
                                     else "ESKI")
                        decision_contexts[symbol] = {
                            "data_freshness": freshness, "sector_score": None, "kap_status": None,
                            "security_cache_source": security_cache.get("source"),
                            "security_cache_at": security_cache.get("created_at"),
                            "security_cache_stale": security_cache.get("stale"),
                        }
                        t1_predictions.append(predict_symbol(symbol, history, as_of, "T+1", artifacts,
                                                             security_type=security_type, benchmark=benchmark))
                        t2_predictions.append(predict_symbol(symbol, history, as_of, "T+2", artifacts,
                                                             security_type=security_type, benchmark=benchmark))
                    strong = row.get("Durum") in {"GÜÇLÜ ERTESİ GÜN ADAYI", "ERKEN BİRİKİM ADAYI"}
                    if row.get("Model Yolu") == "STANDART" and not strong:
                        row["Neden Kodu"] = "REJECTED_LOW_SCORE"
                        row["Eleme Nedeni"] = "Standart T+1 puani aday esiginin altinda"
                    summary.kaydet(row, not history.empty)
                    rows.append(row)
                    # Teknik erken-aday sonucu yalniz on degerlendirmedir; tahmin
                    # deposuna veya kullanici kararina tek basina yazilmaz.
                except Exception as exc:
                    error = {"Hisse": symbol.replace(".IS", ""), "Durum": "VERİ ALINAMADI",
                             "Model Yolu": "BELİRLENEMEDİ", "Neden Kodu": "MISSING_PRICE_DATA",
                             "Eleme Nedeni": str(exc), "Riskler": [str(exc)]}
                    summary.kaydet(error, False); rows.append(error)
                QThread.msleep(2)
            frame = pd.DataFrame(rows)
            if not frame.empty:
                frame["Referans Skor"] = pd.to_numeric(frame.get("Referans Skor"), errors="coerce").fillna(0)
                frame = frame.sort_values("Referans Skor", ascending=False).reset_index(drop=True)
                t1_ranked = cross_sectional_rank(t1_predictions)
                t2_ranked = cross_sectional_rank(t2_predictions)
                t1_decisions = build_candidate_decisions(t1_ranked, market_regime=regime, contexts=decision_contexts)
                t2_decisions = build_candidate_decisions(t2_ranked, market_regime=regime, contexts=decision_contexts)
                t1_ranked = [item.dict() for item in t1_decisions]
                t2_ranked = [item.dict() for item in t2_decisions]
                rank1 = {item["symbol"].replace(".IS", ""): item for item in t1_ranked}
                rank2 = {item["symbol"].replace(".IS", ""): item for item in t2_ranked}
                frame["T+1 Sırası"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("rank"))
                frame["T+2 Sırası"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("rank"))
                frame["T+1 Güç Skoru"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("ranking_score"))
                frame["T+2 Güç Skoru"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("ranking_score"))
                frame["T+1 Yüzdelik"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("percentile"))
                frame["T+2 Yüzdelik"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("percentile"))
                frame["Feature Hash"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("feature_hash"))
                frame["T+1 Kararı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("final_decision"))
                frame["T+2 Kararı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("final_decision"))
                frame["T+1/T+2 Durumu"] = frame["T+1 Kararı"]
                frame["Teknik Ön Değerlendirme"] = frame["Durum"]
                frame["Teknik Ön Değerlendirme Skoru"] = frame["Referans Skor"]
                frame["Durum"] = frame["T+1 Kararı"].fillna("VERİ YETERSİZ")
                frame["T+1 %5+ Olasılığı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("probabilities", {}).get("max_5"))
                frame["T+1 %7+ Olasılığı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("probabilities", {}).get("max_7"))
                frame["T+1 %8+ Olasılığı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("probabilities", {}).get("max_8"))
                frame["T+1 Tavan Olasılığı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("probabilities", {}).get("limit_up"))
                frame["T+1 Kapanış %5+ Olasılığı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("probabilities", {}).get("close_5"))
                frame["T+2 %5+ Olasılığı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("probabilities", {}).get("max_5"))
                frame["T+2 %7+ Olasılığı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("probabilities", {}).get("max_7"))
                frame["T+2 %8+ Olasılığı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("probabilities", {}).get("max_8"))
                frame["T+2 Tavan Olasılığı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("probabilities", {}).get("limit_up"))
                frame["T+2 Pozitif Kapanış Olasılığı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("probabilities", {}).get("close_positive"))
                frame["Hedef Stop'tan Önce T+1"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("probabilities", {}).get("target_before_stop"))
                frame["Hisseye Özel Nedenler"] = frame["Hisse"].map(lambda s: " | ".join(rank1.get(str(s), {}).get("decision_reasons", [])))
                frame["Hisseye Özel Riskler"] = frame["Hisse"].map(lambda s: " | ".join(rank1.get(str(s), {}).get("risks", [])))
                frame["T+1 Neden Kodları"] = frame["Hisse"].map(lambda s: " | ".join(rank1.get(str(s), {}).get("gate_codes", [])))
                frame["T+2 Neden Kodları"] = frame["Hisse"].map(lambda s: " | ".join(rank2.get(str(s), {}).get("gate_codes", [])))
                frame["T+1 Elendiği Kapı"] = frame["Hisse"].map(lambda s: rank1.get(str(s), {}).get("rejected_by"))
                frame["T+2 Elendiği Kapı"] = frame["Hisse"].map(lambda s: rank2.get(str(s), {}).get("rejected_by"))
                frame["T+1 Geniş Radar"] = frame["Hisse"].map(lambda s: bool(rank1.get(str(s), {}).get("eligible_wide")))
                frame["T+2 Geniş Radar"] = frame["Hisse"].map(lambda s: bool(rank2.get(str(s), {}).get("eligible_wide")))
                frame["T+1 Seçkin Aday"] = frame["Hisse"].map(lambda s: bool(rank1.get(str(s), {}).get("eligible_elite")))
                frame["T+2 Seçkin Aday"] = frame["Hisse"].map(lambda s: bool(rank2.get(str(s), {}).get("eligible_elite")))
                frame["Olasılık Güvenilir"] = frame["Hisse"].map(lambda s: bool(rank1.get(str(s), {}).get("probability_reliable")))
                calibration_samples={h:min((a.calibration_samples for a in artifacts.values() if a.horizon==h),default=0) for h in ("T+1","T+2")}
                frame["Geçmiş Örnek Sayısı"] = calibration_samples["T+1"]
                frame["Menkul Türü"] = frame["Hisse"].map(lambda s: security_types.get(str(s)+".IS", "BELIRSIZ"))
                for prefix, ranks in (("T+1", rank1), ("T+2", rank2)):
                    frame[f"{prefix} Giriş"] = frame["Hisse"].map(lambda s, r=ranks: r.get(str(s), {}).get("entry"))
                    frame[f"{prefix} Hedef"] = frame["Hisse"].map(lambda s, r=ranks: r.get(str(s), {}).get("target"))
                    frame[f"{prefix} Stop"] = frame["Hisse"].map(lambda s, r=ranks: r.get(str(s), {}).get("stop"))
                    frame[f"{prefix} Risk/Getiri"] = frame["Hisse"].map(lambda s, r=ranks: r.get(str(s), {}).get("risk_reward"))
                    frame[f"{prefix} Net EV"] = frame["Hisse"].map(lambda s, r=ranks: r.get(str(s), {}).get("net_ev"))
                    frame[f"{prefix} Seviye Doğrulandı"] = frame["Hisse"].map(lambda s, r=ranks: "LEVELS_NOT_VALIDATED" not in r.get(str(s), {}).get("gate_codes", ()))
                # Aksam siralamasi degistirilemez snapshot olarak saklanir.
                snapshot_saved = 0
                for item in (*t1_ranked, *t2_ranked):
                    if snapshot_is_timely(item["as_of_timestamp"]):
                        saved, _ = snapshot_store.save(item)
                        snapshot_saved += int(saved)
                duplicate_hashes = duplicate_feature_hashes(t1_decisions)
                if duplicate_hashes:
                    sample = next(iter(duplicate_hashes.values()))
                    shared_features = sorted({name for artifact in artifacts.values() for name in artifact.feature_names})
                    message_hash = (f" | UYARI: {sum(len(x) for x in duplicate_hashes.values())} sembolde ayni feature hash: "
                                    f"{', '.join(sample[:5])}; aynı kalan model özellikleri: {', '.join(shared_features)}")
                else:
                    message_hash = " | Feature hashler sembol bazinda ayrik"
                ev1, ev2 = net_ev_audit(t1_decisions), net_ev_audit(t2_decisions)
                message_hash += (f" | Net EV T+1: {ev1['calculated']} hesap, {ev1['positive']} pozitif; "
                                 f"T+2: {ev2['calculated']} hesap, {ev2['positive']} pozitif")
                if not snapshot_saved:
                    message_hash += " | Snapshot yazılmadı: seans sonrası tahmin penceresi dışında"
            evren = son_evren_durumu()
            message = summary.metin()
            if evren.get("warning"):
                message += " | UYARI: " + evren["warning"]
            if security_cache.get("warning"):
                message += " | KAP menkul türü cache uyarısı: " + str(security_cache["warning"])
            if benchmark_warning:
                message += " | BIST 100 rejim verisi yok: " + benchmark_warning
            message += " | Kalibre model yoksa olasiliklar bilincli olarak bos gosterilir."
            message += f" | T+1/T+2 artefakt: {len(artifacts)}/12"
            message += (f" | Gerçekleşme: {settlement['settled']} işlendi, "
                        f"{settlement['not_ready']} seans bekliyor")
            message += (f" | Kaçırılan Hareketler raporu: {daily_reports['written']} yeni, "
                        f"{daily_reports['existing']} değişmez kayıt")
            if not frame.empty:
                message += message_hash
            if frame.empty:
                message += " Bugün güvenilir güçlü hareket adayı bulunamadı."
            self.finished.emit(True, frame, message)
        except Exception:
            self.finished.emit(False, pd.DataFrame(), traceback.format_exc())


class NextDayPage(NextDayDashboard):
    central_finished = Signal(str, bool, str)
    central_progress = Signal(str, int, int, str)

    def __init__(self):
        super().__init__(veri_klasoru() / "tahmin_gecmisi.sqlite3")
        self.thread = None; self.worker = None; self._run_id = None; self._pending_render = None
        self._result_cache_path = veri_klasoru() / "yuksek_hareket_son_snapshot.json"
        self._load_cached_results()
        self.scan_requested.connect(self.start_scan)

    def _load_cached_results(self):
        if not self._result_cache_path.exists():
            return
        try:
            frame = pd.read_json(self._result_cache_path, orient="records")
            if not frame.empty:
                self.load_results(frame, "Son kaydedilmiş Yüksek Hareket snapshotı")
        except Exception as exc:
            self.stats.set_error("Son Yüksek Hareket snapshotı okunamadı; yeni tarama bekleniyor.")
            hata_gunlugune_yaz("Yüksek Hareket snapshotı", str(exc))

    def start_scan(self, run_id=None, symbols=None):
        if self.thread and self.thread.isRunning(): return False
        self._run_id = run_id or uuid.uuid4().hex
        self.set_loading("T+1 erken aday taraması başlatılıyor…")
        self.thread = QThread(self); self.worker = NextDayWorker(symbols=symbols); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.stats.setText)
        self.worker.structured_progress.connect(
            lambda done, total, message: self.central_progress.emit(self._run_id or "", done, total, message))
        token = self._run_id
        self.worker.finished.connect(lambda ok, frame, message: self.done(ok, frame, message, token)); self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self._clear); self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        return True

    def done(self, ok, frame, message, run_id=None):
        if run_id is not None and run_id != self._run_id:
            return
        if ok:
            tagged = tag_analysis_result(frame, "high_movement", run_id) if run_id else frame
            try:
                self._result_cache_path.parent.mkdir(parents=True, exist_ok=True)
                tagged.to_json(self._result_cache_path, orient="records", force_ascii=False)
            except Exception as exc:
                hata_gunlugune_yaz("Yüksek Hareket snapshotı kaydı", str(exc))
            if self.isVisible():
                self.load_results(tagged, message)
            else:
                self._full = tagged.copy()
                self._pending_render = (tagged.copy(), message)
        else: self.set_error(message.splitlines()[-1])
        self.central_finished.emit(run_id or self._run_id or "", ok, message)

    def render_pending(self):
        if self._pending_render is None:
            return False
        frame, message = self._pending_render
        self._pending_render = None
        self.load_results(frame, message)
        return True

    def _clear(self):
        self.worker = None; self.thread = None


class ScanProgressPanel(QFrame):
    """Gercek is olaylarini gosteren, 1366x768'e sigan merkezi tarama ozeti."""
    def __init__(self):
        super().__init__(); self.setObjectName("scanProgressPanel"); self.setVisible(False)
        row = QHBoxLayout(self); row.setContentsMargins(14, 5, 14, 5); row.setSpacing(10)
        self.status = QLabel("Tarama hazırlanıyor"); self.status.setObjectName("subText"); self.status.setMinimumWidth(210)
        self.counts = QLabel("0 / 0"); self.counts.setMinimumWidth(75)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0); self.bar.setTextVisible(True); self.bar.setMinimumWidth(210)
        self.phase = QLabel("Tarama hazırlanıyor"); self.phase.setObjectName("muted"); self.phase.setMinimumWidth(230)
        self.started = QLabel("Başlangıç: —"); self.started.setObjectName("muted")
        self.elapsed = QLabel("Geçen süre: 0 sn"); self.elapsed.setObjectName("muted")
        for widget in (self.status, self.counts, self.bar, self.phase, self.started, self.elapsed): row.addWidget(widget)
        row.setStretchFactor(self.bar, 1); row.setStretchFactor(self.phase, 1)

    @staticmethod
    def duration_text(seconds):
        seconds = max(0, int(seconds)); minutes, second = divmod(seconds, 60); hours, minutes = divmod(minutes, 60)
        if hours: return f"{hours} sa {minutes} dk {second} sn"
        if minutes: return f"{minutes} dk {second} sn"
        return f"{second} sn"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME + " v" + APP_VERSION)
        self.resize(1366, 768)
        icon = uygulama_klasoru() / "logo.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.scan_process = None
        self.scan_coordinator = None
        self._scan_started_at = None
        self._scan_result_mtime_before = None
        self._scan_cancelled = False
        self._scan_failure_shown = False
        self._last_view_profile = None
        self._scan_stdout_buffer = ""
        self._scan_stderr_buffer = ""
        self._analysis_workers_started = False
        self._analysis_result_cache = {}
        self._scan_universe_meta = {}
        self._lazy_page_renderers = {}
        self._applying_scan_result = False
        self._scan_apply_count = 0
        self._heartbeat_last = time.monotonic()
        self.pages = QStackedWidget()

        self.home = HomePage()
        self.terminal = InvestmentTerminalPage()
        self.buy = self.terminal.buy
        self.wait = self.terminal.wait
        self.avoid = self.terminal.avoid
        self.onay = self.terminal.onay
        self.tum = self.terminal.tum
        self.single = SingleAnalysisPage()
        self.sale = SalePage()
        self.track = TrackPage()
        self.funds = FundAnalysisPage()
        self.daily_trade = DailyTradePage()
        self.short_term = DecisionPage("KISA VADE FIRSATLARI", "Model, geçmiş performansa göre en anlamlı süreyi seçer; en fazla 5 aday gösterilir.")
        self.short_term.info.setText("Kısa Vade · Tüm Aktif BIST")
        self.medium_term = DecisionPage("ORTA VADE FIRSATLARI", "Orta Vade · Tüm Aktif BIST · Ayrı orta-vade modeli en fazla 5 aday gösterir.")
        self.medium_term.info.setText("Orta Vade · Tüm Aktif BIST")
        self.under_50 = Under50Page()
        self.next_day = NextDayPage()
        self.history = T1T2PerformanceDashboard(veri_klasoru() / "tahmin_gecmisi.sqlite3")
        self.settings_page = PlaceholderPage("Ayarlar", "Uygulama ayarları mevcut yapılandırma dosyasından okunur. Yeni ayar alanları veri kaynağı doğrulandıkça eklenecektir.")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(1200)

        for p in [self.home, self.next_day, self.daily_trade, self.short_term, self.medium_term,
                  self.under_50, self.funds, self.track, self.history, self.settings_page,
                  self.sale, self.single, self.terminal, self.log]:
            self.pages.addWidget(p)

        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        self.top_header = TopHeader()
        self.top_header.set_compact(True)
        self.top_header.scan_requested.connect(self.scan)
        self.top_header.search_requested.connect(self._search_symbol)
        outer.addWidget(self.top_header)
        self.scan_progress = ScanProgressPanel()
        outer.addWidget(self.scan_progress)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        self.sidebar = Sidebar(); self.sidebar.page_requested.connect(self._show_page); root.addWidget(self.sidebar)
        content = QVBoxLayout(); content.setContentsMargins(8, 6, 8, 6); content.setSpacing(6)
        markets = QHBoxLayout(); markets.setSpacing(6); self.market_cards = {}
        for name in ("BIST 100", "BIST 30", "BIST TÜM", "DOLAR/TL", "EURO/TL", "ONS ALTIN"):
            market_card = MarketCard(name); self.market_cards[name] = market_card
            if name not in {"BIST 100","BIST 30","BIST TÜM"}: market_card.hide()
            markets.addWidget(market_card, 1)
        content.addLayout(markets); content.addWidget(self.pages, 1); root.addLayout(content, 1); outer.addLayout(root, 1)
        self.scan_button = self.top_header.scan
        self.reload_button = QPushButton("Son veriyi yükle"); self.reload_button.clicked.connect(self.load_report)
        self.report_path_label = QLabel("Tahminler sürümlü SQLite geçmişinde saklanır.")
        self.setStyleSheet(APP_STYLE)
        self._page_map = {"home":self.home,"next":self.next_day,"daily":self.daily_trade,"short":self.short_term,
                          "medium":self.medium_term,"under50":self.under_50,"funds":self.funds,"portfolio":self.track,
                          "performance":self.history,"settings":self.settings_page}
        self.pages.currentChanged.connect(self._sync_active_page)
        self._market_thread = None; self._market_worker = None
        if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen" and os.environ.get("BORSA_VISUAL_TEST") != "1":
            QTimer.singleShot(100, self._load_market_cards)

        self.home.trade_requested.connect(lambda: self.pages.setCurrentWidget(self.daily_trade))
        self.next_day.central_finished.connect(self._high_movement_finished)
        self.next_day.central_progress.connect(
            lambda run_id, done, total, message: self._worker_progress("high_movement", run_id, done, total, message))
        self.daily_trade.central_finished.connect(
            lambda run_id, ok, frame, message: self._analysis_worker_finished("daily_trade", run_id, ok, frame, message))
        self.daily_trade.central_progress.connect(
            lambda run_id, done, total, message: self._worker_progress("daily_trade", run_id, done, total, message))
        self.under_50.central_finished.connect(
            lambda run_id, ok, frame, message: self._analysis_worker_finished("under_50", run_id, ok, frame, message))
        self.under_50.central_progress.connect(
            lambda run_id, done, total, message: self._worker_progress("under_50", run_id, done, total, message))
        self.home.trade_button.setVisible(False)
        self.pages.setCurrentWidget(self.next_day)
        self.sidebar.set_active("next")

        if not os.getenv("BORSA_UI_SMOKE_SCREENSHOT", "").strip():
            self.load_report()
        self._scan_elapsed_timer = QTimer(self)
        self._scan_elapsed_timer.timeout.connect(self._update_scan_elapsed)
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._gui_heartbeat)
        self._heartbeat_timer.start(250)
        QTimer.singleShot(0,self._apply_responsive_profile)

    def resizeEvent(self,event):
        super().resizeEvent(event); self._apply_responsive_profile()

    def _apply_responsive_profile(self):
        profile=profile_for_width(self.width()); compact=profile==PROFILE_COMPACT
        self.top_header.set_compact(compact)
        if compact and self.sidebar.expanded: self.sidebar.set_expanded(False,remember=False)
        for name,card in self.market_cards.items():
            card.setVisible(not compact or name in {"BIST 100","BIST 30","BIST TÜM"})
        for page in self._page_map.values():
            if hasattr(page,"set_view_profile"): page.set_view_profile(profile)
        self._last_view_profile=profile

    def _show_page(self, key):
        page = self._page_map.get(key)
        if page is not None:
            self.pages.setCurrentWidget(page)
            self.sidebar.set_active(key)
            self._render_lazy_page(page)
            if key == "performance" and hasattr(page, "refresh"):
                page.refresh()

    def _sync_active_page(self, _index):
        current = self.pages.currentWidget()
        for key, page in self._page_map.items():
            if page is current:
                self.sidebar.set_active(key)
                self._render_lazy_page(page)
                break

    def _render_lazy_page(self, page):
        renderer = self._lazy_page_renderers.pop(page, None)
        if renderer is None:
            if hasattr(page, "render_pending"):
                page.render_pending()
            return False
        started = time.perf_counter()
        renderer()
        self._post_scan_trace("lazy_render", page=getattr(page, "analysis_id", type(page).__name__), duration=time.perf_counter()-started)
        return True

    def _post_scan_trace(self, event, **fields):
        payload = {"time": datetime.now().isoformat(timespec="milliseconds"), "event": event,
                   "scan_id": getattr(self, "_scan_run_id", None), **fields}
        try:
            path = veri_klasoru() / "logs" / "post_scan_trace.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def _active_worker_count(self):
        workers = (self.daily_trade.thread, self.under_50.thread, self.next_day.thread, self._market_thread)
        return sum(bool(thread and thread.isRunning()) for thread in workers) + int(
            bool(self.scan_process and self.scan_process.state() != QProcess.NotRunning)
        )

    def _gui_heartbeat(self):
        now = time.monotonic(); gap = now - self._heartbeat_last; self._heartbeat_last = now
        if gap > 1.0 and self.scan_coordinator is not None:
            self._post_scan_trace("gui_heartbeat_lost", gap=gap, phase=self.scan_coordinator.phase,
                                  active_threads=self._active_worker_count())

    def _defer_page_render(self, page, renderer):
        self._lazy_page_renderers[page] = renderer
        if self.pages.currentWidget() is page:
            self._render_lazy_page(page)

    def _search_symbol(self, text):
        symbol = normalize_symbol(text)
        if not symbol:
            return
        self.single.symbol.setText(symbol.replace(".IS", ""))
        self.pages.setCurrentWidget(self.single)

    def _load_market_cards(self):
        if self._market_thread and self._market_thread.isRunning():
            return
        self._market_thread = QThread(self)
        self._market_worker = MarketDataWorker()
        self._market_worker.moveToThread(self._market_thread)
        self._market_thread.started.connect(self._market_worker.run)
        self._market_worker.finished.connect(self._market_data_done)
        self._market_worker.finished.connect(self._market_thread.quit)
        self._market_thread.finished.connect(self._market_worker.deleteLater)
        self._market_thread.finished.connect(self._clear_market_worker)
        self._market_thread.start()

    def _market_data_done(self, payload):
        for name, widget in self.market_cards.items():
            widget.update_data(payload.get(name))
        bist = payload.get("BIST 100")
        if bist:
            is_positive = bist["value"] >= bist["previous"]
            self.top_header.market.setText("● Piyasa Açık" if datetime.now().weekday() < 5 and 10 <= datetime.now().hour < 18 else "● Piyasa Kapalı")
            self.top_header.market.setObjectName("positive" if is_positive else "negative")

    def _clear_market_worker(self):
        if self._market_thread:
            self._market_thread.deleteLater()
        self._market_worker = None; self._market_thread = None

    def load_report(self):
        path = rapor_yolu()
        if not path.exists():
            return False
        if self._applying_scan_result:
            self._post_scan_trace("apply_skipped_reentrant")
            return False
        self._applying_scan_result = True
        self._scan_apply_count += 1
        total_started = time.perf_counter()
        timings = {}
        self._post_scan_trace("apply_scan_result_started", apply_count=self._scan_apply_count)
        try:
            from analiz_deposu import anlik_goruntu_oku
            stage_started = time.perf_counter()
            sheets = anlik_goruntu_oku(path)
            timings["cache_read"] = time.perf_counter() - stage_started
            all_results = sheets.get("Tum Sonuclar", pd.DataFrame()).copy()
            if "Fiyat" in all_results.columns:
                valid_price = pd.to_numeric(all_results["Fiyat"], errors="coerce")
                all_results = all_results[valid_price > 0].reset_index(drop=True)
            visible_columns = [
                "Hisse", "Veri Tarihi", "Yatırım Kararı", "Fırsat Seviyesi",
                "Veri Durumu", "Veri Gecikmesi (İş Günü)",
                "AI Güven Puanı", "v4 Güven Puanı", "Broker Aksiyon", "Fiyat",
                "Açılış Fiyatı", "Gün İçi Hedef", "Gün İçi Yükseliş %",
                "Önerilen Alış Alt", "Önerilen Alış Üst", "Önerilen Satış",
                "Önerilen Stop", "Beklenen Getiri %", "Karar Risk/Getiri",
                "MTF Uyum", "Temel Puan", "Faaliyet Puanı", "KAP Etiket",
                "Karar Nedenleri",
            ]
            compact = all_results[[c for c in visible_columns if c in all_results.columns]].copy()

            stage_started = time.perf_counter()
            trade_frame = sade_firsatlar(all_results, "gunluk", limit=5, sure="Gün içi")
            if trade_frame.empty:
                trade_frame = gunluk_rapor_adaylari(all_results, limit=5)
            central_active = self.scan_coordinator is not None and not self.scan_coordinator.all_terminal
            self.daily_trade.report_fallback = trade_frame.copy()
            if not central_active:
                self._defer_page_render(self.daily_trade, lambda frame=trade_frame.copy(): self.daily_trade.table.load(frame))

            backtest_frame = sheets.get("Backtest Ozet", pd.DataFrame())
            short_days, short_evidence = en_iyi_vade(backtest_frame, "kisa")
            medium_days, medium_evidence = en_iyi_vade(backtest_frame, "orta")
            short_source = sheets.get("Kisa Vade", pd.DataFrame())
            medium_source = sheets.get("Orta Vade", pd.DataFrame()).copy()
            if short_source.empty:
                short_source = all_results.copy()
            if medium_source.empty:
                medium_source = all_results.copy()
            if "Hisse" in all_results:
                base = all_results.set_index(all_results["Hisse"].astype(str).str.replace(".IS", "", regex=False).str.upper())
                for source in (short_source, medium_source):
                    if "Hisse" not in source:
                        continue
                    keys = source["Hisse"].astype(str).str.replace(".IS", "", regex=False).str.upper()
                    for column in ("Fiyat", "Veri Durumu"):
                        if column not in source and column in base:
                            source[column] = keys.map(base[column])
            short_frame = sade_firsatlar(short_source, "kisa", limit=5, sure=sure_metni(short_days))
            if short_frame.empty:
                short_frame = vade_rapor_adaylari(all_results, sure_metni(short_days), limit=5)
            medium_source = orta_vadeden_kisa_adaylari_cikar(short_frame, medium_source)
            medium_frame = sade_firsatlar(medium_source, "orta", limit=5, sure=sure_metni(medium_days))
            if medium_frame.empty:
                medium_frame = vade_rapor_adaylari(
                    all_results, sure_metni(medium_days), limit=5,
                    haric=short_frame.get("Hisse", pd.Series(dtype=str)).tolist(),
                )
            short_strong = int(short_frame.get("Karar", pd.Series(dtype=str)).eq("AL").sum())
            short_watch = max(0, len(short_frame) - short_strong)
            short_note = (f"{len(all_results)} hisse analiz edildi · {short_strong} güçlü aday · {short_watch} takip adayı"
                          if short_strong else
                          f"{len(all_results)} hisse analiz edildi · Güçlü AL koşulunu sağlayan hisse yok · En iyi {short_watch} takip adayı gösteriliyor")
            def render_short(frame=short_frame.copy(), note=short_note, evidence=short_evidence):
                self.short_term.load(frame)
                self.short_term.info.setText(note + f" · Süre dayanağı: {evidence}")
            self._defer_page_render(self.short_term, render_short)
            medium_strong = int(medium_frame.get("Karar", pd.Series(dtype=str)).eq("AL").sum())
            medium_watch = max(0, len(medium_frame) - medium_strong)
            medium_note = (f"{len(all_results)} hisse analiz edildi · {medium_strong} güçlü aday · {medium_watch} takip adayı"
                           if medium_strong else
                           f"{len(all_results)} hisse analiz edildi · Güçlü AL koşulunu sağlayan hisse yok · En iyi {medium_watch} takip adayı gösteriliyor")
            def render_medium(frame=medium_frame.copy(), note=medium_note, evidence=medium_evidence):
                self.medium_term.load(frame)
                self.medium_term.info.setText(note + f" · Süre dayanağı: {evidence}")
            self._defer_page_render(self.medium_term, render_medium)
            # 50 TL Altı kesin ürün evreni tüm aktif BIST'tir; rapor yeniden
            # yüklenirken 120 likit hisseye daraltmak BIST30 dışı adayları saklar.
            under_frame = elli_tl_adaylari(all_results, limit=20)
            timings["post_processing"] = time.perf_counter() - stage_started
            if not central_active:
                self._defer_page_render(self.under_50, lambda frame=under_frame.copy(): self.under_50.load(frame))
            self.home.portfolio_summary.setText(
                f"TAKİP LİSTEM ÖZETİ\n\nKayıtlı hisse: {len(self.track.symbols)}\nFiyatları Takip Listem ekranından yenileyin"
            )
            perf = sheets.get("Sinyal Performansi", pd.DataFrame())
            if not perf.empty:
                self.home.performance.setText(
                    f"SON PERFORMANS\n\nKayıtlı sonuç: {len(perf)}\nDetay için Geçmiş ekranını açın"
                )

            market_score = pd.to_numeric(all_results.get("v4 Güven Puanı", pd.Series(dtype=float)), errors="coerce").median()
            market = "OLUMLU" if pd.notna(market_score) and market_score >= 65 else "RİSKLİ" if pd.notna(market_score) and market_score < 45 else "NÖTR"
            self.home.index_value.setText(f"BIST EVRENİ\n{len(all_results)} hisse analiz edildi")
            self.home.clock.setText(datetime.now().strftime("%d.%m.%Y\n%H:%M"))
            valid_count = int(all_results.get("Fiyat", pd.Series(dtype=float)).notna().sum()) if "Fiyat" in all_results else 0
            self.home.scan_stats.setText(f"Taranan: {len(all_results)}  ·  Veri alınan: {valid_count}  ·  Veri alınamayan: {max(0, len(all_results)-valid_count)}  ·  Son tarama: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
            stage_started = time.perf_counter()
            self.home.update_state(trade_frame, short_frame, medium_frame, market, len(under_frame))
            timings["home_render"] = time.perf_counter() - stage_started

            def numeric(name, default=0):
                if name not in all_results.columns:
                    return pd.Series(default, index=all_results.index, dtype=float)
                return pd.to_numeric(all_results[name], errors="coerce").fillna(default)

            decision = all_results.get("Yatırım Kararı", pd.Series("", index=all_results.index)).astype(str)
            buy_results, wait_results, avoid_results = karar_gruplarina_ayir(all_results)

            decision_columns = [
                "Hisse", "Yatırım Kararı", "Fiyat", "Açılış Fiyatı", "Gün İçi Hedef",
                "Gün İçi Yükseliş %", "Önerilen Alış Alt", "Önerilen Alış Üst",
                "Önerilen Satış", "Önerilen Stop", "Beklenen Getiri %", "Karar Risk/Getiri",
                "Model Olasılığı %", "Veri Durumu", "Karar Nedenleri",
            ]
            decision_columns = [c for c in decision_columns if c in all_results.columns]
            buy_display = buy_results[decision_columns].copy()
            wait_display = wait_results[decision_columns].copy()
            avoid_display = avoid_results[decision_columns].copy()
            mtf = all_results.get("MTF Uyum", pd.Series("", index=all_results.index)).astype(str)
            strict = (
                decision.eq("BUGÜN AL") & (numeric("Veri Yaşı (Gün)", 999) <= 4) &
                (numeric("Model Olasılığı %") >= 72) & (numeric("v4 Güven Puanı") >= 78) &
                (numeric("Karar Risk/Getiri") >= 1.8) &
                ~mtf.str.contains("negatif", case=False, na=False)
            )
            high_conviction = all_results[strict].copy()
            sort_columns = [c for c in ["Model Olasılığı %", "v4 Güven Puanı", "Karar Risk/Getiri"] if c in high_conviction.columns]
            if sort_columns:
                high_conviction = high_conviction.sort_values(sort_columns, ascending=False)
            high_conviction = high_conviction.head(3)
            conviction_columns = [
                "Hisse", "Yatırım Kararı", "Fiyat", "Açılış Fiyatı", "Gün İçi Hedef",
                "Gün İçi Yükseliş %", "Önerilen Alış Alt",
                "Önerilen Alış Üst", "Önerilen Satış", "Önerilen Stop",
                "Beklenen Getiri %", "Karar Risk/Getiri", "Model Olasılığı %",
                "v4 Güven Puanı", "Karar Nedenleri",
            ]
            conviction_display = high_conviction[[c for c in conviction_columns if c in high_conviction.columns]].copy()
            def render_terminal(all_frame=compact.copy(), buy=buy_display, wait=wait_display,
                                avoid=avoid_display, conviction=conviction_display):
                self.tum.load(all_frame)
                self.buy.load(buy)
                self.wait.load(wait)
                self.avoid.load(avoid)
                self.onay.load(conviction)
            self._defer_page_render(self.terminal, render_terminal)
            self.terminal.update_summary(
                path,
                (self.buy.table.rowCount(), self.wait.table.rowCount(), self.avoid.table.rowCount()),
                total=len(all_results),
                conviction=len(high_conviction),
            )
            self.report_path_label.setText("Tahminler sürümlü SQLite geçmişinde saklanır.")
            rows = len(all_results)
            unique = int(all_results["Hisse"].astype(str).nunique()) if "Hisse" in all_results else rows
            self._post_scan_trace(
                "apply_scan_result_finished", duration=time.perf_counter()-total_started,
                timings=timings, shapes={
                    "raw_scan": list(all_results.shape), "daily": list(trade_frame.shape),
                    "short": list(short_frame.shape), "medium": list(medium_frame.shape),
                    "under50": list(under_frame.shape), "terminal_compact": list(compact.shape),
                }, rows=rows, unique_symbols=unique, duplicate_rows=max(0, rows-unique),
                lazy_pages=len(self._lazy_page_renderers), active_threads=self._active_worker_count(),
            )
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Rapor", str(exc))
            hata_gunlugune_yaz("Sonuç sayfalarını yenileme", traceback.format_exc())
            self._post_scan_trace("apply_scan_result_error", duration=time.perf_counter()-total_started, error=str(exc))
            return False
        finally:
            self._applying_scan_result = False

    def open_report(self):
        path = rapor_yolu()
        if not path.exists():
            QMessageBox.information(self, "Excel Raporu", "Henüz Excel raporu oluşmadı. Önce profesyonel taramayı tamamla.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_report_folder(self):
        folder = veri_klasoru() / "output"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def scan(self):
        if self.scan_coordinator is not None and not self.scan_coordinator.all_terminal:
            self.scan_progress.setVisible(True)
            self.scan_progress.status.setText("Tarama zaten devam ediyor")
            self.log.append("Tarama zaten devam ediyor; ikinci süreç başlatılmadı.")
            return False
        if self.scan_process is not None:
            if self.scan_process.state() != QProcess.NotRunning:
                self.scan_progress.setVisible(True); self.scan_progress.status.setText("Tarama zaten devam ediyor")
                return False
            self.scan_process.deleteLater(); self.scan_process = None
        self._scan_run_id = uuid.uuid4().hex
        self._scan_apply_count = 0
        self.scan_coordinator = ScanCoordinator(self._scan_run_id)
        for component in ("core", "daily_trade", "short_term", "medium_term", "under_50", "high_movement"):
            self.scan_coordinator.start_component(component)
        self._analysis_workers_started = False
        self._scan_universe_meta = {}
        self._scan_started_at = time.monotonic()
        self._scan_started_clock = datetime.now()
        result_path = rapor_yolu()
        self._scan_result_mtime_before = result_path.stat().st_mtime_ns if result_path.exists() else None
        self._scan_cancelled = False; self._scan_failure_shown = False
        self.top_header.set_scanning(True)
        self.scan_progress.setVisible(True)
        self.scan_progress.status.setText("Tarama hazırlanıyor")
        self.scan_progress.phase.setText("Tarama hazırlanıyor")
        self.scan_progress.counts.setText("0 / 0")
        self.scan_progress.bar.setValue(0)
        self.scan_progress.started.setText("Başlangıç: " + self._scan_started_clock.strftime("%H:%M:%S"))
        self.scan_progress.elapsed.setText("Geçen süre: 0 sn")
        self._scan_elapsed_timer.start(1000)
        target = getattr(self, "_scan_target", self.home)
        if target is self.daily_trade:
            self.pages.setCurrentWidget(self.daily_trade)
            self.daily_trade.info.setText("Aktif BIST evreni hazırlanıyor…")
        else:
            self.pages.setCurrentWidget(self.log)
        self.log.clear()
        self.log.append("Tarama ayrı ve güvenli bir işlemde başlatılıyor...")
        self._scan_stdout_buffer = ""
        self._scan_stderr_buffer = ""
        program, arguments = tarama_alt_sureci_komutu()
        self.scan_process = QProcess(self)
        self.scan_process.setProgram(program)
        self.scan_process.setArguments(arguments)
        self.scan_process.setWorkingDirectory(str(uygulama_klasoru()))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("BORSA_TARAMA_EVRENI", "ALL")
        environment.insert("BORSA_SCAN_ID", self._scan_run_id)
        self.scan_process.setProcessEnvironment(environment)
        self.scan_process.readyReadStandardOutput.connect(self._read_scan_stdout)
        self.scan_process.readyReadStandardError.connect(self._read_scan_stderr)
        self.scan_process.errorOccurred.connect(self._scan_process_error)
        self.scan_process.finished.connect(self._scan_process_finished)
        self.scan_process.start()
        self.log.append(f"Tarama kimliği: {self._scan_run_id[:12]}")
        return True

    def scan_daily_trade(self):
        self._scan_target = self.daily_trade
        self.scan()

    def scan_all_market(self, target):
        self._scan_target = target
        self._scan_universe = "ALL"
        self.scan()

    def cancel_scan(self):
        if self.scan_process is not None and self.scan_process.state() != QProcess.NotRunning:
            self.scan_process.terminate()
            self.log.append("Tarama kullanıcı tarafından durduruldu.")
        if self.next_day.thread and self.next_day.thread.isRunning():
            self.next_day.thread.requestInterruption()
        if self.daily_trade.thread and self.daily_trade.thread.isRunning():
            self.daily_trade.thread.requestInterruption()
        if self.under_50.thread and self.under_50.thread.isRunning():
            self.under_50.thread.requestInterruption()
        if self.scan_coordinator is not None and not self.scan_coordinator.all_terminal:
            self._scan_cancelled = True
            for component, state in list(self.scan_coordinator.components.items()):
                if state not in TERMINAL_STATES:
                    self.scan_coordinator.finish_component(component, "IPTAL")
            self._finalize_central_scan()

    def _append_process_text(self, text, is_error=False):
        attr = "_scan_stderr_buffer" if is_error else "_scan_stdout_buffer"
        buffer = getattr(self, attr) + text
        lines = buffer.split("\n")
        setattr(self, attr, lines.pop())
        for line in lines:
            if line.strip():
                self.log.append(line.rstrip())
                if line.startswith("UNIVERSE_META|"):
                    parts = line.rstrip().split("|", 5)
                    if len(parts) == 6 and self.scan_coordinator and parts[1] == self.scan_coordinator.scan_id:
                        self._scan_universe_meta = {
                            "count": parts[2], "source": parts[3], "created_at": parts[4], "warning": parts[5],
                        }
                elif line.startswith("UNIVERSE|"):
                    parts = line.rstrip().split("|", 2)
                    if len(parts) == 3 and self.scan_coordinator and parts[1] == self.scan_coordinator.scan_id:
                        self._start_analysis_workers([item for item in parts[2].split(",") if item])
                elif self.scan_coordinator and self.scan_coordinator.accept_line(line.rstrip()):
                    self._render_scan_progress()
                elif line.startswith("SCAN_RESULT|"):
                    parts = line.rstrip().split("|", 4)
                    if len(parts) == 5 and self.scan_coordinator and parts[1] == self.scan_coordinator.scan_id:
                        try:
                            self.scan_coordinator.stock_valid = int(parts[2]); self.scan_coordinator.stock_failed = int(parts[3])
                        except ValueError:
                            pass
                if getattr(self, "_scan_target", None) is self.daily_trade:
                    self.daily_trade.info.setText(line.rstrip())

    def _read_scan_stdout(self):
        if self.scan_process is not None:
            payload = bytes(self.scan_process.readAllStandardOutput())
            try: text = payload.decode("utf-8")
            except UnicodeDecodeError: text = payload.decode("cp1254", errors="replace")
            self._append_process_text(text)

    def _read_scan_stderr(self):
        if self.scan_process is not None:
            payload = bytes(self.scan_process.readAllStandardError())
            try: text = payload.decode("utf-8")
            except UnicodeDecodeError: text = payload.decode("cp1254", errors="replace")
            self._append_process_text(text, is_error=True)

    def _scan_process_error(self, error):
        if self.scan_process is not None:
            detail = f"{self.scan_process.errorString()} ({error})"
            self.log.append(f"Tarama işlemi başlatma/çalışma hatası: {detail}")
            hata_gunlugune_yaz("Tarama alt süreci hatası", detail)
            if error == QProcess.FailedToStart:
                self._fail_central_scan("Tarama başlatılamadı", "Alt süreç dosyası bulunamadı veya çalıştırılamadı.")

    def _scan_process_finished(self, exit_code, exit_status):
        callback_started = time.perf_counter()
        self._post_scan_trace("scan_worker_finished", exit_code=exit_code, exit_status=str(exit_status))
        if _CRASH_STREAM is not None:
            faulthandler.dump_traceback_later(5.0, repeat=False, file=_CRASH_STREAM)
        self._read_scan_stdout()
        self._read_scan_stderr()
        for attr in ("_scan_stdout_buffer", "_scan_stderr_buffer"):
            tail = getattr(self, attr).strip()
            if tail:
                self.log.append(tail)
            setattr(self, attr, "")
        if self.scan_coordinator is None or self.scan_coordinator.components["core"] in TERMINAL_STATES:
            self._cleanup_scan_process()
            if _CRASH_STREAM is not None: faulthandler.cancel_dump_traceback_later()
            return
        ok = exit_status == QProcess.NormalExit and exit_code == 0 and not self._scan_cancelled
        if ok:
            path = rapor_yolu()
            new_result = path.exists() and (self._scan_result_mtime_before is None or path.stat().st_mtime_ns > self._scan_result_mtime_before)
            if not new_result:
                self._component_failed("core", "Tarama çalıştı ancak yeni sonuç kaydı oluşturulamadı. Önceki sonuçlar korunuyor.")
                self._fail_dependent_components()
            else:
                self.scan_progress.status.setText("Tarama bitti · Sonuçlar hazırlanıyor…")
                self.scan_progress.phase.setText("Snapshot okunuyor ve görünür ekran hazırlanıyor")
            if new_result and self.load_report():
                # QProcess'in başarılı çıkışı bütün hisse görevlerinin join edildiğini
                # kanıtlar. Son stdout satırı tamponda kaybolmuş olsa bile sayaç eksik
                # kalıp taramanın %97/%99'da görünmesine izin verme.
                self.scan_coordinator.finish_stock_work()
                self.scan_coordinator.finish_component("core")
                for name in ("short_term", "medium_term", "watchlist", "portfolio", "performance"):
                    self.scan_coordinator.finish_component(name)
                self._refresh_portfolio_from_report()
                if self.scan_coordinator.components["high_movement"] not in TERMINAL_STATES:
                    self.scan_coordinator.phase = "high_movement"
                    self.scan_coordinator.message = "Yüksek Hareket sonuçları hazırlanıyor"
            else:
                self._component_failed("core", "Yeni sonuç kaydı okunamadı. Önceki sonuçlar korunuyor.")
                self._fail_dependent_components()
        else:
            reason = "Tarama kullanıcı tarafından iptal edildi." if self._scan_cancelled else f"Alt süreç normal kapanmadı (çıkış kodu {exit_code})."
            self._component_failed("core", reason, state="IPTAL" if self._scan_cancelled else "HATA")
            self._fail_dependent_components(state="IPTAL" if self._scan_cancelled else "HATA")
        self._render_scan_progress()
        self._maybe_finalize_central_scan()
        self._cleanup_scan_process()
        self._post_scan_trace("scan_finished_callback_returned", duration=time.perf_counter()-callback_started,
                              apply_count=self._scan_apply_count, active_threads=self._active_worker_count())
        if _CRASH_STREAM is not None:
            faulthandler.cancel_dump_traceback_later()

    def _cleanup_scan_process(self):
        if self.scan_process is not None:
            self.scan_process.deleteLater()
            self.scan_process = None

    def _start_analysis_workers(self, all_symbols):
        if self._analysis_workers_started or not self.scan_coordinator:
            return
        universes = build_analysis_universes(all_symbols, bist30_hisseleri())
        self._analysis_workers_started = True
        run_id = self.scan_coordinator.scan_id
        self._pending_analysis_universes = universes
        self.log.append(
            f"Görev evrenleri: Günlük {len(universes['daily_trade'])} · "
            f"Kısa {len(universes['short_term'])} · Orta {len(universes['medium_term'])} · "
            f"50 TL {len(universes['under_50'])} · Yüksek Hareket {len(universes['high_movement'])}"
        )
        try:
            universe_state = dict(self._scan_universe_meta)
            if not universe_state:
                from bist_evreni import son_evren_durumu
                universe_state = son_evren_durumu()
            source = universe_state.get("source") or "bilinmiyor"
            updated = universe_state.get("created_at") or universe_state.get("last_used_at") or "bilinmiyor"
            self.home.source.setText(f"VERİ KAYNAĞI\n{source}")
            self.log.append(f"Aktif BIST evreni: {len(all_symbols)} hisse | Kaynak: {source} | Güncelleme: {updated}")
            warning = universe_state.get("warning")
            if warning:
                self.log.append("EVREN UYARISI: " + str(warning))
                self.scan_progress.phase.setText("Eksik/önbellek evren uyarısı: " + str(warning))
        except Exception as exc:
            self.log.append("Evren kaynak bilgisi okunamadı: " + str(exc))
        # Bu görevlerin üçü de Python ağırlıklı hesap ve aynı piyasa verisi
        # önbelleğini kullanır. Aynı anda QThread olarak çalıştırılmaları Windows'ta
        # Qt olay döngüsünü aç bırakıp AppHangTransient üretiyordu. Kapsamı
        # daraltmadan sırayla çalıştır.
        if not self.daily_trade.start_scan(run_id, universes["daily_trade"]):
            self._component_failed("daily_trade", "Günlük Trade worker başlatılamadı.")
            self._start_next_auxiliary_worker("daily_trade", run_id)

    def _start_next_auxiliary_worker(self, completed_component, run_id):
        if not self.scan_coordinator or run_id != self.scan_coordinator.scan_id:
            return
        universes = getattr(self, "_pending_analysis_universes", {})
        if completed_component == "daily_trade":
            if not self.under_50.start_scan(run_id, universes.get("under_50", [])):
                self._component_failed("under_50", "50 TL Altı worker başlatılamadı.")
                self._start_next_auxiliary_worker("under_50", run_id)
        elif completed_component == "under_50":
            if not self.next_day.start_scan(run_id, universes.get("high_movement", [])):
                self._component_failed("high_movement", "Yüksek Hareket worker başlatılamadı.")

    def _worker_progress(self, component, run_id, completed, total, message):
        if not self.scan_coordinator or run_id != self.scan_coordinator.scan_id:
            return
        self.scan_coordinator.update_component_progress(component, completed, total, message)
        self._render_scan_progress()

    def _analysis_worker_finished(self, component, run_id, ok, frame, message):
        if not self.scan_coordinator or run_id != self.scan_coordinator.scan_id:
            return
        if self.scan_coordinator.components[component] in TERMINAL_STATES:
            return
        self._analysis_result_cache[(run_id, component)] = frame.copy()
        self._post_scan_trace("aux_worker_finished", component=component, ok=ok,
                              shape=list(frame.shape) if isinstance(frame, pd.DataFrame) else None)
        self.scan_coordinator.finish_component(component, "TAMAMLANDI" if ok else "HATA")
        if not ok:
            hata_gunlugune_yaz(f"{component} worker hatası", message)
        if component in {"daily_trade", "under_50"}:
            self._start_next_auxiliary_worker(component, run_id)
        self._render_scan_progress()
        self._maybe_finalize_central_scan()

    def _high_movement_finished(self, run_id, ok, message):
        if self.scan_coordinator is None or run_id != self.scan_coordinator.scan_id:
            return
        current = self.scan_coordinator.components["high_movement"]
        if current in TERMINAL_STATES:
            return
        self.scan_coordinator.finish_component("high_movement", "TAMAMLANDI" if ok else "HATA")
        frame = getattr(self.next_day, "_full", pd.DataFrame())
        self._post_scan_trace("aux_worker_finished", component="high_movement", ok=ok,
                              shape=list(frame.shape) if isinstance(frame, pd.DataFrame) else None)
        if ok:
            self._analysis_result_cache[(run_id, "high_movement")] = tag_analysis_result(frame, "high_movement", run_id)
        if not ok:
            hata_gunlugune_yaz("Yüksek Hareket worker hatası", message)
            self.log.append("Yüksek Hareket sonuçları hazırlanamadı; önceki sonuçlar korunuyor.")
        self._render_scan_progress(); self._maybe_finalize_central_scan()

    def _component_failed(self, name, message, state="HATA"):
        if self.scan_coordinator and self.scan_coordinator.components[name] not in TERMINAL_STATES:
            self.scan_coordinator.finish_component(name, state)
        self.log.append(message); hata_gunlugune_yaz(f"Tarama bileşeni: {name}", message)

    def _fail_dependent_components(self, state="HATA"):
        if not self.scan_coordinator: return
        for name in ("daily_trade", "short_term", "medium_term", "under_50", "watchlist", "portfolio", "performance"):
            if self.scan_coordinator.components[name] not in TERMINAL_STATES:
                self.scan_coordinator.finish_component(name, state)

    def _fail_central_scan(self, title, message):
        if self._scan_failure_shown: return
        self._scan_failure_shown = True
        if self.scan_coordinator:
            self._component_failed("core", message)
            self._fail_dependent_components()
            if self.scan_coordinator.components["high_movement"] not in TERMINAL_STATES:
                self.scan_coordinator.finish_component("high_movement", "HATA")
        if self.next_day.thread and self.next_day.thread.isRunning(): self.next_day.thread.requestInterruption()
        self._cleanup_scan_process(); self._finalize_central_scan()
        detail = message + " Önceki sonuçlar korundu."
        self.scan_progress.status.setText(title); self.scan_progress.phase.setText(detail)
        self.home.scan_status.setText(title + " · " + detail)

    def _refresh_portfolio_from_report(self):
        try:
            from analiz_deposu import anlik_goruntu_oku
            all_results = anlik_goruntu_oku(rapor_yolu()).get("Tum Sonuclar", pd.DataFrame())
            if all_results.empty or "Hisse" not in all_results: return
            wanted = {s.replace(".IS", "").upper() for s in self.track.symbols}
            frame = all_results[all_results["Hisse"].astype(str).str.replace(".IS", "", regex=False).str.upper().isin(wanted)].copy()
            if "Fiyat" in frame: frame["Güncel Fiyat"] = frame["Fiyat"]
            self.track.load(frame)
        except Exception as exc:
            self.log.append("Takip listesi/portföy görünümü yenilenemedi: " + str(exc))

    def _update_scan_elapsed(self):
        if self._scan_started_at is not None:
            self.scan_progress.elapsed.setText("Geçen süre: " + ScanProgressPanel.duration_text(time.monotonic() - self._scan_started_at))

    def _render_scan_progress(self):
        if not self.scan_coordinator: return
        item = self.scan_coordinator
        if item.phase in item.component_progress:
            completed, total = item.component_progress[item.phase]
            self.scan_progress.counts.setText(f"{completed} / {total}")
        else:
            self.scan_progress.counts.setText(f"{item.stock_completed} / {item.stock_total or '—'}")
        self.scan_progress.bar.setValue(item.percent)
        self.scan_progress.status.setText(item.message)
        self.scan_progress.phase.setText(item.message)

    def _maybe_finalize_central_scan(self):
        if self.scan_coordinator and self.scan_coordinator.all_terminal:
            self._finalize_central_scan()

    def _finalize_central_scan(self):
        if not self.scan_coordinator or not self.scan_coordinator.all_terminal: return
        self._scan_elapsed_timer.stop(); self._update_scan_elapsed(); self.top_header.set_scanning(False)
        item = self.scan_coordinator; ended = datetime.now(); elapsed = time.monotonic() - self._scan_started_at if self._scan_started_at else 0
        self.scan_progress.bar.setValue(100)
        if self._scan_cancelled:
            title = "Tarama iptal edildi"; detail = "Önceki sonuçlar korundu."
        elif item.any_error:
            title = "Tarama tamamlanamadı"; detail = "Hata ayrıntısı kaydedildi. Önceki geçerli sonuçlar korundu."
        else:
            title = f"Tarama tamamlandı: {ended.strftime('%H:%M:%S')}"
            detail = (f"Toplam süre: {ScanProgressPanel.duration_text(elapsed)} · {item.stock_total} hisse tarandı · "
                      f"{item.stock_valid} hisse için geçerli veri alındı · {item.stock_failed} hissede veri alınamadı")
            self.log.append("\nTARAMA TAMAMLANDI.")
        self.scan_progress.status.setText(title); self.scan_progress.phase.setText(detail)
        self.home.scan_status.setText(title + " · " + detail)
        self.log.append(title + " | " + detail)
        self.pages.setCurrentWidget(getattr(self, "_scan_target", self.home)); self._scan_target = self.home
        self._render_lazy_page(self.pages.currentWidget())
        self._post_scan_trace("scan_ui_ready", apply_count=self._scan_apply_count,
                              active_threads=self._active_worker_count(), lazy_pages=len(self._lazy_page_renderers))


def exception_hook(exc_type, exc_value, exc_tb):
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    hata_gunlugune_yaz("Yakalanmamış arayüz hatası", text)
    try:
        QMessageBox.critical(None, "Kritik Hata", text)
    except Exception:
        pass


def install_qt_smoke_test(window, app):
    """Yalniz test ortaminda gercek Qt tiklamasi, ekran goruntusu ve guvenli kapanis."""
    screenshot = os.getenv("BORSA_UI_SMOKE_SCREENSHOT", "").strip()
    if not screenshot:
        return
    started = time.monotonic()
    QTimer.singleShot(500, window.scan_button.click)
    timer = QTimer(window)

    def capture_when_started():
        coordinator = window.scan_coordinator
        visible = window.scan_progress.isVisible() and not window.scan_button.isEnabled()
        progressed = bool(coordinator and coordinator.stock_completed > 0)
        if not (visible and progressed) and time.monotonic() - started < 25:
            return
        path = Path(screenshot); path.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(path), "PNG")
        evidence = path.with_suffix(".txt")
        evidence.write_text(
            "\n".join((
                f"button_enabled={window.scan_button.isEnabled()}",
                f"button_text={window.scan_button.text()}",
                f"progress_visible={window.scan_progress.isVisible()}",
                f"process_program={window.scan_process.program() if window.scan_process else ''}",
                f"process_arguments={window.scan_process.arguments() if window.scan_process else []}",
                f"scan_id={coordinator.scan_id if coordinator else ''}",
                f"stock_progress={coordinator.stock_completed if coordinator else 0}/{coordinator.stock_total if coordinator else 0}",
            )), encoding="utf-8",
        )
        timer.stop(); window.cancel_scan()
        if window.scan_process is not None and window.scan_process.state() != QProcess.NotRunning:
            window.scan_process.kill(); window.scan_process.waitForFinished(1000)
        # Ağ çağrısında bekleyen test worker'ı Qt kapanışını geciktirebilir. Bu yalnız
        # BORSA_UI_SMOKE_SCREENSHOT ile etkinleşen, sonuç yazmayan smoke sürecidir.
        QTimer.singleShot(750, lambda: os._exit(0))

    timer.timeout.connect(capture_when_started); timer.start(250)


if __name__ == "__main__":
    if "--headless-scan" in sys.argv:
        import faulthandler
        import warnings
        import main as analiz_main

        warnings.filterwarnings(
            "ignore",
            message=r"Downcasting object dtype arrays.*",
            category=FutureWarning,
        )
        crash_log = veri_klasoru() / "tarama_cokme.log"
        with crash_log.open("a", encoding="utf-8") as crash_stream:
            faulthandler.enable(file=crash_stream, all_threads=True)
            raise SystemExit(int(analiz_main.main() or 0))
    else:
        import faulthandler

        # Qt/C uzantılarındaki sert kapanmalar sys.excepthook'a ulaşmaz; ayrı kaydet.
        _CRASH_STREAM = (veri_klasoru() / "arayuz_cokme.log").open("a", encoding="utf-8")
        faulthandler.enable(file=_CRASH_STREAM, all_threads=True)
        sys.excepthook = exception_hook
        app = QApplication(sys.argv)
        win = MainWindow()
        win.show()
        install_qt_smoke_test(win, app)
        sys.exit(app.exec())
