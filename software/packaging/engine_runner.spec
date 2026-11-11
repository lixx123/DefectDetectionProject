from pathlib import Path
import os,json
root=Path(SPECPATH).parent
payload=Path(os.environ['ENGINE_PAYLOAD']).resolve()
a=Analysis([str(root/'packaging/engine_runner.py')],pathex=[str(root)],
  datas=[(str(payload/'algorithm'),'algorithm'),(str(root/'core/runtime/engine_worker.py'),'bridge')],binaries=[],
  hiddenimports=json.loads((root/'packaging/engine_hidden_imports.json').read_text(encoding='utf-8'))['hiddenimports']+['yaml'],
  hookspath=[],runtime_hooks=[],hooksconfig={'matplotlib':{'backends':['Agg']}},
  excludes=['pytest','tests','torch','tensorflow','jupyter','IPython','tkinter','PySide6','PyQt5','PyQt6','PySide2'],noarchive=False)
a.binaries=[r for r in a.binaries if Path(r[0]).name.lower() not in {'icuuc.dll','icu.dll'}]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='engine_runner',console=True,debug=False,strip=False,upx=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='engine_runner')
