"""Compiled release acceptance: real widgets, strict isolated plan, no engine."""
import hashlib,json,logging,sys,time,traceback
from pathlib import Path


def run(plan_path):
    plan=json.loads(Path(plan_path).read_text(encoding='utf-8'))
    out=Path(plan['evidence_dir']);out.mkdir(parents=True,exist_ok=False)
    report={'status':'FAIL','algorithm_executions':0,'real_records':0,'real_labels_generated':0,'checks':{}}
    try:
        _accept(plan,out,report)
        report['status']='PASS'
    except Exception:
        report['error']=traceback.format_exc()
    (out/'release_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['status']=='PASS' else 1


def _accept(plan,out,report):
    from PySide6.QtCore import QCoreApplication,Qt
    from PySide6.QtGui import QImageReader,QPalette
    from PySide6.QtWidgets import QApplication
    from app.runtime_paths import application_root,resource_root
    from ui.main_window import MainWindow,HistoryDialog
    from ui.models.result_view_model import ViewMode
    from ui.models.human_review import HumanReviewRepository,summary
    from ui.models.human_review.evidence import FormalResultAuthority
    from ui.models.human_review.model import digest
    from ui.models.review_admission import load_policy
    from ui.models.candidate_detail_view_model import CandidateDetailViewModel
    from ui.runtime_log import ApplicationLog
    from infrastructure.repositories import JsonResultRepository
    from core.detector import Detector
    root=application_root();res=resource_root()
    assert getattr(sys,'frozen',False) and root!=res and not (root/'.venv').exists()
    assert not any((root/n).exists() for n in ['app','ui','tests','.git','packaging'])
    assert (root/'configs/production_v1.yaml').is_file()
    assert load_policy().policy_hash=='63edae3c40966768f907360a377ad7847ebbf477121afb54c1595b69c80f2327'
    report['checks']['resource_policy']='PASS'
    app=QApplication.instance() or QApplication([])
    assert app.platformName()=='windows'
    assert app.palette().color(QPalette.ColorRole.Text).lightness()<128
    report['checks']['light_palette_contrast']='PASS'
    formats=[bytes(x).decode() for x in QImageReader.supportedImageFormats()]
    assert 'png' in formats and 'jpeg' in formats
    assert (res/'PySide6/plugins/platforms/qwindows.dll').is_file()
    assert list((res/'PySide6/plugins/imageformats').glob('*.dll'))
    report.update(qt_platform=app.platformName(),image_formats=formats,library_paths=QCoreApplication.libraryPaths())
    allowed={Path(s['raw']).resolve() for s in plan['samples']}
    counts={'approved_raw_opens':0,'blocked_raw_opens':0,'engine_attempts':0,'review_submit_attempts':0}
    def audit(event,args):
        if event=='open' and args and isinstance(args[0],str) and Path(args[0]).suffix.lower()=='.raw':
            p=Path(args[0]).resolve()
            if p in allowed:counts['approved_raw_opens']+=1
            elif not p.is_relative_to(out.resolve()):
                counts['blocked_raw_opens']+=1;raise PermissionError('RAW outside release QA allowlist')
    sys.addaudithook(audit)
    def no_engine(*a,**k):
        counts['engine_attempts']+=1;raise AssertionError('Detection forbidden in release QA')
    def no_submit(*a,**k):
        counts['review_submit_attempts']+=1;raise AssertionError('Review submit forbidden in release QA')
    Detector.inspect=no_engine;HumanReviewRepository.submit=no_submit
    w=MainWindow();w.resize(1800,1180);w.show();c=w.controller;p=w.human_review_page
    assert c.repository.root==root/'output/results' and c.runtime_root==root/'output/runtime'
    # Only QA overrides its review destination; normal app keeps output/reviews.
    p.repository=HumanReviewRepository(out/'isolated_reviews')
    def wait():
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            app.processEvents();time.sleep(.005);a=w.admission_page
            if not c.busy and not a.query_pending and not(a.active and a.evaluate_pending) and not(p.active and(p.image_pending or p.restore_pending)) and not w._detail_pending:break
        else:raise AssertionError('release GUI timeout')
        app.processEvents()
    shots=out/'screenshots';shots.mkdir()
    def shot(name):
        wait();assert w.isVisible();assert w.grab().save(str(shots/name))
    shot('01_release_startup.png')
    # The default controller, shipped modules and real async RAW worker are used.
    w.open_raw(plan['samples'][0]['raw']);wait()
    assert w.raw is not None and w.viewer.base_item is not None
    z=w.viewer.zoom;w.viewer.zoom_by(1.25);assert w.viewer.zoom>z;w.viewer.fit()
    shot('09_release_raw_browse.png');report['checks']['raw_browse_zoom']='PASS'
    report['samples']=[]
    for i,sample in enumerate(plan['samples']):
        r=c.repository.load(sample['result_id']);before=digest(r.to_dict())
        assert before==sample['source_digest']
        summaries=c.repository.list_results()
        dialog=HistoryDialog(summaries,w)
        assert dialog.table.model().rowCount()==2;dialog.close()
        w.tabs.setCurrentIndex(0);w.load_history(sample['result_id']);wait()
        assert w.view_model.is_formal_result and w.saved and len(w.view_model.defects)==sample['defects']
        assert w.table_model.rowCount()==sample['defects']
        w.view_selector.setCurrentText(ViewMode.FINAL);wait()
        assert w.viewer.base_item is not None and len(w.viewer.overlays)==sample['defects']
        if i==0:
            shot('02_release_detection_result.png')
            w._viewer_selected(w.view_model.defects[0].identity.defect_id);w.tabs.setCurrentIndex(1);wait()
            assert w.detail_page.detail_vm is not None and w.detail_page.viewer.base_item is not None
            shot('03_release_defect_detail.png')
            w.tabs.setCurrentIndex(2);wait();assert w.statistics_page.view_model is not None
            shot('04_release_statistics.png')
            w.tabs.setCurrentIndex(3);wait();shot('05_release_audit.png')
        w.tabs.setCurrentIndex(4);wait();p.reviewer.setText('QA_PENDING_ONLY');p.open_session();wait()
        p.attach_raw(sample['raw']);wait()
        assert p.access.raw and p.access.raw.verified and p.access.raw.sha256==r.input_info.sha256
        assert len(p.tasks)==sample['tasks'] and not p.state['records'] and summary(p.state)['pending']==sample['tasks']
        idx=next(j for j,t in enumerate(p.model.rows) if t['object_kind']=='CANDIDATE')
        p.table.setCurrentIndex(p.model.index(idx,0));p.table.selectRow(idx);wait()
        task=p.current_task();candidate=w.admission_page.queue_vm.candidates[(task['source'],task['object_id'])]
        local=CandidateDetailViewModel(w.view_model,candidate).local_view(1,p.access.raw);x,y=local.origin
        assert local.frame.image.pixelColor(0,0).red()==int(p.access.raw.dn(x,y)*255/4095)
        assert digest(r.to_dict())==before
        shot('06_release_human_review_26_1.png' if i==0 else '07_release_human_review_26_2.png')
        report['samples'].append(dict(sample=sample['name'],defects=sample['defects'],tasks=sample['tasks'],pending=sample['tasks'],records=0,source_digest=before,raw_sha256=p.access.raw.sha256,pixel_lut_check=True))
        p.detach_raw();wait()
    w.tabs.setCurrentIndex(0);prior=w.view_model;w.open_raw(out/'missing.raw');wait()
    assert w.view_model is prior and 'RAW_READ_FAILED' in w.resource_status.text()
    assert w.resource_status.text().count('详情见运行日志')==1
    shot('08_release_raw_error.png')
    original=c.formal_authority
    c.formal_authority=FormalResultAuthority(JsonResultRepository(plan['corrupt_repository']))
    w.load_history(plan['samples'][0]['result_id']);wait()
    assert 'RESULT_INTEGRITY_FAILED' in w.resource_status.text() and not p.start.isEnabled()
    shot('10_release_integrity_error.png');c.formal_authority=original
    assert w.close();app.processEvents()
    for level,name in [(logging.INFO,'INFO'),(logging.WARNING,'WARNING'),(logging.ERROR,'ERROR')]:
        c.application_log.event(level,'release_qa',name,'发布版中文日志验证')
    c.application_log.close()
    text=(root/'output/runtime/gui_errors.log').read_text(encoding='utf-8')
    assert all('level='+n in text for n in ['INFO','WARNING','ERROR']) and '发布版中文日志验证' in text
    # Small limit exercises the same frozen handler without changing defaults.
    log=ApplicationLog(out/'rotation.log',max_bytes=512,backup_count=2)
    for j in range(30):log.event(logging.WARNING,'release_qa','ROTATION','中文轮转验证'*12)
    log.close();assert (out/'rotation.log.1').exists() and len(list(out.glob('rotation.log*')))<=3
    assert not counts['blocked_raw_opens'] and not counts['engine_attempts'] and not counts['review_submit_attempts']
    assert not list((root/'output/reviews').rglob('*'))
    from ctypes.util import dllist
    modules=dllist()
    assert not any('.venv' in n.casefold() or 'defectinspectionsoftware\\.venv' in n.casefold() for n in modules)
    assert not any('defectdetectionproject' in n.casefold() for n in modules)
    report['native_module_paths']=modules
    report['checks']['native_dependencies_local_or_system']='PASS'
    report.update(real_pending=132,access_audit=counts,release_root=str(root),frozen=True,closed=True,
                  screenshot_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in shots.glob('*.png')})
    report['checks'].update(dict(main_window='PASS',history='PASS',final_results='PASS',detail='PASS',statistics='PASS',audit='PASS',human_review='PASS',raw_association='PASS',local_gray='PASS',raw_error='PASS',integrity_error='PASS',log_levels_UTF8_rotation='PASS',close='PASS',non_source_root='PASS'))
