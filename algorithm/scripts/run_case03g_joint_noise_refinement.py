"""Case03-G: 10-target evaluation of RAW noise gate + saved bounded G/M refinements.

Actual detector input: historical H masks and E2's automatically detected
H-anchored refined contours. Annotation geometry is used only after gating,
for ten independent review images and post-hoc overlap measurement.
"""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
import sys

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03g_joint_gate import (
    JointGateConfig,decide_gate,build_joint_maps,
)

LOG=logging.getLogger(__name__)
SOURCE=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"
SCREEN=ROOT/"outputs/case03f_localcontrast/run_20261010_small_raw_contrast_v1"
ANNOTATIONS=Path(r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv")
TARGETS=("RAW26_MANUAL_001","RAW26_MANUAL_002","RAW26_MANUAL_003",
         "RAW26_MANUAL_004","RAW26_MANUAL_006","RAW26_MANUAL_007",
         "RAW26_MANUAL_008","RAW26_MANUAL_009","RAW26_MANUAL_010",
         "RAW26_MANUAL_011")


def save_png(path:Path,image:np.ndarray)->None:
    ok,payload=cv2.imencode(".png",image,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise OSError("PNG encode failed: "+str(path))
    path.write_bytes(payload.tobytes())
    if path.stat().st_size < 1000:
        raise OSError("PNG save failed: "+str(path))
    test=cv2.imdecode(np.frombuffer(path.read_bytes(),dtype=np.uint8),
                      cv2.IMREAD_COLOR)
    if test is None or test.shape[:2]!=image.shape[:2]:
        raise OSError("PNG could not be decoded: "+str(path))


def gray(raw:np.ndarray)->np.ndarray:
    f=raw.astype(np.float32)
    lo,hi=np.percentile(f,[1,99.5])
    hi=max(float(hi),float(lo)+1)
    mono=np.uint8(np.rint(np.clip((f-lo)/(hi-lo),0,1)*255))
    return cv2.cvtColor(mono,cv2.COLOR_GRAY2BGR)


def panel(raw:np.ndarray, masks:list[tuple[np.ndarray,tuple[int,int,int]]],
          title:str, polygon:np.ndarray|None=None,zoom:int=1)->np.ndarray:
    """Overlay displays only; RGB colors are BGR tuples."""
    rgb=gray(raw)
    for m,color in masks:
        if m.shape!=raw.shape:
            raise ValueError("image overlay shape mismatch")
        rgb[m]=np.uint8(np.rint(rgb[m]*.35+np.asarray(color)*.65))
    if polygon is not None:
        cv2.polylines(rgb,[polygon.reshape(-1,1,2)],True,(250,218,55),1,
                      lineType=cv2.LINE_8)
    if zoom>1:
        rgb=cv2.resize(rgb,None,fx=zoom,fy=zoom,
                       interpolation=cv2.INTER_NEAREST)
    rgb=cv2.copyMakeBorder(rgb,30,0,0,0,cv2.BORDER_CONSTANT,value=(32,32,32))
    cv2.putText(rgb,title,(7,20),cv2.FONT_HERSHEY_SIMPLEX,.47,
                (235,235,235),1,cv2.LINE_AA)
    return rgb


def present_four(raw:np.ndarray, masks:dict[str,np.ndarray],
                 protected_review:np.ndarray,title:str,
                 poly:np.ndarray|None=None,zoom:int=1)->np.ndarray:
    return np.hstack([
        panel(raw,[],title+" RAW",polygon=poly,zoom=zoom),
        panel(raw,[(masks["h_original"],(70,210,50))],
              title+" H 170/230",zoom=zoom),
        panel(raw,[(masks["h_kept_display"],(70,210,50)),
                   (protected_review,(215,90,210)),
                   (masks["h_hidden_suggestion"],(45,120,240))],
              title+" RAW noise gate",zoom=zoom),
        panel(raw,[(masks["fused_joint_display"],(70,210,50)),
                   (protected_review,(215,90,210))],
              title+" H+G22+C61",zoom=zoom),
    ])


def crop_bounds(cx:int,cy:int,origin:tuple[int,int],
                shape:tuple[int,int],size:int=160)->tuple[int,int,int,int]:
    h,w=shape
    x=max(0,min(w-size,cx-origin[0]-size//2))
    y=max(0,min(h-size,cy-origin[1]-size//2))
    return int(x),int(y),int(x+size),int(y+size)


def run(run_id:str,config:JointGateConfig)->Path:
    output=cfg.OUTPUT_ROOT/"case03g_joint"/run_id
    if output.exists():
        raise FileExistsError(f"Never overwrite a past stage: {output}")
    (output/"figures_10_targets").mkdir(parents=True)
    (output/"figures_9_windows").mkdir()
    trial=pd.read_csv(SCREEN/"candidate_trial_decisions.csv",
                      encoding="utf-8-sig")
    refs=pd.read_csv(SOURCE/"ten_manual_targets_posthoc_evaluation.csv")
    assert set(refs.manual_target_id)==set(TARGETS) and len(refs)==10
    manual=pd.read_csv(ANNOTATIONS,encoding="utf-8-sig").fillna("")
    all_objects=[json.loads(l) for l in
                 (SOURCE/"all_window_objects_exact.jsonl").open(encoding="utf-8")]
    objects={o["local_object_id"]:o for o in all_objects}
    raw_memmap=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                        shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    decisions=[];summaries=[];posthoc=[]
    for npz in sorted((SOURCE/"masks").glob("E2_W*_labels.npz")):
        win=npz.name.removesuffix("_labels.npz")
        with np.load(npz) as z:
            H=z["H170_230"].astype(bool)
            F=z["all_object_labels"].astype(np.int32)
            origin=tuple(int(v) for v in z["roi_origin_raw_xy"])
        n,labels,stats,_=cv2.connectedComponentsWithStats(
            H.astype(np.uint8),connectivity=8)
        window_states=trial.loc[trial.window_id==win].set_index("local_H_id")
        if len(window_states)!=n-1:
            raise AssertionError("H-trial catalogue mismatch: "+win)
        item_states=[];sources=[]
        for j in range(1,n):
            key=f"Hlocal_{j:04d}"
            objid=f"{win}_O{j:04d}"
            if key not in window_states.index or objid not in objects:
                raise AssertionError("missing H/refined ID: "+key)
            rec=objects[objid]
            if rec["window_id"]!=win:
                raise AssertionError("wrong refined source ID")
            if int(rec["exact_area_px"])!=int((F==j).sum()):
                raise AssertionError("refined object area mismatch")
            status=str(window_states.at[key,"trial_status"])
            item_states.append(status)
            sources.append(tuple(rec["sources"]))
        gate,reasons=decide_gate(labels,stats,item_states,sources,config)
        masks=build_joint_maps(labels,F,gate)
        # Already computed E2 Gaussian22 and Closing61 contours are used here.
        # New independent G/M components are NEVER created.
        protected_review=np.isin(labels,[j for j in range(1,n)
            if gate[j-1]=="protected_review"])
        for j in range(1,n):
            decisions.append({
                "window_id":win,"local_H_id":f"Hlocal_{j:04d}",
                "local_object_id":f"{win}_O{j:04d}",
                "trial_state":item_states[j-1],
                "joint_gate_state":gate[j-1],
                "joint_gate_reason":reasons[j-1],
                "existing_refinement_sources":"+".join(sources[j-1]),
                "original_H_area_px":int(stats[j,cv2.CC_STAT_AREA]),
                "precomputed_refined_area_px":int((F==j).sum()),
                "source_H_retained_in_archive":True,
                "manual_labels_used_for_gate":False,
            })
        x0,y0=origin
        image=np.asarray(raw_memmap[y0:y0+H.shape[0],
                                    x0:x0+H.shape[1]],dtype=np.uint16)
        overview=present_four(image,masks,protected_review,win)
        save_png(output/"figures_9_windows"/f"{win}_four_panel.png",overview)
        summaries.append({
            "window_id":win,
            "source_H_candidates":n-1,
            "display_hidden_candidate_count":gate.count("hide_suggestion"),
            "protected_review_candidate_count":gate.count("protected_review"),
            "keep_candidate_count":gate.count("keep"),
            "original_H_pixels":int(H.sum()),
            "original_precomputed_refined_pixels":int(masks["fused_original"].sum()),
            "H_kept_display_pixels":int(masks["h_kept_display"].sum()),
            "gated_precomputed_refined_pixels":int(masks["fused_joint_display"].sum()),
        })
        selected=refs.loc[refs.window_id==win]
        for rec in selected.itertuples(index=False):
            target=str(rec.manual_target_id)
            cx,cy=int(rec.clicked_RAW_x),int(rec.clicked_RAW_y)
            x,y,xx,yy=crop_bounds(cx,cy,origin,H.shape)
            # Human shape is used ONLY now, downstream of the detector/gate.
            polyrows=manual.loc[manual.annotation_kind.eq("poly")].copy()
            polyrows["_distance_sq"]=(pd.to_numeric(polyrows.raw_x)-cx)**2+(
                                      pd.to_numeric(polyrows.raw_y)-cy)**2
            polyrow=polyrows.sort_values("_distance_sq").iloc[0]
            if float(polyrow["_distance_sq"])>400:
                raise AssertionError("no independently matching manual polygon: "+target)
            vertices=np.asarray(
                json.loads(polyrow.vertices_RAW_global_xy_JSON),dtype=np.int32)
            polygon=vertices-np.array([origin[0]+x,origin[1]+y],dtype=np.int32)
            cropped={key:mask[y:yy,x:xx] for key,mask in masks.items()}
            region=present_four(image[y:yy,x:xx],cropped,
                                protected_review[y:yy,x:xx],target,
                                poly=polygon,zoom=3)
            save_png(output/"figures_10_targets"/f"{target}_four_panel.png",region)
            # Complete-window manual polygon is used for post-hoc overlap only.
            m=np.zeros(H.shape,dtype=np.uint8)
            fullpoints=vertices-np.asarray(origin,dtype=np.int32)
            cv2.fillPoly(m,[fullpoints.reshape(-1,1,2)],1)
            ismanual=m.astype(bool)
            previous=int(np.count_nonzero(ismanual & masks["h_original"]))
            after=int(np.count_nonzero(ismanual & masks["h_kept_display"]))
            refined=int(np.count_nonzero(ismanual & masks["fused_joint_display"]))
            posthoc.append({
                "manual_target_id":target,"window_id":win,
                "existing_H_overlap_px":previous,
                "joint_H_overlap_px":after,
                "gated_refined_overlap_px":refined,
                "H_retention_fraction":round(after/max(1,previous),4),
                "raw_manual_approx_area_px":int(ismanual.sum()),
                "manual_polygon_for_posthoc_only":True,
                "not_physical_detection_accuracy":True,
            })
        LOG.info("%s %d candidates, %d hidden suggestions, %d protected review",
                 win,n-1,gate.count("hide_suggestion"),
                 gate.count("protected_review"))
    if len(summaries)!=9 or len(posthoc)!=10 or len(decisions)!=1569:
        raise AssertionError("Expected exactly 9 windows, 10 targets, 1569 H components")
    decisions_csv=output/"joint_candidate_audit.csv"
    pd.DataFrame(decisions).to_csv(decisions_csv,index=False,encoding="utf-8-sig")
    pd.DataFrame(summaries).to_csv(output/"nine_window_comparison.csv",
                                  index=False,encoding="utf-8-sig")
    pd.DataFrame(posthoc).to_csv(output/"ten_manual_targets_posthoc.csv",
                                index=False,encoding="utf-8-sig")
    files=list((output/"figures_10_targets").glob("*.png"))
    wins=list((output/"figures_9_windows").glob("*.png"))
    if len(files)!=10 or len(wins)!=9:
        raise AssertionError("Missing PNG files; refusing success")
    total=pd.DataFrame(summaries).select_dtypes(include="number").sum()
    htarget=[r["manual_target_id"] for r in posthoc
             if r["H_retention_fraction"] < 1.0]
    summary={
        "sample_frame":"26 (1)", "H_source_candidates_archived":1569,
        "windows":len(wins),"individual_target_images":len(files),
        "source_masks_and_refined_masks_modified":False,
        "prior_refinement_reused":True,
        "gaussian_closing_can_propose_independent_targets":False,
        "raw_noise_gate_suggest_hide":int(total["display_hidden_candidate_count"]),
        "raw_noise_gate_protected_review":int(total["protected_review_candidate_count"]),
        "raw_noise_gate_keep":int(total["keep_candidate_count"]),
        "original_H_pixels":int(total["original_H_pixels"]),
        "display_gated_H_pixels":int(total["H_kept_display_pixels"]),
        "original_refined_pixels":int(total["original_precomputed_refined_pixels"]),
        "display_gated_refined_pixels":int(total["gated_precomputed_refined_pixels"]),
        "manual_regions_with_any_H_display_loss":htarget,
        "scope":"pilot 10 selected targets in 9 windows; not full frame",
        "independent_validation":"PENDING_USER"
    }
    (output/"summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"config_snapshot.json").write_text(
        json.dumps({"joint_gate_config":config.__dict__,"source":str(SOURCE),
                    "raw_screen":str(SCREEN),"annotation_use":"posthoc only"},
                   ensure_ascii=False,indent=2),encoding="utf-8")
    LOG.info("RESULT %s",output)
    LOG.info("SUMMARY %s",summary)
    LOG.info("MANUAL CHECK %s",pd.DataFrame(posthoc)[
        ["manual_target_id","H_retention_fraction"]].to_dict("records"))
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default="run_20261010_10target_noise_refinement_v1")
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    run(args.run_id,JointGateConfig(
        protect_support_area_min_px=cfg.CASE03G_PROTECT_STRUCTURE_MIN_AREA_PX,
        protect_support_radius_px=cfg.CASE03G_PROTECT_STRUCTURE_RADIUS_PX,
        protect_any_existing_refinement=cfg.CASE03G_PROTECT_EXISTING_REFINEMENT,
    ))
