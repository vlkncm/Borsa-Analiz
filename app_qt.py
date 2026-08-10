import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

import pandas as pd
from gunluk_islem_plani import gun_sonu_plani, sabah_fiyat_kontrolu
from sosyal_medya_risk import sosyal_medya_risk_analizi
from PySide6.QtCore import Qt, QObject, Signal, QThread, QUrl, QTimer
from PySide6.QtGui import QIcon, QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QMessageBox, QFrame, QLineEdit, QAbstractItemView, QTabWidget,
    QDialog, QGridLayout, QScrollArea, QSizePolicy
)

APP_NAME = "Borsa Analiz Pro MAX"


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


def normalize_symbol(text: str) -> str:
    value = str(text or "").strip().upper()
    if not value:
        return ""
    return value if value.endswith(".IS") else value + ".IS"


def guvenli_sayi(value, default=0.0):
    try:
        number = float(value)
        return number if pd.notna(number) else default
    except (TypeError, ValueError):
        return default


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
            self.finished.emit(False, {}, traceback.format_exc())


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
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
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
        if len(df) <= 100:
            self.table.resizeColumnsToContents()
            for column in range(self.table.columnCount()):
                self.table.setColumnWidth(
                    column,
                    min(260, max(95, self.table.columnWidth(column) + 16)),
                )
        else:
            sample = df.head(80)
            for column, name in enumerate(df.columns):
                lengths = [len(str(name))]
                for value in sample.iloc[:, column]:
                    lengths.append(len("-" if pd.isna(value) else str(value)))
                self.table.setColumnWidth(
                    column,
                    min(260, max(95, max(lengths) * 7 + 32)),
                )
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

    def __init__(self, data, parent=None):
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
        title = QLabel("Profesyonel Yatırım Terminali")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.summary = QLabel("Son rapor yükleniyor...")
        self.summary.setObjectName("terminalSummary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        cards = QHBoxLayout()
        self.metric_labels = {}
        for key, caption in [
            ("total", "TARANAN"), ("short", "KISA VADE"),
            ("medium", "ORTA VADE"), ("long", "UZUN VADE"),
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
        self.kisa = SimpleTable("Kısa Vade Adayları", "5–20 iş günü · momentum ve hacim öncelikli")
        self.orta = SimpleTable("Orta Vade Adayları", "1–3 ay · trend ve risk/getiri dengeli")
        self.uzun = SimpleTable("Uzun Vade Adayları", "3–12 ay · faaliyet ve yıllık momentum öncelikli")
        self.onay = SimpleTable(
            "Yüksek Onaylı Adaylar — Garanti Değildir",
            "Yalnızca güncel veri, güçlü ortak teyit ve en az 1:1,8 risk/getiri koşullarını geçen en fazla 5 aday",
        )
        self.tum = SearchableTable(
            "Tüm BIST Sonuçları",
            "Herhangi bir hisseyi ara; kolon başlığına tıklayarak sırala.",
        )
        self.tabs.addTab(self.kisa, "KISA VADE")
        self.tabs.addTab(self.orta, "ORTA VADE")
        self.tabs.addTab(self.uzun, "UZUN VADE")
        self.tabs.addTab(self.onay, "YÜKSEK ONAY")
        self.tabs.addTab(self.tum, "TÜM BİST / ARAMA")
        for table in (self.kisa, self.orta, self.uzun, self.onay, self.tum):
            table.row_selected.connect(self.show_stock_detail)
        layout.addWidget(self.tabs, 1)

    def show_stock_detail(self, data):
        StockDetailDialog(data, self).exec()

    def update_summary(self, path: Path, counts, total=0, conviction=0):
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M") if path.exists() else "-"
        self.summary.setText(
            f"Son analiz: {when}   |   Kısa: {counts[0]}   Orta: {counts[1]}   Uzun: {counts[2]}   |   "
            "Liste boşsa kalite eşiğini geçen aday yoktur."
        )
        values = {
            "total": total, "short": counts[0], "medium": counts[1],
            "long": counts[2], "conviction": conviction,
        }
        for key, value in values.items():
            self.metric_labels[key].setText(str(value))


class ResponsiveChartLabel(QLabel):
    CHART_HEIGHT = 460

    def __init__(self):
        super().__init__("Bir hisse kodu yazıp analiz başlatın.")
        self._source_pixmap = QPixmap()
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
        self._source_pixmap = QPixmap()
        self._last_scaled_size = None
        self.clear()
        self.setText(message)

    def load_chart(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.show_message("Grafik dosyası görüntülenemedi.")
            return False
        self._source_pixmap = pixmap
        self._last_scaled_size = None
        self.setText("")
        self._refresh_pixmap()
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._source_pixmap.isNull():
            self._resize_timer.start()

    def _refresh_pixmap(self):
        if self._source_pixmap.isNull() or self.width() < 10 or self.height() < 10:
            return
        target_size = self.contentsRect().size()
        if self._last_scaled_size == target_size:
            return
        scaled = self._source_pixmap.scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._last_scaled_size = target_size
        self.setPixmap(scaled)


class SingleAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        self.last_result = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Tek Hisse Analizi")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        sub = QLabel(
            "Tek işlemde günlük ve haftalık trendi, piyasa rejimini, veri güvenini ve tarihsel "
            "kanıtı inceler; sonuç grafiğini ve açıklamalı teknik değerlendirmeyi birlikte gösterir."
        )
        sub.setWordWrap(True)
        sub.setObjectName("subText")
        layout.addWidget(sub)

        top = QHBoxLayout()
        self.symbol = QLineEdit()
        self.symbol.setPlaceholderText("Örnek: ASELS")
        self.symbol.returnPressed.connect(self.run)
        top.addWidget(self.symbol, 1)
        self.button = QPushButton("ANALİZ ET, GRAFİĞİ VE YORUMU GÖSTER")
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
            "Bir hisse kodu girildiğinde karar, alış bandı, hedef, stop ve model güveni burada gösterilir."
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
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)

    def run(self):
        symbol = normalize_symbol(self.symbol.text())
        if not symbol:
            QMessageBox.warning(self, "Hisse", "Bir hisse kodu yaz.")
            return
        if self.thread is not None and self.thread.isRunning():
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
        self.thread = QThread()
        self.worker = SingleWorker(symbol, "analysis")
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

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
        self.summary.setText(
            f"KARAR: {decision}   |   GÜNCEL: {price:.2f} TL   |   "
            f"ALIŞ: {buy_low:.2f}–{buy_high:.2f} TL   |   "
            f"HEDEF: {target:.2f} TL   |   STOP: {stop:.2f} TL   |   "
            f"MODEL OLASILIĞI: %{probability:.0f}"
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
        self.scroll.verticalScrollBar().setValue(0)

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
        try:
            cost = float(self.cost.text().replace(",", "."))
            if cost <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Maliyet", "Geçerli maliyet yaz.")
            return
        self.button.setEnabled(False)
        self.status.setText("Satış kararı hesaplanıyor...")
        self.thread = QThread()
        self.worker = SingleWorker(symbol, f"sale:{cost}")
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def done(self, ok, r, message):
        self.button.setEnabled(True)
        if not ok:
            self.result.setPlainText(message)
            return
        lines = [
            f"KARAR: {r.get('satis_karari', '-')}",
            f"GÜNCEL FİYAT: {r.get('price', 0):.2f} TL",
            f"MALİYET: {r.get('kullanici_maliyeti', 0):.2f} TL",
            f"KÂR/ZARAR: %{r.get('kar_zarar_yuzde', 0):.2f}",
            f"MODEL HEDEFİ: {r.get('onerilen_satis', 0):.2f} TL",
            f"YENİ STOP: {r.get('yeni_stop', 0):.2f} TL",
            f"KÂR REALİZASYONU: %{r.get('kar_realizasyon_orani', 0)}",
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
        label = "KAP Analizi" if kind == "kap" else "Faaliyet Raporu Analizi"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel(label)
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        sub = QLabel("Yalnızca seçtiğin hisse incelenir; toplu taramayı yavaşlatmaz.")
        sub.setObjectName("subText")
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
        self.button.setEnabled(False)
        self.status.setText("İnceleniyor...")
        self.thread = QThread()
        self.worker = InfoWorker(symbol, self.kind)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def done(self, ok, result, message):
        self.button.setEnabled(True)
        if not ok:
            self.result.setPlainText(message)
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

    def load(self, df):
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r, (_, row) in enumerate(df.iterrows()):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME + " v8.1.1")
        self.resize(1380, 820)
        icon = uygulama_klasoru() / "logo.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.thread = None
        self.worker = None
        self.pages = QStackedWidget()

        self.terminal = InvestmentTerminalPage()
        self.kisa = self.terminal.kisa
        self.orta = self.terminal.orta
        self.uzun = self.terminal.uzun
        self.onay = self.terminal.onay
        self.tum = self.terminal.tum
        self.single = SingleAnalysisPage()
        self.sale = SalePage()
        self.track = TrackPage()
        self.kap = SelectedInfoPage("kap")
        self.activity = SelectedInfoPage("activity")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        for p in [self.terminal, self.single, self.sale, self.track, self.kap, self.activity, self.log]:
            self.pages.addWidget(p)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(270)
        side_layout = QVBoxLayout(side)
        brand = QLabel("BORSA ANALİZ\nPRO MAX v8.1.1")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(brand)

        menu = [
            ("YATIRIM TERMİNALİ", 0),
            ("TEK HİSSE ANALİZİ", 1),
            ("SATIŞ KARARI", 2),
            ("TAKİP LİSTEM", 3),
            ("SEÇİLİ HİSSE KAP", 4),
            ("SEÇİLİ HİSSE FAALİYET", 5),
            ("CANLI LOG", 6),
        ]
        for text, index in menu:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, i=index: self.pages.setCurrentIndex(i))
            side_layout.addWidget(button)
        side_layout.addStretch()

        self.scan_button = QPushButton("TEK TUŞ PROFESYONEL TARAMA")
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

        self.setStyleSheet("""
            QMainWindow, QWidget { background:#020617; color:#e5e7eb; font-family:Arial; font-size:13px; }
            #sidebar { background:#0f172a; border-right:1px solid #334155; }
            #brand { font-size:20px; font-weight:bold; color:#38bdf8; padding:18px; }
            QPushButton { background:#1e293b; border:1px solid #334155; padding:11px; border-radius:7px; text-align:left; }
            QPushButton:hover { background:#334155; }
            #primary { background:#0369a1; font-weight:bold; text-align:center; }
            #pageTitle { font-size:24px; font-weight:bold; color:#f8fafc; }
            #subText { color:#94a3b8; }
            #pathText { color:#64748b; font-size:10px; padding:4px; }
            #terminalSummary { background:#0f172a; border:1px solid #1d4ed8; color:#bae6fd; padding:10px; border-radius:7px; }
            #metricCard { background:#0f172a; border:1px solid #334155; border-radius:9px; }
            #metricCaption { color:#94a3b8; font-size:10px; font-weight:bold; }
            #metricValue { color:#f8fafc; font-size:22px; font-weight:bold; }
            #riskBanner { background:#422006; border:1px solid #a16207; color:#fde68a; padding:8px; border-radius:6px; }
            #chartSummary { background:#0f172a; border:1px solid #0369a1; color:#bae6fd; padding:10px; border-radius:7px; }
            #chartCanvas { background:#0f172a; border:1px solid #334155; border-radius:8px; color:#64748b; padding:8px; }
            #analysisTitle { color:#38bdf8; font-size:18px; font-weight:bold; padding-top:10px; }
            #analysisText { background:#0f172a; border:1px solid #334155; color:#e2e8f0; line-height:1.4; }
            QTabBar::tab { background:#1e293b; color:#cbd5e1; padding:10px 24px; margin-right:2px; }
            QTabBar::tab:selected { background:#0369a1; color:white; }
            QLineEdit, QTextEdit, QTableWidget { background:#0f172a; border:1px solid #334155; border-radius:6px; padding:7px; }
            QHeaderView::section { background:#1e293b; color:#e5e7eb; padding:8px; border:0; }
            QTableWidget { gridline-color:#334155; }
        """)

        self.load_report()

    def load_report(self):
        path = rapor_yolu()
        if not path.exists():
            return
        try:
            sheets = pd.read_excel(path, sheet_name=None)
            self.kisa.load(sheets.get("Kisa Vade", pd.DataFrame()))
            self.orta.load(sheets.get("Orta Vade", pd.DataFrame()))
            self.uzun.load(sheets.get("Uzun Vade", pd.DataFrame()))
            all_results = sheets.get("Tum Sonuclar", pd.DataFrame()).copy()
            if "Fiyat" in all_results.columns:
                valid_price = pd.to_numeric(all_results["Fiyat"], errors="coerce")
                all_results = all_results[valid_price > 0].reset_index(drop=True)
            visible_columns = [
                "Hisse", "Veri Tarihi", "Yatırım Kararı", "Fırsat Seviyesi",
                "Veri Durumu", "Veri Gecikmesi (İş Günü)",
                "AI Güven Puanı", "v4 Güven Puanı", "Broker Aksiyon", "Fiyat",
                "Önerilen Alış Alt", "Önerilen Alış Üst", "Önerilen Satış",
                "Önerilen Stop", "Beklenen Getiri %", "Karar Risk/Getiri",
                "MTF Uyum", "Temel Puan", "Faaliyet Puanı", "KAP Etiket",
                "Karar Nedenleri",
            ]
            compact = all_results[[c for c in visible_columns if c in all_results.columns]].copy()
            self.tum.load(compact)

            def numeric(name, default=0):
                if name not in all_results.columns:
                    return pd.Series(default, index=all_results.index, dtype=float)
                return pd.to_numeric(all_results[name], errors="coerce").fillna(default)

            decision = all_results.get("Yatırım Kararı", pd.Series("", index=all_results.index)).astype(str)
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
            high_conviction = high_conviction.head(5)
            conviction_columns = [
                "Hisse", "Yatırım Kararı", "Fiyat", "Önerilen Alış Alt",
                "Önerilen Alış Üst", "Önerilen Satış", "Önerilen Stop",
                "Beklenen Getiri %", "Karar Risk/Getiri", "Model Olasılığı %",
                "v4 Güven Puanı", "Karar Nedenleri",
            ]
            self.onay.load(high_conviction[[c for c in conviction_columns if c in high_conviction.columns]])
            self.terminal.update_summary(
                path,
                (self.kisa.table.rowCount(), self.orta.table.rowCount(), self.uzun.table.rowCount()),
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
        if self.thread is not None and self.thread.isRunning():
            return
        self.scan_button.setEnabled(False)
        self.pages.setCurrentIndex(6)
        self.log.clear()
        self.thread = QThread()
        self.worker = ScanWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log.append)
        self.worker.finished.connect(self.scan_done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def scan_done(self, ok, message):
        self.scan_button.setEnabled(True)
        if ok:
            self.log.append("\nTARAMA TAMAMLANDI.")
            self.load_report()
            self.log.append(f"Excel raporu: {rapor_yolu()}")
            self.pages.setCurrentIndex(0)
        else:
            self.log.append(message)


def exception_hook(exc_type, exc_value, exc_tb):
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        QMessageBox.critical(None, "Kritik Hata", text)
    except Exception:
        pass


if __name__ == "__main__":
    sys.excepthook = exception_hook
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
