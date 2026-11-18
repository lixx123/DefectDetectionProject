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
import argparse,csv,hashlib,json,os,sys,time,traceback,zipfile,shutil
from dataclasses import asdict
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
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

CASE02=ROOT/"outputs/case02/run_20260930_153727/samples/sample_26_frame_1/responses/blackhat_fused.npz"
CACHE=ROOT/"outputs/case03j4_global_cache"
OUTROOT=ROOT / "outputs" / "b151_diagnostics" / "stage_j4"


def fused_mmap(cache:CACHE.__class__=CACHE,source:Path=CASE02)->np.memmap:
    """Stream exact uint16 NPY member from NPZ to disk: peak RAM < few MB."""
    if not source.is_file():raise FileNotFoundError(source)
    cache.mkdir(parents=True,exist_ok=True)
    dest=cache/"sample26_frame1_fused_blackhat_from_case02.npy"
    with zipfile.ZipFile(source,"r") as archive:
        names=archive.namelist()
        if names!=["fused_response_dn.npy"]:
            raise ValueError("unexpected CASE02 BlackHat NPZ members: "+str(names))
        member=archive.getinfo(names[0])
        # Allow an interrupted copy to restart safely; do not trust broken
        # partial cached files.
        if dest.exists():
            try:
                mm=np.load(dest,mmap_mode="r",allow_pickle=False)
                if (mm.shape==(cfg.RAW_HEIGHT,cfg.RAW_WIDTH)
                    and mm.dtype==np.uint16
                    and dest.stat().st_size>=cfg.RAW_WIDTH*cfg.RAW_HEIGHT*2):
                    return mm
            except Exception:
                pass
            dest.unlink()
        temporary=dest.with_suffix(".incomplete")
        if temporary.exists():temporary.unlink()
        with archive.open(names[0]) as inp,open(temporary,"xb") as out:
            shutil.copyfileobj(inp,out,1024*1024)
            out.flush();os.fsync(out.fileno())
        mm=np.load(temporary,mmap_mode="r",allow_pickle=False)
        if mm.shape!=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH) or mm.dtype!=np.uint16:
            temporary.unlink()
            raise ValueError("CASE02 blackhat response shape/dtype mismatched")
        del mm
        temporary.rename(dest)
        return np.load(dest,mmap_mode="r",allow_pickle=False)


def core_axis(length:int,step:int)->list[tuple[int,int]]:
    if length<1 or step<1:raise ValueError("invalid scan geometry")
    return [(x,min(x+step,length)) for x in range(0,length,step)]


def tiles(shape:tuple[int,int],step:int=256)->list[dict]:
    H,W=shape
    out=[]
    for iy,(y0,y1) in enumerate(core_axis(H,step)):
        for ix,(x0,x1) in enumerate(core_axis(W,step)):
            out.append({"tile_id":f"T{iy:03d}_{ix:03d}",
                        "ix":ix,"iy":iy,
                        "core_xyxy":[x0,y0,x1,y1]})
    if sum((t["core_xyxy"][2]-t["core_xyxy"][0])*
           (t["core_xyxy"][3]-t["core_xyxy"][1]) for t in out)!=H*W:
        raise AssertionError("core partition did not fully cover full frame")
    return out


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



def config_j2()->ContinuousConfig:
    return ContinuousConfig(
        context_max_gap_px=cfg.CASE03J2_CONTEXT_MAX_GAP_PX,
        main_stroke_min_length_px=cfg.CASE03J2_MAIN_STROKE_MIN_LENGTH_PX,
        main_stroke_min_aspect=cfg.CASE03J2_MAIN_STROKE_MIN_ASPECT,
        piece_min_area_px=cfg.CASE03J2_PIECE_MIN_AREA_PX,
        piece_min_length_px=cfg.CASE03J2_PIECE_MIN_LENGTH_PX,
        max_perpendicular_offset_px=cfg.CASE03J2_MAX_PERPENDICULAR_OFFSET_PX,
        context_angle_tolerance_deg=cfg.CASE03J2_CONTEXT_ANGLE_TOLERANCE_DEG,
        bridge_half_width_px=cfg.CASE03J2_BRIDGE_HALF_WIDTH_PX,
        bridge_min_dog_dn=cfg.CASE03J2_BRIDGE_MIN_DOG_DN,
        max_context_links_per_group=cfg.CASE03J2_MAX_CONTEXT_LINKS_PER_GROUP,
        ambiguous_gap_margin_px=cfg.CASE03J2_AMBIGUOUS_GAP_MARGIN_PX)


def threshold_maps(spec,l,t,r,b):
    # COMMON_ADAPTER_CHANGE: 像素级冻结EVAL域、float64，所有策略共用。域外65536禁止seed。
    from pixel_thresholds import render
    return render(spec,l,t,r,b)


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


def render_full_preview(raw:np.memmap,records:list[dict],dest:Path,
                        factor:int=8,frame_label:str="26_1")->None:
    reduced=np.asarray(raw[::factor,::factor],dtype=np.uint16)
    preview=gray(reduced)
    # Local core boxes; not the merged physical-defect contours.
    for r in records:
        if r["size_grade"]=="SMALL":continue
        x=int(r["display_bbox_x_global"]//factor)
        y=int(r["display_bbox_y_global"]//factor)
        a=int(r["display_bbox_xmax_inclusive"]//factor)
        b=int(r["display_bbox_ymax_inclusive"]//factor)
        color={"MEDIUM":(25,230,240),"LARGE":(40,45,240)}[r["size_grade"]]
        cv2.rectangle(preview,(x,y),(a,b),color,1,cv2.LINE_8)
    banner=72
    im=cv2.copyMakeBorder(preview,banner,0,0,0,cv2.BORDER_CONSTANT,
                           value=(25,25,25))
    cv2.putText(im,"CASE03-J4 | SCHEDULED CORE COVERAGE | NOT CROSS-TILE MERGED",
                (14,26),cv2.FONT_HERSHEY_SIMPLEX,.58,
                (235,235,235),1,cv2.LINE_AA)
    cv2.putText(im,
            f"J4 local objects: {len(records)}; Boxes are tile CLIPPED where marked",
            (14,53),cv2.FONT_HERSHEY_SIMPLEX,.45,
            (220,220,220),1,cv2.LINE_AA)
    save_png(dest/(f"frame{frame_label}_full_preview_unmerged.png"),im)


def finalize(dest:Path,rawmem:np.memmap,total:int,frame_label:str="26_1")->dict:
    tilefiles=sorted((dest/"tile_status").glob("*.json"))
    succeeded=[]
    for p in tilefiles:
        j=json.loads(p.read_text(encoding="utf-8"))
        if j.get("stage")=="J4_TILE_COMPLETE":
            succeeded.append(j)
    complete=len(succeeded)==total
    objectfiles=sorted((dest/"tile_objects").glob("*.csv"))
    objects=[]
    for p in objectfiles:
        data=pd.read_csv(p,encoding="utf-8-sig")
        objects.extend(data.to_dict("records"))
    pd.DataFrame(succeeded).to_csv(dest/"tile_manifest.csv",index=False,
                                    encoding="utf-8-sig")
    if objects:
        pd.DataFrame(objects).to_csv(dest/"j4_unmerged_tile_objects.csv",
                                     index=False,encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=['object_id','tile_id','local_object_index','source_area_px2',
            'source_max_feret_px','display_bbox_x_global','display_bbox_y_global',
            'display_bbox_xmax_inclusive','display_bbox_ymax_inclusive','source_bbox_x_global',
            'source_bbox_y_global','source_bbox_width_px','source_bbox_height_px',
            'inferred_bridge_pixels','member_count','original_region_members']).to_csv(
                dest/'j4_unmerged_tile_objects.csv',index=False,encoding='utf-8-sig')
    if complete:
        # Sanity-check complete core coverage without dense full-image raster.
        size=sum((r["core_xyxy"][2]-r["core_xyxy"][0])*
                 (r["core_xyxy"][3]-r["core_xyxy"][1]) for r in succeeded)
        plan_path=dest/'scheduled_tiles.json'
        plan=json.loads(plan_path.read_text(encoding='utf8')) if plan_path.exists() else tiles(rawmem.shape,cfg.CASE03J4_CORE_SIZE_PX)
        if {r['tile_id'] for r in succeeded}!={r['tile_id'] for r in plan}:
            raise AssertionError('scheduled tile identity mismatch')
        if size!=sum((r['core_xyxy'][2]-r['core_xyxy'][0])*(r['core_xyxy'][3]-r['core_xyxy'][1]) for r in plan):
            raise AssertionError("tile core coverage invalid")
        render_full_preview(rawmem,objects,dest,frame_label=frame_label)
    result={
        "stage":"J4_COMPLETE" if complete else "J4_PARTIAL",
        "source":Path(getattr(rawmem,"filename",None) or f"frame_{frame_label}").name,
        "width":rawmem.shape[1],"height":rawmem.shape[0],
        "planned_tiles":total,"completed_tiles":len(succeeded),
        "candidate_j4_local_objects":len(objects),
        "not_global_defect_count":True,
        "no_cross_tile_merge":True,
        "no_final_global_IDs":True,
        "complete_frame_preview_exists":bool(complete),
        "original_masks_preserved":True,
        "inferred_bridge_not_measured":True,
        "coverage_mode":"SCHEDULED_ROI" if total!=len(tiles(rawmem.shape,cfg.CASE03J4_CORE_SIZE_PX)) else "FULL_FRAME",
    }
    json_save(dest/"run_status.json",result)
    return result


def run(run_id:str,max_tiles:int=0,halo:int=64,
        resume:bool=False,save_images:bool=True,
        input_raw_file:Path|None=None,input_fused_npy:Path|None=None,
        frame_label:str="26_1",scheduled_tile_ids=None,response_coverage="FULL_FRAME",
        threshold_mode:str="fixed_170_230",perband_spec:dict|None=None)->Path:
    if halo<48:raise ValueError("decision window halo below legacy supported minimum 48px")
    if cfg.CASE03J4_EXTERNAL_CONTEXT_ENABLED and cfg.CASE03J4_FILTER_CONTEXT_PX<93:
        raise ValueError("external filter context below derived 93px support")
    if input_fused_npy is None and not CASE02.is_file():raise FileNotFoundError(CASE02)
    raw_path=Path(input_raw_file) if input_raw_file is not None else cfg.DATA_ROOT/"26 (1).raw"
    if input_fused_npy is not None and not Path(input_fused_npy).is_file():
        raise FileNotFoundError(input_fused_npy)
    if raw_path.stat().st_size!=cfg.RAW_HEIGHT*cfg.RAW_WIDTH*2:
        raise ValueError("RAW data shape/bytes incorrect")
    dest=OUTROOT/run_id
    if resume:
        if not dest.is_dir():raise FileNotFoundError(dest)
    else:
        if dest.exists():raise FileExistsError("refusing overwrite "+str(dest))
        for sub in ("tile_status","tile_objects","tile_masks","tiles_marked"):
            (dest/sub).mkdir(parents=True)
    rawmem=np.memmap(raw_path,dtype=">u2",mode="r",
                     shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    if threshold_mode!="fixed_170_230":
        if perband_spec is None:raise ValueError("perband threshold mode requires perband_spec")
        if [b["band_id"] for b in perband_spec["bands"]]!=[1,2,3,4]:
            raise ValueError("WS1_D1 requires exactly the four approved work bands")
    response=(np.load(Path(input_fused_npy),mmap_mode="r",allow_pickle=False)
              if input_fused_npy is not None else fused_mmap())
    if response.shape!=rawmem.shape:raise ValueError("fused/RAW mismatch")
    task=tiles(rawmem.shape,step=cfg.CASE03J4_CORE_SIZE_PX)
    if scheduled_tile_ids is not None:
        requested=set(scheduled_tile_ids)
        if not requested or not requested<={t['tile_id'] for t in task}:raise ValueError('invalid scheduled tile IDs')
        task=[t for t in task if t['tile_id'] in requested]
    planned=dest/'scheduled_tiles.json'
    if resume and planned.exists():
        if json.loads(planned.read_text(encoding='utf8'))!=task:raise ValueError('resume schedule changed')
    elif not resume:json_save(planned,task)
    pcfg=policies()
    grade=SizeGradeConfig(
        medium_area_min_px2=cfg.CASE03I_MEDIUM_AREA_MIN_PX2,
        large_area_min_px2=cfg.CASE03I_LARGE_AREA_MIN_PX2,
        medium_length_min_px=cfg.CASE03I_MEDIUM_LENGTH_MIN_PX,
        large_length_min_px=cfg.CASE03I_LARGE_LENGTH_MIN_PX)
    j1=AssociationConfig(
        max_gap_px=cfg.CASE03J_MAX_LINK_GAP_PX,
        min_core_area_px=cfg.CASE03J_MIN_CORE_AREA_PX,
        min_piece_area_px=cfg.CASE03J_MIN_PIECE_AREA_PX,
        min_secondary_length_px=cfg.CASE03J_MIN_PIECE_LENGTH_PX,
        strong_aspect_ratio=cfg.CASE03J_STRONG_ASPECT_RATIO,
        angle_tolerance_deg=cfg.CASE03J_ANGLE_TOLERANCE_DEG,
        min_bridge_dog_median_dn=cfg.CASE03J_MIN_BRIDGE_DOG_MEDIAN_DN,
        min_bridge_dog_positive_fraction=cfg.CASE03J_MIN_BRIDGE_POSITIVE_FRACTION,
        small_bridge_gap_px=cfg.CASE03J_SHORT_CONNECTOR_GAP_PX,
        min_piece_dog_median_dn=cfg.CASE03J_MIN_PIECE_DOG_MEDIAN_DN,
        min_core_length_px=cfg.CASE03J_MIN_CORE_LENGTH_PX)
    j2=config_j2()
    config={
        "input_raw":str(raw_path),
        "full_global_blackhat":str(input_fused_npy if input_fused_npy is not None else CASE02),
        "core_px":cfg.CASE03J4_CORE_SIZE_PX,
        "overlap_for_internal_context":halo,
        "external_filter_context_enabled":cfg.CASE03J4_EXTERNAL_CONTEXT_ENABLED,
        "filter_context_px":cfg.CASE03J4_FILTER_CONTEXT_PX,
        "boundary_contract":"fixed_decision_window_external_filters_v1",
        "j2_bridge_conflict_policy":"anchored_inference_reject_unsafe_links_v1",
        "hysteresis_low_high":([170,230] if threshold_mode=="fixed_170_230" else
                               {str(b["band_id"]):[round(b["low_dn"],3),round(b["high_dn"],3)]
                                for b in perband_spec["bands"]}),
        "threshold_mode":threshold_mode,
        "threshold_source":("fixed absolute DN" if threshold_mode=="fixed_170_230" else
                            "per-band constant: max(floor, median+k*MAD_sigma) from fused BH"),
        "threshold_fallback_outside_bands":([170,230] if perband_spec is None
                                            else [float(v) for v in perband_spec["fallback"]]),
        "gate_config_frozen":True,
        "H_Gaussian_Closing_bounded_seeded":True,
        "original_mask_pixels_not_deleted":True,
        "inferred_visual_bridge_separate":True,
        "cross_tile_merge_not_implemented_J5":True,
        "grade":asdict(grade),"association":asdict(j1),
        "display_bridge":asdict(j2),
    }
    if scheduled_tile_ids is not None:config['scheduled_tile_ids']=[t['tile_id'] for t in task]
    if response_coverage!='FULL_FRAME':config['input_fused_coverage']=response_coverage
    if frame_label!="26_1":config["frame_label"]=frame_label
    snapshot=dest/"config_snapshot.json"
    if resume:
        if json.loads(snapshot.read_text(encoding="utf-8"))!=config:
            raise ValueError("resume config/input changed; use new run ID")
    else:
        json_save(snapshot,config)
    done=0;tic=time.perf_counter()
    for i,tile in enumerate(task,1):
        name=tile["tile_id"]
        status=dest/"tile_status"/(name+".json")
        if status.exists():
            if json.loads(status.read_text(encoding="utf-8")).get("stage")!="J4_TILE_COMPLETE":
                raise ValueError("incomplete tile marker "+str(status))
            continue
        if max_tiles>0 and done>=max_tiles:break
        try:
            t0=time.perf_counter()
            row=run_tile(tile,rawmem,response,pcfg,grade,j1,j2,halo,dest,
                         image_enabled=save_images,frame_label=frame_label,
                         threshold_mode=threshold_mode,perband_spec=perband_spec)
            row["elapsed_seconds"]=round(time.perf_counter()-t0,3)
            row['precomputed_full_frame_response']=response_coverage=='FULL_FRAME'
            row['response_coverage']=response_coverage
            json_save(status,row)
        except BaseException as exc:
            json_save(dest/"failed_tile.json",{
                "tile":tile,"type":type(exc).__name__,
                "message":str(exc),"traceback":traceback.format_exc()})
            result=finalize(dest,rawmem,len(task),frame_label=frame_label)
            print("J4_FAILED",json.dumps(result),str(exc),flush=True)
            raise
        done+=1
        if done==1 or done%5==0:
            print("J4_PROGRESS",i,len(task),name,
                  "objects",row["tile_objects"],
                  "seconds",row["elapsed_seconds"],
                  "total_running_sec",round(time.perf_counter()-tic,1),flush=True)
        if done%25==0:
            json_save(dest/"run_status.json",{
                "stage":"J4_RUNNING","planned_tiles":len(task),
                "last_completed":name,"completed_new_this_call":done,
                "do_not_treat_as_complete":True,
            })
    result=finalize(dest,rawmem,len(task),frame_label=frame_label)
    print("J4_RUN_RESULT",json.dumps(result,ensure_ascii=False),flush=True)
    return dest


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",default="run_20261012_frame26_1_full_j4_v1")
    p.add_argument("--max-tiles",type=int,default=0,
                   help="Smoke test partial run; 0=whole image")
    p.add_argument("--halo",type=int,default=64)
    p.add_argument("--resume",action="store_true")
    p.add_argument("--no-images",action="store_true")
    a=p.parse_args()
    run(a.run_id,max_tiles=a.max_tiles,halo=a.halo,
        resume=a.resume,save_images=not a.no_images)
