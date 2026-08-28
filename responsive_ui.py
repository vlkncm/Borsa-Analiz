"""Tum analiz sayfalari icin ortak, DPI-duyarli sonuc ve detay bilesenleri."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
from PySide6.QtCore import QByteArray, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSizePolicy,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


PROFILE_COMPACT = "compact"
PROFILE_STANDARD = "standard"
PROFILE_WIDE = "wide"


def profile_for_width(width: int) -> str:
    if width < 1520:
        return PROFILE_COMPACT
    if width < 1840:
        return PROFILE_STANDARD
    return PROFILE_WIDE


@dataclass(frozen=True)
class AnalysisContext:
    analysis_id: str
    symbol: str = ""
    as_of_timestamp: str = ""
    horizon: str = ""
    model_version: str = ""
    result_id: str = ""
    analysis_type: str = "Hisse"

    def with_record(self, record: Mapping[str, Any]) -> "AnalysisContext":
        symbol = _first(record, "Hisse", "Sembol", "Fon", default=self.symbol)
        as_of = _first(record, "Veri Zamanı", "Veri Tarihi", "Son Değerlendirme Zamanı",
                       default=self.as_of_timestamp)
        horizon = _first(record, "Vade", "T+1/T+2", default=self.horizon)
        model = _first(record, "Model Sürümü", "Strateji Sürümü", default=self.model_version)
        result_id = _first(record, "result_id", "prediction_key", default=self.result_id)
        return AnalysisContext(
            analysis_id=self.analysis_id, symbol=str(symbol or ""),
            as_of_timestamp=str(as_of or ""), horizon=str(horizon or ""),
            model_version=str(model or ""), result_id=str(result_id or ""),
            analysis_type=self.analysis_type,
        )


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() in {"", "nan", "None", "NaT", "Veri yok"}


def _first(record: Mapping[str, Any], *keys: str, default: Any = "—") -> Any:
    for key in keys:
        value = record.get(key)
        if not _missing(value):
            return value
    return default


def _format(value: Any, column: str = "") -> str:
    if _missing(value):
        return "—"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, float):
        text = f"{value:.2f}"
    else:
        text = str(value)
    if "Olasılık" in column and text not in {"—", "-"} and "%" not in text:
        try:
            return f"%{float(value):.1f}"
        except (TypeError, ValueError):
            pass
    return text


class AnalysisStateWidget(QLabel):
    """Yukleniyor, bos, veri eksik ve hata durumlarini tek sozlesmede gosterir."""

    def __init__(self):
        super().__init__("Henüz analiz yapılmadı.")
        self.state = "idle"
        self.setObjectName("analysisState")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_loading(self, current: int | None = None, total: int | None = None, text: str = "Hisseler taranıyor…"):
        self.state = "loading"
        progress = f"\n{current} / {total}" if current is not None and total else ""
        self.setText(text + progress)

    def set_empty(self, text: str = "Bu analiz için güvenilir aday bulunamadı.\nEşikler sonuç oluşturmak amacıyla düşürülmedi."):
        self.state = "empty"; self.setText(text)

    def set_missing(self, missing: str):
        self.state = "missing"; self.setText(f"Analiz tamamlanamadı.\nEksik veri: {missing}")

    def set_error(self, text: str = "Tarama sonucu yüklenemedi.\nÖnceki geçerli sonuç korunuyor."):
        self.state = "error"; self.setText(text)

    def set_ready(self, text: str):
        self.state = "ready"; self.setText(text)


class AnalysisSummaryBar(QFrame):
    """Ekrani uzatmayan, en fazla alti metrikli ortak ozet cubugu."""

    DEFAULTS = ("Taranan", "Geniş Radar", "Seçkin", "Güçlü", "Teyit", "Veri Zamanı")

    def __init__(self, labels: Sequence[str] | None = None):
        super().__init__(); self.setObjectName("summaryBar")
        self._labels: dict[str, QLabel] = {}
        box = QHBoxLayout(self); box.setContentsMargins(8, 5, 8, 5); box.setSpacing(5)
        for name in labels or self.DEFAULTS:
            label = QLabel(f"{name}\n—"); label.setObjectName("summaryMetricCompact")
            label.setAlignment(Qt.AlignCenter); label.setMinimumWidth(70)
            box.addWidget(label, 1); self._labels[name] = label
        self.setMaximumHeight(56)

    def update_metrics(self, values: Mapping[str, Any]):
        for name, label in self._labels.items():
            label.setText(f"{name}\n{values.get(name, '—')}")


class AnalysisFilterBar(QFrame):
    filter_changed = Signal(str)
    reset_columns_requested = Signal()

    def __init__(self, placeholder: str = "Hisse, fon veya karar ara…"):
        super().__init__(); self.setObjectName("filterBar")
        row = QHBoxLayout(self); row.setContentsMargins(0, 2, 0, 2); row.setSpacing(6)
        self.search = QLineEdit(); self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.filter_changed)
        self.reset = QPushButton("Sütunları Sıfırla"); self.reset.setToolTip("Otomatik sütun profilini ve genişlikleri geri yükle")
        self.reset.clicked.connect(self.reset_columns_requested)
        row.addWidget(self.search, 1); row.addWidget(self.reset)


class ResponsiveResultTable(QTableWidget):
    """Kaynak kaydi koruyan, profile gore kolon gizleyen ortak sonuc tablosu."""

    detail_requested = Signal(object, object)

    def __init__(self, analysis_id: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.analysis_id = analysis_id
        self.analysis_context = AnalysisContext(analysis_id=analysis_id)
        self._records: list[dict[str, Any]] = []
        self._source_columns: list[str] = []
        self._profile_columns: dict[str, list[str]] = {}
        self._profile = PROFILE_COMPACT
        self._manual_widths: dict[str, int] = {}
        self._fitting_columns = False
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setWordWrap(False)
        self.verticalHeader().hide(); self.verticalHeader().setDefaultSectionSize(30)
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.horizontalHeader().setMinimumSectionSize(42)
        self.horizontalHeader().sectionResized.connect(self._remember_width)
        self.setSortingEnabled(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cellDoubleClicked.connect(self._open_from_row)

    @property
    def view_profile(self) -> str:
        return self._profile

    def configure_columns(self, compact: Sequence[str], standard: Sequence[str] | None = None,
                          wide: Sequence[str] | None = None):
        self._profile_columns = {
            PROFILE_COMPACT: list(compact),
            PROFILE_STANDARD: list(standard or compact),
            PROFILE_WIDE: list(wide or standard or compact),
        }
        self.apply_profile(self._profile)

    def set_context(self, context: AnalysisContext):
        self.analysis_context = context

    def load_frame(self, frame: pd.DataFrame | None, columns: Sequence[str] | None = None,
                   headers: Sequence[str] | None = None):
        frame = pd.DataFrame() if frame is None else frame.reset_index(drop=True).copy()
        self._records = frame.to_dict("records")
        self._source_columns = list(columns or frame.columns)
        visible_headers = list(headers or self._source_columns)
        self.setUpdatesEnabled(False); self.setSortingEnabled(False); self.clear()
        self.setRowCount(len(frame)); self.setColumnCount(len(self._source_columns) + 1)
        self.setHorizontalHeaderLabels(visible_headers + ["Detay"])
        for row_number, record in enumerate(self._records):
            for column_number, column in enumerate(self._source_columns):
                text = _format(record.get(column), column)
                item = QTableWidgetItem(text); item.setToolTip(text)
                item.setData(Qt.UserRole, dict(record))
                if column_number == 0:
                    item.setData(Qt.UserRole + 1, row_number)
                numeric = isinstance(record.get(column), (int, float)) or any(
                    token in column for token in ("Fiyat", "Hedef", "Stop", "%", "Olasılık", "Risk", "Adet", "Maliyet", "Getiri"))
                item.setTextAlignment((Qt.AlignRight if numeric else Qt.AlignLeft) | Qt.AlignVCenter)
                if any(token in text.upper() for token in ("SAT", "ALMA", "YÜKSEK RİSK", "HATA")):
                    item.setForeground(QColor("#ff6b78"))
                elif any(token in text.upper() for token in ("AL", "GÜÇLÜ", "TEYİT GELDİ")) and "ALMA" not in text.upper():
                    item.setForeground(QColor("#38d996"))
                self.setItem(row_number, column_number, item)
            detail = QPushButton("Aç"); detail.setToolTip("Analiz detayını ayrı pencerede aç")
            detail.setProperty("detailButton", True)
            detail.clicked.connect(lambda _checked=False, rec=dict(record): self._emit_detail(rec))
            self.setCellWidget(row_number, len(self._source_columns), detail)
        self.setSortingEnabled(True); self.setUpdatesEnabled(True)
        self.apply_profile(self._profile); self.viewport().update()

    def record_for_visual_row(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= self.rowCount():
            return None
        for column in range(max(1, len(self._source_columns))):
            item = self.item(row, column)
            if item is not None:
                record = item.data(Qt.UserRole)
                if isinstance(record, dict):
                    return dict(record)
        return None

    def apply_filter(self, text: str):
        needle = str(text or "").strip().casefold(); visible = 0
        for row in range(self.rowCount()):
            record = self.record_for_visual_row(row) or {}
            show = not needle or needle in " ".join(map(str, record.values())).casefold()
            self.setRowHidden(row, not show); visible += int(show)
        return visible

    def apply_profile(self, profile: str):
        self._profile = profile if profile in {PROFILE_COMPACT, PROFILE_STANDARD, PROFILE_WIDE} else PROFILE_COMPACT
        wanted = self._profile_columns.get(self._profile) or self._source_columns[:8]
        for index, column in enumerate(self._source_columns):
            self.setColumnHidden(index, column not in wanted)
        detail_index = len(self._source_columns)
        if detail_index < self.columnCount():
            self.setColumnHidden(detail_index, False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff if self._profile != PROFILE_WIDE else Qt.ScrollBarAsNeeded)
        self._fit_columns()

    def reset_columns(self):
        self._manual_widths.clear(); self.apply_profile(self._profile)

    def _fit_columns(self):
        visible = [index for index in range(self.columnCount()) if not self.isColumnHidden(index)]
        if not visible:
            return
        available = max(400, self.viewport().width() - 18)
        detail_index = len(self._source_columns)
        fixed = 58 if detail_index in visible else 0
        normal = [index for index in visible if index != detail_index]
        usable=max(1,available-fixed)
        self._fitting_columns=True
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        weights=[]
        for index in normal:
            name = self._source_columns[index]
            if "Sıra" in name or name == "Vade": weight=.65
            elif "Hisse" in name or "Sembol" in name: weight=.85
            elif "Durum" in name or "Karar" in name: weight=1.35
            else: weight=1.0
            weights.append(weight)
        total=sum(weights) or 1; used=0
        for position,(index,weight) in enumerate(zip(normal,weights)):
            name=self._source_columns[index]
            if self._profile==PROFILE_WIDE and name in self._manual_widths:
                width=self._manual_widths[name]
            elif position==len(normal)-1:
                width=max(42,usable-used)
            else:
                width=max(42,int(usable*weight/total))
            self.setColumnWidth(index,width)
            used+=width
        if detail_index in visible:
            self.setColumnWidth(detail_index, fixed)
        self._fitting_columns=False

    def resizeEvent(self, event):
        super().resizeEvent(event); self._fit_columns()

    def _remember_width(self, logical: int, _old: int, new: int):
        if not self._fitting_columns and 0 <= logical < len(self._source_columns) and new > 0:
            self._manual_widths[self._source_columns[logical]] = new

    def _open_from_row(self, row: int, _column: int):
        record = self.record_for_visual_row(row)
        if record:
            self._emit_detail(record)

    def _emit_detail(self, record: Mapping[str, Any]):
        context = self.analysis_context.with_record(record)
        self.detail_requested.emit(dict(record), context)


class AnalysisDetailWindow(QMainWindow):
    """Tekrar kullanilan, bloklamayan ve ekran sinirlari icinde kalan detay penceresi."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Hisse/Fon Analiz Detayı")
        self.setMinimumSize(720, 520)
        self.resize(980, 720)
        self._settings = QSettings("VSoftware", "BorsaAnalizProMAX")
        self._context = AnalysisContext("unknown")
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(10, 10, 10, 10); root.setSpacing(7)
        self.header = QLabel("Analiz detayı"); self.header.setObjectName("detailHeader"); self.header.setWordWrap(True)
        root.addWidget(self.header)
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True); root.addWidget(self.tabs, 1)
        close = QPushButton("Kapat"); close.clicked.connect(self.close)
        footer = QHBoxLayout(); footer.addStretch(); footer.addWidget(close); root.addLayout(footer)
        geometry = self._settings.value("analysisDetail/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)

    @property
    def context(self) -> AnalysisContext:
        return self._context

    def show_record(self, record: Mapping[str, Any], context: AnalysisContext):
        self._context = context
        symbol = _first(record, "Hisse", "Sembol", "Fon", default="—")
        price = _first(record, "Güncel Fiyat", "Fiyat", "Güncel", "Güncel Değer")
        decision = _first(record, "Ana Karar", "Karar", "Yatırım Kararı", "Durum", "Sonuç")
        probability = _first(record, "T+1 %7+ Olasılığı", "%7 Olasılığı", "Model Olasılığı %")
        self.header.setText(
            f"{symbol}  ·  {context.analysis_id}  ·  {context.horizon or 'Vade belirtilmedi'}\n"
            f"Güncel: {_format(price)}  ·  Karar: {decision}  ·  Olasılık: {_format(probability, 'Olasılık')}  ·  "
            f"Veri: {context.as_of_timestamp or '—'}"
        )
        self.tabs.clear()
        is_fund = context.analysis_type.casefold() == "fon" or "Fon" in record
        self._add_tab("Karar Özeti", record, (
            "Karar", "Yatırım Kararı", "Ana Karar", "Durum", "Sonuç", "T+1/T+2 Durumu",
            "Giriş", "Giriş Bölgesi", "Alım Bölgesi", "Hedef", "Hedef 1", "Hedef 2", "Stop",
            "Risk/Getiri", "Net EV", "Net Beklenti %", "Beklenen Süre", "Kalibrasyon Durumu"))
        self._add_tab("Neden ve Riskler", record, (
            "Aday Nedenleri", "Hisseye Özel Nedenler", "Gerekçe", "Karar Nedenleri", "Riskler",
            "Hisseye Özel Riskler", "Eleme Nedeni", "Eksik Özellikler", "Ne Olursa Karar Değişir"))
        if not is_fund:
            self._add_tab("Teknik Analiz", record, (
                "Fiyat", "Güncel Fiyat", "Hacim", "Göreceli Hacim", "RVOL", "EMA20", "EMA50", "EMA200",
                "RSI", "MACD", "ADX", "ATR", "VWAP", "Destek", "Direnç", "CMF", "MFI", "OBV"))
            self._add_tab("Temel ve KAP", record, (
                "Temel Puan", "Faaliyet Puanı", "KAP Etiket", "KAP", "Katalizör", "Büyüme", "Kârlılık",
                "Borçluluk", "Değerleme", "Finansal Özet"))
            self._add_tab("Piyasa ve Sektör", record, (
                "Piyasa Rejimi", "Sektör", "Sektör Puanı", "Sektör Gücü", "Göreceli Güç", "RS BIST 5",
                "RS Sektör 5", "Piyasa Genişliği", "T+1 Sırası", "T+2 Sırası", "T+1 Yüzdelik", "T+2 Yüzdelik"))
        else:
            self._add_tab("Fon Bilgileri", record, tuple(record.keys()))
        self._add_tab("Tahmin Geçmişi", record, (
            "Tahmin Zamanı", "T+1 %7+ Olasılığı", "T+1 %8+ Olasılığı", "T+1 Tavan Olasılığı",
            "T+2 %7+ Olasılığı", "T+2 %8+ Olasılığı", "Gerçekleşen Maksimum Getiri",
            "Kapanış Getirisi", "Hedef/Stop Sonucu", "Model Sürümü", "Strateji Sürümü", "Feature Hash"))
        self._add_tab("Tüm Veriler", record, tuple(record.keys()))
        self._clamp_to_screen(); self.show(); self.raise_(); self.activateWindow()

    def _add_tab(self, title: str, record: Mapping[str, Any], keys: Iterable[str]):
        selected = []
        for key in keys:
            if key in record and not _missing(record.get(key)) and key not in {name for name, _ in selected}:
                selected.append((key, record.get(key)))
        if not selected and title != "Tüm Veriler":
            return
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); grid = QGridLayout(body); grid.setColumnStretch(1, 1)
        for row, (key, value) in enumerate(selected):
            name = QLabel(str(key)); name.setObjectName("detailKey"); name.setAlignment(Qt.AlignTop)
            text = QLabel(_format(value, key)); text.setObjectName("detailValue"); text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(name, row, 0); grid.addWidget(text, row, 1)
        grid.setRowStretch(len(selected), 1); scroll.setWidget(body); self.tabs.addTab(scroll, title)

    def _clamp_to_screen(self):
        screens = QGuiApplication.screens()
        screen = next((item for item in screens if item.availableGeometry().intersects(self.frameGeometry())), None)
        screen = screen or QGuiApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry(); frame = self.frameGeometry()
        width = min(max(self.minimumWidth(), frame.width()), area.width())
        height = min(max(self.minimumHeight(), frame.height()), area.height())
        x = min(max(frame.x(), area.left()), area.right() - width + 1)
        y = min(max(frame.y(), area.top()), area.bottom() - height + 1)
        self.setGeometry(x, y, width, height)

    def closeEvent(self, event):
        self._settings.setValue("analysisDetail/geometry", self.saveGeometry())
        super().closeEvent(event)


class BaseAnalysisPage(QWidget):
    """Baslik, ozet, filtre, tablo ve durum alanlarinin ortak iskeleti."""

    def __init__(self, analysis_id: str, title: str, subtitle: str = "", analysis_type: str = "Hisse"):
        super().__init__(); self.analysis_id = analysis_id; self.responsive_layout = True
        self._profile = PROFILE_COMPACT
        self._detail_window = AnalysisDetailWindow(self)
        self._layout = QVBoxLayout(self); self._layout.setContentsMargins(12, 9, 12, 9); self._layout.setSpacing(6)
        header = QHBoxLayout(); titles = QVBoxLayout(); self.title_label = QLabel(title); self.title_label.setObjectName("pageTitle")
        titles.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle); self.subtitle_label.setWordWrap(True); self.subtitle_label.setObjectName("muted")
        if subtitle: titles.addWidget(self.subtitle_label)
        header.addLayout(titles); header.addStretch(); self._layout.addLayout(header)
        self.summary_bar = AnalysisSummaryBar(); self._layout.addWidget(self.summary_bar)
        self.filter_bar = AnalysisFilterBar(); self._layout.addWidget(self.filter_bar)
        self.state_widget = AnalysisStateWidget(); self._layout.addWidget(self.state_widget)
        self.table = ResponsiveResultTable(analysis_id)
        self.table.set_context(AnalysisContext(analysis_id=analysis_id, analysis_type=analysis_type))
        self.table.detail_requested.connect(self.open_detail)
        self.filter_bar.filter_changed.connect(self.table.apply_filter)
        self.filter_bar.reset_columns_requested.connect(self.table.reset_columns)
        self._layout.addWidget(self.table, 1)

    def layout(self):
        return self._layout

    def open_detail(self, record: Mapping[str, Any], context: AnalysisContext):
        self._detail_window.show_record(record, context)

    def set_view_profile(self, profile: str):
        self._profile = profile; self.table.apply_profile(profile)
        self.summary_bar.setVisible(profile != PROFILE_COMPACT or self.height() >= 620)

    def resizeEvent(self, event):
        super().resizeEvent(event); self.set_view_profile(profile_for_width(self.width()))
