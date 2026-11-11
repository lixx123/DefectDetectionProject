"""Regression tests for bounded H-seeded rescue of a background-connected stripe.

Scientific acceptance of real physical scratch contour remains independent.
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
import pytest

from src.detection.case03e2_bounded_rescue import rescue_bounded_H_extension
from src.detection.case03e2_hseeded import detect_window_H_seeded,HSeedConfig

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"


def fixture_long_dark_stroke_with_global_low_component_to_crop_edge():
    raw=np.full((256,256),2200,np.uint16)
    cv2.rectangle(raw,(45,115),(178,132),1800,-1)
    cv2.rectangle(raw,(176,115),(205,255),1830,-1)
    # H core covers a 110px center of the stroke but is disconnected
    # from dark cross/background beyond x=180.
    H=np.zeros((256,256),bool)
    H[119:129,52:165]=True
    R=np.zeros_like(raw)
    R[H]=240
    S=np.zeros_like(H)
    S[H]=True
    return raw,H,S,R


def test_fallback_recovers_bounded_stroke_when_global_background_reaches_edge():
    raw,H,S,R=fixture_long_dark_stroke_with_global_low_component_to_crop_edge()
    original=detect_window_H_seeded(raw,H,S,R)
    assert len(original["objects"])==1
    assert original["objects"][0].area_px==int(H.sum())
    improved=detect_window_H_seeded(
        raw,H,S,R,policy=HSeedConfig(enable_bounded_extension_fallback=True)
    )
    assert improved["num_output_objects"]==1
    obj=improved["objects"][0]
    assert obj.area_px>original["objects"][0].area_px
    assert obj.area_px<3*H.sum()
    assert obj.status=="needs_review_bounded_extension"
    assert np.all(obj.mask[H])
    assert not obj.mask[-1].any()  # does NOT swallow background to crop edge
    assert not obj.mask[0].any()
    assert all("H170_230" in o.sources for o in improved["objects"])


def test_competing_H_components_are_not_swallowed_by_refined_stroke():
    raw,H,S,R=fixture_long_dark_stroke_with_global_low_component_to_crop_edge()
    H[119:130,194:205]=True
    S[119:130,194:205]=True
    R[119:130,194:205]=245
    out=detect_window_H_seeded(
        raw,H,S,R,policy=HSeedConfig(enable_bounded_extension_fallback=True)
    )
    assert len(out["objects"])==2
    assert not any(np.any(a.mask&b.mask)
                   for i,a in enumerate(out["objects"])
                   for b in out["objects"][i+1:])
    assert np.array_equal(np.logical_or.reduce([o.mask for o in out["objects"]])&H,H)


def test_large_dark_background_without_H_source_creates_zero_candidates():
    raw=np.full((256,256),2200,np.uint16)
    cv2.rectangle(raw,(0,110),(255,255),1700,-1)
    H=np.zeros((256,256),bool)
    R=np.zeros_like(raw)
    out=detect_window_H_seeded(raw,H,H.copy(),R,
         policy=HSeedConfig(enable_bounded_extension_fallback=True))
    assert out["num_output_objects"]==0
    assert out["independent_gaussian_morph_candidates"]==0


def test_bounded_rescue_never_creates_new_object_without_H_owner():
    H=np.zeros((256,256),bool)
    labels=np.zeros((256,256),np.int32)
    response=np.full((256,256),120.,np.float32)
    with pytest.raises(ValueError):
        rescue_bounded_H_extension(H,H,labels,response,20.,owner_label=1)


def test_v4_real_W005_long_scratch_improves_but_is_not_approved_as_true_contour():
    ev=pd.read_csv(RUN/"ten_manual_targets_posthoc_evaluation.csv")
    row=ev.loc[ev.manual_target_id=="RAW26_MANUAL_003"].iloc[0]
    assert row.historical_H_coverage==pytest.approx(.6844,abs=.001)
    assert row.fused_union_coverage>.98
    assert row.top_fused_object_status=="needs_review_bounded_extension"
    original=1936
    o=[json.loads(s) for s in
        (RUN/"all_window_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()]
    item=next(a for a in o if a["local_object_id"]=="E2_W005_O0050")
    assert original<item["exact_area_px"]<2*original
    x,y,w,h=item["bbox_global_xywh"]
    assert 2944<x and x+w<3200 and 1024<y and y+h<1280
    assert item["size_grade"]=="PENDING_USER_THRESHOLDS"
    assert item["physical_defect_truth"] is False


def test_v4_base_H_source_exactly_preserved_and_no_new_background_only_objects():
    raw=[json.loads(s) for s in
         (RUN/"all_window_objects_exact.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(raw)==1569
    assert all("H170_230" in x["sources"] for x in raw)
    assert all(not x["physical_defect_truth"] for x in raw)
    acc=json.loads((RUN/"acceptance.json").read_text(encoding="utf-8"))
    assert acc["H_pixel_conservation"]
    assert acc["objects_with_no_H_seed"]==0
    assert acc["candidate_count"]==1569
    assert acc["counts"]=={"PASS":9,"FAIL":2,"DEFERRED":3}
