"""Borsa Analiz masaustu uygulamasi icin ortak finans dashboard bileşenleri."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QObject, QSettings, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from responsive_ui import (
    AnalysisContext, AnalysisDetailWindow, AnalysisFilterBar, AnalysisStateWidget,
    AnalysisSummaryBar, PROFILE_COMPACT, ResponsiveResultTable, profile_for_width,
)


COLORS = {
    "bg": "#04111f", "panel": "#091b2d", "panel2": "#0b2238", "border": "#173a58",
    "text": "#eef5ff", "muted": "#8da5bd", "blue": "#0878f9", "green": "#18d486",
    "red": "#ff5364", "orange": "#ffad32",
}


APP_STYLE = """
QMainWindow, QWidget { background:#04111f; color:#eef5ff; font-family:'Segoe UI',Arial; font-size:11px; }
#appRoot { background:#04111f; } #topHeader { background:#061624; border-bottom:1px solid #173a58; }
#brandTitle { font-size:18px; font-weight:800; } #brandSub, #muted, #dataTime { color:#8da5bd; font-size:10px; }
#sidebar { background:#061624; border-right:1px solid #173a58; } #sidebar QPushButton { min-height:32px; }
QPushButton { background:transparent; color:#bdd0e3; border:0; border-radius:6px; padding:6px 9px; text-align:left; }
QPushButton:hover { background:#102c45; color:white; } QPushButton:checked, #activeNav { background:#0878f9; color:white; font-weight:700; }
#primary { background:#0878f9; color:white; font-weight:700; text-align:center; border:1px solid #3194ff; }
#primary:hover { background:#1688ff; } #iconButton { font-size:16px; text-align:center; }
#card, #marketCard, #detailPanel, #bottomCard { background:#091b2d; border:1px solid #173a58; border-radius:8px; }
#marketName, #sectionTitle { color:#c8d7e7; font-weight:700; } #marketValue { color:#f5f9ff; font-size:17px; font-weight:800; }
#positive { color:#18d486; } #negative { color:#ff5364; } #warning { color:#ffad32; } #pageTitle { font-size:20px; font-weight:800; }
#pillBlue { color:#52a5ff; background:#092b4d; border:1px solid #145b9b; border-radius:5px; padding:4px 8px; }
#pillGreen { color:#4ce6a1; background:#083424; border:1px solid #14724b; border-radius:5px; padding:4px 8px; }
#pillOrange { color:#ffc15a; background:#3b290b; border:1px solid #8c5f13; border-radius:5px; padding:4px 8px; }
QLineEdit { background:#0b2238; border:1px solid #1b4265; border-radius:7px; padding:8px 11px; color:white; }
QTableWidget { background:#071827; alternate-background-color:#0a1f32; border:0; gridline-color:#17334e; selection-background-color:#0c4b80; }
QTableWidget::item { padding:4px; } QHeaderView::section { background:#0a1c2e; color:#a9bed2; border:0; border-bottom:1px solid #244660; padding:7px 4px; font-weight:600; }
QTabWidget::pane { border:0; } QTabBar::tab { background:#071827; color:#9db2c7; padding:7px 15px; border:1px solid #173a58; }
QTabBar::tab:selected { background:#0878f9; color:white; }
QScrollArea { border:0; } QToolTip { background:#102c45; color:white; border:1px solid #3184c7; }
#summaryBar, #filterBar { background:#071827; border:1px solid #173a58; border-radius:7px; }
#summaryMetricCompact { color:#dce9f6; font-size:10px; font-weight:600; }
#analysisState { color:#8da5bd; padding:3px 5px; }
#detailHeader { background:#0c4a6e; color:white; font-size:17px; font-weight:700; padding:10px; border-radius:7px; }
#detailKey { color:#91a9c0; font-weight:700; min-width:150px; padding:6px; }
#detailValue { background:#091b2d; border:1px solid #173a58; border-radius:5px; padding:6px; }
QPushButton[detailButton="true"] { background:#0c4b80; color:white; padding:3px 7px; text-align:center; }
"""


class Sparkline(QWidget):
    def __init__(self):
        super().__init__(); self.values = []; self.positive = True; self.setMinimumSize(54, 28)

    def set_values(self, values):
        self.values = [float(v) for v in values if pd.notna(v)]; self.positive = len(self.values) < 2 or self.values[-1] >= self.values[0]; self.update()

    def paintEvent(self, _event):
        if len(self.values) < 2: return
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        lo, hi = min(self.values), max(self.values); span = hi-lo or 1
        path = QPainterPath()
        for i, value in enumerate(self.values):
            x = 2 + i*(self.width()-4)/(len(self.values)-1); y = self.height()-3-(value-lo)*(self.height()-6)/span
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        painter.setPen(QPen(QColor(COLORS["green"] if self.positive else COLORS["red"]), 1.6)); painter.drawPath(path)


class MarketCard(QFrame):
    def __init__(self, title):
        super().__init__(); self.setObjectName("marketCard"); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.setFixedHeight(75)
        box = QVBoxLayout(self); box.setContentsMargins(10, 6, 8, 5); box.setSpacing(1)
        self.name = QLabel(title); self.name.setObjectName("marketName"); self.name.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred); box.addWidget(self.name)
        row = QHBoxLayout(); self.value = QLabel("Veri bekleniyor"); self.value.setObjectName("marketValue"); self.value.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred); self.spark = Sparkline(); row.addWidget(self.value, 1); row.addWidget(self.spark); box.addLayout(row)
        self.change = QLabel("Veri bekleniyor"); self.change.setObjectName("dataTime"); self.change.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred); box.addWidget(self.change)

    def update_data(self, payload):
        if not payload: self.value.setText("Veri bekleniyor"); self.change.setText("Veri bekleniyor"); self.spark.set_values([]); return
        value, previous = payload["value"], payload["previous"]; delta = value-previous; pct = delta/previous*100 if previous else 0
        self.value.setText(f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.change.setText(f"{'▲' if delta >= 0 else '▼'} %{abs(pct):.2f}   {delta:+.2f}  · {payload['time']}")
        self.change.setObjectName("positive" if delta >= 0 else "negative"); self.style().unpolish(self.change); self.style().polish(self.change)
        self.spark.set_values(payload.get("series", []))


class MarketDataWorker(QObject):
    finished = Signal(object)
    SYMBOLS = {"BIST 100":"XU100.IS", "BIST 30":"XU030.IS", "BIST TÜM":"XUTUM.IS", "DOLAR/TL":"TRY=X", "EURO/TL":"EURTRY=X", "ONS ALTIN":"GC=F"}
    def run(self):
        result = {}
        try:
            import yfinance as yf
            for name, symbol in self.SYMBOLS.items():
                try:
                    frame = yf.Ticker(symbol).history(period="5d", interval="30m", auto_adjust=False)
                    close = pd.to_numeric(frame.get("Close"), errors="coerce").dropna()
                    if len(close) >= 2:
                        result[name] = {"value":float(close.iloc[-1]), "previous":float(close.iloc[-2]), "series":close.tail(24).tolist(), "time":str(close.index[-1])[:16]}
                except Exception: pass
        finally: self.finished.emit(result)


class TopHeader(QFrame):
    scan_requested = Signal(); search_requested = Signal(str)
    def __init__(self):
        super().__init__(); self.setObjectName("topHeader"); self.setFixedHeight(58)
        row = QHBoxLayout(self); row.setContentsMargins(14, 7, 12, 7); row.setSpacing(9)
        brand = QVBoxLayout(); self.title = QLabel("▥  Borsa Analiz"); self.title.setObjectName("brandTitle"); self.subtitle = QLabel("Daha Seçici Analiz, Daha Güçlü Kararlar"); self.subtitle.setObjectName("brandSub"); brand.addWidget(self.title); brand.addWidget(self.subtitle); row.addLayout(brand)
        self.search = QLineEdit(); self.search.setPlaceholderText("⌕  Hisse ara… (örn. TGSAS)"); self.search.setMaximumWidth(330); self.search.returnPressed.connect(lambda:self.search_requested.emit(self.search.text())); row.addWidget(self.search, 1)
        row.addStretch(); self.clock = QLabel(); self.clock.setObjectName("muted"); row.addWidget(self.clock)
        self.market = QLabel("● Piyasa durumu bekleniyor"); self.market.setObjectName("warning"); row.addWidget(self.market)
        self.icon_buttons=[]
        for text, tip in (("♢", "Bildirimler"), ("⚙", "Ayarlar"), ("●", "Kullanıcı")):
            button=QPushButton(text); button.setObjectName("iconButton"); button.setToolTip(tip); button.setFixedWidth(34); row.addWidget(button)
            self.icon_buttons.append(button)
        self.scan = QPushButton("↗  Tüm Hisse Analizlerini Başlat"); self.scan.setObjectName("primary"); self.scan.clicked.connect(self.scan_requested.emit); row.addWidget(self.scan)
        timer=QTimer(self); timer.timeout.connect(self._tick); timer.start(1000); self._tick()
    def _tick(self): self.clock.setText(datetime.now().strftime("%d %B %Y  %H:%M:%S"))
    def set_compact(self, compact):
        self.subtitle.setVisible(not compact); self.clock.setVisible(not compact)
        self.market.setVisible(not compact); self.search.setMaximumWidth(210 if compact else 330)
        self.scan.setText("↗  Taramayı Başlat" if compact else "↗  Tüm Hisse Analizlerini Başlat")
        self.scan.setToolTip("Tüm aktif BIST hisselerinin analizini güvenli ayrı süreçte başlat")
        for button in self.icon_buttons: button.setVisible(not compact)


class Sidebar(QFrame):
    page_requested = Signal(str)
    ITEMS = [("next","◎","Yüksek Hareket Radarı"),("home","⌂","Ana Sayfa"),("daily","◉","Günlük Trade"),("short","▥","Kısa Vade · BIST 30"),("medium","▥","Orta Vade · BIST 30"),("under50","◫","50 TL Altı"),("funds","◈","Fon Analizi"),("portfolio","▣","Portföy"),("performance","⌁","Tahmin Performansı"),("settings","⚙","Ayarlar")]
    def __init__(self):
        super().__init__(); self.setObjectName("sidebar"); self._settings=QSettings("VSoftware","BorsaAnalizProMAX")
        self.expanded=str(self._settings.value("sidebar/expanded","true")).lower() not in {"false","0"}; self.setFixedWidth(190 if self.expanded else 54)
        self.box=QVBoxLayout(self); self.box.setContentsMargins(6,7,6,7); self.box.setSpacing(3); self.buttons={}
        collapse=QPushButton("☰  Menüyü Daralt"); collapse.clicked.connect(self.toggle); self.box.addWidget(collapse); self.collapse=collapse
        for key, icon, text in self.ITEMS:
            button=QPushButton(f"{icon}  {text}"); button.setCheckable(True); button.setToolTip(text); button.clicked.connect(lambda checked=False,k=key:self.page_requested.emit(k)); self.box.addWidget(button); self.buttons[key]=button
        self.box.addStretch(); self.set_expanded(self.expanded, remember=False); self.set_active("home")
    def toggle(self):
        self.set_expanded(not self.expanded)
    def set_expanded(self, expanded, remember=True):
        self.expanded=bool(expanded); self.setFixedWidth(190 if self.expanded else 54); self.collapse.setText("☰  Menüyü Daralt" if self.expanded else "☰")
        for key, icon, text in self.ITEMS: self.buttons[key].setText(f"{icon}  {text}" if self.expanded else icon)
        if remember: self._settings.setValue("sidebar/expanded",self.expanded)
    def set_active(self,key):
        for name,button in self.buttons.items(): button.setChecked(name==key)


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame=QFrame(); frame.setObjectName("bottomCard"); box=QVBoxLayout(frame); box.setContentsMargins(10,8,10,8); box.setSpacing(5); heading=QLabel(title); heading.setObjectName("sectionTitle"); box.addWidget(heading); return frame,box


class DetailPanel(QFrame):
    def __init__(self):
        super().__init__(); self.setObjectName("detailPanel"); box=QVBoxLayout(self); box.setContentsMargins(10,9,10,9); box.setSpacing(5)
        self.title=QLabel("Seçili Hisse Detayı"); self.title.setObjectName("sectionTitle"); box.addWidget(self.title)
        self.chart=Sparkline(); self.chart.setMinimumHeight(72); box.addWidget(self.chart)
        self.facts=QLabel("Bir aday seçildiğinde ayrıntılar burada gösterilir."); self.facts.setWordWrap(True); self.facts.setTextInteractionFlags(Qt.TextSelectableByMouse); box.addWidget(self.facts)
        why=QLabel("Neden Aday?"); why.setObjectName("sectionTitle"); box.addWidget(why)
        self.reasons=QLabel("Veri bekleniyor"); self.reasons.setWordWrap(True); box.addWidget(self.reasons,1)
    @staticmethod
    def _value(row,*names,default="Veri yetersiz"):
        for name in names:
            value=row.get(name)
            if value is not None and not (isinstance(value,float) and pd.isna(value)) and str(value).strip() not in {"","nan","None"}: return value
        return default
    def set_row(self,row):
        symbol=self._value(row,"Hisse",default="—"); status=self._value(row,"Canlı Durum","Durum")
        self.title.setText(f"Seçili Hisse Detayı · {symbol}   [{status}]")
        facts=[("Piyasa rejimi",self._value(row,"Piyasa Rejimi")),("Sektör gücü",self._value(row,"Sektör Puanı")),("Göreceli hacim",self._value(row,"Göreceli Hacim","RVOL")),("Para akışı",self._value(row,"Para Akışı","CMF")),("KAP katalizörü",self._value(row,"KAP Etiket")),("Risk seviyesi",self._value(row,"Risk Seviyesi",default="Yüksek" if "RİSK" in str(status) else "Veri yetersiz")),("Giriş bölgesi",self._value(row,"Giriş Bölgesi","Alım Bölgesi")),("Hedef",self._value(row,"Hedef","Tahmini En Yüksek Fiyat")),("Stop",self._value(row,"Stop")),("Risk/getiri",self._value(row,"Risk/Getiri","Karar Risk/Getiri")),("Tahmini süre",self._value(row,"Tahmini Süre","Beklenen Süre")),("Veri zamanı",self._value(row,"Veri Zamanı","Veri Tarihi"))]
        self.facts.setText("\n".join(f"{k}:  {v}" for k,v in facts)); self.chart.set_values(row.get("Fiyat Serisi",[]) or [])
        def lines(value):
            if isinstance(value,str):
                try: value=json.loads(value)
                except Exception: value=[value]
            return value if isinstance(value,(list,tuple)) else []
        reasons=lines(row.get("Aday Nedenleri")) or [x.strip() for x in str(row.get("Hisseye Özel Nedenler","")).split("|") if x.strip()]
        risks=lines(row.get("Riskler")) or [x.strip() for x in str(row.get("Hisseye Özel Riskler","")).split("|") if x.strip()]
        missing=[k for k,v in facts if v=="Veri yetersiz"]
        chunks=[]
        if reasons: chunks.append("Olumlu\n"+"\n".join("✓ "+str(x) for x in reasons[:4]))
        if "TEYİT" in str(status): chunks.append("Teyit bekleyen\n• Canlı fiyat ve hacim doğrulaması")
        if risks: chunks.append("Riskler\n"+"\n".join("⚠ "+str(x) for x in risks[:3]))
        if missing: chunks.append("Eksik veri\n• "+", ".join(missing))
        self.reasons.setText("\n\n".join(chunks) if chunks else "Aday gerekçesi için veri bekleniyor")


class NextDayDashboard(QWidget):
    scan_requested = Signal()
    COLUMNS=["Hisse","Önceki Kapanış","Güncel Fiyat","Günlük Değişim %","Tavan Fiyatı","Tavana Kalan %","%8+ Olasılığı","Tavan Olasılığı","Tahmini En Yüksek Fiyat","Durum"]
    HEADERS=["Hisse","Önceki Kapanış","Güncel","Günlük %","Tavan","Tavana Kalan","%8+ Olasılık","Tavan Olasılığı","Tahmini En Yüksek","Durum"]
    IPO_COLUMNS=["Hisse","Kotasyon Tarihi","İşlem Günü Sayısı","Halka Arz Fiyatı","Güncel Fiyat","Halka Arzdan Beri Getiri %","Ardışık Tavan Sayısı","Günlük Değişim %","Göreceli Hacim","Tavan Fiyatı","Tavana Kalan %","Momentum Durumu","Risk Durumu","Veri Yeterlilik Seviyesi","Son Değerlendirme Zamanı"]
    IPO_HEADERS=["Hisse","Kotasyon","Gün","Arz Fiyatı","Güncel","Arzdan Getiri %","Tavan Serisi","Günlük %","RVOL","Tavan","Kalan %","Momentum","Risk","Veri Seviyesi","Değerlendirme"]
    T1_COLUMNS=["T+1 Sırası","Hisse","Güncel Fiyat","T+1 %7+ Olasılığı","T+1 %8+ Olasılığı","T+1 Tavan Olasılığı","T+1 Giriş","T+1 Hedef","T+1 Stop","T+1 Risk/Getiri","T+1/T+2 Durumu"]
    T2_COLUMNS=["T+2 Sırası","Hisse","Güncel Fiyat","T+2 %7+ Olasılığı","T+2 %8+ Olasılığı","T+2 Tavan Olasılığı","T+2 Giriş","T+2 Hedef","T+2 Stop","T+2 Risk/Getiri","T+1/T+2 Durumu"]
    def __init__(self, prediction_path: Path):
        super().__init__(); self.responsive_layout=True; self.analysis_id="high_movement_radar"; self.prediction_path=prediction_path; self._records=[]; self._full=pd.DataFrame(); root=QVBoxLayout(self); root.setContentsMargins(10,8,10,8); root.setSpacing(6)
        self._detail_window=AnalysisDetailWindow(self)
        header=QHBoxLayout(); titles=QVBoxLayout(); title=QLabel("YÜKSEK HAREKET RADARI"); title.setObjectName("pageTitle"); self.subtitle=QLabel("T+1 / T+2 gün içi %7–10 hareket hazırlığı · Tüm aktif BIST"); self.subtitle.setObjectName("muted"); self.subtitle.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred); titles.addWidget(title); titles.addWidget(self.subtitle); header.addLayout(titles); header.addStretch(); self.header_pills=[]
        for text,obj in (("◎ Seans Sonrası","pillBlue"),("● Canlı Teyit","pillGreen")):
            lab=QLabel(text); lab.setObjectName(obj); lab.hide(); header.addWidget(lab); self.header_pills.append(lab)
        self.last_scan=QLabel("Son Tarama: —"); self.last_scan.setObjectName("muted"); header.addWidget(self.last_scan); self.scan=QPushButton("Taramayı Başlat"); self.scan.setObjectName("primary"); self.scan.clicked.connect(self.scan_requested.emit); header.addWidget(self.scan); root.addLayout(header)
        self.summary_bar=AnalysisSummaryBar(); root.addWidget(self.summary_bar)
        self.filter_bar=AnalysisFilterBar("Radar sonuçlarında hisse veya durum ara…"); root.addWidget(self.filter_bar)
        self.stats=AnalysisStateWidget(); self.stats.set_ready("Veri bekleniyor"); root.addWidget(self.stats)
        main=QHBoxLayout(); main.setSpacing(8); left=QVBoxLayout(); self.tabs=QTabWidget(); self.tabs.tabBar().setUsesScrollButtons(True); self.tabs.tabBar().setExpanding(False); self.tabs.tabBar().setElideMode(Qt.ElideRight); self.tables={}
        for key,title,columns in (("t1wide","T+1 Geniş Radar",self.T1_COLUMNS),("t1elite","T+1 Seçkin",self.T1_COLUMNS),("t2wide","T+2 Geniş Radar",self.T2_COLUMNS),("t2elite","T+2 Seçkin",self.T2_COLUMNS),("ceiling","Tavan Hazırlık",self.T1_COLUMNS)):
            table=ResponsiveResultTable(f"radar_{key}"); context=AnalysisContext(f"radar_{key}",horizon="T+2" if key.startswith("t2") else "T+1")
            table.set_context(context); compact=[columns[0],"Hisse","Güncel Fiyat",columns[3],columns[4],columns[5],columns[-1]]
            table.configure_columns(compact,compact+columns[6:9],columns); table.detail_requested.connect(self._open_detail)
            table.cellClicked.connect(lambda row,col,t=table:self._selected(t,row)); self.tabs.addTab(table,title); self.tables[key]=table; self._fill(table,pd.DataFrame(columns=columns),columns,columns)
        ipo=ResponsiveResultTable("radar_ipo"); ipo.set_context(AnalysisContext("radar_ipo",horizon="Yeni Halka Arz",analysis_type="Hisse"))
        ipo_compact=["Hisse","İşlem Günü Sayısı","Halka Arz Fiyatı","Güncel Fiyat","Halka Arzdan Beri Getiri %","Momentum Durumu","Risk Durumu","Veri Yeterlilik Seviyesi"]
        ipo.configure_columns(ipo_compact,ipo_compact+["Kotasyon Tarihi","Göreceli Hacim"],self.IPO_COLUMNS); ipo.detail_requested.connect(self._open_detail)
        ipo.cellClicked.connect(lambda row,col,t=ipo:self._selected(t,row)); self.tabs.addTab(ipo,"Yeni Halka Arzlar"); self.tables["ipo"]=ipo; self._fill(ipo,pd.DataFrame(columns=self.IPO_COLUMNS),self.IPO_COLUMNS,self.IPO_HEADERS)
        self.filter_bar.filter_changed.connect(lambda text:[table.apply_filter(text) for table in self.tables.values()])
        self.filter_bar.reset_columns_requested.connect(lambda:[table.reset_columns() for table in self.tables.values()])
        left.addWidget(self.tabs,1); main.addLayout(left,1); self.detail=DetailPanel(); self.detail.hide(); root.addLayout(main,1)
        self.bottom_tabs=QTabWidget(); self.bottom_tabs.setMaximumHeight(112)
        perf,perfbox=card("Tahmin Performansı"); self.performance=QLabel("Yerel tahmin deposu bekleniyor"); self.performance.setWordWrap(True); perfbox.addWidget(self.performance)
        regime,regbox=card("Piyasa ve Sektör Rejimi"); self.regime=QLabel("Veri bekleniyor"); self.regime.setWordWrap(True); regbox.addWidget(self.regime)
        opened,openbox=card("Açık Tahminler"); self.open_predictions=QLabel("Açık tahmin kaydı bekleniyor"); self.open_predictions.setWordWrap(True); openbox.addWidget(self.open_predictions)
        self.bottom_tabs.addTab(perf,"Performans"); self.bottom_tabs.addTab(regime,"Piyasa Rejimi"); self.bottom_tabs.addTab(opened,"Açık Tahminler"); root.addWidget(self.bottom_tabs); self.refresh_store()
    def set_loading(self,text="Aktif BIST hisseleri taranıyor…"): self.stats.set_loading(text=text); self.scan.setEnabled(False)
    def set_error(self,text): self.stats.set_error("Tarama hatası: "+text+"\nÖnceki geçerli sonuç korunuyor."); self.scan.setEnabled(True)
    def load_results(self,frame,message=""):
        self.scan.setEnabled(True); self._full=frame.copy() if frame is not None else pd.DataFrame(); self.last_scan.setText("Son Tarama: "+datetime.now().strftime("%H:%M"))
        status=self._full.get("Durum",pd.Series(dtype=str)).astype(str)
        model=self._full.get("Model Yolu",pd.Series("",index=self._full.index)).astype(str)
        standard=~model.eq("YENI_HALKA_ARZ")
        t1=self._full.sort_values("T+1 Sırası",na_position="last") if "T+1 Sırası" in self._full else self._full
        t2=self._full.sort_values("T+2 Sırası",na_position="last") if "T+2 Sırası" in self._full else self._full
        t1type=t1.get("Menkul Türü",pd.Series("",index=t1.index)); t2type=t2.get("Menkul Türü",pd.Series("",index=t2.index))
        t1elite=t1[(pd.to_numeric(t1.get("T+1 %7+ Olasılığı"),errors="coerce")>=20)&(pd.to_numeric(t1.get("T+1 %8+ Olasılığı"),errors="coerce")>=10)&t1type.eq("NORMAL_PAY")&t1.get("T+1 Seviye Doğrulandı",pd.Series(False,index=t1.index)).fillna(False).astype(bool)&(pd.to_numeric(t1.get("T+1 Net EV"),errors="coerce")>0)].head(5)
        t2elite=t2[(pd.to_numeric(t2.get("T+2 %7+ Olasılığı"),errors="coerce")>=20)&(pd.to_numeric(t2.get("T+2 %8+ Olasılığı"),errors="coerce")>=10)&t2type.eq("NORMAL_PAY")&t2.get("T+2 Seviye Doğrulandı",pd.Series(False,index=t2.index)).fillna(False).astype(bool)&(pd.to_numeric(t2.get("T+2 Net EV"),errors="coerce")>0)].head(5)
        ceiling=t1.sort_values("T+1 Tavan Olasılığı",ascending=False,na_position="last").head(20) if "T+1 Tavan Olasılığı" in t1 else t1.head(0)
        groups={"t1wide":t1.head(30),"t1elite":t1elite,"t2wide":t2.head(30),"t2elite":t2elite,"ceiling":ceiling,"ipo":self._full[model.eq("YENI_HALKA_ARZ")]}
        for key,data in groups.items():
            if key=="ipo": self._fill(self.tables[key],data,self.IPO_COLUMNS,self.IPO_HEADERS)
            else:
                columns=self.T2_COLUMNS if key.startswith("t2") else self.T1_COLUMNS; self._fill(self.tables[key],data,columns,columns)
        elite_message = " Bugün güvenilir %7–10 hareket adayı bulunamadı." if t1elite.empty and t2elite.empty else ""
        state_text=(message or (f"{len(self._full)} hisse sıralandı" if not self._full.empty else "")) + elite_message
        self.stats.set_empty() if self._full.empty else self.stats.set_ready(state_text)
        self.summary_bar.update_metrics({"Taranan":len(self._full),"Geniş Radar":len(t1.head(30))+len(t2.head(30)),"Seçkin":len(t1elite)+len(t2elite),"Güçlü":int(status.str.contains("GÜÇLÜ",case=False,na=False).sum()),"Teyit":int(status.str.contains("TEYİT",case=False,na=False).sum()),"Veri Zamanı":datetime.now().strftime("%H:%M")})
        for index,(key,label) in enumerate((("t1wide","T+1 Geniş"),("t1elite","T+1 Seçkin"),("t2wide","T+2 Geniş"),("t2elite","T+2 Seçkin"),("ceiling","Tavan Hazırlık"),("ipo","Yeni Halka Arz"))): self.tabs.setTabText(index,f"{label}  {len(groups[key])}")
        if not self._full.empty: self.detail.set_row(self._full.iloc[0].to_dict())
        regimes=status if "Piyasa Rejimi" not in self._full else self._full["Piyasa Rejimi"].dropna().astype(str)
        self.regime.setText("BIST rejimi: "+(regimes.mode().iloc[0] if not regimes.empty else "Veri bekleniyor")+"\nPiyasa genişliği ve sektör çubukları: Veri bekleniyor")
        self.refresh_store()
    def _fill(self,table,data,columns=None,headers=None):
        columns,headers=columns or self.COLUMNS,headers or self.HEADERS
        table.load_frame(data,columns,headers)
    def _selected(self,table,row):
        record=table.record_for_visual_row(row) if hasattr(table,"record_for_visual_row") else None
        if record: self.detail.set_row(record)
    def _open_detail(self,record,context): self._detail_window.show_record(record,context)
    def resizeEvent(self,event):
        super().resizeEvent(event); profile=profile_for_width(self.width())
        for table in self.tables.values(): table.apply_profile(profile)
        compact=profile==PROFILE_COMPACT; self.subtitle.setVisible(not compact)
        for pill in self.header_pills: pill.setVisible(not compact)
        self.bottom_tabs.setVisible(self.height()>=570)
    def refresh_store(self):
        if not self.prediction_path.exists(): return
        try:
            from tahmin_deposu import TahminDeposu
            store=TahminDeposu(self.prediction_path); perf=store.performans(); pending=store.bekleyenler()
            total=perf.get("toplam",0); fp=(perf.get("basarisiz",0)/total*100) if total else None
            self.performance.setText(f"Toplam tahmin: {total}   ·   %8+ gören: {perf.get('yuzde8_goren',0)}   ·   Tavan gören: {perf.get('tavan_goren',0)}\nPrecision@1 / Precision@3 / 7-30-90 gün: Veri bekleniyor\nYanlış pozitif: {'Veri bekleniyor' if fp is None else f'%{fp:.1f}'}")
            lines=[f"{x.get('symbol','—')}  ·  {x.get('session_date','—')}  ·  {x.get('status','—')}" for x in pending[:4]]; self.open_predictions.setText("\n".join(lines) if lines else "Açık tahmin bulunmuyor")
        except Exception as exc: self.performance.setText("Performans verisi okunamadı: "+str(exc))


class T1T2PerformanceDashboard(QWidget):
    """Değiştirilemez Radar snapshot'larının gerçek T+1/T+2 sonuç ekranı."""
    COLUMNS=["Tarih","Hisse","Vade","Gerçekleşen Maksimum %","Tavan Gördü","Önceki Sıra","Geniş Radarda","Seçkin Aday"]
    def __init__(self, database_path: Path):
        super().__init__(); self.responsive_layout=True; self.analysis_id="prediction_performance"; self.database_path=Path(database_path); self._detail_window=AnalysisDetailWindow(self)
        root=QVBoxLayout(self); root.setContentsMargins(12,10,12,10); root.setSpacing(8)
        header=QHBoxLayout(); titles=QVBoxLayout(); title=QLabel("TAHMİN PERFORMANSI"); title.setObjectName("pageTitle")
        subtitle=QLabel("Yalnız önceden kaydedilmiş, değiştirilemez T+1/T+2 snapshot sonuçları"); subtitle.setObjectName("muted")
        titles.addWidget(title); titles.addWidget(subtitle); header.addLayout(titles); header.addStretch()
        refresh=QPushButton("Yenile"); refresh.setObjectName("primary"); refresh.clicked.connect(self.refresh); header.addWidget(refresh); root.addLayout(header)
        cards=QHBoxLayout(); self.t1=QLabel(); self.t2=QLabel(); self.data=QLabel()
        for label in (self.t1,self.t2,self.data): label.setObjectName("bottomCard"); label.setWordWrap(True); label.setMinimumHeight(90); cards.addWidget(label,1)
        root.addLayout(cards)
        self.notice=AnalysisStateWidget(); root.addWidget(self.notice)
        self.table=ResponsiveResultTable("prediction_performance"); self.table.set_context(AnalysisContext("prediction_performance",analysis_type="Hisse"))
        self.table.configure_columns(self.COLUMNS[:6],self.COLUMNS,self.COLUMNS); self.table.detail_requested.connect(self._detail_window.show_record)
        root.addWidget(self.table,1); self.refresh()
    @staticmethod
    def _fmt(value, percent=False):
        if value is None or pd.isna(value): return "—"
        return f"%{float(value)*100:.1f}" if percent else f"{float(value):.2f}"
    def refresh(self):
        try:
            from t1t2_tahmin_sistemi import EveningSnapshotStore
            store=EveningSnapshotStore(self.database_path); summary=store.performance_summary(); audit=store.winner_audit()
            for horizon,label in (("T+1",self.t1),("T+2",self.t2)):
                item=summary.get("horizons",{}).get(horizon,{})
                label.setText(f"{horizon} GERÇEK SONUÇ\nÖrnek: {item.get('total',0)} · %7+: {item.get('hit_7',0)} · Tavan: {item.get('hit_limit_up',0)}\nPrecision@3: {self._fmt(item.get('precision_at_3'),True)} · Recall@20: {self._fmt(item.get('recall_at_20'),True)}\nBrier %7: {self._fmt(item.get('brier_7'))}")
            self.data.setText(f"KAYIT DURUMU\nSonuçlanan snapshot: {summary.get('total',0)}\nGerçek %7+ hareket: {len(audit)}\nTahmin yoksa geçmiş sıra üretilmez")
            self.notice.set_ready("Sonuçlar yalnız tahmin tarihinde kaydedilmiş snapshot'larla eşleştirilir; bugünkü veriyle geriye dönük aday oluşturulmaz.")
            frame=pd.DataFrame(audit,columns=self.COLUMNS); self.table.load_frame(frame,self.COLUMNS,self.COLUMNS)
            if frame.empty: self.notice.set_empty("Henüz sonuçlanmış tahmin snapshot'ı yok.\nBugünkü veriyle sahte geçmiş sıra üretilmedi.")
        except Exception as exc:
            self.notice.set_error("Performans verisi okunamadı: "+str(exc)+"\nÖnceki geçerli sonuç korunuyor."); self.table.setRowCount(0)
    def resizeEvent(self,event):
        super().resizeEvent(event); self.table.apply_profile(profile_for_width(self.width()))


class PlaceholderPage(QWidget):
    def __init__(self,title,text="Bu sayfa ortak dashboard temasıyla hazırdır."):
        super().__init__(); self.responsive_layout=True; self.analysis_id="settings"; box=QVBoxLayout(self); box.setContentsMargins(12,10,12,10); heading=QLabel(title); heading.setObjectName("pageTitle"); box.addWidget(heading); panel=QLabel(text); panel.setObjectName("card"); panel.setWordWrap(True); panel.setAlignment(Qt.AlignCenter); box.addWidget(panel,1)
