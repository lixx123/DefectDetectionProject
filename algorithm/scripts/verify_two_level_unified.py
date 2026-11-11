"""Independent pixel/member-set/measurement QA against frozen full-frame data.

No detector output is trusted by count alone. Diagnostics are written before
raising; any WORK/final mismatch blocks acceptance and subsequent runs.
"""
from pathlib import Path
import sys,json,ast,inspect
import numpy as np
import pandas as pd
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_unified_final_revision import write_json,sha,negative_objects
from scripts import run_case03_unified_final_detector_26_1_2 as old
from scripts.run_two_level_unified import member_signatures
from src.detection.case03i_size_grade import max_feret_centers_px
from src.visualization.unified_final_boxes import render,comparison


def read_png(path):
    a=cv2.imdecode(np.frombuffer(Path(path).read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if a is None:raise AssertionError('PNG decode failed: '+str(path))
    return a


def verify(out,frame,reference=None):
    out=Path(out);reference=Path(reference) if reference else C.OUTPUT_ROOT/f'UNIFIED_FRESH_RAW_26_{frame}_20261019_v1'
    qa=out/'independent_QA';qa.mkdir(exist_ok=False)
    plan=json.loads((out/'detection_plan.json').read_text(encoding='utf8'))
    summary=json.loads((out/'acceptance.json').read_text(encoding='utf8'))
    j4=out/'upstream_J4/fresh';j5=out/'upstream_J5/fresh'
    rj4=reference/'upstream_J4/fresh';rj5=reference/'upstream_J5/fresh'
    fused=np.load(out/'fused_blackhat.npy',mmap_mode='r');ref=np.load(reference/'fused_blackhat.npy',mmap_mode='r')
    errors=[];tiles=[];response_differences=source_differences=0
    for t in plan['tiles']:
        name=t['tile_id'];status=json.loads((j4/'tile_status'/(name+'.json')).read_text(encoding='utf8'))
        x,y,a,b=status['work_xyxy'];bh_diff=int(np.count_nonzero(fused[y:b,x:a]!=ref[y:b,x:a]));response_differences+=bh_diff
        different={}
        with np.load(j4/'tile_masks'/(name+'.npz')) as cur,np.load(rj4/'tile_masks'/(name+'.npz')) as previous:
            for key in cur.files:
                n=int(np.count_nonzero(cur[key]!=previous[key]));different[key]=n
                if n:
                    np.savez_compressed(qa/(name+'_'+key+'_DIFFERENCE.npz'),before=previous[key],after=cur[key])
            source_differences+=different.get('grouped_source_only_i32',0)
        tiles.append({'tile_id':name,'BlackHat_diff_pixels':bh_diff,**different})
    pd.DataFrame(tiles).to_csv(qa/'ALL_EXECUTED_TILE_PIXEL_COMPARISONS.csv',index=False,encoding='utf-8-sig')
    if any(any(v for k,v in r.items() if k!='tile_id') for r in tiles):errors.append('BH_OR_J4_PIXEL_OR_LABEL_CHANGED')
    types=read_png(out/'region_type_fullres.png');ids=read_png(out/'band_id_fullres.png')
    if not np.array_equal(ids,read_png(reference/'band_id_fullres.png')):errors.append('K8A_ID_CHANGED')
    newsig=member_signatures(j5);oldsig=member_signatures(rj5);reverse={v:k for k,v in newsig.items()}
    before=pd.read_csv(rj5/'global_defects.csv');after=pd.read_csv(j5/'global_defects.csv').set_index('global_defect_id')
    members=[]
    for z in before.itertuples(index=False):
        x,y=int(z.source_bbox_x_global),int(z.source_bbox_y_global);w,h=int(z.source_bbox_width_px),int(z.source_bbox_height_px)
        region=types[y:y+h,x:x+w];required=bool(np.any((region==2)|(region==3)))
        current=reverse.get(oldsig[z.global_defect_id]);row={'historical_ID':z.global_defect_id,'current_ID':current or '',
            'touches_WORK_or_EDGE_bbox':required,'exact_member_set':current is not None}
        if current:
            q=after.loc[current]
            for col in ['source_area_px2','source_max_feret_px','source_bbox_x_global','source_bbox_y_global','source_bbox_width_px','source_bbox_height_px']:
                row[col+'_delta']=float(q[col])-float(getattr(z,col))
                if required and abs(row[col+'_delta'])>1e-6:errors.append('WORK_J5_MEASUREMENT_CHANGED')
        elif required:errors.append('WORK_EDGE_J5_MEMBERS_CHANGED')
        row['reason']='EXACT_RECOMPUTATION' if current else 'OUTSIDE_WORK_HISTORICAL_ARCHIVE_NOT_RESCANNED_OR_PARTIAL_ROI'
        members.append(row)
    pd.DataFrame(members).to_csv(qa/'ALL_HISTORICAL_J5_MEMBERSHIP_AND_SIZE_DIFF.csv',index=False,encoding='utf-8-sig')
    # K8B seed masks are independently compared, including all micro candidates.
    for p in (out/'upstream_K8BCD').glob('band*/B_SOURCE_ALL.png'):
        if not np.array_equal(read_png(p),read_png(reference/p.relative_to(out))):errors.append('K8B_SOURCE_PIXELS_CHANGED')
    oldtable=pd.read_csv(reference/'FINAL_DEFECTS_AND_MEASUREMENTS.csv').set_index('final_ID')
    table=pd.read_csv(out/'FINAL_DEFECTS_AND_MEASUREMENTS.csv');diffs=[];objects=[]
    for z in table.itertuples(index=False):
        with np.load(z.mask_path) as a:
            mask=a['mask']>0;bbox=tuple(map(int,a['global_RAW_bbox_xyxy_exclusive']))
        y,x=np.where(mask);feret=max_feret_centers_px(np.column_stack([x,y]));area=int(mask.sum())
        if area!=z.final_area_detector_px2 or abs(feret-z.max_Feret_detector_px)>1e-6:errors.append('FINAL_MEASUREMENT_NOT_MASK')
        item={'bbox':bbox,'mask':mask};objects.append(item)
        if z.final_ID not in oldtable.index:errors.append('NEW_FINAL_ID');continue
        previous=oldtable.loc[z.final_ID]
        with np.load(previous.mask_path) as a:
            equal=np.array_equal(mask,a['mask']>0) and np.array_equal(bbox,a['global_RAW_bbox_xyxy_exclusive'])
        equal=bool(equal and z.source_uids==previous.source_uids)
        diffs.append({'final_ID':z.final_ID,'mask_and_sources_equal':equal,
            'area_delta':area-int(previous.final_area_detector_px2),'Feret_delta':feret-float(previous.max_Feret_detector_px),
            'bbox_equal':json.loads(z.bbox_xyxy_exclusive)==json.loads(previous.bbox_xyxy_exclusive),
            'reason':'UNCHANGED_EXACT_MASK_AND_SOURCES' if equal else 'BLOCKED_REQUIRES_CAUSAL_ANALYSIS'})
        if not equal:errors.append('FINAL_MASK_OR_SOURCES_CHANGED')
    if set(table.final_ID)!=set(oldtable.index):errors.append('FINAL_ID_SET_CHANGED')
    pd.DataFrame(diffs).to_csv(qa/'ALL_FINAL_OBJECT_MEASUREMENT_DIFF.csv',index=False,encoding='utf-8-sig')
    binary=read_png(out/'01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png')
    oldbin=read_png(reference/'01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png')
    finaldiff=int(np.count_nonzero(binary!=oldbin))
    if finaldiff:
        base=qa/'FINAL_BINARY_DIFF.png';ok,b=cv2.imencode('.png',np.uint8(binary!=oldbin)*255);assert ok;base.write_bytes(b.tobytes())
        errors.append('FINAL_FULLRES_BINARY_CHANGED')
    # Direct immutable approval and negative-mask QA (not just area counts).
    lineage=pd.read_csv(old.I/f'frame26_{frame}/end_to_end_candidate_lineage.csv',low_memory=False)
    approved=[z for z in old.build_b(frame,lineage)[0] if z['user_approved']]
    approvals=[]
    for a in approved:
        matching=[z for z in objects if old.global_intersection(z,a)==int(a['mask'].sum()) and int(z['mask'].sum())==int(a['mask'].sum())]
        approvals.append({'area':int(a['mask'].sum()),'pixel_exact_single_match':len(matching)==1})
        if len(matching)!=1:errors.append('APPROVED_MASK_CHANGED')
    negative=negative_objects(frame)
    conflicts=sum(old.global_intersection(z,n) for z in objects for n in negative)
    if conflicts:errors.append('HUMAN_NEGATIVE_REINTRODUCED')
    audit=pd.read_csv(out/'ALL_HISTORICAL_SOURCE_DISPOSITIONS_NO_DROP.csv',low_memory=False)
    if len(audit)!=len(lineage) or audit.candidate_source_uid.duplicated().any() or set(audit.candidate_source_uid)!=set(lineage.candidate_source_uid):errors.append('HISTORICAL_SOURCE_LOSS')
    if sha(out/'HISTORICAL_ALL_SOURCE_LINEAGE_UNCHANGED.csv')!=sha(old.I/f'frame26_{frame}/end_to_end_candidate_lineage.csv'):errors.append('HISTORICAL_ARCHIVE_BYTES_CHANGED')
    layout=pd.read_csv(out/'render_layout_audit.csv')
    if layout.box_overlap_pixels.sum() or layout.label_overlap_pixels.sum() or layout.mask_contour_drawn.any():errors.append('RENDER_COLLISION_OR_CONTOURS')
    tree=ast.parse(inspect.getsource(render));calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    if calls&{'drawContours','polylines','findContours'}:errors.append('RENDER_CONTOUR_CALL')
    image=read_png(out/'00_FINAL_DEFECTS_ONLY_fullframe_1to4.png')
    priorimage=read_png(reference/'00_FINAL_DEFECTS_ONLY_fullframe_1to4.png')
    cv2.imencode('.png',np.hstack([priorimage,image]))[1].tofile(qa/'BEFORE_AFTER_FINAL_RECTANGLES.png')
    if frame==1:
        raw=np.memmap(C.DATA_ROOT/'26 (1).raw',dtype='>u2',mode='r',shape=ids.shape)
        previous=[]
        for z in oldtable.itertuples():
            with np.load(z.mask_path) as a:
                previous.append({'mask':a['mask']>0,'bbox':tuple(map(int,a['global_RAW_bbox_xyxy_exclusive']))})
        comparison(raw,previous,objects,(5180,4460,5390,4750),qa/'F1_FINAL_0029_RAW_BEFORE_AFTER.png')
    state=json.loads((j4/'run_status.json').read_text(encoding='utf8'))
    result={'status':'PASS' if not errors else 'STOP_DETECTION_REGRESSION','errors':sorted(set(errors)),
        'frame':frame,'reference':str(reference),'BH_work_window_diff_pixels_with_repeats':response_differences,
        'J4_grouped_source_diff_pixels':source_differences,'verified_tiles':len(tiles),
        'WORK_EDGE_J5_required':sum(r['touches_WORK_or_EDGE_bbox'] for r in members),
        'final_binary_diff_pixels':finaldiff,'final_objects':len(table),'approved_masks':approvals,
        'negative_conflict_pixels':conflicts,'historical_source_rows':len(audit),
        'historical_not_recomputed_rows':int(audit.execution_disposition.str.startswith('HISTORICAL').sum()),
        'actual_tile_files':len(list((j4/'tile_masks').glob('*.npz'))),
        'actual_scheduled_complete':state['completed_tiles']==summary['actual_fresh_J4_tiles']==len(plan['tiles'])}
    write_json(qa/'QA.json',result)
    if errors:raise AssertionError(result)
    print('INDEPENDENT_QA_PASS',out,result,flush=True)
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--frame',required=True,type=int)
    p.add_argument('--reference',type=Path);a=p.parse_args();verify(a.output,a.frame,a.reference)
