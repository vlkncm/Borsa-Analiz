# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app_qt.py'],
    pathex=[],
    binaries=[],
    datas=[('logo.png', '.'), ('logo.ico', '.'), ('assets', 'assets'), ('models', 'models'), ('bist_hisseleri_613_aktif.txt', '.')],
    hiddenimports=['main', 'bist30', 'sembol_esleme', 'veri_saglayici', 'borsa_tarayici', 'gunluk_trade_gostergeleri', 'dashboard_ui', 'analiz_deposu', 'ertesi_gun_motoru', 'vade_motoru', 'tahmin_deposu', 't1t2_tahmin_sistemi'],
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
