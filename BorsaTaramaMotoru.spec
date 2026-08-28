# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scan_runner.py'],
    pathex=[],
    binaries=[],
    datas=[('models', 'models')],
    hiddenimports=['main', 'bist_evreni', 'sembol_esleme', 'yeni_halka_arz', 'tarama_seffafligi', 't1t2_tahmin_sistemi'],
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
    name='BorsaTaramaMotoru',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BorsaTaramaMotoru',
)
