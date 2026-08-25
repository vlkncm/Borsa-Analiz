import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

import pandas as pd
from gunluk_trade_gostergeleri import en_iyi_gunluk_trade_adaylari
from sade_karar_modeli import (
    elli_tl_adaylari, elli_tl_ohlcv_adayi, en_iyi_vade, gunluk_rapor_adaylari, on_x_senaryosu,
    orta_vadeden_kisa_adaylari_cikar, sade_firsatlar, sure_metni, vade_rapor_adaylari,
)
from bist_evreni import likit_120_sec
from bist30 import normalize_bist_sembolu
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
    QCheckBox
)

APP_NAME = "Borsa Analiz Pro MAX"
APP_VERSION = "10.1.2"
_CRASH_STREAM = None


def uygulama_klasoru() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def veri_klasoru() -> Path:
    base = Path.home() / "Documents" / "Borsa Analiz Pro MAX"
    base.mkdir(parents=True, exist_ok=True)
    return base


def rapor_yolu() -> Path:
    output = veri_klasoru() / "output"
    primary = output / "Borsa_Analiz_Pro_MAX_Rapor.xlsx"
    if primary.exists():
        return primary
    alternatives = sorted(output.glob("Borsa_Analiz_Pro_MAX_Rapor_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return alternatives[0] if alternatives else primary


def tarama_alt_sureci_komutu():
    """Kaynak kod ve PyInstaller EXE için güvenli tarama alt süreci komutu."""
    if getattr(sys, "frozen", False):
        worker = uygulama_klasoru() / "BorsaTaramaMotoru.exe"
        return str(worker), []
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

    def __init__(self, symbol, mode):
        super().__init__()
        self.symbol = symbol
        self.mode = mode

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


class SimpleTable(QWidget):
    row_selected = Signal(object)

    def __init__(self, title, subtitle=""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setObjectName("subText")
            layout.addWidget(sub)
        self.info = QLabel("Henüz analiz yapılmadı.")
        self.info.setObjectName("subText")
        layout.addWidget(self.info)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._emit_selected_row)
        layout.addWidget(self.table, 1)
        self._data = pd.DataFrame()

    def _emit_selected_row(self, row, _column):
        marker = self.table.item(row, 0)
        source_row = marker.data(Qt.UserRole) if marker is not None else row
        if source_row is not None and 0 <= int(source_row) < len(self._data):
            self.row_selected.emit(self._data.iloc[int(source_row)].to_dict())

    def load(self, df):
        if df is None:
            df = pd.DataFrame()
        self._data = df.reset_index(drop=True).copy()
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r, (_, row) in enumerate(df.iterrows()):
            for c, value in enumerate(row):
                if pd.isna(value):
                    text = "-"
                elif isinstance(value, float):
                    text = f"{value:.2f}"
                else:
                    text = str(value)
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, r)
                column_name = str(df.columns[c])
                item.setToolTip(text)
                if column_name in {"Yatırım Kararı", "İşlem Durumu", "Broker Aksiyon"}:
                    if "AL" in text and "ALMA" not in text:
                        item.setForeground(QColor("#22c55e"))
                    elif "ALMA" in text or "SAT" in text:
                        item.setForeground(QColor("#ef4444"))
                    elif "BEKLE" in text or "TUT" in text:
                        item.setForeground(QColor("#f59e0b"))
                elif column_name in {"Sinyal Güveni", "Fırsat Seviyesi"}:
                    if "ÇOK YÜKSEK" in text or "ÇOK GÜÇLÜ" in text:
                        item.setForeground(QColor("#22c55e"))
                    elif "YÜKSEK" in text or "GÜÇLÜ" in text:
                        item.setForeground(QColor("#38bdf8"))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        self.info.setText(f"Gösterilen hisse: {len(df)}")


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
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hisse veya karar ara... (örnek: ASELS, AL, TUT)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.layout().insertWidget(3, self.search)

    def apply_filter(self, text):
        needle = str(text or "").strip().casefold()
        visible = 0
        for row in range(self.table.rowCount()):
            haystack = " ".join(
                self.table.item(row, col).text()
                for col in range(self.table.columnCount())
                if self.table.item(row, col) is not None
            ).casefold()
            show = not needle or needle in haystack
            self.table.setRowHidden(row, not show)
            visible += int(show)
        self.info.setText(f"Gösterilen / toplam: {visible} / {self.table.rowCount()}")


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
        for table in (self.buy, self.wait, self.avoid, self.onay, self.tum):
            table.row_selected.connect(self.show_stock_detail)
        layout.addWidget(self.tabs, 1)

    def show_stock_detail(self, data):
        StockDetailDialog(data, self).exec()

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

        self.status = QLabel("")
        self.status.setObjectName("subText")
        layout.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)

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
        self.worker = SingleWorker(symbol, "analysis")
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
        from takip_modulu import takip_listesini_oku, takip_listesini_yaz, takip_fiyatlarini_getir
        self.read_list = takip_listesini_oku
        self.write_list = takip_listesini_yaz
        self.get_prices = takip_fiyatlarini_getir
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
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
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
        df = pd.DataFrame({"Hisse": [s.replace(".IS", "") for s in self.symbols]})
        self.load(df)

    def refresh(self):
        self.load(self.get_prices(self.symbols))

    def remove(self, symbol):
        symbol = normalize_symbol(symbol)
        if not symbol or symbol not in self.symbols:
            return
        self.symbols.remove(symbol)
        self.write_list(self.symbols)
        self.show_symbols()

    def load(self, df):
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns) + 1)
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns] + ["İşlem"])
        for r, (_, row) in enumerate(df.iterrows()):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
            symbol = normalize_symbol(row.get("Hisse", ""))
            remove_button = QPushButton("SİL")
            remove_button.setToolTip(f"{symbol.replace('.IS', '')} hissesini takip listesinden çıkar")
            remove_button.clicked.connect(lambda checked=False, value=symbol: self.remove(value))
            self.table.setCellWidget(r, len(df.columns), remove_button)
        self.table.horizontalHeader().setSectionResizeMode(
            len(df.columns), QHeaderView.ResizeToContents
        )


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
        self.selection.setMinimumHeight(310)
        self.selection.setPlainText(
            "Tarama sonunda şartları geçen en fazla 3 risk-ayarlı fon adayı; kurum, kademeli alım, 2-3 aylık hedef ve çıkış koşuluyla gösterilir."
        )
        layout.addWidget(self.selection)
        self.table = SearchableTable(
            "Yüksek Getiri ve Fon Karar Adayları",
            "Tablo puana göre sıralanır. Bir aylık yükselişi aşırı hızlanan fonlarda 'kovalama' uyarısı verilir.",
        )
        self.table.row_selected.connect(self.show_detail)
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
        StockDetailDialog(data, self, show_chart=False).exec()


class DailyTradeWorker(QObject):
    finished = Signal(bool, object, str)
    progress = Signal(str)

    def __init__(self, interval, account, risk, min_rr, confirmed_only):
        super().__init__()
        self.interval, self.account, self.risk = interval, account, risk
        self.min_rr, self.confirmed_only = min_rr, confirmed_only

    def run(self):
        try:
            from bist_evreni import tum_bist_hisseleri
            from gunluk_trade_motoru import gunluk_trade_analiz
            rows = []
            symbols = tum_bist_hisseleri()
            for index, symbol in enumerate(symbols, 1):
                if QThread.currentThread().isInterruptionRequested():
                    break
                self.progress.emit(f"{index}/{len(symbols)} {symbol.replace('.IS','')} inceleniyor...")
                row = gunluk_trade_analiz(
                    symbol, interval=self.interval, hesap_buyuklugu=self.account or None,
                    risk_yuzdesi=self.risk, min_risk_getiri=self.min_rr,
                    sadece_teyitli=self.confirmed_only,
                )
                if not self.confirmed_only or row.get("Sonuç") == "AL ADAYI":
                    rows.append(row)
            self.finished.emit(True, pd.DataFrame(rows), "Tarama tamamlandı.")
        except Exception:
            self.finished.emit(False, pd.DataFrame(), traceback.format_exc())


class DailyTradePage(QWidget):
    """Gecikme ve kanıt durumunu gizlemeden sunan günlük trade karar-destek sayfası."""
    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        self.results = pd.DataFrame()
        self.report_fallback = pd.DataFrame()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("GÜNLÜK TRADE")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        warning = QLabel(
            "Karar-destek ve kâğıt işlem ekranıdır; gerçek emir göndermez. Yahoo intraday veri ücretsizdir, "
            "gecikmesi garanti edilmez. Geçmiş performans gelecekteki sonucu garanti etmez."
        )
        warning.setWordWrap(True)
        warning.setObjectName("riskBanner")
        layout.addWidget(warning)
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
        layout.addLayout(controls)
        self.status = QLabel("Henüz tarama yapılmadı.")
        self.status.setObjectName("subText")
        layout.addWidget(self.status)
        self.table = SimpleTable("Adaylar", "Uygun aday yoksa liste boş bırakılır.")
        self.table.row_selected.connect(self.show_detail)
        layout.addWidget(self.table, 1)
        self.paper_button = QPushButton("SEÇİLİ SATIRI KÂĞIT İŞLEM OLARAK KAYDET")
        self.paper_button.clicked.connect(self.save_selected)
        layout.addWidget(self.paper_button)
        self.scan_button.clicked.connect(self.start_scan)

    def start_scan(self):
        if self.thread and self.thread.isRunning():
            return
        self.scan_button.setEnabled(False)
        self.status.setText("Aktif BIST evreni tamamlanmış intraday mumlarla taranıyor...")
        self.thread = QThread(self)
        self.worker = DailyTradeWorker(self.interval.currentText(), self.account.value(), self.risk.value(),
                                       self.min_rr.value(), self.confirmed.isChecked())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.scan_done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

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
            display["_pot"] = pd.to_numeric(display.get("Hedef Potansiyeli %", 0), errors="coerce").fillna(0)
            display["_rr"] = pd.to_numeric(display.get("Risk/Getiri", 0), errors="coerce").fillna(0)
            display = display.sort_values(["_öncelik", "_pot", "_rr"], ascending=False).head(5)
            columns = ["Hisse", "Sonuç", "Referans Fiyat", "Alış Alt", "Alış Üst", "Hedef", "Stop", "Hedef Potansiyeli %", "Risk/Getiri"]
            display = display[[c for c in columns if c in display.columns]].reset_index(drop=True)
        if display.empty and not self.report_fallback.empty:
            display = self.report_fallback.copy()
        self.table.load(display)
        if not ok:
            self.status.setText("Tarama hatası: " + message.splitlines()[-1])
        elif display.empty:
            self.status.setText("Bugün ölçütleri geçen aday bulunamadı. Veri yetersiz/gecikmeli sonuçlardan işlem üretilmedi.")
        elif "Karar" in display.columns and display["Karar"].astype(str).eq("GÜNCEL FİYATLA DOĞRULA").any():
            self.status.setText("Canlı intraday veri alınamadı. Son güvenilir günlük analiz gösteriliyor; işlem öncesinde güncel fiyatı doğrulayın.")
        else:
            counts = display["Sonuç"].value_counts().to_dict()
            self.status.setText(f"Tarama tamamlandı: {counts} | Çift tıklayarak ayrıntıları açın.")

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
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 12, 16, 12); layout.setSpacing(10)
        top = QFrame(); top.setObjectName("topStrip"); top_box = QHBoxLayout(top)
        self.index_value = QLabel("BIST 100\nVeri bekleniyor"); self.index_value.setObjectName("topMetric")
        self.market = QLabel("PİYASA DURUMU\nVERİ BEKLENİYOR"); self.market.setObjectName("topMetric")
        self.source = QLabel("VERİ KAYNAĞI\nGecikmeli (15 dk)"); self.source.setObjectName("topMetric")
        self.clock = QLabel(datetime.now().strftime("%d.%m.%Y\n%H:%M")); self.clock.setObjectName("topMetric")
        for widget in (self.index_value, self.market, self.source): top_box.addWidget(widget, 1)
        top_box.addStretch(); top_box.addWidget(self.clock); layout.addWidget(top)

        summary = QFrame(); summary.setObjectName("dashboardPanel"); summary_box = QHBoxLayout(summary)
        left = QVBoxLayout(); title = QLabel("BUGÜNÜN DURUMU"); title.setObjectName("sectionTitle"); left.addWidget(title)
        cards = QHBoxLayout(); self.counts = {}
        for key, caption in (("trade", "Günlük Trade"), ("short", "Kısa Vade"), ("medium", "Orta Vade"), ("growth", "Büyüme Adayları")):
            value = QLabel(f"{caption}\n0\nuygun aday"); value.setObjectName("summaryMetric"); cards.addWidget(value); self.counts[key] = value
        left.addLayout(cards); summary_box.addLayout(left, 2)
        self.trade_button = QPushButton("BUGÜNÜN TRADE\nADAYLARINI BUL\nEn iyi 5 hisseyi analiz et"); self.trade_button.setObjectName("heroButton")
        self.trade_button.clicked.connect(self.trade_requested.emit); summary_box.addWidget(self.trade_button, 1); layout.addWidget(summary)

        content = QHBoxLayout(); tables = QGridLayout(); tables.setSpacing(8); self.preview_tables = {}
        for column, (key, caption) in enumerate((("trade", "GÜNLÜK TRADE – EN İYİ 5"), ("short", "KISA VADE – EN İYİ 5"), ("medium", "ORTA VADE – EN İYİ 5"))):
            panel = QFrame(); panel.setObjectName("dashboardPanel"); box = QVBoxLayout(panel)
            label = QLabel(caption); label.setObjectName("tableTitle"); box.addWidget(label)
            table = QTableWidget(0, 6); table.setHorizontalHeaderLabels(["Hisse", "Alım", "Hedef", "Stop", "Potansiyel", "Skor"])
            table.verticalHeader().setVisible(False); table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            box.addWidget(table); self.preview_tables[key] = table; tables.addWidget(panel, 0, column)
        content.addLayout(tables, 4)
        rail = QVBoxLayout()
        self.portfolio_summary = QLabel("TAKİP LİSTEM ÖZETİ\n\nKayıtlı hisse: 0\nGüncel değer: —"); self.portfolio_summary.setObjectName("sidePanel")
        self.performance = QLabel("SON PERFORMANS (30 İŞLEM)\n\nHenüz sonuçlanmış işlem yok"); self.performance.setObjectName("sidePanel")
        rail.addWidget(self.portfolio_summary); rail.addWidget(self.performance); rail.addStretch(); content.addLayout(rail, 1)
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
        parts = str(data.get("Alım Bölgesi", "")).replace("TL", "").replace("–", "-").split("-")
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
        self.layout().insertWidget(3, button)


class Under50Worker(QObject):
    finished = Signal(bool, object, str)
    progress = Signal(str)

    def run(self):
        try:
            from bist_evreni import tum_bist_hisseleri
            from veri_saglayici import get_daily_ohlcv
            symbols, rows = tum_bist_hisseleri(), []
            for index, symbol in enumerate(symbols, 1):
                if QThread.currentThread().isInterruptionRequested():
                    break
                self.progress.emit(f"{index}/{len(symbols)} hisse inceleniyor · {len(rows)} aday bulundu")
                try:
                    history, _meta = get_daily_ohlcv(symbol, "1y")
                    candidate = elli_tl_ohlcv_adayi(symbol, history)
                    if candidate:
                        rows.append(candidate)
                except Exception:
                    continue
            frame = pd.DataFrame(rows)
            if not frame.empty:
                frame = frame.sort_values(["Skor", "Risk/Getiri", "Ortalama İşlem Tutarı"], ascending=False).head(20)
                frame = frame.drop(columns=["Ortalama İşlem Tutarı"], errors="ignore").reset_index(drop=True)
            self.finished.emit(True, frame, f"{len(symbols)} BIST hissesi tarandı; en iyi {len(frame)} aday gösteriliyor.")
        except Exception:
            self.finished.emit(False, pd.DataFrame(), traceback.format_exc())


class Under50Page(FullMarketPage):
    def __init__(self):
        super().__init__("50 TL ALTI HİSSE FIRSATLARI", "613 aktif BIST hissesi doğrudan taranır; iPhone ile aynı formülle en iyi 20 sonuç gösterilir.")
        self.thread = None; self.worker = None
        button = self.layout().itemAt(3).widget()
        button.clicked.disconnect()
        button.setText("613 BIST HİSSESİNİ TARA")
        button.clicked.connect(self.start_scan)

    def start_scan(self):
        if self.thread and self.thread.isRunning(): return
        self.info.setText("Tüm BIST 50 TL altı taraması başlatılıyor…")
        self.thread = QThread(self); self.worker = Under50Worker(); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.progress.connect(self.info.setText)
        self.worker.finished.connect(self.done); self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self._clear)
        self.thread.start()

    def done(self, ok, frame, message):
        if ok: self.load(frame); self.info.setText(message)
        else: self.info.setText("Tarama hatası: " + message.splitlines()[-1])

    def _clear(self):
        self.worker = None; self.thread = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME + " v" + APP_VERSION)
        self.resize(1366, 768)
        icon = uygulama_klasoru() / "logo.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.scan_process = None
        self._scan_stdout_buffer = ""
        self._scan_stderr_buffer = ""
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
        self.medium_term = DecisionPage("ORTA VADE FIRSATLARI", "Model hedefi ve süre tahmindir; kesin fiyat garantisi değildir.")
        self.under_50 = Under50Page()
        self.ten_x = FullMarketPage("10X POTANSİYEL SENARYOSU", "Tüm BIST taranır. Senaryo çok yüksek belirsizlik içerir ve kesin getiri tahmini değildir.")
        self.history = SimpleTable("GEÇMİŞ PERFORMANS", "Geçmiş önerilerin gerçekleşen sonuçları.")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        for p in [self.home, self.daily_trade, self.short_term, self.medium_term,
                  self.under_50, self.ten_x, self.track, self.sale, self.single,
                  self.history, self.log]:
            self.pages.addWidget(p)

        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        side_layout = QVBoxLayout(side)
        brand = QLabel("BORSA ANALİZ\nPRO MAX v" + APP_VERSION)
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(brand)

        menu = [
            ("BUGÜN", self.home), ("  Günlük Trade", self.daily_trade),
            ("KISA VADE", self.short_term), ("ORTA VADE", self.medium_term),
            ("BÜYÜME · 50 TL Altı", self.under_50), ("  10X Potansiyel", self.ten_x),
            ("TAKİP LİSTEM", self.track), ("  Satış / Çıkış Kararı", self.sale),
            ("DETAY · Hisse İncele", self.single), ("GEÇMİŞ", self.history),
        ]
        for text, page in menu:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, p=page: self.pages.setCurrentWidget(p))
            side_layout.addWidget(button)
        side_layout.addStretch()

        self.scan_button = QPushButton("YENİ ANALİZ YAP")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.scan)
        side_layout.addWidget(self.scan_button)

        self.reload_button = QPushButton("SON RAPORU YÜKLE")
        self.reload_button.clicked.connect(self.load_report)
        side_layout.addWidget(self.reload_button)


        self.open_report_button = QPushButton("EXCEL RAPORUNU AÇ")
        self.open_report_button.clicked.connect(self.open_report)
        side_layout.addWidget(self.open_report_button)

        self.open_folder_button = QPushButton("RAPOR KLASÖRÜNÜ AÇ")
        self.open_folder_button.clicked.connect(self.open_report_folder)
        side_layout.addWidget(self.open_folder_button)

        self.report_path_label = QLabel(str(rapor_yolu()))
        self.report_path_label.setWordWrap(True)
        self.report_path_label.setObjectName("pathText")
        side_layout.addWidget(self.report_path_label)

        root.addWidget(side)
        root.addWidget(self.pages, 1)

        bg_path = (uygulama_klasoru() / "assets" / "terminal-background-v1.png").as_posix()
        style_sheet = """
            QMainWindow, QWidget {{ background:#071521; color:#f4f7fb; font-family:Segoe UI, Arial; font-size:12px; }}
            #appRoot {{ background:#071521; }}
            #sidebar {{ background:#06111c; border-right:1px solid #203648; }}
            QStackedWidget {{ background:#0a1825; border-left:1px solid #203648; }}
            #brand {{ font-size:20px; font-weight:800; color:#ffffff; padding:14px 8px; }}
            QPushButton {{ background:transparent; color:#cbd5e1; border:0; border-bottom:1px solid #172a3a; padding:6px 10px; border-radius:6px; text-align:left; font-weight:600; }}
            QPushButton:hover {{ background:#102535; color:#68e05f; }}
            #primary {{ background:#45a839; color:#ffffff; font-weight:800; text-align:center; border:1px solid #6ad75b; }}
            #heroButton {{ background:#4daf3d; border:1px solid #6ad75b; color:white; font-size:16px; min-height:86px; text-align:center; font-weight:800; border-radius:10px; }}
            #topStrip, #dashboardPanel {{ background:#0d1d2b; border:1px solid #21384b; border-radius:11px; }}
            #topMetric {{ color:#e7edf5; padding:6px 14px; border-right:1px solid #203648; }}
            #sectionTitle, #tableTitle {{ color:#f8fafc; font-weight:800; font-size:13px; }}
            #summaryMetric {{ color:#65dc57; font-size:15px; font-weight:800; padding:5px 16px; border-right:1px solid #21384b; }}
            #sidePanel {{ background:#0d1d2b; color:#e5edf6; border:1px solid #21384b; border-radius:10px; padding:15px; line-height:1.5; }}
            #footerText, #subText, #pathText {{ color:#95a7b8; }}
            #pageTitle {{ font-size:20px; font-weight:800; color:#ffffff; }}
            #riskBanner {{ background:#102535; border:1px solid #29465d; color:#d8e4ee; padding:8px; border-radius:6px; }}
            #terminalSummary, #metricCard, #chartSummary, #chartCanvas, #analysisText {{ background:#0d1d2b; border:1px solid #21384b; color:#ffffff; border-radius:7px; }}
            #metricCaption {{ color:#9fb0c0; font-size:11px; font-weight:bold; }} #metricValue {{ color:#65dc57; font-size:20px; font-weight:bold; }}
            #analysisTitle {{ color:#65dc57; font-size:16px; font-weight:bold; }}
            QTabBar::tab {{ background:#0d1d2b; color:#cbd5e1; padding:8px 18px; border:1px solid #21384b; }} QTabBar::tab:selected {{ background:#18354a; color:#65dc57; }}
            QLineEdit, QTextEdit, QDoubleSpinBox, QComboBox {{ background:#091622; color:#ffffff; border:1px solid #29465d; border-radius:6px; padding:6px; }}
            QTableWidget {{ background:#0b1926; color:#f4f7fb; border:1px solid #21384b; border-radius:7px; alternate-background-color:#0f2130; gridline-color:#203648; font-size:12px; }}
            QTableWidget::item {{ color:#f4f7fb; padding:4px; }} QTableWidget::item:selected {{ background:#24503c; color:#ffffff; }}
            QHeaderView::section {{ background:#102434; color:#dce6ef; padding:7px; border:0; border-right:1px solid #203648; font-weight:600; font-size:12px; }}
        """
        self.setStyleSheet(
            style_sheet.replace("__BACKGROUND__", bg_path).replace("{{", "{").replace("}}", "}")
        )

        self.home.trade_requested.connect(lambda: self.pages.setCurrentWidget(self.daily_trade))
        self.ten_x.scan_requested.connect(lambda: self.scan_all_market(self.ten_x))
        self.pages.setCurrentWidget(self.home)

        self.load_report()

    def load_report(self):
        path = rapor_yolu()
        if not path.exists():
            return
        try:
            sheets = pd.read_excel(path, sheet_name=None)
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
            self.tum.load(compact)

            trade_frame = sade_firsatlar(all_results, "gunluk", limit=5, sure="Gün içi")
            if trade_frame.empty:
                trade_frame = gunluk_rapor_adaylari(all_results, limit=5)
            self.daily_trade.report_fallback = trade_frame.copy()
            self.daily_trade.table.load(trade_frame)

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
            self.short_term.load(short_frame)
            self.short_term.info.setText(f"{len(short_frame)} aday · Süre dayanağı: {short_evidence}")
            self.medium_term.load(medium_frame)
            self.medium_term.info.setText(f"{len(medium_frame)} aday · Süre dayanağı: {medium_evidence}")
            under_frame = elli_tl_adaylari(likit_120_sec(all_results), limit=20)
            ten_frame = on_x_senaryosu(all_results, limit=5)
            self.under_50.load(under_frame)
            self.ten_x.load(ten_frame)
            self.history.load(sheets.get("Sinyal Gecmisi", pd.DataFrame()).tail(30))
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
            self.home.update_state(trade_frame, short_frame, medium_frame, market, len(under_frame) + len(ten_frame))

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
            self.buy.load(buy_results[decision_columns].copy())
            self.wait.load(wait_results[decision_columns].copy())
            self.avoid.load(avoid_results[decision_columns].copy())
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
            self.onay.load(high_conviction[[c for c in conviction_columns if c in high_conviction.columns]])
            self.terminal.update_summary(
                path,
                (self.buy.table.rowCount(), self.wait.table.rowCount(), self.avoid.table.rowCount()),
                total=len(all_results),
                conviction=len(high_conviction),
            )
            self.report_path_label.setText(str(path))
        except Exception as exc:
            QMessageBox.warning(self, "Rapor", str(exc))

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
        if self.scan_process is not None and self.scan_process.state() != QProcess.NotRunning:
            return
        self.scan_button.setEnabled(False)
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
        environment.insert("BORSA_TARAMA_EVRENI", getattr(self, "_scan_universe", "BIST30"))
        self.scan_process.setProcessEnvironment(environment)
        self.scan_process.readyReadStandardOutput.connect(self._read_scan_stdout)
        self.scan_process.readyReadStandardError.connect(self._read_scan_stderr)
        self.scan_process.errorOccurred.connect(self._scan_process_error)
        self.scan_process.finished.connect(self._scan_process_finished)
        self.scan_process.start()

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

    def _append_process_text(self, text, is_error=False):
        attr = "_scan_stderr_buffer" if is_error else "_scan_stdout_buffer"
        buffer = getattr(self, attr) + text
        lines = buffer.split("\n")
        setattr(self, attr, lines.pop())
        for line in lines:
            if line.strip():
                self.log.append(line.rstrip())
                if getattr(self, "_scan_target", None) is self.daily_trade:
                    self.daily_trade.info.setText(line.rstrip())

    def _read_scan_stdout(self):
        if self.scan_process is not None:
            text = bytes(self.scan_process.readAllStandardOutput()).decode("utf-8", errors="replace")
            self._append_process_text(text)

    def _read_scan_stderr(self):
        if self.scan_process is not None:
            text = bytes(self.scan_process.readAllStandardError()).decode("utf-8", errors="replace")
            self._append_process_text(text, is_error=True)

    def _scan_process_error(self, error):
        if self.scan_process is not None:
            self.log.append(f"Tarama işlemi başlatma/çalışma hatası: {self.scan_process.errorString()} ({error})")

    def _scan_process_finished(self, exit_code, exit_status):
        self._read_scan_stdout()
        self._read_scan_stderr()
        for attr in ("_scan_stdout_buffer", "_scan_stderr_buffer"):
            tail = getattr(self, attr).strip()
            if tail:
                self.log.append(tail)
            setattr(self, attr, "")
        ok = exit_status == QProcess.NormalExit and exit_code == 0
        if not ok and rapor_yolu().exists():
            self.log.append(
                "Tarama alt süreci normal kapanmadı; ana program korundu ve oluşan son rapor yükleniyor."
            )
        self.scan_done(ok, f"Alt süreç çıkış kodu: {exit_code}")
        if self.scan_process is not None:
            self.scan_process.deleteLater()
            self.scan_process = None

    def scan_done(self, ok, message):
        self.scan_button.setEnabled(True)
        if ok:
            self.log.append("\nTARAMA TAMAMLANDI.")
            self.load_report()
            self.log.append(f"Excel raporu: {rapor_yolu()}")
            self.pages.setCurrentWidget(getattr(self, "_scan_target", self.home))
            self._scan_target = self.home
            self._scan_universe = "BIST30"
        else:
            self.log.append(message)
            if rapor_yolu().exists():
                self.load_report()


def exception_hook(exc_type, exc_value, exc_tb):
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    hata_gunlugune_yaz("Yakalanmamış arayüz hatası", text)
    try:
        QMessageBox.critical(None, "Kritik Hata", text)
    except Exception:
        pass


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
            analiz_main.main()
    else:
        import faulthandler

        # Qt/C uzantılarındaki sert kapanmalar sys.excepthook'a ulaşmaz; ayrı kaydet.
        _CRASH_STREAM = (veri_klasoru() / "arayuz_cokme.log").open("a", encoding="utf-8")
        faulthandler.enable(file=_CRASH_STREAM, all_threads=True)
        sys.excepthook = exception_hook
        app = QApplication(sys.argv)
        win = MainWindow()
        win.show()
        sys.exit(app.exec())
