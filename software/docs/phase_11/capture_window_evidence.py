"""Phase11 real-window evidence; two frozen RAW files only, no real submissions."""
import os,sys,json,time,hashlib,threading,re
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ['PHASE11_ROOT']);sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=False);SHOTS=OUT/'screenshots';SHOTS.mkdir()
RAW=Path(os.environ['PHASE11_QA_RAW_ROOT']);allowed={(RAW/n).resolve() for n in ['26 (1).raw','26 (2).raw']}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(p):return {f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()} if p.exists() else None
formal=ROOT/'output/phase4_validation/repository';reviews=ROOT/'output/reviews';original=snapshot(formal);prior_reviews=snapshot(reviews)
opens={'real_raw_opens':0,'blocked_raw_opens':0}
def audit(event,args):
    if event=='open' and args and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0]))
        if p.suffix.lower()=='.raw':
            p=p.resolve()
            if p in allowed:opens['real_raw_opens']+=1
            elif not p.is_relative_to((ROOT/'output').resolve()):opens['blocked_raw_opens']+=1;raise PermissionError('RAW outside two-file QA allowlist')
sys.addaudithook(audit)
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor
from infrastructure.repositories import JsonResultRepository
from ui.controllers.inspection_controller import InspectionController
from ui.main_window import MainWindow
from ui.models.human_review import HumanReviewRepository,summary
from ui.models.human_review.evidence import FormalResultAuthority
from ui.models.human_review.model import digest
from ui.models.candidate_detail_view_model import CandidateDetailViewModel
from regression.golden import no_engine_execution
from test_phase10_revision import synthetic_case
app=QApplication.instance() or QApplication([]);QCursor.setPos(0,0)
c=InspectionController(JsonResultRepository(formal),runtime_root=OUT/'runtime');w=MainWindow(c);w.resize(1800,1180);w.show();p=w.human_review_page
p.repository=HumanReviewRepository(OUT/'isolated_reviews')
def wait():
    end=time.monotonic()+180
    while time.monotonic()<end:
        app.processEvents();time.sleep(.005);a=w.admission_page
        if not c.busy and not a.query_pending and not(a.active and a.evaluate_pending) and not(p.active and(p.image_pending or p.restore_pending)):break
    else:raise AssertionError('UI timeout')
    app.processEvents()
def shot(name,settle=True):
    if settle:wait()
    app.processEvents();assert w.grab().save(str(SHOTS/name))
rid1='8a363da8-7a3b-4c77-84cf-d13a375c3b15';rid2='f15a42a0-c022-47eb-93d8-d0d191939589'
samples=[]
with no_engine_execution(),patch('core.detector.Detector.inspect',side_effect=AssertionError('Detector forbidden in Phase11 real QA')),patch.object(HumanReviewRepository,'submit',side_effect=AssertionError('real review submissions forbidden')):
    w.load_history(rid1);wait();assert w.saved and len(w.view_model.defects)==36;shot('01_normal_operation_status.png')
    hold=threading.Event()
    c.submit('phase11_qa_wait',lambda:hold.wait(5));app.processEvents();assert c.busy
    shot('02_background_task_busy.png',False);assert not w.close();hold.set();wait()
    prior_vm=w.view_model;w.open_raw(OUT/'missing.raw');wait()
    assert w.view_model is prior_vm and 'RAW_READ_FAILED' in w.resource_status.text() and not c.busy
    shot('03_raw_error_user_message.png')
    synthetic,cfg,path=synthetic_case(OUT/'synthetic_source');badrepo=JsonResultRepository(OUT/'synthetic_formal')
    bad=badrepo.save(synthetic,path.parent,config_snapshot=cfg);(Path(bad.result_dir)/'result.json').write_text('{}',encoding='utf-8')
    authority=c.formal_authority;c.formal_authority=FormalResultAuthority(badrepo)
    w.load_history(synthetic.result_id);wait()
    assert w.view_model is None and 'RESULT_INTEGRITY_FAILED' in w.resource_status.text() and not p.start.isEnabled()
    shot('04_history_integrity_error.png');c.formal_authority=authority
    w.load_history(rid1);wait();w._viewer_selected(w.view_model.defects[0].identity.defect_id);w.tabs.setCurrentIndex(1);wait()
    assert w.view_model.is_formal_result and not c.busy and w.open_action.isEnabled();shot('05_operation_failed_recovered.png')
    for sample,rid,n,d,raw_name,filename in [('26_1',rid1,83,36,'26 (1).raw','06_phase10_review_still_available.png'),('26_2',rid2,49,35,'26 (2).raw','07_26_2_review_49_pending.png')]:
        w.tabs.setCurrentIndex(0);w.load_history(rid);wait();r=w.view_model.result;before=digest(r.to_dict())
        w.tabs.setCurrentIndex(4);wait();p.reviewer.setText('QA_PENDING_ONLY');p.open_session();wait();p.attach_raw(RAW/raw_name);wait()
        assert p.access.raw and p.access.raw.verified and p.access.raw.sha256==r.input_info.sha256
        assert len(p.tasks)==n and len(r.defects)==d and not p.state['records'] and summary(p.state)['pending']==n
        i=next(i for i,t in enumerate(p.model.rows) if t['object_kind']=='CANDIDATE');p.table.setCurrentIndex(p.model.index(i,0));p.table.selectRow(i);wait()
        task=p.current_task();candidate=w.admission_page.queue_vm.candidates[(task['source'],task['object_id'])]
        local=CandidateDetailViewModel(w.view_model,candidate).local_view(1,p.access.raw);x,y=local.origin
        assert local.frame.image.pixelColor(0,0).red()==int(p.access.raw.dn(x,y)*255/4095)
        assert digest(r.to_dict())==before;shot(filename)
        samples.append(dict(sample_id=sample,result_id=rid,defect_count=d,task_count=n,pending=n,records=0,labels_generated=0,source_digest=before,original_result_unchanged=True,raw_validation=dict(sha256=r.input_info.sha256,status='PASS'),pixel_lut_check=True))
        p.detach_raw();wait()
    w.tabs.setCurrentIndex(0);w.close();app.processEvents()
assert snapshot(formal)==original and snapshot(reviews)==prior_reviews and prior_reviews is None
assert opens['blocked_raw_opens']==0
for base in [formal,OUT/'isolated_reviews']:
    for f in base.rglob('*'):
        if f.is_file() and f.suffix.lower() in ('.json','.csv'):
            content=f.read_text(encoding='utf-8-sig')
            # Frozen algorithm evidence CSV retains historical tile-mask/member
            # paths. Never rewrite it. Review protocol must contain no absolute
            # path; formal artifacts must not disclose complete RAW input paths.
            assert not re.search(r'[CD]:[\\/][^\r\n"<>]*?\.raw',content,re.I)
            if base!=formal:assert not re.search(r'[CD]:[\\/]',content)
report=dict(status='PASS',samples=samples,real_records=0,real_labels_generated=0,algorithm_executions=0,real_pending=132,formal_package_unchanged=True,production_reviews_existed=False,production_reviews_unchanged=True,raw_paths_persisted=False,access_audit=opens,errors_observed=['RAW_READ_FAILED','RESULT_INTEGRITY_FAILED'],screenshot_sha256={f.name:sha(f) for f in SHOTS.glob('*.png')},synthetic_busy_task='Explicit QA hold; proves responsiveness/close guard, never a detection run')
(OUT/'phase_11_real_queue_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
