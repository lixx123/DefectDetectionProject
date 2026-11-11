"""Pixel, tile and exact-mask audits. No detection or pixel repair."""
from pathlib import Path
import json,math
import numpy as np,cv2,pandas as pd
from .common import ROOT,OUT,RAW,read,dump,csvwrite,baseline,verify_sources

def image(p):
    x=cv2.imdecode(np.frombuffer(Path(p).read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if x is None:raise ValueError(p)
    return x
def summary(v):
    a=np.asarray(list(v),float)
    return dict(count=len(a),mean=float(a.mean()) if len(a) else None,median=float(np.median(a)) if len(a) else None,P90=float(np.percentile(a,90)) if len(a) else None,P95=float(np.percentile(a,95)) if len(a) else None,max=float(a.max()) if len(a) else None,sum=float(a.sum()))
def area(rect):x,y,a,b=rect;return (a-x)*(b-y)
def diff(a,b):return sum(int(np.count_nonzero(a[y:y+256]!=b[y:y+256])) for y in range(0,a.shape[0],256))
def audit():
    from src.detection.case03k8a_band_locator import BandLocatorConfig,locate_transmission_bands,rasterize_region_masks
    from scripts.run_case03j4_fullscan import tiles,halo_rect
    from src.detection.two_level_roi import build_plan,intersects
    from config import user_config as C
    b=baseline();raw=np.memmap(RAW,mode='r',dtype='>u2',shape=(9200,11276));h,w=raw.shape
    config=read(b/'config_snapshot.json');assert config['locator']==__import__('dataclasses').asdict(BandLocatorConfig())
    geometry=locate_transmission_bands(raw,BandLocatorConfig());saved=read(b/'band_geometry.json')
    current={k:v for k,v in geometry.items() if k!='profile'}
    # JSON converts shape tuples to lists; compare canonical wire representations.
    geometry_equal=json.loads(json.dumps(current))==saved
    region,bandids=rasterize_region_masks(raw.shape,geometry['bands'],geometry['exterior'],BandLocatorConfig())
    saved_ids=image(b/'band_id_fullres.png');id_diff=diff(bandids,saved_ids);del saved_ids
    saved_region=image(b/'region_type_fullres.png');region_diff=diff(region,saved_region);del saved_region,bandids
    gate=dict(geometry_equal=geometry_equal,band_id_pixel_differences=id_diff,region_type_pixel_differences=region_diff,band_count=len(geometry['bands']))
    dump(OUT/'k8a_recompute_equivalence.json',gate)
    assert geometry_equal and id_diff==0 and region_diff==0,'STOP: saved and recomputed WORK geometry disagree'
    np.save(OUT/'recomputed_region_type.npy',region);del region
    region=np.load(OUT/'recomputed_region_type.npy',mmap_mode='r');counts=np.zeros(4,np.int64)
    for y in range(0,h,256):counts+=np.bincount(region[y:y+256].ravel(),minlength=4)
    dump(OUT/'recomputed_band_geometry.json',current)
    plan=read(b/'detection_plan.json');rebuilt=build_plan(raw.shape,geometry)
    assert plan==json.loads(json.dumps(rebuilt)),'Saved plan differs from recomputed scheduling'
    rects=plan['detection_rectangles'];scheduled={t['tile_id'] for t in plan['tiles']}
    rows=[];tile_rows=[];work_visits=full_visits=core_union=roi_union=0
    base_rows={p.stem:read(p) for p in (b/'upstream_J4/fresh/tile_status').glob('*.json')}
    for tile in tiles(raw.shape,C.CASE03J4_CORE_SIZE_PX):
        name=tile['tile_id'];x0,y0,x1,y1=rect=tile['core_xyxy'];n=area(rect)
        should=any(intersects(rect,r) for r in rects);assert (name in scheduled)==should
        local=region[y0:y1,x0:x1];bc=np.bincount(local.ravel(),minlength=4)
        inside=np.zeros(local.shape,bool)
        for l,t,r,bb in rects:
            if intersects(rect,[l,t,r,bb]):inside[max(t,y0)-y0:min(bb,y1)-y0,max(l,x0)-x0:min(r,x1)-x0]=True
        nr=int(inside.sum());roi_union+=nr;window=halo_rect(rect,raw.shape,C.CASE03J4_HALO_PX);full_visits+=area(window)
        rows.append(dict(tile_id=name,ix=tile['ix'],iy=tile['iy'],scheduled=should,core_pixels=n,WORK_CORE_pixels_in_core=int(bc[2]),WORK_EDGE_pixels_in_core=int(bc[3]),NONWORK_pixels_in_core=int(bc[0]+bc[1]),SHIELD_pixels_in_core=int(bc[1]),expanded_ROI_pixels_in_core=nr,WORK_CORE_fraction=float(bc[2]/n),WORK_EDGE_fraction=float(bc[3]/n),NONWORK_fraction=float((bc[0]+bc[1])/n)))
        if not should:continue
        status=base_rows[name];assert status['core_xyxy']==rect and status['work_xyxy']==list(window)
        core_union+=n;work_visits+=area(window)
        tile_rows.append(dict(tile_id=name,ix=tile['ix'],iy=tile['iy'],**{f'core_{k}':v for k,v in zip(['x0','y0','x1','y1'],rect)},**{f'work_{k}':v for k,v in zip(['x0','y0','x1','y1'],window)},core_pixels=n,work_window_pixels=area(window),core_to_work_window_pixel_ratio=n/area(window),**{k:status[k] for k in ['elapsed_seconds','candidate_pre_gate_H_in_work_area','final_source_core_pixels','source_core_connected_regions','tile_objects','linked_objects','inferred_bridge_pixels']}))
    assert len(rows)==1620 and len(tile_rows)==len(scheduled)==len(base_rows)
    csvwrite(OUT/'j4_schedule_geometry_audit.csv',rows);csvwrite(OUT/'j4_tile_profile.csv',tile_rows)
    groups=[];j4_seconds=read(OUT/'PROFILE_BASELINE_RUN.json')['J4_seconds']
    groupspec=[('H=0',lambda r:r['candidate_pre_gate_H_in_work_area']==0),('H=1..5',lambda r:1<=r['candidate_pre_gate_H_in_work_area']<=5),('H=6..20',lambda r:6<=r['candidate_pre_gate_H_in_work_area']<=20),('H>20',lambda r:r['candidate_pre_gate_H_in_work_area']>20),('objects=0',lambda r:r['tile_objects']==0),('objects>0',lambda r:r['tile_objects']>0)]
    for name,fn in groupspec:
        s=summary(r['elapsed_seconds'] for r in tile_rows if fn(r));groups.append(dict(group=name,**s,J4_wall_fraction=s['sum']/j4_seconds))
    csvwrite(OUT/'j4_tile_group_profile.csv',groups);dump(OUT/'j4_tile_time_summary.json',summary(r['elapsed_seconds'] for r in tile_rows))
    scheduled_rows=[r for r in rows if r['scheduled']]
    spatial=dict(full_pixels=h*w,WORK_CORE_pixels=int(counts[2]),WORK_EDGE_pixels=int(counts[3]),NONWORK_pixels=int(counts[0]+counts[1]),SHIELD_pixels=int(counts[1]),EXTERIOR_NONWORK_pixels=int(counts[0]),WORK_plus_EDGE_pixels=int(counts[2]+counts[3]),expanded_detection_rectangle_union_pixels=roi_union,scheduled_core_union_pixels=core_union,J4_window_visits=work_visits,full_grid_window_visits=full_visits,full_tiles=len(rows),scheduled_tiles=len(scheduled),skipped_tiles=len(rows)-len(scheduled),scheduled_zero_core=sum(r['WORK_CORE_pixels_in_core']==0 for r in scheduled_rows),scheduled_core_fraction_under_10pct=sum(r['WORK_CORE_fraction']<.1 for r in scheduled_rows),scheduled_core_fraction_under_25pct=sum(r['WORK_CORE_fraction']<.25 for r in scheduled_rows),WORK_CORE_fraction=float(counts[2]/(h*w)),scheduled_core_full_ratio=core_union/(h*w),J4_window_full_ratio=work_visits/(h*w),J4_window_WORK_CORE_ratio=float(work_visits/counts[2]),J4_window_scheduled_core_ratio=work_visits/core_union,window_visits_reduction_vs_full_grid=1-work_visits/full_visits,NONWORK_definition='region codes0 EXTERIOR_NONWORK +1 SHIELD; original code counts separately retained')
    # Exact J4 pixels/objects, on original source ownership (not bridges/display masks).
    source_counts=np.zeros(4,np.int64);source_objects=[];points={k:[] for k in [0,1,2,3]}
    for p in sorted((b/'upstream_J4/fresh/tile_masks').glob('*.npz')):
        with np.load(p,allow_pickle=False) as data:
            x0,y0,x1,y1=map(int,data['core_xyxy']);mask=data['source_detected_uint8']>0;labels=data['grouped_source_only_i32']
            assert np.array_equal(labels>0,mask)
            codes=region[y0:y1,x0:x1];source_counts+=np.bincount(codes[mask],minlength=4)
            for code in points:
                yy,xx=np.where(mask&(codes==code));points[code].extend(zip((xx+x0).tolist(),(yy+y0).tolist()))
            for uid in np.unique(labels):
                if uid<=0:continue
                yy,xx=np.where(labels==uid);cc=np.bincount(codes[yy,xx],minlength=4);cx=int(round(float(xx.mean())))+x0;cy=int(round(float(yy.mean())))+y0
                source_objects.append(dict(tile_id=p.stem,object_id=int(uid),pixels=int(len(xx)),WORK_CORE=int(cc[2]),WORK_EDGE=int(cc[3]),NONWORK=int(cc[0]+cc[1]),SHIELD=int(cc[1]),center_x=cx,center_y=cy,center_in_WORK=bool(region[cy,cx]==2),strict_outside=int(cc[0]+cc[1]+cc[3])))
    source_rows=[dict(region=name,pixels=int(count),fraction=float(count/source_counts.sum())) for name,count in [('WORK_CORE',source_counts[2]),('WORK_EDGE',source_counts[3]),('NONWORK',source_counts[0]+source_counts[1])]]
    csvwrite(OUT/'j4_source_pixels_by_region.csv',source_rows);csvwrite(OUT/'j4_source_objects_by_region.csv',source_objects)
    spatial['J4_source_region_counts']=source_rows
    spatial['J4_objects']=dict(total=len(source_objects),entirely_WORK_CORE=sum(r['strict_outside']==0 for r in source_objects),cross_CORE_EDGE=sum(r['WORK_CORE']>0 and r['WORK_EDGE']>0 for r in source_objects),containing_NONWORK=sum(r['NONWORK']>0 for r in source_objects),center_in_WORK_mask_outside=sum(r['center_in_WORK'] and r['strict_outside']>0 for r in source_objects),center_outside_WORK=sum(not r['center_in_WORK'] for r in source_objects),center_definition='rounded centroid of exact grouped-source pixel centers')
    final_rows=[];final_points=[];union=np.lib.format.open_memmap(OUT/'audited_final_union.npy',mode='w+',dtype=np.uint8,shape=raw.shape);union[:]=0
    table=pd.read_csv(b/'FINAL_DEFECTS_AND_MEASUREMENTS.csv')
    for row in table.to_dict('records'):
        p=b/'EXACT_FINAL_BINARY_MASKS'/(row['final_ID']+'.npz')
        with np.load(p,allow_pickle=False) as d:
            mask=d['mask']>0;x0,y0,x1,y1=map(int,d['global_RAW_bbox_xyxy_exclusive'])
            yy,xx=np.where(mask);cc=np.bincount(region[y0:y1,x0:x1][mask],minlength=4)
            assert mask.sum()==row['final_area_detector_px2'] and not np.any(union[y0:y1,x0:x1][mask])
            union[y0:y1,x0:x1][mask]=255;final_points.extend(zip((xx+x0).tolist(),(yy+y0).tolist()))
            cx=x0+int(round(float(xx.mean())));cy=y0+int(round(float(yy.mean())))
            final_rows.append(dict(final_ID=row['final_ID'],area=int(mask.sum()),WORK_CORE=int(cc[2]),WORK_EDGE=int(cc[3]),NONWORK=int(cc[0]+cc[1]),SHIELD=int(cc[1]),outside_WORK_CORE=int(cc[0]+cc[1]+cc[3]),outside_WORK_plus_EDGE=int(cc[0]+cc[1]),center_in_WORK=bool(region[cy,cx]==2),source_uids=row['source_uids']))
    union.flush();saved_final=image(b/'01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png');union_diff=diff(union,saved_final);del saved_final;assert union_diff==0
    csvwrite(OUT/'final_mask_workband_audit.csv',final_rows)
    spatial['final']=dict(objects=len(final_rows),area=sum(r['area'] for r in final_rows),outside_WORK_CORE=sum(r['outside_WORK_CORE'] for r in final_rows),outside_WORK_plus_EDGE=sum(r['outside_WORK_plus_EDGE'] for r in final_rows),objects_outside_CORE=sum(r['outside_WORK_CORE']>0 for r in final_rows),objects_containing_NONWORK=sum(r['NONWORK']>0 for r in final_rows),saved_final_union_pixel_difference=union_diff)
    dump(OUT/'spatial_audit_summary.json',spatial)
    dump(OUT/'figure_points.json',dict(source={str(k):v for k,v in points.items()},final=final_points))
    verify_sources();print('K8A_PIXEL_GATE_AND_SPATIAL_AUDIT_PASS',spatial['final'],flush=True)
