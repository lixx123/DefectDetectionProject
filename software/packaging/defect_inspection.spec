# Explicit onedir application. Stock hooks collect Qt/numpy/OpenCV binaries.
from pathlib import Path
root = Path(SPECPATH).parent
datas = [(str(root / 'configs/production_v1.yaml'), 'configs'),
         (str(root / 'ui/models/review_admission/review_admission_v1.yaml'), 'ui/models/review_admission')]
a = Analysis([str(root / 'packaging/launch.py')], pathex=[str(root), str(root / 'packaging')],
             binaries=[], datas=datas, hiddenimports=['cv2', 'numpy', 'yaml', 'release_qa', 'release_engine_qa', 'tools.install_engine'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['pytest', 'tests', 'regression', 'torch', 'tensorflow', 'IPython', 'jupyter',
                       'matplotlib', 'pandas', 'scipy', 'skimage', 'tkinter',
                       'PyQt5', 'PyQt6', 'PySide2'], noarchive=False, optimize=0)
# Qt6 uses Windows' system ICU. A PATH-provided Poppler icuuc has different
# exports and breaks QtCore in a clean process. Do not redistribute OS ICU.
a.binaries = [item for item in a.binaries if Path(item[0]).name.lower() not in {'icuuc.dll', 'icu.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DefectInspectionSoftware',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DefectInspectionSoftware')
