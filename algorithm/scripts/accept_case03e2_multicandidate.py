"""Case03-E2 automatic reproducibility/acceptance and risk register.

Engineering acceptance is NOT physical segmentation accuracy acceptance.
This checker does not treat manual polygon coverage of all unsafe masks as
a successful final contour; it reports safe-only coverage separately.
"""
from __future__ import annotations
import argparse,json,math,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
import pandas as pd

from src.detection.case03e2_window_stitch import read_bbox_binary
from src.detection.case03e2_multicandidate import FusionConfig

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"outputs/case03e2/run_20261010_multiseed_fusion_v5"


def record(gates:list,key:str,criterion:bool|None,
           detail:str)->None:
    gates.append({
       "gate":key,
       "status":"DEFERRED" if criterion is None else ("PASS" if criterion else "FAIL"),
       "evidence":detail
    })


def check(out:Path)->dict:
    if not out.is_dir():raise FileNotFoundError(out)
    summary=json.loads((out/"summary.json").read_text(encoding="utf-8"))
    window=pd.read_csv(out/"window_summary.csv",keep_default_na=False)
    evals=pd.read_csv(out/"ten_manual_targets_posthoc_evaluation.csv",
                      keep_default_na=False)
    Haudit=pd.read_csv(out/"all_original_H_components_in_windows.csv",
                       keep_default_na=False)
    links=pd.read_csv(out/"association_audit.csv",keep_default_na=False)
    source_files=json.loads((out/"source_manifest.json").read_text(encoding="utf-8"))
    all_objs=[json.loads(line) for line in
        (out/"all_window_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()]
    global_objects=[json.loads(line) for line in
        (out/"global_fused_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()]
    assert len(all_objs)>=1 and len(global_objects)>=1
    by_window={}
    for win in window.to_dict("records"):
        name=win["window_id"]
        with np.load(out/"masks"/(name+"_labels.npz"),allow_pickle=False) as z:
            labels=z["all_object_labels"]
            H=z["H170_230"].astype(bool)
            S=z["S230"].astype(bool)
            origin=z["roi_origin_raw_xy"]
        assert labels.shape==H.shape==S.shape==(256,256)
        assert np.all(S<=H)
        assert (labels>=0).all()
        assert len(Haudit[Haudit.window_id==name])==int(win["H_source_connected_components"])
        assert int(H.sum())==int(win["H_source_pixel_count"])
        by_window[name]={
            "labels":labels.copy(),
            "H":H.copy(),
            "origin":origin.astype(int).tolist(),
            "used":np.zeros_like(H,dtype=bool)
        }
    ids=set()
    fused_counts=Counter()
    for obj in all_objs:
        uid=obj["local_object_id"]
        if uid in ids:raise AssertionError("duplicate local ID")
        ids.add(uid)
        fused_counts[obj["fusion_status"]]+=1
        x,y,w,h=obj["bbox_global_xywh"]
        binary=read_bbox_binary(obj)
        assert binary.shape==(h,w)
        a=by_window[obj["window_id"]]
        local_x=x-a["origin"][0]
        local_y=y-a["origin"][1]
        if not(0<=local_x<=256-w and 0<=local_y<=256-h):
            raise AssertionError("mask outside listed window")
        original=a["labels"][local_y:local_y+h,local_x:local_x+w]
        expected_label=int(uid.rsplit("O",1)[-1])
        if not np.all(original[binary]==expected_label):
            raise AssertionError("lossless global mask vs local label map mismatch")
        if np.any(a["used"][local_y:local_y+h,local_x:local_x+w]&binary):
            raise AssertionError("same window object pixels counted twice")
        a["used"][local_y:local_y+h,local_x:local_x+w]|=binary
        assert obj["exact_area_px"]==int(binary.sum())
        assert obj["physical_defect_truth"] is False
        assert obj["object_plane_um_per_px"] is None
        assert obj["size_grade"]=="PENDING_USER_THRESHOLDS"
    for win,v in by_window.items():
        if not np.array_equal(v["used"],v["labels"]>0):
            raise AssertionError(f"window {win}: some fused object pixels lost")
    all_members=set()
    for obj in global_objects:
        assert obj["exact_area_px"]==int(read_bbox_binary(obj).sum())
        ids_=set(obj["member_window_object_ids"])
        if all_members&ids_:raise AssertionError("cross-window mapping double counted")
        all_members|=ids_
        assert obj["physical_defect_truth"] is False
        assert not obj["measurement_validated"]
    assert all_members==ids
    assert len(global_objects)==int(summary["deduped_global_objects"])
    record_gate=[]
    record(record_gate,"G01_Source_files_unchanged",
           bool(source_files["all_sources_unchanged"] and
                source_files["inputs_before"]==source_files["inputs_after"]),
           "SHA256 before/after matches input RAW-derived H/S/fused plus annotations")
    record(record_gate,"G02_No_human_seed_or_manual_polygon_for_fusion",
           len(evals)==10 and
           not evals["manual_click_used_as_any_detector_seed"].astype(bool).any() and
           not evals["manual_polygon_used_to_choose_any_candidate"].astype(bool).any(),
           "Detector API receives only RAW, H, S, fused response; manual ROIs for testing location only")
    record(record_gate,"G03_Multi_seed_two_independent_spots_007_008",
           bool(summary["region_007_008_detects_two_independent_targets"]),
           "One fixed 256px ROI produced two distinct fused object IDs for 007 and 008")
    record(record_gate,"G04_H170230_preservation_and_weak_audit",
           len(Haudit)==1569 and
           int((~Haudit.promoted_to_fusion_pool.astype(bool)).sum())==979,
           "1,569 H source components accounted for, 979 small in full H audit, not silently destroyed")
    record(record_gate,"G05_All_fused_masks_lossless_no_double_count",
           len(all_members)==len(all_objs) and
           len(all_objs)==int(summary["unique_source_window_objects"]),
           "Every exported bbox bitpacked mask matches label NPZ with no duplicate output pixels")
    q7=evals[evals.manual_target_id=="RAW26_MANUAL_007"].iloc[0]
    q8=evals[evals.manual_target_id=="RAW26_MANUAL_008"].iloc[0]
    record(record_gate,"G06_007_008_both_contours_min_manual_coverage_80pct",
           bool(q7.top_fused_mask_coverage>=.8 and
                q8.top_fused_mask_coverage>=.8 and
                q7.top_fused_object_status=="provisional_fused" and
                q8.top_fused_object_status=="provisional_fused"),
           "Post-hoc manual approximate polygon coverage >=80% in both independent regions")
    problematic=evals.set_index("manual_target_id")
    trouble=["RAW26_MANUAL_003","RAW26_MANUAL_010"]
    record(record_gate,"G07_Big_dark_background_bridges_not_measured_as_safe",
           all(str(problematic.loc[k,"top_fused_object_status"]).startswith("needs_review")
               for k in trouble),
           "Long dark stripe/band examples remain review-required; no confident physical contour")
    record(record_gate,"G08_Unstable_004_contour_not_auto_approved",
           str(problematic.loc["RAW26_MANUAL_004",
                               "top_fused_object_status"]).startswith("needs_review"),
           "Manual004 may have more pixels in all-method union, but unsafe union cannot be called correct")
    record(record_gate,"G09_009_safe_only_nonregression_vs_historic",
           bool(problematic.loc["RAW26_MANUAL_009",
                                "provisional_safe_union_coverage"]>=
                problematic.loc["RAW26_MANUAL_009",
                                "historical_H_coverage"]),
           "Known small faint anomaly: reliable-only fusion must not underperform historic H (currently unresolved)")
    record(record_gate,"G10_004_safe_contour_improves_vs_original_H",
           bool(problematic.loc["RAW26_MANUAL_004",
                                 "provisional_safe_union_coverage"]>
                problematic.loc["RAW26_MANUAL_004","historical_H_coverage"]),
           "Only safe provisional fusion pixels count; all-proposal unsafe union cannot pass")
    record(record_gate,"G11_Real_overlap_window_dedup_demonstrated",
           None,"Current 9 selected windows are disjoint; synthetic overlap tests required, real full-grid remains pending")
    record(record_gate,"G12_Independent_frame_holdout_annotation",
           None,"Sample26 manually selected ROIs are development examples; no independent blind validation yet")
    record(record_gate,"G13_Whole_11276x9200_RAW_exhaustive_run",
           None,"Only 9 selected fixed-grid windows run; full-image processing not yet implemented")
    record(record_gate,"G14_Absolute_object_plane_size_and_grade",
           None,"Need optical system object-plane calibration and user-defined size thresholds")

    acceptance_statuses=Counter(g["status"] for g in record_gate)
    assert sum(acceptance_statuses.values())==len(record_gate)
    # Deliverable is always usable as an ENGINEERING PILOT, but conditional
    # acceptance is explicit and cannot be silently replaced by blanket PASS.
    overall=("ENGINEERING_PILOT_PASS_BUT_GATES_FAILED_OR_DEFERRED"
             if (acceptance_statuses["FAIL"] or acceptance_statuses["DEFERRED"])
             else "ALL_ENGINEERING_GATES_PASS")
    reviewlist=[]
    for o in global_objects:
        if o["fusion_status"].startswith("needs_review"):
            score=(20*min(3,len(o["sources"]))+
                   7*np.log1p(o["exact_area_px"])+
                   (5 if "H170_230" in o["sources"] else 0))
            score-=35 if "unsafe" in o["fusion_status"] else 0
            reviewlist.append({
                "global_object_id":o["global_object_id"],
                "review_priority_score_unvalidated":round(float(score),2),
                "fused_status":o["fusion_status"],
                "source_types":"+".join(o["sources"]),
                "pixel_area_provisional":o["exact_area_px"],
                "bbox_global_xywh":json.dumps(o["bbox_global_xywh"]),
                "source_window_object_IDs":";".join(o["member_window_object_ids"]),
                "not_anomaly_probability":True
            })
    reviewlist.sort(key=lambda x:(-x["review_priority_score_unvalidated"],
                                  x["global_object_id"]))
    pd.DataFrame(reviewlist).to_csv(
        out/"uncertain_candidates_priority_all.csv",index=False,
        encoding="utf-8-sig")
    pd.DataFrame(reviewlist[:80]).to_csv(
        out/"uncertain_candidates_top80_for_human.csv",index=False,
        encoding="utf-8-sig")
    accepted={
        "status":overall,
        "number_gates":len(record_gate),
        "counts":dict(acceptance_statuses),
        "gates":record_gate,
        "source_window_count":len(window),
        "candidate_total":len(global_objects),
        "candidate_status_counts":dict(fused_counts),
        "review_candidates":len(reviewlist),
        "review_first_batch_count":min(80,len(reviewlist)),
        "exact_masks_checked_against_local_label_arrays":len(all_objs),
        "all_source_H_components_checked":len(Haudit),
        "all_source_H_low_area_audit_only":979,
        "all_10_human_regions_are_NOT_a_random_or_independent_testset":True,
        "size_unit":"pixels_only_until_optical_calibration",
        "no_true_defect_count_proven":True
    }
    (out/"acceptance.json").write_text(
        json.dumps(accepted,ensure_ascii=False,indent=2),encoding="utf-8")
    pd.DataFrame(record_gate).to_csv(out/"acceptance_gates.csv",index=False,
                                    encoding="utf-8-sig")
    print("CASE03E2_ACCEPTANCE",json.dumps({
        k:accepted[k] for k in ("status","counts","source_window_count",
                                "candidate_total","review_candidates")
    },ensure_ascii=False))
    print("CASE03E2_GATE_TABLE\n"+pd.DataFrame(record_gate).to_string(index=False))
    return accepted


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-dir",type=Path,default=DEFAULT)
    args=p.parse_args()
    check(args.run_dir)
