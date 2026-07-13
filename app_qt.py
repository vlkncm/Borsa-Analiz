import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

import pandas as pd
from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtGui import QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QFileDialog, QMessageBox, QFrame, QGridLayout, QLineEdit,
    QComboBox, QAbstractItemView, QDialog, QScrollArea, QCheckBox
)

from piyasa_guncelleme import tum_listeleri_guncelle, cache_halka_arz_oku, veri_yasi_gun


def global_exception_hook(exc_type, exc_value, exc_traceback):
    """
    Beklenmeyen arayüz hatalarını kullanıcıya gösterir ve loga yazar.
    Uygulamanın sessizce kapanmasını önler.
    """
    try:
        hata = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_dir = veri_klasoru() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "kritik_hatalar.log").open("a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().isoformat(timespec='seconds')}]\n{hata}\n")
        QMessageBox.critical(
            None,
            "Beklenmeyen Hata",
            "Program beklenmeyen bir hatayla karşılaştı. "
            "Hata kaydı Belgeler/Borsa Analiz Pro MAX/logs klasörüne yazıldı."
        )
    except Exception:
        pass

sys.excepthook = global_exception_hook

APP_NAME = "Borsa Analiz Pro MAX"
KAP_LIMIT = 30

LEGAL_VERSION = "3.4"
KISA_UYARI = (
    "Bu yazılım yatırım tavsiyesi veya yatırım danışmanlığı hizmeti sunmaz. "
    "Çıktılar genel nitelikte algoritmik karar destek verileridir; kesin getiri, "
    "fiyat hedefi ya da alım-satım garantisi değildir. Tüm karar ve risk kullanıcıya aittir."
)

SORUMLULUK_REDDI = """
BORSA ANALİZ PRO MAX — SORUMLULUK REDDİ VE KULLANIM UYARISI

1. Bu yazılım yatırım danışmanlığı, portföy yöneticiliği, aracılık veya kişiye özel yatırım tavsiyesi hizmeti sunmaz.
2. Yazılımın ürettiği puanlar, sıralamalar, hedefler, stop seviyeleri, görünümler ve olasılıklar; teknik, temel, istatistiksel ve kamuya açık verilerin algoritmik olarak işlenmesiyle oluşturulan genel nitelikte karar destek çıktılarıdır.
3. Çıktılar herhangi bir sermaye piyasası aracının yükseleceğini, düşeceğini, tavan olacağını veya belirli bir getiriyi sağlayacağını garanti etmez.
4. Veriler gecikebilir, eksik, hatalı veya güncelliğini yitirmiş olabilir. KAP, faaliyet raporu, haber ve fiyat verileri işlem öncesinde resmi kaynaklardan ayrıca doğrulanmalıdır.
5. Geçmiş performans ve backtest sonuçları gelecekteki performansın göstergesi veya garantisi değildir.
6. Kullanıcı; yatırım kararlarını kendi bilgi, mali durum, risk tercihi ve bağımsız değerlendirmesine göre verir. Doğabilecek kâr, zarar, vergi, komisyon ve diğer sonuçlardan kullanıcı sorumludur.
7. Yazılım sahibi; veri sağlayıcı kesintileri, hesaplama hataları, gecikmeler, kullanıcı işlemleri veya finansal kayıplar nedeniyle sorumluluk kabul etmez.
8. Yazılım üzerinden otomatik emir iletilmez. Kullanıcı, herhangi bir işlemi kendi hesabından ve kendi kararıyla gerçekleştirir.
9. Bu metnin kabulü, yürürlükteki mevzuattan doğan vazgeçilemez hakları ortadan kaldırmaz.

Satışa veya geniş kitlelere sunulmadan önce ürünün iş modeli, reklam dili ve fonksiyonlarının Türkiye'de sermaye piyasası mevzuatı konusunda uzman bir hukukçu tarafından incelenmesi önerilir.
""".strip()


def kabul_dosyasi() -> Path:
    return veri_klasoru() / f"yasal_kabul_{LEGAL_VERSION}.txt"


def gorunum_metni(value):
    harita = {
        "GÜÇLÜ AL": "GÜÇLÜ POZİTİF",
        "AL": "POZİTİF",
        "TUT": "NÖTR / İZLE",
        "SAT": "NEGATİF / RİSKLİ",
    }
    return harita.get(str(value), value)


def guvenli_gosterim_df(df):
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    sonuc = df.copy()
    for kolon in ["Broker Aksiyon", "Aksiyon", "Karar", "MTF Karar"]:
        if kolon in sonuc.columns:
            sonuc[kolon] = sonuc[kolon].map(gorunum_metni)
    sonuc = sonuc.rename(columns={
        "Broker Aksiyon": "Algoritmik Görünüm",
        "Aksiyon": "Teknik Görünüm",
        "AI Güven Puanı": "Algoritmik Güven Puanı",
        "Broker Yorum": "Algoritmik Yorum",
    })
    return sonuc


class YasalKabulDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Önemli kullanım uyarısı")
        self.setModal(True)
        self.resize(760, 620)
        layout = QVBoxLayout(self)
        baslik = QLabel("ÖNEMLİ UYARI — LÜTFEN OKUYUN")
        baslik.setObjectName("pageTitle")
        layout.addWidget(baslik)
        metin = QTextEdit()
        metin.setReadOnly(True)
        metin.setPlainText(SORUMLULUK_REDDI)
        layout.addWidget(metin, 1)
        self.onay = QCheckBox("Metni okudum, anladım ve kabul ediyorum.")
        self.onay.stateChanged.connect(self.onay_degisti)
        layout.addWidget(self.onay)
        butonlar = QHBoxLayout()
        vazgec = QPushButton("Çıkış")
        vazgec.clicked.connect(self.reject)
        self.gir = QPushButton("Programa Gir")
        self.gir.setEnabled(False)
        self.gir.clicked.connect(self.accept)
        butonlar.addWidget(vazgec)
        butonlar.addStretch()
        butonlar.addWidget(self.gir)
        layout.addLayout(butonlar)

    def onay_degisti(self):
        self.gir.setEnabled(self.onay.isChecked())


def uygulama_klasoru() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def veri_klasoru() -> Path:
    belgeler = Path.home() / "Documents"
    if not belgeler.exists():
        belgeler = Path.home()
    ana = belgeler / APP_NAME
    (ana / "output" / "grafikler").mkdir(parents=True, exist_ok=True)
    (ana / "logs").mkdir(parents=True, exist_ok=True)
    return ana


def en_yeni_excel():
    dosyalar = list((veri_klasoru() / "output").glob("*.xlsx"))
    return max(dosyalar, key=lambda p: p.stat().st_mtime) if dosyalar else None


class LogStream(QObject):
    text_ready = Signal(str)

    def write(self, text):
        if text:
            self.text_ready.emit(str(text))

    def flush(self):
        pass



class PiyasaGuncellemeWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, object, str)

    def run(self):
        try:
            self.log.emit("Güncel BIST ve halka arz listeleri kontrol ediliyor...\n")
            sonuc = tum_listeleri_guncelle()
            self.finished.emit(True, sonuc, sonuc.get("mesaj", "Listeler güncellendi."))
        except Exception:
            hata = traceback.format_exc()
            self.log.emit("Piyasa listesi güncelleme hatası:\n" + hata + "\n")
            self.finished.emit(False, {}, "Listeler güncellenemedi; son kayıtlar kullanılacak.")


class AnalysisWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def run(self):
        eski_stdout, eski_stderr = sys.stdout, sys.stderr
        stream = LogStream()
        stream.text_ready.connect(self.log.emit)
        try:
            os.environ["PRO_ANALIZ_LIMIT"] = str(KAP_LIMIT)
            os.environ["KAP_ANALIZ_LIMIT"] = str(KAP_LIMIT)
            os.chdir(uygulama_klasoru())
            sys.stdout = stream
            sys.stderr = stream
            self.log.emit("Analiz motoru yükleniyor...\n")
            import main
            main.main()
            self.finished.emit(True, "Analiz tamamlandı.")
        except Exception:
            self.log.emit("\nHATA OLUŞTU:\n" + traceback.format_exc() + "\n")
            self.finished.emit(False, "Analiz sırasında hata oluştu.")
        finally:
            sys.stdout, sys.stderr = eski_stdout, eski_stderr


class VeriTablosu(QWidget):
    def __init__(self, baslik):
        super().__init__()
        self.df = pd.DataFrame()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        ust = QHBoxLayout()
        title = QLabel(baslik)
        title.setObjectName("pageTitle")
        ust.addWidget(title)
        ust.addStretch()
        self.arama = QLineEdit()
        self.arama.setPlaceholderText("Tabloda ara...")
        self.arama.setFixedWidth(260)
        self.arama.textChanged.connect(self.filtrele)
        ust.addWidget(self.arama)
        layout.addLayout(ust)

        self.bilgi = QLabel("Henüz veri yüklenmedi.")
        self.bilgi.setObjectName("subText")
        layout.addWidget(self.bilgi)

        self.tablo = QTableWidget()
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setSortingEnabled(True)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tablo.verticalHeader().setVisible(False)
        layout.addWidget(self.tablo)

    def dataframe_yukle(self, df):
        self.df = guvenli_gosterim_df(df)
        self.arama.clear()
        self._tabloya_yaz(self.df)

    def filtrele(self, metin):
        if self.df.empty:
            return
        metin = metin.strip().lower()
        if not metin:
            self._tabloya_yaz(self.df)
            return
        maske = self.df.astype(str).apply(lambda s: s.str.lower().str.contains(metin, na=False)).any(axis=1)
        self._tabloya_yaz(self.df[maske])

    def _tabloya_yaz(self, df):
        self.tablo.setSortingEnabled(False)
        self.tablo.clear()
        self.tablo.setRowCount(len(df))
        self.tablo.setColumnCount(len(df.columns))
        self.tablo.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r, (_, row) in enumerate(df.iterrows()):
            for c, value in enumerate(row):
                if pd.isna(value):
                    text = "Veri yok"
                elif isinstance(value, float):
                    text = f"{value:.2f}"
                else:
                    text = str(value).strip() or "Veri yok"
                self.tablo.setItem(r, c, QTableWidgetItem(text))
        self.bilgi.setText(f"Gösterilen satır: {len(df)}")
        self.tablo.resizeColumnsToContents()
        self.tablo.setSortingEnabled(True)


class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        ust = QHBoxLayout()
        baslik = QLabel("Dashboard")
        baslik.setObjectName("pageTitle")
        ust.addWidget(baslik)
        ust.addStretch()
        self.rapor_tarihi = QLabel("Rapor yüklenmedi")
        self.rapor_tarihi.setObjectName("subText")
        ust.addWidget(self.rapor_tarihi)
        layout.addLayout(ust)

        # Özet kartları
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.kartlar = {}

        kart_tanimlari = [
            ("toplam", "Toplam Hisse"),
            ("pozitif", "Güçlü / Pozitif"),
            ("tut", "Nötr / İzle"),
            ("sat", "Negatif / Riskli"),
            ("potansiyel", "2-6 Hafta Adayı"),
            ("temettu", "Yaklaşan Temettü"),
        ]

        for i, (key, title) in enumerate(kart_tanimlari):
            kart = QFrame()
            kart.setObjectName("card")
            kart.setMinimumHeight(92)
            k = QVBoxLayout(kart)
            k.setContentsMargins(14, 12, 14, 12)
            t = QLabel(title)
            t.setObjectName("cardTitle")
            v = QLabel("0")
            v.setObjectName("cardValue")
            k.addWidget(t)
            k.addWidget(v)
            grid.addWidget(kart, i // 3, i % 3)
            self.kartlar[key] = v

        layout.addLayout(grid)

        # Alt tablolar birbirinden ayrılmış iki panelde.
        alt = QHBoxLayout()
        alt.setSpacing(12)

        aday_panel = QFrame()
        aday_panel.setObjectName("card")
        aday_layout = QVBoxLayout(aday_panel)
        aday_baslik = QLabel("Bugünün En Yüksek Puanlı 5 Adayı")
        aday_baslik.setObjectName("cardTitle")
        aday_layout.addWidget(aday_baslik)

        self.aday_tablosu = QTableWidget()
        self.aday_tablosu.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.aday_tablosu.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.aday_tablosu.verticalHeader().setVisible(False)
        self.aday_tablosu.setAlternatingRowColors(True)
        aday_layout.addWidget(self.aday_tablosu)

        temettu_panel = QFrame()
        temettu_panel.setObjectName("card")
        temettu_layout = QVBoxLayout(temettu_panel)
        temettu_baslik = QLabel("En Yakın 5 Temettü")
        temettu_baslik.setObjectName("cardTitle")
        temettu_layout.addWidget(temettu_baslik)

        self.temettu_tablosu = QTableWidget()
        self.temettu_tablosu.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.temettu_tablosu.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.temettu_tablosu.verticalHeader().setVisible(False)
        self.temettu_tablosu.setAlternatingRowColors(True)
        temettu_layout.addWidget(self.temettu_tablosu)

        alt.addWidget(aday_panel, 3)
        alt.addWidget(temettu_panel, 2)
        layout.addLayout(alt, 1)

    @staticmethod
    def _tablo_doldur(widget, df, kolonlar, max_rows=5):
        mevcut = [c for c in kolonlar if c in df.columns]
        goster = df[mevcut].head(max_rows).copy() if not df.empty and mevcut else pd.DataFrame()

        widget.setSortingEnabled(False)
        widget.clear()
        widget.setRowCount(len(goster))
        widget.setColumnCount(len(mevcut))
        widget.setHorizontalHeaderLabels([str(c) for c in mevcut])

        for r, (_, row) in enumerate(goster.iterrows()):
            for c, value in enumerate(row):
                if pd.isna(value):
                    text = "-"
                elif isinstance(value, pd.Timestamp):
                    text = value.strftime("%d.%m.%Y")
                elif isinstance(value, float):
                    text = f"{value:.2f}"
                else:
                    text = str(value)
                widget.setItem(r, c, QTableWidgetItem(text))

        widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        widget.setSortingEnabled(True)

    def guncelle(self, sayfalar, rapor):
        tum = sayfalar.get("Tum Sonuclar", pd.DataFrame())
        self.kartlar["toplam"].setText(str(len(tum)))

        pozitif = tut = sat = 0
        if not tum.empty:
            col = "Broker Aksiyon" if "Broker Aksiyon" in tum.columns else (
                "Aksiyon" if "Aksiyon" in tum.columns else None
            )
            if col:
                s = tum[col].astype(str)
                pozitif = int(((s == "GÜÇLÜ AL") | (s == "AL")).sum())
                tut = int((s == "TUT").sum())
                sat = int((s == "SAT").sum())

        self.kartlar["pozitif"].setText(str(pozitif))
        self.kartlar["tut"].setText(str(tut))
        self.kartlar["sat"].setText(str(sat))

        pot = sayfalar.get("2-6 Hafta Potansiyel", pd.DataFrame())
        self.kartlar["potansiyel"].setText(str(len(pot)))

        temettu = sayfalar.get("Temettu Takip", pd.DataFrame())
        yaklasan_sayi = 0
        if not temettu.empty and "Kalan Gün" in temettu.columns:
            kalan = pd.to_numeric(temettu["Kalan Gün"], errors="coerce")
            yaklasan_sayi = int((kalan >= 0).sum())
            temettu = temettu[kalan >= 0].copy()
            temettu["_kalan"] = pd.to_numeric(temettu["Kalan Gün"], errors="coerce")
            temettu = temettu.sort_values("_kalan").drop(columns="_kalan")
        self.kartlar["temettu"].setText(str(yaklasan_sayi))

        adaylar = sayfalar.get("Bugunun Firsatlari", pd.DataFrame())
        if adaylar.empty:
            adaylar = tum

        self._tablo_doldur(
            self.aday_tablosu,
            adaylar,
            ["Hisse", "v4 Görünüm", "v4 Güven Puanı", "v4 2-6 Hafta Puanı", "Risk/Getiri 1"],
            max_rows=5
        )
        self._tablo_doldur(
            self.temettu_tablosu,
            temettu,
            ["Hisse", "Yaklaşan Temettü/Ex-Date", "Kalan Gün", "Temettü Verimi %"],
            max_rows=5
        )

        self.rapor_tarihi.setText(
            "Son rapor: " + datetime.fromtimestamp(rapor.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        )



class FirsatlarSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        self.df = pd.DataFrame()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)

        title = QLabel("Bugünün Yüksek Puanlı Adayları")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        info = QLabel("En yüksek puanlı 10 aday; genel nitelikte algoritmik karar destek çıktısıdır. Yatırım tavsiyesi ve kesin getiri garantisi değildir.")
        info.setWordWrap(True)
        info.setObjectName("infoBox")
        layout.addWidget(info)

        self.tablo = QTableWidget()
        self.tablo.setAlternatingRowColors(True)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSortingEnabled(True)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tablo.doubleClicked.connect(self.detay_ac)
        layout.addWidget(self.tablo)

        hint = QLabel("Bir hisseye çift tıklayarak ayrıntıları açabilirsin.")
        hint.setObjectName("subText")
        layout.addWidget(hint)

    def dataframe_yukle(self, df):
        self.df = guvenli_gosterim_df(df)
        self.tablo.setSortingEnabled(False)
        self.tablo.clear()
        self.tablo.setRowCount(len(self.df))
        self.tablo.setColumnCount(len(self.df.columns))
        self.tablo.setHorizontalHeaderLabels([str(c) for c in self.df.columns])
        for r, (_, row) in enumerate(self.df.iterrows()):
            for c, value in enumerate(row):
                text = "" if pd.isna(value) else (f"{value:.2f}" if isinstance(value, float) else str(value))
                self.tablo.setItem(r, c, QTableWidgetItem(text))
        self.tablo.resizeColumnsToContents()
        self.tablo.setSortingEnabled(True)

    def detay_ac(self, index):
        if self.df.empty or index.row() >= len(self.df):
            return
        row = self.df.iloc[index.row()]
        dlg = QDialog(self)
        dlg.setWindowTitle(str(row.get("Hisse", "Hisse Detayı")))
        dlg.resize(760, 650)
        l = QVBoxLayout(dlg)

        baslik = QLabel(f"{row.get('Hisse','')} — {row.get('Fırsat Seviyesi','')}")
        baslik.setObjectName("pageTitle")
        l.addWidget(baslik)

        alanlar = [
            ("Algoritmik Güven Puanı", row.get("Algoritmik Güven Puanı", "")),
            ("Algoritmik Görünüm", row.get("Algoritmik Görünüm", "")),
            ("Fiyat", row.get("Fiyat", "")),
            ("Alış Aralığı", f"{row.get('Alış Alt','')} – {row.get('Alış Üst','')}"),
            ("Stop", row.get("Stop Loss", "")),
            ("Hedefler", f"{row.get('Hedef 1','')} / {row.get('Hedef 2','')}"),
            ("Beklenen Getiri", f"%{row.get('Beklenen Getiri %','')}"),
            ("Tahmini Süre", row.get("Tahmini Süre", "")),
            ("MTF", f"{row.get('MTF Karar','')} ({row.get('MTF Skor','')})"),
            ("Temel / Faaliyet", f"{row.get('Temel Puan','')} / {row.get('Faaliyet Puanı','')}"),
            ("KAP / Haber", f"{row.get('KAP Etiket','')} / {row.get('Haber Etiket','')}"),
        ]
        for ad, deger in alanlar:
            lab = QLabel(f"<b>{ad}:</b> {deger}")
            lab.setWordWrap(True)
            lab.setObjectName("infoBox")
            l.addWidget(lab)

        neden = QLabel(f"<b>Neden seçildi?</b><br>{row.get('Seçilme Nedenleri','')}")
        neden.setWordWrap(True)
        neden.setObjectName("infoBox")
        l.addWidget(neden)

        yorum = QLabel(f"<b>Algoritmik değerlendirme:</b><br>{row.get('Algoritmik Yorum','')}")
        yorum.setWordWrap(True)
        yorum.setObjectName("infoBox")
        l.addWidget(yorum)

        kapat = QPushButton("Kapat")
        kapat.clicked.connect(dlg.accept)
        l.addWidget(kapat)
        dlg.exec()

class GrafiklerSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(16,16,16,16)
        title = QLabel("Grafikler"); title.setObjectName("pageTitle"); layout.addWidget(title)
        self.secim = QComboBox(); self.secim.currentIndexChanged.connect(self.grafik_goster); layout.addWidget(self.secim)
        self.gorsel = QLabel("Grafik seçilmedi"); self.gorsel.setAlignment(Qt.AlignCenter); self.gorsel.setMinimumHeight(500); self.gorsel.setObjectName("imagePanel"); layout.addWidget(self.gorsel,1)
        b = QPushButton("Grafik Klasörünü Aç"); b.clicked.connect(lambda: os.startfile(veri_klasoru()/"output"/"grafikler")); layout.addWidget(b)
        self.dosyalar = []

    def yenile(self):
        klasor = veri_klasoru()/"output"/"grafikler"; klasor.mkdir(parents=True, exist_ok=True)
        self.dosyalar = sorted(klasor.glob("*.png")); self.secim.clear()
        for p in self.dosyalar: self.secim.addItem(p.stem)
        if not self.dosyalar: self.gorsel.setText("Henüz grafik oluşturulmadı.")

    def grafik_goster(self, index):
        if index < 0 or index >= len(self.dosyalar): return
        pix = QPixmap(str(self.dosyalar[index]))
        self.gorsel.setPixmap(pix.scaled(self.gorsel.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event); self.grafik_goster(self.secim.currentIndex())


class RaporlarSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__(); self.ana = ana
        layout = QVBoxLayout(self); layout.setContentsMargins(16,16,16,16)
        title = QLabel("Raporlar"); title.setObjectName("pageTitle"); layout.addWidget(title)
        self.label = QLabel("Henüz rapor yok"); self.label.setObjectName("infoBox"); self.label.setWordWrap(True); layout.addWidget(self.label)
        b1 = QPushButton("Son Excel Raporunu Aç"); b1.clicked.connect(self.excel_ac); layout.addWidget(b1)
        b2 = QPushButton("Rapor Klasörünü Aç"); b2.clicked.connect(lambda: os.startfile(veri_klasoru()/"output")); layout.addWidget(b2)
        b3 = QPushButton("Başka Excel Dosyası Seç"); b3.clicked.connect(self.farkli_sec); layout.addWidget(b3)
        layout.addStretch()

    def excel_ac(self):
        if self.ana.aktif_rapor and self.ana.aktif_rapor.exists(): os.startfile(self.ana.aktif_rapor)
        else: QMessageBox.warning(self,"Rapor yok","Açılacak rapor bulunamadı.")

    def farkli_sec(self):
        f,_ = QFileDialog.getOpenFileName(self,"Excel raporu seç",str(veri_klasoru()/"output"),"Excel (*.xlsx)")
        if f: self.ana.rapor_yukle(Path(f))

    def guncelle(self, rapor):
        self.label.setText(str(rapor) if rapor else "Henüz rapor yok")


class YasalUyariSayfasi(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        title = QLabel("Yasal Uyarı / Hakkında")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        metin = QTextEdit()
        metin.setReadOnly(True)
        metin.setPlainText(SORUMLULUK_REDDI + "\n\nSürüm: 3.4\nYayıncı: V Software")
        layout.addWidget(metin)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME + " v4.1")
        self.resize(1500, 900)
        icon = uygulama_klasoru()/"logo.ico"
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
        self.aktif_rapor = None; self.sayfalar = {}; self.analysis_thread = None; self.analysis_worker = None
        self.piyasa_thread = None; self.piyasa_worker = None

        central = QWidget(); self.setCentralWidget(central)
        dis = QVBoxLayout(central); dis.setContentsMargins(0,0,0,0); dis.setSpacing(0)
        ana_widget = QWidget()
        ana = QHBoxLayout(ana_widget); ana.setContentsMargins(0,0,0,0); ana.setSpacing(0)
        ana.addWidget(self.sol_menu_olustur())
        self.stack = QStackedWidget(); ana.addWidget(self.stack,1)
        dis.addWidget(ana_widget, 1)
        footer = QLabel(
            "UYARI: Bu yazılım yatırım tavsiyesi veya yatırım danışmanlığı hizmeti sunmaz. "
            "Algoritmik analiz ve karar destek aracıdır. Nihai karar kullanıcıya aittir."
        )
        footer.setWordWrap(True)
        footer.setObjectName("legalFooter")
        footer.setAlignment(Qt.AlignCenter)
        footer.setMinimumHeight(52)
        footer.setMaximumHeight(72)
        dis.addWidget(footer)

        self.dashboard = Dashboard(); self.firsatlar = FirsatlarSayfasi(); self.tum = VeriTablosu("Tüm Sonuçlar"); self.pot = VeriTablosu("2-6 Hafta Potansiyel")
        self.tem = VeriTablosu("Temettü Takibi"); self.kap = VeriTablosu("KAP / Haber")
        self.faaliyet = VeriTablosu("Faaliyet Raporları")
        self.halka_arz = VeriTablosu("Halka Arzlar — SPK Başvuruları ve Tamamlanan Arzlar")
        self.back = VeriTablosu("Backtest")
        self.graf = GrafiklerSayfasi(); self.raporlar = RaporlarSayfasi(self); self.log = self.log_sayfasi(); self.yasal = YasalUyariSayfasi()
        for w in [self.dashboard,self.firsatlar,self.tum,self.pot,self.tem,self.kap,self.faaliyet,self.halka_arz,self.back,self.graf,self.raporlar,self.log,self.yasal]: self.stack.addWidget(w)
        self.stil_uygula()
        r = en_yeni_excel()
        if r: self.rapor_yukle(r)

        self.halka_arz.dataframe_yukle(cache_halka_arz_oku())
        self.piyasa_guncelle_baslat()

    def sol_menu_olustur(self):
        """
        Farklı ekran çözünürlüklerinde taşmayan sol menü.
        Menü seçenekleri kaydırılabilir, durum ve işlem düğmeleri altta sabittir.
        """
        menu = QFrame()
        menu.setObjectName("sidebar")
        menu.setMinimumWidth(270)
        menu.setMaximumWidth(310)

        ana_layout = QVBoxLayout(menu)
        ana_layout.setContentsMargins(12, 12, 12, 12)
        ana_layout.setSpacing(8)

        # Logo ve marka
        lp = uygulama_klasoru() / "logo.png"
        if lp.exists():
            logo_label = QLabel()
            logo_label.setObjectName("sidebarLogo")
            logo_label.setPixmap(
                QPixmap(str(lp)).scaled(
                    105, 105, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setMaximumHeight(110)
            ana_layout.addWidget(logo_label)

        brand = QLabel("BORSA ANALİZ\nPRO MAX v4.2.1")
        brand.setAlignment(Qt.AlignCenter)
        brand.setObjectName("brand")
        brand.setMaximumHeight(66)
        ana_layout.addWidget(brand)

        # Menü seçenekleri kaydırılabilir alanda
        scroll = QScrollArea()
        scroll.setObjectName("menuScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        menu_icerik = QWidget()
        menu_icerik.setObjectName("menuContent")
        menu_layout = QVBoxLayout(menu_icerik)
        menu_layout.setContentsMargins(0, 4, 0, 4)
        menu_layout.setSpacing(4)

        menu_items = [
            ("Dashboard", 0),
            ("Bugünün Fırsatları", 1),
            ("Tüm Sonuçlar", 2),
            ("2-6 Hafta Potansiyel", 3),
            ("Temettü Takibi", 4),
            ("KAP / Haber", 5),
            ("Faaliyet Raporları", 6),
            ("Halka Arzlar", 7),
            ("Backtest", 8),
            ("Grafikler", 9),
            ("Raporlar", 10),
            ("Canlı Log", 11),
            ("Yasal Uyarı / Hakkında", 12),
        ]

        for text, index in menu_items:
            buton = QPushButton(text)
            buton.setObjectName("menuButton")
            buton.setMinimumHeight(36)
            buton.setMaximumHeight(42)
            buton.clicked.connect(
                lambda checked=False, i=index: self.sayfa_degistir(i)
            )
            menu_layout.addWidget(buton)

        menu_layout.addStretch()
        scroll.setWidget(menu_icerik)
        ana_layout.addWidget(scroll, 1)

        # Alt bölüm sabit: durum + üç işlem düğmesi
        alt_panel = QFrame()
        alt_panel.setObjectName("sidebarBottom")
        alt_layout = QVBoxLayout(alt_panel)
        alt_layout.setContentsMargins(0, 8, 0, 0)
        alt_layout.setSpacing(8)

        self.piyasa_durum = QLabel("Henüz güncellenmedi")
        self.piyasa_durum.setWordWrap(True)
        self.piyasa_durum.setAlignment(Qt.AlignCenter)
        self.piyasa_durum.setObjectName("marketStatus")
        self.piyasa_durum.setMinimumHeight(48)
        self.piyasa_durum.setMaximumHeight(72)
        alt_layout.addWidget(self.piyasa_durum)

        guncelle = QPushButton("LİSTELERİ GÜNCELLE")
        guncelle.setObjectName("updateButton")
        guncelle.setMinimumHeight(44)
        guncelle.clicked.connect(self.piyasa_guncelle_baslat)
        alt_layout.addWidget(guncelle)

        self.analiz_buton = QPushButton("ANALİZİ BAŞLAT")
        self.analiz_buton.setObjectName("startButton")
        self.analiz_buton.setMinimumHeight(46)
        self.analiz_buton.clicked.connect(self.analiz_baslat)
        alt_layout.addWidget(self.analiz_buton)

        rapor_yenile = QPushButton("RAPORU YENİLE")
        rapor_yenile.setObjectName("refreshButton")
        rapor_yenile.setMinimumHeight(44)
        rapor_yenile.clicked.connect(self.son_raporu_yukle)
        alt_layout.addWidget(rapor_yenile)

        ana_layout.addWidget(alt_panel)
        return menu

    def log_sayfasi(self):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(16,16,16,16)
        t=QLabel("Canlı Analiz Logu"); t.setObjectName("pageTitle"); l.addWidget(t)
        self.log_alani=QTextEdit(); self.log_alani.setReadOnly(True); l.addWidget(self.log_alani); return w

    def sayfa_degistir(self,index):
        self.stack.setCurrentIndex(index)
        if index==9: self.graf.yenile()


    def piyasa_guncelle_baslat(self):
        try:
            if self.piyasa_thread is not None and self.piyasa_thread.isRunning():
                return
        except RuntimeError:
            # Önceki Qt thread nesnesi deleteLater ile silinmiş olabilir.
            self.piyasa_thread = None
            self.piyasa_worker = None

        self.piyasa_durum.setText("Listeler güncelleniyor...")
        self.piyasa_thread = QThread()
        self.piyasa_worker = PiyasaGuncellemeWorker()
        self.piyasa_worker.moveToThread(self.piyasa_thread)

        self.piyasa_thread.started.connect(self.piyasa_worker.run)
        self.piyasa_worker.log.connect(self.log_ekle)
        self.piyasa_worker.finished.connect(self.piyasa_guncelle_bitti)
        self.piyasa_worker.finished.connect(self.piyasa_thread.quit)
        self.piyasa_thread.finished.connect(self.piyasa_worker.deleteLater)
        self.piyasa_thread.finished.connect(self._piyasa_thread_temizle)
        self.piyasa_thread.start()

    def _piyasa_thread_temizle(self):
        thread = self.piyasa_thread
        self.piyasa_worker = None
        self.piyasa_thread = None
        if thread is not None:
            try:
                thread.deleteLater()
            except RuntimeError:
                pass

    def piyasa_guncelle_bitti(self, basarili, sonuc, mesaj):
        try:
            if basarili:
                halka_df = sonuc.get("halka_arz_df", pd.DataFrame())
                self.halka_arz.dataframe_yukle(halka_df)
                metadata = sonuc.get("metadata", {})
                yas = sonuc.get("veri_yasi_gun")

                if yas is None:
                    yas_text = "veri yaşı bilinmiyor"
                elif yas == 0:
                    yas_text = "bugün güncellendi"
                else:
                    yas_text = f"{yas} günlük veri"

                if not metadata.get("bist_basarili") or not metadata.get("halka_arz_basarili"):
                    self.piyasa_durum.setText(
                        f"KISMİ GÜNCELLEME\n"
                        f"{metadata.get('hisse_sayisi', 0)} hisse • "
                        f"{metadata.get('halka_arz_kayit_sayisi', 0)} halka arz\n"
                        f"{yas_text}"
                    )
                else:
                    self.piyasa_durum.setText(
                        f"LISTELER GÜNCEL\n"
                        f"{metadata.get('hisse_sayisi', 0)} hisse • "
                        f"{metadata.get('halka_arz_kayit_sayisi', 0)} halka arz"
                    )
                self.log_ekle(mesaj + "\n")
            else:
                self.halka_arz.dataframe_yukle(cache_halka_arz_oku())
                yas = veri_yasi_gun()
                yas_text = "bilinmiyor" if yas is None else f"{yas} gün"
                self.piyasa_durum.setText(
                    f"GÜNCELLEME BAŞARISIZ\n"
                    f"Son güvenilir kayıt kullanılıyor\n"
                    f"Veri yaşı: {yas_text}"
                )
                self.log_ekle(mesaj + "\n")
        except Exception:
            self.log_ekle("Piyasa güncelleme sonucu işlenirken hata oluştu:\n")
            self.log_ekle(traceback.format_exc() + "\n")

    def analiz_baslat(self):
        if self.analysis_thread and self.analysis_thread.isRunning():
            QMessageBox.information(self,"Analiz devam ediyor","Analiz zaten çalışıyor."); return
        self.log_alani.clear(); self.stack.setCurrentIndex(11); self.analiz_buton.setEnabled(False); self.analiz_buton.setText("ANALİZ ÇALIŞIYOR...")
        self.analysis_thread=QThread(); self.analysis_worker=AnalysisWorker(); self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run); self.analysis_worker.log.connect(self.log_ekle); self.analysis_worker.finished.connect(self.analiz_bitti); self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_thread.start()

    def log_ekle(self,metin):
        self.log_alani.moveCursor(QTextCursor.End); self.log_alani.insertPlainText(metin); self.log_alani.ensureCursorVisible()

    def analiz_bitti(self,basarili,mesaj):
        self.analiz_buton.setEnabled(True); self.analiz_buton.setText("ANALİZİ BAŞLAT")
        if basarili: self.son_raporu_yukle(); QMessageBox.information(self,"Tamamlandı",mesaj)
        else: QMessageBox.critical(self,"Hata",mesaj)

    def son_raporu_yukle(self):
        r=en_yeni_excel()
        if r: self.rapor_yukle(r)
        else: QMessageBox.warning(self,"Rapor yok","Excel raporu bulunamadı.")

    def rapor_yukle(self,rapor):
        try: sayfalar=pd.read_excel(rapor,sheet_name=None)
        except PermissionError:
            QMessageBox.critical(
                self,
                "Rapor açılamadı",
                "Rapor dosyasına erişim yok. Dosya başka bir program tarafından kullanılıyor olabilir."
            )
            return
        except Exception as e:
            QMessageBox.critical(self, "Rapor açılamadı", str(e))
            return
        self.aktif_rapor=rapor; self.sayfalar=sayfalar; self.dashboard.guncelle(sayfalar,rapor)
        self.firsatlar.dataframe_yukle(sayfalar.get("Bugunun Firsatlari", pd.DataFrame()))
        self.tum.dataframe_yukle(sayfalar.get("Tum Sonuclar",pd.DataFrame()))
        pot_df = sayfalar.get("2-6 Hafta Potansiyel", pd.DataFrame())
        if pot_df.empty:
            pot_df = sayfalar.get("2-6 Hafta Yakin", pd.DataFrame()).copy()
            if not pot_df.empty:
                pot_df.insert(0, "Bilgi", "Katı filtrede aday çıkmadı; bunlar yakın adaylardır")
        self.pot.dataframe_yukle(pot_df)
        self.tem.dataframe_yukle(sayfalar.get("Temettu Takip",pd.DataFrame()))
        tum=sayfalar.get("Tum Sonuclar",pd.DataFrame())
        if not tum.empty:
            cols=[c for c in tum.columns if any(k in str(c).lower() for k in ["kap","haber","hisse","broker","fiyat"])]
            self.kap.dataframe_yukle(tum[cols] if cols else tum)
        else: self.kap.dataframe_yukle(pd.DataFrame())
        self.faaliyet.dataframe_yukle(sayfalar.get("Faaliyet Raporlari", pd.DataFrame()))
        b=sayfalar.get("Backtest Ozet",pd.DataFrame())
        if b.empty: b=sayfalar.get("Backtest Islemler",pd.DataFrame())
        self.back.dataframe_yukle(b); self.graf.yenile(); self.raporlar.guncelle(rapor)

    def stil_uygula(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background: #020617;
            color: #e5e7eb;
            font-family: Arial;
            font-size: 13px;
        }

        #sidebar {
            background: #0f172a;
            border-right: 1px solid #1e293b;
        }

        #menuContent, #menuScroll, #sidebarBottom {
            background: transparent;
        }

        QScrollArea {
            border: none;
        }

        QScrollBar:vertical {
            background: #0f172a;
            width: 8px;
            margin: 0;
        }

        QScrollBar::handle:vertical {
            background: #334155;
            border-radius: 4px;
            min-height: 24px;
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0;
        }

        #brand {
            font-size: 18px;
            font-weight: bold;
            color: #f8fafc;
            background: #111827;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 6px;
        }

        #menuButton {
            text-align: left;
            padding: 8px 12px;
            border: none;
            border-radius: 7px;
            background: transparent;
            color: #cbd5e1;
            font-weight: bold;
        }

        #menuButton:hover {
            background: #1e293b;
            color: white;
        }

        #marketStatus {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 7px;
            color: #bfdbfe;
            font-size: 11px;
            font-weight: bold;
        }

        #startButton {
            padding: 10px;
            border-radius: 8px;
            background: #16a34a;
            color: white;
            font-weight: bold;
            font-size: 13px;
        }

        #startButton:hover {
            background: #15803d;
        }

        #updateButton, #refreshButton {
            background: #1e293b;
            font-weight: bold;
        }

        QPushButton {
            padding: 8px 12px;
            border: 1px solid #334155;
            border-radius: 7px;
            background: #1e293b;
            color: #f8fafc;
        }

        QPushButton:hover {
            background: #334155;
        }

        #pageTitle {
            font-size: 24px;
            font-weight: bold;
            color: #f8fafc;
        }

        #subText {
            color: #94a3b8;
        }

        #card {
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 10px;
            min-height: 100px;
        }

        #cardTitle {
            color: #94a3b8;
            font-weight: bold;
        }

        #cardValue {
            color: #60a5fa;
            font-size: 27px;
            font-weight: bold;
        }

        #infoBox {
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 8px;
            padding: 12px;
            color: #cbd5e1;
        }

        #imagePanel {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 8px;
        }

        QLineEdit, QComboBox {
            background: #111827;
            color: white;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 8px;
        }

        QTableWidget {
            background: #0b1120;
            alternate-background-color: #111827;
            gridline-color: #1f2937;
            border: 1px solid #334155;
            selection-background-color: #1d4ed8;
        }

        QHeaderView::section {
            background: #1e293b;
            color: #f8fafc;
            padding: 8px;
            border: 1px solid #334155;
            font-weight: bold;
        }

        QTextEdit {
            background: #020617;
            color: #d1d5db;
            border: 1px solid #334155;
            border-radius: 8px;
            font-family: Consolas;
            font-size: 12px;
        }

        #legalFooter {
            background: #7f1d1d;
            color: #fff;
            padding: 10px 16px;
            font-size: 11px;
            font-weight: bold;
            border-top: 1px solid #ef4444;
        }

        QCheckBox {
            padding: 8px;
            font-weight: bold;
            color: #f8fafc;
        }
        """)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    if not kabul_dosyasi().exists():
        dialog = YasalKabulDialog()
        if dialog.exec() != QDialog.Accepted:
            sys.exit(0)
        kabul_dosyasi().write_text(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " | sürüm " + LEGAL_VERSION,
            encoding="utf-8"
        )
    pencere = MainWindow()
    pencere.showMaximized()
    sys.exit(app.exec())
