"""Bounded, source-anchored RAW recovery for the final object backend.

No new candidate seeds, morphology, inferred bridge area, or relaxed global
thresholds. A shared connected RAW residual must cover each source. The old
single-center radial cap is replaced by distance to the actual source union;
touching that bound still rejects the proposal. Approved masks are immutable.
"""
import json
import cv2
import numpy as np
from scipy import ndimage
from config import user_config as C
from src.detection.case03k3_spot_contour_pilot import robust_outer_plane

def bbox_gap(a,b):
    return max(0,a[0]-b[2],b[0]-a[2],a[1]-b[3],b[1]-a[3])

def recover_objects(objects,raw,band_ids,negative_masks=(),config=None):
    """Return source-conserving objects and all trial decisions, in RAW pixels."""
    from scripts.run_case03_unified_final_detector_26_1_2 import combine,item,global_intersection
    cfg=dict(C.UNIFIED_FINAL if config is None else config)
    eligible=[i for i,z in enumerate(objects) if not z['user_approved'] and z['kind'].startswith('B_')]
    parent={i:i for i in eligible}
    def root(i):
        while parent[i]!=i: i=parent[i]
        return i
    for n,i in enumerate(eligible):
        for j in eligible[n+1:]:
            if objects[i]['band']==objects[j]['band'] and bbox_gap(objects[i]['bbox'],objects[j]['bbox'])<=cfg['recovery_max_pair_bbox_gap_px']:
                parent[root(j)]=root(i)
    groups={}
    for i in eligible: groups.setdefault(root(i),[]).append(i)
    replacements={}; consumed=set(); audit=[]
    for indices in groups.values():
        parts=[objects[i] for i in indices]
        seed,bb=combine(parts); pad=cfg['recovery_background_outer_px']+4
        x0=max(0,bb[0]-pad);y0=max(0,bb[1]-pad)
        x1=min(raw.shape[1],bb[2]+pad);y1=min(raw.shape[0],bb[3]+pad)
        row={'source_uids':';'.join(sorted(set().union(*(v['sources'] for v in parts)))),
             'roi':json.dumps([x0,y0,x1,y1]),'prior_area_px2':int(seed.sum()),'accepted':False}
        def reject(reason):
            row['reason']=reason;audit.append(row)
        if max(x1-x0,y1-y0)>cfg['recovery_max_roi_px']:
            reject('ROI_TOO_LARGE');continue
        source=np.zeros((y1-y0,x1-x0),bool)
        source[bb[1]-y0:bb[3]-y0,bb[0]-x0:bb[2]-x0]=seed
        dist=ndimage.distance_transform_edt(~source)
        band=int(parts[0]['band']); core=band_ids[y0:y1,x0:x1]==band
        ring=(dist>=cfg['recovery_background_inner_px'])&(dist<=cfg['recovery_background_outer_px'])&core
        if ring.sum()<500:
            reject('INSUFFICIENT_SAME_BAND_BACKGROUND');continue
        data=np.asarray(raw[y0:y1,x0:x1],np.float32)
        yy,xx=np.mgrid[:data.shape[0],:data.shape[1]]
        plane=robust_outer_plane(data,xx-data.shape[1]/2,yy-data.shape[0]/2,ring)
        if len(parts)>1:
            # 多源细长目标跨行背景不满足单平面假设。使用受原候选锚定的
            # 多尺度RAW暗响应；不独立产生Gaussian候选，仍受CORE/距离保护。
            plane=cv2.GaussianBlur(data,(0,0),cfg['recovery_line_background_sigma_px'])
        residual=plane-cv2.GaussianBlur(data,(0,0),1.3)
        vals=residual[ring];center=float(np.median(vals))
        sigma=max(cfg['recovery_min_sigma_dn'],1.4826*float(np.median(abs(vals-center))))
        peak=float(np.percentile(residual[source],99))
        threshold=max(center+cfg['recovery_sigma_multiplier']*sigma,cfg['recovery_peak_fraction']*peak)
        support=residual>=threshold
        labels,count=ndimage.label(support,np.ones((3,3)))
        ids=np.unique(labels[source]);ids=ids[ids>0]
        row.update(sigma_dn=sigma,threshold_dn=threshold,peak_dn=peak,raw_component_count=len(ids))
        # One shared RAW component is required; disconnected spots stay separate.
        proposed=None
        for label in ids:
            component=labels==label
            fractions=[]
            for part in parts:
                a,b,c,d=part['bbox']; pm=part['mask']
                fractions.append(float(np.count_nonzero(component[b-y0:d-y0,a-x0:c-x0]&pm)/pm.sum()))
            if min(fractions)>=cfg['recovery_min_seed_coverage']:
                proposed=component;row['seed_coverages']=json.dumps(fractions);break
        if proposed is None:
            reject('NO_SHARED_RAW_COMPONENT_COVERING_ALL_SEEDS');continue
        row['proposed_area_px2']=int(proposed.sum())
        if np.any(proposed&~core):
            reject('RAW_COMPONENT_CROSSES_WORK_CORE');continue
        if np.any(proposed&(dist>=cfg['recovery_seed_distance_px']-1)):
            reject('RAW_COMPONENT_REACHES_SOURCE_DISTANCE_CAP');continue
        if proposed[0].any() or proposed[-1].any() or proposed[:,0].any() or proposed[:,-1].any():
            reject('RAW_COMPONENT_TOUCHES_ROI');continue
        candidate=proposed|source
        points=np.column_stack(np.where(proposed)[::-1]).astype(np.float32)
        short=min(cv2.minAreaRect(points)[1]) if len(points)>2 else 0
        row['short_axis_px']=float(short)
        if short>cfg['recovery_max_short_axis_px'] or candidate.sum()>cfg['recovery_max_area_px2']:
            reject('WIDTH_OR_ABSOLUTE_AREA_LIMIT');continue
        if candidate.sum()>cfg['max_raw_growth_ratio']*source.sum():
            reject('SOURCE_UNION_GROWTH_LIMIT');continue
        result=item(candidate,(x0,y0,x1,y1),'B_RAW_BOUNDED_RECOVERY',
                    set().union(*(v['sources'] for v in parts)),band,False,
                    'SHARED_CONNECTED_RAW_3SIGMA_SOURCE_DISTANCE_BOUNDED',2)
        others=[z for j,z in enumerate(objects) if j not in indices]
        if any(global_intersection(result,z) for z in [*others,*negative_masks]):
            reject('OTHER_OBJECT_OR_HUMAN_NEGATIVE_CONFLICT');continue
        if candidate.sum()<=source.sum():
            reject('NO_ADDITIONAL_RAW_SUPPORT');continue
        replacements[indices[0]]=result;consumed.update(indices[1:])
        row.update(accepted=True,reason=result['reason'],final_area_px2=int(candidate.sum()))
        audit.append(row)
    return [replacements.get(i,z) for i,z in enumerate(objects) if i not in consumed],audit
