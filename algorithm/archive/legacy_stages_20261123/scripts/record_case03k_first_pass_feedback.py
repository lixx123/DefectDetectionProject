"""Freeze user's first-pass direct image review without modifying base labels.

User said ONLY K0_SMALL_053, 054, 073, 074, 077 are real small defects.
The other 19 SMALL_CANDIDATE targets in this 30-item first-pass set are
marked BACKGROUND_NOISE (not other 72 candidate examples), while six
NO_J5_CANDIDATE_ROI controls remain UNREVIEWED for missed defects.
"""
from pathlib import Path
from datetime import date
import json
import pandas as pd

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
ORIGIN=ROOT/"first_pass_review_30.csv"
DEST=ROOT/"first_pass_review_30_user_feedback_20261012.csv"
MANIFEST=ROOT/"first_pass_user_feedback_provenance.json"
POSITIVES={f"K0_SMALL_{n:03d}" for n in (53,54,77,73,74)}

if DEST.exists() or MANIFEST.exists():
    raise FileExistsError("Never overwrite human feedback record")
df=pd.read_csv(ORIGIN,encoding="utf-8-sig",keep_default_na=False)
assert len(df)==30 and df["sample_id"].is_unique
cand=df.sample_kind.eq("SMALL_CANDIDATE")
assert cand.sum()==24
assert (df.sample_kind=="NO_J5_CANDIDATE_ROI").sum()==6
assert POSITIVES.issubset(set(df.loc[cand,"sample_id"]))
assert df["manual_candidate_label"].eq("").all(), "Original label table already modified"
df.loc[cand,"manual_candidate_label"]="BACKGROUND_NOISE"
df.loc[df.sample_id.isin(POSITIVES),"manual_candidate_label"]="REAL_MICRO_DEFECT"
df.loc[cand,"operator_comment"]="User visual review: only five listed sample IDs are real micro-defects; remaining first-pass small candidates called noise."
# Confidence was never supplied. Do not fabricate it.
df.loc[cand,"human_confidence"]=""
# An image-target classification does NOT entail having inspected the entire ROI.
for field in ("manual_complete_roi_review","manual_any_missed_defect_in_roi","manual_missed_count"):
    assert df[field].eq("").all()
df.to_csv(DEST,index=False,encoding="utf-8-sig")
check=pd.read_csv(DEST,encoding="utf-8-sig",keep_default_na=False)
assert check.manual_candidate_label.value_counts().to_dict()=={
    "BACKGROUND_NOISE":19,"":6,"REAL_MICRO_DEFECT":5}
assert check.loc[check.sample_kind=="NO_J5_CANDIDATE_ROI","manual_candidate_label"].eq("").all()
assert check.manual_complete_roi_review.eq("").all()
manifest={
    "timestamp_context":"2026-10-12 (user response)",
    "source_first_pass":str(ORIGIN),
    "labeled_output":str(DEST),
    "real_sample_ids":sorted(POSITIVES),
    "first_pass_total_examples":30,
    "first_pass_small_candidates_labeled":24,
    "reviewed_real":5,
    "reviewed_noise_by_only_statement":19,
    "unpredicted_ROIs_without_human_miss_label":6,
    "other_72_small_candidate_samples_unreviewed":True,
    "human_confidence_not_provided":True,
    "original_review_table_unchanged":True,
    "detector_and_thresholds_unchanged":True,
    "note":"Only first-pass human impression, not independently confirmed microscopic ground truth. No population precision/recall claim."
}
MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print("CASE03K_FIRST_PASS_HUMAN_LABELS_RECORDED",json.dumps(manifest,ensure_ascii=False))
