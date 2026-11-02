# -*- mode: python ; coding: utf-8 -*-
"""Paquete Ubuntu: onedir + GUI (console=False). El .deb lo arma build/deb-build.sh.

Se invoca desde la raíz del repo:  pyinstaller build/konta2r.spec
"""
import os

from PyInstaller.utils.hooks import collect_all

_HERE = os.path.abspath(SPECPATH)          # build/
_ROOT = os.path.dirname(_HERE)             # raíz del repo

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
          icon=os.path.join(_HERE, 'deb-icon', 'konta2r.png'))
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='konta2r')
