"""Acceptance for Case03-E2-H: H170/230 only seeds, local refinement only.

Engineering gates differentiate 'H candidate retained' from 'refined safe
contour approved'. Never hide real failures by renaming gate meanings.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.detection.case03e2_window_stitch import read_bbox_binary

def flag(gates,name,value,notes):
    gates.append({"gate":name,"status":"DEFERRED" if value is None else
                  ("PASS" if bool(value) else "FAIL"),"evidence":notes})

def check_H_seeded(out:Path)->dict:
    out=Path(out)
    source=json.loads((out/"source_manifest.json").read_text(encoding="utf-8"))
    summary=json.loads((out/"summary.json").read_text(encoding="utf-8"))
    snap=json.loads((out/"config_snapshot.json").read_text(encoding="utf-8"))
    windows=pd.read_csv(out/"window_summary.csv",keep_default_na=False)
    Hcat=pd.read_csv(out/"all_original_H_components_in_windows.csv",keep_default_na=False)
    audit=pd.read_csv(out/"local_source_candidates_audit.csv",keep_default_na=False)
    evaluation=pd.read_csv(out/"ten_manual_targets_posthoc_evaluation.csv",keep_default_na=False)
    lines=(out/"all_window_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()
    objs=[json.loads(s) for s in lines if s.strip()]
    global_objs=[json.loads(s) for s in
        (out/"global_fused_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()
        if s.strip()]
    fields_by_window={}
    for win in windows.to_dict("records"):
        wid=win["window_id"]
        with np.load(out/"masks"/f"{wid}_labels.npz",allow_pickle=False) as z:
            H=np.asarray(z["H170_230"],bool)
            labels=z["all_object_labels"].copy()
            origin=z["roi_origin_raw_xy"].tolist()
        fields_by_window[wid]={
            "H":H,"labels":labels,"origin":origin,
            "used":np.zeros(H.shape,bool),
            "recovered_original_H":np.zeros(H.shape,bool)
        }
    catalog_ids=set(zip(Hcat.window_id,Hcat.local_H_id))
    out_ids=set()
    status_counter=Counter()
    exact_restored=True
    no_Hless=False
    for o in objs:
        oid=o["local_object_id"]
        if oid in out_ids:raise AssertionError("duplicate global oid")
        out_ids.add(oid)
        status_counter[o["fusion_status"]]+=1
        status_counter["has_H"]+=int("H170_230" in o["sources"])
        if "H170_230" not in o["sources"]:
            no_Hless=True
        win=o["window_id"]
        d=fields_by_window[win]
        x,y,w,h=o["bbox_global_xywh"]
        x-=d["origin"][0];y-=d["origin"][1]
        inside=read_bbox_binary(o)
        if not(0<=x<=256-w and 0<=y<=256-h):
            raise AssertionError("outside RAW ROI")
        if inside.shape!=(h,w) or inside.sum()!=o["exact_area_px"]:
            raise AssertionError("lossless bbox data invalid")
        block=d["labels"][y:y+h,x:x+w]
        number=int(oid.rsplit("_O",1)[-1])
        if np.any(block[inside]!=number):
            exact_restored=False
        used=d["used"][y:y+h,x:x+w]
        if (used&inside).any():
            raise AssertionError("within-window object masks overlap")
        used|=inside
        d["recovered_original_H"][y:y+h,x:x+w]|=(
            inside & d["H"][y:y+h,x:x+w]
        )
    original_H_complete=True
    for d in fields_by_window.values():
        if not np.array_equal(d["labels"]>0,d["used"]):
            exact_restored=False
        if not np.array_equal(d["recovered_original_H"],d["H"]):
            original_H_complete=False
    val=evaluation.set_index("manual_target_id")
    g=[]
    flag(g,"H01_protected_historical_sources",
         source["all_sources_unchanged"] and
         source["inputs_before"]==source["inputs_after"],
         "Source H/S/BlackHat and original annotation SHA256 unchanged")
    flag(g,"H02_seed_exclusivity",
         summary["candidate_discovery_mode"]=="H170230_only" and
         snap["candidate_discovery_mode"]=="H170230_only" and
         not no_Hless and
         windows["independent_Gaussian_or_Morph_candidates"].eq(0).all(),
         "Every final object is anchored by original H170/230; no local-alone objects")
    flag(g,"H03_all_H_components_kept",
         len(Hcat)==sum(windows.H_source_connected_components) and
         len(objs)==len(Hcat) and original_H_complete and
         Hcat.H_hysteresis_proposal_always_retained.astype(bool).all(),
         "Original H connected components and EVERY H pixel (including 1px) retained in exact masks")
    flag(g,"H04_no_standalone_background_Gaussian_Morph_proposals",
         len(audit)>0 and
         audit.status.isin({
             "accepted_H_seeded_extension",
             "H_too_small_to_refine_but_retained",
             "H_present_but_local_response_too_weak",
             "H_anchor_not_within_low_response_region",
             "rejected_source_component_touches_window_edge",
             "rejected_large_background_component",
             "rejected_bridge_between_independent_H_seeds",
             "rejected_oversized_refined_component",
             "rejected_unbounded_area_ratio",
             "rejected_refined_component_at_crop_edge",
             "no_added_pixels_H_retained",
             "accepted_bounded_H_extension_REVIEW",
         }).all(),
         "All local source attempts are tied to H-local labels; no method alone generates objects")
    flag(g,"H05_lossless_exact_masks_and_no_double_count",
         exact_restored and
         len(objs)==summary["unique_source_window_objects"] and
         len(global_objs)==summary["deduped_global_objects"],
         "Lossless bbox mask roundtrip reconciles every original ROI pixel owner")
    q7=val.loc["RAW26_MANUAL_007"];q8=val.loc["RAW26_MANUAL_008"]
    flag(g,"H06_007_008_automatic_independent_two_spots",
         q7.window_id==q8.window_id and
         q7.top_fused_object_id!=q8.top_fused_object_id and
         q7.top_fused_mask_coverage>=.75 and
         q8.top_fused_mask_coverage>=.75,
         "Two real separate H-seeded objects within one fixed ROI; approximate coverage>=75%")
    flag(g,"H07_009_faint_H_region_preserved_at_candidate_layer",
         val.loc["RAW26_MANUAL_009","fused_union_coverage"]>=
         val.loc["RAW26_MANUAL_009","historical_H_coverage"]-0.005,
         "Weak spot not deleted from H-candidate catalog; this is not a safe contour quality claim")
    flag(g,"H08_009_safe_measured_contour_not_regressed",
         val.loc["RAW26_MANUAL_009","provisional_safe_union_coverage"]>=
         val.loc["RAW26_MANUAL_009","historical_H_coverage"]-0.005,
         "Strict safe mask coverage remains a separate scientific goal (may FAIL)")
    flag(g,"H09_004_safe_refinement_contour_improves",
         val.loc["RAW26_MANUAL_004","provisional_safe_union_coverage"]>
         val.loc["RAW26_MANUAL_004","historical_H_coverage"]+0.01,
         "Must improve only provisional SAFE contour, not by including unsafe background")
    flag(g,"H10_background_blackband_not_from_independent_sources",
         windows.independent_Gaussian_or_Morph_candidates.eq(0).all(),
         "Gaussian/Closing can only add pixels to H seed-bound local component")
    flag(g,"H11_dark_background_bridge_case003_010_not_claimed_valid",
         all(str(val.loc[f"RAW26_MANUAL_{k}","top_fused_object_status"])
             .startswith("needs_review") for k in ("003","010")),
         "Connected large dark anomalies flagged; unvalidated area must never be graded")
    flag(g,"H12_real_cross_window_dedup",None,
         "Selected nine fixed grid windows do not overlap; only synthetic tests available")
    flag(g,"H13_independent_sample_and_full_frame_recall",None,
         "One development sample / nine selected windows; no blind full-frame FNR/precision established")
    flag(g,"H14_object_plane_scale_and_size_grades",None,
         "Calibration and user-defined size limits needed before conversion to micrometres")
    counts=dict(Counter(v["status"] for v in g))
    status=("ENGINEERING_PILOT_WITH_OPEN_GATES"
            if counts.get("FAIL",0) or counts.get("DEFERRED",0)
            else "ENGINEERING_ACCEPTED_NOT_PHYSICAL_VALIDATION")
    review=[]
    for obj in global_objs:
        if str(obj["fusion_status"]).startswith("needs_review"):
            review.append({
                "global_object_id":obj["global_object_id"],
                "status":obj["fusion_status"],
                "pixel_area_preliminary":obj["exact_area_px"],
                "bbox_global_xywh":json.dumps(obj["bbox_global_xywh"]),
                "source_types":"+".join(obj["sources"]),
                "not_ground_truth":True
            })
    pd.DataFrame(review).to_csv(out/"uncertain_candidates_priority_all.csv",
                                encoding="utf-8-sig",index=False)
    pd.DataFrame(review[:80]).to_csv(out/"uncertain_candidates_top80_for_human.csv",
                                  encoding="utf-8-sig",index=False)
    accept={
        "status":status,"counts":counts,"gates":g,
        "candidate_discovery_mode":"H170230_only",
        "source_window_count":len(windows),
        "all_H_components":len(Hcat),
        "objects_with_no_H_seed":int(no_Hless),
        "candidate_count":len(global_objs),
        "review_candidates":len(review),
        "H_pixel_conservation":bool(original_H_complete),
        "exact_masks_checked":len(objs),
        "physical_defect_truth_validated":False,
        "independent_validation_done":False,
        "whole_RAW_scan_done":False,
        "pixel_physical_size_calibrated":False
    }
    (out/"acceptance.json").write_text(
        json.dumps(accept,ensure_ascii=False,indent=2),
        encoding="utf-8")
    pd.DataFrame(g).to_csv(out/"acceptance_gates.csv",index=False,
                           encoding="utf-8-sig")
    print("H_SEEDED_ACCEPTANCE",json.dumps({
       "status":status,"counts":counts,
       "candidate_count":len(global_objs),
       "H_pixel_conservation":bool(original_H_complete)
    },ensure_ascii=False))
    print(pd.DataFrame(g).to_string(index=False))
    return accept

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--run-dir",type=Path,required=True)
    args=p.parse_args()
    check_H_seeded(args.run_dir)
