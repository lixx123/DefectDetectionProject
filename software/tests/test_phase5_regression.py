"""Failing examples prove the gate can detect regressions, not just replay PASS."""
from pathlib import Path
from copy import deepcopy
from uuid import uuid4
import json, os, shutil
import numpy as np
import pytest
from test_phase3_adapter import detector, table
from domain import InspectionResult, FinalValidationError
from domain.configuration import InspectionConfig
from domain.enums import FallbackReason, PipelineMode, ExecutionStatus, FilterReason
from domain.audit import CandidateAuditRecord
from infrastructure.repositories import JsonResultRepository
from infrastructure.storage.package import sha256
from regression.comparator import compare_inspection_results, semantic_snapshot, compare_snapshots
from regression.policies import schema_contract, code_impact, auto_policy_gate
from regression.release_gate import release_decision
from regression.golden import run_golden, no_engine_execution
from scripts.update_golden_baseline import publish_candidate
from scripts.run_regression_suite import run_real

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def pair(tmp_path):
    raw=tmp_path/'26 (1).raw'; raw.write_bytes(np.arange(144,dtype='>u2').tobytes())
    d,_=detector(tmp_path); result=d.inspect(raw,InspectionConfig())
    return result,deepcopy(result),d.last_run_dir


def compare(pair):
    before,after,directory=pair
    return compare_inspection_results(before,after,directory,directory)


def test_identity_timestamp_and_runtime_are_diagnostics(pair):
    before,after,_=pair; old=after.defects[0].identity.defect_id
    after.defects[0].identity.defect_id='PERMUTED_ID'
    for row in after.audit_log.candidates:
        if row.final_defect_id==old: row.final_defect_id='PERMUTED_ID'
        if row.merged_into==old: row.merged_into='PERMUTED_ID'
    after.result_id=str(uuid4()); after.task_id='new_run'; after.algorithm_info.run_timestamp='new_time'
    after.algorithm_info.execution_time_seconds=before.algorithm_info.execution_time_seconds
    after.algorithm_info.runtime_environment['platform']='different_host'
    report=compare(pair)
    assert report.status in ('PASS','PASS_WITH_WARNINGS') and report.info and not report.critical_differences


@pytest.mark.parametrize('field',['area','Feret','grade','band','roi','None_to_zero','calibration','stats','audit','qa','config_hash','algorithm_runtime'])
def test_semantic_changes_fail_independently(pair,field):
    _,after,_=pair
    if field=='area': after.defects[0].geometry.area_px+=1
    elif field=='Feret': after.defects[0].geometry.length_px+=0.000001
    elif field=='grade': after.defects[0].classification.size_grade=__import__('domain.enums',fromlist=['SizeGrade']).SizeGrade.LARGE
    elif field=='band': after.defects[0].location.band_id='2'
    elif field=='roi': after.roi_info.band_list[0].mean_gray_dn=999
    elif field=='None_to_zero': after.defects[0].geometry.width_px=0
    elif field=='calibration': after.calibration_info.spatial_scale_um_per_px=2.8
    elif field=='stats': after.statistics.total_defects+=1
    elif field=='audit': after.audit_log.candidates[0].filter_message='changed reference decision'
    elif field=='qa': after.quality_control.checks[0].message='changed result QC meaning'
    elif field=='config_hash': after.algorithm_info.config_hash='f'*64
    else: after.algorithm_info.runtime_environment['opencv']='unapproved version'
    assert compare(pair).status=='FAIL'


def test_source_set_changed_still_pairs_by_exact_global_mask(pair):
    _,after,_=pair
    after.defects[0].detection.candidate_ids=['different_source']
    after.audit_log.candidates[0].candidate_id='different_source'
    report=compare(pair)
    assert report.status=='FAIL' and report.source_membership_changes
    assert not report.added_objects and not report.disappeared_objects


def test_final_binary_hash_detects_same_area_different_location(pair):
    before,_,directory=pair
    view=semantic_snapshot(before,directory); current=deepcopy(view)
    current['final_mask_sha256']='0'*64
    report=compare_snapshots(view,current)
    assert report.status=='FAIL' and report.mask_changes


def test_mask_file_tampering_is_not_a_missing_value_pass(pair):
    before,_,directory=pair
    (directory/before.defects[0].geometry.mask_reference.path).write_bytes(b'tampered')
    report=compare(pair)
    assert report.status=='FAIL' and report.errors


def test_candidate_json_order_is_not_semantic(pair):
    before,after,_=pair
    extra=CandidateAuditRecord(candidate_id='EXTRA',source='H',filter_message='unknown')
    for result in (before,after):
        result.audit_log.candidates.append(deepcopy(extra)); result.audit_log.source_candidate_count+=1
    after.audit_log.candidates.reverse()
    assert compare(pair).status in ('PASS','PASS_WITH_WARNINGS')


def test_runtime_slowdown_is_warning_not_physical_failure(pair):
    before,after,_=pair
    before.algorithm_info.execution_time_seconds=10; after.algorithm_info.execution_time_seconds=21
    report=compare(pair)
    assert report.status=='PASS_WITH_WARNINGS' and report.warnings and not report.critical_differences


def test_comparison_can_be_saved_for_review(pair,tmp_path):
    report=compare(pair); path=tmp_path/'comparison.json'; report.save_json(path)
    assert json.loads(path.read_text(encoding='utf-8'))==report.to_dict()


@pytest.mark.parametrize('path,required',[('core/pipeline.py',True),('domain/defect.py',True),('configs/production_v1.yaml',True),
    ('ui/viewer.py',False),('docs/design.md',False),('README.md',False),('regression/comparator.py',False),('unknown/new_module.py',True)])
def test_change_impact_is_conservative(path,required):
    # Known display-only paths do not imply a fresh algorithm execution.
    assert code_impact([path])['real_engine_required']==required


@pytest.mark.parametrize('required,executed,real_status,expected',[(False,False,'NOT_RUN','PASS'),
    (True,False,'NOT_RUN','NOT_COMPLETE'),(True,True,'PASS','PASS'),(True,True,'FAIL','FAIL')])
def test_real_not_run_cannot_satisfy_release(required,executed,real_status,expected):
    assert release_decision(fast_status='PASS',golden_status='PASS',repository_status='PASS',schema_status='PASS',
        auto_status='PASS',protection_status='PASS',real_required=required,real_executed=executed,real_status=real_status)==expected


def test_release_fails_on_golden_or_repository_failure():
    assert release_decision(fast_status='PASS',golden_status='FAIL',repository_status='PASS',schema_status='PASS',auto_status='PASS',protection_status='PASS')=='FAIL'
    assert release_decision(fast_status='PASS',golden_status='PASS',repository_status='FAIL',schema_status='PASS',auto_status='PASS',protection_status='PASS')=='FAIL'


@pytest.mark.parametrize('reason',list(FallbackReason))
def test_each_fallback_rejects_roi_and_skips_roi_j4(tmp_path,reason):
    raw=tmp_path/'tiny.raw'; raw.write_bytes(np.arange(144,dtype='>u2').tobytes())
    d,adapter=detector(tmp_path,{PipelineMode.ROI_BH:reason})
    result=d.inspect(raw,InspectionConfig())
    assert adapter.calls==[PipelineMode.ROI_BH,PipelineMode.FULL]
    assert PipelineMode.ROI_J4 not in adapter.calls
    assert result.execution_info.fallback_used and result.execution_info.fallback_reason==reason
    assert result.execution_info.attempts[0].status==ExecutionStatus.FAILED
    result.validate_final()


def test_both_attempts_failed_never_enter_repository(tmp_path):
    raw=tmp_path/'tiny.raw'; raw.write_bytes(np.arange(144,dtype='>u2').tobytes())
    d,_=detector(tmp_path,{PipelineMode.ROI_BH:FallbackReason.SENTINEL_CONSUMED,PipelineMode.FULL:FallbackReason.J4_EXECUTION_FAILED})
    result=d.inspect(raw,InspectionConfig()); repo=JsonResultRepository(tmp_path/'repository')
    assert result.execution_info.status==ExecutionStatus.FAILED and result.execution_info.final_mode is None
    with pytest.raises(FinalValidationError): repo.save(result,d.last_run_dir)
    assert repo.list_results()==[]


def test_sentinel_consumption_reaches_actual_qa_fallback(tmp_path):
    raw=tmp_path/'tiny.raw'; raw.write_bytes(np.arange(144,dtype='>u2').tobytes())
    d,adapter=detector(tmp_path)
    # Bridge QA is what the real consumed-window guard publishes; inject its rejection.
    path=adapter.outputs[PipelineMode.ROI_BH]/'bridge_qa.json'
    qa=json.loads(path.read_text(encoding='utf-8')); qa['sentinel_status']='FAIL'
    path.write_text(json.dumps(qa),encoding='utf-8')
    result=d.inspect(raw,InspectionConfig())
    assert adapter.calls==[PipelineMode.ROI_BH,PipelineMode.FULL]
    assert result.execution_info.fallback_reason==FallbackReason.SENTINEL_CONSUMED
    assert auto_policy_gate(ROOT)['sentinel_consumed_guards']>=2


def test_frozen_wire_schema_and_enums():
    expected=json.loads((ROOT/'tests/golden/schema_contract.json').read_text(encoding='utf-8'))
    actual=schema_contract(); assert actual==expected
    assert len(actual['enum_wire_values']['FallbackReason'])==10
    assert 'SIZE_OR_GEOMETRY_FILTER' not in actual['enum_wire_values']['FilterReason']
    assert actual['classes']['DefectGeometry']['width_px']['nullable']


def test_golden_writes_refused_without_explicit_approval(tmp_path):
    path=tmp_path/'golden.json'; path.write_text('{"preserve":true}')
    before=sha256(path)
    with pytest.raises(PermissionError): publish_candidate({},path)
    with pytest.raises(PermissionError): publish_candidate({},path,approve=True,reason='test')
    assert sha256(path)==before


def test_explicit_update_generates_human_audit(tmp_path):
    view={'golden_set_version':'1.0','baseline_commit':'old','samples':[]}
    path=tmp_path/'golden.json'
    publish_candidate(view,path,approve=True,reason='initialize fixture')
    candidate=dict(view,baseline_commit='new')
    audit=publish_candidate(candidate,path,approve=True,allow_update=True,reason='reviewed fixture update')
    assert audit['old_commit']=='old' and audit['new_commit']=='new' and not audit['physical_evidence_modified']
    assert len(list(tmp_path.glob('golden_change_report_*.json')))==2


def test_missing_real_raw_is_explicit_not_run_and_never_constructs_detector(tmp_path):
    def forbidden(**kwargs): raise AssertionError('must not construct engine for missing RAW')
    report=run_real(ROOT,tmp_path,raw_root=None,detector_factory=forbidden)
    assert report['status']=='NOT_RUN' and not report['real_engine_executed'] and report['algorithm_executions']==0


def test_golden_forbids_starting_subprocess():
    import subprocess
    with no_engine_execution(),pytest.raises(RuntimeError,match='GOLDEN forbids'):
        subprocess.Popen(['not-an-engine'])


@pytest.fixture(scope='module')
def golden_report(tmp_path_factory):
    scratch=tmp_path_factory.mktemp('golden_suite')
    report=run_golden(ROOT,scratch)
    destination=os.environ.get('DEFECT_REGRESSION_REPORT_DIR')
    if destination:
        with (Path(destination)/'golden_report.json').open('x',encoding='utf-8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
    return report


@pytest.mark.golden
@pytest.mark.slow
@pytest.mark.parametrize('sample,mode',[(f'26_{f}',m) for f in (1,2) for m in ('full','roi-bh','auto')])
def test_six_golden_semantics(golden_report,sample,mode):
    case=next(c for c in golden_report['cases'] if c['sample_id']==sample and c['mode']==mode)
    assert case['status']=='PASS',case
    assert case['mask_hash_match'] and case['object_level_match'] and case['roi_band_match'] and case['audit_semantics_match']
    assert case['current_audit_mapper']=='PASS'


@pytest.mark.golden
@pytest.mark.repository
@pytest.mark.parametrize('sample',['26_1','26_2'])
def test_two_golden_packages(golden_report,sample):
    case=next(c for c in golden_report['repository_cases'] if c['sample_id']==sample)
    assert case['status']=='PASS',case
    assert case['zip_crc']=='PASS' and golden_report['repository_status']=='PASS'
    assert golden_report['algorithm_executions']==0 and not golden_report['golden_evidence_changed']


def test_real_profile_six_mode_flow_can_be_simulated_without_real_claim(pair,tmp_path,monkeypatch):
    import scripts.run_regression_suite as module
    before,_,source=pair
    raw_root=tmp_path/'raw'; raw_root.mkdir()
    files=[]
    for frame in (1,2):
        path=raw_root/f'26 ({frame}).raw'; path.write_bytes(np.arange(144,dtype='>u2').tobytes()); files.append(path)
    def make_result(frame,config):
        result=deepcopy(before)
        mode=PipelineMode.ROI_BH if config.pipeline_mode==PipelineMode.AUTO else config.pipeline_mode
        result.input_info.file_name=files[frame-1].name; result.input_info.sha256=sha256(files[frame-1])
        result.execution_info.requested_mode=config.pipeline_mode
        result.execution_info.attempted_mode=mode; result.execution_info.final_mode=mode
        result.execution_info.attempts[0].mode=mode
        result.algorithm_info.config_hash=config.config_hash()
        return result
    from domain.serialization import to_dict
    samples=[]
    for frame in (1,2):
        sample={'sample_id':f'26_{frame}','raw_file_name':files[frame-1].name,'raw_sha256':sha256(files[frame-1])}
        for mode,key in [('full','expected_full'),('roi-bh','expected_roi_bh'),('auto','expected_auto')]:
            config=InspectionConfig(pipeline_mode=PipelineMode(mode),advanced_debug=mode!='auto')
            sample[key]={'config_snapshot':to_dict(config),'snapshot':semantic_snapshot(make_result(frame,config),source)}
        samples.append(sample)
    monkeypatch.setattr(module,'load_manifest',lambda root:{'samples':samples})
    calls=[]
    class SimulatedDetector:
        def __init__(self,**kwargs): self.root=kwargs['output_root']; self.root.mkdir(parents=True)
        def inspect(self,path,config):
            calls.append(config.pipeline_mode.value)
            self.last_run_dir=self.root/str(len(calls)); shutil.copytree(source,self.last_run_dir)
            frame=1 if path.name==files[0].name else 2
            return make_result(frame,config)
    report=module.run_real(ROOT,tmp_path/'real_profile',raw_root,detector_factory=SimulatedDetector)
    assert report['status'] in ('PASS','PASS_WITH_WARNINGS'),report
    assert calls==['full','roi-bh','auto']*2
    assert report['simulation'] and not report['real_engine_executed'] and report['algorithm_executions']==0


def test_missing_golden_evidence_fails_without_skipping(tmp_path):
    report=run_golden(tmp_path,tmp_path/'scratch')
    assert report['status']=='FAIL' and report['errors']


def test_ui_config_edit_cannot_recalibrate_historical_result(pair,tmp_path):
    before,_,source=pair
    history=tmp_path/'history.json'; before.save_json(history)
    # A separate global configuration file is changed, never the frozen production YAML.
    config=InspectionConfig(); config.calibration=config.calibration.with_user_scale(2.8)
    from configs.loader import save_config,load_config
    path=tmp_path/'production.yaml'; save_config(config,path)
    assert load_config(path).calibration.spatial_scale_um_per_px==2.8
    restored=InspectionResult.load_json(history)
    assert restored==before and restored.calibration_info.spatial_scale_um_per_px==3.2
    assert restored.defects[0].geometry.area_um2==restored.defects[0].geometry.area_px*3.2**2


@pytest.mark.parametrize('required,executed',[(True,False),(False,True)])
def test_explicit_real_failure_always_fails_release(required,executed):
    assert release_decision(fast_status='PASS',golden_status='PASS',repository_status='PASS',schema_status='PASS',auto_status='PASS',
        protection_status='PASS',real_required=required,real_executed=executed,real_status='FAIL')=='FAIL'


def test_disappeared_object_is_critical_even_with_unchanged_full_mask(pair):
    _,after,_=pair; after.defects=[]
    report=compare(pair)
    assert report.status=='FAIL' and report.disappeared_objects


@pytest.mark.parametrize('failure',['roi_j4','sentinel_removed'])
def test_independent_policy_gate_rejects_unsafe_refactor(tmp_path,failure):
    for relative in ('configs/production_v1.yaml','core/pipeline.py','core/runtime/engine_worker.py'):
        target=tmp_path/relative; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/relative,target)
    if failure=='roi_j4':
        path=tmp_path/'core/pipeline.py'
        path.write_text(path.read_text(encoding='utf-8').replace('[PipelineMode.ROI_BH, PipelineMode.FULL]',
            '[PipelineMode.ROI_BH, PipelineMode.ROI_J4, PipelineMode.FULL]'),encoding='utf-8')
    else:
        path=tmp_path/'core/runtime/engine_worker.py'
        path.write_text(path.read_text(encoding='utf-8').replace('require_computed_response','removed_computed_guard'),encoding='utf-8')
    gate=auto_policy_gate(tmp_path)
    assert gate['status']=='FAIL'
    if failure=='roi_j4': assert gate['roi_j4_in_auto']
