"""Publish static resources and checksums; zip hash lives beside the zip."""
import argparse, hashlib, shutil, zipfile,sys
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--release',type=Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--engine-package',required=True,type=Path);a=p.parse_args()
    sys.path.insert(0,str(a.project))
    r=a.release
    shutil.copy2(a.project/'README_RELEASE.md',r/'README_RELEASE.md')
    shutil.copy2(a.project/'packaging/defect_inspection.spec',r/'defect_inspection.spec')
    shutil.copytree(a.project/'configs',r/'configs',ignore=shutil.ignore_patterns('__pycache__','*.py'))
    (r/'resources').mkdir();(r/'resources/README.txt').write_text('Qt plugins and admission policy are bundled under _internal.\n',encoding='utf-8')
    for folder in ['results','runtime','reviews']:(r/'output'/folder).mkdir(parents=True)
    (r/'VERSION.txt').write_text('DefectInspectionSoftware\nRelease: Phase12_Engine\nBaseline: e5018ba787b839c9648ff36cf50db6f0ab6cd07c\nBuild commit: '+a.commit+'\nSchema: 1.0\n',encoding='utf-8')
    from infrastructure.engines import EngineRegistry
    from app.runtime_paths import native_path
    engine=EngineRegistry(r).install(a.engine_package)
    shutil.copytree(a.project/'tools',r/'tools',ignore=shutil.ignore_patterns('*.py','__pycache__'))
    with (r/'VERSION.txt').open('a',encoding='utf-8') as f:f.write('Engine: '+engine.data['engine_id']+' '+engine.data['engine_version']+'\nEngine protocol: 1.0\n')
    files=sorted(f for f in native_path(r,force=True).rglob('*') if f.is_file())
    r=native_path(r,force=True)
    (r/'checksums.sha256').write_text(''.join(sha(f)+'  '+f.relative_to(r).as_posix()+'\n' for f in files),encoding='utf-8')
    zpath=r.parent/'DefectInspectionSoftware_Phase12_Engine.zip'
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(r.rglob('*')):z.write(f,f.relative_to(r.parent).as_posix())
    (r.parent/'checksums.sha256').write_text(sha(zpath)+'  '+zpath.name+'\n'+sha(r/'checksums.sha256')+'  '+r.name+'/checksums.sha256\n',encoding='utf-8')

if __name__=='__main__':main()
