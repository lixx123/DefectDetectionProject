"""Phase10 synthetic-only review execution tests; never label formal samples."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import json
import time
import pytest
from PySide6.QtGui import QCursor
from test_phase6_ui import qapp,window,vm,wait,image_frame
from test_phase9_admission import candidate,set_candidates
from domain.audit import AuditInfo
from ui.models.review_admission import ReviewAdmissionEngine,load_policy
from ui.models.human_review import *
from ui.models.human_review.model import allowed_decisions,digest,canonical,now,POLICY_HASH,source_payload
from ui.models.human_review.service import make_guard

@pytest.fixture(autouse=True)
def protocol_unit_isolation(request,monkeypatch):
    # Preserve earlier protocol/revision unit coverage independently of the new
    # live evidence prerequisites. Revision end-to-end tests never use this mock.
    if request.node.get_closest_marker('golden'):return
    from ui.models.human_review.evidence import ReviewAccess,ReviewEligibility
    monkeypatch.setattr(HumanReviewRepository,'_require_access',staticmethod(lambda *a,**k:None))
    monkeypatch.setattr(ReviewAccess,'eligibility',lambda self,context=None,stale=None:ReviewEligibility(True,not stale,True,True,not stale,not stale,'PROTOCOL_UNIT_FIXTURE'))

@pytest.fixture(autouse=True)
def cursor(qapp):
    QCursor.setPos(0,0);yield;QCursor.setPos(0,0);qapp.processEvents()

@pytest.fixture
def context(vm):
    vm.result.defects[0].geometry.area_px=39
    set_candidates(vm,[candidate('C1','A'),candidate('C1','B',final_defect_id='INVALID')])
    return ReviewContext.from_result(vm.result,ReviewAdmissionEngine().evaluate(vm.result,load_policy()))

@pytest.fixture
def repo(tmp_path):return HumanReviewRepository(tmp_path/'reviews')

@pytest.fixture
def state(repo,context):return repo.create(context,'合成审核者甲')


def cand(context):return next(t for t in context.tasks if t['object_kind']=='CANDIDATE')
def defect(context):return next(t for t in context.tasks if t['object_kind']=='DEFECT')
def submit(repo,context,state,task=None,decision='UNCERTAIN',**kwargs):
    t=task or cand(context);previous=latest(state).get(t['task_key'])
    args=dict(selected_task_key=t['task_key'],expected_revision=previous['revision'] if previous else 0,
              acknowledge_special=True);args.update(kwargs)
    return repo.submit(context,state['session_id'],t['task_key'],decision,'合成审核者甲',**args)

@pytest.mark.parametrize('decision',list(HumanReviewDecision))
def test_five_candidate_decisions(repo,context,state,decision,vm):
    before=deepcopy(source_payload(vm.result));t=cand(context)
    result=submit(repo,context,state,t,decision,target_defect_id=context.final_ids[0] if decision.name.startswith('DUPLICATE') else None)
    record=result['records'][0]
    assert record['decision']==decision and record['revision']==1 and record['geometry_evidence']==t['geometry']
    assert record['object_key'][2] in ('A','B') and record['object_key'][3]=='C1'
    assert source_payload(vm.result)==before

@pytest.mark.parametrize('decision',list(HumanReviewDecision))
def test_defect_allowed(repo,context,state,decision):
    t=defect(context)
    if decision.name=='NEW_MISSED_DEFECT' or decision.name.startswith('DUPLICATE'):
        with pytest.raises(ReviewError):submit(repo,context,state,t,decision,target_defect_id=t['object_id'] if decision.name.startswith('DUPLICATE') else None)
    else:assert submit(repo,context,state,t,decision)['records'][-1]['decision']==decision

@pytest.mark.parametrize('decision,target',[('BOGUS',None),('DUPLICATE_OF_EXISTING_DEFECT',None),('DUPLICATE_OF_EXISTING_DEFECT','missing'),('UNCERTAIN','missing')])
def test_invalid_decision_target_rejected(repo,context,state,decision,target):
    with pytest.raises(ReviewError):submit(repo,context,state,decision=decision,target_defect_id=target)
    assert not repo.load(context.result_id)['records']

@pytest.mark.parametrize('decision',['DUPLICATE_OF_EXISTING_DEFECT','NEW_MISSED_DEFECT'])
def test_special_requires_explicit_ack(repo,context,state,decision):
    with pytest.raises(ReviewError,match='确认'):submit(repo,context,state,decision=decision,target_defect_id=context.final_ids[0] if decision.startswith('DUPLICATE') else None,acknowledge_special=False)


def test_identity_and_source_and_immutable_snapshot(context):
    a,b=[t for t in context.tasks if t['object_kind']=='CANDIDATE'];assert a['task_key']!=b['task_key']
    tasks=context.tasks;tasks.clear();assert len(context.tasks)==3
    assert len(allowed_decisions('DEFECT'))==4 and len(allowed_decisions('CANDIDATE'))==5
    assert any(t['task_kind']=='CANDIDATE_CONSISTENCY' and t['evidence']['final_defect_id']=='INVALID' for t in context.tasks)


def test_revision_history_latest_and_uncertain(repo,context,state):
    a=submit(repo,context,state);b=submit(repo,context,a,decision='CONFIRMED_DEFECT')
    assert len(b['records'])==2 and b['records'][0]['decision']=='UNCERTAIN'
    assert b['records'][0]['review_record_id']!=b['records'][1]['review_record_id']
    assert latest(b)[cand(context)['task_key']]['revision']==2
    assert b['events'][-1]['event']=='REVISE_REVIEW'
    assert repo.load(context.result_id)==b
    assert not hasattr(repo,'delete')


def test_record_bindings_and_timestamp(repo,context,state):
    r=submit(repo,context,state)['records'][0]
    for key in ('result_id','source_result_digest','task_digest','policy_id','policy_version','policy_hash'):assert r[key]==getattr(context,key)
    assert r['review_task_key']==cand(context)['task_key'] and r['comment'] is None
    assert r['reviewed_at'].endswith('+00:00')

@pytest.mark.parametrize('name',['','  ',None])
def test_reviewer_required(repo,context,name):
    with pytest.raises(ReviewError):repo.create(context,name)


def test_other_reviewer_and_optimistic_revision(repo,context,state):
    state=submit(repo,context,state);t=cand(context)
    with pytest.raises(ReviewConflict,match='另一'):repo.submit(context,state['session_id'],t['task_key'],'FALSE_POSITIVE','乙',selected_task_key=t['task_key'],expected_revision=1)
    b=repo.submit(context,state['session_id'],t['task_key'],'FALSE_POSITIVE','乙',selected_task_key=t['task_key'],expected_revision=1,acknowledge_previous_reviewer=True)
    assert [r['reviewer'] for r in b['records']]==['合成审核者甲','乙']
    with pytest.raises(ReviewConflict,match='revision'):submit(repo,context,state)


def test_selected_task_identity_guard(repo,context,state):
    with pytest.raises(ReviewConflict,match='identity'):submit(repo,context,state,selected_task_key='wrong')
    assert not repo.load(context.result_id)['records']

@pytest.mark.parametrize('field,value,expected',[('source_result_digest','0'*64,'RESULT_MISMATCH'),('policy_hash','1'*64,'POLICY_MISMATCH'),('policy_version','9','POLICY_MISMATCH'),('tasks_json','[]','STALE')])
def test_mismatch_readonly(repo,context,state,field,value,expected):
    changed=replace(context,**{field:value});assert mismatch(state,changed)==expected
    with pytest.raises(ReviewConflict,match=expected):submit(repo,changed,state,task=cand(context))
    assert summary(state,expected)['completed']==0 and all(task_status(t,latest(state),expected)=='STALE' for t in state['tasks'])


def test_new_session_retains_old_and_blocks_old_submit(repo,context,state):
    state=submit(repo,context,state);second=repo.create(context,'乙',new_session=True)
    assert second['session_id']!=state['session_id'] and not second['records']
    assert repo.load(context.result_id,state['session_id'])==state
    with pytest.raises(ReviewConflict,match='active'):submit(repo,context,state)


def test_progress_complete_uncertain_breakdowns(repo,context,state):
    assert summary(state)['pending']==3
    for task in context.tasks:state=submit(repo,context,state,task)
    s=summary(state)
    assert s['completed']==s['uncertain']==3 and s['percent']==100 and s['pending']==0
    assert state['events'][-1]['event']=='COMPLETE_SESSION'
    assert s['by_dimension']['object_kind']['CANDIDATE']['UNCERTAIN']==2
    assert 'priority' in s['by_dimension'] and 'source' in s['by_dimension'] and 'band' in s['by_dimension']

@pytest.mark.parametrize('filters',[{'status':'PENDING'},{'status':'UNCERTAIN'},{'status':'REVIEWED'},{'decision':'FALSE_POSITIVE'},{'priority':'HIGH'},{'source':'B'},{'reason':'INVALID_FINAL_LINK'},{'object_kind':'DEFECT'}])
def test_global_filters(repo,context,state,filters):
    state=submit(repo,context,state,decision='FALSE_POSITIVE');records=latest(state)
    rows=query_tasks(context.tasks,records,filters=filters)
    for t in rows:
        key,value=next(iter(filters.items()))
        if key=='status':assert task_status(t,records)==value
        elif key=='decision':assert records[t['task_key']]['decision']==value
        elif key=='reason':assert value in t['reasons']
        else:assert t[key]==value

@pytest.mark.parametrize('sort',['priority','status','area','id','reason'])
def test_sorting(context,sort):
    a=query_tasks(context.tasks,{},sort=sort);assert len(a)==3
    assert query_tasks(context.tasks,{},sort=sort,descending=True)==list(reversed(a))
    same=[dict(t,priority='HIGH') for t in context.tasks]
    assert query_tasks(same,{},sort='priority')[0]['object_kind']=='DEFECT'

@pytest.mark.parametrize('failure',['replace','fsync'])
def test_atomic_failure_previous_valid(repo,context,state,failure):
    with patch('ui.models.human_review.repository.os.'+failure,side_effect=OSError('synthetic disk failure')):
        with pytest.raises(OSError):submit(repo,context,state)
    assert repo.load(context.result_id)==state
    assert not list((repo.root/context.result_id).glob('*.tmp'))

@pytest.mark.parametrize('field,value',[('decision','illegal'),('reviewed_at','2026-01-01T00:00:00'),('revision',2),('reviewer',''),('policy_hash','0'*64),('target_defect_id','missing')])
def test_semantic_corruption_even_rechecksummed(repo,context,state,field,value):
    state=submit(repo,context,state);state['records'][0][field]=value
    path=repo.root/context.result_id/(state['session_id']+'.json')
    path.write_text(canonical(dict(state=state,checksum=digest(state))),encoding='utf-8')
    with pytest.raises(ReviewError):repo.load(context.result_id)


def test_checksum_and_bad_json_detection(repo,context,state):
    path=repo.root/context.result_id/(state['session_id']+'.json');path.write_text('{broken',encoding='utf-8')
    with pytest.raises(ReviewError):repo.load(context.result_id)
    repo._write(state);value=json.loads(path.read_text());value['state']['reviewer']='changed';path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ReviewError,match='校验'):repo.load(context.result_id)

@pytest.mark.parametrize('text',['Z:/private/image.raw','X:\\work\\image.raw','/private/image.raw'])
def test_no_machine_paths(repo,context,state,text):
    with pytest.raises(ValueError):submit(repo,context,state,comment=text)
    assert not repo.load(context.result_id)['records']

@pytest.mark.parametrize('bad_id',['../escape','a/b','..','x:y'])
def test_safe_result_id(repo,context,bad_id):
    with pytest.raises(ReviewError):repo.create(replace(context,result_id=bad_id),'甲')


def test_export_independent_minimal(repo,context,state,tmp_path):
    state=submit(repo,context,state,comment='=synthetic formula');original=deepcopy(state)
    for fmt in ('json','csv'):repo.export(state,tmp_path/('export.'+fmt),fmt)
    assert json.loads((tmp_path/'export.json').read_text(encoding='utf-8'))['state']==state
    assert "'=synthetic formula" in (tmp_path/'export.csv').read_text(encoding='utf-8-sig')
    assert state==original


def test_source_file_and_live_policy_guard(context,tmp_path):
    path=tmp_path/'result.json';path.write_text('synthetic result');guard=make_guard(tmp_path,context);guard()
    path.write_text('modified')
    with pytest.raises(ReviewConflict,match='RESULT_MISMATCH'):guard()
    path.write_text('synthetic result')
    with patch('ui.models.human_review.service.load_policy',return_value=replace(load_policy(),preferred_max_per_result=51)):
        with pytest.raises(ReviewConflict,match='POLICY_MISMATCH'):guard()


def show_human(window,vm,qapp):
    window.display_result(vm,image_frame());window.tabs.setCurrentIndex(4)
    wait(qapp,lambda:not window.controller.busy and window.human_review_page.admission is not None and not window.admission_page.query_pending)
    return window.human_review_page


def settle(window,qapp):wait(qapp,lambda:not window.controller.busy and not window.human_review_page.image_pending and not window.admission_page.query_pending)


def test_ui_workspace_and_save_next_restore(window,vm,context,qapp):
    p=show_human(window,vm,qapp);assert window.tabs.count()==5 and window.review_workspace.count()==2
    assert p.model.rowCount()==3 and all(p.model.data(p.model.index(i,0))=='PENDING' for i in range(3))
    p.open_session();assert '审核者' in p.message.text() and p.state is None
    p.reviewer.setText('Synthetic UI Reviewer');p.open_session();settle(window,qapp)
    key=p.selected_task_key;assert p.decision.currentData() is None
    p.decision.setCurrentIndex(p.decision.findData('UNCERTAIN'));p.save_next();settle(window,qapp)
    assert len(p.state['records'])==1 and p.state['records'][0]['review_task_key']==key
    assert p.selected_task_key!=key and summary(p.state)['completed']==1
    p.set_result(vm);p.bind_admission();settle(window,qapp)
    assert len(p.state['records'])==1 and task_status(p.current_task(),latest(p.state))=='PENDING'


def test_ui_invalid_link_jump_and_defect_jump(window,vm,context,qapp):
    p=show_human(window,vm,qapp)
    ci=next(i for i,t in enumerate(p.model.rows) if t['task_kind']=='CANDIDATE_CONSISTENCY')
    p.table.setCurrentIndex(p.model.index(ci,0));settle(window,qapp);p.jump_selected();settle(window,qapp)
    assert window.tabs.currentIndex()==3
    window.tabs.setCurrentIndex(4);settle(window,qapp)
    di=next(i for i,t in enumerate(p.model.rows) if t['object_kind']=='DEFECT')
    p.table.setCurrentIndex(p.model.index(di,0));settle(window,qapp);p.jump_selected();settle(window,qapp)
    assert window.tabs.currentIndex()==1 and window.selection.defect_id==context.final_ids[0]


def test_ui_selected_identity_and_stale_frame(window,vm,context,qapp):
    p=show_human(window,vm,qapp);p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp)
    p.decision.setCurrentIndex(p.decision.findData('UNCERTAIN'));p.form_task_key='old task';p.save_next()
    assert not p.state['records'] and '身份' in p.message.text()
    p.viewer.clear();p.completed('human_image',((p.epoch,'old task',p.image_revision),__import__('ui.models.candidate_detail_view_model',fromlist=['CandidateDetailViewModel']).CandidateDetailViewModel.empty('STALE')))
    assert p.viewer.frame is None if hasattr(p.viewer,'frame') else p.viewer.scene().items()==[]
    p.stale='RESULT_MISMATCH';p.refresh();assert not p.save.isEnabled() and p.viewer.base_item is None


def test_spatial_reason_and_duplicate_statistics(repo,context,state):
    tasks=context.tasks;t=next(t for t in tasks if t['object_kind']=='CANDIDATE');t['reasons'].append('SPATIAL_FINAL_ASSOCIATION');t['evidence']['spatial_final_ids']=list(context.final_ids)
    c=replace(context,tasks_json=canonical(tasks));s=repo.create(c,'Synthetic',new_session=True)
    s=submit(repo,c,s,task=t,decision='DUPLICATE_OF_EXISTING_DEFECT',target_defect_id=c.final_ids[0])
    breakdown=summary(s)['by_dimension']['reason']['SPATIAL_FINAL_ASSOCIATION']
    assert breakdown['total']==breakdown['DUPLICATE_OF_EXISTING_DEFECT']==1


def test_thousand_record_projection_append_load_summary(repo,context):
    tasks=[]
    original=cand(context)
    for i in range(1000):
        t=deepcopy(original);t['task_key']='synthetic-'+str(i);t['object_key'][3]=t['object_id']=str(i);tasks.append(t)
    c=replace(context,tasks_json=canonical(tasks));state=repo.create(c,'Synthetic load fixture')
    # Build a synthetic protocol fixture efficiently; validate it before persistence.
    from ui.models.human_review.model import HumanReviewRecord
    for t in tasks:
        state['records'].append(HumanReviewRecord(str(uuid4()),c.result_id,t['task_key'],t['object_kind'],tuple(t['object_key']),
          'UNCERTAIN',None,'Synthetic',now(),None,c.policy_id,c.policy_version,c.policy_hash,c.source_result_digest,c.task_digest,1,canonical(t['geometry'])).to_dict())
    repo._write(state);start=time.perf_counter();loaded=repo.load(c.result_id);projected=latest(loaded);s=summary(loaded)
    assert len(projected)==s['completed']==1000
    revised=submit(repo,c,loaded,tasks[0],decision='FALSE_POSITIVE',acknowledge_previous_reviewer=True)
    assert len(revised['records'])==1001 and latest(revised)[tasks[0]['task_key']]['revision']==2
    assert time.perf_counter()-start<20



@pytest.mark.parametrize('decision',list(HumanReviewDecision))
def test_ui_submit_each_decision_and_revision(window,vm,context,qapp,decision):
    p=show_human(window,vm,qapp);p.reviewer.setText('Synthetic operator');p.open_session();settle(window,qapp)
    index=next(i for i,t in enumerate(p.model.rows) if t['object_kind']=='CANDIDATE')
    p.table.setCurrentIndex(p.model.index(index,0));settle(window,qapp);key=p.selected_task_key
    p.decision.setCurrentIndex(p.decision.findData(decision.value))
    if decision.name.startswith('DUPLICATE'):p.target.setCurrentIndex(p.target.findData(context.final_ids[0]))
    p.special.setChecked(True);p.save_next();settle(window,qapp)
    assert latest(p.state)[key]['decision']==decision
    index=next(i for i,t in enumerate(p.model.rows) if t['task_key']==key);p.table.setCurrentIndex(p.model.index(index,0));settle(window,qapp)
    p.decision.setCurrentIndex(p.decision.findData('CONFIRMED_DEFECT'));p.save_next();settle(window,qapp)
    assert latest(p.state)[key]['revision']==2 and len(p.state['records'])==2


def test_ui_duplicate_target_jump(window,vm,context,qapp):
    p=show_human(window,vm,qapp);p.target.setCurrentIndex(p.target.findData(context.final_ids[0]));p.jump_final(p.target.currentData());settle(window,qapp)
    assert window.tabs.currentIndex()==1 and window.selection.defect_id==context.final_ids[0]


def test_ui_save_locks_navigation_and_stale_context(window,vm,context,qapp):
    import threading
    p=show_human(window,vm,qapp);p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp)
    key=p.selected_task_key;p.decision.setCurrentIndex(p.decision.findData('UNCERTAIN'))
    entered=threading.Event();release=threading.Event();original=p.repository.submit
    def slow(*args,**kwargs):entered.set();release.wait(5);return original(*args,**kwargs)
    try:
        with patch.object(p.repository,'submit',side_effect=slow):
            p.save_next();wait(qapp,entered.is_set)
            assert not p.table.isEnabled() and not p.decision.isEnabled()
            p.selected_task_key='wrong'
            release.set();settle(window,qapp)
    finally:release.set()
    # Selection was captured and validated before dispatch. The recorded key never
    # follows a later programmatic selection; users cannot navigate during save.
    assert all(r['review_task_key']==key for r in p.repository.load(context.result_id)['records'])


def test_raw_crop_reuses_provider_and_geometry_unchanged(vm,context,tmp_path):
    import numpy as np
    from ui.raw_image_provider import RawImageProvider
    from ui.models.candidate_detail_view_model import CandidateDetailViewModel
    path=tmp_path/'synthetic.raw';np.full((800,1000),2048,dtype='>u2').tofile(path)
    raw=RawImageProvider(path,1000,800);c=vm.result.audit_log.candidates[0];before=deepcopy(source_payload(c))
    try:
        with patch.object(raw,'crop',wraps=raw.crop) as crop:
            small=CandidateDetailViewModel(vm,c).local_view(1,raw,margin=40)
            large=CandidateDetailViewModel(vm,c).local_view(1,raw,margin=120)
            assert crop.call_count==2 and large.frame.width>small.frame.width
            assert 'RAW' in small.source and small.overlays[0].defect_id=='Candidate'
    finally:raw.clear()
    assert source_payload(c)==before


def test_live_in_memory_result_change_blocks_submission(repo,context,state,vm):
    guard=make_guard(vm.package_dir,context,vm.result);vm.result.input_info.file_name='changed'
    with pytest.raises(ReviewConflict,match='RESULT_MISMATCH'):submit(repo,context,state,guard=guard)
    assert not repo.load(context.result_id)['records']


def test_valid_source_snapshot_equals_frozen_serializer(vm):
    vm.result.audit_log=AuditInfo(source_candidate_count=0,lineage_complete=True)
    assert source_payload(vm.result)==vm.result.to_dict()


def test_duplicate_defect_other_target_accepted(repo,context):
    context=replace(context,final_ids=(*context.final_ids,'second-final'))
    state=repo.create(context,'Synthetic')
    result=submit(repo,context,state,defect(context),'DUPLICATE_OF_EXISTING_DEFECT',target_defect_id='second-final')
    assert result['records'][0]['target_defect_id']=='second-final'


@pytest.mark.golden
@pytest.mark.parametrize('rid,count',[('8a363da8-7a3b-4c77-84cf-d13a375c3b15',83),('f15a42a0-c022-47eb-93d8-d0d191939589',49)])
def test_real_sessions_pending_only_no_labels(qapp,tmp_path,rid,count):
    from infrastructure.repositories import JsonResultRepository
    from regression.golden import no_engine_execution
    root=Path(__file__).resolve().parents[1]/'output/phase4_validation/repository'
    with no_engine_execution(),patch.object(HumanReviewRepository,'submit',side_effect=AssertionError('real submissions forbidden')):
        from ui.models.human_review.evidence import FormalResultAuthority,ReviewAccess
        result,binding=FormalResultAuthority(JsonResultRepository(root)).load(rid);before=digest(result.to_dict())
        admission=ReviewAdmissionEngine().evaluate(result,load_policy());context=ReviewContext.from_result(result,admission,ReviewAccess(binding))
        repo=HumanReviewRepository(tmp_path/'pending-only');state=repo.create(context,'QA_PENDING_ONLY')
        assert len(context.tasks)==count and summary(state)['pending']==count and not state['records']
        assert repo.load(rid)==state and context.policy_hash==POLICY_HASH
        assert all(task_status(t,{})=='PENDING' for t in state['tasks'])
        assert digest(result.to_dict())==before



def test_snapshot_target_ids_bound_to_current_result(repo,context,state):
    changed=replace(context,final_ids=(*context.final_ids,'not-in-snapshot'))
    assert mismatch(state,changed)=='RESULT_MISMATCH'
    with pytest.raises(ReviewConflict,match='RESULT_MISMATCH'):submit(repo,changed,state)


def test_append_checks_active_revision_across_instances(repo,context,state):
    another=HumanReviewRepository(repo.root);updated=submit(repo,context,state)
    with pytest.raises(ReviewConflict,match='revision'):submit(another,context,state)
    assert another.load(context.result_id)==updated


def test_source_changed_before_session_guard_is_rejected(vm,tmp_path):
    from domain import InspectionResult
    vm.result.audit_log=AuditInfo(source_candidate_count=0,lineage_complete=True)
    original=InspectionResult.from_dict(vm.result.to_dict())
    context=ReviewContext.from_result(original,ReviewAdmissionEngine().evaluate(original,load_policy()))
    path=tmp_path/'result.json';path.write_text(original.to_json(),encoding='utf-8')
    make_guard(tmp_path,context,original)()
    changed=deepcopy(original);changed.input_info.file_name='external modification before session'
    path.write_text(changed.to_json(),encoding='utf-8')
    with pytest.raises(ReviewConflict,match='RESULT_MISMATCH'):make_guard(tmp_path,context,original)

    path.unlink();(tmp_path/'manifest.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ReviewConflict,match='RESULT_MISMATCH'):make_guard(tmp_path,context,original)
