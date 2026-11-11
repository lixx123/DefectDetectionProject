"""Strict, unmocked formal/evidence admission tests. All RAW pixels synthetic."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
import hashlib,json,time,threading,shutil
import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage,QCursor
from test_phase6_ui import qapp,window,wait,image_frame
from domain import InspectionResult,Defect,DefectIdentity,DefectGeometry
from domain.audit import AuditInfo,CandidateAuditRecord
from domain.common import BoundingBox,Point
from domain.enums import PipelineMode,ExecutionStatus,QAStatus,CandidateDisposition,SizeGrade
from domain.execution import ExecutionInfo,ExecutionAttempt
from domain.configuration import InspectionConfig
from infrastructure.repositories import JsonResultRepository
from ui.models.human_review import HumanReviewRepository,ReviewContext,ReviewConflict,summary,latest
from ui.models.human_review.model import source_payload,digest
from ui.models.human_review.evidence import FormalResultAuthority,ReviewAccess,validate_raw,stream_sha256
from ui.models.review_admission import ReviewAdmissionEngine,load_policy
from ui.models.result_view_model import ResultViewModel,DisplayFrame
from ui.controllers.inspection_controller import InspectionController

@pytest.fixture(autouse=True)
def isolate(qapp):
    QCursor.setPos(0,0)
    with patch('core.detector.Detector.inspect',side_effect=AssertionError('Detector forbidden in Revision')):yield
    QCursor.setPos(0,0);qapp.processEvents()


def synthetic_case(root):
    root.mkdir(parents=True,exist_ok=True)
    path=root/'synthetic.raw';pixels=((np.indices((80,100))[0]*19+np.indices((80,100))[1]*13)%4096).astype('>u2');pixels.tofile(path)
    r=InspectionResult(task_id='SYNTHETIC_REVIEW_EVIDENCE');i=r.input_info
    i.file_name=path.name;i.width_px=100;i.height_px=80;i.container_bits=16;i.effective_bits=12;i.byte_order='big';i.input_format='RAW';i.sha256=stream_sha256(path)
    cfg=InspectionConfig(pipeline_mode=PipelineMode.FULL,advanced_debug=True);r.calibration_info=cfg.calibration
    r.algorithm_info.config_name=cfg.config_name;r.algorithm_info.config_version=cfg.config_version;r.algorithm_info.config_hash=cfg.config_hash()
    r.execution_info=ExecutionInfo(requested_mode=PipelineMode.FULL,attempted_mode=PipelineMode.FULL,final_mode=PipelineMode.FULL,
      status=ExecutionStatus.SUCCEEDED,qa_status=QAStatus.PASS,attempts=[ExecutionAttempt(mode=PipelineMode.FULL,status=ExecutionStatus.SUCCEEDED,qa_status=QAStatus.PASS)])
    r.quality_control.status=QAStatus.PASS
    g=DefectGeometry(bbox=BoundingBox(20,20,26,27),center=Point(23,23),area_px=39,length_px=10)
    d=Defect(identity=DefectIdentity(defect_id='SYNTHETIC-FINAL'),geometry=g);d.classification.size_grade=SizeGrade.SMALL;r.defects=[d];r.statistics.total_defects=1
    c=CandidateAuditRecord(candidate_id='C1',source='SYNTHETIC',current_stage='FINAL_SELECTION',disposition=CandidateDisposition.REVIEW,
      initial_geometry=DefectGeometry(bbox=BoundingBox(22,22,25,26),area_px=12,length_px=4))
    r.audit_log=AuditInfo(candidates=[c],source_candidate_count=1,lineage_complete=True)
    r.validate_final();return r,cfg,path

@pytest.fixture
def formal(tmp_path):
    r,cfg,path=synthetic_case(tmp_path/'source');repo=JsonResultRepository(tmp_path/'formal')
    record=repo.save(r,path.parent,config_snapshot=cfg);loaded,binding=FormalResultAuthority(repo).load(r.result_id)
    vm=ResultViewModel(loaded,record.result_dir,formal_binding=binding)
    return vm,path,repo,cfg


def context(vm):return ReviewContext.from_result(vm.result,ReviewAdmissionEngine().evaluate(vm.result,load_policy()),vm.review_access)
def show(window,vm,qapp,saved=True):
    window.display_result(vm,image_frame(),saved=saved);window.tabs.setCurrentIndex(4)
    wait(qapp,lambda:not window.controller.busy and window.human_review_page.admission is not None and not window.admission_page.query_pending)
    return window.human_review_page

def settle(window,qapp):wait(qapp,lambda:not window.controller.busy and not window.admission_page.query_pending and not window.human_review_page.image_pending)


def test_temporary_gate_is_service_level_even_with_raw(tmp_path):
    r,cfg,path=synthetic_case(tmp_path/'source');vm=ResultViewModel(r,path.parent);ctx=context(vm);repo=HumanReviewRepository(tmp_path/'reviews')
    vm.review_access.raw=validate_raw(path,r)
    try:
        assert not vm.review_access.eligibility(ctx).can_create_session
        with pytest.raises(ReviewConflict,match='TEMPORARY'):repo.create(ctx,'Synthetic')
        with pytest.raises(ReviewConflict,match='TEMPORARY'):repo.submit(ctx,'fake','task','UNCERTAIN','Synthetic',selected_task_key='task',expected_revision=0)
        assert not repo.root.exists()
    finally:vm.review_access.raw.clear()


def test_explicit_staging_authority_cannot_grant_binding(tmp_path):
    r,cfg,path=synthetic_case(tmp_path/'source');repo=JsonResultRepository(tmp_path/'staging');repo.save(r,path.parent,config_snapshot=cfg)
    with pytest.raises(ReviewConflict,match='TEMPORARY'):FormalResultAuthority(repo,staging_root=repo.root).load(r.result_id)


def test_formal_no_raw_can_create_restore_but_never_submit(formal,tmp_path):
    vm,path,_,_=formal;ctx=context(vm);repo=HumanReviewRepository(tmp_path/'reviews');s=repo.create(ctx,'Synthetic')
    assert vm.is_formal_result and vm.review_access.eligibility(ctx).can_create_session
    assert not vm.review_access.eligibility(ctx).can_submit_review and repo.load(ctx.result_id)==s
    t=ctx.tasks[0]['task_key']
    with pytest.raises(ReviewConflict,match='RAW_REQUIRED'):repo.submit(ctx,s['session_id'],t,'UNCERTAIN','Synthetic',selected_task_key=t,expected_revision=0)
    assert not repo.load(ctx.result_id)['records']

@pytest.mark.parametrize('change,error',[('hash','RAW_MISMATCH'),('size','RAW_SIZE_MISMATCH'),('byte_order','UNSUPPORTED'),('effective_bits','UNSUPPORTED'),('container_bits','UNSUPPORTED'),('input_format','UNSUPPORTED'),('dimensions','DIMENSIONS'),('missing_sha','SHA256')])
def test_raw_adverse_checks(formal,tmp_path,change,error):
    vm,path,_,_=formal;r=deepcopy(vm.result);candidate=tmp_path/'wrong.raw';shutil.copyfile(path,candidate)
    if change=='hash':candidate.write_bytes(b'X'*candidate.stat().st_size)
    elif change=='size':candidate.write_bytes(b'X')
    elif change=='dimensions':r.input_info.width_px=0
    elif change=='missing_sha':r.input_info.sha256=None
    else:setattr(r.input_info,change,{'byte_order':'little','effective_bits':16,'container_bits':8,'input_format':'PNG'}[change])
    before=r.to_dict()
    with pytest.raises(ReviewConflict,match=error):validate_raw(candidate,r)
    assert r.to_dict()==before


def test_missing_and_directory_raw(formal,tmp_path):
    vm,*_=formal
    for path in (tmp_path/'absent.raw',tmp_path):
        with pytest.raises(ReviewConflict):validate_raw(path,vm.result)


def test_different_filename_same_hash_and_same_filename_wrong_bytes(formal,tmp_path):
    vm,path,_,_=formal;renamed=tmp_path/'different-name.raw';shutil.copyfile(path,renamed)
    b=validate_raw(renamed,vm.result)
    try:assert b.verified and b.width==100 and b.height==80 and b.sha256==vm.result.input_info.sha256
    finally:b.clear()
    wrong=tmp_path/path.name;wrong.write_bytes(b'0'*path.stat().st_size)
    with pytest.raises(ReviewConflict,match='RAW_MISMATCH'):validate_raw(wrong,vm.result)


def test_raw_readonly_lease_and_closed_provider(formal):
    vm,path,_,_=formal;b=validate_raw(path,vm.result);ctx=context(vm)
    try:
        b.require(ctx);assert b.crop(20,20,30,30).width()==10
        assert b.dn(20,20)==640 and b.crop(20,20,21,21).pixelColor(0,0).red()==int(640*255/4095)
        if __import__('os').name=='nt':
            with pytest.raises(OSError):path.open('r+b')
    finally:b.clear()
    assert b.provider._raw is None
    with pytest.raises(ReviewConflict):b.require(ctx)


def test_verified_submission_and_no_path_persisted_restart_requires_raw(formal,tmp_path):
    vm,path,repo,_=formal;ctx=context(vm);reviews=HumanReviewRepository(tmp_path/'reviews');state=reviews.create(ctx,'Synthetic');vm.review_access.raw=validate_raw(path,vm.result)
    before=vm.result.to_dict();t=ctx.tasks[0]['task_key']
    try:
        state=reviews.submit(ctx,state['session_id'],t,'UNCERTAIN','Synthetic',selected_task_key=t,expected_revision=0)
        text=(reviews.root/ctx.result_id/(state['session_id']+'.json')).read_text(encoding='utf-8')
        assert str(path) not in text and 'raw_binding' not in text
        for fmt in ('csv','json'):
            target=tmp_path/('review.'+fmt);reviews.export(state,target,fmt);assert str(path) not in target.read_text(encoding='utf-8-sig')
        loaded,binding=FormalResultAuthority(repo).load(ctx.result_id);restarted=ResultViewModel(loaded,binding.package_dir,formal_binding=binding)
        assert not restarted.review_access.eligibility(context(restarted)).can_submit_review
        assert reviews.load(ctx.result_id)==state and vm.result.to_dict()==before
    finally:vm.review_access.raw.clear()


def test_stream_hash_bounded_reads(formal):
    vm,path,_,_=formal;original=Path.open;sizes=[]
    class Reader:
        def __init__(self,f):self.f=f
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def read(self,n=-1):sizes.append(n);assert 0<n<=1024*1024;return self.f.read(n)
    def opener(self,*args,**kw):return Reader(original(self,*args,**kw)) if self==path and args and args[0]=='rb' else original(self,*args,**kw)
    with patch.object(Path,'open',opener):assert stream_sha256(path)==vm.result.input_info.sha256
    assert sizes


def test_ui_temporary_disabled(window,qapp,tmp_path):
    r,_,path=synthetic_case(tmp_path/'s');p=show(window,ResultViewModel(r,path.parent),qapp,saved=False)
    assert window.tabs.tabText(4)=='人工复核'
    assert not p.start.isEnabled() and not p.save.isEnabled() and not p.attach.isEnabled()
    assert '先保存正式结果' in p.evidence_status.text()
    p.reviewer.setText('Synthetic');p.open_session();assert p.state is None


def test_ui_formal_attach_crop_detach_and_switch(window,qapp,formal,tmp_path):
    vm,path,_,_=formal;p=show(window,vm,qapp);before=vm.result.to_dict();p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp)
    assert p.state and not p.save.isEnabled() and '缺少可验证' in p.evidence_status.text()
    assert p.attach_raw(path);settle(window,qapp)
    assert p.save.isEnabled() and 'SHA256 已校验' in p.image_status.text()
    bound=p.access.raw;p.detach_raw();settle(window,qapp);assert bound.provider._raw is None and not p.save.isEnabled()
    p.attach_raw(path);settle(window,qapp);bound=p.access.raw
    r,_,newpath=synthetic_case(tmp_path/'second');window.display_result(ResultViewModel(r,newpath.parent),image_frame(),saved=False);settle(window,qapp)
    assert bound.provider._raw is None and p.access.raw is None and vm.result.to_dict()==before


def test_ui_async_old_validation_discarded(window,qapp,formal,tmp_path):
    vm,path,_,_=formal;p=show(window,vm,qapp);entered=threading.Event();release=threading.Event();bindings=[]
    def slow(*args):
        entered.set();release.wait(5);b=validate_raw(*args);bindings.append(b);return b
    try:
        with patch('ui.widgets.human_review_workspace.validate_raw',side_effect=slow):
            p.attach_raw(path);wait(qapp,entered.is_set)
            assert not p.save.isEnabled() and p.raw_verifying
            r,_,newpath=synthetic_case(tmp_path/'new');window.display_result(ResultViewModel(r,newpath.parent),image_frame(),saved=False)
            release.set();settle(window,qapp)
    finally:release.set()
    assert p.access.raw is None and bindings and bindings[0].provider._raw is None


def test_ui_worker_heartbeat_and_wrong_replacement(window,qapp,formal,tmp_path):
    vm,path,_,_=formal;p=show(window,vm,qapp);ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(2)
    original=stream_sha256
    def slow(p):time.sleep(.15);return original(p)
    with patch('ui.models.human_review.evidence.stream_sha256',side_effect=slow):p.attach_raw(path);settle(window,qapp)
    timer.stop();assert ticks and p.access.raw
    wrong=tmp_path/'wrong.raw';wrong.write_bytes(b'X'*path.stat().st_size);p.attach_raw(wrong);settle(window,qapp)
    assert p.access.raw is None and 'RAW_MISMATCH' in p.message.text()


def test_save_formalizes_vm_preserves_result_tasks_and_verified_raw(window,qapp,tmp_path):
    r,cfg,path=synthetic_case(tmp_path/'src');c=window.controller
    record=c.staging.save(r,path.parent,config_snapshot=cfg);temporary=c.staging.load(r.result_id)
    source=ResultViewModel(temporary,record.result_dir);p=show(window,source,qapp,saved=False)
    from ui.raw_image_provider import RawImageProvider
    window.raw=RawImageProvider(path,100,80)
    before=source.result.to_dict();tasks=[t.task_key for t in ReviewAdmissionEngine().evaluate(source.result,load_policy()).tasks]
    window._request_filter_metadata=lambda:("QA_FILTER", "")
    window._save();settle(window,qapp)
    vm=window.view_model
    assert window.saved and vm is not source and vm.is_formal_result and vm.package_dir==c.repository.root/r.result_id
    expected=deepcopy(before);expected['extensions']['filter_metadata']={'filter_id':'QA_FILTER','notes':''}
    assert source.result.to_dict()==before
    assert vm.result.to_dict()==expected and [t.task_key for t in ReviewAdmissionEngine().evaluate(vm.result,load_policy()).tasks]==tasks
    assert vm.review_access.raw and vm.review_access.raw.verified and vm.review_access.eligibility().can_submit_review


def test_save_failure_leaves_temporary(window,qapp,tmp_path):
    r,_,path=synthetic_case(tmp_path/'s');p=show(window,ResultViewModel(r,path.parent),qapp,saved=False)
    with patch.object(window.controller.repository,'save',side_effect=ValueError('synthetic save failure')):
        window._request_filter_metadata=lambda:("QA_FILTER", "")
        window._save();settle(window,qapp)
    assert not window.saved and not window.view_model.is_formal_result and not p.start.isEnabled()

@pytest.mark.parametrize('kind',['null','zero-width','zero-height'])
def test_image_viewer_empty_defense(window,kind):
    frame=image_frame()
    if kind=='null':frame.image=QImage()
    elif kind=='zero-width':frame.width=0
    else:frame.height=0
    window.viewer.set_frame(frame,fit=True);assert window.viewer.base_item is None
    assert any(getattr(x,'text',lambda:'' )().startswith('图像不可用') for x in window.viewer.scene().items())


def test_regression_temp_reservation_survives_stale_directory(tmp_path):
    from scripts.run_regression_suite import run_pytest
    root=tmp_path/'r';(root/'output/.pt_aaaaaaaa').mkdir(parents=True);out=tmp_path/'report';out.mkdir();seen=[]
    def fake(command,**kwargs):
        base=Path(command[command.index('--basetemp')+1]);assert base.parent.is_dir() and base.name=='t';seen.append(base)
        Path(command[command.index('--junitxml')+1]).write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"/></testsuites>')
        return type('Completed',(),dict(returncode=0))()
    with patch('scripts.run_regression_suite.subprocess.run',side_effect=fake):assert run_pytest(root,out,'fast')['status']=='PASS'
    assert seen[0].parent.name!='.pt_aaaaaaaa' and (root/'output/.pt_aaaaaaaa').exists()
