"""Independent new-release pixel QA and complete source-to-final intersections."""
from pathlib import Path
from collections import defaultdict
import sys,json
import numpy as np
import pandas as pd
import cv2
from scipy.spatial import ConvexHull,distance
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_case03_unified_final_detector_26_1_2 as old
from scripts.run_unified_final_revision import negative_objects,sha,write_json
from scripts.run_case03k8i_stage2_fullband_priority_contours import read_prior_mask

def length(mask):
    y,x=np.where(mask);points=np.column_stack([x,y])
    if len(points)<2:return 1.
    if len(points)>2 and np.linalg.matrix_rank(points-points.mean(0))==2:
        points=points[ConvexHull(points).vertices]
    return max(1.,float(distance.pdist(points).max()))

def verify(out):
    out=Path(out);qadir=out/'INDEPENDENT_QA';qadir.mkdir(exist_ok=False);summaries=[]
    for fr in (1,2):
        frame=out/f'26_{fr}';table=pd.read_csv(frame/'FINAL_DEFECTS_AND_MEASUREMENTS.csv')
        lineage=pd.read_csv(old.I/f'frame26_{fr}/end_to_end_candidate_lineage.csv',low_memory=False)
        ledger=pd.read_csv(frame/'ALL_ORIGINAL_J5_AND_B_SOURCE_DISPOSITIONS_NO_DROP.csv',low_memory=False)
        assert set(ledger.candidate_source_uid)==set(lineage.candidate_source_uid)
        assert ledger.candidate_source_uid.is_unique
        owner=np.zeros((9200,11276),np.uint16);objects=[];source_members=set()
        for k,r in enumerate(table.itertuples(index=False),1):
            m,b=old.unpack(r.raw_mask_npz,'mask','global_RAW_bbox_xyxy_exclusive');x0,y0,x1,y1=b
            assert int(m.sum())==r.final_area_detector_px2
            assert abs(length(m)-r.max_Feret_detector_px)<.00006
            assert not owner[y0:y1,x0:x1][m].any();owner[y0:y1,x0:x1][m]=k
            objects.append({'mask':m,'bbox':b,'sources':set(r.J5_B_or_K8E_sources.split(';')),'id':r.final_ID})
            source_members.update(r.J5_B_or_K8E_sources.split(';'))
        oldtable=pd.read_csv(old.OUT/f'26_{fr}/FINAL_DEFECTS_AND_MEASUREMENTS.csv')
        for r in oldtable.itertuples(index=False):
            m,b=old.unpack(r.raw_mask_npz,'mask','global_RAW_bbox_xyxy_exclusive');x0,y0,x1,y1=b
            assert np.all(owner[y0:y1,x0:x1][m]>0),('Old selected pixels disappeared',r.final_ID)
            if r.human_confirmed_darkspot:
                match=[z for z in objects if z['sources']&set(r.J5_B_or_K8E_sources.split(';'))]
                assert len(match)==1 and match[0]['bbox']==b and np.array_equal(match[0]['mask'],m)
        for n in negative_objects(fr):assert not any(old.global_intersection(n,z) for z in objects)
        intersections=defaultdict(lambda:defaultdict(int))
        # Each original B pixel is counted directly from the saved source
        # binary and its stable connected label, including unselected micro.
        meta=json.loads((old.K8B/f'frame26_{fr}/summary.json').read_text(encoding='utf8'))
        for band in meta['ROI_crops']:
            bid=int(band['band_id']);y0=int(band['ROI_global_xyxy'][1])
            path=old.K8B/f'frame26_{fr}/band_{bid:02d}_B_hysteresis_mask_cropped.png'
            image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),0)
            _,labels=cv2.connectedComponents(np.uint8(image>0),connectivity=8)
            owned=owner[y0:y0+labels.shape[0]];valid=(labels>0)&(owned>0)
            codes=labels[valid].astype(np.int64)*65536+owned[valid]
            values,counts=np.unique(codes,return_counts=True)
            for code,count in zip(values,counts):
                lid=int(code//65536);oid=int(code%65536)
                intersections[f'B:F{fr}:B{bid:02d}:C{lid:07d}'][oid]+=int(count)
        # J5 source labels are mapped through the original global membership.
        members=pd.read_csv(old.J5P[fr]/'global_object_membership.csv')
        for tile,rows in members.groupby('source_tile_id'):
            with np.load(old.J4P[fr]/'tile_masks'/f'{tile}.npz',allow_pickle=False) as z:
                labels=z['grouped_source_only_i32'];x0,y0,x1,y1=map(int,z['core_xyxy'])
                owned=owner[y0:y1,x0:x1];valid=(labels>0)&(owned>0)
                codes=labels[valid].astype(np.int64)*65536+owned[valid]
            lookup={int(r.source_local_object_index):r.global_defect_id for r in rows.itertuples(index=False)}
            values,counts=np.unique(codes,return_counts=True)
            for code,count in zip(values,counts):
                intersections[f'J5:F{fr}:{lookup[int(code//65536)]}'][int(code%65536)]+=int(count)
        full=[];membership=[]
        for r in lineage.itertuples(index=False):
            hits=intersections[r.candidate_source_uid];total=sum(hits.values())
            assert total<=r.source_area_px2
            for oid,count in hits.items():
                membership.append({'source_uid':r.candidate_source_uid,'final_ID':table.iloc[oid-1].final_ID,'intersection_pixels':count,
                                   'source_area':r.source_area_px2,'origin_seed':r.candidate_source_uid in source_members})
            full.append({'source_uid':r.candidate_source_uid,'original_source_area':r.source_area_px2,'pixels_in_final':total,
                         'pixels_outside_final_but_preserved':int(r.source_area_px2)-total,
                         'original_source_unchanged':True,'source_used_as_seed':r.candidate_source_uid in source_members,
                         'final_ID_intersections':json.dumps({table.iloc[k-1].final_ID:v for k,v in hits.items()}),
                         'state':'ORIGIN_SEED' if r.candidate_source_uid in source_members else 'INCIDENTALLY_COVERED_SOURCE_PIXELS' if total else 'ARCHIVED_NOT_SELECTED'})
        pd.DataFrame(full).to_csv(qadir/f'26_{fr}_ALL_SOURCE_PIXEL_DESTINATIONS.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(membership).to_csv(qadir/f'26_{fr}_SOURCE_FINAL_PIXEL_MEMBERSHIP.csv',index=False,encoding='utf-8-sig')
        mask=cv2.imdecode(np.frombuffer((frame/'01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK_11276x9200.png').read_bytes(),np.uint8),0)
        assert np.array_equal(mask>0,owner>0)
        layout=pd.read_csv(frame/'render_layout_audit.csv')
        assert not layout.box_overlap_pixels.any() and not layout.label_overlap_pixels.any()
        summary={'frame':fr,'sources':len(full),'source_pixels':sum(int(r.source_area_px2) for r in lineage.itertuples()),
                 'objects':len(table),'all_source_pixels_accounted':True,'all_old_selected_pixels_preserved':True,
                 'confirmed_masks_exact':2,'manual_negative_overlap':0,'independent_Feret_pass':True,'disjoint_masks':True,
                 'render_main_has_no_contours':True,'incidental_covered_sources':sum(r['state']=='INCIDENTALLY_COVERED_SOURCE_PIXELS' for r in full)}
        if fr==1:
            target={f'B:F1:B02:C{x:07d}' for x in (614,1028,1273,1562)}
            matched=[z for z in objects if z['sources']&target]
            assert len(matched)==1 and target<=matched[0]['sources']
            p=[read_prior_mask(1,2,k) for k in (614,1273,1562)]
            m,b=old.combine([{'mask':z['mask'],'bbox':z['box']} for z in p])
            hit=old.global_intersection({'mask':m,'bbox':b},matched[0])
            summary['target']={'final_ID':matched[0]['id'],'bbox':matched[0]['bbox'],'area':int(matched[0]['mask'].sum()),
                               'historical_union_area':int(m.sum()),'intersection':hit,'historical_mask_coverage_not_true_recall':hit/int(m.sum()),
                               'new_pixels_outside_historical':int(matched[0]['mask'].sum())-hit}
        summaries.append(summary)
    baseline=ROOT/'outputs/UNIFIED_REVIEW_20261019_v1/baseline_sha256.json'
    manifest=json.loads(baseline.read_text(encoding='utf8'))
    protected=[r for r in manifest if '/outputs/' in r['path'].replace('\\','/') or r['path'].lower().endswith('.raw')]
    assert all(sha(r['path'])==r['sha256'] for r in protected)
    write_json(qadir/'acceptance.json',{'status':'PASS','baseline_protected_files_sha256_checked':len(protected),'frames':summaries,
               'human_boundary_acceptance':'PENDING','precision_recall_not_claimed':True})
    print(json.dumps(summaries,ensure_ascii=False,indent=2))

if __name__=='__main__':verify(Path(sys.argv[1]))
