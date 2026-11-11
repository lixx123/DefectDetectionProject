"""Phase13 static engineering candidate; no final tag is claimed."""
import argparse,sys,shutil,zipfile
from pathlib import Path
from datetime import datetime,timezone

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--release',type=Path,required=True);parser.add_argument('--commit',required=True);parser.add_argument('--engine-package',type=Path,required=True)
    args=parser.parse_args();sys.path.insert(0,str(args.project))
    from infrastructure.engines import EngineRegistry
    from infrastructure.engines.manifest import sha
    from app.runtime_paths import native_path
    root=native_path(args.release,force=True)
    shutil.copy2(args.project/'README_RELEASE.md',root/'README_RELEASE.md')
    shutil.copytree(args.project/'configs',root/'configs',ignore=shutil.ignore_patterns('__pycache__','*.py'))
    (root/'resources').mkdir();(root/'resources/README.txt').write_text('Frozen Qt and review policy resources are in _internal.\n',encoding='utf-8')
    shutil.copytree(args.project/'tools',root/'tools',ignore=shutil.ignore_patterns('*.py','__pycache__'))
    for name in ['results','runtime','reviews']:(root/'output'/name).mkdir(parents=True)
    engine=EngineRegistry(root).install(args.engine_package)
    text='DefectInspectionSoftware V1.0.0\nGUI Version: 1.0.0\nEngine: reference 1.0.0\nEngine Protocol: 1.0\nInspectionResult Schema: 1.0\nSource Commit: '+args.commit+'\nGit Tag: NOT_CREATED (mandatory acceptance pending)\nBuild Date: '+datetime.now(timezone.utc).astimezone().isoformat()+'\nRelease Status: ENGINEERING_RELEASE_UNSIGNED\nPhase13 Acceptance: CONDITIONAL / SECOND_PC_NOT_AVAILABLE / STRICT_BLIND_NOT_AVAILABLE\nEngine bundle SHA256: '+engine.data['engine_bundle_sha256']+'\nAlgorithm source SHA256: '+engine.data['algorithm_source_sha256']+'\n'
    (root/'VERSION.txt').write_text(text,encoding='utf-8')
    files=sorted(p for p in root.rglob('*') if p.is_file())
    (root/'checksums.sha256').write_text(''.join(sha(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in files),encoding='utf-8')
    archive=root.parent/'DefectInspectionSoftware_V1.0.0.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):z.write(p,p.relative_to(root.parent).as_posix())
    (root.parent/'checksums.sha256').write_text(sha(archive)+'  '+archive.name+'\n'+sha(root/'checksums.sha256')+'  '+root.name+'/checksums.sha256\n',encoding='utf-8')
    print('V1 engineering candidate packaged; final tag NOT_CREATED',flush=True)

if __name__=='__main__':main()
