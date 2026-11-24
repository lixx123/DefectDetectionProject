"""Run-independent and saved-output regression checks of exact human pixel re-targeting."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import numpy as np
import pytest

from scripts.resolve_case03c_user_retarget import (
    flood_8_component, match_component, nearest_mask_pixel,
    validate_annotation, lookup_by_geometry
)

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v1"


def _rows(name):
    with (RUN/name).open("r",newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_connected_component_diagonal_exact_full_geometry():
    mask=np.zeros((14,16),bool)
    mask[0,0]=True
    mask[1,1]=True
    mask[2,2]=True
    mask[12,14]=True
    result=flood_8_component(mask,0,0)
    assert result["bbox_x"]==0
    assert result["bbox_y"]==0
    assert result["bbox_w"]==3
    assert result["bbox_h"]==3
    assert result["area_px"]==3
    assert flood_8_component(mask,12,12) is None
    expected={"candidate_id":"testH","bbox_x":"0","bbox_y":"0","bbox_w":"3","bbox_h":"3","area_px":"3"}
    index=lookup_by_geometry([expected])
    got,geometry=match_component(mask,index,1,1,{})
    assert got["candidate_id"]=="testH"
    assert geometry["area_px"]==3


def test_nearest_pixel_is_only_suggestion_no_match_at_original_click():
    mask=np.zeros((12,12),bool)
    mask[3,4]=True
    assert flood_8_component(mask,4,4) is None
    nearest=nearest_mask_pixel(mask,4,4,radius=2)
    assert nearest=={"x":4,"y":3,"euclidean_distance_px":1.0}
    assert nearest_mask_pixel(mask,10,10,radius=2) is None


def test_annotation_exact_pixel_or_box_counts_validation():
    s=np.zeros((18,20),bool)
    h=s.copy()
    s[3,4]=True
    h[3,4]=True
    h[4,5]=True
    base={"review_id":"review_021","source_sample":"26","source_frame":"1"}
    assert validate_annotation({**base,"mode":"point","raw_global_x":"4","raw_global_y":"3",
        "mask_membership_at_point":"S230_yellow"},s,h)["membership_verified"]=="S230_yellow"
    assert validate_annotation({**base,"mode":"point","raw_global_x":"5","raw_global_y":"4",
        "mask_membership_at_point":"H170_only_cyan"},s,h)["membership_verified"]=="H170_only_cyan"
    with pytest.raises(ValueError,match="browser PNG/CSV mismatch"):
        validate_annotation({**base,"mode":"point","raw_global_x":"4","raw_global_y":"3",
            "mask_membership_at_point":"no_segmented_pixel"},s,h)
    box={**base,"mode":"box","raw_global_x0":"3","raw_global_y0":"2",
         "raw_global_x1":"6","raw_global_y1":"5",
         "box_S230_pixel_count":"1","box_H170_pixel_count":"2"}
    assert validate_annotation(box,s,h)["box_H170_coverage_pct"]==22.2222


def test_real_annotated_mapping_has_no_guessed_ids_and_no_deleted_history():
    summary=json.loads((RUN/"summary.json").read_text(encoding="utf-8"))
    rows=_rows("pixel_retarget_associations.csv")
    assert summary["review_rows"]==12
    assert summary["unique_review_ids"]==8
    assert summary["missing_review_056"]
    assert summary["unique_directly_mapped_positive_H_candidates"]==4
    exact=[r for r in rows if r["retarget_status"]=="EXACT_H_CONNECTED_COMPONENT_FROM_PIXEL"]
    missing=[r for r in rows if r["retarget_status"]=="POINT_NOT_IN_MASK_REVIEW_RING_OR_MISSED"]
    box=[r for r in rows if r["retarget_status"]=="BOX_REGION_NOT_A_SINGLE_COMPONENT"]
    assert len(exact)==5 and len(missing)==6 and len(box)==1
    assert all(r["exact_H_candidate_id"] and r["H_area_px"] for r in exact)
    assert all(not r["exact_H_candidate_id"] for r in missing+box)
    map39={r["exact_H_candidate_id"] for r in exact if r["review_id"]=="review_039"}
    assert len(map39)==1
    b31=box[0]
    assert b31["review_id"]=="review_031"
    assert b31["box_S230_pixels"]=="0" and b31["box_H170_pixels"]=="0"
    assert summary["source_file_unmodified"]


def test_real_label_evaluation_contains_only_validated_or_prior_candidates():
    labels=_rows("candidate_labels_verified.csv")
    auc=_rows("reconciled_exploratory_feature_auc.csv")
    ids=[r["candidate_id"] for r in labels]
    assert len(ids)==len(set(ids))==53
    assert sum(x["manual_label"]=="confirmed_dark_spot" for x in labels)==14
    assert sum(x["manual_label"]=="background_artifact" for x in labels)==39
    assert all(x["status"]=="EXPLORATORY_ONLY" for x in auc)
    assert sum(x["provenance"]=="new_exact_pixel" for x in labels)==4


def test_user_review_box_local_diagnostics_31_has_no_seeds():
    rows=_rows("point_box_local_response_diagnostics.csv")
    box=next(r for r in rows if r["review_id"]=="review_031" and r["mode"]=="box")
    assert int(box["response_max_dn"])==216
    assert int(box["response_over_230_px"])==0
    assert int(box["response_over_170_px"])==35
    assert int(box["S230_count"])==int(box["H170_count"])==0
