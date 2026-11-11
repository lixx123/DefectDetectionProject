"""Explicit, isolated GUI ledger acceptance. No detection or review submission."""
def run(plan_path):
    from pathlib import Path
    import sys,json,time,traceback,hashlib
    from uuid import uuid4
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem,QDialog
    from openpyxl import load_workbook
    from infrastructure.repositories import JsonResultRepository
    from ui.controllers.inspection_controller import InspectionController
    from ui.main_window import MainWindow,HistoryDialog
    from ui.widgets.filter_metadata_dialog import FilterMetadataDialog
    from ui.models.result_view_model import ResultViewModel
    from ui.models.defect_ledger import DefectLedger,HistoryLedgerEntry,filter_metadata
    from ui.models.human_review import HumanReviewRepository
    from core.detector import Detector
    plan=json.loads(Path(plan_path).read_text(encoding='utf-8'));out=Path(plan['output']);out.mkdir(exist_ok=False,parents=True)
    shots=out/'screenshots';shots.mkdir();report=dict(status='FAIL',algorithm_executions=0,real_records=0,real_labels_generated=0,fixture='Copied historical measurement fixture; not newly detected production results',frozen=bool(getattr(sys,'frozen',False)))
    counts={'algorithm_attempts':0,'review_submit_attempts':0,'subprocess_attempts':0}
    def forbid_engine(*a,**k):counts['algorithm_attempts']+=1;raise AssertionError('Algorithm forbidden in ledger QA')
    def forbid_review(*a,**k):counts['review_submit_attempts']+=1;raise AssertionError('Production reviews forbidden')
    def audit(event,args):
        if event=='subprocess.Popen':counts['subprocess_attempts']+=1;raise AssertionError('Subprocess forbidden in ledger QA')
    sys.addaudithook(audit);Detector.inspect=forbid_engine;HumanReviewRepository.submit=forbid_review
    app=QApplication.instance() or QApplication([]);repo=JsonResultRepository(out/'output/results')
    w=MainWindow(InspectionController(repo,runtime_root=out/'output/runtime'));w.resize(1800,1100);w.show()
    c=w.controller
    def wait():
        end=time.monotonic()+180
        while time.monotonic()<end:
            app.processEvents();time.sleep(.01)
            if not c.busy and not w.admission_page.query_pending and not(w.tabs.currentIndex()==1 and w._detail_pending):return
        raise TimeoutError('GUI ledger QA timeout')
    def shot(name):wait();assert w.grab().save(str(shots/name))
    def workbook_rows(path,sheet):
        wb=load_workbook(path)
        try:return list(wb[sheet].values)
        finally:wb.close()
    def sheet_shot(sheet,columns,name):
        # Actual saved XLSX cells shown read-only; no Excel/WPS dependency.
        data=workbook_rows(out/'output/defect_ledger.xlsx',sheet);headers=data[0];cols=[headers.index(k) for k in columns]
        view=QTableWidget(len(data)-1,len(cols));view.setWindowTitle('XLSX 只读 QA 预览 — '+sheet);view.setHorizontalHeaderLabels(columns)
        for i,row in enumerate(data[1:]):
            for j,k in enumerate(cols):
                from datetime import datetime
                value=row[k]
                text='' if value is None else value.strftime('%Y-%m-%d %H:%M:%S') if isinstance(value,datetime) else f'{value:.3f}' if isinstance(value,float) else str(value)
                item=QTableWidgetItem(text);view.setItem(i,j,item)
        view.resize(1850,620);view.resizeColumnsToContents();view.show();app.processEvents();assert view.grab().save(str(shots/name));view.close()
    try:
        wait();source=Path(plan['source_package']);original=hashlib.sha256((source/'result.json').read_bytes()).hexdigest()
        source_repo=JsonResultRepository(source.parent);r=source_repo.load(source.name)
        ids=[]
        for i in range(2):
            # Explicit test copies; original measurements and artifacts never rewritten.
            from domain.serialization import from_dict
            from domain import InspectionResult
            result=from_dict(InspectionResult,r.to_dict());result.result_id=str(uuid4())
            result.extensions.pop('filter_metadata',None);result.extensions['ledger_qa_fixture']=True
            rec=c.staging.save(result,source);vm=ResultViewModel(c.staging.load(result.result_id),rec.result_dir)
            w.display_result(vm,saved=False);wait();before=vm.result.to_dict()
            error=[]
            def fill_dialog():
                d=app.activeModalWidget()
                if not isinstance(d,FilterMetadataDialog):QTimer.singleShot(10,fill_dialog);return
                try:
                    d.filter_id.setText('QA-FILTER-01');d.notes.setText('QA only; existing measurement fixture')
                    if i==0:assert d.grab().save(str(shots/'01_filter_id_save_dialog.png'))
                    d.accept()
                except Exception as exc:error.append(str(exc));d.reject()
            QTimer.singleShot(10,fill_dialog);w.save_action.trigger();wait();assert not error,error
            assert w.saved and vm.result.to_dict()==before
            assert '台账已更新' in w.statusBar().currentMessage();ids.append(result.result_id)
            assert repo.verify(result.result_id).status=='PASS'
            assert repo.load(result.result_id).extensions['filter_metadata']['filter_id']=='QA-FILTER-01'
            if i==0:shot('02_save_success_ledger_updated.png')
        entries=[HistoryLedgerEntry(s,filter_metadata(repo.load(s.result_id)).get('filter_id')) for s in repo.list_results()]
        dialog=HistoryDialog(entries,w);dialog.resize(1700,500);dialog.show();app.processEvents()
        assert dialog.table.model().item(0,7).text()=='QA-FILTER-01'
        assert dialog.grab().save(str(shots/'03_history_filter_id_column.png'));dialog.close()
        ledger=DefectLedger(repo);summary_before=workbook_rows(ledger.path,'Filter_Summary');detail_before=workbook_rows(ledger.path,'Defect_Detail')
        assert len(summary_before)==3 and len({row[1] for row in summary_before[1:]})==2
        sheet_shot('Filter_Summary',['Filter_ID','Result_ID','Result_Folder','Large_Count','Medium_Count','Saved_Time'],'04_filter_summary_sheet.png')
        sheet_shot('Defect_Detail',['Filter_ID','Defect_ID','Size_Grade','Area_px2','Area_um2','Max_Feret_px','Max_Feret_um','Saved_Time'],'05_defect_detail_sheet.png')
        sheet_shot('Filter_Summary',['Filter_ID','Result_ID','Large_Count','Medium_Count'],'06_same_filter_multiple_results.png')
        w.sync_ledger_action.trigger();wait();assert workbook_rows(ledger.path,'Filter_Summary')==summary_before and workbook_rows(ledger.path,'Defect_Detail')==detail_before
        shot('07_duplicate_result_not_reinserted.png')
        ledger.path.unlink();w.sync_ledger_action.trigger();wait()
        assert workbook_rows(ledger.path,'Filter_Summary')==summary_before and workbook_rows(ledger.path,'Defect_Detail')==detail_before
        shot('08_ledger_rebuild_success.png')
        assert not counts['algorithm_attempts'] and not counts['review_submit_attempts'] and not counts['subprocess_attempts']
        assert not list((out/'output/reviews').rglob('*.json'))
        assert hashlib.sha256((source/'result.json').read_bytes()).hexdigest()==original
        report.update(status='PASS',result_ids=ids,summary_rows=2,detail_rows=len(detail_before)-1,filter_id_in_metadata=True,history_filter_id_visible=True,duplicate_prevented=True,rebuild_identical=True,source_unchanged=True,xlsx_previews='Actual saved cells rendered by read-only Qt QA table; not Excel/WPS application',source_package=str(source))
    except Exception:report['error']=traceback.format_exc()
    finally:
        wait();w.close();app.processEvents()
        report['guards']=counts
        (out/'ledger_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':
    import sys
    raise SystemExit(run(sys.argv[1]))
