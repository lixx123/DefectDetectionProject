"""Stable source sets, then exact global mask. Never match by sequential ID."""
from collections import Counter
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
import hashlib, json
import numpy as np
from infrastructure.storage.paths import safe_path
from infrastructure.storage.package import sha256
from .models import RegressionComparison


def plain(value):
    if isinstance(value,Enum): return value.value
    if is_dataclass(value):
        data={f.name:plain(getattr(value,f.name)) for f in fields(value) if f.name!='_unknown_fields'}
        data.update(plain(getattr(value,'_unknown_fields',{})))
        return data
    if isinstance(value,dict): return {str(k):plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [plain(v) for v in value]
    # JSON/domain float decoding must not turn integer text into a semantic delta.
    if isinstance(value,float) and value.is_integer(): return int(value)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(plain(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def content_refs(value):
    if isinstance(value,dict):
        return {k:content_refs(v) for k,v in value.items() if not (k=='path' and 'sha256' in value)}
    if isinstance(value,list): return [content_refs(v) for v in value]
    return value


def mask_signature(defect,directory):
    ref=defect.geometry.mask_reference
    if ref is None: return None
    path=safe_path(directory,ref.path)
    if sha256(path)!=ref.sha256: raise ValueError('object mask resource hash mismatch: '+ref.path)
    with np.load(path,allow_pickle=False) as data:
        mask=np.ascontiguousarray(data['mask']>0,dtype=np.uint8)
        bbox=[int(v) for v in data['global_RAW_bbox_xyxy_exclusive']]
    return digest({'bbox':bbox,'shape':list(mask.shape),'foreground_sha256':hashlib.sha256(mask.tobytes()).hexdigest()})


def normalize_ids(value,mapping):
    if isinstance(value,dict): return {k:normalize_ids(v,mapping) for k,v in value.items()}
    if isinstance(value,list): return [normalize_ids(v,mapping) for v in value]
    if isinstance(value,str): return mapping.get(value,value)
    return value


def semantic_snapshot(result,directory):
    """Compact frozen metadata: candidate semantic digest, not repeated 60 MB JSON."""
    objects=[]; id_map={}
    for defect in result.defects:
        signature=mask_signature(defect,directory)
        token='MASK:'+signature if signature else 'SOURCE:'+digest(sorted(defect.detection.candidate_ids))
        id_map[defect.identity.defect_id]=token
        objects.append({'defect_id':defect.identity.defect_id,'token':token,
            'source_membership':sorted(defect.detection.candidate_ids),'global_mask_signature':signature,
            'bbox':plain(defect.geometry.bbox),'area_px':plain(defect.geometry.area_px),
            'Feret':plain(defect.geometry.length_px),'size_grade':defect.classification.size_grade.value,
            'band_id':defect.location.band_id,'roi_id':defect.location.roi_id,
            'mask_sha256':None if defect.geometry.mask_reference is None else defect.geometry.mask_reference.sha256,
            'semantic':content_refs(plain(defect))})
    for obj in objects:
        obj['semantic']=normalize_ids(obj['semantic'],id_map)
        obj['semantic']['detection']['candidate_ids']=sorted(obj['semantic']['detection']['candidate_ids'])
    candidates=[]; counts=Counter(); reasons=Counter(); anchors={}; micro=Counter()
    for row in result.audit_log.candidates:
        record=normalize_ids(content_refs(plain(row)),id_map)
        candidates.append((row.source,row.candidate_id,record))
        counts[row.disposition.value]+=1; reasons[row.filter_reason.value if row.filter_reason else 'NONE']+=1
        if row.candidate_id=='J5:F1:DEFECT_00001': anchors[row.candidate_id]=record
        raw=row.filter_message or ''
        if ('MICRO_HIDE_SUGGESTION' in raw and 'NO_DELETE' in raw) or ('MICRO_REVIEW' in raw and 'NOT_PROVEN_NOISE' in raw):
            micro[row.disposition.value]+=1
            if row.filter_reason is not None or row.disposition.value not in ('REVIEW','RETAINED','MERGED'):
                raise ValueError('unapproved automatic micro-candidate rejection: '+row.candidate_id)
    candidates.sort(key=lambda row:(row[0],row[1]))
    roi=content_refs(plain(result.roi_info))
    roi['band_list']=sorted(roi['band_list'],key=lambda b:b['band_id'])
    execution=plain(result.execution_info)
    for holder in [execution,*execution['attempts']]:
        for key in ('started_at','finished_at','execution_time_seconds'): holder.pop(key,None)
    algorithm=plain(result.algorithm_info)
    for key in ('run_timestamp','execution_time_seconds','software_version'): algorithm.pop(key,None)
    for key in ('platform','adapter_python'): algorithm.get('runtime_environment',{}).pop(key,None)
    intermediate=content_refs(plain(result.intermediate_results))
    # Annotated previews/CSV byte differences are diagnostics; physical masks are strict.
    supporting={'annotated_image':intermediate.pop('annotated_image',None)}
    extensions=plain(result.extensions)
    for key in ('reference_final_table','reference_acceptance'): supporting[key]=extensions.pop(key,None)
    provenance={key:extensions.pop(key,None) for key in ('mapping_provenance','original_result_id',
        'fresh_engine_execution','remapped_after_audit_reason_revision','algorithm_recomputed_in_this_mapping_step')}
    audit=plain(result.audit_log); audit.pop('candidates',None)
    audit=normalize_ids(content_refs(audit),id_map)
    # Supporting ledger hashes may encode machine run paths; all candidate records remain strict.
    supporting['audit_evidence']=audit['extensions'].pop('evidence',None)
    return {'schema_version':result.schema_version,'input':plain(result.input_info),
        'objects':sorted(objects,key=lambda o:(o['source_membership'],o['token'])),
        'final_mask_sha256':None if result.intermediate_results.final_mask is None else result.intermediate_results.final_mask.sha256,
        'roi':roi,'statistics':plain(result.statistics),'calibration':plain(result.calibration_info),
        'execution':execution,'quality_control':plain(result.quality_control),'algorithm':algorithm,
        'intermediate_physical':intermediate,'extensions':extensions,
        'audit':{'source_candidate_count':result.audit_log.source_candidate_count,
            'lineage_complete':result.audit_log.lineage_complete,
            'fresh_source_count':result.audit_log.extensions.get('fresh_source_count'),
            'historical_source_count':result.audit_log.extensions.get('historical_source_count'),
            'union_source_count':result.audit_log.extensions.get('union_source_count'),
            'disposition_counts':dict(sorted(counts.items())),'filter_reason_counts':dict(sorted(reasons.items())),
            'candidate_semantic_sha256':digest(candidates),'anchors':anchors,'micro_dispositions':dict(sorted(micro.items())),
            'other_audit':audit},
        'supporting_artifacts':supporting,
        'allowed_metadata':{'result_id':result.result_id,'task_id':result.task_id,
            'run_timestamp':result.algorithm_info.run_timestamp,'execution_time_seconds':result.algorithm_info.execution_time_seconds,
            'software_version':result.algorithm_info.software_version,'mapping_provenance':provenance}}


def compare_snapshots(reference,current):
    report=RegressionComparison(); before=reference['objects']; after=current['objects']
    remaining_before=set(range(len(before))); remaining_after=set(range(len(after))); pairs=[]
    for criterion in ('source_membership','global_mask_signature'):
        for i in sorted(remaining_before.copy()):
            value=before[i][criterion]
            if not value: continue
            # Ambiguous source sets do not become an arbitrary match.
            if sum(before[k][criterion]==value for k in remaining_before)!=1: continue
            matches=[j for j in remaining_after if after[j][criterion]==value]
            if len(matches)==1:
                j=matches[0]; pairs.append((i,j)); remaining_before.remove(i); remaining_after.remove(j)
    report.disappeared_objects=[before[i]['defect_id'] for i in sorted(remaining_before)]
    report.added_objects=[after[j]['defect_id'] for j in sorted(remaining_after)]
    def change(name,label,b,a):
        if b!=a:
            getattr(report,name).append({'object':label,'before':b,'after':a})
    for i,j in pairs:
        b,a=before[i],after[j]; label=b['defect_id']
        for field,category in [('bbox','bbox_changes'),('area_px','area_changes'),('Feret','Feret_changes'),
                ('size_grade','grade_changes'),('source_membership','source_membership_changes'),
                ('mask_sha256','mask_changes'),('global_mask_signature','mask_changes'),
                ('band_id','ROI_changes'),('roi_id','ROI_changes'),('semantic','object_semantic_changes')]:
            change(category,label+':'+field,b[field],a[field])
        if b['defect_id']!=a['defect_id']:
            report.info.append({'severity':'INFO','field':'defect_id','before':b['defect_id'],'after':a['defect_id'],'matching_basis':'EXACT_SOURCE_SET_OR_EXACT_GLOBAL_MASK'})
    for field,category in [('roi','ROI_changes'),('audit','audit_changes'),('statistics','statistics_changes'),
            ('execution','execution_changes'),('calibration','calibration_changes'),('quality_control','quality_control_changes'),
            ('final_mask_sha256','mask_changes'),('intermediate_physical','mask_changes'),
            ('algorithm','metadata_changes'),('input','metadata_changes'),('schema_version','metadata_changes'),('extensions','metadata_changes')]:
        change(category,field,reference[field],current[field])
    for category in ('added_objects','disappeared_objects','bbox_changes','area_changes','Feret_changes',
            'grade_changes','source_membership_changes','mask_changes','ROI_changes','audit_changes',
            'statistics_changes','execution_changes','object_semantic_changes','metadata_changes','calibration_changes','quality_control_changes'):
        if getattr(report,category): report.critical_differences.append({'severity':'CRITICAL','category':category,'count':len(getattr(report,category))})
    for field in ('allowed_metadata','supporting_artifacts'):
        if reference[field]!=current[field]: report.info.append({'severity':'INFO','field':field,'message':'non-physical metadata/evidence locator bytes changed'})
    for snapshot in (reference,current):
        plan=next((a['plan'] for a in reversed(snapshot['execution']['attempts']) if a['status']=='SUCCEEDED'),None)
        if plan and plan.get('planned_tiles') is not None and plan.get('full_tiles'):
            planned,full=plan['planned_tiles'],plan['full_tiles']
            if planned>full: report.errors.append('planned_tiles exceeds full_tiles')
            elif snapshot['execution']['final_mode']=='roi-bh' and planned/full>0.9:
                report.warnings.append({'severity':'WARNING','message':'ROI schedule approaches full-frame','planned_tiles':planned,'full_tiles':full})
    old=reference['allowed_metadata'].get('execution_time_seconds'); new=current['allowed_metadata'].get('execution_time_seconds')
    if old and new and new>2*old: report.warnings.append({'severity':'WARNING','message':'runtime exceeds 2x reference; not a physical FAIL','before':old,'after':new})
    return report.finish()


def compare_inspection_results(reference,current,reference_dir,current_dir):
    try:
        before=semantic_snapshot(reference,reference_dir); after=semantic_snapshot(current,current_dir)
        report=compare_snapshots(before,after)
        if report.audit_changes:
            def rows(result,view):
                mapping={o['defect_id']:o['token'] for o in view['objects']}
                return {(r.source,r.candidate_id):normalize_ids(content_refs(plain(r)),mapping) for r in result.audit_log.candidates}
            left,right=rows(reference,before),rows(current,after)
            changed=[key for key in sorted(left.keys()|right.keys()) if left.get(key)!=right.get(key)]
            report.audit_changes.append({'candidate_changes_total':len(changed),'truncated':len(changed)>100,
                'candidates':[{'source':key[0],'candidate_id':key[1],'before':left.get(key),'after':right.get(key)} for key in changed[:100]]})
        return report.finish()
    except Exception as exc: return RegressionComparison(errors=[f'{type(exc).__name__}: {exc}']).finish()
