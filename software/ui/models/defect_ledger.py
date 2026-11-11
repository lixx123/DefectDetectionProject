"""Derived ledger only. Verified InspectionResult packages are the source of truth."""
from pathlib import Path
from datetime import datetime, timezone
from threading import RLock
from tempfile import NamedTemporaryFile
from dataclasses import dataclass
import json, math, os, re, shutil
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from infrastructure.repositories.index import exclusive_lock

SCHEMA_VERSION='1.0'
SUMMARY='''Filter_ID Result_ID RAW_File RAW_SHA256 Sample_ID Detection_Time Saved_Time Result_Folder Software_Version Engine_ID Engine_Version Engine_Protocol Algorithm_Version Config_Hash Pixel_Size_um Large_Count Medium_Count Large_Medium_Count Large_Total_Area_px2 Medium_Total_Area_px2 Large_Medium_Total_Area_px2 Large_Total_Area_um2 Medium_Total_Area_um2 Large_Medium_Total_Area_um2 Max_Defect_Area_px2 Max_Defect_Area_um2 Max_Feret_px Max_Feret_um Review_Status Record_Status Final_Judgement Standard_Version Performance_Link Notes Filter_ID_Source Scale_Source Metrologically_Calibrated'''.split()
DETAIL='''Filter_ID Result_ID Defect_ID Size_Grade Band_ID ROI_Type BBox_X_px BBox_Y_px BBox_Width_px BBox_Height_px Center_X_px Center_Y_px Area_px2 Area_um2 Max_Feret_px Max_Feret_um Detection_Time Saved_Time RAW_File RAW_SHA256 Result_Folder Engine_Version Algorithm_Version Config_Hash Review_Status Notes'''.split()
MANUAL=('Final_Judgement','Standard_Version','Performance_Link','Notes')
_LOCK=RLock()

def filter_metadata(result):
    value=result.extensions.get('filter_metadata',{})
    return dict(value) if isinstance(value,dict) else {}

def validate_filter_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',value):
        raise ValueError('Filter_ID 必须为1–64位字母、数字、-、_或.，不能含空格或路径分隔符')
    return value

def excel_time(value):
    if not value:return None
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d

def finite(v):return isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)
def total(values):
    values=list(values)
    return sum(values) if all(finite(v) for v in values) else None
def maximum(values):
    values=[v for v in values if finite(v)]
    return max(values) if values else None
def feret(d):
    return d.geometry.length_px if d.geometry.length_method in ('MAX_FERET_PIXEL_CENTERS','MAX_FERET') else None

def project(result,saved_at,annotations=None):
    """Copy declared measurements; never classify, recover geometry or infer regions."""
    a=result.algorithm_info;c=result.calibration_info;i=result.input_info
    meta=filter_metadata(result);annotations=annotations or {}
    fid=meta.get('filter_id')
    source='RESULT_METADATA' if fid else None
    if not fid and annotations.get('Filter_ID'):
        fid=validate_filter_id(annotations['Filter_ID']);source='LEDGER_OVERRIDE'
    scale=c.spatial_scale_um_per_px if c.valid and str(c.scale_source)!='UNKNOWN' and finite(c.spatial_scale_um_per_px) and c.spatial_scale_um_per_px>0 else None
    def area(v):return v*scale**2 if scale is not None and finite(v) else None
    def length(v):return v*scale if scale is not None and finite(v) else None
    engine=a.extensions.get('engine',{})
    common=dict(Filter_ID=fid,Result_ID=result.result_id,RAW_File=i.file_name,RAW_SHA256=i.sha256,
        Detection_Time=excel_time(a.run_timestamp),Saved_Time=excel_time(saved_at),
        Result_Folder='output/results/'+result.result_id,Algorithm_Version=a.algorithm_version,
        Config_Hash=a.config_hash,Engine_Version=engine.get('engine_version'),Review_Status='PENDING',Notes=meta.get('notes'))
    large=[d for d in result.defects if str(d.classification.size_grade)=='LARGE']
    medium=[d for d in result.defects if str(d.classification.size_grade)=='MEDIUM']
    la=total(d.geometry.area_px for d in large);ma=total(d.geometry.area_px for d in medium);lm=total([la,ma])
    mx=maximum(d.geometry.area_px for d in result.defects);mf=maximum(feret(d) for d in result.defects)
    summary=dict(common,Sample_ID=i.sample_id,Software_Version=a.software_version,Engine_ID=engine.get('engine_id'),
        Engine_Protocol=engine.get('protocol_version'),Pixel_Size_um=scale,Large_Count=len(large),Medium_Count=len(medium),
        Large_Medium_Count=len(large)+len(medium),Large_Total_Area_px2=la,Medium_Total_Area_px2=ma,
        Large_Medium_Total_Area_px2=lm,Large_Total_Area_um2=area(la),Medium_Total_Area_um2=area(ma),
        Large_Medium_Total_Area_um2=area(lm),Max_Defect_Area_px2=mx,Max_Defect_Area_um2=area(mx),
        Max_Feret_px=mf,Max_Feret_um=length(mf),Record_Status='FORMAL_VERIFIED',Filter_ID_Source=source,
        Scale_Source=str(c.scale_source) if scale is not None else None,Metrologically_Calibrated=c.metrologically_calibrated if scale is not None else None)
    summary.update({k:annotations[k] for k in MANUAL if k in annotations})
    detail=[]
    for d in result.defects:
        if str(d.classification.size_grade) not in ('LARGE','MEDIUM'):continue
        g=d.geometry;b=g.bbox;p=g.center
        detail.append(dict(common,Defect_ID=d.identity.defect_id,Size_Grade=str(d.classification.size_grade),
            Band_ID=d.location.band_id,ROI_Type=d.location.roi_id,BBox_X_px=b.x0 if b else None,
            BBox_Y_px=b.y0 if b else None,BBox_Width_px=b.x1-b.x0 if b else None,BBox_Height_px=b.y1-b.y0 if b else None,
            Center_X_px=p.x if p else None,Center_Y_px=p.y if p else None,Area_px2=g.area_px,Area_um2=area(g.area_px),
            Max_Feret_px=feret(d),Max_Feret_um=length(feret(d))))
    for row in detail:
        if row['Defect_ID'] in annotations.get('_defect_notes',{}):row['Notes']=annotations['_defect_notes'][row['Defect_ID']]
    return summary,detail

def _atomic(path,write):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with NamedTemporaryFile(dir=path.parent,prefix='.ledger_',suffix=path.suffix,delete=False) as f:temp=Path(f.name)
    try:
        write(temp)
        with temp.open('r+b') as f:os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

@dataclass
class HistoryLedgerEntry:
    summary: object
    filter_id: str | None
    def __getattr__(self,key):return getattr(self.summary,key)

class DefectLedger:
    def __init__(self,repository):
        self.repository=repository;self.root=repository.root.parent
        self.path=self.root/'defect_ledger.xlsx';self.annotations=self.root/'ledger_annotations.json'

    def _annotations(self,rebuild):
        values=json.loads(self.annotations.read_text(encoding='utf-8')) if self.annotations.exists() else {}
        if not self.path.exists():return values,False
        try:
            wb=load_workbook(self.path)
            try:
                ws=wb['Filter_Summary'];headers=[c.value for c in ws[1]]
                if headers!=SUMMARY:raise ValueError('未知台账字段版本；请备份后重建')
                for row in ws.iter_rows(min_row=2,values_only=True):
                    d=dict(zip(headers,row));key=d.get('Result_ID')
                    if not key:continue
                    entry={k:d[k] for k in MANUAL if d.get(k) is not None}
                    if d.get('Filter_ID_Source') in ('LEDGER_OVERRIDE',None) and d.get('Filter_ID'):
                        entry['Filter_ID']=validate_filter_id(d['Filter_ID'])
                    values[key]=entry
                ws=wb['Defect_Detail']
                if [c.value for c in ws[1]]!=DETAIL:raise ValueError('Unknown detail columns')
                for row in ws.iter_rows(min_row=2,values_only=True):
                    d=dict(zip(DETAIL,row))
                    if d.get('Result_ID') and d.get('Defect_ID') and d.get('Notes') is not None:
                        values.setdefault(d['Result_ID'],{}).setdefault('_defect_notes',{})[d['Defect_ID']]=d['Notes']
            finally:wb.close()
            return values,True
        except PermissionError:raise
        except Exception:
            if not rebuild:raise ValueError('台账损坏或版本不兼容，请使用“同步/重建检测台账”恢复')
            return values,False

    def sync(self,*,rebuild=False):
        """One row per Result_ID, rebuildable without Excel; all packages verified first."""
        with _LOCK,exclusive_lock(self.root/'.ledger.lock'):
            annotations,valid_old=self._annotations(rebuild)
            rows=[];details=[];seen=set()
            # Scan packages rather than trusting a possibly stale derived repository index.
            for directory in self.repository._formal_dirs():
                r=self.repository.load(directory.name)
                if r.result_id in seen:raise ValueError('重复 Result_ID')
                seen.add(r.result_id)
                m=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
                row,ds=project(r,m['saved_at'],annotations.get(r.result_id));rows.append(row);details.extend(ds)
            rows.sort(key=lambda d:(d['Saved_Time'] or datetime.min,d['Result_ID']))
            order={r['Result_ID']:i for i,r in enumerate(rows)}
            details.sort(key=lambda d:(order[d['Result_ID']],d['Defect_ID']))
            wb=Workbook();wb.remove(wb.active)
            for name,headers,data in [('Filter_Summary',SUMMARY,rows),('Defect_Detail',DETAIL,details)]:
                ws=wb.create_sheet(name);ws.append(headers);ws.freeze_panes='C2';ws.sheet_view.showGridLines=False
                ws.row_dimensions[1].height=44
                for row in data:ws.append([row.get(k) for k in headers])
                ws.auto_filter.ref=ws.dimensions
                for j,key in enumerate(headers,1):
                    ws.column_dimensions[get_column_letter(j)].width={'Result_ID':42,'Result_Folder':68,'RAW_SHA256':70}.get(key,25)
                    for cell in ws.iter_cols(min_col=j,max_col=j):
                        for c in cell:
                            if isinstance(c.value,str):c.data_type='s' # Literal text, including formula-like notes/filenames.
                            c.font=Font(name='Arial',size=10,bold=c.row==1,color='FFFFFF' if c.row==1 else '172B4D')
                            c.alignment=Alignment(vertical='center',wrap_text=c.row==1)
                            if c.row==1:c.fill=PatternFill('solid',fgColor='203864')
                            elif isinstance(c.value,datetime):c.number_format='yyyy-mm-dd hh:mm:ss'
                            elif isinstance(c.value,float):c.number_format='0.000'
            meta=wb.create_sheet('Metadata');meta.append(['Field','Value'])
            for k,v in [('ledger_schema_version',SCHEMA_VERSION),('gui_version','1.0.0'),('last_updated_utc',datetime.now(timezone.utc).isoformat()),
                ('authority','InspectionResult = Source of Truth; Excel = Derived Ledger / Index'),('datetime_timezone','UTC; source offset normalized, offset-free source kept unchanged'),
                ('physical_units','From valid declared result calibration; Scale_Source and Metrologically_Calibrated distinguish configured scale from metrology'),
                ('Feret','Only MAX_FERET / MAX_FERET_PIXEL_CENTERS length_method is exported'),
                ('review_status','PENDING: no aggregation of independent human-review decisions'),
                ('manual_annotations','Final_Judgement, Standard_Version, Performance_Link, Notes copied to ledger_annotations.json on successful sync; save Excel edits before sync')]:meta.append([k,v])
            meta.freeze_panes='A2';meta.auto_filter.ref=meta.dimensions;meta.column_dimensions['A'].width=28;meta.column_dimensions['B'].width=100
            for row in meta:
                for c in row:c.alignment=Alignment(wrap_text=True,vertical='top');c.font=Font(name='Arial',size=10,bold=c.row==1)
                meta.row_dimensions[row[0].row].height=42
            try:
                # Independent annotations survive later XLSX corruption/deletion.
                _atomic(self.annotations,lambda p:p.write_text(json.dumps(annotations,ensure_ascii=False,indent=2),encoding='utf-8'))
                if valid_old:_atomic(self.root/'defect_ledger.backup.xlsx',lambda p:shutil.copyfile(self.path,p))
                _atomic(self.path,lambda p:wb.save(p))
            finally:wb.close()
            return dict(path=str(self.path),summary_rows=len(rows),detail_rows=len(details),status='PASS')
