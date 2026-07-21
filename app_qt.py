import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

import pandas as pd
from PySide6.QtCore import Qt, QObject, Signal, QThread, QUrl
from PySide6.QtGui import QIcon, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QMessageBox, QFrame, QLineEdit, QAbstractItemView, QTabWidget,
    QDialog, QGridLayout, QScrollArea, QDoubleSpinBox
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

            result = teknik_analiz(self.symbol, "TEK HİSSE")
            if not result:
                self.finished.emit(False, {}, "Yeterli fiyat verisi bulunamadı.")
                return
            result.update(v4_puanla(result, final=False))
            result.update(karar_uret(result))
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
        self.table.resizeColumnsToContents()
        for column in range(self.table.columnCount()):
            self.table.setColumnWidth(column, min(260, max(95, self.table.columnWidth(column) + 16)))
        self.table.resizeRowsToContents()
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


class PortfolioPage(QWidget):
    def __init__(self):
        super().__init__()
        self.results = pd.DataFrame()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Risk Bazlı Portföy ve Lot Planı")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        info = QLabel(
            "Her işlemde kabul edilen azami zarara ve stop mesafesine göre lot hesaplar. "
            "Bu ekran emir göndermez ve alarm üretmez."
        )
        info.setObjectName("subText")
        info.setWordWrap(True)
        layout.addWidget(info)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Sermaye (TL)"))
        self.capital = QDoubleSpinBox()
        self.capital.setRange(1000, 1000000000)
        self.capital.setDecimals(0)
        self.capital.setValue(100000)
        self.capital.setSingleStep(10000)
        controls.addWidget(self.capital)
        controls.addWidget(QLabel("İşlem başı risk (%)"))
        self.risk = QDoubleSpinBox()
        self.risk.setRange(0.1, 5.0)
        self.risk.setDecimals(1)
        self.risk.setValue(1.0)
        self.risk.setSingleStep(0.1)
        controls.addWidget(self.risk)
        controls.addWidget(QLabel("Hisse başı üst sınır (%)"))
        self.position_limit = QDoubleSpinBox()
        self.position_limit.setRange(1.0, 50.0)
        self.position_limit.setDecimals(1)
        self.position_limit.setValue(20.0)
        controls.addWidget(self.position_limit)
        calculate = QPushButton("LOT PLANINI HESAPLA")
        calculate.setObjectName("primary")
        calculate.clicked.connect(self.calculate)
        controls.addWidget(calculate)
        controls.addStretch()
        layout.addLayout(controls)
        self.table = SimpleTable("Örnek Pozisyon Planı")
        layout.addWidget(self.table, 1)

    def set_results(self, df):
        self.results = df.copy() if df is not None else pd.DataFrame()

    def calculate(self):
        from pro_moduller import portfoy_onerisi_uret
        plan = portfoy_onerisi_uret(
            self.results,
            sermaye=self.capital.value(),
            islem_riski_yuzde=self.risk.value(),
            max_pozisyon_yuzde=self.position_limit.value(),
        )
        self.table.load(plan)


class SingleAnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        title = QLabel("Tek Hisse Analizi")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        sub = QLabel("İstediğin BIST hissesini yaz. Teknik ayrıntılar arka planda incelenir; sonuç sade gösterilir.")
        sub.setWordWrap(True)
        sub.setObjectName("subText")
        layout.addWidget(sub)
        top = QHBoxLayout()
        self.symbol = QLineEdit()
        self.symbol.setPlaceholderText("Örnek: ASELS")
        self.symbol.returnPressed.connect(self.run)
        top.addWidget(self.symbol, 1)
        self.button = QPushButton("ANALİZ ET")
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.run)
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
        self.button.setEnabled(False)
        self.status.setText("Analiz yapılıyor...")
        self.thread = QThread()
        self.worker = SingleWorker(symbol, "analysis")
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def done(self, ok, r, message):
        self.button.setEnabled(True)
        if not ok:
            self.status.setText("Analiz yapılamadı.")
            self.result.setPlainText(message)
            return
        self.status.setText("Analiz tamamlandı.")
        decision = r.get("yatirim_karari", "İZLE")
        lines = [
            f"HİSSE: {self.symbol.text().strip().upper()}",
            f"KARAR: {decision}",
            "",
            f"ALIŞ ARALIĞI: {r.get('onerilen_alis_alt', 0):.2f} - {r.get('onerilen_alis_ust', 0):.2f} TL",
            f"SATIŞ HEDEFİ: {r.get('onerilen_satis', 0):.2f} TL",
            f"STOP: {r.get('onerilen_stop', 0):.2f} TL",
            f"BEKLENEN GETİRİ: %{r.get('beklenen_getiri_yuzde', 0):.2f}",
            f"TAHMİNİ SÜRE: {r.get('beklenen_sure', '-')}",
            f"MODEL OLASILIĞI: %{r.get('model_olasiligi', 0)}",
            "",
            f"NEDEN: {r.get('karar_nedenleri', '-')}",
            "",
            "Bu sonuç teknik model senaryosudur; kesin getiri veya yatırım garantisi değildir.",
        ]
        self.result.setPlainText("\n".join(lines))


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
        self.setWindowTitle(APP_NAME + " v7.2 FINAL")
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
        self.portfolio = PortfolioPage()
        self.track = TrackPage()
        self.kap = SelectedInfoPage("kap")
        self.activity = SelectedInfoPage("activity")
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        for p in [self.terminal, self.single, self.sale, self.portfolio, self.track, self.kap, self.activity, self.log]:
            self.pages.addWidget(p)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(270)
        side_layout = QVBoxLayout(side)
        brand = QLabel("BORSA ANALİZ\nPRO MAX v7.2 FINAL")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(brand)

        menu = [
            ("YATIRIM TERMİNALİ", 0),
            ("TEK HİSSE ANALİZİ", 1),
            ("SATIŞ KARARI", 2),
            ("PORTFÖY / LOT PLANI", 3),
            ("TAKİP LİSTEM", 4),
            ("SEÇİLİ HİSSE KAP", 5),
            ("SEÇİLİ HİSSE FAALİYET", 6),
            ("CANLI LOG", 7),
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
            self.portfolio.set_results(all_results)
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
        self.pages.setCurrentIndex(7)
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
