"""Case03-J4: full RAW core-tile scan, local objectization and external boxes.

Case03-J5 (NOT implemented here) alone will merge across core boundaries
and assign final physical-defect IDs. This file deliberately never calls
a global union-find and never claims whole-object completeness at tile edges.

Existing fixed 170/230 + Case03E2 anchored bounded refinements and the
Case03-F/G/H gates are used unchanged via Case03-T fixed process_one.

Memory: RAW is read-only big-endian memmap. The fused Black-Hat input may be
either a legacy full-frame response or the current two-level ROI response.
For every scheduled tile, the complete core+halo work window must be computed
and pixel-equivalent to a full-frame Black-Hat result; uncomputed sentinel
pixels are rejected before detection. Workers process one core+halo tile at a
time and commit manifests atomically.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from stage_process import policies,process_one
from src.detection.case03i_size_grade import SizeGradeConfig,extract_regions
from src.detection.case03j_fragment_association import AssociationConfig,associate_fragments
from src.detection.case03j_continuous_contour import (
    ContinuousConfig,reconstruct_continuous_visual
)
from src.detection.two_level_roi import require_computed_response
from src.visualization.case03j_object_boxes import (
    BoxStyle,measure_visual_bbox,render_grouped_box_comparison
)
from scripts.run_case03g_joint_noise_refinement import save_png,gray

def halo_rect(rect:list[int],shape:tuple[int,int],halo:int,
              min_work_size:int=192)->tuple[int,int,int,int]:
    x0,y0,x1,y1=rect;H,W=shape
    l=max(0,x0-halo);t=max(0,y0-halo)
    r=min(W,x1+halo);b=min(H,y1+halo)
    # For narrow remainder at right/bottom, grow inward to satisfy
    # existing Hseed >=190px constraints without adding fake RAW data.
    if r-l<min_work_size:
        l=max(0,r-min_work_size)
    if b-t<min_work_size:
        t=max(0,b-min_work_size)
    if (r-l)<min_work_size or (b-t)<min_work_size:
        raise ValueError("full image too small to accommodate Hseed")
    return l,t,r,b


def json_save(path,value):
    import memory_store
    memory_store.event(path,value)







_BAND_MAP_CACHE={}
def threshold_maps(spec,l,t,r,b):
 p=spec['pixel_band_ids']
 if p not in _BAND_MAP_CACHE:_BAND_MAP_CACHE[p]=np.load(p,mmap_mode='r')
 ids=_BAND_MAP_CACHE[p][t:b,l:r]
 lo=np.full(ids.shape,float(spec['fallback'][0]),np.float64);hi=np.full(ids.shape,float(spec['fallback'][1]),np.float64)
 for z in spec['bands']:
  m=ids==int(z['band_id']);lo[m]=z['low_dn'];hi[m]=z['high_dn']
 if np.any(lo>hi):raise ValueError('TL>TH')
 return lo,hi


def run_tile(tile:dict,rawmem:np.memmap,fused:np.memmap,
             pcfg:tuple,grade:SizeGradeConfig,j1:AssociationConfig,
             j2:ContinuousConfig,halo:int,dest:Path,
             image_enabled:bool=True,frame_label:str="26_1",
             threshold_mode:str="fixed_170_230",perband_spec:dict|None=None)->dict:
    name=tile["tile_id"]
    x0,y0,x1,y1=rect=tile["core_xyxy"]
    l,t,r,b=halo_rect(rect,rawmem.shape,halo)
    local=np.asarray(rawmem[t:b,l:r],dtype=np.uint16)
    response=np.asarray(fused[t:b,l:r],dtype=np.uint16)
    require_computed_response(response,f'J4 work window {name} {(l,t,r,b)}')
    # The scheduled core+halo response is precomputed before J4. In roi-bh it
    # is sparse outside the scheduled region, but every consumed pixel must be
    # exactly equivalent to the corresponding full-frame Black-Hat response.
    refine,seed,f,g,h=pcfg
    context_cache={}
    def context_provider():
        from src.detection.j4_filter_context import filter_context
        if not context_cache:
            context_cache.update(filter_context(rawmem,(l,t,r,b),cfg.CASE03J4_FILTER_CONTEXT_PX,h))
        return context_cache
    from fast_state import STATE
    STATE.geometry(rect,(l,t,r,b))
    enabled=cfg.CASE03J4_EXTERNAL_CONTEXT_ENABLED
    if threshold_mode=="fixed_170_230":
        detection=process_one(local,response,170.,230.,refine,seed,f,g,h,
                              context_provider=context_provider if enabled else None)
        wlo=whi=None
    else:
        if perband_spec is None:raise ValueError("perband threshold mode requires spec")
        wlo,whi=threshold_maps(perband_spec,l,t,r,b)
        if wlo.shape!=response.shape:raise AssertionError("threshold map/response mismatch")
        detection=process_one(local,response,wlo,whi,refine,seed,f,g,h,
                              context_provider=context_provider if enabled else None)
    from memory_store import capture_stage
    capture_stage(dest,name,(l,t,r,b),rect,response,wlo,whi,detection)
    sy0,sy1=y0-t,y1-t
    sx0,sx1=x0-l,x1-l
    local_mask=detection["maps"]["fused_joint_display"][sy0:sy1,sx0:sx1].copy()
    from early_rules import second_gate
    local_mask=second_gate(local_mask)
    assert local_mask.shape==(y1-y0,x1-x0)
    assert local_mask.dtype==np.bool_
    core_raw=local[sy0:sy1,sx0:sx1].copy()
    regions,labels=extract_regions(local_mask,grade,name,(x0,y0,x1,y1))
    for a in regions:
        a.update(_global_x0=x0,_global_y0=y0,frame=frame_label)
    core_dog=(context_provider()["dog"][sy0:sy1,sx0:sx1].copy()
              if enabled and regions else None)
    objects_j1,edges,_,checkmap=associate_fragments(
        labels,regions,core_raw,j1,grade,dog_map=core_dog)
    objects,orig_ids,bridge_ids,display_ids,all_edges,bridge_log=(
        reconstruct_continuous_visual(labels,core_raw,regions,
                                      edges,grade,j1,j2,dog_map=core_dog))
    repair_events=[event for event in bridge_log if event.get('action')=='removed_unanchored_inferred_bridge']
    rejected_links=[edge for edge in all_edges if edge.get('reason')=='rejected_bridge_conflict_preserve_independent_sources']
    if repair_events or rejected_links:
        json_save(dest/'tile_objects'/(name+'_bridge_repair.json'),{
            'policy':'anchored_inference_reject_unsafe_links_v1',
            'tile_id':name,'source_pixels_preserved':True,
            'removed_unanchored_inference':repair_events,'rejected_links':rejected_links})
    if not np.array_equal(checkmap>0,local_mask):
        raise AssertionError("J1 ownership lost original candidate pixels")
    if not np.array_equal(orig_ids>0,local_mask):
        raise AssertionError("J2 ownership lost original candidate pixels")
    boxrows=measure_visual_bbox(display_ids,orig_ids,objects,rect)
    output=[]
    for o,box in zip(objects,boxrows):
        if o["object_id"]!=box["object_id"]:
            raise AssertionError("object output and bbox misaligned")
        output.append({**box,
                       "tile_id":name,
                       "original_region_members":o["members"],
                       "size_trigger":o["grade_trigger"],
                       "inferred_bridge_pixels":o["inferred_bridge_pixels"],
                       "source_area_px2":o["original_area_px2"],
                       "source_max_feret_px":o["original_max_feret_px"],
                       "member_count":o["member_count"],
                       "unique_global_object_id_assigned":False,
                       "cross_tile_reconciled":False,
                       "touches_full_image_border":bool(
                          box["display_bbox_x_global"]==0 or
                          box["display_bbox_y_global"]==0 or
                          box["display_bbox_xmax_inclusive"]==rawmem.shape[1]-1 or
                          box["display_bbox_ymax_inclusive"]==rawmem.shape[0]-1),
                      })
    tilefile=dest/"tile_masks"/(name+".npz")
    import memory_store
    memory_store.put_mask(name,
        source_detected_uint8=local_mask.astype(np.uint8),
        source_region_label_i32=labels,
        grouped_source_only_i32=orig_ids,
        inferred_bridge_i32=bridge_ids,
        continuous_display_i32=display_ids,
        core_xyxy=np.asarray(rect,dtype=np.int32))
    # Avoid writing thousands of empty frames. A nonempty tile always has
    # one high-resolution annotated PNG accessible for review.
    if image_enabled and len(objects):
        visible=render_grouped_box_comparison(
            core_raw,orig_ids,display_ids,bridge_ids,
            boxrows,rect,name,BoxStyle(zoom=1))
        save_png(dest/"tiles_marked"/(name+"_fourpanel.png"),visible)
    if output:
        import memory_store
        memory_store.put_rows(name,output)
    row={
        **tile,
        "work_xyxy":[l,t,r,b],
        "stage":"J4_TILE_COMPLETE",
        "boundary_contract":"fixed_decision_window_external_filters_v1" if enabled else "legacy",
        "filter_context_px":cfg.CASE03J4_FILTER_CONTEXT_PX if enabled else 0,
        "filter_read_xyxy":context_cache.get("read_xyxy"),
        "additional_filter_RAW_pixels":context_cache.get("raw_pixels",0),
        "candidate_pre_gate_H_in_work_area":detection["candidate_count"],
        "early_exit_empty_H":bool(detection.get("empty_tile_early_exit",False)),
        "dog_mode":detection.get("dog_mode","full_window"),
        "final_source_core_pixels":int(local_mask.sum()),
        "source_core_connected_regions":len(regions),
        "tile_objects":len(objects),
        "linked_objects":sum(o["member_count"]>1 for o in objects),
        "inferred_bridge_pixels":int(np.count_nonzero(bridge_ids)),
        "tile_objects_truncated_by_core":sum(b["bbox_may_be_truncated"]
                                              for b in boxrows),
        "cross_tile_merged":False,
        "precomputed_full_frame_response":True,
        "threshold_mode":threshold_mode,
        "window_low_dn_min_median_max":([float(wlo.min()),float(np.median(wlo)),float(wlo.max())]
                                        if wlo is not None else [170.,170.,170.]),
        "window_high_dn_min_median_max":([float(whi.min()),float(np.median(whi)),float(whi.max())]
                                         if whi is not None else [230.,230.,230.]),
        "mask_file":str(tilefile.relative_to(dest)),
        "measured_area_excludes_inferred_bridge":True,
    }
    return row
