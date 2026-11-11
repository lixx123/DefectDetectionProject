"""Process Protocol V1 client: only schema results and typed artifacts cross."""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import os,sys,json,time,subprocess
from domain import InspectionResult
from domain.serialization import to_dict
from infrastructure.storage.package import artifact_references
from .manifest import EngineError,sha,inside
from .registry import EngineRegistry
from app.runtime_paths import native_path

def stamp():return datetime.now(timezone.utc).isoformat()

class DetectionEngineClient:
    def __init__(self,release_root,output_root,*,timeout_seconds=7200,cancellation_event=None):
        self.registry=EngineRegistry(release_root);self.output_root=Path(output_root);self.timeout_seconds=timeout_seconds;self.cancellation_event=cancellation_event;self.last_run_dir=None

    def inspect(self,image_path,config):
        engine=self.registry.resolve();image=Path(image_path).resolve()
        task=native_path(self.output_root/('ENGINE_'+uuid4().hex),force=True);task.mkdir(parents=True,exist_ok=False)
        run_id=task.name;request=dict(protocol_version='1.0',task_id=run_id,run_id=run_id,image_path=str(image),config_snapshot=to_dict(config),work_directory=str(task))
        request_path=task/'request.json';request_path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
        record=dict(run_id=run_id,task_id=run_id,parent_exe=sys.executable,engine_runner_path=str(engine.runner),engine_manifest_path=str(engine.root/'engine_manifest.json'),working_directory=str(engine.root),runtime_origin='RELEASE_ENGINE_PACKAGE',input_file_name=image.name,input_sha256=sha(image),config_hash=config.config_hash(),start_time=stamp(),**engine.identity)
        env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','VIRTUAL_ENV','QT_'))}
        env['PATH']=os.pathsep.join([str(engine.root),str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'),os.environ.get('SystemRoot','C:/Windows')])
        command=[str(engine.runner),'--request',str(request_path)]
        start=time.monotonic()
        with (task/'engine_execution.log').open('x',encoding='utf-8') as log:
            child=subprocess.Popen(command,cwd=engine.root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            record['pid']=child.pid
            try:
                while child.poll() is None:
                    if time.monotonic()-start>self.timeout_seconds:raise EngineError('ENGINE_TIMEOUT')
                    if self.cancellation_event and self.cancellation_event.is_set():raise EngineError('ENGINE_CANCELLED')
                    time.sleep(.1)
            except BaseException:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                else:child.kill()
                child.wait();raise
            finally:
                record.update(end_time=stamp(),exit_code=child.poll())
                (task/'process_receipt.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        if child.returncode:raise EngineError('ENGINE_PROCESS_FAILED; see engine_execution.log')
        engine.verify()
        try:
            receipt=json.loads((task/'engine_receipt.json').read_text(encoding='utf-8'))
            if receipt['status']!='PASS' or receipt['run_id']!=run_id or receipt['input_sha256']!=sha(image) or receipt['config_hash']!=config.config_hash() or receipt['engine']!=engine.identity:raise EngineError('ENGINE_RECEIPT_MISMATCH')
            result_file=inside(task,receipt['output_result']);directory=inside(task,receipt['artifact_root'])
            if result_file.parent!=directory or sha(result_file)!=receipt['result_sha256']:raise EngineError('ENGINE_RESULT_HASH_MISMATCH')
            result=InspectionResult.load_json(result_file);result.validate_final()
            if result.input_info.sha256!=receipt['input_sha256'] or result.algorithm_info.config_hash!=config.config_hash() or result.algorithm_info.extensions.get('engine')!=engine.identity:raise EngineError('ENGINE_RESULT_IDENTITY_MISMATCH')
            for name,h in artifact_references(result).items():
                if sha(inside(directory,name))!=h:raise EngineError('ENGINE_ARTIFACT_HASH_MISMATCH')
            record.update(output_result=receipt["output_result"],result_id=result.result_id,algorithm_executions=receipt["algorithm_executions"])
            (task/"process_receipt.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
            self.last_run_dir=directory
            return result
        except (KeyError,ValueError,OSError) as e:raise EngineError('ENGINE_RECEIPT_INVALID') from e
