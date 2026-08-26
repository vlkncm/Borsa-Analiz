# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('logo.png', '.'), ('logo.ico', '.'), ('assets', 'assets'), ('bist_hisseleri_613_aktif.txt', '.')],
    hiddenimports=['main', 'bist30', 'veri_saglayici', 'bist_bulteni', 'borsa_tarayici', 'gunluk_trade_gostergeleri', 'rsi_supertrend_stratejisi', 'pro_moduller', 'kap_modulu', 'backtest', 'mtf_grafik', 'olasilik_temettu', 'faaliyet_raporu', 'sirket_arastirmasi', 'fon_analizi', 'piyasa_guncelleme', 'sistem_kontrol', 'v4_puanlama', 'formasyon_motoru', 'takip_modulu', 'fibonacci_motoru', 'karar_motoru', 'satis_karar_motoru', 'vade_motoru', 'profesyonel_analiz', 'dashboard_ui', 'analiz_deposu', 'ertesi_gun_motoru', 'fiyat_limitleri', 'tahmin_deposu', 't1_etiketleri'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BorsaAnalizProMAX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BorsaAnalizProMAX',
)
