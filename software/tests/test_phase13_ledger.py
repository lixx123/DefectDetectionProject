"""Synthetic archive/ledger QA. No real detector or production review writes."""
from pathlib import Path
from copy import deepcopy
from uuid import uuid4
from datetime import datetime
import hashlib,json,os
import pytest
from openpyxl import load_workbook
from test_phase6_ui import qapp,window,wait,image_frame
from test_phase10_revision import synthetic_case
from ui.models.defect_ledger import DefectLedger,project,validate_filter_id,SUMMARY,DETAIL
from ui.models.result_view_model import ResultViewModel
from ui.widgets.filter_metadata_dialog import FilterMetadataDialog
from domain.enums import SizeGrade,ScaleSource
from infrastructure.repositories import JsonResultRepository

def build(tmp_path,*,fid='260624-01',name='source'):
    r,cfg,path=synthetic_case(tmp_path/name)
    r.extensions['filter_metadata']={'filter_id':fid,'notes':'=literal note'} if fid else {}
    r.algorithm_info.run_timestamp='2026-10-26T10:20:30+08:00'
    base=r.defects[0];r.defects=[]
    for i,g in enumerate([SizeGrade.LARGE,SizeGrade.MEDIUM,SizeGrade.SMALL]):
        d=deepcopy(base);d.identity.defect_id='D'+str(i);d.classification.size_grade=g
        d.geometry.area_px=30+i;d.geometry.length_px=10+i;d.geometry.length_method='MAX_FERET_PIXEL_CENTERS';r.defects.append(d)
    r.statistics.total_defects=3;r.validate_final()
    return r,cfg,path

def records(path,sheet):
    wb=load_workbook(path)
    try:
        ws=wb[sheet];keys=[c.value for c in ws[1]]
        return [dict(zip(keys,row)) for row in ws.iter_rows(min_row=2,values_only=True)]
    finally:wb.close()

@pytest.mark.parametrize('value',['',' a','a ','a/b','a\\b','a:b','a\n','中','x'*65])
def test_invalid_filter_id(value):
    with pytest.raises(ValueError):validate_filter_id(value)

@pytest.mark.parametrize('value',['A-1.a_2','0','x'*64])
def test_valid_filter_id(value):assert validate_filter_id(value)==value

def test_create_project_rebuild_duplicates_and_same_filter(tmp_path):
    repo=JsonResultRepository(tmp_path/'output/results');r,cfg,path=build(tmp_path)
    repo.save(r,path.parent,config_snapshot=cfg);ledger=DefectLedger(repo)
    before=r.to_dict();ledger.sync()
    rows=records(ledger.path,'Filter_Summary');detail=records(ledger.path,'Defect_Detail')
    assert len(rows)==1 and len(detail)==2 and {d['Size_Grade'] for d in detail}=={'LARGE','MEDIUM'}
    row=rows[0]
    assert row['Filter_ID']=='260624-01' and row['Filter_ID_Source']=='RESULT_METADATA'
    assert row['Large_Count']==row['Medium_Count']==1 and row['Large_Medium_Total_Area_px2']==61
    assert row['Detection_Time']==datetime(2026,10,26,2,20,30) and isinstance(row['Saved_Time'],datetime)
    assert row['Result_Folder']=='output/results/'+r.result_id and not Path(row['Result_Folder']).is_absolute()
    assert row['Large_Total_Area_um2']==pytest.approx(30*3.2**2)
    assert row['Max_Feret_um']==pytest.approx(12*3.2) and row['Metrologically_Calibrated'] is False
    assert detail[0]['BBox_Width_px']==6 and detail[0]['BBox_Height_px']==7
    assert detail[0]['Band_ID'] is None and detail[0]['ROI_Type'] is None
    wb=load_workbook(ledger.path)
    assert wb['Filter_Summary'].freeze_panes=='C2' and wb['Filter_Summary'].auto_filter.ref
    assert wb['Filter_Summary'].column_dimensions['D'].width>=68
    assert wb['Filter_Summary'].column_dimensions['H'].width>=64
    note=wb['Filter_Summary'].cell(2,SUMMARY.index('Notes')+1);assert note.data_type=='s' and note.value=='=literal note'
    wb.close();ledger.sync();assert records(ledger.path,'Filter_Summary')==rows
    r2,cfg2,path2=build(tmp_path,name='source2');repo.save(r2,path2.parent,config_snapshot=cfg2);ledger.sync()
    both=records(ledger.path,'Filter_Summary');ds=records(ledger.path,'Defect_Detail')
    assert len(both)==2 and len({d['Result_ID'] for d in both})==2 and {d['Filter_ID'] for d in both}=={'260624-01'}
    ledger.path.unlink();ledger.sync(rebuild=True)
    assert records(ledger.path,'Filter_Summary')==both and records(ledger.path,'Defect_Detail')==ds
    ledger.path.write_bytes(b'corrupt');ledger.sync(rebuild=True)
    assert records(ledger.path,'Filter_Summary')==both and records(ledger.path,'Defect_Detail')==ds
    assert r.to_dict()==before

def test_no_calibration_no_invented_physical_and_no_feret(tmp_path):
    r,_,_=build(tmp_path,fid=None);r.calibration_info.valid=False;r.calibration_info.spatial_scale_um_per_px=None
    r.calibration_info.scale_source=ScaleSource.UNKNOWN;r.defects[0].geometry.length_method='SKELETON'
    row,ds=project(r,'2026-10-26T00:00:00Z')
    assert row['Filter_ID'] is None and row['Pixel_Size_um'] is None
    assert row['Large_Total_Area_um2'] is None and row['Max_Feret_um'] is None
    assert all(d['Area_um2'] is None and d['Max_Feret_um'] is None for d in ds)
    assert ds[0]['Max_Feret_px'] is None

def test_annotation_preservation_and_historical_override(tmp_path):
    r,cfg,path=build(tmp_path,fid=None);repo=JsonResultRepository(tmp_path/'output/results');repo.save(r,path.parent,config_snapshot=cfg)
    original=(repo.root/r.result_id/'result.json').read_bytes();ledger=DefectLedger(repo);ledger.sync()
    wb=load_workbook(ledger.path);ws=wb['Filter_Summary']
    for k,v in [('Filter_ID','LEGACY-1'),('Filter_ID_Source','LEDGER_OVERRIDE'),('Final_Judgement','研究中'),('Notes','manual')]:ws.cell(2,SUMMARY.index(k)+1).value=v
    wb.save(ledger.path);wb.close();ledger.sync();ledger.path.write_bytes(b'broken');ledger.sync(rebuild=True)
    row=records(ledger.path,'Filter_Summary')[0]
    assert row['Filter_ID']=='LEGACY-1' and row['Final_Judgement']=='研究中' and row['Notes']=='manual'
    assert (repo.root/r.result_id/'result.json').read_bytes()==original

def test_atomic_replace_failure_preserves_old_and_retry(tmp_path,monkeypatch):
    r,cfg,path=build(tmp_path);repo=JsonResultRepository(tmp_path/'output/results');repo.save(r,path.parent,config_snapshot=cfg);ledger=DefectLedger(repo);ledger.sync()
    before=ledger.path.read_bytes();real=os.replace
    def locked(a,b):
        if Path(b)==ledger.path:raise PermissionError('Excel opened by another process')
        return real(a,b)
    with monkeypatch.context() as m:
        m.setattr('ui.models.defect_ledger.os.replace',locked)
        with pytest.raises(PermissionError):ledger.sync()
    assert ledger.path.read_bytes()==before and not list(ledger.root.glob('.ledger_*'))
    assert repo.verify(r.result_id).status=='PASS';ledger.sync()
    assert len(records(ledger.path,'Filter_Summary'))==1

def test_gui_save_requires_confirm_cancel_and_metadata(window,qapp,tmp_path):
    r,cfg,path=build(tmp_path,fid=None);c=window.controller
    rec=c.staging.save(r,path.parent,config_snapshot=cfg);vm=ResultViewModel(c.staging.load(r.result_id),rec.result_dir)
    before=deepcopy(vm.result.to_dict());window.display_result(vm,image_frame(),saved=False)
    window._request_filter_metadata=lambda:None;window._save()
    assert not c.repository.list_results() and not (c.repository.root.parent/'defect_ledger.xlsx').exists()
    window._request_filter_metadata=lambda:('CONFIRMED-1','note');window._save();wait(qapp,lambda:not c.busy)
    assert window.saved and c.repository.load(r.result_id).extensions['filter_metadata']['filter_id']=='CONFIRMED-1'
    assert vm.result.to_dict()==before and '台账已更新' in window.statusBar().currentMessage()
    assert len(records(c.repository.root.parent/'defect_ledger.xlsx','Filter_Summary'))==1
    window.controller.sync_ledger();wait(qapp,lambda:not c.busy)
    assert len(records(c.repository.root.parent/'defect_ledger.xlsx','Filter_Summary'))==1

def test_ledger_failure_after_formal_save_never_rolls_back(window,qapp,tmp_path,monkeypatch):
    r,cfg,path=build(tmp_path);c=window.controller;rec=c.staging.save(r,path.parent,config_snapshot=cfg)
    window.display_result(ResultViewModel(c.staging.load(r.result_id),rec.result_dir),image_frame(),saved=False)
    def fail(*a,**k):raise PermissionError('locked')
    with monkeypatch.context() as m:
        m.setattr(DefectLedger,'sync',fail);window._save();wait(qapp,lambda:not c.busy)
    assert window.saved and c.repository.verify(r.result_id).status=='PASS'
    assert '正式结果已保存，但 Excel 台账更新失败' in window.statusBar().currentMessage()
    assert 'LEDGER_UPDATE_FAILED' in c.application_log.path.read_text(encoding='utf-8')
    c.sync_ledger();wait(qapp,lambda:not c.busy)
    assert (c.repository.root.parent/'defect_ledger.xlsx').exists()

def test_filter_dialog_validation(qapp):
    d=FilterMetadataDialog();d.filter_id.setText('bad/id');d.accept();assert d.result()==0 and d.error.text()
    d.filter_id.setText('VALID-1');d.accept();assert d.result()==1

def test_bad_package_not_silently_dropped(tmp_path):
    r,cfg,path=build(tmp_path);repo=JsonResultRepository(tmp_path/'output/results');repo.save(r,path.parent,config_snapshot=cfg)
    ledger=DefectLedger(repo);ledger.sync();before=ledger.path.read_bytes()
    (repo.root/r.result_id/'result.json').write_text('{}',encoding='utf-8')
    with pytest.raises(Exception):ledger.sync(rebuild=True)
    assert ledger.path.read_bytes()==before


def test_concurrent_sync_has_no_duplicate_or_partial_workbook(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    r,cfg,path=build(tmp_path);repo=JsonResultRepository(tmp_path/'output/results');repo.save(r,path.parent,config_snapshot=cfg)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(DefectLedger(repo).sync) for _ in range(2)]
        assert all(j.result()['summary_rows']==1 for j in jobs)
    assert len(records(DefectLedger(repo).path,'Filter_Summary'))==1


def test_real_windows_file_lock_preserves_formal_package(tmp_path):
    if os.name!='nt':return
    import ctypes
    from ctypes import wintypes
    r,cfg,path=build(tmp_path);repo=JsonResultRepository(tmp_path/'output/results');repo.save(r,path.parent,config_snapshot=cfg)
    ledger=DefectLedger(repo);ledger.sync();before=ledger.path.read_bytes()
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    api.CreateFileW.restype=wintypes.HANDLE;api.CloseHandle.argtypes=[wintypes.HANDLE]
    # A real Windows handle denies delete sharing, like an open Excel workbook.
    handle=api.CreateFileW(str(ledger.path),0x80000000,3,None,3,0,None)
    assert handle not in (None,ctypes.c_void_p(-1).value)
    try:
        with pytest.raises(PermissionError):ledger.sync()
        assert ledger.path.read_bytes()==before and repo.verify(r.result_id).status=='PASS'
    finally:api.CloseHandle(handle)
    ledger.sync();assert len(records(ledger.path,'Filter_Summary'))==1
