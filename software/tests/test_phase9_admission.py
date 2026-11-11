"""Read-only admission rules and UI. All pixels are synthetic; history is frozen."""
from dataclasses import replace,asdict
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import time
import pytest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QCursor
from test_phase6_ui import qapp,window,vm,wait,image_frame
from domain.audit import AuditInfo,CandidateAuditRecord
from domain.common import BoundingBox,Point
from domain.defect import DefectGeometry
from domain.review import ReviewInfo
from domain.enums import CandidateDisposition as D,FilterReason as F,ReviewStatus,SizeGrade
from ui.models.result_view_model import ResultViewModel
from ui.models.review_admission import ReviewAdmissionEngine,ReviewAdmissionConfig,load_policy,ReviewBucket as B,ReviewPriority as P,ReviewObjectKey
from ui.models.review_admission.rules import near_threshold,RULE_PRIORITY
from ui.models.review_admission.model import ReviewAdmissionDecision,ReviewTask
from ui.models.review_queue_view_model import ReviewQueueViewModel,ReviewQueueQuery,object_key,row_key


@pytest.fixture(autouse=True)
def cursor(qapp):
    QCursor.setPos(0,0)
    yield
    QCursor.setPos(0,0);qapp.processEvents()


@pytest.fixture
def clean(vm):
    vm.result.audit_log=AuditInfo(source_candidate_count=0,lineage_complete=True)
    return vm


def candidate(cid='C1',source='A',**kwargs):
    g=DefectGeometry(bbox=BoundingBox(20,20,24,25),center=Point(22,22.5),area_px=20,length_px=5)
    return CandidateAuditRecord(candidate_id=cid,source=source,initial_geometry=g,current_stage='FINAL_SELECTION',disposition=D.REVIEW,**kwargs)


def set_candidates(vm,rows):
    vm.result.audit_log=AuditInfo(candidates=rows,source_candidate_count=len(rows),lineage_complete=True)
    return vm


def evaluate(vm,config=None):return ReviewAdmissionEngine().evaluate(vm.result,config)
def for_candidate(a,source='A',cid='C1'):
    return next(d for d in a.decisions if d.object_key==ReviewObjectKey('CANDIDATE',candidate_source=source,candidate_id=cid))
def for_defect(a):return next(d for d in a.decisions if d.object_key.kind=='DEFECT')
def settled(window,qapp):wait(qapp,lambda:not window.controller.busy and not window.admission_page.query_pending)
def show(window,vm,qapp):
    window.display_result(vm,image_frame());window.tabs.setCurrentIndex(4)
    wait(qapp,lambda:not window.controller.busy and window.admission_page.queue_vm is not None and not window.admission_page.query_pending)
    return window.admission_page


def test_four_buckets_and_documented_precedence():
    assert [b.value for b in B]==['AUTO_ACCEPT','AUTO_REJECT','MANUAL_REVIEW','AUDIT_ONLY']
    assert RULE_PRIORITY[0]=='HARD_SAFETY' and RULE_PRIORITY[1]=='FINAL_DEFECT_PROTECTION'


def test_key_is_kind_and_source_identity():
    assert ReviewObjectKey('CANDIDATE',candidate_source='A',candidate_id='001')!=ReviewObjectKey('CANDIDATE',candidate_source='B',candidate_id='001')
    with pytest.raises(ValueError):ReviewObjectKey('CANDIDATE',candidate_id='001')


@pytest.mark.parametrize('bucket',[B.AUTO_REJECT,B.AUDIT_ONLY])
def test_final_defect_bucket_protection_constructor(bucket):
    with pytest.raises(ValueError,match='protected'):
        ReviewAdmissionDecision(ReviewObjectKey('DEFECT',defect_id='F'),bucket,None,('reason',),{})


@pytest.mark.parametrize('reason',[F.OUTSIDE_WORK_REGION,F.BACKGROUND_NOISE,F.LOW_EVIDENCE])
def test_explicit_filtered_low_risk_reject(clean,reason):
    c=candidate();c.disposition=D.FILTERED;c.filter_reason=reason;set_candidates(clean,[c])
    a=evaluate(clean);d=for_candidate(a)
    assert d.bucket==B.AUTO_REJECT and not a.tasks


def test_historical_review_is_not_manual_queue(clean):
    c=candidate();c.current_stage='HISTORICAL_ARCHIVE_NOT_RESCANNED';set_candidates(clean,[c]);a=evaluate(clean)
    assert a.summary['audit_review_count']==1 and a.summary['manual_review_task_count']==0
    assert for_candidate(a).bucket==B.AUDIT_ONLY and 'HISTORICAL_AUDIT_ONLY' in for_candidate(a).reasons


def test_historical_outside_large_kept_as_audit_not_image_task(clean):
    c=candidate(extensions={'reference_reason_category':'OUTSIDE_WORK_REGION'});c.current_stage='HISTORICAL_ARCHIVE_NOT_RESCANNED';c.initial_geometry.area_px=1000
    set_candidates(clean,[c]);assert for_candidate(evaluate(clean)).bucket==B.AUDIT_ONLY


@pytest.mark.parametrize('risk',['area','feret','promising','boundary','independent_source','spatial'])
def test_weak_evidence_high_risk_never_auto_rejected(clean,risk):
    c=candidate();c.disposition=D.FILTERED;c.filter_reason=F.LOW_EVIDENCE;rows=[c]
    if risk=='area':c.initial_geometry.area_px=300
    if risk=='feret':c.initial_geometry.length_px=50
    if risk=='promising':c.extensions={'reference_decision':'K8C_PROMISING_DARK_REVIEW'}
    if risk=='boundary':c.extensions={'reference_decision':'K8C_BOUNDARY_REVIEW'}
    if risk=='independent_source':
        c.extensions={'independent_source_evidence':True};rows.append(candidate(source='B'))
    if risk=='spatial':c.initial_geometry.bbox=clean.defects[0].geometry.bbox
    set_candidates(clean,rows);d=for_candidate(evaluate(clean))
    assert d.bucket==B.MANUAL_REVIEW and d.priority in (P.HIGH,P.MEDIUM)


def test_bbox_coincidence_not_independent_source_claim(clean):
    a=candidate();b=candidate(source='B')
    for c in (a,b):c.extensions={'reference_decision':'K8C_MICRO_REVIEW_NOT_PROVEN_NOISE'}
    set_candidates(clean,[a,b]);result=evaluate(clean)
    assert for_candidate(result).evidence['multi_source_coincidence']
    assert not for_candidate(result).evidence['independent_source_support']
    assert all(d.bucket==B.AUDIT_ONLY for d in result.decisions if d.object_key.kind=='CANDIDATE')


@pytest.mark.parametrize('flag',['MICRO_HIDE_SUGGESTION_AREA_1_OR_2PX_PROVISIONAL_NO_DELETE','MICRO_REVIEW_AREA_3_TO_7PX_NOT_PROVEN_NOISE','J5_J5_WORK_SMALL','EXISTING_FIXED_H_SHARES_FIXED_170_230_H_SEED','DARK_SPOT_EVIDENCE_NOT_SUFFICIENT'])
def test_known_low_risk_review_kept_not_relabelled_noise(clean,flag):
    c=candidate(extensions={'reference_decision':flag});set_candidates(clean,[c]);before=clean.result.to_dict();d=for_candidate(evaluate(clean))
    assert d.bucket==B.AUDIT_ONLY and 'PROVISIONAL_LOW_RISK_AUDIT_ONLY' in d.reasons
    assert clean.result.to_dict()==before and c.disposition==D.REVIEW and c.filter_reason is None


def test_linked_retained_candidate_not_duplicate_task(clean):
    fid=clean.defects[0].identity.defect_id;c=candidate(final_defect_id=fid);c.disposition=D.RETAINED
    set_candidates(clean,[c]);clean.defects[0].detection.candidate_ids=['C1'];a=evaluate(clean)
    assert for_candidate(a).bucket==B.AUDIT_ONLY and for_defect(a).bucket==B.AUTO_ACCEPT and not a.tasks


@pytest.mark.parametrize('historical',[False,True])
def test_normal_and_historical_merged_safe(clean,historical):
    fid=clean.defects[0].identity.defect_id;t=candidate(cid='target',final_defect_id=fid);t.disposition=D.RETAINED
    c=candidate(cid='merged',final_defect_id=fid);c.disposition=D.MERGED;c.merged_into=fid if historical else 'target'
    set_candidates(clean,[t,c]);clean.defects[0].detection.candidate_ids=['target','merged'];a=evaluate(clean)
    d=for_candidate(a,cid='merged');assert d.bucket==B.AUDIT_ONLY and not a.tasks
    assert ('DATA_LIMITATION' in d.reasons)==historical


def test_invalid_nonempty_link_consistency_task_high_preserves_original(clean):
    c=candidate(final_defect_id='missing-final');set_candidates(clean,[c]);clean.result.audit_log.lineage_complete=False
    before=clean.result.to_dict();a=evaluate(clean);d=for_candidate(a)
    assert d.bucket==B.MANUAL_REVIEW and d.priority==P.HIGH
    assert {'INVALID_FINAL_LINK','LINEAGE_INCONSISTENT'}<=set(d.reasons)
    task=next(t for t in a.tasks if t.primary_object.kind=='CANDIDATE')
    assert task.task_kind=='CANDIDATE_CONSISTENCY' and task.priority==P.HIGH and task.evidence['final_defect_id']=='missing-final'
    assert c.final_defect_id=='missing-final' and clean.result.to_dict()==before


def test_orphan_task_semantics_distinct_from_consistency(clean):
    a=candidate(cid='orphan');b=candidate(cid='invalid',final_defect_id='invalid');set_candidates(clean,[a,b]);r=evaluate(clean)
    kinds={t.primary_object.candidate_id:t.task_kind for t in r.tasks}
    assert kinds=={'orphan':'ORPHAN_CANDIDATE_REVIEW','invalid':'CANDIDATE_CONSISTENCY'}
    assert next(t for t in r.tasks if t.task_kind=='ORPHAN_CANDIDATE_REVIEW').evidence['final_defect_id'] is None


def test_unresolved_final_selection_low_priority(clean):
    set_candidates(clean,[candidate()]);d=for_candidate(evaluate(clean))
    assert d.bucket==B.MANUAL_REVIEW and d.priority==P.LOW and 'UNRESOLVED_FINAL_SELECTION' in d.reasons


def test_final_normal_and_photometry_optional(clean):
    a=evaluate(clean);assert for_defect(a).bucket==B.AUTO_ACCEPT and clean.defects[0].photometry.mean_gray_dn is None
    b=evaluate(clean,replace(load_policy(),review_when_missing_photometry=True))
    assert for_defect(b).bucket==B.MANUAL_REVIEW and 'MISSING_PHOTOMETRY' in for_defect(b).reasons


@pytest.mark.parametrize('area,feret,expected',[(39,10,True),(1000,15,False),(249,20,True),(30,44,True),(1000,100,False),(20,12,False)])
def test_effective_or_grade_threshold_only(clean,area,feret,expected):
    assert near_threshold(area,feret,load_policy())==expected


def test_near_threshold_defect_manual(clean):
    g=clean.defects[0].geometry;g.area_px=39;g.length_px=10
    d=for_defect(evaluate(clean));assert d.bucket==B.MANUAL_REVIEW and 'NEAR_SIZE_THRESHOLD' in d.reasons


@pytest.mark.parametrize('issue',['missing_geometry','incomplete','reverse','status','source_count','grade_conflict'])
def test_final_safety_rules_protect_all_defects(clean,issue):
    if issue=='missing_geometry':clean.defects[0].geometry.bbox=None
    if issue=='incomplete':clean.result.audit_log.lineage_complete=False
    if issue=='reverse':clean.defects[0].detection.candidate_ids=['nonexistent']
    if issue=='status':clean.defects[0].review=ReviewInfo(review_status=ReviewStatus.UNCERTAIN)
    if issue=='source_count':clean.result.audit_log.source_candidate_count=10
    if issue=='grade_conflict':clean.defects[0].classification.size_grade=SizeGrade.LARGE
    d=for_defect(evaluate(clean));assert d.bucket==B.MANUAL_REVIEW and d.priority==P.HIGH


def test_valid_link_candidate_conflict_aggregates_under_defect(clean):
    fid=clean.defects[0].identity.defect_id;c=candidate(final_defect_id=fid);c.disposition=D.FILTERED;c.filter_reason=F.OUTSIDE_WORK_REGION
    set_candidates(clean,[c]);clean.defects[0].detection.candidate_ids=['C1'];a=evaluate(clean)
    assert for_candidate(a).bucket==B.MANUAL_REVIEW and for_defect(a).bucket==B.MANUAL_REVIEW
    assert len(a.tasks)==1 and a.tasks[0].primary_object.kind=='DEFECT' and a.tasks[0].related_candidates==(('A','C1'),)
    assert 'LINEAGE_INCONSISTENT' in a.tasks[0].reasons


def test_multiple_reasons_and_priorities(clean):
    c=candidate(final_defect_id='missing');c.initial_geometry.area_px=300
    set_candidates(clean,[c,candidate(cid='medium'),candidate(cid='low')]);clean.result.audit_log.candidates[1].initial_geometry.area_px=45
    a=evaluate(clean);assert {t.priority for t in a.tasks}=={P.HIGH,P.MEDIUM,P.LOW}
    assert len(for_candidate(a).reasons)>=2 and list(a.tasks)==sorted(a.tasks,key=lambda t:({P.HIGH:0,P.MEDIUM:1,P.LOW:2}[t.priority],t.primary_object))


def test_policy_hash_deterministic_and_configuration_sensitive():
    a=load_policy();b=ReviewAdmissionConfig(**dict(reversed(list(asdict(a).items()))))
    assert a.policy_hash==b.policy_hash and len(a.policy_hash)==64
    assert replace(a,area_grade_margin_px=a.area_grade_margin_px+1).policy_hash!=a.policy_hash


@pytest.mark.parametrize('changes',[{'area_grade_margin_px':-1},{'candidate_risk_area_px':float('nan')},{'preferred_max_per_result':True},{'candidate_high_area_px':1},{'review_when_missing_photometry':'yes'}])
def test_invalid_policy_fails_closed(changes):
    with pytest.raises(ValueError):ReviewAdmissionConfig(**changes)


def test_deterministic_input_order_and_zero_writeback(clean):
    set_candidates(clean,[candidate(cid='B'),candidate(cid='A')]);before=clean.result.to_dict();a=evaluate(clean);b=evaluate(clean)
    assert a==b and clean.result.to_dict()==before
    clean.result.audit_log.candidates.reverse();c=evaluate(clean)
    assert a.decisions==c.decisions and a.tasks==c.tasks and dict(a.summary)==dict(c.summary)
    with pytest.raises(TypeError):a.decisions[0].evidence['area_px']=5


@pytest.mark.parametrize('zero',['candidates','defects','both'])
def test_zero_states(clean,zero):
    if zero in ('defects','both'):clean.result.defects=[]
    if zero=='defects':set_candidates(clean,[candidate()])
    a=evaluate(clean);assert a.summary['decision_count']==len(clean.result.defects)+len(clean.result.audit_log.candidates)
    if zero in ('candidates','both'):assert a.summary['manual_review_task_count']==0 and a.summary['audit_review_to_manual_task_compression_ratio'] is None


def test_preferred_target_is_advisory_never_truncates(clean):
    set_candidates(clean,[candidate(cid=f'{i:03}') for i in range(60)]);a=evaluate(clean)
    assert len(a.tasks)==60 and not a.summary['preferred_max_met'] and any('TARGET_NOT_MET' in x for x in a.warnings)
    assert len(evaluate(clean,replace(load_policy(),preferred_max_per_result=2)).tasks)==60


def test_50000_no_images_or_domain_mutation(clean):
    rows=[candidate(cid=f'{i:05}',extensions={'reference_decision':'MICRO_REVIEW_NOT_PROVEN_NOISE'}) for i in range(50000)]
    set_candidates(clean,rows);before=clean.result.to_dict();cfg=load_policy()
    with patch('builtins.open',side_effect=AssertionError('image/file read forbidden')):
        started=time.perf_counter();a=evaluate(clean,cfg);elapsed=time.perf_counter()-started
    assert len(a.decisions)==50001 and not a.tasks and elapsed<15
    assert clean.result.to_dict()==before


def test_fifth_tab_and_readonly_empty(window):
    assert window.tabs.count()==5 and window.tabs.tabText(4)=='人工复核'
    p=window.admission_page;assert '尚未执行人工审核' in p.heading.text() and p.model.rowCount()==0
    assert not p.jump.isEnabled() and '暂无检测结果' in p.summary.text()


@pytest.fixture
def queue_fixture(clean):
    rows=[candidate(cid='orphan'),candidate(cid='invalid',final_defect_id='missing'),candidate(cid='archived'),candidate(cid='excluded')]
    rows[2].current_stage='HISTORICAL_ARCHIVE_NOT_RESCANNED';rows[3].disposition=D.FILTERED;rows[3].filter_reason=F.OUTSIDE_WORK_REGION
    set_candidates(clean,rows);clean.defects[0].geometry.area_px=39;clean.defects[0].geometry.length_px=10
    return clean


def test_manual_queue_and_dual_counts(window,queue_fixture,qapp):
    p=show(window,queue_fixture,qapp)
    assert p.view.currentData()=='TASKS' and len(p.model.rows)==3
    assert 'Audit REVIEW 候选：3' in p.summary.text() and '人工待复核任务：3' in p.summary.text()
    assert all(isinstance(row,ReviewTask) for row in p.model.rows)
    assert p.model.row(0).priority==P.HIGH


@pytest.mark.parametrize('name,value,expected',[('kind','DEFECT',1),('priority','HIGH',1),('reason','INVALID_FINAL_LINK',1),('band','—',3),('source','A',2)])
def test_queue_filters(window,queue_fixture,qapp,name,value,expected):
    p=show(window,queue_fixture,qapp);p.filters[name].setCurrentIndex(p.filters[name].findData(value));settled(window,qapp)
    assert len(p.model.rows)==expected
    p.clear_filters();settled(window,qapp);assert len(p.model.rows)==3


@pytest.mark.parametrize('column',[2,3,5,6,7])
def test_global_queue_sort(window,queue_fixture,qapp,column):
    p=show(window,queue_fixture,qapp);p.sort(column,False);settled(window,qapp);asc=p.model.rows
    p.sort(column,True);settled(window,qapp);assert p.model.rows==tuple(reversed(asc))


def test_task_selection_consistency_and_jump_to_audit(window,queue_fixture,qapp):
    p=show(window,queue_fixture,qapp);row=next(row for row in p.model.rows if row.task_kind=='CANDIDATE_CONSISTENCY')
    p.select_row(row);settled(window,qapp)
    assert 'CANDIDATE_CONSISTENCY' in p.details.toPlainText() and 'missing' in p.details.toPlainText()
    p.jump.click();wait(qapp,lambda:not window.controller.busy and window.audit_page.audit is not None and not window.audit_page.query_pending)
    assert window.tabs.currentIndex()==3 and window.audit_page.selection.candidate_key==('A','invalid')
    assert '不存在' in window.audit_page.detail_warning.text()


def test_task_jump_to_defect(window,queue_fixture,qapp):
    p=show(window,queue_fixture,qapp);row=next(row for row in p.model.rows if object_key(row).kind=='DEFECT')
    p.select_row(row);settled(window,qapp);p.jump.click();settled(window,qapp)
    assert window.tabs.currentIndex()==1 and window.selection.defect_id==queue_fixture.defects[0].identity.defect_id


@pytest.mark.parametrize('bucket,expected',[(B.AUDIT_ONLY,1),(B.AUTO_REJECT,1),(B.AUTO_ACCEPT,0),(B.MANUAL_REVIEW,3)])
def test_all_buckets_remain_browsable(window,queue_fixture,qapp,bucket,expected):
    p=show(window,queue_fixture,qapp);p.view.setCurrentIndex(p.view.findData(bucket.value));settled(window,qapp)
    assert len(p.model.rows)==expected and all(row.bucket==bucket for row in p.model.rows)


def test_stale_images_and_inactive_no_crop(window,queue_fixture,qapp):
    from ui.models.candidate_detail_view_model import CandidateDetailViewModel
    p=show(window,queue_fixture,qapp);row=next(row for row in p.model.rows if object_key(row).kind=='CANDIDATE')
    window.tabs.setCurrentIndex(0)
    with patch.object(CandidateDetailViewModel,'local_view',side_effect=AssertionError('inactive crop')):
        p.select_row(row);settled(window,qapp)
    old=p.image_key();p.image_revision+=1;p.completed('admission_frame',(old,CandidateDetailViewModel.empty('STALE')))
    assert 'STALE' not in p.image_status.text()
    epoch=p.epoch;p.set_result(None);p.completed('admission_result',(epoch,ReviewQueueViewModel(evaluate(queue_fixture))))
    assert p.queue_vm is None


def test_filter_excluding_selected_task_clears_stale_detail(window,queue_fixture,qapp):
    p=show(window,queue_fixture,qapp);p.select_row(p.model.rows[0]);settled(window,qapp)
    p.filters['kind'].setCurrentIndex(p.filters['kind'].findData('DEFECT'));settled(window,qapp)
    assert p.selected_key is None and not p.details.toPlainText() and not p.jump.isEnabled()


def test_50000_worker_heartbeat_without_bulk_images(window,clean,qapp):
    from ui.models.candidate_detail_view_model import CandidateDetailViewModel
    g=DefectGeometry(bbox=BoundingBox(20,20,24,25),area_px=20,length_px=5)
    rows=[CandidateAuditRecord(candidate_id=f'C{i:05}',source='S',initial_geometry=g,current_stage='HISTORICAL_ARCHIVE_NOT_RESCANNED',disposition=D.REVIEW) for i in range(50000)]
    set_candidates(clean,rows);ticks=[];timer=QTimer();timer.setInterval(2);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    with patch.object(CandidateDetailViewModel,'local_view',side_effect=AssertionError('bulk image read')):
        p=show(window,clean,qapp)
        p.view.setCurrentIndex(p.view.findData(B.AUDIT_ONLY.value));settled(window,qapp)
    timer.stop();assert ticks and p.model.rowCount()==500 and p.model.pages==100
    p.change_page(99);assert p.model.page==99 and p.model.rowCount()==500


@pytest.mark.golden
@pytest.mark.parametrize('rid',['8a363da8-7a3b-4c77-84cf-d13a375c3b15','f15a42a0-c022-47eb-93d8-d0d191939589'])
def test_real_admission_all_objects_protected_and_no_mutation(qapp,rid):
    from infrastructure.repositories import JsonResultRepository
    from regression.golden import no_engine_execution
    root=Path(__file__).resolve().parents[1]/'output/phase4_validation/repository'
    with no_engine_execution(),patch('core.detector.Detector.inspect',side_effect=AssertionError('algorithm forbidden')):
        result=JsonResultRepository(root).load(rid,verify='full');before=result.to_dict();a=ReviewAdmissionEngine().evaluate(result,load_policy())
        assert before==result.to_dict()
        finals=[d for d in a.decisions if d.object_key.kind=='DEFECT'];candidates=[d for d in a.decisions if d.object_key.kind=='CANDIDATE']
        assert len(finals)==len(result.defects) and len(candidates)==len(result.audit_log.candidates)
        assert all(d.bucket in (B.AUTO_ACCEPT,B.MANUAL_REVIEW) for d in finals)
        assert {d.object_key.defect_id for d in finals}=={d.identity.defect_id for d in result.defects}
        assert len({t.task_key for t in a.tasks})==len(a.tasks)
        assert a.summary['manual_review_task_count']==len(a.tasks)
        assert a.summary['audit_review_count']==sum(c.disposition==D.REVIEW for c in result.audit_log.candidates)
        manual={t.primary_object for t in a.tasks}
        for c in candidates:
            if c.bucket==B.MANUAL_REVIEW:
                fid=c.evidence['final_defect_id']
                assert c.object_key in manual if fid is None or 'INVALID_FINAL_LINK' in c.reasons else ReviewObjectKey('DEFECT',defect_id=fid) in manual
        confirmed={d.identity.defect_id for d in result.defects if d.review.review_status==ReviewStatus.CONFIRMED}
        assert confirmed<={d.object_key.defect_id for d in finals}
        if not a.summary['preferred_max_met']:assert any('TARGET_NOT_MET' in x for x in a.warnings)
