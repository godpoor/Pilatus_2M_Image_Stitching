# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['numpy', 'scipy.ndimage', 'fabio', 'fabio.tifimage']
hiddenimports += collect_submodules('fabio')


a = Analysis(
    ['mian.py'],
    pathex=[],
    binaries=[],
    datas=[('d:\\Codes\\Pilatus_2M_Image_Stitching\\img\\owl.ico', 'img')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PyQt5', 'tkinter', 'PIL.ImageQt'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pilatus 2M 图像拼接工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['d:\\Codes\\Pilatus_2M_Image_Stitching\\img\\owl.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Pilatus 2M 图像拼接工具',
)
