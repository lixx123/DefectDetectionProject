"""Case03-E2-H acceptance, regressions, H-only seed constrained extension."""
from __future__ import annotations
import inspect
import json
from pathlib import Path
from collections import Counter
import cv2
import numpy as np
import pandas as pd
import pytest

from src.detection.case03e2_hseeded import (
    detect_window_H_seeded,HSeedConfig
)
from src.detection.case03e2_window_stitch import read_bbox_binary

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"outputs/case03e2/run_20261010_H_only_seeded_refinement_v2"


def raw_two():
    raw=np.full((256,256),2100,np.uint16)
    cv2.circle(raw,(70,70),11,1760,-1)
    cv2.circle(raw,(150,180),12,1810,-1)
    response=np.maximum(2100-raw.astype(np.int32),0).astype(np.uint16)
    H=response>=170
    S=response>=230
    return raw,H,S,response


def test_two_synthetic_spots_without_click_found_as_two_independent_H_objects():
    raw,H,S,R=raw_two()
    got=detect_window_H_seeded(raw,H,S,R)
    assert len(got["H_audit"])==2
    assert got["candidate_discovery_mode"]=="H170230_only"
    assert got["independent_gaussian_morph_candidates"]==0
    assert got["num_output_objects"]==2
    a,b=got["objects"]
    assert a.mask[70,70] != a.mask[180,150]
    assert b.mask[70,70] != b.mask[180,150]
    assert all("H170_230" in o.sources for o in (a,b))
    assert all(o.area_px>=o.source_H_candidate_areas_px[0] for o in (a,b))
    assert np.array_equal((a.mask|b.mask)&H,H)


def test_Gaussian_only_dark_region_without_H_seed_is_not_detected():
    raw,H,S,R=raw_two()
    H[:]=False;S[:]=False;R[:]=0
    got=detect_window_H_seeded(raw,H,S,R)
    assert not got["objects"]
    assert got["num_source_proposals"]==0
    assert got["independent_gaussian_morph_candidates"]==0


def test_black_band_alone_without_H_cannot_create_seed_candidate():
    raw=np.full((256,256),2100,np.uint16)
    raw[155:255]=300
    H=np.zeros(raw.shape,bool);S=H.copy();R=np.zeros_like(raw)
    got=detect_window_H_seeded(raw,H,S,R)
    assert got["num_output_objects"]==0
    assert sum(d["H_seeded_refined_count"] for d in
               got["local_source_diagnostics"].values())==0


def test_black_band_does_not_swallow_independent_source_H_seed():
    raw=np.full((256,256),2100,np.uint16)
    raw[160:]=350
    cv2.circle(raw,(70,70),10,1680,-1)
    cv2.circle(raw,(180,97),10,1630,-1)
    H=np.zeros(raw.shape,bool)
    for cx,cy in [(70,70),(180,97)]:
        cv2.circle(Hview:=np.zeros(raw.shape,np.uint8),(cx,cy),8,1,-1)
        H|=Hview.astype(bool)
    R=np.zeros_like(raw)
    R[H]=400
    S=H.copy()
    got=detect_window_H_seeded(raw,H,S,R)
    assert len(got["objects"])==2
    assert all(o.area_px<2000 for o in got["objects"])
    assert not any(o.mask[220,100] for o in got["objects"])
    assert np.array_equal(np.logical_or.reduce([o.mask for o in got["objects"]])&H,H)


def test_original_weak_1px_H_candidate_is_audit_only_not_deleted():
    raw=np.full((256,256),2100,np.uint16)
    H=np.zeros(raw.shape,bool);H[80,80]=True
    S=H.copy();R=np.zeros_like(raw);R[H]=230
    got=detect_window_H_seeded(raw,H,S,R)
    assert got["num_output_objects"]==1
    obj=got["objects"][0]
    assert obj.area_px==1
    assert obj.mask[80,80]
    assert obj.status=="audit_only_H_micro"
    assert len(got["H_audit"])==1
    assert got["H_audit"][0]["H_hysteresis_proposal_always_retained"]


def test_strong_1px_H_candidate_kept_as_explicit_review():
    raw=np.full((256,256),2100,np.uint16)
    H=np.zeros(raw.shape,bool);H[81,81]=True
    R=np.zeros_like(raw);R[H]=500
    got=detect_window_H_seeded(raw,H,H.copy(),R)
    assert got["num_output_objects"]==1
    assert got["objects"][0].status=="needs_review_H_micro_high_peak"


def test_H_sources_must_have_true_R_response_and_S_is_subset():
    raw,H,S,R=raw_two()
    badR=R.copy();badR[H]=0
    with pytest.raises(ValueError):
        detect_window_H_seeded(raw,H,S,badR)
    S[5,5]=True
    with pytest.raises(ValueError):
        detect_window_H_seeded(raw,H,S,R)


def test_no_human_argument_in_pure_detector():
    pars=inspect.signature(detect_window_H_seeded).parameters
    assert set(pars)=={"raw","H","S","fused","cfg","policy"}
    pure=inspect.getsource(detect_window_H_seeded)
    assert "clicked" not in pure and "manual_polygon" not in pure
    from scripts.run_case03e2_multicandidate_fusion import run
    implementation=inspect.getsource(run)
    area=implementation[implementation.index("if hseeded:"):implementation.index(
        "        props=detected")]
    assert "annotations" not in area
    assert "clicked_" not in area


def test_real_nine_windows_preserve_all_original_H_exactly():
    q=json.loads((RUN/"summary.json").read_text(encoding="utf-8"))
    assert q["candidate_discovery_mode"]=="H170230_only"
    h=pd.read_csv(RUN/"all_original_H_components_in_windows.csv")
    w=pd.read_csv(RUN/"window_summary.csv")
    assert len(h)==1569
    assert len(w)==9
    assert h.H_hysteresis_proposal_always_retained.astype(bool).all()
    assert w.independent_Gaussian_or_Morph_candidates.eq(0).all()
    assert w.fusion_objects.sum()==len(h)
    assert (RUN/"figures/E2_all_9_windows_contact_sheet.png").is_file()


def test_real_candidate_geometry_every_H_pixel_is_conserved_and_no_overlap():
    rows=[json.loads(line) for line in
          (RUN/"all_window_objects_exact.jsonl").read_text(
              encoding="utf-8").splitlines()]
    assert len(rows)==1569
    grouped={}
    for w in pd.read_csv(RUN/"window_summary.csv").to_dict("records"):
        with np.load(RUN/"masks"/f"{w['window_id']}_labels.npz",
                     allow_pickle=False) as z:
            grouped[w["window_id"]]={
                "H":z["H170_230"].astype(bool),
                "labels":z["all_object_labels"].copy(),
                "origin":z["roi_origin_raw_xy"].astype(int),
                "check":np.zeros((256,256),bool)
            }
    for r in rows:
        assert r["sources"][0]=="H170_230"
        assert not r["physical_defect_truth"]
        m=read_bbox_binary(r)
        assert int(m.sum())==r["exact_area_px"]
        z=grouped[r["window_id"]]
        x,y,w,h=r["bbox_global_xywh"]
        xx=x-z["origin"][0];yy=y-z["origin"][1]
        val=int(r["local_object_id"].split("_O")[-1])
        assert np.all(z["labels"][yy:yy+h,xx:xx+w][m]==val)
        assert not np.any(z["check"][yy:yy+h,xx:xx+w]&m)
        z["check"][yy:yy+h,xx:xx+w]|=m
    for z in grouped.values():
        assert np.array_equal(z["labels"]>0,z["check"])
        assert np.all(z["check"][z["H"]])


def test_real_manual007_and008_in_one_window_two_unique_H_ids():
    t=pd.read_csv(RUN/"ten_manual_targets_posthoc_evaluation.csv")
    s=t.set_index("manual_target_id")
    a=s.loc["RAW26_MANUAL_007"];b=s.loc["RAW26_MANUAL_008"]
    assert a.window_id==b.window_id=="E2_W001"
    assert a.top_fused_object_id!=b.top_fused_object_id
    assert a.top_fused_mask_coverage>.80
    assert b.top_fused_mask_coverage>.90
    assert a.top_fused_object_status=="provisional_fused"
    assert b.top_fused_object_status=="provisional_fused"


def test_real_009_weak_H_remains_candidate_but_measured_boundary_not_accepted():
    t=pd.read_csv(RUN/"ten_manual_targets_posthoc_evaluation.csv").set_index("manual_target_id")
    s=t.loc["RAW26_MANUAL_009"]
    assert s.fused_union_coverage==pytest.approx(s.historical_H_coverage)
    assert s.provisional_safe_union_coverage==0
    assert s.top_fused_object_status.startswith("needs_review")


def test_real_003_004_010_unsafe_not_pretend_contour_complete():
    t=pd.read_csv(RUN/"ten_manual_targets_posthoc_evaluation.csv").set_index("manual_target_id")
    for n in ("003","004","010"):
        v=t.loc[f"RAW26_MANUAL_{n}"]
        assert v.top_fused_object_status.startswith("needs_review")
        assert v.provisional_safe_union_coverage==0
        assert v.fused_union_coverage==pytest.approx(v.historical_H_coverage,
                                                     abs=.005)


def test_real_micro_H_suppressed_in_preview_only_and_kept_in_data():
    r=[json.loads(line) for line in
       (RUN/"all_window_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()]
    hist=Counter(x["fusion_status"] for x in r)
    assert hist["audit_only_H_micro"]>=900
    assert hist["provisional_fused"]>=4
    assert len(r)==1569
    manifest=json.loads((RUN/"source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["all_sources_unchanged"]
    assert manifest["inputs_before"]==manifest["inputs_after"]


def test_acceptance_and_main_default_do_not_claim_all_pass():
    a=json.loads((RUN/"acceptance.json").read_text(encoding="utf-8"))
    assert a["counts"]=={"PASS":9,"FAIL":2,"DEFERRED":3}
    assert a["H_pixel_conservation"]
    assert a["candidate_discovery_mode"]=="H170230_only"
    assert not a["whole_RAW_scan_done"]
    from main import main
    source=inspect.getsource(main)
    assert "run(args.run_id,hseeded=True)" in source
    assert "run(args.run_id,hseeded=False)" in source
