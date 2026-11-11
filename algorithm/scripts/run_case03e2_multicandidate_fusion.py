"""Case03-E2: MULTI-SEED no-click local-window candidate discovery + fusion.

The user-marked ten centers are used only to select fixed-grid EVALUATION
windows and later to evaluate discovered objects. They are NEVER given to
the candidate detector as seed points; annotation polygons are never passed
to the detector or its fusion code.

This is a PILOT on selected windows, not exhaustive full RAW coverage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from src.detection.case03e2_multicandidate import (
    detect_window,FusionConfig,stats_mask
)
from src.detection.case03e2_window_stitch import (
    serialize_bbox_binary,read_bbox_binary,exact_overlap_global,
    deduplicate_cross_window
)

SOURCE=ROOT/"outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching"
INPUT=SOURCE/"10_retained_manual_targets_for_boundary_refinement.csv"
ANNOTATIONS=Path(r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv")
HNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_H_TL170_TH230.npz"
SNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_S_TL230_TH230.npz"
FUSED=ROOT/"outputs/case02/run_20260930_153727/samples/sample_26_frame_1/responses/blackhat_fused.npz"
OUT_ROOT=cfg.OUTPUT_ROOT/"case03e2"


def hashfile(p:Path)->dict:
    h=hashlib.sha256()
    with p.open("rb") as f:
        while part:=f.read(1024*1024):h.update(part)
    return {"path":str(p),"bytes":p.stat().st_size,"sha256":h.hexdigest()}


def fixed_grid_window(x:int,y:int,shape:tuple[int,int],
                      size:int=256,stride:int=128)->tuple[int,int,int,int]:
    """Deterministic RAW-aligned windows. Multiple user targets share the
    same grid window; clicks are NOT used to choose detector seeds.
    """
    H,W=shape
    if not(0<=x<W and 0<=y<H):raise ValueError("RAW point outside frame")
    if size<190 or size>min(H,W):raise ValueError("bad size")
    x0=min((int(x)//stride)*stride,W-size)
    y0=min((int(y)//stride)*stride,H-size)
    return x0,y0,x0+size,y0+size


def make_manual_reference_mask(polygon_global:list,origin:tuple[int,int],
                               shape:tuple[int,int])->np.ndarray:
    """Read-only post-detection comparison; never part of detect_window."""
    x0,y0=origin
    coords=np.asarray(polygon_global,dtype=np.int32)
    if len(coords)<3:raise ValueError("manual polygon cannot be <3 vertices")
    local=coords-np.asarray([x0,y0],dtype=np.int32)
    mask=np.zeros(shape,dtype=np.uint8)
    cv2.fillPoly(mask,[local.reshape(-1,1,2)],1)
    return mask.astype(bool)


def manual_overlap(obj:dict,polygon:np.ndarray,origin_xy:tuple[int,int]
                   )->int:
    """Exact overlap of global bbox-packed candidate pixels with polygon."""
    ox,oy=origin_xy
    x,y,w,h=(int(v) for v in obj["bbox_global_xywh"])
    if not(ox<=x and oy<=y and x+w<=ox+polygon.shape[1]
           and y+h<=oy+polygon.shape[0]):
        raise ValueError("object bbox outside chosen ROI")
    mine=read_bbox_binary(obj)
    return int(np.count_nonzero(mine & polygon[y-oy:y-oy+h,x-ox:x-ox+w]))


def _gray(raw:np.ndarray)->np.ndarray:
    f=np.asarray(raw,dtype=np.float32)
    lo,hi=np.percentile(f,[1,99.5])
    hi=max(float(hi),float(lo)+1)
    g=np.uint8(np.rint(np.clip((f-lo)/(hi-lo),0,1)*255))
    return cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)


def overlay_proposals(image:np.ndarray,objects:list,source:str,
                      *,label_max_area_px:int=3000
                      )->tuple[np.ndarray,int,int]:
    """Show ALL proposals of one source (not the selected manual component)."""
    canvas=image.copy()
    seq=[p for p in objects if p.source==source]
    count_ok=0
    for p in seq:
        if p.excluded_from_safe_fusion:
            canvas[p.mask]=(46,157,245)  # orange means unsafe
        else:
            canvas[p.mask]=(55,223,61)  # green candidate evidence
            count_ok+=1
    for i,p in enumerate(sorted(seq,key=lambda x:-x.area_px)[:12],1):
        if p.area_px<12:continue
        x,y,w,h=p.bbox
        cv2.rectangle(canvas,(x,y),(x+w-1,y+h-1),
                      (12,45,235) if p.excluded_from_safe_fusion else
                      (62,80,235),1)
        cv2.putText(canvas,str(i),(max(0,x),max(10,y-3)),
                    cv2.FONT_HERSHEY_SIMPLEX,.38,(255,255,255),1)
    return canvas,len(seq),count_ok


def draw_window_atlas(
    raw:np.ndarray,H:np.ndarray,S:np.ndarray,
    objects:list,proposals:list,
    manual_refs:list[tuple[str,np.ndarray]],
    window_id:str,origin:tuple[int,int],
    diagnostic:dict,
    *,hseeded:bool=False,
)->np.ndarray:
    size=raw.shape[0]
    base=_gray(raw)
    frame0=base.copy()
    # Human annotations appear only after detector results are computed,
    # and only in this diagnostic RAW panel.
    for j,(ident,m) in enumerate(manual_refs,1):
        contours,_=cv2.findContours(np.uint8(m),cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(frame0,contours,-1,(0,226,249),1)
        yy,xx=np.nonzero(m)
        if len(xx):
            cv2.putText(frame0,str(j),(int(np.mean(xx)),int(np.mean(yy))),
                 cv2.FONT_HERSHEY_SIMPLEX,.45,(0,21,245),1)
    frame1=base.copy()
    frame1[S]=(22,230,255)
    frame1[H&~S]=(244,211,20)
    ga,ng,gg=overlay_proposals(base,proposals,"gaussian22")
    mo,nm,mg=overlay_proposals(base,proposals,"closing61")
    fused=base.copy()
    # Stable categories have priority; unsafe overlays remain amber.
    chosen=sorted(objects,key=lambda o:(o.status.startswith("needs_review"),
                                         -o.area_px))
    for obj in reversed(chosen):
        if obj.area_px==0:continue
        # 1-2px weak H responses are retained in the lossless H catalog,
        # but excluded from this optional priority visualization to prevent
        # thousands of noise dots disguising the meaningful contours.
        if hseeded and obj.status=="audit_only_H_micro":continue
        if obj.status=="needs_review_bounded_extension":
            fused[obj.mask]=(188,73,187)  # magenta: bounded rescue, NOT certified
        elif obj.status.startswith("needs_review"):
            fused[obj.mask]=(29,165,255)  # amber QA/review
        elif obj.H_only:
            fused[obj.mask]=(245,224,41)  # H-only cyan
        else:
            fused[obj.mask]=(50,215,64)  # multi-source green
    count=0
    for obj in chosen:
        if obj.area_px<12 or count>=16:continue
        if obj.status.startswith("needs_review") and obj.area_px<20:continue
        x,y,w,h=obj.bbox
        cv2.rectangle(fused,(x,y),(x+w-1,y+h-1),(22,46,235),1)
        cv2.putText(fused,obj.object_id.rsplit("_",1)[-1].lstrip("0") or "0",
                    (max(0,x),max(10,y-3)),cv2.FONT_HERSHEY_SIMPLEX,
                    .40,(255,255,255),1)
        count+=1
    if hseeded:
        displayed=sum(o.status!="audit_only_H_micro" and o.area_px>0
                      for o in objects)
        panels=[
          (frame0,"1 RAW + manual eval ONLY","yellow=hand reference"),
          (frame1,"2 ALL ORIGINAL H170/230","Original weak H pixels retained"),
          (ga,f"3 GAUSS H-REFINED {ng}","H-seeded extensions ONLY"),
          (mo,f"4 MORPH H-REFINED {nm}","H-seeded extensions ONLY"),
          (fused,f"5 H-SEED FUSED {displayed}/{len(objects)}",
           "magenta=bounded REVIEW; micro H saved"),
        ]
    else:
        panels=[
          (frame0,"1 RAW + manual eval ONLY","yellow=hand reference"),
          (frame1,"2 H170/230 all pixels","S230=yellow, Hextra=cyan"),
          (ga,f"3 GAUSS ALL {ng}","green=usable / orange=risky"),
          (mo,f"4 MORPH ALL {nm}","green=usable / orange=risky"),
          (fused,f"5 FUSED objects {len(objects)}","green=fused cyan=H-only amber=review"),
        ]
    header=88;panelh=size+58;gap=7
    out=np.full((header+panelh,5*(size+gap),3),247,np.uint8)
    cv2.putText(out,
        f"Case03-E2: {window_id} | RAW grid origin ({origin[0]}, {origin[1]}) | AUTOMATED MULTI-SEED",
        (12,25),cv2.FONT_HERSHEY_SIMPLEX,.60,(30,46,64),1,cv2.LINE_AA)
    cv2.putText(out,
        ("H170/230 EXCLUSIVE seeds; Gaussian/Closing refine ONLY H. Non-H background cannot create new candidates."
         if hseeded else "CANDIDATE PROPOSALS, NOT VERIFIED FILTER DEFECTS. Same ROI contains ALL independent candidate components."),
        (11,50),cv2.FONT_HERSHEY_SIMPLEX,.46,(42,60,80),1,cv2.LINE_AA)
    cv2.putText(out,
        "Manual yellow appears ONLY in RAW for reference; no click or polygon was passed to detection.",
        (11,72),cv2.FONT_HERSHEY_SIMPLEX,.44,(51,71,88),1,cv2.LINE_AA)
    for j,(im,title,note) in enumerate(panels):
        x=j*(size+gap)
        y=header
        cv2.putText(out,title[:37],(x+3,y+18),
                    cv2.FONT_HERSHEY_SIMPLEX,.45,(30,48,65),1)
        cv2.putText(out,note[:41],(x+2,y+38),
                    cv2.FONT_HERSHEY_SIMPLEX,.32,(65,75,87),1)
        out[y+58:y+58+size,x:x+size]=im
    return out


def run(run_id:str|None=None,*,hseeded:bool=False)->dict:
    if not (INPUT.is_file() and ANNOTATIONS.is_file()):
        raise FileNotFoundError("needs retained target list and original polygons")
    # All algorithm thresholds come from user_config, recorded per-run.
    # The acceptance fixture currently requires the frozen 256/128 grid.
    if (cfg.CASE03E2_WINDOW_SIZE_PX,cfg.CASE03E2_GRID_STRIDE_PX)!=(256,128):
        raise ValueError("Current E2 test fixture requires frozen 256px / 128px grid")
    cfgE=FusionConfig(
        source_min_region_area_px=cfg.CASE03E2_MIN_LOCAL_COMPONENT_AREA_PX,
        background_high_floor_dn=cfg.CASE03E2_GAUSSIAN_MORPH_HIGH_FLOOR_DN,
        background_low_floor_dn=cfg.CASE03E2_GAUSSIAN_MORPH_LOW_FLOOR_DN,
        high_noise_k=cfg.CASE03E2_GAUSSIAN_MORPH_HIGH_K_MAD,
        low_noise_k=cfg.CASE03E2_GAUSSIAN_MORPH_LOW_K_MAD,
        max_mask_area_fraction=cfg.CASE03E2_MAX_LOCAL_REGION_AREA_FRACTION,
        keep_H_if_area_at_least_px=cfg.CASE03E2_KEEP_H_REGION_MIN_AREA_PX,
        keep_H_if_peak_at_least_dn=cfg.CASE03E2_KEEP_H_REGION_STRONG_PEAK_DN,
        H_only_provisional_min_area_px=cfg.CASE03E2_H_ONLY_PROVISIONAL_AREA_MIN_PX,
        H_only_provisional_peak_DN=cfg.CASE03E2_H_ONLY_PROVISIONAL_PEAK_DN,
    )
    dest=OUT_ROOT/(run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    if dest.exists():raise FileExistsError("do not replace previous run")
    dest.mkdir(parents=True)
    (dest/"figures").mkdir()
    (dest/"masks").mkdir()
    from dataclasses import asdict
    (dest/"config_snapshot.json").write_text(
        json.dumps({"fusion":asdict(cfgE),
                    "source_window_size_px":256,
                    "grid_stride_px":128,
                    "physical_grade_thresholds":None,
                    "object_plane_um_per_pixel":None,
                    "thresholds_are_engineering_pilot_not_calibrated":True,
                    "candidate_discovery_mode":"H170230_only" if hseeded else "independent_all_sources"},
                    ensure_ascii=False,indent=2),encoding="utf-8"
    )
    important=[INPUT,ANNOTATIONS,HNPZ,SNPZ,FUSED]
    before=[hashfile(p) for p in important]
    user=pd.read_csv(INPUT)
    if len(user)!=10 or user.review_target_id.duplicated().any():
        raise ValueError("ten user-retained targets required")
    if user.original_ROI_parent_candidate_id.eq("H_sample26_0452065").any():
        raise ValueError("confirmed no-anomaly region must remain excluded")
    points=pd.read_csv(ANNOTATIONS,encoding="utf-8-sig",keep_default_na=False)
    polygons=points[points.annotation_kind=="poly"].copy()
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    H=load_packed_mask(HNPZ)
    S=load_packed_mask(SNPZ)
    with np.load(FUSED,allow_pickle=False) as z:
        R=z["fused_response_dn"]
    if not(R.shape==H.shape==S.shape==raw.shape==(9200,11276)):
        raise AssertionError("source shape mismatch")
    if np.any(S&~H):raise AssertionError("historic H does not contain S")
    annotations={}
    by_window=defaultdict(list)
    for row in user.to_dict("records"):
        uid=row["review_target_id"]
        x,y=int(row["clicked_raw_x"]),int(row["clicked_raw_y"])
        roi=fixed_grid_window(x,y,raw.shape,size=256,stride=128)
        by_window[roi].append(uid)
        polygon=polygons.loc[
            (polygons.source_parent_H_candidate_id==row["original_ROI_parent_candidate_id"])&
            (polygons.target_index_in_roi.astype(int)==int(row["manual_polygon_row_id"]))
        ]
        if len(polygon)!=1:raise AssertionError("manual polygon index mismatch")
        annotations[uid]={
            "clicked_raw_xy":[x,y],"roi":roi,
            "original_parent":row["original_ROI_parent_candidate_id"],
            "polygon_vertices_RAW":json.loads(
                polygon.iloc[0]["vertices_RAW_global_xy_JSON"]
            )
        }
    if len(by_window)>=len(user) or not any(len(v)>=2 for v in by_window.values()):
        raise AssertionError("MANUAL007/008 must share one independent window")
    windows=[]
    object_records=[]
    proposal_catalog=[]
    H_catalog=[]
    audit_links=[]
    results={}
    for window_idx,(roi,identifiers) in enumerate(sorted(by_window.items(),
            key=lambda item:(item[0][1],item[0][0])),1):
        x0,y0,x1,y1=roi
        winid=f"E2_W{window_idx:03d}"
        r=np.ascontiguousarray(raw[y0:y1,x0:x1],dtype=np.uint16)
        h=H[y0:y1,x0:x1].copy()
        s=S[y0:y1,x0:x1].copy()
        f=R[y0:y1,x0:x1].copy()
        # IMPORTANT: no manual centroid or polygon argument here.
        if hseeded:
            from src.detection.case03e2_hseeded import detect_window_H_seeded,HSeedConfig
            policy=HSeedConfig(
                max_extension_radius_px=cfg.CASE03E2_HSEED_MAX_EXTENSION_RADIUS_PX,
                min_h_pixels_for_refinement=cfg.CASE03E2_HSEED_MIN_H_PIXELS_FOR_REFINEMENT,
                max_extended_to_H_area_ratio=cfg.CASE03E2_HSEED_MAX_AREA_RATIO,
                max_source_component_window_fraction=cfg.CASE03E2_HSEED_MAX_RAW_COMPONENT_FRACTION,
                enable_bounded_extension_fallback=cfg.CASE03E2_HSEED_BOUNDED_FALLBACK_ENABLED,
                bounded_fallback_radius_px=cfg.CASE03E2_HSEED_BOUNDED_RADIUS_PX,
                bounded_fallback_max_area_ratio=cfg.CASE03E2_HSEED_BOUNDED_MAX_AREA_RATIO,
            )
            if window_idx==1:
                snap_path=dest/"config_snapshot.json"
                snap=json.loads(snap_path.read_text(encoding="utf-8"))
                from dataclasses import asdict
                snap["H_seeded_refinement_policy"]=asdict(policy)
                snap["H_seeded_bounded_fallback_is_heuristic_not_validated"]=bool(
                    policy.enable_bounded_extension_fallback)
                snap_path.write_text(
                    json.dumps(snap,ensure_ascii=False,indent=2),
                    encoding="utf-8"
                )
            detected=detect_window_H_seeded(r,h,s,f,cfg=cfgE,policy=policy)
        else:
            detected=detect_window(r,h,s,f,cfg=cfgE)
        props=detected["all_proposal_masks"]
        objs=detected["objects"]
        regions=np.zeros(r.shape,dtype=np.uint16)
        for j,obj in enumerate(objs,1):
            if j>=65535:raise AssertionError("too many ROI objects for uint16")
            if np.any((regions>0)&obj.mask):
                raise AssertionError("fusion masks must not double count pixels")
            regions[obj.mask]=j
            obj.object_id=f"{winid}_O{j:04d}"
            source_info=serialize_bbox_binary(obj.mask,(x0,y0)) if obj.area_px else None
            record={
                "local_object_id":obj.object_id,
                "window_id":winid,
                "roi_origin_raw_xy":[x0,y0],
                "center_raw_x":round(float(x0+obj.center_x),4),
                "center_raw_y":round(float(y0+obj.center_y),4),
                "sources":obj.sources,
                "H_only":obj.H_only,
                "source_proposals":obj.source_proposal_ids,
                "fusion_status":obj.status,
                "qa_flags":obj.flags,
                "area_px":obj.area_px,
                "max_span_px":round(obj.max_span_px,2),
                "equiv_diameter_px":round(obj.eq_diameter_px,2),
                "physical_defect_truth":False,
                "object_plane_um_per_px":None,
                "size_grade":"PENDING_USER_THRESHOLDS",
                **(source_info or {"bbox_global_xywh":[x0,y0,0,0],
                                   "exact_area_px":0,"encoding":"EMPTY",
                                   "binary_bbox_mask_base64":""})
            }
            object_records.append(record)
        np.savez_compressed(dest/"masks"/f"{winid}_labels.npz",
                            all_object_labels=regions,
                            roi_origin_raw_xy=np.array((x0,y0),dtype=np.int32),
                            H170_230=np.uint8(h),
                            S230=np.uint8(s))
        for x in detected["H_audit"]:
            H_catalog.append({"window_id":winid,
                    "roi_origin_x":x0,"roi_origin_y":y0,**x})
        for x in detected["local_proposal_audit"]:
            proposal_catalog.append({"window_id":winid,**x})
        audit_links.extend([{"window_id":winid,**link}
                            for link in detected["association_audit"]])
        # Manual polygons are introduced AFTER all detections and fusion.
        reference_masks=[]
        for uid in identifiers:
            ref=make_manual_reference_mask(
                annotations[uid]["polygon_vertices_RAW"],(x0,y0),r.shape)
            reference_masks.append((uid,ref))
        overview=draw_window_atlas(
            r,h,s,objs,props,reference_masks,winid,(x0,y0),
            detected["local_source_diagnostics"],hseeded=hseeded
        )
        ok,enc=cv2.imencode(".png",overview,[cv2.IMWRITE_PNG_COMPRESSION,3])
        if not ok:raise IOError(winid)
        (dest/"figures"/f"{winid}_5panel_ALL_AUTO.png").write_bytes(enc.tobytes())
        entry={
            "window_id":winid,"roi_xyxy":[x0,y0,x1,y1],
            "manual_reference_target_ids":identifiers,
            "manual_input_used_to_seed_detector":False,
            "manual_input_used_to_select_evaluation_window":True,
            "H_source_connected_components":len(detected["H_audit"]),
            "H_in_fusion_pool":detected["H_source_proposal_count"],
            "H_low_area_audit_only":detected["H_low_area_audit_only_count"],
            "H_source_pixel_count":detected["H_full_window_pixels"],
            "sources":detected["local_source_diagnostics"],
            "raw_source_proposals":detected["num_source_proposals"],
            "candidate_discovery_mode":detected.get("candidate_discovery_mode","independent_all_sources"),
            "independent_Gaussian_or_Morph_candidates":detected.get("independent_gaussian_morph_candidates",-1),
            "fusion_objects":len(objs),
            "provisional_fused_objects":sum(o.status=="provisional_fused" for o in objs),
            "H_only_objects":sum(o.status=="provisional_H_only" for o in objs),
            "unsafe_and_review_objects":sum(o.status.startswith("needs_review") for o in objs),
            "H_micro_audit_only_objects":sum(o.status=="audit_only_H_micro" for o in objs),
            "discovery_overflow":detected["window_incomplete_due_to_overflow"],
            "reversible_all_source_H_candidates":True
        }
        windows.append(entry)
        results[winid]={
            "objects":objs,"roi":roi,"identifiers":identifiers
        }
        print("WINDOW_DONE",winid,identifiers,len(objs),len(props),flush=True)

    with (dest/"all_window_objects_exact.jsonl").open("w",encoding="utf-8") as f:
        for item in object_records:
            if item["exact_area_px"]==0:
                # Retain the audit in status logs but zero-area must not
                # enter the physical region measurement/union.
                continue
            f.write(json.dumps(item,ensure_ascii=False)+"\n")
    np.savez_compressed(dest/"window_index.npz",
                       origins=np.array([r["roi_xyxy"][:2] for r in windows],
                                        dtype=np.int32))
    pd.DataFrame(H_catalog).to_csv(dest/"all_original_H_components_in_windows.csv",
                                  index=False,encoding="utf-8-sig")
    pd.DataFrame(proposal_catalog).to_csv(dest/"local_source_candidates_audit.csv",
                                          index=False,encoding="utf-8-sig")
    pd.DataFrame(audit_links).to_csv(dest/"association_audit.csv",
                                    index=False,encoding="utf-8-sig")
    valid_objects=[o for o in object_records if o["exact_area_px"]>0]
    stitched,duplicate_edges=deduplicate_cross_window(valid_objects)
    with (dest/"global_fused_objects_exact.jsonl").open("w",encoding="utf-8") as f:
        for obj in stitched:f.write(json.dumps(obj,ensure_ascii=False)+"\n")
    pd.DataFrame([{
        "global_object_id":o["global_object_id"],
        "bbox_global_xywh":json.dumps(o["bbox_global_xywh"]),
        "area_px":o["exact_area_px"],
        "sources":"+".join(o["sources"]),
        "status":o["fusion_status"],
        "contributing_window_objects":";".join(o["member_window_object_ids"]),
        "validation":"provisional_not_physical_truth"
    } for o in stitched]).to_csv(dest/"global_objects_geometry.csv",index=False,
                                  encoding="utf-8-sig")
    pd.DataFrame(duplicate_edges,columns=[
        "left_object","right_object","shared_exact_pixels",
        "smaller_mask_coverage","action"
    ]).to_csv(dest/"cross_window_dedup_audit.csv",
             index=False,encoding="utf-8-sig")
    eval_rows=[]
    for uid,reference in annotations.items():
        roi=reference["roi"]
        x0,y0,x1,y1=roi
        winid=next(k for k,v in results.items() if v["roi"]==roi)
        mask=make_manual_reference_mask(
            reference["polygon_vertices_RAW"],(x0,y0),(256,256))
        baseline=H[y0:y1,x0:x1]
        options=results[winid]["objects"]
        rankings=[]
        for obj in options:
            if not obj.mask.any():continue
            hit=int((obj.mask&mask).sum())
            if hit:
                rankings.append((hit,obj))
        rankings.sort(key=lambda p:(-p[0],p[1].object_id))
        top=rankings[0][1] if rankings else None
        # All-proposal union can look artificially complete by absorbing
        # enormous unsafe bridge regions. Always present a SEPARATE
        # provisional-safe union; never equate ALL union with validated
        # segmentation quality.
        safe=[o for o in options
              if o.status in ("provisional_fused","provisional_H_only")]
        risky=[o for o in options if o.status.startswith("needs_review")]
        safe_union=np.zeros_like(mask,dtype=bool)
        review_union=np.zeros_like(mask,dtype=bool)
        for o in safe:safe_union|=o.mask
        for o in risky:review_union|=o.mask
        safe_hit=int(np.count_nonzero(safe_union&mask))
        risky_hit=int(np.count_nonzero(review_union&mask))
        x,y=reference["clicked_raw_xy"]
        clicked_local=(x-x0,y-y0)
        local_hit=[obj for obj in options
                   if obj.mask[clicked_local[1],clicked_local[0]]]
        eval_rows.append({
            "manual_target_id":uid,"window_id":winid,
            "clicked_RAW_x":x,"clicked_RAW_y":y,
            "manual_polygon_px":int(mask.sum()),
            "historical_H_overlap_px":int((baseline&mask).sum()),
            "historical_H_coverage":round(float((baseline&mask).sum()/mask.sum()),4),
            "number_of_fused_objects_intersecting_manual_polygon":len(rankings),
            "top_fused_object_id":top.object_id if top else "",
            "top_fused_object_sources":"+".join(top.sources) if top else "",
            "top_fused_object_status":top.status if top else "NO_CANDIDATE",
            "top_fused_mask_coverage":round(rankings[0][0]/int(mask.sum()),4) if top else 0.,
            "fused_union_overlap_manual_px":int(np.count_nonzero(
                mask&np.logical_or.reduce([obj.mask for obj in options])
            )) if options else 0,
            "fused_union_coverage":round(
                int(np.count_nonzero(mask&np.logical_or.reduce([obj.mask for obj in options])))
                 /int(mask.sum()),4) if options else 0,
            "provisional_safe_union_overlap_manual_px":safe_hit,
            "provisional_safe_union_coverage":round(safe_hit/int(mask.sum()),4),
            "risky_review_union_overlap_manual_px":risky_hit,
            "risky_review_union_coverage":round(risky_hit/int(mask.sum()),4),
            "safe_only_coverage_gain_vs_H":round(
                safe_hit/int(mask.sum())-float((baseline&mask).sum()/mask.sum()),4),
            "coverage_is_not_physical_accuracy":True,
            "clicked_pixel_any_auto_fusion":bool(local_hit),
            "clicked_pixel_matched_object_ids":";".join(
                obj.object_id for obj in local_hit),
            "multiple_user_targets_in_same_window":len(results[winid]["identifiers"])>1,
            "manual_polygon_used_to_choose_any_candidate":False,
            "manual_click_used_as_any_detector_seed":False,
            "not_independent_accuracy_test":True
        })
    evalu=pd.DataFrame(eval_rows)
    evalu.to_csv(dest/"ten_manual_targets_posthoc_evaluation.csv",index=False,
                 encoding="utf-8-sig")
    pd.DataFrame([{
        **{k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v)
           for k,v in rec.items() if k!="sources"},
        "sources_diagnostic_json":json.dumps(rec["sources"],ensure_ascii=False)
    } for rec in windows]).to_csv(dest/"window_summary.csv",index=False,
                                 encoding="utf-8-sig")
    (dest/"window_summary.json").write_text(
        json.dumps(windows,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    after=[hashfile(p) for p in important]
    if before!=after:raise AssertionError("historic source modified")
    (dest/"source_manifest.json").write_text(
        json.dumps({"inputs_before":before,"inputs_after":after,
                    "all_sources_unchanged":True},ensure_ascii=False,indent=2),
        encoding="utf-8"
    )
    two=evalu[evalu.manual_target_id.isin(["RAW26_MANUAL_007","RAW26_MANUAL_008"])]
    two_ids=two.top_fused_object_id.tolist()
    criterion_007008=(
        len(two)==2 and two.window_id.nunique()==1
        and all(two_ids) and two_ids[0]!=two_ids[1]
    )
    manual004=evalu[evalu.manual_target_id=="RAW26_MANUAL_004"].iloc[0]
    unsafe_manuals=evalu[evalu.manual_target_id.isin(
        ["RAW26_MANUAL_003","RAW26_MANUAL_010"]
    )]
    summary={
        "stage":"Case03-E2 / H170230 as exclusive discovery seed" if hseeded else "Case03-E2 / auto discovery multiseed in user-selected fixed grid windows",
        "candidate_discovery_mode":"H170230_only" if hseeded else "independent_all_sources",
        "source_ROI_count":len(windows),
        "human_reference_targets":len(user),
        "unique_windows_including_shared_007_008":len(windows),
        "independent_user_seed_given_to_detector":False,
        "manual_polygons_used_by_detector_or_fusion":False,
        "H_source_candidates_all_preserved_in_audit":len(H_catalog),
        "H_source_low_area_candidates_not_in_primary_fusion":sum(
            not a["promoted_to_fusion_pool"] for a in H_catalog),
        "per_window_all_source_proposals":len(proposal_catalog)+
            sum(x["H_in_fusion_pool"] for x in windows),
        "unique_source_window_objects":len(valid_objects),
        "deduped_global_objects":len(stitched),
        "number_cross_window_dedup_edges":len(duplicate_edges),
        "region_007_008_detects_two_independent_targets":bool(criterion_007008),
        "region_007_008_global_roi":two.window_id.iloc[0] if len(two) else "",
        "manual004_H_coverage":float(manual004.historical_H_coverage),
        "manual004_fused_union_coverage":float(manual004.fused_union_coverage),
        "manual004_all_proposals_coverage_improved":bool(
            manual004.fused_union_coverage>manual004.historical_H_coverage
        ),
        "manual004_provisional_safe_coverage_improved":bool(
            manual004.provisional_safe_union_coverage>manual004.historical_H_coverage
        ),
        "warning_union_including_unsafe_is_not_validated":True,
        "unresolved_003_010":unsafe_manuals[[
            "manual_target_id","top_fused_object_status",
            "fused_union_coverage"]].to_dict("records"),
        "full_raw_exhaustive_detector_implemented":False,
        "actual_filter_defects_confirmed_by_algorithm":False,
        "micro_H_visualization_hidden_only":bool(hseeded),
        "all_H_micro_regions_still_preserved_in_lossless_outputs":True,
        "user_defined_size_grade_thresholds":None,
        "object_plane_magnification_or_um_per_pixel":None,
        "measured_contours_independent_truth_verified":False,
        "pilot_source_data_unchanged":True,
        "pilot_status":"COMPLETE_WITH_UNRESOLVED_RISK_CASES"
    }
    (dest/"summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    print("CASE03E2_OUTPUT",dest)
    print("CASE03E2_SUMMARY",json.dumps(summary,ensure_ascii=False))
    print("CASE03E2_EVAL\n"+evalu[[
        "manual_target_id","window_id","historical_H_coverage",
        "top_fused_object_id","top_fused_object_status",
        "top_fused_mask_coverage","fused_union_coverage",
        "number_of_fused_objects_intersecting_manual_polygon"
    ]].to_string(index=False))
    # Always execute acceptance at the end of a newly generated run.
    # Failed scientific gates do NOT delete its diagnostic outputs or
    # misrepresent physical defect measurement as accepted.
    if hseeded:
        from scripts.accept_case03e2_hseeded import check_H_seeded as check
    else:
        from scripts.accept_case03e2_multicandidate import check
    acceptance=check(dest)
    summary["engineering_acceptance"]=acceptance["status"]
    summary["acceptance_summary_counts"]=acceptance["counts"]
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id")
    args=parser.parse_args()
    run(args.run_id)
