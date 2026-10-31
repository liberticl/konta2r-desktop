# -*- mode: python ; coding: utf-8 -*-
block_cipher = None
a = Analysis(
    ['../../konta2r/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('../../models/*.onnx', 'models')],
    hiddenimports=['onnxruntime', 'cv2', 'PIL', 'customtkinter', 'numpy', 'requests'],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='konta2r',
          debug=False, console=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='konta2r')
