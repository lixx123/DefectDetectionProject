"""Case03-E pilot quality gates and image/area conservation."""
from __future__ import annotations
import inspect
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

from scripts.summarize_case03e_pilot_quality import judge_pilot

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03e/run_20261010_10roi_boundary_pilot_v1"


def test_all_ten_methods_quality_uses_only_algorithmic_area_and_crop_boundary():
    experiments=pd.read_csv(OUT/"all_60_pilot_experiments.csv")
    qa=judge_pilot(experiments)
    assert len(qa)==10
    assert qa.engineering_quality_gate.value_counts().to_dict()=={
        "NEEDS_INDEPENDENT_CONTOUR_REVIEW":6,
        "UNRESOLVED_CONNECTED_TO_CROP_BOUNDARY":2,
        "UNRESOLVED_METHOD_INSTABILITY":2
    }
    assert qa.user_annotations_used_to_change_gate.eq(False).all()
    assert set(qa.loc[qa.any_method_crop_edge,"user_target_id"])=={
        "RAW26_MANUAL_003","RAW26_MANUAL_010"
    }
    assert set(qa.loc[
        qa.engineering_quality_gate=="UNRESOLVED_METHOD_INSTABILITY",
        "user_target_id"
    ])=={"RAW26_MANUAL_004","RAW26_MANUAL_006"}


def test_default_cannot_claim_known_physical_defect_accuracy():
    s=json.loads((OUT/"engineering_qa_summary.json").read_text(encoding="utf-8"))
    assert s["all_targets"]==10
    assert s["stable_enough_for_manual_boundary_review_not_proven_valid"]==6
    assert s["do_not_use_unresolved_masks_for_final_size_grades"]
    assert s["reference_variant_not_validated"]
    assert s["quality_rules_fixed_without_manual_polygon_ground_truth"]


def test_visibles_and_diagnostic_tables_exist_without_touching_old_Case03D():
    table=pd.read_csv(OUT/"per_target_engineering_QA.csv")
    assert len(table)==10
    assert len(pd.read_csv(OUT/"six_methods_comparison.csv"))==6
    assert len(pd.read_csv(OUT/"historic_H_baseline_10.csv"))==10
    pic=OUT/"figures/CASE03E_all_10_boundary_comparison.png"
    assert pic.is_file()
    image=cv2.imdecode(np.frombuffer(pic.read_bytes(),dtype=np.uint8),
                       cv2.IMREAD_COLOR)
    assert image.shape[1]==720
    assert image.shape[0]==2700
    assert (OUT/"CASE03E_PILOT_REPORT.md").is_file()
    old=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    assert len(pd.read_csv(old/"detected_provisional.csv"))==139
    assert len(pd.read_csv(old/"uncertain_review_full.csv"))==6685


def test_local_pilot_detection_code_does_not_pass_manual_polygon_to_segmenter():
    from scripts.run_case03e_local_boundary_pilot import run
    s=inspect.getsource(run)
    assert "grow_from_clicked_center(" in s
    assert "manual_polygon_mask" in s
    call_section=s[s.index("result=grow_from_clicked_center("):
                   s.index("key=method+")]
    assert "manual" not in call_section
    assert "polygon" not in call_section
