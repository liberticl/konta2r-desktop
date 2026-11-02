# -*- mode: python ; coding: utf-8 -*-
"""Onedir + GUI (console=False) para Ubuntu y Windows.

Se invoca desde la raíz del repo:  pyinstaller build/konta2r.spec
El .deb de Ubuntu lo arma build/deb-build.sh.
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

_HERE = os.path.abspath(SPECPATH)          # build/
_ROOT = os.path.dirname(_HERE)             # raíz del repo
# .ico en Windows, .png en el resto (PyInstaller no convierte solo).
_ICON = os.path.join(
    _HERE, 'deb-icon',
    'konta2r.ico' if sys.platform == 'win32' else 'konta2r.png')

ct_datas, ct_binaries, ct_hidden = collect_all('customtkinter')

a = Analysis(
    [os.path.join(_ROOT, 'konta2r', '__main__.py')],
    pathex=[_ROOT],
    binaries=ct_binaries,
    datas=[(os.path.join(_ROOT, 'models', '*.onnx'), 'models')] + ct_datas,
    hiddenimports=['onnxruntime', 'cv2', 'PIL', 'PIL._tkinter_finder', 'PIL._imagingtk',
                   'customtkinter', 'numpy', 'requests'] + ct_hidden,
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='konta2r',
          debug=False, console=False,
          icon=_ICON if os.path.exists(_ICON) else None)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='konta2r')
