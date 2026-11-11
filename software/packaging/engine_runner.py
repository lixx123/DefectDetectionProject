"""Standalone Engine Protocol V1 host, plus isolated frozen reference attempts."""
import os,sys,json,time,traceback,subprocess,hashlib,runpy
from pathlib import Path
sys.dont_write_bytecode=True
for stream in [sys.stdout,sys.stderr]:
    if stream is not None:stream.reconfigure(encoding="utf-8")


def dump(p,value):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def algorithm_root():
    from app.runtime_paths import native_path
    return native_path(Path(sys._MEIPASS)/'algorithm',force=True)


def setup_algorithm(raw_path,work):
    """Resource relocation only. Source bytes and numeric configuration untouched."""
    root=algorithm_root();sys.path.insert(0,str(root))
    import config.user_config as cfg
    cfg.DATA_ROOT=Path(raw_path).parent
    cfg.LOG_ROOT=Path(work)/'logs'
    import pandas as pd
    original=pd.read_csv
    def relocate(value):
        if isinstance(value,str) and len(value)>3 and value[1]==':':
            n=value.replace('\\','/')
            if '/outputs/' in n:return str(root/'outputs'/n.split('/outputs/',1)[1])
        return value
    def read(*args,**kwargs):
        frame=original(*args,**kwargs)
        for column in frame.select_dtypes(include=['object','str']).columns:
            frame[column]=frame[column].map(relocate)
        return frame
    pd.read_csv=read
    # Pin the reference namespace, never the software scripts package.
    import types,importlib.machinery
    package=types.ModuleType('scripts');package.__package__='scripts';package.__path__=[str(root/'scripts')]
    package.__spec__=importlib.machinery.ModuleSpec('scripts',loader=None,is_package=True)
    sys.modules['scripts']=package
    return root


def audit_access(work,raw):
    """Fail closed for Python file opens outside release, task and approved RAWs."""
    from ctypes.util import dllist
    from app.runtime_paths import logical_path
    root=logical_path(Path(sys.executable).resolve().parent)
    windows=Path(os.environ['SystemRoot']).resolve()
    approved={Path(raw).resolve(),Path(raw).parent/'26 (1).raw',Path(raw).parent/'26 (2).raw'}
    counters=dict(development_project_accesses=0,development_venv_accesses=0,system_python_accesses=0,blocked_external_opens=0,approved_raw_opens=0)
    accesses=[]
    def hook(event,args):
        if event!='open' or not args or not isinstance(args[0],(str,bytes)):return
        p=logical_path(Path(os.fsdecode(args[0])).absolute())
        lower=str(p).casefold()
        if p in approved:
            counters['approved_raw_opens']+=1;return
        allowed=p.is_relative_to(root) or p.is_relative_to(logical_path(Path(work).resolve())) or p.is_relative_to(windows)
        if not allowed:
            counters['blocked_external_opens']+=1
            if '.venv' in lower:counters['development_venv_accesses']+=1
            if 'defectdetectionproject' in lower or 'defectinspectionsoftware' in lower:counters['development_project_accesses']+=1
            if 'python' in lower:counters['system_python_accesses']+=1
            accesses.append(str(p));raise PermissionError('ENGINE_EXTERNAL_ACCESS_FORBIDDEN')
    sys.addaudithook(hook)
    def finish():
        modules=dllist()
        external=[p for p in modules if not logical_path(Path(p)).is_relative_to(root) and not logical_path(Path(p)).is_relative_to(windows)]
        from infrastructure.engines.runtime_audit import verify_security_module
        security=[verify_security_module(p) for p in external]
        if any(s is None for s in security):raise RuntimeError('ENGINE_EXTERNAL_NATIVE_MODULES: '+str(external))
        return dict(counters=counters,blocked_paths=accesses,native_modules=modules,os_security_modules=security,audit_scope='Python open events plus actual native module paths; not an OS-wide file-system trace')
    return finish


def main_request(request_path):
    from infrastructure.engines.manifest import EngineManifest,sha,inside
    from domain.serialization import from_dict
    from domain.configuration import InspectionConfig
    from core.detector import Detector
    from core.adapters.reference_engine_adapter import ReferenceEngineAdapter
    from core.runtime.execution_runner import timestamp
    request_path=Path(request_path).resolve();request=json.loads(request_path.read_text(encoding='utf-8'))
    work=request_path.parent
    if request['protocol_version']!='1.0' or Path(request['work_directory']).resolve()!=work:raise ValueError('ENGINE_REQUEST_INVALID')
    package=EngineManifest.load(Path(sys.executable).parent);raw=Path(request['image_path']).resolve()
    os.environ['MPLCONFIGDIR']=str(work/'mpl_cache');os.environ['MPLBACKEND']='Agg'
    finish=audit_access(work,raw)
    receipt=dict(status='FAIL',protocol_version='1.0',run_id=request['run_id'],task_id=request['task_id'],engine=package.identity,start_time=timestamp(),algorithm_executions=0,attempt_processes=[])
    class Adapter(ReferenceEngineAdapter):
        def __init__(self):super().__init__(reference_root=algorithm_root(),python_executable=sys.executable)
        def run(self,image_path,mode,run_dir,logger):
            output=run_dir/'engine'/mode.value;output.parent.mkdir(parents=True,exist_ok=True)
            spec=work/('attempt_'+mode.value+'.json')
            dump(spec,dict(input=str(image_path),output=str(output),mode=mode.value,work=str(work)))
            with (run_dir/'logs'/(mode.value+'_engine.log')).open('x',encoding='utf-8') as log:
                child=subprocess.Popen([sys.executable,'--reference-attempt',str(spec)],cwd=Path(sys.executable).parent,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                receipt['attempt_processes'].append(dict(pid=child.pid,runner=sys.executable,mode=mode.value))
                dump(work/'engine_receipt.json',receipt);code=child.wait()
            if (work/('algorithm_started_'+mode.value+'.json')).exists():receipt['algorithm_executions']+=1
            receipt['attempt_processes'][-1]['exit_code']=code
            error=json.loads((output/'bridge_error.json').read_text(encoding='utf-8')) if (output/'bridge_error.json').exists() else ({'reason':'UNKNOWN_EXCEPTION','stage':'PROCESS','error':'engine child failed'} if code else None)
            return output,error
    try:
        cfg=from_dict(InspectionConfig,request['config_snapshot'])
        if cfg.pipeline_mode.value not in ['auto','full','roi-bh','roi-j4']:raise ValueError('No replay modes in packaged engine')
        adapter=Adapter()
        if adapter.source_manifest()[0]!=package.data['algorithm_source_sha256']:raise RuntimeError('ENGINE_ALGORITHM_SOURCE_MISMATCH')
        detector=Detector(output_root=work/'inspection',engine_adapter=adapter)
        result=detector.inspect(raw,cfg);result.validate_final()
        result.algorithm_info.extensions['engine']=package.identity
        result.algorithm_info.extensions['engine_execution']=dict(run_id=request['run_id'],task_id=request['task_id'],protocol_version='1.0')
        result.extensions['engine_execution']=dict(run_id=request['run_id'],engine_id=package.data['engine_id'],engine_version=package.data['engine_version'])
        dest=detector.last_run_dir/'result.json';result.save_json(dest)
        receipt.update(status='PASS',input_sha256=sha(raw),config_hash=cfg.config_hash(),output_result=dest.relative_to(work).as_posix(),artifact_root=dest.parent.relative_to(work).as_posix(),result_id=result.result_id,result_sha256=sha(dest))
    except Exception:
        receipt['traceback']=traceback.format_exc();print(receipt['traceback'],file=sys.stderr,flush=True)
    finally:
        receipt['end_time']=timestamp();receipt['runtime_access']=finish();dump(work/'engine_receipt.json',receipt)
    return 0 if receipt['status']=='PASS' else 2


def attempt(spec_path):
    spec=json.loads(Path(spec_path).read_text(encoding='utf-8'));work=Path(spec['work'])
    os.environ['MPLCONFIGDIR']=str(work/'mpl_cache');os.environ['MPLBACKEND']='Agg'
    finish=audit_access(work,spec['input'])
    try:
        root=setup_algorithm(spec['input'],work)
        from scripts import run_two_level_unified as engine
        original_run=engine.run_raw
        def measured_run(*args,**kwargs):
            dump(work/('algorithm_started_'+spec['mode']+'.json'),dict(pid=os.getpid(),mode=spec['mode'],started=time.time(),entry='frozen run_two_level_unified.run_raw'))
            return original_run(*args,**kwargs)
        engine.run_raw=measured_run
        sys.argv=['engine_worker.py','--reference-root',str(root),'--input',spec['input'],'--output',spec['output'],'--mode',spec['mode']]
        runpy.run_path(str(Path(sys._MEIPASS)/'bridge/engine_worker.py'),run_name='__main__')
    finally:dump(work/('attempt_'+spec['mode']+'_access.json'),finish())


def probe(dest):
    work=Path(dest).parent;os.environ['MPLCONFIGDIR']=str(work/'mpl_cache');os.environ['MPLBACKEND']='Agg'
    root=setup_algorithm(root_path:=algorithm_root()/'references/missing.raw',work)
    from scripts import run_two_level_unified
    dump(dest,dict(status='PASS',root=str(root),runtime=sys.executable))
    return 0


if __name__=='__main__':
    try:
        if sys.argv[1]=='--request':raise SystemExit(main_request(sys.argv[2]))
        if sys.argv[1]=='--reference-attempt':attempt(sys.argv[2])
        elif sys.argv[1]=='--probe':raise SystemExit(probe(sys.argv[2]))
        else:raise ValueError('Unknown engine command')
    except Exception:
        traceback.print_exc();raise SystemExit(2)
