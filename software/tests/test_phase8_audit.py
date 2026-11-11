"""Audit-only QA: synthetic pixels and frozen packages; no detector execution."""
import json
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor,QImage
from PySide6.QtWidgets import QWidget
from test_phase6_ui import qapp,window,vm,wait,image_frame
from domain.audit import AuditInfo,CandidateAuditRecord
from domain.defect import DefectGeometry
from domain.common import BoundingBox,Point,ArtifactReference
from domain.enums import CandidateDisposition as D,FilterReason as F,PipelineMode as M,ExecutionStatus as E,QAStatus as Q,FallbackReason
from domain.execution import ExecutionInfo,ExecutionAttempt
from domain.serialization import to_dict
from ui.models.audit_view_model import AuditViewModel,AuditQuery,key
from ui.models.candidate_audit_table_model import CandidateAuditTableModel,CandidateSelectionController
from ui.models.candidate_detail_view_model import CandidateDetailViewModel
from ui.raw_image_provider import RawImageProvider
from ui.models.result_view_model import ResultViewModel
from infrastructure.repositories import JsonResultRepository


@pytest.fixture(autouse=True)
def cursor(qapp):
    QCursor.setPos(0,0)
    yield
    QCursor.setPos(0,0);qapp.processEvents()


@pytest.fixture
def audited(vm):
    fid=vm.defects[0].identity.defect_id
    g=DefectGeometry(bbox=BoundingBox(205,155,210,160),center=Point(207.5,157.5),area_px=3,length_px=2)
    rows=[CandidateAuditRecord(candidate_id='001',source='A',initial_geometry=g,current_stage='FINAL',disposition=D.RETAINED,final_defect_id=fid),
          CandidateAuditRecord(candidate_id='001',source='B',disposition=D.REVIEW),
          CandidateAuditRecord(candidate_id='merge',source='A',initial_geometry=g,current_stage='J5',disposition=D.MERGED,merged_into='001',final_defect_id=fid),
          CandidateAuditRecord(candidate_id='noise',source='B',initial_geometry=g,current_stage='J4',disposition=D.FILTERED,filter_reason=F.BACKGROUND_NOISE,filter_message='原始 decision_reason：真实噪声'),
          CandidateAuditRecord(candidate_id='pending',source='NEW',disposition=D.PENDING),
          CandidateAuditRecord(candidate_id='outside',source='NEW',disposition=D.FILTERED,filter_reason=F.OUTSIDE_WORK_REGION),
          CandidateAuditRecord(candidate_id='unique',source='C',disposition=D.REVIEW),
          CandidateAuditRecord(candidate_id='merge_unique',source='C',disposition=D.MERGED,merged_into='unique')]
    vm.result.audit_log=AuditInfo(candidates=rows,source_candidate_count=len(rows),lineage_complete=True,
        events=[{'arbitrary':{'nested':[1,2]},'stage':'J4'},{'time':'t','type':'guard','message':'SENTINEL_CONSUMED'},{'custom':None}])
    vm.defects[0].detection.candidate_ids=['001','merge']
    return vm


def show(window,audited,qapp):
    window.display_result(audited,image_frame());window.tabs.setCurrentIndex(3)
    wait(qapp,lambda:not window.controller.busy and window.audit_page.audit is not None and not window.audit_page.query_pending)
    return window.audit_page


def settle(window,qapp):
    wait(qapp,lambda:not window.controller.busy and not window.audit_page.query_pending)


def test_fourth_tab_and_empty(window):
    assert window.tabs.count()==5 and window.tabs.tabText(3)=='检测过程 / 审计'
    p=window.audit_page
    assert p.model.rowCount()==0 and '暂无检测结果' in p.execution.text()
    assert '只读' in p.heading.text() and not p.jump_final.isEnabled()


def test_execution_and_fallback(window,audited,qapp):
    reason=next(iter(FallbackReason))
    e=ExecutionInfo(requested_mode=M.AUTO,attempted_mode=M.ROI_BH,final_mode=M.FULL,status=E.SUCCEEDED,
        fallback_used=True,fallback_reason=reason,qa_status=Q.PASS,
        attempts=[ExecutionAttempt(mode=M.ROI_BH,status=E.FAILED,qa_status=Q.FAIL,reason=reason,message='ROI_CONTEXT_INCOMPLETE'),
                  ExecutionAttempt(mode=M.FULL,status=E.SUCCEEDED,qa_status=Q.PASS)])
    audited.result.execution_info=e;p=show(window,audited,qapp)
    assert '请求：auto' in p.execution.text() and '最终：full' in p.execution.text()
    assert '回退：是' in p.execution.text() and str(reason) in p.execution.text()
    text=p.execution.text();assert text.index('1. roi-bh')<text.index('2. full') and 'QA：PASS' in text
    assert 'ROI_CONTEXT_INCOMPLETE' in p.execution_detail.toPlainText() and 'roi_geometry_status' in p.execution_detail.toPlainText()


def test_counts_and_dynamic_groups(audited):
    a=AuditViewModel(audited.result);s=a.summary()
    assert s['candidate_count']==s['source_candidate_count']==8 and s['lineage_complete']
    assert sum(a.dispositions.values())==8 and a.dispositions['PENDING']==1
    assert a.reasons=={'BACKGROUND_NOISE':1,'OUTSIDE_WORK_REGION':1}
    assert a.sources['NEW']==2 and a.stages[None]==5
    assert s['linked_to_final_count']==2 and s['unlinked_count']==6


def test_tuple_identity_and_ambiguous_reverse(audited):
    a=AuditViewModel(audited.result)
    assert a.candidate(('A','001')) is not a.candidate(('B','001'))
    assert a.duplicate_count==0
    assert any('无法唯一反向匹配' in x for x in a.reverse_issues[audited.defects[0].identity.defect_id])
    assert a.merged_target(a.candidate(('A','merge'))) is None
    assert a.merged_target(a.candidate(('C','merge_unique')))==('C','unique')


@pytest.mark.parametrize('field,query,expected',[
 ('disposition',AuditQuery(disposition='FILTERED'),2),('reason',AuditQuery(reason='BACKGROUND_NOISE'),1),
 ('source',AuditQuery(source='B'),2),('stage',AuditQuery(stage='J4'),1),('missing_stage',AuditQuery(stage='—'),5),
 ('linked',AuditQuery(linked=True),2),('unlinked',AuditQuery(linked=False),6),
 ('search',AuditQuery(search='NOiS'),1),('and',AuditQuery(disposition='FILTERED',source='B',stage='J4',linked=False,search='ISE'),1),
 ('empty',AuditQuery(disposition='REVIEW',reason='BACKGROUND_NOISE'),0)])
def test_query_filters(audited,field,query,expected):
    a=AuditViewModel(audited.result);assert len(a.query(query))==expected


@pytest.mark.parametrize('n',[0,1,499,500,501,50000])
def test_page_boundaries(vm,n):
    vm.result.audit_log=AuditInfo(candidates=[CandidateAuditRecord(source='S',candidate_id=f'{i:05}') for i in range(n)],source_candidate_count=n)
    a=AuditViewModel(vm.result);m=CandidateAuditTableModel();m.set_query(a,a.query(AuditQuery()))
    assert m.rowCount()==min(n,500) and m.pages==(n+499)//500
    m.set_page(999);assert m.page==max(0,m.pages-1)
    assert m.rowCount()==(n%500 or min(n,500))


@pytest.mark.parametrize('column',[1,2,3,4,5,7,8,9])
def test_global_sort_and_key(audited,column):
    a=AuditViewModel(audited.result);q=AuditQuery(sort_column=column)
    asc=a.query(q);desc=a.query(replace(q,descending=True))
    assert desc==tuple(reversed(asc))
    m=CandidateAuditTableModel();m.page_size=2;m.set_query(a,desc);m.set_page(1)
    c=a.records[desc[2]];assert m.index(0,0).data(m.KeyRole)==key(c)
    assert all(m.index(0,i).data() is not None for i in range(10))


def test_large_global_filter_sort_pagination(vm):
    vm.result.audit_log=AuditInfo(candidates=[CandidateAuditRecord(candidate_id=f'{50000-i:05}',source=str(i%3),
        disposition=D.FILTERED if i<12345 else D.REVIEW,filter_reason=F.OTHER if i<12345 else None) for i in range(50000)],source_candidate_count=50000,lineage_complete=True)
    a=AuditViewModel(vm.result);indexes=a.query(AuditQuery(disposition='FILTERED'));m=CandidateAuditTableModel();m.set_query(a,indexes)
    assert len(indexes)==12345 and m.pages==25
    assert m.index(0,1).data()=='37656';m.set_page(24);assert m.rowCount()==345
    assert a.records[0] is vm.result.audit_log.candidates[0]
    assert sum(a.dispositions.values())==50000


def test_select_details_and_missing_geometry(window,audited,qapp):
    p=show(window,audited,qapp);p.selection.set(('B','noise'));settle(window,qapp)
    assert p.fields['filter_reason'].text()=='BACKGROUND_NOISE' and 'decision_reason' in p.fields['filter_message'].text()
    assert p.fields['area_px'].text()=='3' and p.fields['bbox（初始测量）'].text()=='[205, 155, 210, 160)'
    assert p.fields['area_um2'].text()=='—' and p.selection.candidate_key==('B','noise')
    p.selection.set(('A','001'));settle(window,qapp);assert p.jump_final.isEnabled()
    p.selection.set(('B','001'));settle(window,qapp)
    assert '无候选初始几何' in p.image_status.text() and p.fields['bbox（初始测量）'].text()=='—'


def test_merged_ambiguity_and_unique_jump(window,audited,qapp):
    p=show(window,audited,qapp);p.selection.set(('A','merge'));settle(window,qapp)
    assert p.fields['merged_into'].text()=='001' and not p.jump_merged.isEnabled()
    assert '目标候选无法唯一解析' in p.detail_warning.text()
    p.selection.set(('C','merge_unique'));settle(window,qapp);p.jump_merged.click();settle(window,qapp)
    assert p.selection.candidate_key==('C','unique')


def test_bidirectional_jump_clears_hidden_final_filter(window,audited,qapp):
    p=show(window,audited,qapp);fid=audited.defects[0].identity.defect_id
    window.proxy.set_filters('LARGE',None,None);assert window.proxy.rowCount()==0
    p.selection.set(('A','001'));settle(window,qapp);p.jump_final.click();settle(window,qapp)
    assert window.tabs.currentIndex()==1 and window.selection.defect_id==fid and window.proxy.rowCount()==1
    window.tabs.setCurrentIndex(3);settle(window,qapp);p.reverse.click();settle(window,qapp)
    assert len(p.model.indexes)==2 and '已存 candidate_ids' in p.lineage.text()
    assert set(p.model.index(i,0).data(p.model.KeyRole) for i in range(2))=={('A','001'),('A','merge')}


def test_invalid_draft_warnings(window,audited,qapp):
    c=audited.result.audit_log.candidates[3];c.filter_reason=None;c.final_defect_id='missing-final'
    audited.result.audit_log.lineage_complete=False;audited.result.audit_log.source_candidate_count=1
    p=show(window,audited,qapp);p.selection.set(key(c));settle(window,qapp)
    assert '不存在' in p.detail_warning.text() and '协议异常' in p.detail_warning.text() and not p.jump_final.isEnabled()
    assert '完整正式审计记录' in p.warning.text() and '实际审计记录数不一致' in p.warning.text()
    assert p.audit.reasons[None]==1 and p.audit.reasons.get('OTHER',0)==0


def test_duplicate_key_fails_closed(audited):
    audited.result.audit_log.candidates.append(audited.result.audit_log.candidates[0])
    a=AuditViewModel(audited.result);assert a.duplicate_count==1 and a.candidate(('A','001')) is None


def test_debounce_clear_size_and_preserved_selection(window,audited,qapp):
    p=show(window,audited,qapp);p.selection.set(('B','noise'));settle(window,qapp)
    before=p.query_revision;p.search.setText('noise');assert p.debounce.isActive() and p.debounce.interval()==200
    assert p.query_revision==before
    wait(qapp,lambda:p.query_revision>before);settle(window,qapp)
    assert len(p.model.indexes)==1 and p.selection.candidate_key==('B','noise')
    p.size.setCurrentText('200');assert p.model.page_size==200 and p.model.page==0
    p.clear_filters();settle(window,qapp);assert len(p.model.indexes)==8


def test_events_generic_and_empty(window,audited,qapp):
    p=show(window,audited,qapp);assert p.event_model.rowCount()==3
    p.event_table.setCurrentIndex(p.event_model.index(0,0));assert 'nested' in p.event_json.toPlainText()
    p.event_table.setCurrentIndex(p.event_model.index(1,0));assert 'SENTINEL_CONSUMED' in p.event_json.toPlainText()
    assert p.event_model.index(2,4).data()=='—'
    p.set_result(None);assert p.event_model.rowCount()==0 and not p.event_json.toPlainText()


def test_inactive_tab_no_image_io(window,audited,qapp):
    p=show(window,audited,qapp);window.tabs.setCurrentIndex(0)
    with patch.object(CandidateDetailViewModel,'local_view',side_effect=AssertionError('inactive image read')):
        p.selection.set(('B','noise'));settle(window,qapp)
    assert p.fields['candidate_id'].text()=='noise'


def test_stale_image_and_query_requests(window,audited,qapp):
    p=show(window,audited,qapp);p.selection.set(('B','noise'));settle(window,qapp)
    old=p.image_key();old_revision=p.query_revision;old_epoch=p.epoch
    local=CandidateDetailViewModel.empty('STALE')
    p.selection.set(('A','001'));p.completed('candidate_frame',(old,local))
    assert 'STALE' not in p.image_status.text()
    p.request_query();p.completed('audit_query',(old_epoch,old_revision,()))
    settle(window,qapp);assert len(p.model.indexes)==8
    p.set_result(None);p.completed('audit_index',(old_epoch,AuditViewModel(audited.result)));assert p.audit is None


def test_fast_switch_real_worker_latest_wins(window,audited,qapp,monkeypatch):
    p=show(window,audited,qapp);original=CandidateDetailViewModel.local_view
    def slow(self,mode,raw=None):
        time.sleep(.03);return original(self,mode,raw)
    monkeypatch.setattr(CandidateDetailViewModel,'local_view',slow)
    p.selection.set(('A','001'));p.selection.set(('B','noise'));p.selection.set(('B','001'))
    settle(window,qapp);assert '无候选初始几何' in p.image_status.text()


def test_candidate_crop_synthetic_raw(audited,tmp_path):
    pixels=np.arange(800*1000,dtype=np.uint16).reshape(800,1000)%4096
    path=tmp_path/'synthetic.raw';pixels.astype('>u2').tofile(path);raw=RawImageProvider(path,width=1000,height=800)
    c=audited.result.audit_log.candidates[0];before=to_dict(c)
    local=CandidateDetailViewModel(audited,c).local_view(2,raw)
    assert local.origin==(165,115) and local.frame.width==85 and local.frame.height==85
    assert local.frame.image.pixelColor(0,0).red()==int(pixels[115,165])*255//4095
    assert [o.defect_id for o in local.overlays]==['Candidate','Final']
    assert local.overlays[0].measurement_bbox==(40,40,45,45)
    assert local.overlays[1].measurement_bbox==(35,35,75,65)
    assert to_dict(c)==before;raw.clear()


@pytest.mark.parametrize('resource',['original_preview','candidate_preview','missing'])
def test_candidate_preview_priority(audited,tmp_path,resource):
    c=audited.result.audit_log.candidates[0]
    if resource!='missing':
        image=QImage(1000,800,QImage.Format.Format_Grayscale8);image.fill(99);assert image.save(str(tmp_path/'preview.png'))
        setattr(audited.result.intermediate_results,resource,ArtifactReference(path='preview.png'))
    local=CandidateDetailViewModel(audited,c).local_view(1)
    assert local.frame.image.pixelColor(0,0).red()==(28 if resource=='missing' else 99)
    if resource=='candidate_preview':assert '候选预览资源' in local.source
    if resource=='missing':assert '中性底图' in local.source


def test_no_candidate_geometry_never_uses_final_bbox(audited):
    c=audited.result.audit_log.candidates[0];c.initial_geometry=None
    local=CandidateDetailViewModel(audited,c).local_view(2)
    assert not local.overlays and '无候选初始几何' in local.source


def test_result_zero_writeback_and_full_stats(window,audited,qapp):
    before=audited.result.to_dict();p=show(window,audited,qapp);summary=deepcopy(p.audit.summary())
    p.filters['disposition'].setCurrentText('FILTERED');settle(window,qapp);p.selection.set(('B','noise'));settle(window,qapp)
    p.model.set_page(99);p.sort(8,True);settle(window,qapp)
    assert p.audit.summary()==summary and audited.result.to_dict()==before


def test_large_ui_background_heartbeat_and_no_images(window,vm,qapp,monkeypatch):
    vm.result.audit_log=AuditInfo(candidates=[CandidateAuditRecord(candidate_id=f'{i:05}',source='S',
        disposition=D.REVIEW) for i in range(50000)],source_candidate_count=50000,lineage_complete=True)
    ticks=[];timer=QTimer();timer.setInterval(1);timer.timeout.connect(lambda:ticks.append(1));timer.start()
    before=len(window.findChildren(QWidget))
    monkeypatch.setattr(CandidateDetailViewModel,'local_view',lambda *args:pytest.fail('bulk image read'))
    p=show(window,vm,qapp)
    assert p.model.rowCount()==500 and p.model.pages==100 and ticks
    assert len(window.findChildren(QWidget))-before<10
    p.change_page(99);assert p.model.page==99
    p.sort(1,True);settle(window,qapp)
    assert p.model.page==0 and p.model.index(0,1).data()=='49999'
    p.size.setCurrentText('1000');assert p.model.rowCount()==1000 and p.model.pages==50
    timer.stop()


def test_selected_candidate_key_survives_sort_and_page(window,audited,qapp):
    p=show(window,audited,qapp);p.selection.set(('B','001'));settle(window,qapp)
    p.sort(2,True);settle(window,qapp);p.size.setCurrentText('200');p.change_page(1)
    assert p.selection.candidate_key==('B','001') and p.fields['source'].text()=='B'


def test_missing_unique_reverse_links_and_retained_reason_excluded(audited):
    audited.defects[0].detection.candidate_ids=['unknown','unique']
    audited.result.audit_log.candidates[0].filter_reason=F.OTHER
    a=AuditViewModel(audited.result);issues=' '.join(a.reverse_issues[audited.defects[0].identity.defect_id])
    assert '不存在' in issues and '关联不一致' in issues and '未声明' in issues
    assert a.reasons.get('OTHER',0)==0


def test_preview_escape_and_hash_checked(audited,tmp_path):
    image=QImage(1000,800,QImage.Format.Format_Grayscale8);image.fill(1);image.save(str(tmp_path/'preview.png'))
    audited.result.intermediate_results.original_preview=ArtifactReference(path='preview.png',sha256='0'*64)
    with pytest.raises(ValueError,match='SHA256'):
        CandidateDetailViewModel(audited,audited.result.audit_log.candidates[0]).local_view(1)


@pytest.mark.golden
@pytest.mark.parametrize('rid',['8a363da8-7a3b-4c77-84cf-d13a375c3b15','f15a42a0-c022-47eb-93d8-d0d191939589'])
def test_formal_audit_readonly_bidirectional(window,qapp,rid):
    root=Path(__file__).resolve().parents[1]/'output/phase4_validation/repository'
    with patch('core.detector.Detector.inspect',side_effect=AssertionError('engine forbidden')):
        result=JsonResultRepository(root).load(rid,verify='full');before=result.to_dict()
        vm=ResultViewModel(result,root/rid);p=show(window,vm,qapp);a=p.audit;s=a.summary()
        assert s['candidate_count']==s['source_candidate_count'] and s['lineage_complete']
        assert sum(a.dispositions.values())==len(a.records)
        assert a.duplicate_count==a.invalid_links==a.ambiguous_targets==0
        assert all(c.filter_reason for c in a.records if c.disposition==D.FILTERED)
        assert all(c.merged_into for c in a.records if c.disposition==D.MERGED)
        # Existing packages store final IDs in merged_into, not candidate IDs.
        # Keep the original strings and explicitly report unresolved candidate links.
        unresolved=[c for c in a.records if c.merged_into and len(a.by_id.get(c.merged_into,()))!=1]
        assert len(unresolved)==a.unresolved_targets
        assert all(c.merged_into==c.final_defect_id and c.final_defect_id in a.final_ids for c in unresolved)
        assert len(a.issues)==len(unresolved) and all('目标候选无法唯一解析' in x for x in a.issues)
        for d in result.defects[:3]:
            fid=d.identity.defect_id;keys=a.candidates_for_final_defect(fid);assert keys
            assert not a.reverse_issues[fid]
            p.selection.set(keys[0]);settle(window,qapp);p.jump_final.click();settle(window,qapp)
            assert window.selection.defect_id==fid and window.tabs.currentIndex()==1
            window.tabs.setCurrentIndex(3);settle(window,qapp);p.reverse.click();settle(window,qapp)
            assert len(p.model.indexes)==len(keys)
        assert result.to_dict()==before and window.raw is None
