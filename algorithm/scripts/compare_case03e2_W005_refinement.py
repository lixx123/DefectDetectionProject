"""Prepare W005 focused before-after atlas and exact pixel-geometric diagnostics.

Metrics against the user's approximate hand polygon are only diagnostic.
No manual polygon is passed into the segmentation logic; it is introduced
after the three completed runs for visual and statistical comparison.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
import pandas as pd

from config import user_config as cfg
from src.detection.case03e2_window_stitch import read_bbox_binary
from scripts.run_case03e2_multicandidate_fusion import (
    ANNOTATIONS,make_manual_reference_mask
)

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/case03e2"
OLD_INDEPENDENT=BASE/"run_20261010_multiseed_fusion_v5"
OLD_H=BASE/"run_20261010_H_only_seeded_refinement_v2"
NEW=BASE/"run_20261010_H_seeded_bounded_consensus_v5"
ORIGIN=(2944,1024)
WID="E2_W005"
H_ID="E2_W005_O0050"
MANUAL_PARENT="H_sample26_0409762"
MANUAL_POLY_ID=2


def read_whole_mask(path:Path,object_id:str)->np.ndarray:
    records=[json.loads(s) for s in
        (path/"all_window_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()
        if s.strip()]
    obj=next(x for x in records if x["local_object_id"]==object_id)
    x,y,w,h=obj["bbox_global_xywh"]
    ox,oy=ORIGIN
    if not(ox<=x and oy<=y and x+w<=ox+256 and y+h<=oy+256):
        raise AssertionError("ROI coordinate mismatch")
    whole=np.zeros((256,256),bool)
    whole[y-oy:y-oy+h,x-ox:x-ox+w]=read_bbox_binary(obj)
    assert int(whole.sum())==obj["exact_area_px"]
    return whole


def score(mask:np.ndarray,manual:np.ndarray)->dict:
    area=int(mask.sum())
    hit=int(np.count_nonzero(mask&manual))
    target=int(manual.sum())
    return {
        "candidate_area_px2":area,
        "manual_polygon_approximate_px2":target,
        "manual_intersection_px2":hit,
        "manual_coverage_fraction":round(hit/max(target,1),4),
        "predicted_mask_fraction_within_manual":round(hit/max(area,1),4),
        "iou_vs_manual_reference_only":round(hit/max(area+target-hit,1),4),
        "candidate_mask_pixels_outside_manual_approximation":area-hit,
    }


def to_RGB(raw:np.ndarray)->np.ndarray:
    p1,p2=np.percentile(raw,[1,99.5])
    raw=np.clip((raw.astype(np.float32)-p1)/max(p2-p1,1),0,1)
    return cv2.cvtColor(np.uint8(np.round(raw*255)),cv2.COLOR_GRAY2BGR)


def plot_panel(base:np.ndarray,manual:np.ndarray,mode:str,
               mask:np.ndarray|None,base_H:np.ndarray
              )->np.ndarray:
    pic=base.copy()
    if mode=="manual":
        outlines,_=cv2.findContours(np.uint8(manual),
            cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(pic,outlines,-1,(0,238,255),1)
    elif mode=="new":
        pic[base_H]=(242,224,37)  # original H is cyan-blue
        pic[(mask & ~base_H)]=(186,70,186) # added support purple
        outlines,_=cv2.findContours(np.uint8(manual),
            cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(pic,outlines,-1,(0,238,255),1)
    elif mask is not None:
        pic[mask]=(50,207,60)
        outlines,_=cv2.findContours(np.uint8(manual),
            cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(pic,outlines,-1,(0,238,255),1)
    return pic


def run():
    user=pd.read_csv(ANNOTATIONS,encoding="utf-8-sig",keep_default_na=False)
    row=user[(user.source_parent_H_candidate_id==MANUAL_PARENT)&
        (user.target_index_in_roi.astype(int)==MANUAL_POLY_ID)&
        (user.annotation_kind=="poly")]
    if len(row)!=1:raise AssertionError("single manual reference expected")
    polygon=json.loads(row.iloc[0]["vertices_RAW_global_xy_JSON"])
    manual=make_manual_reference_mask(polygon,ORIGIN,(256,256))
    source=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
        shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    raw=np.asarray(source[1024:1280,2944:3200],dtype=np.uint16)
    old_H=read_whole_mask(OLD_H,H_ID)
    new_H=read_whole_mask(NEW,H_ID)
    old_independent=read_whole_mask(OLD_INDEPENDENT,"E2_W005_O0001")
    if not np.all(new_H[old_H]):
        raise AssertionError("bounded candidate must retain all historical H core")
    results=[
       ("Original H170/230 only",old_H,"historical H seed"),
       ("Old independent local-source candidate",old_independent,
        "unsafe background touching ROI border"),
       ("H-only restrictive refinement v2",old_H,
        "old version: refinement entirely rejected"),
       ("NEW bounded local consensus v5",new_H,
        "7px H-near Gaussian and Closing consensus")
    ]
    result=[{"method":label,**score(mask,manual)} for label,mask,_ in results]
    df=pd.DataFrame(result)
    if not(
        result[0]["manual_coverage_fraction"]<.70 and
        result[3]["manual_coverage_fraction"]>.98 and
        result[3]["candidate_area_px2"]<2*result[0]["candidate_area_px2"]
    ):
        raise AssertionError("W005 must show bounded contour gain without 2x area inflation")
    base=to_RGB(raw)
    rows=[
      ("1 RAW reference", "yellow=user approximate polygon",
       plot_panel(base,manual,"manual",None,old_H)),
    ]
    for j,(title,mask,note) in enumerate(results[1:],2):
        mode="new" if j==4 else "other"
        rows.append((f"{j} {title}",note,
                    plot_panel(base,manual,mode,mask,old_H)))
    cols=4;pix=256;pad=8;header=108
    out=np.full((header+pix+50,cols*(pix+pad),3),245,np.uint8)
    cv2.putText(out,"W005 / horizontal scratched stripe: Original vs H-only vs bounded consensus",
                (12,23),cv2.FONT_HERSHEY_SIMPLEX,.61,(28,48,62),1,cv2.LINE_AA)
    cv2.putText(out,
       "Manual polygon only for diagnostic comparison. Purple=H-seeded added contour, BLUE=original H. No standalone Gaussian/Morph targets.",
       (12,48),cv2.FONT_HERSHEY_SIMPLEX,.38,(47,68,80),1,cv2.LINE_AA)
    cv2.putText(out,
       f"Original H area={int(old_H.sum())}, new bounded area={int(new_H.sum())}, manual approximate area={int(manual.sum())} px2.",
       (12,72),cv2.FONT_HERSHEY_SIMPLEX,.48,(42,58,76),1,cv2.LINE_AA)
    cv2.putText(out,
       "Newly restored perimeter is PRELIMINARY and NEEDS HUMAN REVIEW; no validated physical size.",
       (12,94),cv2.FONT_HERSHEY_SIMPLEX,.44,(35,63,79),1,cv2.LINE_AA)
    for j,(name,note,panel) in enumerate(rows):
        xx=j*(pix+pad)
        cv2.putText(out,name[:38],(xx+2,header+15),
                    cv2.FONT_HERSHEY_SIMPLEX,.39,(35,53,66),1,cv2.LINE_AA)
        cv2.putText(out,note[:41],(xx+2,header+31),
                    cv2.FONT_HERSHEY_SIMPLEX,.30,(58,78,85),1,cv2.LINE_AA)
        out[header+40:header+40+pix,xx:xx+pix]=panel
    image_path=NEW/"figures"/"E2_W005_cross_scratch_before_after.png"
    ok,buf=cv2.imencode(".png",out,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise IOError("PNG encode")
    image_path.write_bytes(buf.tobytes())
    df.to_csv(NEW/"W005_refinement_before_after_metrics.csv",
              encoding="utf-8-sig",index=False)
    detail={
        "comparison_is_after_prediction_not_algorithm_input":True,
        "manual_polygon_approximation_not_exact_physical_ground_truth":True,
        "H_anchor_id":H_ID,
        "new_bounded_mask_status":"needs_review_bounded_extension",
        "threshold_type":"local background DN",
        "new_background_independent_candidates":0,
        "new_contrast_two_estimator_intersection":True,
        "reference_ROI_origin_RAW":[2944,1024],
        "reference_ROI_size_px":[256,256],
        "comparison_metrics":result,
        "target_reaches_actual_cross_center":"other H components; not proven one physical contiguous mask",
    }
    (NEW/"W005_refinement_before_after.json").write_text(
        json.dumps(detail,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    print("W005_COMPARISON",df.to_string(index=False))
    print("W005_FIGURE",image_path)


if __name__=="__main__":
    run()
