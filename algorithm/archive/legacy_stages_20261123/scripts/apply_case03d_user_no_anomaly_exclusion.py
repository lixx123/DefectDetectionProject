"""Exclude user-confirmed non-anomaly from derived target lists only."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching"
SOURCE=FOLDER/"11_manual_target_size_and_status_preliminary.csv"
EXCLUDE="H_sample26_0452065"

source=pd.read_csv(SOURCE,encoding="utf-8-sig")
if len(source)!=11 or source["review_target_id"].duplicated().any():
    raise ValueError("Preliminary target source changed unexpectedly")
chosen=source["original_ROI_parent_candidate_id"].eq(EXCLUDE)
if chosen.sum()!=1 or not bool(source.loc[chosen,"user_note_conflict_no_anomaly"].iloc[0]):
    raise ValueError("User-excluded annotation identity or conflict flag mismatch")
source.assign(human_target_final_use_status=chosen.map({
    True:"excluded_by_user_no_anomaly",False:"retained_manual_anomaly_candidate"
})).to_csv(FOLDER/"11_manual_targets_with_final_user_decision.csv",
          index=False,encoding="utf-8-sig")
valid=source.loc[~chosen].copy()
valid["human_target_final_use_status"]="retained_manual_anomaly_candidate"
valid["ground_truth_caveat"]="user marked location; contour remains provisional"
valid.to_csv(FOLDER/"10_retained_manual_targets_for_boundary_refinement.csv",
             index=False,encoding="utf-8-sig")
omitted=source.loc[chosen].copy()
omitted["exclude_reason"]="User explicitly confirmed ignore: 无异常"
omitted.to_csv(FOLDER/"excluded_manual_target_no_anomaly.csv",index=False,encoding="utf-8-sig")
summary={
    "excluded_parent_H_candidate":"H_sample26_0452065",
    "exclusion_reason":"用户确认该区域无异常，可以忽略",
    "original_polygon_regions":11,
    "excluded_no_anomaly_regions":1,
    "retained_manual_anomaly_candidates":len(valid),
    "retained_parent_roi_count":int(valid.original_ROI_parent_candidate_id.nunique()),
    "retained_dominant_H_auto_candidates":int(valid.dominant_exact_H_candidate_decision.eq("detected_provisional").sum()),
    "retained_dominant_H_uncertain_candidates":int(valid.dominant_exact_H_candidate_decision.eq("uncertain_review").sum()),
    "retained_low_H_coverage_below_40pct":int(valid.existing_H_segmentation_polygon_coverage.lt(.4).sum()),
    "retained_roi_boundary_nearby":int(valid.manual_polygon_near_160px_ROI_boundary.sum()),
    "source_annotations_and_detector_untouched":True,
    "physical_defect_ground_truth_independently_confirmed":False
}
assert summary["retained_manual_anomaly_candidates"]==10
assert summary["retained_dominant_H_auto_candidates"]==3
assert summary["retained_dominant_H_uncertain_candidates"]==7
(FOLDER/"user_confirmed_no_anomaly_exclusion.json").write_text(
    json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
(FOLDER/"USER_DECISION_EXCLUSION.md").write_text(
    "# 人工无异常区域排除确认\n\n"
    "用户明确确认：H_sample26_0452065 无异常，可以忽略。\n\n"
    "- 后续目标统计、轮廓精修、尺寸分级和正样本分析均排除该区域。\n"
    "- 原始11条多边形分析保留，生成10条待分析的目标清单。\n"
    "- 原人工CSV/JSON、H掩膜、Case03-D判别结果不被覆盖。\n"
    "- 10处保留位置仍需要进一步精修轮廓。\n",
    encoding="utf-8")
print("USER_EXCLUSION_APPLIED",json.dumps(summary,ensure_ascii=False))
