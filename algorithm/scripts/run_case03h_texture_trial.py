"""Case03-H: second-stage medium area texture-veto pilot on selected 10 targets.

Reuses READ-ONLY source H masks, Case03-G gate decisions and existing bounded
Gaussian22/Closing61 refined contours. Manual polygons used only for after-gate
review images and post-hoc intersection, NEVER for any gate decision.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
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
from src.detection.case03g_joint_gate import build_joint_maps
from src.detection.case03h_background_texture import TextureTrialConfig,extend_gate
from scripts.run_case03g_joint_noise_refinement import (
    gray,panel,save_png,crop_bounds,TARGETS,SOURCE,SCREEN,ANNOTATIONS,
)

LOG=logging.getLogger(__name__)
G_STAGE=ROOT/"outputs/case03g_joint/run_20261010_10target_noise_refinement_v1"


def _five(raw:np.ndarray,old_maps:dict,new_maps:dict,
          new_hidden:np.ndarray,title:str,poly:np.ndarray|None,zoom:int)->np.ndarray:
    return np.hstack([
        panel(raw,[],title+" RAW",polygon=poly,zoom=zoom),
        panel(raw,[(old_maps["h_original"],(55,220,70))],
              title+" H 170/230",zoom=zoom),
        panel(raw,[(old_maps["fused_joint_display"],(55,220,70))],
              title+" Case03G output",zoom=zoom),
        panel(raw,[(new_maps["h_kept_display"],(55,220,70)),
                   (new_hidden,(35,135,245))],
              title+" H texture gate",zoom=zoom),
        panel(raw,[(new_maps["fused_joint_display"],(55,220,70))],
              title+" H+G22+C61",zoom=zoom)
    ])


def run(run_id:str,config:TextureTrialConfig)->Path:
    dest=cfg.OUTPUT_ROOT/"case03h_texture"/run_id
    if dest.exists():raise FileExistsError(f"experiment exists: {dest}")
    (dest/"figures_10_targets").mkdir(parents=True)
    (dest/"figures_9_windows").mkdir()
    fdf=pd.read_csv(SCREEN/"candidate_trial_decisions.csv",encoding="utf-8-sig")
    gdf=pd.read_csv(G_STAGE/"joint_candidate_audit.csv",encoding="utf-8-sig")
    refs=pd.read_csv(SOURCE/"ten_manual_targets_posthoc_evaluation.csv")
    manual=pd.read_csv(ANNOTATIONS,encoding="utf-8-sig").fillna("")
    if len(refs)!=10 or set(refs.manual_target_id)!=set(TARGETS):
        raise AssertionError("Expected EXACTLY 10 user cases")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    records=[];summaries=[];evaluations=[]
    for file in sorted((SOURCE/"masks").glob("E2_W*_labels.npz")):
        win=file.name.removesuffix("_labels.npz")
        with np.load(file) as z:
            h=z["H170_230"].astype(bool)
            refined_labels=z["all_object_labels"].astype(np.int32)
            ox,oy=[int(v) for v in z["roi_origin_raw_xy"]]
        n,labels,stats,_=cv2.connectedComponentsWithStats(
            h.astype(np.uint8),connectivity=8)
        tile=np.asarray(raw[oy:oy+h.shape[0],ox:ox+h.shape[1]],dtype=np.uint16)
        float_raw=tile.astype(np.float32)
        coherent_dark=(cv2.GaussianBlur(
                           float_raw,(0,0),config.dog_large_sigma_px)-
                       cv2.GaussianBlur(
                           float_raw,(0,0),config.dog_small_sigma_px))
        trial=fdf.loc[fdf.window_id==win].set_index("local_H_id")
        earlier=gdf.loc[gdf.window_id==win].set_index("local_H_id")
        if len(trial)!=n-1 or len(earlier)!=n-1:
            raise AssertionError(win+" candidate count mismatch")
        features=[];earlier_states=[];earlier_reasons=[]
        for j in range(1,n):
            key=f"Hlocal_{j:04d}"
            if key not in trial.index or key not in earlier.index:
                raise AssertionError(win+" missing "+key)
            a=trial.loc[key].to_dict()
            a["dog_median_dn"]=float(np.median(coherent_dark[labels==j]))
            b=earlier.loc[key]
            if int(a["area_px"])!=int(stats[j,cv2.CC_STAT_AREA]):
                raise AssertionError("Case03F inconsistent area")
            features.append(a)
            earlier_states.append(str(b.joint_gate_state))
            earlier_reasons.append(str(b.joint_gate_reason))
        new_states,new_reasons=extend_gate(
            labels,stats,earlier_states,earlier_reasons,features,config
        )
        old_masks=build_joint_maps(labels,refined_labels,earlier_states)
        new_masks=build_joint_maps(labels,refined_labels,new_states)
        new_hidden_ids=[j for j in range(1,n)
            if earlier_states[j-1]!="hide_suggestion" and new_states[j-1]=="hide_suggestion"]
        hidden_new=np.isin(labels,new_hidden_ids)
        if np.any(new_masks["fused_joint_display"] & ~old_masks["fused_joint_display"]):
            raise AssertionError("Case03H cannot add independent proposals")
        if not np.array_equal(new_masks["h_original"],h):
            raise AssertionError("Case03H altered source H pixels")
        for j in range(1,n):
            key=f"Hlocal_{j:04d}"
            records.append({
                "window_id":win,"local_H_id":key,
                "original_H_area_px":int(stats[j,cv2.CC_STAT_AREA]),
                "original_BlackHat_peak_dn":features[j-1]["fused_blackhat_peak_dn"],
                "raw_relative_contrast":features[j-1]["relative_contrast"],
                "raw_significance_z":features[j-1]["significance_z"],
                "raw_reference_valid":features[j-1]["reference_valid"],
                "coherent_dark_DoG_median_dn":features[j-1]["dog_median_dn"],
                "case03g_state":earlier_states[j-1],
                "case03h_state":new_states[j-1],
                "case03h_reason":new_reasons[j-1],
                "source_H_preserved":True,"source_refined_preserved":True,
                "manual_label_used_to_filter":False,
            })
        save_png(dest/"figures_9_windows"/f"{win}_5panel.png",
                 _five(tile,old_masks,new_masks,hidden_new,win,None,1))
        summaries.append({
            "window_id":win,"original_H_components":n-1,
            "case03g_hidden":earlier_states.count("hide_suggestion"),
            "case03h_hidden":new_states.count("hide_suggestion"),
            "additional_medium_hidden_components":len(new_hidden_ids),
            "original_H_pixels":int(h.sum()),
            "case03g_display_H_pixels":int(old_masks["h_kept_display"].sum()),
            "case03h_display_H_pixels":int(new_masks["h_kept_display"].sum()),
            "case03g_display_refined_pixels":int(old_masks["fused_joint_display"].sum()),
            "case03h_display_refined_pixels":int(new_masks["fused_joint_display"].sum()),
        })
        for ref in refs.loc[refs.window_id==win].itertuples(index=False):
            cx,cy=int(ref.clicked_RAW_x),int(ref.clicked_RAW_y)
            x,y,x1,y1=crop_bounds(cx,cy,(ox,oy),h.shape)
            rows=manual.loc[manual.annotation_kind.eq("poly")].copy()
            rows["_distance"]=(pd.to_numeric(rows.raw_x)-cx)**2+(
                                pd.to_numeric(rows.raw_y)-cy)**2
            polygonrow=rows.sort_values("_distance").iloc[0]
            if float(polygonrow["_distance"])>400:
                raise AssertionError("unmatched historical manual polygon")
            coords=np.asarray(json.loads(polygonrow.vertices_RAW_global_xy_JSON),
                              dtype=np.int32)-np.array([ox,oy],np.int32)
            region=np.zeros_like(h,dtype=np.uint8)
            cv2.fillPoly(region,[coords.reshape(-1,1,2)],1)
            q=region.astype(bool)
            old_overlap=int(np.count_nonzero(q & old_masks["h_kept_display"]))
            new_overlap=int(np.count_nonzero(q & new_masks["h_kept_display"]))
            old_r=int(np.count_nonzero(q & old_masks["fused_joint_display"]))
            new_r=int(np.count_nonzero(q & new_masks["fused_joint_display"]))
            evaluations.append({
                "manual_target_id":ref.manual_target_id,"window_id":win,
                "original_H_overlap":int(np.count_nonzero(q & h)),
                "prior_gate_H_overlap":old_overlap,"new_gate_H_overlap":new_overlap,
                "prior_refined_overlap":old_r,"new_refined_overlap":new_r,
                "new_H_overlap_retention":round(new_overlap/max(old_overlap,1),4),
                "manual_region_used_only_posthoc":True,
                "not_true_detection_sensitivity":True,
            })
            cropped_old={k:v[y:y1,x:x1] for k,v in old_masks.items()}
            cropped_new={k:v[y:y1,x:x1] for k,v in new_masks.items()}
            polygon_local=coords-np.array([x,y],np.int32)
            image=_five(tile[y:y1,x:x1],cropped_old,cropped_new,
                        hidden_new[y:y1,x:x1],ref.manual_target_id,
                        polygon_local,3)
            save_png(dest/"figures_10_targets"/
                     f"{ref.manual_target_id}_5panel.png",image)
        LOG.info("%s components=%d prev_hidden=%d new_hidden=%d",
                 win,n-1,earlier_states.count("hide_suggestion"),
                 new_states.count("hide_suggestion"))
    if len(records)!=1569 or len(summaries)!=9 or len(evaluations)!=10:
        raise AssertionError("Incomplete 1569 H, 9 windows, 10 individual cases")
    pd.DataFrame(records).to_csv(dest/"candidate_screen_audit.csv",
                                 index=False,encoding="utf-8-sig")
    pd.DataFrame(summaries).to_csv(dest/"window_summary.csv",
                                   index=False,encoding="utf-8-sig")
    pd.DataFrame(evaluations).to_csv(dest/"ten_target_retention_review.csv",
                                     index=False,encoding="utf-8-sig")
    if len(list((dest/"figures_10_targets").glob("*.png")))!=10:
        raise AssertionError("Missing one or more of 10 case PNGs")
    if len(list((dest/"figures_9_windows").glob("*.png")))!=9:
        raise AssertionError("Missing one or more of 9 window PNGs")
    sums=pd.DataFrame(summaries).select_dtypes("number").sum()
    impacted=[v for v in evaluations if v["new_gate_H_overlap"] <
              v["prior_gate_H_overlap"]]
    report={
        "case_images":10,"source_windows":9,
        "original_H_count_preserved":1569,
        "case03g_hidden_suggestions":int(sums["case03g_hidden"]),
        "case03h_hidden_suggestions":int(sums["case03h_hidden"]),
        "extra_medium_hidden_suggestions":int(sums["additional_medium_hidden_components"]),
        "case03g_display_H_pixels":int(sums["case03g_display_H_pixels"]),
        "case03h_display_H_pixels":int(sums["case03h_display_H_pixels"]),
        "case03g_refined_display_pixels":int(sums["case03g_display_refined_pixels"]),
        "case03h_refined_display_pixels":int(sums["case03h_display_refined_pixels"]),
        "manual_regions_with_any_new_H_overlap_loss":impacted,
        "source_H_and_refined_objects_modified":False,
        "gaussian_closing_refinement_source":"historical Case03-E2-H5, not recomputed",
        "pilot_not_blind_validated":True,
    }
    (dest/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    (dest/"config_snapshot.json").write_text(
        json.dumps({"trial_parameters":asdict(config),
                    "source_e2":str(SOURCE),"source_g":str(G_STAGE),
                    "annotations_not_used_in_gate":True},
                   ensure_ascii=False,indent=2),encoding="utf-8")
    LOG.info("FINAL %s",json.dumps(report,ensure_ascii=False))
    LOG.info("OUTPUT %s",dest)
    return dest


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default="run_20261010_10target_texture_conservative_v1")
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    run(args.run_id,TextureTrialConfig(
        medium_min_area_px=cfg.CASE03H_MEDIUM_MIN_AREA_PX,
        medium_max_area_px=cfg.CASE03H_MEDIUM_MAX_AREA_PX,
        min_relative_contrast=cfg.CASE03H_MIN_RELATIVE_CONTRAST,
        min_significance_z=cfg.CASE03H_MIN_SIGNIFICANCE_Z,
        protect_peak_dn=cfg.CASE03H_PROTECT_BLACKHAT_PEAK_DN,
        protect_dog_median_dn=cfg.CASE03H_PROTECT_DOG_MEDIAN_DN,
        dog_small_sigma_px=cfg.CASE03H_DOG_SMALL_SIGMA_PX,
        dog_large_sigma_px=cfg.CASE03H_DOG_LARGE_SIGMA_PX,
        protect_big_area_px=cfg.CASE03H_PROTECT_BIG_AREA_PX,
        protect_big_radius_px=cfg.CASE03H_PROTECT_BIG_RADIUS_PX,
        protect_stroke_min_length_px=cfg.CASE03H_PROTECT_STROKE_MIN_LENGTH_PX,
        protect_stroke_aspect=cfg.CASE03H_PROTECT_STROKE_ASPECT,
    ))
