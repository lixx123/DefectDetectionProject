from pathlib import Path
import os,sys,subprocess,json,hashlib,shutil
R=Path(os.environ['ENGINE_PROJECT']);label=sys.argv[1];out=R/'output'/label;out.mkdir(exist_ok=False)
env=dict(os.environ,ENGINE_PAYLOAD=os.environ.get('ENGINE_PAYLOAD_OUT',str(R/'output/engine_payload_v1')),PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
python=Path(os.environ.get('ENGINE_BUILD_PYTHON',str(R/'output/engine_build_env/Scripts/python.exe')))
sys.path.insert(0,str(R));from app.runtime_paths import native_path
with (out/'build.log').open('w',encoding='utf-8') as f:
 p=subprocess.run([str(python),'-m','PyInstaller','--noconfirm','--workpath',str(native_path(out/'build',force=True)),'--distpath',str(native_path(out/'dist',force=True)),str(R/'packaging/engine_runner.spec')],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT)
if p.returncode:
 print((out/'build.log').read_text(encoding='utf-8')[-6000:]);raise SystemExit(p.returncode)
package=native_path(out/'dist/engine_runner',force=True)
shutil.copy2(Path(env['ENGINE_PAYLOAD'])/'payload_manifest.json',package/'algorithm_source_manifest.json')
sys.path.insert(0,str(R));from infrastructure.engines.manifest import sha,canonical,PROFILE,EngineManifest
files={p.relative_to(package).as_posix():sha(p) for p in sorted(package.rglob('*')) if p.is_file()}
payload=json.loads((Path(env['ENGINE_PAYLOAD'])/'payload_manifest.json').read_text(encoding='utf-8'))
manifest=dict(engine_id='reference',engine_version='1.0.0',protocol_version='1.0',output_schema_version='1.0',runner='engine_runner.exe',runner_sha256=files['engine_runner.exe'],algorithm_source_sha256=payload['algorithm_source_sha256'],engine_bundle_sha256=hashlib.sha256(canonical(files)).hexdigest(),config_version='0.2.0',supported_input=PROFILE,files=files)
(package/'engine_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
EngineManifest.load(package)
print(json.dumps(dict(status='PASS',package=str(package),files=len(files),runner_sha256=files['engine_runner.exe'],bundle_sha256=manifest['engine_bundle_sha256'])),flush=True)
probe=out/'probe/probe.json';probe.parent.mkdir()
with (out/'probe.log').open('w',encoding='utf-8') as f:p=subprocess.run([str(package/'engine_runner.exe'),'--probe',str(probe)],cwd=out,env=dict(env,PATH=os.environ['SystemRoot']+'/System32;'+os.environ['SystemRoot']),stdout=f,stderr=subprocess.STDOUT,timeout=180)
assert p.returncode==0,(out/'probe.log').read_text(encoding='utf-8',errors='replace')
print('ENGINE IMPORT PROBE PASS',flush=True)
