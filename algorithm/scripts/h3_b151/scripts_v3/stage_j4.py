"""Case03-J4: full RAW core-tile scan, local objectization and external boxes.

Case03-J5 (NOT implemented here) alone will merge across core boundaries
and assign final physical-defect IDs. This file deliberately never calls
a global union-find and never claims whole-object completeness at tile edges.

Thresholds: the only supported mode is b15_pixel, i.e. per-band H3 P95/P99.9
values frozen by prepare_raw and expanded to a per-pixel float64 surface.
There is no fixed 170/230 fallback and no scalar default: a missing or invalid
spec fails before any detection work. Pixels outside EVAL keep the 65536
disable pair so the uint16 response can never cross it.
Case03E2 anchored bounded refinements and the Case03-F/G/H gates are unchanged.

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
def save_png(path:Path,image:np.ndarray)->None:
    """Encode a display PNG on Unicode Windows paths; detection data untouched.

    Deliberately no minimum-file-size test: a legitimately small tile image is
    still valid. Integrity is proven by decoding and comparing geometry.
    """
    path.parent.mkdir(parents=True,exist_ok=True)
    ok,payload=cv2.imencode('.png',image,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise OSError('PNG encode failed: '+str(path))
    path.write_bytes(payload.tobytes())
    decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
    if decoded is None or decoded.shape[:2]!=image.shape[:2]:
        raise OSError('PNG could not be decoded with matching geometry: '+str(path))


def gray(raw:np.ndarray)->np.ndarray:
    """Stretch RAW DN to BGR for display only; input array is never modified."""
    f=raw.astype(np.float32);lo,hi=np.percentile(f,[1,99.5])
    hi=max(float(hi),float(lo)+1.)
    mono=np.uint8(np.rint(np.clip((f-lo)/(hi-lo),0,1)*255))
    return cv2.cvtColor(mono,cv2.COLOR_GRAY2BGR)


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







_DISABLE_DN=65536.
_BAND_MAP_CACHE={}


def clear_band_map_cache():
    """Run init clears the band-raster cache so a recycled path cannot reuse it."""
    _BAND_MAP_CACHE.clear()


def validate_threshold_spec(spec):
    """Reject anything that could silently turn H3 into another threshold."""
    if not isinstance(spec,dict):raise ValueError('threshold spec must be a mapping')
    for key in ('bands','fallback','pixel_band_ids'):
        if key not in spec:raise ValueError(f'threshold spec missing {key}')
    bands=spec['bands']
    if not bands:raise ValueError('threshold spec has no bands')
    seen=set()
    for b in bands:
        for key in ('band_id','low_dn','high_dn'):
            if key not in b:raise ValueError(f'band spec missing {key}')
        bid=int(b['band_id'])
        if bid<=0 or bid in seen:raise ValueError(f'invalid or duplicated band_id {bid}')
        seen.add(bid)
        lo,hi=float(b['low_dn']),float(b['high_dn'])
        if not (np.isfinite(lo) and np.isfinite(hi)):
            raise ValueError(f'non-finite threshold in band {bid}')
        if not 0.<=lo<hi<_DISABLE_DN-1:
            raise ValueError(f'band {bid} breaks 0<=low<high<65535: {lo}/{hi}')
    fb=[float(v) for v in spec['fallback']]
    if len(fb)!=2 or not all(np.isfinite(v) for v in fb):
        raise ValueError('fallback thresholds must be two finite values')
    if fb[0]!=fb[1] or fb[0]<_DISABLE_DN:
        raise ValueError('out-of-domain fallback must disable the uint16 response; a fixed threshold is not allowed')
    if not Path(str(spec['pixel_band_ids'])).is_file():
        raise ValueError(f"band id raster not found: {spec['pixel_band_ids']}")
    return seen


def threshold_maps(spec,l,t,r,b):
    """Expand the frozen per-band H3 table into per-pixel low/high surfaces.

    Returns (low, high, per-band pixel accounting) for the requested window.
    """
    validate_threshold_spec(spec)
    key=str(spec['pixel_band_ids'])
    if key not in _BAND_MAP_CACHE:_BAND_MAP_CACHE[key]=np.load(key,mmap_mode='r')
    raster=_BAND_MAP_CACHE[key]
    height,width=raster.shape
    if not (0<=l<r<=width and 0<=t<b<=height):
        raise ValueError(f'window {(l,t,r,b)} outside band raster {(height,width)}')
    ids=raster[t:b,l:r]
    lo=np.full(ids.shape,float(spec['fallback'][0]),np.float64)
    hi=np.full(ids.shape,float(spec['fallback'][1]),np.float64)
    applied=[];covered=np.zeros(ids.shape,bool)
    for z in spec['bands']:
        bid=int(z['band_id']);m=ids==bid
        lo[m]=z['low_dn'];hi[m]=z['high_dn'];covered|=m
        applied.append(dict(band_id=bid,low_dn=float(z['low_dn']),high_dn=float(z['high_dn']),
                            pixels=int(np.count_nonzero(m))))
    unknown=int(np.count_nonzero((ids!=0)&~covered))
    if unknown:
        raise ValueError(f'{unknown} window pixels name bands absent from the frozen spec')
    if np.any(lo>hi):raise AssertionError('threshold surface inverted')
    applied.append(dict(band_id=0,low_dn=float(spec['fallback'][0]),high_dn=float(spec['fallback'][1]),
                        disabled=True,pixels=int(np.count_nonzero(ids==0))))
    return lo,hi,applied


def run_tile(tile:dict,rawmem:np.memmap,fused:np.memmap,
             pcfg:tuple,grade:SizeGradeConfig,j1:AssociationConfig,
             j2:ContinuousConfig,halo:int,dest:Path,
             image_enabled:bool=True,frame_label:str="26_1",
             threshold_mode:str="b15_pixel",perband_spec:dict|None=None,
             residual_layers:tuple|None=None)->dict:
    # Contract first: refuse an unusable threshold surface before touching RAW.
    if threshold_mode!="b15_pixel":
        raise ValueError(f"threshold_mode {threshold_mode!r} is not supported; the official chain is b15_pixel")
    if perband_spec is None:
        raise ValueError('b15_pixel requires an explicit per-band H3 threshold spec')
    validate_threshold_spec(perband_spec)
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
        if not context_cache:
            if residual_layers is not None:
                # Precomputed full-frame float32 layers: crop the decision window.
                # Equivalent to filter_context's guarded-window compute because the
                # 96px prepare halo covers every large-kernel support (~66px max).
                g22,c61,dog=residual_layers
                context_cache.update(
                    residuals={'gaussian22':np.asarray(g22[t:b,l:r],dtype=np.float32).copy(),
                               'closing61':np.asarray(c61[t:b,l:r],dtype=np.float32).copy()},
                    dog=np.asarray(dog[t:b,l:r],dtype=np.float32).copy(),
                    read_xyxy=[l,t,r,b],raw_pixels=(r-l)*(b-t))
            else:
                from src.detection.j4_filter_context import filter_context
                context_cache.update(filter_context(rawmem,(l,t,r,b),cfg.CASE03J4_FILTER_CONTEXT_PX,h))
        return context_cache
    from fast_state import STATE
    STATE.geometry(rect,(l,t,r,b))
    enabled=cfg.CASE03J4_EXTERNAL_CONTEXT_ENABLED
    wlo,whi,band_usage=threshold_maps(perband_spec,l,t,r,b)
    if wlo.shape!=response.shape:raise AssertionError('threshold map/response mismatch')
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
        "threshold_strategy":"H3_P95_P99_9_PER_BAND",
        "threshold_bands_applied":json.dumps(band_usage,ensure_ascii=False),
        "window_low_dn_min_median_max":[float(wlo.min()),float(np.median(wlo)),float(wlo.max())],
        "window_high_dn_min_median_max":[float(whi.min()),float(np.median(whi)),float(whi.max())],
        "mask_file":str(tilefile.relative_to(dest)),
        "measured_area_excludes_inferred_bridge":True,
    }
    return row
