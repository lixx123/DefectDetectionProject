"""Case03-E pilot: untrained local dark-anomaly boundary refinement on 10 user marks.

The only annotation parameter consumed by detection: clicked point x/y.
Manual polygons are used solely *after* predictions for diagnostic comparison.
Do not tune parameters against these same 10 targets then claim independent
accuracy. Source Case02/03B/03D images, masks and user labels remain unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from config import user_config as cfg
from src.detection.local_boundary_refinement import (
    METHODS,LEVELS,compute_local_residual,
    grow_from_clicked_center,image_crop_at_target,
)
from src.detection.thresholding import load_packed_mask

SOURCE=ROOT/"outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching"
TARGETS=SOURCE/"10_retained_manual_targets_for_boundary_refinement.csv"
MANUAL=Path(r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv")
HNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_H_TL170_TH230.npz"
OUT_ROOT=cfg.OUTPUT_ROOT/"case03e"


def fingerprint(path:Path)->dict:
    sha=hashlib.sha256()
    with path.open("rb") as f:
        while part:=f.read(1024*1024):sha.update(part)
    return {"path":str(path),"sha256":sha.hexdigest(),"bytes":path.stat().st_size}


def manual_polygon_mask(
    points:list[list[int]],origin_xy:tuple[int,int],
    size:int
)->tuple[np.ndarray,bool]:
    """Manual polygon rasterized for post-prediction comparison ONLY."""
    x0,y0=origin_xy
    local=np.asarray(points,dtype=np.int32)-np.asarray([x0,y0],dtype=np.int32)
    if len(local)<3:
        raise ValueError("manual polygon missing vertices")
    clipped=bool((local<0).any() or (local>=size).any())
    out=np.zeros((size,size),np.uint8)
    cv2.fillPoly(out,[local.reshape(-1,1,2)],1)
    return out.astype(bool),clipped


def pixel_agreement(mask:np.ndarray,manual:np.ndarray)->dict:
    if mask.shape!=manual.shape or mask.ndim!=2:
        raise ValueError("different ROI mask coordinate systems")
    hit=int(np.count_nonzero(mask&manual))
    area=int(mask.sum());gt=int(manual.sum())
    union=gt+area-hit
    return {
        "predicted_area_px":area,
        "manual_polygon_area_raster_px":gt,
        "intersection_px":hit,
        "coverage_of_manual_polygon":round(hit/gt,5) if gt else None,
        "predicted_pixels_outside_manual_polygon":area-hit,
        "fraction_predicted_inside_manual":round(hit/area,5) if area else 0.,
        "iou_against_manual_approximation":round(hit/union,5) if union else 0.
    }


def describe_mask(mask:np.ndarray)->dict:
    ys,xs=np.nonzero(mask)
    if not len(xs):
        return dict(bbox_xywh=None,area_px=0)
    return {"bbox_xywh":[int(xs.min()),int(ys.min()),
            int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)],
            "area_px":int(len(xs))}


def draw_subplot(
    base:np.ndarray,
    mask:np.ndarray|None,
    manual:np.ndarray,
    origin:tuple[int,int],
    clicked:tuple[int,int],
    label:str,
    subtitle:str,
    *,
    selected_seed:tuple[int,int]|None=None
)->np.ndarray:
    size=base.shape[0]
    color=base.copy()
    if mask is not None:
        color[mask]=(46,216,64)
    # Manual contour is evidence, not the method's prediction.
    outlines,_=cv2.findContours(
        np.uint8(manual),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(color,outlines,-1,(10,223,254),1,cv2.LINE_8)
    cx,cy=clicked[0]-origin[0],clicked[1]-origin[1]
    cv2.drawMarker(color,(cx,cy),(25,48,243),cv2.MARKER_CROSS,10,1)
    if selected_seed:
        sx,sy=selected_seed
        cv2.circle(color,(sx,sy),3,(251,173,30),1)
    # 2x magnification is for display, not measurement.
    color=cv2.resize(color,(size,size),interpolation=cv2.INTER_NEAREST)
    tile=np.full((size+59,size,3),245,np.uint8)
    tile[59:]=color
    cv2.putText(tile,label[:34],(6,16),cv2.FONT_HERSHEY_SIMPLEX,.49,
                (32,47,57),1,cv2.LINE_AA)
    cv2.putText(tile,subtitle[:41],(5,36),cv2.FONT_HERSHEY_SIMPLEX,.40,
                (43,57,66),1,cv2.LINE_AA)
    cv2.putText(tile,"yellow=manual, green=predicted",(5,52),
                cv2.FONT_HERSHEY_SIMPLEX,.36,(56,70,79),1,cv2.LINE_AA)
    return tile


def make_target_atlas(
    raw:np.ndarray,baseline_mask:np.ndarray,
    results:dict[str,object],
    manual:np.ndarray,
    clicked_global:tuple[int,int],
    origin:tuple[int,int],
    *,
    title:str
)->np.ndarray:
    size=raw.shape[0]
    vals=np.asarray(raw,dtype=np.float32)
    lo,hi=np.percentile(vals,[1,99.5]);hi=max(float(hi),float(lo)+1)
    g=np.uint8(np.rint(np.clip((vals-lo)/(hi-lo),0,1)*255))
    base=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    tiles=[
        draw_subplot(base,None,manual,origin,clicked_global,
                     "1 RAW + MANUAL","Manual polygon for evaluation"),
        draw_subplot(base,baseline_mask,manual,origin,clicked_global,
                     "2 HISTORIC H170/230",
                     "all existing H pixels in ROI")
    ]
    for method in METHODS:
        for level in LEVELS:
            key=method+"_"+level
            result=results[key]
            tiles.append(draw_subplot(base,result.mask,manual,origin,
                clicked_global,str(len(tiles)+1)+" "+key,
                "area="+str(result.area_px)+"px "+result.status,
                selected_seed=(result.seed_x,result.seed_y)))
    ncols=4;gap=10;top=58
    H=size+59
    out=np.full((top+2*(H+gap),ncols*(size+gap),3),248,np.uint8)
    cv2.putText(out,title[:95],(13,26),cv2.FONT_HERSHEY_SIMPLEX,
                .60,(35,47,62),1,cv2.LINE_AA)
    cv2.putText(out,"RED cross=clicked RAW, BLUE circle=auto seed; not measured physical size",
                (12,48),cv2.FONT_HERSHEY_SIMPLEX,.43,(50,60,77),1,cv2.LINE_AA)
    for i,tile in enumerate(tiles):
        x=(i%4)*(size+gap)
        y=top+(i//4)*(H+gap)
        out[y:y+H,x:x+size]=tile
    return out


def run(run_id:str|None=None)->dict:
    if not TARGETS.is_file() or not MANUAL.is_file():
        raise FileNotFoundError("needs previously confirmed user RAW target files")
    dest=OUT_ROOT/(run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    if dest.exists():raise FileExistsError("never overwrite previous pilot")
    dest.mkdir(parents=True)
    (dest/"figures").mkdir()
    (dest/"masks").mkdir()
    source_paths=[TARGETS,MANUAL,HNPZ]
    before=[fingerprint(p) for p in source_paths]
    data=pd.read_csv(TARGETS,low_memory=False)
    if len(data)!=10 or data["review_target_id"].duplicated().any():
        raise ValueError("expected ten retained user RAW anomaly locations")
    if data["original_ROI_parent_candidate_id"].eq("H_sample26_0452065").any():
        raise AssertionError("user excluded region must not be reintroduced")
    original=pd.read_csv(MANUAL,encoding="utf-8-sig",keep_default_na=False)
    manual_polygon_by_roi={}
    for r in original.to_dict("records"):
        if r["annotation_kind"]=="poly":
            k=r["source_parent_H_candidate_id"]
            manual_polygon_by_roi.setdefault(k,[]).append(
                json.loads(r["vertices_RAW_global_xy_JSON"])
            )
    H=load_packed_mask(HNPZ)
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    assert H.shape==raw.shape==(9200,11276)
    records=[]
    pair_count=0
    for user_target in data.to_dict("records"):
        uid=user_target["review_target_id"]
        parent=user_target["original_ROI_parent_candidate_id"]
        clicked=(int(user_target["clicked_raw_x"]),
                 int(user_target["clicked_raw_y"]))
        rawroi,origin=image_crop_at_target(
            raw,clicked,size=cfg.CASE03E_ROI_SIZE_PX
        )
        x0,y0=origin
        # USER polygon: diagnostics only, not submitted to segmentation.
        polys=manual_polygon_by_roi.get(parent,[])
        polyidx=int(user_target["manual_polygon_row_id"])
        poly_annotations=original.loc[
            (original.source_parent_H_candidate_id==parent)&
            (original.annotation_kind=="poly")
        ].copy().sort_values("target_index_in_roi",key=lambda x:x.astype(int))
        match=poly_annotations.loc[
            poly_annotations.target_index_in_roi.eq(polyidx)
        ]
        if len(match)!=1:raise AssertionError("one polygon must match exact row")
        points=json.loads(match.iloc[0]["vertices_RAW_global_xy_JSON"])
        manual,clipped=manual_polygon_mask(points,origin,cfg.CASE03E_ROI_SIZE_PX)
        baseline=H[y0:y0+cfg.CASE03E_ROI_SIZE_PX,
                   x0:x0+cfg.CASE03E_ROI_SIZE_PX].copy()
        experiments={}
        for method in cfg.CASE03E_METHODS:
            for level in cfg.CASE03E_LEVELS:
                result=grow_from_clicked_center(
                    rawroi,(clicked[0]-x0,clicked[1]-y0),
                    method=method,level=level,
                    max_area_fraction=cfg.CASE03E_MAX_AREA_FRACTION
                )
                key=method+"_"+level
                experiments[key]=result
                metrics=pixel_agreement(result.mask,manual)
                records.append({
                    "user_target_id":uid,
                    "parent_review_candidate_ID":parent,
                    "clicked_raw_x":clicked[0],"clicked_raw_y":clicked[1],
                    "crop_origin_x":x0,"crop_origin_y":y0,
                    "crop_size_px":cfg.CASE03E_ROI_SIZE_PX,
                    "manual_polygon_clipped_in_new_crop":clipped,
                    "manual_original_160px_roi_boundary_flag":bool(
                        user_target["manual_polygon_near_160px_ROI_boundary"]),
                    "method":method,"threshold_level":level,
                    "segmentation_status":result.status,
                    "method_is_local_clicked_seed_not_full_image_automatic":True,
                    "used_manual_polygon_to_fit":False,
                    "seed_shift_px":round(result.seed_shift_px,3),
                    "seed_response_dn":round(result.initial_seed_response_dn,3),
                    "threshold_dn":round(result.threshold_dn,3),
                    "background_response_median_dn":round(result.background_response_median_dn,3),
                    "background_noise_sigma_DN":round(result.background_response_mad_sigma_dn,3),
                    "bbox_global_xywh":json.dumps(
                        [result.bbox_xywh[0]+x0,result.bbox_xywh[1]+y0,
                         result.bbox_xywh[2],result.bbox_xywh[3]]
                        if result.bbox_xywh else []
                    ),
                    "equivalent_diameter_px":round(result.equivalent_diameter_px,2),
                    "max_hull_vertex_span_px":round(result.max_hull_span_px,2),
                    "touches_crop_edge":result.touches_crop_edge,
                    **metrics,
                    "original_full_H_pixels_inside_manual_polygon":
                        int(np.count_nonzero(baseline&manual)),
                    "source_manual_human_area_approx_only":True,
                    "size_grade":"NOT_DEFINED",
                    "object_plane_pixel_scale":"NOT_CALIBRATED",
                })
                # Distinct lossless masks, relative origin in filename audit.
                np.savez_compressed(dest/"masks"/f"{uid}_{key}.npz",
                    binary_mask=np.uint8(result.mask),
                    crop_origin_xy=np.asarray(origin,dtype=np.int32),
                    clicked_raw_xy=np.asarray(clicked,dtype=np.int32))
                pair_count+=1
        image=make_target_atlas(rawroi,baseline,experiments,manual,clicked,origin,
            title=f"{uid} | selected RAW center {clicked} | manual polygon reference only")
        ok,encoded=cv2.imencode(".png",image,
                                [cv2.IMWRITE_PNG_COMPRESSION,4])
        if not ok:raise IOError(uid)
        (dest/"figures"/f"{uid}_local_8panel.png").write_bytes(encoded.tobytes())
        if clipped:
            print("WARNING_MANUAL_POLYGON_CLIPPED",uid,flush=True)
        print("TARGET_DONE",uid,len(experiments),flush=True)
    frame=pd.DataFrame(records)
    if len(frame)!=60 or pair_count!=60 or len(list((dest/"masks").glob("*.npz")))!=60:
        raise AssertionError("lost target/method combination")
    frame.to_csv(dest/"all_60_pilot_experiments.csv",index=False,encoding="utf-8-sig")
    summary=frame.groupby(["method","threshold_level"],sort=False).agg(
        n=("user_target_id","nunique"),
        mean_annotation_iou=("iou_against_manual_approximation","mean"),
        median_manual_coverage=("coverage_of_manual_polygon","median"),
        median_predicted_inside_manual=("fraction_predicted_inside_manual","median"),
        median_predicted_area_px=("predicted_area_px","median"),
        empty=("segmentation_status",lambda x:int(x.eq("no_reliable_seed").sum())),
        overgrown=("segmentation_status",lambda x:int(x.eq("overgrown_needs_review").sum())),
        crop_edge=("touches_crop_edge","sum")
    ).reset_index()
    summary.to_csv(dest/"six_methods_comparison.csv",index=False,encoding="utf-8-sig")
    baseline=[]
    for u in data.to_dict("records"):
        baseline.append({
            "user_target_id":u["review_target_id"],
            "manual_polygon_area_px":u["manual_polygon_raster_area_px"],
            "H_pixel_count_inside_manual":u[
                "existing_H_segmentation_area_intersect_polygon_px"
            ],
            "historic_H_coverage_fraction":u[
                "existing_H_segmentation_polygon_coverage"
            ]
        })
    pd.DataFrame(baseline).to_csv(dest/"historic_H_baseline_10.csv",
                                  index=False,encoding="utf-8-sig")
    after=[fingerprint(p) for p in source_paths]
    if before!=after:raise AssertionError("source changed while processing")
    (dest/"source_manifest.json").write_text(json.dumps({
        "source_inputs_before":before,"source_inputs_after":after,"unchanged":True
    },ensure_ascii=False,indent=2),encoding="utf-8")
    overview={
       "stage":"Case03-E local boundary refinement, experimental only",
       "retained_manual_target_count":len(data),
       "methods":list(METHODS),"threshold_levels":list(LEVELS),
       "experiment_count":len(frame),
       "output_lossless_masks":pair_count,
       "pixel_size":cfg.CASE03E_ROI_SIZE_PX,
       "manual_polygon_never_used_as_segmenter_input":True,
       "source_case03b_H_unchanged":True,
       "case03d_auto_decisions_unchanged":True,
       "not_full_image_detection":True,
       "cannot_use_same_10_hand_polygons_as_independent_accuracy_test":True,
       "measurement_unit":"px or px^2 only",
       "user_excluded_no_anomaly":"H_sample26_0452065",
       "size_grade_threshold":"NOT_SET",
       "algorithms_may_under_or_over_segment":True
    }
    (dest/"summary.json").write_text(json.dumps(overview,ensure_ascii=False,indent=2),
                                     encoding="utf-8")
    print("CASE03E_OUTPUT",dest)
    print("CASE03E_METHOD_METRICS\n"+summary.to_string(index=False))
    print("CASE03E_RESULT",json.dumps(overview,ensure_ascii=False))
    return overview


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default=None)
    args=parser.parse_args()
    run(args.run_id)
