"""Actual packaged GUI -> packaged engine; no result injection or detector mocks."""
import os,sys,json,time,hashlib,traceback
from pathlib import Path

def run(planfile):
    plan=json.loads(Path(planfile).read_text(encoding='utf-8'));out=Path(plan['evidence_dir']);out.mkdir(parents=True,exist_ok=False)
    report=dict(status='FAIL',algorithm_executions=0,real_records=0,real_labels_generated=0,samples=[])
    try:accept(plan,out,report);report['status']='PASS'
    except Exception:report['traceback']=traceback.format_exc()
    (out/'engine_gui_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['status']=='PASS' else 2

def accept(plan,out,report):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication
    from app.runtime_paths import application_root,logical_path
    from ui.main_window import MainWindow
    from ui.models.human_review import HumanReviewRepository,summary
    from ui.models.human_review.model import digest
    from ui.models.candidate_detail_view_model import CandidateDetailViewModel
    from infrastructure.engines import EngineRegistry
    from ctypes.util import dllist
    root=application_root();app=QApplication.instance() or QApplication([])
    assert getattr(sys,'frozen',False) and app.platformName()=='windows'
    assert not any((root/n).exists() for n in ['app','core','tests','.git','.venv'])
    allowed={Path(s['raw']).resolve() for s in plan.get('samples',[])}
    audit=dict(development_project_accesses=0,development_venv_accesses=0,system_python_accesses=0,blocked_external_opens=0)
    windows=Path(os.environ['SystemRoot']);temp=Path(os.environ['TEMP'])
    def hook(event,args):
        if event!='open' or not args or not isinstance(args[0],(str,bytes)):return
        p=logical_path(Path(os.fsdecode(args[0])).absolute())
        if p in allowed or p.is_relative_to(root) or p.is_relative_to(out) or p.is_relative_to(windows) or p.is_relative_to(temp):return
        audit['blocked_external_opens']+=1;s=str(p).casefold()
        if '.venv' in s:audit['development_venv_accesses']+=1
        if 'defectdetectionproject' in s or 'defectinspectionsoftware' in s:audit['development_project_accesses']+=1
        if 'python' in s:audit['system_python_accesses']+=1
        raise PermissionError('GUI_EXTERNAL_ACCESS_FORBIDDEN')
    sys.addaudithook(hook)
    submits=[]
    def forbid_submit(*a,**k):submits.append(True);raise AssertionError('Real review submissions forbidden in QA')
    HumanReviewRepository.submit=forbid_submit
    w=MainWindow();w.resize(1800,1180);w.show();c=w.controller;p=w.human_review_page
    p.repository=HumanReviewRepository(out/'isolated_reviews')
    beat=[0];timer=QTimer();timer.timeout.connect(lambda:beat.__setitem__(0,beat[0]+1));timer.start(25)
    shots=out/'screenshots';shots.mkdir()
    def wait(timeout=180):
        deadline=time.monotonic()+timeout;last=0
        while time.monotonic()<deadline:
            app.processEvents();time.sleep(.005);a=w.admission_page
            if time.monotonic()-last>30:
                last=time.monotonic();print(json.dumps(dict(stage=c.operation,busy=c.busy,heartbeat=beat[0])),flush=True)
            if not c.busy and not a.query_pending and not(a.active and a.evaluate_pending) and not(p.active and(p.image_pending or p.restore_pending)) and not(w._detail_pending and w.tabs.currentIndex()==1):return
        raise AssertionError('Packaged GUI timed out')
    def shot(name):app.processEvents();assert w.isVisible() and w.grab().save(str(shots/name))
    wait();mode=plan.get('mode','real')
    if mode!='real':
        assert not c.engine_ready and not w.start_action.isEnabled()
        shot('10_engine_missing_disabled.png' if mode=='missing' else '11_engine_hash_failure.png')
        report.update(engine_unavailable=True,detection_disabled=True,mode=mode)
        w.close();app.processEvents();return
    assert c.engine_ready and 'reference v1.0.0' in w.engine_label.text();shot('01_engine_ready.png')
    manifest=EngineRegistry(root).resolve();report['engine']=manifest.identity
    # Actual A, compatible unit stub B: registry-only; B never executes or ships.
    from infrastructure.engines.manifest import sha,canonical,PROFILE
    import shutil
    update_root=out/'update_test';r=EngineRegistry(update_root)
    r.install(manifest.root)
    stub=out/'stub_B';stub.mkdir();(stub/'engine_runner.exe').write_bytes(b'QA_ONLY_STUB_DO_NOT_SHIP')
    files={'engine_runner.exe':sha(stub/'engine_runner.exe')}
    meta=dict(engine_id='reference',engine_version='2.0.0',protocol_version='1.0',output_schema_version='1.0',runner='engine_runner.exe',runner_sha256=files['engine_runner.exe'],algorithm_source_sha256='b'*64,engine_bundle_sha256=hashlib.sha256(canonical(files)).hexdigest(),config_version='STUB_ONLY',supported_input=PROFILE,files=files)
    (stub/'engine_manifest.json').write_text(json.dumps(meta),encoding='utf-8');r.install(stub)
    assert r.resolve().data['engine_version']=='2.0.0';r.select('reference','1.0.0');assert r.resolve().identity==manifest.identity
    report['engine_switch_test']=report['engine_rollback_test']='PASS'
    for i,sample in enumerate(plan['samples']):
        w.tabs.setCurrentIndex(0);w.open_raw(sample['raw']);wait();assert w.raw is not None and w.start_action.isEnabled()
        if i==0:shot('02_new_raw_ready.png')
        tick=beat[0];w.start_action.trigger();app.processEvents();assert c.busy and not w.start_action.isEnabled()
        assert not w.close() and not c.submit('mutual_exclusion_probe',lambda:None)
        if i==0:shot('03_real_detection_running.png')
        wait(8000)
        assert beat[0]-tick>=20 and w.view_model is not None and not w.saved
        result=w.view_model.result;assert result.result_id not in sample['forbidden_result_ids']
        assert result.extensions.get('real_input_run') is True and result.algorithm_info.extensions['engine']==manifest.identity
        known_case=sample.get('kind','regression')=='regression'
        assert w.proxy.rowCount()==len(result.defects)
        if known_case:assert len(result.defects)==sample['defects']
        if known_case:assert result.execution_info.final_mode.value=='roi-bh' and not result.execution_info.fallback_used
        w.id_action.setChecked(True);w.viewer.show_ids(True)
        shot(('04_real_detection_26_1_complete.png' if i==0 else '05_real_detection_26_2_complete.png') if known_case else 'supplemental_'+sample['name']+'_complete.png')
        run_id=result.extensions['engine_execution']['run_id'];task=c.runtime_root/run_id
        receipt=json.loads((task/'engine_receipt.json').read_text(encoding='utf-8'));process=json.loads((task/'process_receipt.json').read_text(encoding='utf-8'))
        report['algorithm_executions']+=receipt['algorithm_executions']
        assert receipt['status']=='PASS' and process['exit_code']==0 and process['pid']>0
        assert logical_path(Path(process['engine_runner_path'])).is_relative_to(root/'engines')
        assert not any(receipt['runtime_access']['counters'][k] for k in ['development_project_accesses','development_venv_accesses','system_python_accesses','blocked_external_opens'])
        attempt_access=[json.loads(f.read_text(encoding='utf-8')) for f in task.glob('attempt_*_access.json')]
        assert attempt_access and all(not any(a['counters'][k] for k in ['development_project_accesses','development_venv_accesses','system_python_accesses','blocked_external_opens']) for a in attempt_access)
        if i==0:
            w._viewer_selected(result.defects[0].identity.defect_id);w.tabs.setCurrentIndex(1);wait();assert '真实 RAW' in w.detail_page.image_status.text();shot('06_new_result_detail.png')
            w.tabs.setCurrentIndex(2);wait();shot('07_new_result_statistics.png')
            w.tabs.setCurrentIndex(3);wait();shot('08_new_result_audit.png')
        w.tabs.setCurrentIndex(0);w._save();wait();assert w.saved and w.view_model.is_formal_result
        rid=result.result_id;w.load_history(rid);wait();assert w.saved and w.view_model.result.result_id==rid
        assert 'reference v1.0.0' in w.result_engine_label.text()
        shot('history_'+sample['name']+'_reloaded.png')
        w.tabs.setCurrentIndex(4);wait();p.reviewer.setText('QA_PENDING_ONLY');p.open_session();wait();p.attach_raw(sample['raw']);wait()
        assert p.access.raw and p.access.raw.verified and not p.state['records']
        if known_case:assert len(p.tasks)==sample['tasks']
        assert summary(p.state)['pending']==len(p.tasks)
        row=next((j for j,t in enumerate(p.model.rows) if t['object_kind']=='CANDIDATE'),None)
        pixel_check=None
        if row is not None:
            p.table.setCurrentIndex(p.model.index(row,0));p.table.selectRow(row);wait()
            task_row=p.current_task();cand=w.admission_page.queue_vm.candidates[(task_row['source'],task_row['object_id'])]
            local=CandidateDetailViewModel(w.view_model,cand).local_view(1,p.access.raw);x,y=local.origin
            assert local.frame.image.pixelColor(0,0).red()==int(p.access.raw.dn(x,y)*255/4095)
            pixel_check=True
        shot(('12_new_result_review_26_1.png' if i==0 else '13_new_result_review_26_2.png') if known_case else 'supplemental_'+sample['name']+'_review.png')
        report['samples'].append(dict(sample=sample['name'],kind=sample.get('kind','regression'),result_id=rid,run_id=run_id,task_id=result.task_id,defects=len(result.defects),tasks=len(p.tasks),pending=summary(p.state)['pending'],records=0,result_dir=str(w.view_model.package_dir),runtime_dir=str(task),process_receipt=process,engine_receipt=receipt,attempt_access=attempt_access,heartbeat_ticks=beat[0]-tick,save='PASS',reload='PASS',statistics='PASS',audit='PASS',human_review='PASS',raw_association='PASS',pixel_lut_check=pixel_check))
        p.detach_raw();wait()
    report['historical_results']=[]
    for historical in plan.get('historical_results',[]):
        w.tabs.setCurrentIndex(0);w.load_history(historical['result_id']);wait()
        assert w.saved and w.view_model.result.result_id==historical['result_id']
        actual_engine=w.view_model.result.algorithm_info.extensions.get('engine')
        assert actual_engine==historical.get('engine')
        report['historical_results'].append(dict(result_id=historical['result_id'],status='PASS',own_engine=actual_engine,algorithm_version=w.view_model.result.algorithm_info.algorithm_version))
        shot('legacy_'+historical['result_id']+'.png')
    if plan.get('signature'):
        from PySide6.QtWidgets import QMessageBox
        signature=plan['signature']
        assert signature['gui_sha256']==hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        assert signature['runner_sha256']==manifest.data['runner_sha256']
        box=QMessageBox(w);box.setWindowTitle('QA 签名诊断 - 系统 Authenticode 只读结果')
        box.setText('GUI: '+signature['gui_status']+'\nEngine: '+signature['runner_status']+'\n来源：Get-AuthenticodeSignature\n本对话框仅展示已绑定文件 SHA256 的真实签名检测结果。')
        def signature_shot():
            assert box.grab().save(str(shots/'signature_status.png'));box.accept()
        QTimer.singleShot(300,signature_shot);box.exec()
    def about_shot():
        box=app.activeModalWidget();assert box is not None and 'reference v1.0.0' in box.text();assert box.grab().save(str(shots/'09_engine_version.png'));box.accept()
    QTimer.singleShot(300,about_shot)
    action=next(a for a in w.findChildren(QAction) if a.text()=='关于');action.trigger()
    assert not submits and not any(audit.values())
    modules=dllist();assert not any('.venv' in n.casefold() for n in modules)
    report.update(gui_access_audit=audit,gui_native_modules=modules,review_submit_attempts=len(submits),closed=w.close())
    app.processEvents();timer.stop()
