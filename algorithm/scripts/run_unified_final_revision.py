"""Versioned final reconstruction, RAW recovery, measurement and source audit.

Existing 26_1/26_2 upstream masks are read-only. Every invocation computes a
new final decision from these masks and original RAW; it never re-verifies an
old release in place. The trace explicitly distinguishes upstream reuse.
"""
from pathlib import Path
from datetime import datetime
import sys,json,hashlib,platform
import numpy as np
import pandas as pd
import cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts import run_case03_unified_final_detector_26_1_2 as old
from src.detection.unified_raw_recovery import recover_objects
from src.detection.unified_proposal_selection import select_proposals
from src.visualization.unified_final_boxes import render,comparison
from src.detection.case03i_size_grade import max_feret_centers_px,grade_size,SizeGradeConfig

K8A=C.OUTPUT_ROOT/'case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def write_json(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf8')

def read_png(path):
    return cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)

def negative_objects(frame):
    summary=json.loads((old.OUT/f'26_{frame}/summary.json').read_text(encoding='utf8'))
    excluded=set(summary['all_green_false_review_group_ids'])
    table=pd.read_csv(old.II/f'frame26_{frame}/new_exact_group_union_review.csv')
    result=[]
    for row in table.itertuples(index=False):
        if row.new_group_id in excluded:
            m,b=old.unpack(row.npz_file,'exact_review_union','RAW_global_bbox')
            result.append({'mask':m,'bbox':b,'group_id':row.new_group_id})
    return result

def compute(frame):
    lineage=pd.read_csv(old.I/f'frame26_{frame}/end_to_end_candidate_lineage.csv',low_memory=False)
    raw=np.memmap(C.DATA_ROOT/f'26 ({frame}).raw',mode='r',dtype='>u2',shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    ids=read_png(K8A/f'frame26_{frame}/band_id_fullres.png')
    original=old.build_j5(frame,lineage,{})
    b,green=old.build_b(frame,lineage);original+=b
    negative=negative_objects(frame)
    selected,proposals=select_proposals(frame,list(original),lineage,negative)
    # Stable historical outer proposals are kept; recovery only addresses
    # unresolved B seeds. They remain collision obstacles for recovery.
    selected,recovery=recover_objects(selected,raw,ids,negative)
    final,edges=old.consolidate(selected)
    assert set().union(*(v['sources'] for v in original))<=set().union(*(v['sources'] for v in final))
    return raw,lineage,original,final,negative,proposals,recovery,edges

def export_frame(out,frame,data):
    raw,lineage,original,final,negative,proposals,recovery,edges=data
    dest=out/f'26_{frame}';dest.mkdir()
    masks=dest/'EXACT_FINAL_BINARY_MASKS';masks.mkdir()
    local=dest/'LOCAL_BOXES_ONLY';local.mkdir()
    comparisons=dest/'BEFORE_AFTER_SAME_RAW';comparisons.mkdir()
    binary=np.zeros(raw.shape,np.uint8);records=[];view=[];membership=[];ownership={}
    oldrows=pd.read_csv(old.OUT/f'26_{frame}/FINAL_DEFECTS_AND_MEASUREMENTS.csv') if (old.OUT/f'26_{frame}/FINAL_DEFECTS_AND_MEASUREMENTS.csv').exists() else pd.DataFrame()
    source_rows={r.candidate_source_uid:r for r in lineage.itertuples(index=False)}
    differences=[]
    for i,z in enumerate(final,1):
        uid=f'F{frame}_FINAL_{i:04d}';m=z['mask'];b=z['bbox'];x0,y0,x1,y1=b
        crop=binary[y0:y1,x0:x1];assert not np.any(crop[m]);crop[m]=255
        y,x=np.where(m);area=int(m.sum());length=max_feret_centers_px(np.column_stack([x,y]));grade,_=grade_size(area,length,SizeGradeConfig())
        path=masks/f'{uid}.npz'
        np.savez_compressed(path,mask=np.uint8(m),global_RAW_bbox_xyxy_exclusive=np.int32(b),original_J5_K8B_source_uids=np.array(sorted(z['sources'])))
        record={'final_ID':uid,'frame':frame,'band_id':z['band'],'final_area_detector_px2':area,
                'max_Feret_detector_px':round(length,4),'bbox_xyxy_exclusive':json.dumps(b),'grade':grade,
                'human_confirmed_darkspot':z['user_approved'],'origin_stage':z['kind'],'acceptance_reason':z['reason'],
                'J5_B_or_K8E_sources':';'.join(sorted(z['sources'])),'raw_mask_npz':str(path),
                'area_method':'COUNT_FINAL_MASK_PIXELS_NOT_DISPLAY_BOX','length_method':'MAX_FERET_PIXEL_CENTERS',
                'connected_components':cv2.connectedComponents(np.uint8(m),connectivity=8)[0]-1,
                'physical_boundary_human_accepted':bool(z['user_approved'])}
        records.append(record)
        vr={'final_ID':uid,'bbox':b,'area':area,'length':length,'approved':z['user_approved'],'grade':grade}
        view.append(vr)
        for source in z['sources']:
            assert source not in ownership;ownership[source]=uid
            membership.append({'source_uid':source,'final_ID':uid,'source_area':source_rows[source].source_area_px2,'final_mask_path':str(path)})
        prior=[v for v in original if v['sources']&z['sources']]
        before,beforebox=old.combine(prior)
        exact=old.global_intersection({'mask':before,'bbox':beforebox},z)
        assert exact==int(before.sum()),('Original selected source pixels lost',uid)
        if z['user_approved']:assert area==int(before.sum())
        assert not any(old.global_intersection(z,n) for n in negative)
        differences.append({'final_ID':uid,'source_uids':';'.join(sorted(z['sources'])),'before_objects':len(prior),
                            'before_area':int(before.sum()),'after_area':area,'before_pixels_preserved':exact,
                            'added_pixels':area-exact,'bbox':str(b),'after_length':length})
        pad=35;box=(max(0,min(b[0],beforebox[0])-pad),max(0,min(b[1],beforebox[1])-pad),min(raw.shape[1],max(b[2],beforebox[2])+pad),min(raw.shape[0],max(b[3],beforebox[3])+pad))
        comparison(raw,prior,[z],box,comparisons/f'{uid}.png')
        a=max(0,b[0]-140);c=max(0,b[1]-65);xx=min(raw.shape[1],b[2]+140);yy=min(raw.shape[0],b[3]+65)
        localvr=dict(vr,bbox=(b[0]-a,b[1]-c,b[2]-a,b[3]-c))
        # Local view is native resolution; render uses explicit temporary config.
        localconfig=dict(C.UNIFIED_FINAL)
        try:
            C.UNIFIED_FINAL['display_stride']=1;C.UNIFIED_FINAL['display_font_px']=12
            render(raw[c:yy,a:xx],[localvr],local/f'{uid}.png')
        finally:C.UNIFIED_FINAL.update(localconfig)
    layout=render(raw,view,dest/'00_FINAL_DEFECTS_ONLY_fullframe_1to4.png')
    assert not any(r['box_overlap_pixels'] or r['label_overlap_pixels'] for r in layout),'Main labels collide'
    ok,buf=cv2.imencode('.png',binary);assert ok
    (dest/'01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK_11276x9200.png').write_bytes(buf.tobytes())
    pd.DataFrame(records).to_csv(dest/'FINAL_DEFECTS_AND_MEASUREMENTS.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(membership).to_csv(dest/'final_group_membership.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(layout).to_csv(dest/'render_layout_audit.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(proposals).to_csv(dest/'RAW_proposal_selection_audit.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(recovery).to_csv(dest/'RAW_recovery_gate_audit.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(differences).to_csv(dest/'before_after_objects.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(edges).to_csv(dest/'pixel_overlap_edges.csv',index=False,encoding='utf-8-sig')
    audit=[]
    oldaudit=pd.read_csv(old.OUT/f'26_{frame}/ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv',low_memory=False).set_index('candidate_source_uid')
    negative_uids={}
    group=pd.read_csv(old.II/f'frame26_{frame}/new_exact_group_union_review.csv')
    for n in negative:
        nr=group[group.new_group_id==n['group_id']].iloc[0]
        for v in str(nr.new_source_B_labels).split(';'):
            negative_uids[f'B:F{frame}:B{int(nr.band_id):02d}:C{int(v):07d}']=n['group_id']
    for r in lineage.itertuples(index=False):
        source=r.candidate_source_uid;chosen=ownership.get(source,'')
        trial=[p for p in proposals if p['source_uid']==source]
        rec=[p for p in recovery if source in p['source_uids'].split(';')]
        oldrow=oldaudit.loc[source]
        reason=(next(z['acceptance_reason'] for z in records if z['final_ID']==chosen) if chosen else oldrow['reason'])
        # User negatives are recorded specifically, not as generic low evidence.
        if source in negative_uids:reason='EXPLICIT_USER_NEGATIVE_GROUP_'+negative_uids[source]
        audit.append({'candidate_source_uid':source,'stage':r.stage,'band_id':r.band_id,'source_area_px2':r.source_area_px2,
                      'final_defect_ID':chosen,'decision_reason':reason,'prior_final_ID':str(oldrow.get('final_defect_ID','')),
                      'original_source_mask_preserved':True,'original_source_ledger':str(old.I/f'frame26_{frame}/end_to_end_candidate_lineage.csv'),
                      'raw_proposal_decisions':json.dumps(trial,default=str),'recovery_decisions':json.dumps(rec,default=str),
                      'source_pixels_removed':0,'human_verified_as_noise':False})
    pd.DataFrame(audit).to_csv(dest/'ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv',index=False,encoding='utf-8-sig')
    assert len(audit)==len(lineage) and len({z['candidate_source_uid'] for z in audit})==len(audit)
    summary={'frame':frame,'objects':len(final),'area_px2':int(binary.astype(bool).sum()),'source_rows':len(audit),
             'confirmed_areas':sorted(r['final_area_detector_px2'] for r in records if r['human_confirmed_darkspot']),
             'selected_source_pixels_preserved':True,'all_masks_disjoint':True,'negative_overlap':0,'render_labels_no_collision':True}
    write_json(dest/'acceptance.json',summary)
    print('REVISION_FRAME_COMPLETE',summary,flush=True)
    return summary

def run(run_id=None,frames=(1,2),input_path=None):
    if input_path is not None:
        from scripts.run_unified_raw_input import run_raw
        return run_raw(Path(input_path).resolve(),run_id)
    name=run_id or ('CASE03_UNIFIED_FINAL_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    if Path(name).name!=name:raise ValueError('run-id must be a single directory name')
    out=C.OUTPUT_ROOT/name;out.mkdir(exist_ok=False)
    write_json(out/'config_snapshot.json',C.UNIFIED_FINAL)
    sources=[ROOT/'main.py',ROOT/'config/user_config.py',*list((ROOT/'src').rglob('*.py')),*list((ROOT/'scripts').glob('*.py'))]
    sources += [C.DATA_ROOT/f'26 ({fr}).raw' for fr in frames]
    for fr in frames:
        for folder in (old.J4P[fr],old.J5P[fr],old.I/f'frame26_{fr}',old.K8B/f'frame26_{fr}',old.E/f'frame26_{fr}',old.II/f'frame26_{fr}',old.USR,K8A/f'frame26_{fr}'):
            sources.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix in {'.npz','.csv','.json','.png'})
    manifest=[{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(set(sources))]
    write_json(out/'input_and_code_SHA256.json',manifest)
    try:
        summaries=[export_frame(out,fr,compute(fr)) for fr in frames]
        changed=[m['path'] for m in manifest if sha(m['path'])!=m['sha256']]
        assert not changed,changed
        write_json(out/'execution_trace.json',{'python':sys.version,'platform':platform.platform(),
                  'argv':sys.argv,'mode':'FRESH_FINAL_DECISION_AND_RAW_RECOVERY_WITH_HASHED_FROZEN_UPSTREAM',
                  'J4_J5_recomputed':False,'RAW_recovery_executed':True,'historical_inputs_unchanged':True,'frames':summaries})
        write_json(out/'acceptance.json',{'engineering_checks':'PASS','human_effect_acceptance':'PENDING','frames':summaries})
    except BaseException as e:
        write_json(out/'FAILED.json',{'error':repr(e)});raise
    print('NEW_UNIFIED_RELEASE',out,flush=True)
    return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run-id');p.add_argument('--input',type=Path)
    a=p.parse_args();run(a.run_id,input_path=a.input)
