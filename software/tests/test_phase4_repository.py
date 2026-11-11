from pathlib import Path
from copy import deepcopy
from uuid import uuid4
import json, os, shutil, subprocess, zipfile
from concurrent.futures import ThreadPoolExecutor
import pytest

from test_phase3_adapter import detector
from domain import InspectionResult, FinalValidationError
from domain.configuration import InspectionConfig
from domain.enums import ExecutionStatus, QAStatus
from infrastructure.repositories import JsonResultRepository, ResultRepository
from infrastructure.repositories.errors import (ResultAlreadyExistsError, PackageIntegrityError,
    UnsafeArtifactPathError, ConfigSnapshotError, ResultNotFoundError, RepositoryError)
from infrastructure.storage.paths import relative_path, result_key
from infrastructure.storage.package import sha256
from application.inspection_service import InspectionService


@pytest.fixture
def case(tmp_path):
    raw=tmp_path/'26 (1).raw'
    import numpy as np
    raw.write_bytes(np.arange(144,dtype='>u2').tobytes())
    d,_=detector(tmp_path)
    config=InspectionConfig(); result=d.inspect(raw,config)
    return d,raw,config,result,JsonResultRepository(tmp_path/'repository')


def save(case,**kwargs):
    d,raw,config,result,repo=case
    return repo.save(result,d.last_run_dir,**kwargs)


def test_repository_contract_and_complete_roundtrip(case):
    d,_,_,result,repo=case
    assert isinstance(repo,ResultRepository)
    record=save(case)
    restored=repo.load(result.result_id); restored.validate_final()
    assert restored==result
    assert repo.load(result.result_id,verify='light')==result
    assert record.index_status=='PASS'
    assert repo.verify(result.result_id).status=='PASS'
    assert repo.list_results()==[record.summary]


@pytest.mark.parametrize('field,value',[('status',ExecutionStatus.FAILED),('qa_status',QAStatus.FAIL)])
def test_failed_draft_rejected(case,field,value):
    _,_,_,result,repo=case
    setattr(result.execution_info,field,value)
    with pytest.raises(FinalValidationError): save(case)
    assert not (repo.root/result.result_id).exists()


def test_duplicate_result_never_overwrites(case):
    *_,result,repo=case
    save(case); before=sha256(repo.root/result.result_id/'result.json')
    with pytest.raises(ResultAlreadyExistsError): save(case)
    assert sha256(repo.root/result.result_id/'result.json')==before


def test_atomic_stage_verified_before_publication(case,monkeypatch):
    import infrastructure.repositories.json_repository as module
    _,_,_,result,repo=case
    rename=module.os.rename; seen=[]
    def checked(source,target):
        assert source.name.startswith('.tmp_')
        assert not target.exists()
        assert repo.verifier.verify(source,expected_result_id=result.result_id).status=='PASS'
        seen.append(True); rename(source,target)
    monkeypatch.setattr(module.os,'rename',checked)
    save(case); assert seen==[True]
    assert not list(repo.root.glob('.tmp_*'))


def test_partial_copy_failure_leaves_no_formal_package(case,monkeypatch):
    import infrastructure.repositories.json_repository as module
    _,_,_,result,repo=case
    original=module.copy_checked; calls=[]
    def fail(*args,**kwargs):
        if calls: raise OSError('injected mid-copy failure')
        calls.append(True); return original(*args,**kwargs)
    monkeypatch.setattr(module,'copy_checked',fail)
    with pytest.raises(RepositoryError): save(case)
    assert not (repo.root/result.result_id).exists()
    assert not list(repo.root.glob('.tmp_*')) and not list(repo.root.glob('.save_*'))


def test_all_references_deduplicated_and_only_needed_files(case):
    from infrastructure.storage.package import artifact_references
    d,_,_,result,repo=case
    refs=artifact_references(result)
    (d.last_run_dir/'engine').mkdir(); (d.last_run_dir/'engine/fused_blackhat.npy').write_bytes(b'unrelated')
    (d.last_run_dir/'unrelated.raw').write_bytes(b'unrelated')
    record=save(case); directory=Path(record.result_dir)
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['artifact_count']==len(refs)
    assert len([e for e in manifest['package_files'] if e['role']=='artifact'])==len(refs)
    for relative,digest in refs.items(): assert sha256(directory/relative)==digest
    assert not (directory/'engine').exists() and not (directory/'unrelated.raw').exists()


@pytest.mark.parametrize('value',['../x','a/../x','/x','C:/x','C:\\x','//host/share/x','a\\..\\x','a:b','a//b','a/./b','NUL.txt','a/COM1','a.','a ',''])
def test_unsafe_artifact_paths(value):
    with pytest.raises(UnsafeArtifactPathError): relative_path(value)


@pytest.mark.parametrize('value',['../x','C:x','CON','a/b','.tmp_bad',''])
def test_unsafe_result_ids(value):
    with pytest.raises(UnsafeArtifactPathError): result_key(value)


@pytest.mark.parametrize('mode',['missing','hash','directory','extension_traversal','no_hash'])
def test_bad_artifact_blocks_save(case,mode):
    d,_,_,result,repo=case
    ref=result.defects[0].geometry.mask_reference; path=d.last_run_dir/ref.path
    if mode=='missing': path.unlink()
    elif mode=='hash': path.write_bytes(b'corrupted')
    elif mode=='directory': path.unlink(); path.mkdir()
    elif mode=='extension_traversal': result.extensions['extra']={'path':'../escaped','sha256':'0'*64}
    else: result.extensions['extra']={'path':'artifacts/unknown','sha256':None}
    with pytest.raises((RepositoryError,FileNotFoundError)): save(case)
    assert not (repo.root/result.result_id).exists()


def test_junction_or_symlink_escape_rejected(case,tmp_path):
    d,_,_,result,repo=case
    outside=tmp_path/'outside'; outside.mkdir(); (outside/'payload').write_bytes(b'known')
    link=d.last_run_dir/'escape'
    if os.name=='nt':
        process=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        assert process.returncode==0,process.stderr
    else: link.symlink_to(outside,target_is_directory=True)
    result.extensions['escape']={'path':'escape/payload','sha256':sha256(outside/'payload')}
    with pytest.raises(UnsafeArtifactPathError): save(case)


def test_manifest_metadata_and_no_self_hash_or_absolute_path(case):
    _,_,_,result,repo=case; record=save(case)
    manifest=json.loads((Path(record.result_dir)/'manifest.json').read_text(encoding='utf-8'))
    required={'schema_version','result_id','task_id','saved_at','software_version','algorithm_version',
        'config_name','config_version','config_hash','source_file_name','source_sha256','final_mode',
        'fallback_used','defect_count','total_area_px','artifact_count','artifact_total_bytes','package_files'}
    assert required<=manifest.keys() and manifest['schema_version']=='1.0'
    for entry in manifest['package_files']:
        assert not Path(entry['relative_path']).is_absolute()
        assert ':' not in entry['relative_path']
        assert entry['relative_path']!='manifest.json'
        path=Path(record.result_dir)/entry['relative_path']
        assert path.stat().st_size==entry['bytes'] and sha256(path)==entry['sha256']


@pytest.mark.parametrize('damage',['missing','hash','result_id','unexpected','manifest','result_json','config'])
def test_verify_exposes_structured_corruption(case,damage):
    _,_,_,result,repo=case; record=save(case); directory=Path(record.result_dir)
    path=directory/result.defects[0].geometry.mask_reference.path
    if damage=='missing': path.unlink()
    elif damage=='hash': path.write_bytes(b'tampered')
    elif damage=='unexpected': (directory/'unexpected.txt').write_text('x')
    elif damage=='result_id':
        payload=json.loads((directory/'result.json').read_text(encoding='utf-8')); payload['result_id']='wrong'
        (directory/'result.json').write_text(json.dumps(payload),encoding='utf-8')
    elif damage=='manifest': (directory/'manifest.json').write_text('{}')
    elif damage=='result_json': (directory/'result.json').write_text('{broken')
    else: (directory/'metadata/config_snapshot.json').write_text('{}')
    report=repo.verify(result.result_id)
    assert report.status=='FAIL'
    assert any((report.missing_files,report.hash_mismatches,report.errors,report.unexpected_files))
    with pytest.raises(PackageIntegrityError): repo.load(result.result_id)


def test_log_absence_is_explicit_not_fabricated(case):
    d,_,_,result,repo=case
    (d.last_run_dir/'logs/inspection.log').unlink()
    record=save(case); report=repo.verify(result.result_id)
    assert report.status=='PASS' and report.missing_logs==['logs/inspection.log']
    assert 'INSPECTION_LOG_MISSING' in record.warnings
    assert not (Path(record.result_dir)/'logs/inspection.log').exists()


def test_snapshot_is_actual_config_not_changed_global(case):
    d,_,config,result,repo=case
    config.calibration=config.calibration.with_user_scale(2.8)
    with pytest.raises(ConfigSnapshotError): save(case,config_snapshot=config)
    record=save(case)
    loaded=repo.load(record.result_id)
    assert loaded.calibration_info.spatial_scale_um_per_px==3.2


def test_no_snapshot_cannot_silently_reread_yaml(case):
    d,_,_,_,_=case
    (d.last_run_dir/'metadata/config_snapshot.json').unlink()
    with pytest.raises(ConfigSnapshotError): save(case)


def test_same_raw_multiple_results_and_basic_queries(case):
    d,_,_,result,repo=case; first=save(case)
    second=deepcopy(result); second.result_id=str(uuid4())
    repo.save(second,d.last_run_dir)
    assert len(repo.find_by_source_sha256(result.input_info.sha256))==2
    assert len(repo.query(sample_id='26',file_name='26 (1).raw',final_mode='roi-bh',fallback_used=False,min_defects=1,max_defects=1))==2
    assert repo.query(sample_id='missing')==[] and repo.query(fallback_used=True)==[]
    assert repo.query(final_mode='roi-j4')==[]
    assert len(repo.query(start_time=first.summary.saved_at))==2
    assert len(repo.query(end_time=first.summary.saved_at))==1
    assert repo.list_results()[0].result_id==second.result_id


def test_missing_and_invalid_load_options(case):
    *_,repo=case
    with pytest.raises(ResultNotFoundError): repo.load('unknown')
    assert repo.verify('unknown').status=='FAIL'
    with pytest.raises(ValueError): repo.load('unknown',verify='none')


def test_index_missing_corrupt_and_tampered_cache_rebuilds(case):
    *_,repo=case; save(case)
    for contents in (None,'{invalid}\n','{}\n'):
        index=repo.root/'index.jsonl'
        if contents is None: index.unlink()
        else: index.write_text(contents)
        assert len(repo.list_results())==1
        assert repo.last_index_report.status=='PASS'


def test_bad_result_does_not_break_rebuild(case):
    *_,repo=case; save(case)
    bad=repo.root/'broken'; bad.mkdir(); (bad/'result.json').write_text('broken')
    report=repo.rebuild_index()
    assert len(report.indexed_results)==1 and report.skipped_corrupt_results==['broken']
    assert report.status=='PARTIAL' and report.errors
    assert len(repo.list_results())==1


def test_index_failure_does_not_undo_valid_package(case,monkeypatch):
    *_,result,repo=case
    def fail(rows): raise OSError('injected index write failure')
    monkeypatch.setattr(repo.index,'write',fail)
    record=save(case)
    assert record.index_status=='INDEX_UPDATE_FAILED'
    assert repo.verify(result.result_id).status=='PASS'
    monkeypatch.undo()
    assert len(repo.rebuild_index().indexed_results)==1


def test_concurrent_same_id_one_commit(case):
    d,_,_,result,repo=case
    def attempt(_):
        try: return repo.save(deepcopy(result),d.last_run_dir).result_id
        except ResultAlreadyExistsError: return 'EXISTS'
    with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(attempt,range(2)))
    assert sorted(outcomes)==sorted([result.result_id,'EXISTS'])
    assert repo.verify(result.result_id).status=='PASS'


def test_export_full_package_crc_hash_and_no_overwrite(case,tmp_path):
    *_,result,repo=case; save(case)
    target=tmp_path/'export.zip'; record=repo.export_package(result.result_id,target)
    assert sha256(target)==record.sha256 and record.crc_status=='PASS'
    assert target.with_name(target.name+'.sha256').read_text().strip()==record.sha256
    with zipfile.ZipFile(target) as package:
        assert package.testzip() is None
        assert 'manifest.json' in package.namelist() and 'result.json' in package.namelist()
        assert all(not name.endswith(('.raw','.npy')) and not name.startswith('engine/') for name in package.namelist())
    with pytest.raises(FileExistsError): repo.export_package(result.result_id,target)


def test_export_refuses_repository_destination_and_corrupt_result(case):
    *_,result,repo=case; save(case)
    with pytest.raises(UnsafeArtifactPathError): repo.export_package(result.result_id,repo.root/'export.zip')
    (repo.root/result.result_id/'manifest.json').write_text('{}')
    with pytest.raises(PackageIntegrityError): repo.export_package(result.result_id,repo.root.parent/'other.zip')


@pytest.mark.parametrize('kwargs',[{'start_time':'2026-01-01'},{'min_defects':-1},{'min_defects':2,'max_defects':1},{'fallback_used':'false'}])
def test_query_invalid_constraints(case,kwargs):
    *_,repo=case
    with pytest.raises(ValueError): repo.query(**kwargs)


def test_application_service_uses_production_yaml_and_separates_persistence(case):
    d,raw,_,_,repo=case
    service=InspectionService(d,repo)
    record=service.inspect_and_save(raw)
    loaded=repo.load(record.result_id)
    snapshot=json.loads((Path(record.result_dir)/'metadata/config_snapshot.json').read_text(encoding='utf-8'))
    assert snapshot['status']=='REFERENCE_ENGINE_CONNECTED'
    assert loaded.algorithm_info.config_hash
    assert loaded.execution_info.final_mode.value=='roi-bh'
    assert not hasattr(repo,'detector')


def test_import_and_delete_are_explicitly_absent(case):
    *_,repo=case
    assert not hasattr(repo,'import_package') and not hasattr(repo,'delete')


@pytest.mark.parametrize('field',['algorithm_version','file_name','task_id'])
def test_absolute_manifest_metadata_is_refused(case,field):
    _,_,_,result,repo=case
    if field=='algorithm_version': result.algorithm_info.algorithm_version='D:/private/engine.py'
    elif field=='file_name': result.input_info.file_name='D:/private/input.raw'
    else: result.task_id='D:/private/task'
    with pytest.raises(PackageIntegrityError): save(case)
    assert not (repo.root/result.result_id).exists()


def test_existing_staging_directory_is_never_removed(case,monkeypatch):
    import infrastructure.repositories.json_repository as module
    from types import SimpleNamespace
    _,_,_,result,repo=case
    stage=repo.root/('.tmp_'+'a'*16); stage.mkdir(); marker=stage/'owned_by_other'; marker.write_text('preserve')
    monkeypatch.setattr(module,'uuid4',lambda:SimpleNamespace(hex='a'*32))
    with pytest.raises(RepositoryError): save(case)
    assert marker.read_text()=='preserve'
    assert not (repo.root/result.result_id).exists()
