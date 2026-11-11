"""Recompute packaged-engine semantic evidence; never trust PASS flags alone."""
from pathlib import Path
import json
from copy import deepcopy
from domain import InspectionResult
from infrastructure.engines import EngineManifest
from infrastructure.engines.manifest import sha
from infrastructure.repositories import JsonResultRepository
from app.runtime_paths import logical_path
from ui.models.review_admission import ReviewAdmissionEngine,load_policy
from ui.models.human_review.model import canonical
from regression.comparator import semantic_snapshot,compare_snapshots,plain
from regression.golden import load_manifest

def task_signature(result):
    tasks=ReviewAdmissionEngine().evaluate(result,load_policy()).tasks
    return sorted([plain(t) for t in tasks],key=lambda t:t['task_key'])

def verified_config_metadata(expected,actual,actual_hash):
    """Only the historical connection-status label may differ; no tuning drift."""
    from domain.configuration import InspectionConfig
    from domain.serialization import from_dict
    expected=deepcopy(expected);actual=deepcopy(actual)
    before=from_dict(InspectionConfig,expected).config_hash()
    if from_dict(InspectionConfig,actual).config_hash()!=actual_hash:raise ValueError('Actual config hash not verified')
    old=expected.pop('status');new=actual.pop('status')
    if expected!=actual:raise ValueError('Production configuration changed')
    if old!=new and (old,new)!=('MODEL_ONLY_NOT_CONNECTED_TO_ENGINE','REFERENCE_ENGINE_CONNECTED'):
        raise ValueError('Unexpected configuration status transition')
    return before,old!=new

def accept_evidence(root,path,head):
    root=Path(root).resolve();path=Path(path)
    data=json.loads(path.read_text(encoding='utf-8'))
    if data['tested_head']!=head:raise ValueError('Packaged evidence HEAD mismatch')
    release=Path(data['release_dir']).resolve();engine=EngineManifest.load(data['engine_dir'])
    if not logical_path(engine.root).is_relative_to(release/'engines'):raise ValueError('Engine outside release')
    if sha(release/'DefectInspectionSoftware.exe')!=data['gui_exe_sha256']:raise ValueError('GUI artifact changed')
    frozen=load_manifest(root);reference=JsonResultRepository(root/'output/phase4_validation/repository')
    old_ids={'26_1':'8a363da8-7a3b-4c77-84cf-d13a375c3b15','26_2':'f15a42a0-c022-47eb-93d8-d0d191939589'}
    outputs=[];executions=0
    if {s['sample'] for s in data['samples']}!={'26_1','26_2'} or len(data['samples'])!=2:raise ValueError('Both independent real frames required')
    for sample in data['samples']:
        directory=Path(sample['result_dir']);result=InspectionResult.load_json(directory/'result.json');result.validate_final()
        task=Path(sample['runtime_dir']);receipt=json.loads((task/'engine_receipt.json').read_text(encoding='utf-8'));process=json.loads((task/'process_receipt.json').read_text(encoding='utf-8'))
        if process['exit_code']!=0 or not process['pid'] or receipt['status']!='PASS':raise ValueError('Actual engine process not successful')
        if logical_path(Path(process['engine_runner_path'])).resolve()!=logical_path(engine.runner).resolve():raise ValueError('Wrong engine runner')
        if logical_path(Path(process['parent_exe'])).resolve()!=(release/'DefectInspectionSoftware.exe').resolve():raise ValueError('Detection was not launched by release GUI')
        if process['runtime_origin']!='RELEASE_ENGINE_PACKAGE' or receipt['engine']!=engine.identity or result.algorithm_info.extensions.get('engine')!=engine.identity:raise ValueError('Engine identity mismatch')
        if result.result_id==old_ids[sample['sample']] or result.result_id!=receipt['result_id'] or result.extensions['engine_execution']['run_id']!=receipt['run_id']:raise ValueError('Old/replayed result identity')
        for process_info in receipt['attempt_processes']:
            if process_info['exit_code']!=0:raise ValueError('Failed attempt not accepted as success evidence')
        markers=list(task.glob('algorithm_started_*.json'))
        if len(markers)!=receipt['algorithm_executions'] or not markers:raise ValueError('No actual frozen pipeline execution marker')
        executions+=receipt['algorithm_executions']
        access=[receipt['runtime_access'],*[json.loads(p.read_text(encoding='utf-8')) for p in task.glob('attempt_*_access.json')]]
        if any(any(a['counters'][k] for k in ['development_project_accesses','development_venv_accesses','system_python_accesses','blocked_external_opens']) for a in access):raise ValueError('Forbidden release access')
        frame=next(s for s in frozen['samples'] if s['sample_id']==sample['sample'])
        current=semantic_snapshot(result,directory)
        # New, verified Engine provenance is expected metadata; keep every other
        # semantic field and the frozen Golden set unchanged.
        for key in ['engine','engine_execution']:current['algorithm']['extensions'].pop(key,None)
        current['extensions'].pop('engine_execution',None)
        request=json.loads((task/'request.json').read_text(encoding='utf-8'))
        expected_hash,status_metadata=verified_config_metadata(frame['expected_auto']['config_snapshot'],request['config_snapshot'],result.algorithm_info.config_hash)
        if process['config_hash']!=result.algorithm_info.config_hash or receipt['config_hash']!=result.algorithm_info.config_hash:raise ValueError('Receipt config mismatch')
        if expected_hash!=frame['expected_auto']['snapshot']['algorithm']['config_hash']:raise ValueError('Frozen config hash mismatch')
        current['algorithm']['config_hash']=expected_hash
        comparison=compare_snapshots(frame['expected_auto']['snapshot'],current)
        if comparison.status not in ['PASS','PASS_WITH_WARNINGS']:
            raise ValueError('Semantic comparison failed: '+json.dumps(comparison.to_dict(),ensure_ascii=False))
        old=reference.load(old_ids[sample['sample']])
        before=task_signature(old);after=task_signature(result)
        if before!=after:raise ValueError('ReviewTask membership/priority/reason/source changed')
        expected={'26_1':(36,83),'26_2':(35,49)}[sample['sample']]
        if (len(result.defects),len(after))!=expected:raise ValueError('Frozen acceptance counts changed')
        outputs.append(dict(sample=sample['sample'],semantic_regression='PASS',comparison=comparison.to_dict(),review_task_set_equal=True,config_connection_status_metadata_normalized=status_metadata,defects=len(result.defects),tasks=len(after),result_id=result.result_id,run_id=receipt['run_id']))
    return dict(status='PASS',real_engine_executed=True,algorithm_executions=executions,cases=outputs,tested_head=head,engine=engine.identity,simulation=False)
