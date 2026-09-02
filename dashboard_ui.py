"""Borsa Analiz masaustu uygulamasi icin ortak finans dashboard bileşenleri."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt, QObject, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
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
        self.name = QLabel(title); self.name.setObjectName("marketName"); box.addWidget(self.name)
        row = QHBoxLayout(); self.value = QLabel("Veri bekleniyor"); self.value.setObjectName("marketValue"); self.spark = Sparkline(); row.addWidget(self.value, 1); row.addWidget(self.spark); box.addLayout(row)
        self.change = QLabel("Veri bekleniyor"); self.change.setObjectName("dataTime"); box.addWidget(self.change)

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
        brand = QVBoxLayout(); title = QLabel("▥  Borsa Analiz"); title.setObjectName("brandTitle"); sub = QLabel("Daha Seçici Analiz, Daha Güçlü Kararlar"); sub.setObjectName("brandSub"); brand.addWidget(title); brand.addWidget(sub); row.addLayout(brand)
        self.search = QLineEdit(); self.search.setPlaceholderText("⌕  Hisse ara… (örn. TGSAS)"); self.search.setMaximumWidth(330); self.search.returnPressed.connect(lambda:self.search_requested.emit(self.search.text())); row.addWidget(self.search, 1)
        row.addStretch(); self.clock = QLabel(); self.clock.setObjectName("muted"); row.addWidget(self.clock)
        self.market = QLabel("● Piyasa durumu bekleniyor"); self.market.setObjectName("warning"); row.addWidget(self.market)
        for text, tip in (("♢", "Bildirimler"), ("⚙", "Ayarlar"), ("●", "Kullanıcı")):
            button=QPushButton(text); button.setObjectName("iconButton"); button.setToolTip(tip); button.setFixedWidth(34); row.addWidget(button)
        self.scan = QPushButton("↗  Tüm Hisse Analizlerini Başlat"); self.scan.setObjectName("primary"); self.scan.clicked.connect(self.scan_requested.emit); row.addWidget(self.scan)
        timer=QTimer(self); timer.timeout.connect(self._tick); timer.start(1000); self._tick()
    def _tick(self): self.clock.setText(datetime.now().strftime("%d %B %Y  %H:%M:%S"))


class Sidebar(QFrame):
    page_requested = Signal(str)
    ITEMS = [("next","◎","Yüksek Hareket Radarı"),("home","⌂","Ana Sayfa"),("daily","◉","Günlük Trade"),("short","▥","Kısa Vade · Tüm BIST"),("medium","▥","Orta Vade · Tüm BIST"),("under50","◫","50 TL Altı"),("funds","◈","Fon Analizi"),("portfolio","▣","Portföy"),("performance","⌁","Tahmin Performansı"),("settings","⚙","Ayarlar")]
    def __init__(self):
        super().__init__(); self.setObjectName("sidebar"); self.expanded=True; self.setFixedWidth(190)
        self.box=QVBoxLayout(self); self.box.setContentsMargins(6,7,6,7); self.box.setSpacing(3); self.buttons={}
        collapse=QPushButton("☰  Menüyü Daralt"); collapse.clicked.connect(self.toggle); self.box.addWidget(collapse); self.collapse=collapse
        for key, icon, text in self.ITEMS:
            button=QPushButton(f"{icon}  {text}"); button.setCheckable(True); button.setToolTip(text); button.clicked.connect(lambda checked=False,k=key:self.page_requested.emit(k)); self.box.addWidget(button); self.buttons[key]=button
        self.box.addStretch(); self.set_active("home")
    def toggle(self):
        self.expanded=not self.expanded; self.setFixedWidth(190 if self.expanded else 54); self.collapse.setText("☰  Menüyü Daralt" if self.expanded else "☰")
        for key, icon, text in self.ITEMS: self.buttons[key].setText(f"{icon}  {text}" if self.expanded else icon)
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
        super().__init__(); self.prediction_path=prediction_path; self._records=[]; self._full=pd.DataFrame(); root=QVBoxLayout(self); root.setContentsMargins(10,8,10,8); root.setSpacing(7)
        header=QHBoxLayout(); titles=QVBoxLayout(); title=QLabel("YÜKSEK HAREKET RADARI"); title.setObjectName("pageTitle"); sub=QLabel("T+1 / T+2 gün içi %7–10 hareket hazırlığı · Tüm aktif BIST"); sub.setObjectName("muted"); titles.addWidget(title); titles.addWidget(sub); header.addLayout(titles); header.addStretch()
        for text,obj in (("◎ Seans Sonrası","pillBlue"),("● Canlı Teyit","pillGreen")):
            lab=QLabel(text); lab.setObjectName(obj); header.addWidget(lab)
        self.last_scan=QLabel("Son Tarama: —"); self.last_scan.setObjectName("muted"); header.addWidget(self.last_scan); self.scan=QPushButton("Taramayı Başlat"); self.scan.setObjectName("primary"); self.scan.clicked.connect(self.scan_requested.emit); header.addWidget(self.scan); root.addLayout(header)
        self.stats=QLabel("Veri bekleniyor"); self.stats.setObjectName("muted"); root.addWidget(self.stats)
        main=QHBoxLayout(); main.setSpacing(8); left=QVBoxLayout(); self.tabs=QTabWidget(); self.tables={}
        for key,title,columns in (("t1wide","T+1 Geniş Radar",self.T1_COLUMNS),("t1elite","T+1 Seçkin",self.T1_COLUMNS),("t2wide","T+2 Geniş Radar",self.T2_COLUMNS),("t2elite","T+2 Seçkin",self.T2_COLUMNS),("ceiling","Tavan Hazırlık",self.T1_COLUMNS)):
            table=QTableWidget(); table.setAlternatingRowColors(True); table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setSelectionBehavior(QAbstractItemView.SelectRows); table.verticalHeader().hide(); table.setSortingEnabled(True); table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); table.cellClicked.connect(lambda row,col,t=table:self._selected(t,row)); self.tabs.addTab(table,title); self.tables[key]=table; self._fill(table,pd.DataFrame(columns=columns),columns,columns)
        ipo=QTableWidget(); ipo.setAlternatingRowColors(True); ipo.setEditTriggers(QAbstractItemView.NoEditTriggers); ipo.setSelectionBehavior(QAbstractItemView.SelectRows); ipo.verticalHeader().hide(); ipo.setSortingEnabled(True); ipo.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); ipo.cellClicked.connect(lambda row,col,t=ipo:self._selected(t,row)); self.tabs.addTab(ipo,"Yeni Halka Arzlar"); self.tables["ipo"]=ipo; self._fill(ipo,pd.DataFrame(columns=self.IPO_COLUMNS),self.IPO_COLUMNS,self.IPO_HEADERS)
        left.addWidget(self.tabs,1); main.addLayout(left,7); self.detail=DetailPanel(); self.detail.setMinimumWidth(245); main.addWidget(self.detail,3); root.addLayout(main,1)
        bottom=QHBoxLayout(); perf,perfbox=card("Tahmin Performansı"); self.performance=QLabel("Yerel tahmin deposu bekleniyor"); self.performance.setWordWrap(True); perfbox.addWidget(self.performance); regime,regbox=card("Piyasa ve Sektör Rejimi"); self.regime=QLabel("Veri bekleniyor"); self.regime.setWordWrap(True); regbox.addWidget(self.regime); opened,openbox=card("Açık Tahminler"); self.open_predictions=QLabel("Açık tahmin kaydı bekleniyor"); self.open_predictions.setWordWrap(True); openbox.addWidget(self.open_predictions)
        bottom.addWidget(perf,1); bottom.addWidget(regime,1); bottom.addWidget(opened,1); root.addLayout(bottom); self.refresh_store()
    def set_loading(self,text="Aktif BIST hisseleri taranıyor…"): self.stats.setText(text); self.scan.setEnabled(False)
    def set_error(self,text): self.stats.setText("Tarama hatası: "+text); self.scan.setEnabled(True)
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
        self.stats.setText((message or (f"{len(self._full)} hisse sıralandı" if not self._full.empty else "")) + elite_message)
        for index,(key,label) in enumerate((("t1wide","T+1 Geniş"),("t1elite","T+1 Seçkin"),("t2wide","T+2 Geniş"),("t2elite","T+2 Seçkin"),("ceiling","Tavan Hazırlık"),("ipo","Yeni Halka Arz"))): self.tabs.setTabText(index,f"{label}  {len(groups[key])}")
        if not self._full.empty: self.detail.set_row(self._full.iloc[0].to_dict())
        regimes=status if "Piyasa Rejimi" not in self._full else self._full["Piyasa Rejimi"].dropna().astype(str)
        self.regime.setText("BIST rejimi: "+(regimes.mode().iloc[0] if not regimes.empty else "Veri bekleniyor")+"\nPiyasa genişliği ve sektör çubukları: Veri bekleniyor")
        self.refresh_store()
    def _fill(self,table,data,columns=None,headers=None):
        columns,headers=columns or self.COLUMNS,headers or self.HEADERS
        table.setSortingEnabled(False); table.clear(); table.setColumnCount(len(columns)); table.setHorizontalHeaderLabels(headers); table.setRowCount(len(data)); records=data.to_dict("records")
        for r,row in enumerate(records):
            for c,name in enumerate(columns):
                value=row.get(name); text="—" if value is None or (isinstance(value,float) and pd.isna(value)) else f"{value:.2f}" if isinstance(value,(float,int)) else str(value)
                item=QTableWidgetItem(text); item.setData(Qt.UserRole,row); item.setToolTip(text); item.setTextAlignment(Qt.AlignLeft|Qt.AlignVCenter if name in ("Hisse","Durum","Momentum Durumu","Risk Durumu") else Qt.AlignRight|Qt.AlignVCenter)
                if name in ("Günlük Değişim %","Halka Arzdan Beri Getiri %"): item.setForeground(QColor(COLORS["green"] if float(value or 0)>=0 else COLORS["red"]))
                if name in ("Durum","Momentum Durumu","Risk Durumu"): item.setForeground(QColor(COLORS["orange"] if "RİSK" in text or "BEKL" in text or "KACTI" in text else COLORS["green"]))
                table.setItem(r,c,item)
        header=table.horizontalHeader(); header.setSectionResizeMode(QHeaderView.ResizeToContents if columns is self.IPO_COLUMNS else QHeaderView.Stretch); header.setSectionResizeMode(0,QHeaderView.ResizeToContents); table.verticalHeader().setDefaultSectionSize(27); table.setSortingEnabled(True)
    def _selected(self,table,row):
        item=table.item(row,0)
        if item: self.detail.set_row(item.data(Qt.UserRole) or {})
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
        super().__init__(); self.database_path=Path(database_path)
        root=QVBoxLayout(self); root.setContentsMargins(12,10,12,10); root.setSpacing(8)
        header=QHBoxLayout(); titles=QVBoxLayout(); title=QLabel("TAHMİN PERFORMANSI"); title.setObjectName("pageTitle")
        subtitle=QLabel("Yalnız önceden kaydedilmiş, değiştirilemez T+1/T+2 snapshot sonuçları"); subtitle.setObjectName("muted")
        titles.addWidget(title); titles.addWidget(subtitle); header.addLayout(titles); header.addStretch()
        refresh=QPushButton("Yenile"); refresh.setObjectName("primary"); refresh.clicked.connect(self.refresh); header.addWidget(refresh); root.addLayout(header)
        cards=QHBoxLayout(); self.t1=QLabel(); self.t2=QLabel(); self.data=QLabel()
        for label in (self.t1,self.t2,self.data): label.setObjectName("bottomCard"); label.setWordWrap(True); label.setMinimumHeight(90); cards.addWidget(label,1)
        root.addLayout(cards)
        self.notice=QLabel(); self.notice.setObjectName("muted"); self.notice.setWordWrap(True); root.addWidget(self.notice)
        self.table=QTableWidget(); self.table.setAlternatingRowColors(True); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.verticalHeader().hide(); self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.table,1); self.refresh()
    @staticmethod
    def _fmt(value, percent=False):
        if value is None or pd.isna(value): return "—"
        return f"%{float(value)*100:.1f}" if percent else f"{float(value):.2f}"
    def refresh(self):
        try:
            from t1t2_tahmin_sistemi import EveningSnapshotStore
            store=EveningSnapshotStore(self.database_path); summary=store.performance_summary(); audit=store.winner_audit(); insights=store.performance_insights()
            for horizon,label in (("T+1",self.t1),("T+2",self.t2)):
                item=summary.get("horizons",{}).get(horizon,{})
                label.setText(f"{horizon} GERÇEK SONUÇ\nÖrnek: {item.get('total',0)} · %7+: {item.get('hit_7',0)} · Tavan: {item.get('hit_limit_up',0)}\nPrecision@3: {self._fmt(item.get('precision_at_3'),True)} · Recall@20: {self._fmt(item.get('recall_at_20'),True)}\nBrier %7: {self._fmt(item.get('brier_7'))}")
            top=insights.get("top", {})
            top_text=" · ".join(f"İlk{k}: {v.get('rising',0)}/{v.get('count',0)} yükseldi, ort. max %{v.get('avg_max_return_pct','—')}" for k,v in top.items()) or "Yeterli günlük kayıt yok"
            missed_text=", ".join(f"{x['symbol']} (%{x['max_return_pct']:.1f}, sıra {x['rank']})" for x in insights.get("missed", [])[:4]) or "Yok/yeterli kayıt yok"
            fp_text=", ".join(f"{x['symbol']} (%{x['max_return_pct']:.1f})" for x in insights.get("false_positive", [])[:4]) or "Yok/yeterli kayıt yok"
            self.data.setText(f"KAYIT DURUMU\nSonuçlanan snapshot: {summary.get('total',0)}\nGerçek %7+ hareket: {len(audit)}\nDün İlk 5/10/20: {top_text}\nKaçırılan güçlüler: {missed_text}\nYanlış pozitifler: {fp_text}")
            self.notice.setText("Sonuçlar yalnız tahmin tarihinde kaydedilmiş snapshot'larla eşleştirilir; bugünkü veriyle geriye dönük aday oluşturulmaz.")
            # Geçmiş değişmez ve veritabanında eksiksiz korunur; ekranda yalnız
            # en güçlü/sonuçlanmış beş kayıt gösterilir.
            frame=pd.DataFrame(audit,columns=self.COLUMNS).head(5); self.table.clear(); self.table.setColumnCount(len(self.COLUMNS)); self.table.setHorizontalHeaderLabels(self.COLUMNS); self.table.setRowCount(len(frame))
            for row_index,row in frame.iterrows():
                for column_index,name in enumerate(self.COLUMNS):
                    value=row.get(name); text="—" if value is None else f"{value:.2f}" if isinstance(value,float) else str(value)
                    self.table.setItem(row_index,column_index,QTableWidgetItem(text))
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        except Exception as exc:
            self.notice.setText("Performans verisi okunamadı: "+str(exc)); self.table.setRowCount(0)


class PlaceholderPage(QWidget):
    def __init__(self,title,text="Bu sayfa ortak dashboard temasıyla hazırdır."):
        super().__init__(); box=QVBoxLayout(self); box.setContentsMargins(18,18,18,18); heading=QLabel(title); heading.setObjectName("pageTitle"); box.addWidget(heading); panel=QLabel(text); panel.setObjectName("card"); panel.setAlignment(Qt.AlignCenter); box.addWidget(panel,1)
