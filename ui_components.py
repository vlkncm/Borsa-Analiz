"""Borsa Analiz masaüstü uygulamasının ortak ve responsive UI bileşenleri."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


class PrimaryActionButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("primaryAction")
        self.setAccessibleName(text)
        self.setCursor(Qt.PointingHandCursor)


class StatusBadge(QLabel):
    def __init__(self, text="Bekle", tone="neutral", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_status(text, tone)

    def set_status(self, text, tone="neutral"):
        self.setText(str(text))
        self.setProperty("tone", tone)
        self.setObjectName("statusBadge")
        self.style().unpolish(self)
        self.style().polish(self)


class DataFreshnessBadge(StatusBadge):
    def __init__(self, text=None, parent=None):
        value = text or f"Veri bekleniyor · {datetime.now():%H:%M}"
        super().__init__(value, "info", parent)
        self.setObjectName("freshnessBadge")

    def set_freshness(self, text, stale=False):
        self.set_status(text, "warning" if stale else "info")
        self.setObjectName("freshnessBadge")


class PageHeader(QFrame):
    def __init__(self, title, subtitle="", action=None, freshness=True, parent=None):
        super().__init__(parent)
        self.setObjectName("pageHeader")
        self.root = QHBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 10)
        self.root.setSpacing(16)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        copy.addWidget(self.title)
        if subtitle:
            copy.addWidget(self.subtitle)
        self.root.addLayout(copy, 1)
        self.freshness = DataFreshnessBadge(parent=self) if freshness else None
        if self.freshness:
            self.root.addWidget(self.freshness, 0, Qt.AlignTop)
        self.action = action
        if action is not None:
            self.root.addWidget(action, 0, Qt.AlignTop)

    def set_action(self, action):
        if self.action is not None:
            self.action.setParent(None)
        self.action = action
        if action is not None:
            self.root.addWidget(action, 0, Qt.AlignTop)


class SummaryCard(QFrame):
    def __init__(self, caption, value="—", note="", parent=None):
        super().__init__(parent)
        self.setObjectName("summaryCard")
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 14, 18, 14)
        box.setSpacing(5)
        self.caption = QLabel(caption)
        self.caption.setObjectName("cardCaption")
        self.value = QLabel(str(value))
        self.value.setObjectName("cardValue")
        self.note = QLabel(note)
        self.note.setObjectName("cardNote")
        self.note.setWordWrap(True)
        box.addWidget(self.caption)
        box.addWidget(self.value)
        box.addWidget(self.note)

    def set_value(self, value, note=None):
        self.value.setText(str(value))
        if note is not None:
            self.note.setText(str(note))


class EmptyState(QFrame):
    def __init__(self, title="Henüz sonuç yok", message="Analiz tamamlandığında sonuçlar burada gösterilir.", parent=None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 16)
        heading = QLabel(title)
        heading.setObjectName("emptyTitle")
        self.message = QLabel(message)
        self.message.setObjectName("emptyMessage")
        self.message.setWordWrap(True)
        box.addWidget(heading)
        box.addWidget(self.message)


class SelectedRowDetailPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailPanel")
        self.setMinimumHeight(96)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(7)
        title = QLabel("Seçilen satır ayrıntısı")
        title.setObjectName("detailTitle")
        self.content = QLabel("Bir satır seçildiğinde ikincil bilgiler burada gösterilir.")
        self.content.setObjectName("detailContent")
        self.content.setWordWrap(True)
        self.content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(title)
        box.addWidget(self.content)

    def set_data(self, data):
        if not data:
            self.content.setText("Bir satır seçildiğinde ikincil bilgiler burada gösterilir.")
            return
        parts = []
        for key, value in data.items():
            if value is None or str(value).strip() in {"", "nan", "None"}:
                continue
            parts.append(f"{key}: {value}")
        self.content.setText("   ·   ".join(parts) if parts else "Bu satır için ayrıntı bulunmuyor.")


class ProbabilityTimeCell(QWidget):
    def __init__(self, probability="—", horizon="Süre bilinmiyor", parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(4, 2, 4, 2)
        box.setSpacing(0)
        value = QLabel(str(probability))
        value.setObjectName("probabilityValue")
        time = QLabel(str(horizon))
        time.setObjectName("probabilityTime")
        box.addWidget(value, alignment=Qt.AlignRight)
        box.addWidget(time, alignment=Qt.AlignRight)


class RiskRewardCell(QLabel):
    def __init__(self, value="—", parent=None):
        super().__init__(str(value), parent)
        self.setObjectName("riskRewardCell")
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)


class ResponsiveResultTable(QTableWidget):
    """Dar alanda ikincil kolonları gizleyen, yatay kaydırmasız sonuç tablosu."""

    selection_data_requested = Signal(int)

    CRITICAL_TOKENS = (
        "hisse", "karar", "sonuç", "alis", "alış", "hedef", "stop",
        "potansiyel", "yükseliş", "olasilik", "olasılık", "süre", "sure",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultTable")
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(42)
        self.horizontalHeader().setMinimumSectionSize(74)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setStretchLastSection(True)
        self._column_names = []

    def set_column_names(self, names):
        self._column_names = [str(name) for name in names]
        self._apply_responsive_columns()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_columns()

    def _priority(self, name):
        normalized = name.casefold().replace(" ", "")
        groups = (
            ("hisse", "karar", "sonuç"),
            ("alis", "alış"),
            ("hedef",),
            ("stop",),
            ("olasilik", "olasılık", "süre", "sure"),
            ("potansiyel", "yükseliş"),
        )
        for priority, tokens in enumerate(groups):
            if any(token in normalized for token in tokens):
                return priority
        return len(groups) + 1

    def _apply_responsive_columns(self):
        if not self._column_names:
            return
        width = max(self.viewport().width(), self.width())
        if width < 850:
            limit = 6
        elif width < 1100:
            limit = 8
        else:
            limit = len(self._column_names)
        ranked = sorted(range(len(self._column_names)), key=lambda index: (self._priority(self._column_names[index]), index))
        visible = set(ranked[:limit])
        for index in range(len(self._column_names)):
            self.setColumnHidden(index, index not in visible)


class AppSidebar(QFrame):
    page_requested = Signal(object)

    def __init__(self, version, items, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(250)
        self._buttons = {}
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 20, 16, 16)
        box.setSpacing(5)
        brand = QLabel("Borsa Analiz")
        brand.setObjectName("brand")
        subtitle = QLabel(f"Pro MAX v{version} · Sade karar merkezi")
        subtitle.setObjectName("brandSubtitle")
        subtitle.setWordWrap(True)
        box.addWidget(brand)
        box.addWidget(subtitle)
        box.addSpacing(18)
        for text, page in items:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAccessibleName(f"{text} sayfasını aç")
            button.clicked.connect(lambda checked=False, target=page: self.page_requested.emit(target))
            box.addWidget(button)
            self._buttons[page] = button
        box.addStretch(1)
        self.footer_layout = QVBoxLayout()
        self.footer_layout.setSpacing(5)
        box.addLayout(self.footer_layout)

    def set_active(self, page):
        for target, button in self._buttons.items():
            button.setChecked(target is page)


DARK_THEME = """
QMainWindow, QWidget {
    background: #0b1421;
    color: #e7ecf4;
    font-family: "Segoe UI", Arial;
    font-size: 13px;
}
#appRoot { background: #080f19; }
#sidebar { background: #111b2b; border-right: 1px solid #233147; }
#brand { color: #f2f5fb; font-size: 20px; font-weight: 800; }
#brandSubtitle, #pathText { color: #94a0b4; font-size: 12px; }
#navButton {
    background: transparent; color: #dce2ec; border: 0; border-radius: 10px;
    padding: 11px 14px; text-align: left; font-weight: 500;
}
#navButton:hover { background: #17243a; color: #ffffff; }
#navButton:checked { background: #2f6cf0; color: #ffffff; font-weight: 700; }
QStackedWidget { background: #0d1724; }
#pageHeader { border-bottom: 1px solid #243247; background: transparent; }
#pageTitle { color: #f2f5fb; font-size: 27px; font-weight: 800; }
#pageSubtitle, #subText, #cardCaption, #cardNote, #detailContent, #emptyMessage, #footerText {
    color: #98a5ba;
}
#freshnessBadge, #statusBadge {
    background: #1c2b43; color: #dce4f1; border: 1px solid #263852;
    border-radius: 18px; padding: 8px 14px;
}
#statusBadge[tone="positive"] { background: #123a30; color: #7ee2b8; border-color: #205b49; }
#statusBadge[tone="warning"] { background: #3b2d18; color: #f4c86b; border-color: #604822; }
#statusBadge[tone="danger"] { background: #3c2028; color: #ff9aaa; border-color: #63303c; }
#primaryAction, #primary, #heroButton {
    background: #2f6cf0; color: white; border: 1px solid #3c78f2; border-radius: 9px;
    padding: 10px 16px; text-align: center; font-weight: 700; min-height: 20px;
}
#primaryAction:hover, #primary:hover, #heroButton:hover { background: #3e79f4; }
QPushButton {
    background: #162238; color: #dbe3ef; border: 1px solid #263650;
    border-radius: 8px; padding: 8px 12px; font-weight: 600;
}
QPushButton:hover { background: #1d2d47; border-color: #385078; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #4b82f2;
}
#summaryCard, #metricCard, #dashboardPanel, #topStrip, #sidePanel, #chartSummary,
#chartCanvas, #analysisText, #detailPanel, #emptyState {
    background: #111b2b; border: 1px solid #27354c; border-radius: 13px;
}
#cardValue, #metricValue { color: #f2f5fb; font-size: 25px; font-weight: 800; }
#cardCaption, #metricCaption { font-size: 13px; }
#detailTitle, #emptyTitle, #sectionTitle, #tableTitle, #analysisTitle {
    color: #f0f3f9; font-size: 16px; font-weight: 750;
}
#riskBanner { background: #241d23; border: 1px solid #573644; color: #f2c5cf; padding: 10px; border-radius: 9px; }
QLineEdit, QTextEdit, QDoubleSpinBox, QComboBox {
    background: #101a29; color: #f0f3f8; border: 1px solid #2a3a53; border-radius: 8px; padding: 8px;
}
QTableWidget {
    background: #0d1724; color: #e5eaf2; border: 0; gridline-color: #263348;
    selection-background-color: #1d3f78; selection-color: #ffffff;
}
QTableWidget::item { padding: 7px; border-bottom: 1px solid #202e42; }
QHeaderView::section {
    background: #0d1724; color: #dfe5ee; border: 0; border-bottom: 1px solid #2a394f;
    padding: 9px 7px; font-weight: 650;
}
QScrollBar:vertical { background: #0d1724; width: 10px; }
QScrollBar::handle:vertical { background: #34445f; border-radius: 5px; min-height: 24px; }
QTabBar::tab { background: #111b2b; color: #aab5c6; padding: 9px 14px; border: 1px solid #27354c; }
QTabBar::tab:selected { background: #1b2e4a; color: #ffffff; border-bottom: 2px solid #2f6cf0; }
"""
