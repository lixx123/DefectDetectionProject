"""Real QThread/controller/window tests; only synthetic input and isolated storage."""
import threading,time,json
from pathlib import Path
from unittest.mock import patch
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QSignalSpy
from PySide6.QtGui import QImage
from test_phase6_ui import qapp,window,wait,image_frame
from test_phase10_revision import formal,show,settle
from ui.models.human_review import HumanReviewRepository,ReviewConflict
from ui.models.result_view_model import ResultViewModel
from infrastructure.repositories.errors import PackageIntegrityError

@pytest.mark.parametrize('fail',[False,True])
def test_real_thread_lifecycle_heartbeat_close_and_exclusion(window,qapp,fail):
    import shiboken6
    c=window.controller;ticks=[];ids=[];transitions=[]
    c.busy_changed.connect(lambda busy:transitions.append(busy));timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(5)
    def job():
        ids.append(threading.get_ident());time.sleep(.12)
        if fail:raise RuntimeError('worker failure')
        return 'ok'
    assert c.task_state=='IDLE' and c.submit('fixture',job)
    thread,worker=c.thread,c.worker
    assert c.task_state=='RUNNING' and not c.submit('duplicate',job) and not window.close()
    wait(qapp,lambda:not c.busy);timer.stop()
    wait(qapp,lambda:not shiboken6.isValid(thread) and not shiboken6.isValid(worker))
    assert c.task_state==('FAILED' if fail else 'SUCCEEDED') and c.thread is c.worker is None
    assert len(ticks)>=3 and ids[0]!=threading.get_ident() and transitions==[True,False]
    if not fail:assert window.statusBar().currentMessage()=='操作完成'
    assert window.open_action.isEnabled() and not window.progress.isVisible()

def test_raw_open_failure_retains_old_result(window,qapp,formal):
    vm,path,repo,cfg=formal;window.display_result(vm,image_frame(),saved=True)
    window.open_raw(path.parent/'missing.raw');wait(qapp,lambda:not window.controller.busy)
    assert window.view_model is vm and window.saved
    assert 'RAW_READ_FAILED' in window.resource_status.text()
    assert window.resource_status.text().count('详情见运行日志')==1
    assert window.statusBar().currentMessage().count('详情见运行日志')==1
    assert window.controller.application_log.path.is_file()

def test_corrupt_history_is_rejected(window,qapp,formal):
    vm,path,repo,cfg=formal;c=window.controller
    c.repository=repo
    from ui.models.human_review.evidence import FormalResultAuthority
    c.formal_authority=FormalResultAuthority(repo)
    (vm.package_dir/'result.json').write_text('{}',encoding='utf-8')
    window.load_history(vm.result.result_id);wait(qapp,lambda:not c.busy)
    assert window.view_model is None and not window.saved and not window.human_review_page.start.isEnabled()
    assert 'RESULT_INTEGRITY_FAILED' in window.resource_status.text()

def test_save_failure_does_not_formalize(window,qapp,formal,monkeypatch):
    vm,path,repo,cfg=formal;temp=ResultViewModel(vm.result,vm.package_dir);window.display_result(temp,image_frame(),saved=False)
    def fail(*a,**k):raise OSError('full disk')
    monkeypatch.setattr(window.controller.repository,'save',fail)
    window._request_filter_metadata=lambda:("QA_FILTER", "")
    window._save();wait(qapp,lambda:not window.controller.busy)
    assert window.view_model is temp and not window.saved and not temp.is_formal_result
    assert not window.human_review_page.start.isEnabled() and 'RESULT_SAVE_FAILED' in window.resource_status.text()

def test_raw_mismatch_logged_and_review_conflict_atomic(window,qapp,formal,tmp_path,monkeypatch):
    vm,path,repo,cfg=formal;p=show(window,vm,qapp);p.repository=HumanReviewRepository(tmp_path/'isolated_reviews')
    p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp)
    wrong=path.parent/'wrong.raw';wrong.write_bytes(b'X'*path.stat().st_size)
    p.attach_raw(wrong);settle(window,qapp)
    assert not p.access.raw and not p.save.isEnabled() and not p.state['records'] and 'RAW_MISMATCH' in p.message.text()
    p.attach_raw(path);settle(window,qapp)
    before=json.dumps(p.state,sort_keys=True);persisted=next((p.repository.root/vm.result.result_id).glob('????????-*.json')).read_bytes()
    p.decision.setCurrentIndex(p.decision.findData('UNCERTAIN'))
    def conflict(*a,**k):raise ReviewConflict('revision conflict; reload first')
    monkeypatch.setattr(p.repository,'submit',conflict);p.save_next();settle(window,qapp)
    assert json.dumps(p.state,sort_keys=True)==before and not p.state['records']
    assert next((p.repository.root/vm.result.result_id).glob('????????-*.json')).read_bytes()==persisted
    assert 'REVIEW_CONFLICT' in p.message.text() and p.save.isEnabled()
    text=window.controller.application_log.path.read_text(encoding='utf-8');assert 'RAW_MISMATCH' in text and 'REVIEW_CONFLICT' in text

def test_thumbnail_failure_releases_raw(window,qapp,monkeypatch):
    class BrokenRaw:
        cleared=False
        def __init__(self,path):pass
        def thumbnail(self):raise OSError('read failed')
        def clear(self):BrokenRaw.cleared=True
    monkeypatch.setattr('ui.controllers.inspection_controller.RawImageProvider',BrokenRaw)
    window.open_raw('synthetic.raw');wait(qapp,lambda:not window.controller.busy)
    assert BrokenRaw.cleared and window.raw is None and not window.controller.busy

def test_viewer_crop_background_and_stale_result(window,qapp):
    from ui.models.result_view_model import DisplayFrame
    viewer=window.viewer;threads=[]
    class SlowRaw:
        width=height=100
        def crop(self,*a):threads.append(threading.get_ident());time.sleep(.12);return image_frame().image
        def dn(self,*a):return 1
    raw=SlowRaw();viewer.raw_provider=raw;viewer.detail_enabled=True;viewer.set_frame(DisplayFrame(image_frame().image,100,100));viewer.actual_size();viewer._refresh_raw_detail()
    assert window.controller.busy;viewer.clear()
    wait(qapp,lambda:not window.controller.busy)
    assert threads and all(t!=threading.get_ident() for t in threads) and viewer.detail_item is None

def test_actual_review_write_failure_and_retry(window,qapp,formal,tmp_path,monkeypatch):
    vm,path,repo,cfg=formal;p=show(window,vm,qapp);p.repository=HumanReviewRepository(tmp_path/'isolated_reviews')
    p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp);p.attach_raw(path);settle(window,qapp)
    original=p.repository._atomic;before=json.dumps(p.state,sort_keys=True)
    files={f.name:f.read_bytes() for f in (p.repository.root/vm.result.result_id).glob('*.json')}
    def fail(*a,**k):raise OSError('injected atomic-write failure')
    monkeypatch.setattr(p.repository,'_atomic',fail);p.decision.setCurrentIndex(p.decision.findData('UNCERTAIN'));p.save_next();settle(window,qapp)
    assert json.dumps(p.state,sort_keys=True)==before and not p.state['records'] and p.save.isEnabled()
    assert files=={f.name:f.read_bytes() for f in (p.repository.root/vm.result.result_id).glob('*.json')}
    monkeypatch.setattr(p.repository,'_atomic',original);p.save_next();settle(window,qapp)
    assert len(p.state['records'])==1 and p.state['records'][0]['revision']==1

def test_actual_optimistic_conflict_does_not_append(window,qapp,formal,tmp_path):
    vm,path,repo,cfg=formal;p=show(window,vm,qapp);p.repository=HumanReviewRepository(tmp_path/'isolated_reviews')
    p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp);p.attach_raw(path);settle(window,qapp)
    key=p.selected_task_key
    external=p.repository.submit(p.context,p.state['session_id'],key,'UNCERTAIN','Synthetic',selected_task_key=key,expected_revision=0)
    p.decision.setCurrentIndex(p.decision.findData('UNCERTAIN'));p.save_next();settle(window,qapp)
    assert not p.state['records'] and 'REVIEW_CONFLICT' in p.message.text()
    assert p.repository.load(vm.result.result_id)==external and len(external['records'])==1

def test_detection_failure_has_no_formal_result(window,qapp,monkeypatch):
    c=window.controller
    def fail(repository):raise RuntimeError('synthetic engine failure')
    c.service_factory=fail;c.detect('synthetic.raw');wait(qapp,lambda:not c.busy)
    assert c.task_state=='FAILED' and window.view_model is None and not window.saved
    assert c.repository.list_results()==[] and c.staging.list_results()==[] and window.open_action.isEnabled()
    assert 'DETECTION_FAILED' in window.resource_status.text()

def test_view_resource_failure_is_logged_and_retryable(window,qapp,monkeypatch):
    class Broken:
        def frame(self,*a):raise ValueError('resource hash mismatch')
    window.controller.view(Broken(),'final',None,True);wait(qapp,lambda:not window.controller.busy)
    assert 'VIEW_RESOURCE_FAILED' in window.resource_status.text() and window.view_selector.isEnabled()
    assert 'Traceback' in window.controller.application_log.path.read_text(encoding='utf-8')

def test_export_failure_leaves_state_and_target_unmodified(window,qapp,formal,tmp_path):
    vm,path,repo,cfg=formal;p=show(window,vm,qapp);p.repository=HumanReviewRepository(tmp_path/'isolated_reviews')
    p.reviewer.setText('Synthetic');p.open_session();settle(window,qapp)
    before=json.dumps(p.state,sort_keys=True);target=tmp_path/'not-created/records.json'
    with patch('ui.widgets.human_review_workspace.QFileDialog.getSaveFileName',return_value=(str(target),'JSON')):p.export('json')
    settle(window,qapp)
    assert not target.exists() and json.dumps(p.state,sort_keys=True)==before and 'EXPORT_FAILED' in p.message.text()

def test_late_raw_failure_logs_but_does_not_poison_new_result(window,qapp,formal,tmp_path):
    from test_phase10_revision import synthetic_case
    vm,path,repo,cfg=formal;p=show(window,vm,qapp);started=threading.Event();release=threading.Event()
    def late(*args):started.set();release.wait(5);raise RuntimeError('late private failure')
    try:
        with patch('ui.widgets.human_review_workspace.validate_raw',side_effect=late):
            p.attach_raw(path);wait(qapp,started.is_set)
            other,_,other_path=synthetic_case(tmp_path/'other');window.display_result(ResultViewModel(other,other_path.parent),image_frame(),saved=False)
            release.set();settle(window,qapp)
    finally:release.set()
    assert p.access.raw is None and p.raw_error is None and not p.save.isEnabled()
    assert 'late private failure' not in p.message.text()
    assert 'late private failure' in window.controller.application_log.path.read_text(encoding='utf-8')

def test_gui_completion_callback_error_is_not_silent(window,qapp,monkeypatch):
    def fail(*a,**k):raise RuntimeError('callback diagnostic')
    monkeypatch.setattr(window,'_apply_frame',fail)
    window.controller.submit('frame',image_frame);wait(qapp,lambda:not window.controller.busy)
    assert window.controller.task_state=='FAILED' and 'VIEW_RESOURCE_FAILED' in window.resource_status.text()
    assert 'callback diagnostic' in window.controller.application_log.path.read_text(encoding='utf-8')


def test_save_reload_failure_keeps_vm_temporary_and_published_package_complete(window,qapp,formal,monkeypatch):
    vm,path,repo,cfg=formal;temporary=ResultViewModel(vm.result,vm.package_dir)
    window.display_result(temporary,image_frame(),saved=False)
    def fail(*a,**k):raise PackageIntegrityError('injected post-save reload failure')
    monkeypatch.setattr(window.controller.formal_authority,'load',fail)
    window._request_filter_metadata=lambda:("QA_FILTER", "")
    window._save();wait(qapp,lambda:not window.controller.busy)
    assert window.view_model is temporary and not window.saved and not temporary.is_formal_result
    assert window.controller.repository.verify(vm.result.result_id).status=='PASS'
    assert not window.human_review_page.start.isEnabled()


def test_pointer_does_not_wait_on_raw_lock_during_worker(window,qapp):
    from PySide6.QtTest import QTest
    from ui.models.result_view_model import DisplayFrame
    viewer=window.viewer;entered=threading.Event();release=threading.Event();reads=[]
    class ContendedRaw:
        def dn(self,*args):reads.append(1);release.wait(.4);return 17
    viewer.set_frame(DisplayFrame(image_frame().image,100,100),fit=True);viewer.raw_provider=ContendedRaw()
    def hold():entered.set();release.wait(3)
    window.controller.submit('fixture',hold);wait(qapp,entered.is_set)
    try:
        started=time.monotonic();QTest.mouseMove(viewer.viewport(),viewer.mapFromScene(50,50));qapp.processEvents()
        assert time.monotonic()-started<.25 and not reads
        assert 'DN：—' in window.pointer.text()
    finally:release.set();wait(qapp,lambda:not window.controller.busy)
    assert reads==[1] and 'DN：17' in window.pointer.text()
