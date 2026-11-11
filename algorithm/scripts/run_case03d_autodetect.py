"""Case03-D-R2: automatic provisional triage and exact candidate contours.

Engineering baseline, not independently validated physical filter defects.
Never delete source candidate, even if labeled noise_like_retained.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.candidate_autodecision import (
    REVIEW_STATES,classify_candidates,inspect_reviewed_against_triage
)
from src.detection.candidate_contour_export import describe_exact_contour
from src.detection.thresholding import load_packed_mask

FEAT=ROOT/"outputs/case03c/run_20261008_174000/hysteresis_candidate_features.csv"
HNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_H_TL170_TH230.npz"
SNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_S_TL230_TH230.npz"
CORRECTED=ROOT/"outputs/case03d/run_20261009_190000/manual_label_revision_after_review045/strict_corrected_labels.csv"
PRIORITY=ROOT/"outputs/case03d/run_20261009_190000/review_order.csv"
DATA_RAW=cfg.DATA_ROOT/"26 (1).raw"


def fingerprint(path):
    s=path.stat()
    info={"path":str(path),"bytes":s.st_size,"mtime_ns":s.st_mtime_ns}
    if s.st_size<=40_000_000:
        info["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    return info


def reviewed_labels(path):
    a=pd.read_csv(path,dtype=str,keep_default_na=False)
    if len(a)!=55 or a["candidate_id"].duplicated().any():
        raise ValueError("human review correction missing/duplicate")
    counts=dict(Counter(a["manual_label"]))
    if counts!={"confirmed_dark_spot":13,"background_artifact":42}:
        raise ValueError(f"latest human label counts incorrect: {counts}")
    return dict(zip(a["candidate_id"],a["manual_label"]))


def sorted_uncertain(f):
    return f.sort_values(["near_band_transition","peak_response_dn","area_px","candidate_id"],
                          ascending=[True,False,False,True],kind="mergesort")


def draw_centroid_locator(path,frame,raw,stride=6):
    bg=np.asarray(raw[::stride,::stride],dtype=np.float32)
    lo,hi=np.percentile(bg,[1,99.5]);hi=max(lo+1,hi)
    grey=np.uint8(np.rint(np.clip((bg-lo)/(hi-lo),0,1)*185+35))
    out=cv2.cvtColor(grey,cv2.COLOR_GRAY2BGR)
    for status,color,radius in (
        ("uncertain_review",(25,175,235),1),
        ("detected_provisional",(45,228,40),2)
    ):
        for row in frame[frame["triage_status"].eq(status)].itertuples(index=False):
            cx=int(round(row.centroid_x/stride));cy=int(round(row.centroid_y/stride))
            if 0<=cx<out.shape[1] and 0<=cy<out.shape[0]:
                cv2.circle(out,(cx,cy),radius,color,-1)
    cv2.rectangle(out,(8,8),(1110,76),(245,245,245),-1)
    cv2.putText(out,"Case03-D-R2: green=provisional detected, amber=uncertain",
                (17,33),cv2.FONT_HERSHEY_SIMPLEX,.7,(28,28,28),1,cv2.LINE_AA)
    cv2.putText(out,"CENTROID LOCATOR ONLY, not actual contours. Noise-like candidate IDs are retained.",
                (17,59),cv2.FONT_HERSHEY_SIMPLEX,.52,(38,38,38),1,cv2.LINE_AA)
    ok,image=cv2.imencode(".png",out)
    if not ok:raise IOError(path)
    path.write_bytes(image.tobytes())


def tile_for(row,raw,H,S,size=160):
    height,width=raw.shape
    cx=int(round(float(row["centroid_x"])))
    cy=int(round(float(row["centroid_y"])))
    x0=min(max(0,cx-size//2),width-size)
    y0=min(max(0,cy-size//2),height-size)
    x1=x0+size;y1=y0+size
    xraw=np.asarray(raw[y0:y1,x0:x1],dtype=np.float32)
    lo,hi=np.percentile(xraw,[1,99.5]);hi=max(lo+1,hi)
    grey=np.uint8(np.rint(np.clip((xraw-lo)/(hi-lo),0,1)*255))
    raw_bgr=cv2.cvtColor(grey,cv2.COLOR_GRAY2BGR)
    seg=raw_bgr.copy()
    sp=S[y0:y1,x0:x1]
    hp=H[y0:y1,x0:x1]
    seg[sp]=(18,226,255)
    seg[hp&~sp]=(239,215,27)
    exact=raw_bgr.copy()
    _meta,component,(bx,by,bw,bh)=describe_exact_contour(H,row)
    xa=max(x0,bx);xb=min(x1,bx+bw)
    ya=max(y0,by);yb=min(y1,by+bh)
    if xb>xa and yb>ya:
        local=component[ya-by:yb-by,xa-bx:xb-bx].astype(bool)
        v=exact[ya-y0:yb-y0,xa-x0:xb-x0]
        v[local]=(35,216,59)
    cv2.rectangle(exact,(bx-x0,by-y0),(bx+bw-1-x0,by+bh-1-y0),(26,40,245),1)
    cv2.drawMarker(raw_bgr,(cx-x0,cy-y0),(20,20,245),cv2.MARKER_CROSS,9,1)
    sep=np.full((size,6,3),245,dtype=np.uint8)
    combo=np.concatenate([raw_bgr,sep,seg,sep,exact],axis=1)
    label_h=53
    tile=np.full((size+label_h,combo.shape[1],3),244,dtype=np.uint8)
    tile[label_h:]=combo
    title=str(row["candidate_id"]).replace("H_sample26_","H_")
    cv2.putText(tile,f"{title} / {row['triage_status']}",(6,17),
                cv2.FONT_HERSHEY_SIMPLEX,.40,(30,42,52),1,cv2.LINE_AA)
    cv2.putText(tile,f"Area {int(row['area_px'])} px; peak {int(row['peak_response_dn'])} DN",
                (6,34),cv2.FONT_HERSHEY_SIMPLEX,.41,(32,44,50),1,cv2.LINE_AA)
    cv2.putText(tile,"RAW         all S/H           EXACT selected", (6,48),
                cv2.FONT_HERSHEY_SIMPLEX,.40,(45,45,45),1,cv2.LINE_AA)
    return tile


def draw_atlas(out,frame,H,S,labels):
    folder=out/"figures"
    folder.mkdir(exist_ok=True)
    raw=np.memmap(DATA_RAW,mode="r",dtype=">u2",shape=H.shape)
    draw_centroid_locator(folder/"automatic_detection_centroid_locator.png",frame,raw)
    targets=[
        ("detected_top12",frame[frame["triage_status"]=="detected_provisional"].sort_values(
            ["peak_response_dn","area_px"],ascending=False).head(12)),
        ("uncertain_top12",sorted_uncertain(frame[frame["triage_status"]=="uncertain_review"]).head(12)),
        ("band_edge_artifacts",frame[frame["band_edge_artifact_signature"]].head(12)),
        ("human_positive_13",frame[frame["candidate_id"].isin(
            [key for key,value in labels.items() if value=="confirmed_dark_spot"])]),
        ("human_negative_top12",frame[frame["candidate_id"].isin(
            [key for key,value in labels.items() if value=="background_artifact"])].sort_values(
                ["area_px","peak_response_dn"],ascending=False).head(12))
    ]
    manifest=[]
    for name,group in targets:
        rs=group.to_dict("records")
        if not rs:continue
        # Scheme A: this particular atlas must visualize ALL AUTO candidates
        # inside each ROI, not only the current selected component.
        if name=="detected_top12":
            from src.visualization.case03d_detected_atlas import atlas_three_view
            with np.load(out/"candidate_status_map_lossless.npz",
                         allow_pickle=False) as arr:
                status_map=arr["class_map"]
            all_detected=frame.loc[
                frame["triage_status"]=="detected_provisional"
            ].to_dict("records")
            three,roi_numbers=atlas_three_view(
                rs,all_detected,raw,H,S,status_map,size=160,columns=3)
            if len(rs)!=12:
                raise AssertionError("unexpected top12 card count")
            ok,png=cv2.imencode(".png",three)
            if not ok:raise IOError("atlas_detected_top12 three-panel encode")
            (folder/"atlas_detected_top12.png").write_bytes(png.tobytes())
            pd.DataFrame(roi_numbers).to_csv(
                out/"atlas_detected_top12_roi_numbers.csv",
                index=False,encoding="utf-8-sig")
            for row in rs:
                manifest.append({
                    "atlas_name":name,
                    "candidate_id":row["candidate_id"],
                    "triage_status":row["triage_status"],
                    "manual_label":labels.get(row["candidate_id"],"unlabeled")
                })
            continue
        w=3*160+12
        h=160+53
        gap=12
        image=np.full((int(math.ceil(len(rs)/3))*(h+gap)+43,3*(w+gap),3),245,np.uint8)
        cv2.putText(image,name+": left RAW, middle all-S/H, right EXACT target pixels",
                    (15,28),cv2.FONT_HERSHEY_SIMPLEX,.62,(35,46,56),1,cv2.LINE_AA)
        for i,row in enumerate(rs):
            tile=tile_for(row,raw,H,S)
            px=(i%3)*(w+gap)
            py=43+(i//3)*(h+gap)
            image[py:py+h,px:px+w]=tile
            manifest.append({"atlas_name":name,"candidate_id":row["candidate_id"],
                             "triage_status":row["triage_status"],
                             "manual_label":labels.get(row["candidate_id"],"unlabeled")})
        ok,png=cv2.imencode(".png",image)
        if not ok:raise IOError(name)
        (folder/("atlas_"+name+".png")).write_bytes(png.tobytes())
    pd.DataFrame(manifest).to_csv(out/"atlas_manifest.csv",index=False,encoding="utf-8-sig")


def run(run_id=None):
    started=perf_counter()
    base=cfg.OUTPUT_ROOT/"case03d_autodetect"
    base.mkdir(exist_ok=True)
    out=base/(run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    if out.exists():raise FileExistsError(out)
    out.mkdir()
    protected=[FEAT,HNPZ,SNPZ,CORRECTED,PRIORITY]
    before=[fingerprint(p) for p in protected]
    source=pd.read_csv(FEAT,dtype={"candidate_id":str},low_memory=False)
    if len(source)!=88043 or int(source["area_px"].sum())!=311790:
        raise AssertionError("Case03-C H candidate population mismatch")
    if not (source["sample"].eq(26).all() and source["frame"].eq(1).all() and
            source["method"].eq("H").all() and
            source["low_threshold_dn"].eq(170).all() and
            source["high_threshold_dn"].eq(230).all()):
        raise AssertionError("wrong source sample or thresholds")
    decisions=classify_candidates(
        source,
        auto_min_area=cfg.CASE03D_AUTO_MIN_AREA_PX,
        auto_min_peak=cfg.CASE03D_AUTO_MIN_PEAK_DN,
        auto_min_raw_delta=cfg.CASE03D_AUTO_MIN_RAW_DARK_DELTA_DN,
        auto_min_fill=cfg.CASE03D_AUTO_MIN_BBOX_FILL,
        review_min_area=cfg.CASE03D_AUTO_REVIEW_MIN_AREA_PX,
        review_min_peak=cfg.CASE03D_AUTO_REVIEW_MIN_PEAK_DN,
        tiny_high_peak=cfg.CASE03D_AUTO_REVIEW_TINY_HIGH_PEAK_DN,
    )
    frame=source.copy()
    for name in decisions.columns:
        if name!="candidate_id":
            frame[name]=decisions[name].to_numpy()
    # The prior A/B/C order is metadata only, not an independent feature.
    ranking=pd.read_csv(PRIORITY,usecols=["candidate_id","priority_rank","review_tier"],
                        dtype={"candidate_id":str})
    frame=frame.merge(ranking,on="candidate_id",sort=False,how="left",validate="one_to_one")
    if len(frame)!=len(source) or frame["priority_rank"].isna().any():
        raise AssertionError("ranking merge missing candidate")
    frame["decision_version"]="Case03D_R2_unvalidated_fixed_rules"
    frame["physical_defect_confirmed"]=False
    frame.to_csv(out/"candidate_decisions_full.csv",index=False,encoding="utf-8-sig")
    detected=frame[frame["triage_status"].eq("detected_provisional")].sort_values(
        ["peak_response_dn","area_px"],ascending=[False,False])
    uncertain=sorted_uncertain(frame[frame["triage_status"].eq("uncertain_review")])
    noise=frame[frame["triage_status"].eq("noise_like_retained")]
    detected.to_csv(out/"detected_provisional.csv",index=False,encoding="utf-8-sig")
    uncertain.to_csv(out/"uncertain_review_full.csv",index=False,encoding="utf-8-sig")
    uncertain.head(cfg.CASE03D_AUTO_UNCERTAIN_FIRST_BATCH).to_csv(
        out/"uncertain_review_top500.csv",index=False,encoding="utf-8-sig"
    )
    noise.to_csv(out/"noise_like_retained.csv",index=False,encoding="utf-8-sig")
    labels=reviewed_labels(CORRECTED)
    comparisons=inspect_reviewed_against_triage(decisions,labels)
    pd.DataFrame(comparisons).to_csv(out/"in_sample_human_comparison.csv",
                                     index=False,encoding="utf-8-sig")
    H=load_packed_mask(HNPZ)
    S=load_packed_mask(SNPZ)
    if not (H.shape==S.shape==(9200,11276)) or np.any(S&~H):
        raise AssertionError("H/S original mask geometry changed")
    classes=np.zeros(H.shape,dtype=np.uint8)
    classes[H]=1
    geometries=[]
    processed=0
    with (out/"component_contours_exact.jsonl").open("w",encoding="utf-8") as handle:
        for r in pd.concat([detected,uncertain]).to_dict("records"):
            item,blob,(x,y,w,h)=describe_exact_contour(H,r)
            item["decision_reason"]=r["decision_reason"]
            handle.write(json.dumps(item,ensure_ascii=False,separators=(",",":"))+"\n")
            cut=classes[y:y+h,x:x+w]
            active=blob.astype(bool)
            if not np.all(cut[active]==1):
                raise AssertionError(f"component overlap: {r['candidate_id']}")
            cut[active]=3 if r["triage_status"]=="detected_provisional" else 2
            geometries.append({
                "candidate_id":r["candidate_id"],"triage_status":r["triage_status"],
                "morphology_hint":r["morphology_hint"],
                "centroid_x":r["centroid_x"],"centroid_y":r["centroid_y"],
                "bbox_x":x,"bbox_y":y,"bbox_w":w,"bbox_h":h,
                "exact_area_px":int(blob.sum()),
                "peak_response_dn":int(r["peak_response_dn"]),
                "contour_count":len(item["boundary_contours"]),
                "holes":item["hole_count"],
                "binary_mask_packed_in_jsonl":True
            })
            processed+=1
            if processed%2000==0:
                print("EXACT_CONTOUR_PROGRESS",processed,flush=True)
    assert np.array_equal(classes>0,H)
    area_per_class={k:int((classes==v).sum()) for k,v in (
        ("noise_like_retained",1),("uncertain_review",2),("detected_provisional",3))}
    if any(area_per_class[k]!=int(group["area_px"].sum())
           for k,group in (("noise_like_retained",noise),
                           ("uncertain_review",uncertain),
                           ("detected_provisional",detected))):
        raise AssertionError("pixel-area conservation mismatch")
    np.savez_compressed(out/"candidate_status_map_lossless.npz",
        class_map=classes,
        status_definitions=np.array(["0=not H","1=noise_like_retained",
            "2=uncertain_review","3=detected_provisional"]))
    pd.DataFrame(geometries).to_csv(out/"exact_region_geometry.csv",
                                   index=False,encoding="utf-8-sig")
    draw_atlas(out,frame,H,S,labels)
    from scripts.render_case03d_autodetect_fullview import make_preview
    if make_preview(out)!=len(detected):
        raise AssertionError("full-view contour preview count mismatch")
    after=[fingerprint(p) for p in protected]
    if before!=after:
        raise AssertionError("protected inputs changed")
    (out/"source_manifest.json").write_text(json.dumps({
        "sources_before":before,"sources_after":after,"unchanged":True
    },ensure_ascii=False,indent=2),encoding="utf-8")
    counts={k:int(frame["triage_status"].eq(k).sum()) for k in REVIEW_STATES}
    if sum(counts.values())!=88043 or processed!=counts["detected_provisional"]+counts["uncertain_review"]:
        raise AssertionError("candidate state count mismatch")
    summary={
        "status":"ENGINEERING_PASS_PENDING_INDEPENDENT_DETECTION_VALIDATION",
        "source_candidate_count":88043,
        "source_H_mask_pixels":311790,
        "candidate_counts":counts,
        "exact_contoured_regions":processed,
        "class_map_status_codes":{"0":"outside existing H",
            "1":"noise_like_retained","2":"uncertain_review","3":"detected_provisional"},
        "class_pixel_counts":area_per_class,
        "manually_reviewed_development_sample":{"positive":13,"negative":42},
        "in_sample_reviewed_comparison":comparisons,
        "independent_holdout_available":False,
        "user_observations_previously_informed_rules":True,
        "no_candidate_deleted":True,
        "mask_and_feature_sources_unchanged":True,
        "no_physical_filter_defect_probabilities":True,
        "uncertain_initial_review_budget":min(len(uncertain),500),
        "non_target_ROIs":"review_031_046_056 user deferred",
        "runtime_seconds":round(perf_counter()-started,3)}
    config_keys=[
        "CASE03D_AUTO_MIN_AREA_PX","CASE03D_AUTO_MIN_PEAK_DN",
        "CASE03D_AUTO_MIN_RAW_DARK_DELTA_DN","CASE03D_AUTO_MIN_BBOX_FILL",
        "CASE03D_AUTO_REVIEW_MIN_AREA_PX","CASE03D_AUTO_REVIEW_MIN_PEAK_DN",
        "CASE03D_AUTO_REVIEW_TINY_HIGH_PEAK_DN",
        "CASE03D_AUTO_UNCERTAIN_FIRST_BATCH",
        "CASE03D_AUTO_EXPECTED_SOURCE_H_COUNT",
        "CASE03D_AUTO_EXPECTED_SOURCE_H_PIXELS",
        "CASE03D_AUTO_ROI_031_046_056"
    ]
    (out/"config_snapshot.json").write_text(json.dumps(
        {k:getattr(cfg,k) for k in config_keys},ensure_ascii=False,indent=2
    ),encoding="utf-8")
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    (out/"acceptance.json").write_text(json.dumps({
        "engineering_status":"PASS",
        "all_original_candidate_ids_and_pixels_preserved":True,
        "accurate_H_mask_per_region_and_contours_written":True,
        "user_labels_not_inputs_to_decision_function":True,
        "physical_defect_accuracy_validated":False,
        "independent_validation_status":"PENDING_HUMAN_EXTERNAL_REVIEW",
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("CASE03D_R2_OUTPUT",out)
    print("CASE03D_R2_SUMMARY",json.dumps(summary,ensure_ascii=False))
    return out


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id")
    run(parser.parse_args().run_id)
