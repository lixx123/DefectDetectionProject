"""Evidence only: formal history, isolated PENDING sessions, explicit RAW input."""
import os,sys,json,time,hashlib,re
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ['PHASE10_EVIDENCE_ROOT']);sys.path.insert(0,str(ROOT))
OUT=Path(sys.argv[1]);OUT.mkdir(parents=True,exist_ok=False)
RAW=Path(os.environ['PHASE10_REVISION_QA_RAW_ROOT'])
allowed={(RAW/n).resolve() for n in ('26 (1).raw','26 (2).raw')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(p):return {f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()} if p.exists() else None
production=ROOT/'output/reviews';before_reviews=snapshot(production)
formal=ROOT/'output/phase4_validation/repository';before_formal=snapshot(formal)
audit_counts={'real_raw_open_events':0,'blocked_raw_opens':0}
def audit(event,args):
    if event=='open' and args and isinstance(args[0],(str,bytes)) and Path(os.fsdecode(args[0])).suffix.lower()=='.raw':
        if Path(os.fsdecode(args[0])).resolve() not in allowed:
            audit_counts['blocked_raw_opens']+=1;raise PermissionError('RAW outside explicit two-input allowlist')
        audit_counts['real_raw_open_events']+=1
sys.addaudithook(audit)
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor
from infrastructure.repositories import JsonResultRepository
from ui.main_window import MainWindow
from ui.controllers.inspection_controller import InspectionController
from ui.models.human_review import HumanReviewRepository,summary
from ui.models.human_review.model import digest
from ui.models.candidate_detail_view_model import CandidateDetailViewModel
from regression.golden import no_engine_execution
app=QApplication([]);QCursor.setPos(0,0)
w=MainWindow(InspectionController(JsonResultRepository(formal),runtime_root=OUT/'runtime'));w.resize(1800,1180);w.show()
p=w.human_review_page;p.repository=HumanReviewRepository(OUT/'isolated_reviews')
def wait():
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        app.processEvents();time.sleep(.005);a=w.admission_page
        if not w.controller.busy and not a.query_pending and not(a.active and a.evaluate_pending) and not(p.active and(p.image_pending or p.restore_pending)):break
    else:raise AssertionError('UI timeout')
    app.processEvents()
samples=[]
with no_engine_execution(),patch('core.detector.Detector.inspect',side_effect=AssertionError('Detector forbidden')),patch.object(HumanReviewRepository,'submit',side_effect=AssertionError('Human submission forbidden')):
    for sample,rid,n,d,name in [('26_1','8a363da8-7a3b-4c77-84cf-d13a375c3b15',83,36,'26 (1).raw'),('26_2','f15a42a0-c022-47eb-93d8-d0d191939589',49,35,'26 (2).raw')]:
        w.tabs.setCurrentIndex(0);w.load_history(rid);wait();result=w.view_model.result;original=digest(result.to_dict())
        w.tabs.setCurrentIndex(4);wait();assert w.view_model.is_formal_result and len(p.tasks)==n and len(result.defects)==d
        p.reviewer.setText('QA_PENDING_ONLY');p.open_session();wait();p.attach_raw(RAW/name);wait()
        assert p.access.raw and p.access.raw.verified and p.access.raw.sha256==result.input_info.sha256
        i=next(i for i,t in enumerate(p.model.rows) if t['object_kind']=='CANDIDATE')
        p.table.setCurrentIndex(p.model.index(i,0));p.table.selectRow(i);wait()
        task=p.current_task();candidate=w.admission_page.queue_vm.candidates[(task['source'],task['object_id'])]
        local=CandidateDetailViewModel(w.view_model,candidate).local_view(1,p.access.raw);x,y=local.origin
        assert local.frame.image.pixelColor(0,0).red()==int(p.access.raw.dn(x,y)*255/4095)
        assert summary(p.state)['pending']==n and not p.state['records']
        assert digest(result.to_dict())==original
        if sample=='26_1':assert w.grab().save(str(OUT/'09_26_1_83_pending.png'))
        samples.append(dict(sample_id=sample,result_id=rid,formal_package=True,task_count=n,defect_count=d,pending=n,completed=0,records=0,labels_generated=0,original_result_unchanged=True,source_digest=original,raw_validation=dict(sha256=result.input_info.sha256,status='PASS'),pixel_lut_check=True))
        p.detach_raw();wait()
    w.tabs.setCurrentIndex(0);w.close();app.processEvents()
assert snapshot(production)==before_reviews and snapshot(formal)==before_formal
assert before_reviews is None or not before_reviews,'Production review data requires independent investigation'
# Scan formal packages, isolated review persistence, and production reviews; paths
# used to open RAW remain runtime variables and never enter these records.
violations=[];checked=0
for base in [formal,OUT/'isolated_reviews',production]:
    for f in base.rglob('*'):
        if f.is_file() and f.suffix.lower() in ('.json','.csv'):
            text=f.read_text(encoding='utf-8-sig');checked+=1
            if any(str(a) in text or a.as_posix() in text or str(a).replace('\\','\\\\') in text for a in allowed):violations.append(f.name)
            if base!=formal and re.search(r'[CD]:[\\/]',text):violations.append(f.name)
assert not violations,violations
report=dict(status='PASS',samples=samples,total_tasks=132,pending=132,real_records=0,real_labels_generated=0,algorithm_executions=0,production_reviews_existed=before_reviews is not None,production_reviews_unchanged=True,formal_package_files_unchanged=True,raw_paths_persisted=False,privacy_files_checked=checked,privacy_violations=violations,access_audit=audit_counts)
(OUT/'phase_10_revision_real_queue_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
