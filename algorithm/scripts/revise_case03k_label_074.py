"""Versioned correction for K0_SMALL_074: obvious real dark spot, NOT micro.

Preserves prior first-pass user annotation and all J4/J5 masks/parameters.
Separates physical authenticity from size/visual morphology assessment.
"""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
BASE=SOURCE/"first_pass_review_30_user_feedback_20261012.csv"
OUT=SOURCE/"revision_074_obvious_dark_spot_20261012"
if OUT.exists():raise FileExistsError("refuse overwrite "+str(OUT))
OUT.mkdir()
df=pd.read_csv(BASE,encoding="utf-8-sig",keep_default_na=False)
target=df.sample_id=="K0_SMALL_074"
assert target.sum()==1
assert str(df.loc[target,"manual_candidate_label"].iloc[0])=="REAL_MICRO_DEFECT"
df["manual_visible_defect_category"]=""
micro=(df["manual_candidate_label"]=="REAL_MICRO_DEFECT")
df.loc[micro,"manual_visible_defect_category"]="MICRO_DEFECT"
df.loc[target,"manual_candidate_label"]="REAL_OBVIOUS_DARK_SPOT"
df.loc[target,"manual_visible_defect_category"]="OBVIOUS_DARK_SPOT"
df.loc[target,"operator_comment"]=(
  "User correction: 74 is a clearly visible dark spot, NOT a micro defect. "
  "Although J5 source detector labels it SMALL (24 px2, Feret 9.8489 px), "
  "the visible dark structure extends beyond the indicated box; inspect "
  "segmentation completeness/underestimated outline and size. "
  "Original detection, category, and historical first-pass labels preserved."
)
corrected=OUT/"first_pass_review_30_labels_corrected.csv"
df.to_csv(corrected,index=False,encoding="utf-8-sig")
r=pd.read_csv(corrected,encoding="utf-8-sig",keep_default_na=False)
counts=r.manual_candidate_label.value_counts().to_dict()
assert counts=={"BACKGROUND_NOISE":19,"":6,"REAL_MICRO_DEFECT":4,
               "REAL_OBVIOUS_DARK_SPOT":1},counts
features=["source_area_px2","source_max_feret_px",
          "target_blackhat_peak_DN","target_relative_dark_contrast",
          "target_dark_z_MAD","target_DoG_median_DN"]
subset=r[r.sample_kind=="SMALL_CANDIDATE"].copy()
lines=[]
for col in features:
    for cls in ("REAL_MICRO_DEFECT","REAL_OBVIOUS_DARK_SPOT","BACKGROUND_NOISE"):
        vals=pd.to_numeric(subset.loc[subset.manual_candidate_label==cls,col],
                           errors="coerce").dropna()
        lines.append({
            "feature":col,"label":cls,"n":len(vals),
            "median":float(vals.median()) if len(vals) else None,
            "min":float(vals.min()) if len(vals) else None,
            "max":float(vals.max()) if len(vals) else None
        })
pd.DataFrame(lines).to_csv(OUT/"corrected_feature_comparison.csv",
                            encoding="utf-8-sig",index=False)
micro_dog=pd.to_numeric(subset.loc[
    subset.manual_candidate_label=="REAL_MICRO_DEFECT","target_DoG_median_DN"])
noise_dog=pd.to_numeric(subset.loc[
    subset.manual_candidate_label=="BACKGROUND_NOISE","target_DoG_median_DN"])
all_real=pd.to_numeric(subset.loc[
    subset.manual_candidate_label.isin(
      ["REAL_MICRO_DEFECT","REAL_OBVIOUS_DARK_SPOT"]),
    "target_DoG_median_DN"])
meta={
 "status":"USER_CLASSIFICATION_CORRECTION",
 "sample":"K0_SMALL_074",
 "global_defect_id":str(df.loc[target,"global_defect_id"].iloc[0]),
 "original_user_label":"REAL_MICRO_DEFECT",
 "revised_user_label":"REAL_OBVIOUS_DARK_SPOT",
 "counts":{
   "genuine_micro_defects":4,"visually_obvious_real_dark_spot":1,
   "visually_judged_noise":19,"unexamined_zero_prediction_ROIs":6
 },
 "J5_detected_area_px2_for_074":24,
 "J5_detected_feret_px_for_074":9.8489,
 "J5_size_grade":"SMALL",
 "74_full_visible_extent_measured":False,
 "diagnosis":"possible incomplete segmentation of obvious dark spot; require objective contour review before interpreting physical extent",
 "DoG_true_micro_median_DN":round(float(micro_dog.median()),4),
 "DoG_all_real_including_obvious_median_DN":round(float(all_real.median()),4),
 "DoG_noise_median_DN":round(float(noise_dog.median()),4),
 "prior_first_pass_source_untouched":True,
 "fixed170230_H_J5_parameters_untouched":True,
 "not_population_precision":True,
 "not_blind_validation":True,
 "corrected_label_path":str(corrected)
}
(OUT/"revision_provenance.json").write_text(
 json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
report=(
 "# Case03-K：74号分类修订及分割完整性待检\n\n"
 "**用户更正：74号为非常明显的真实黑斑，不属于真实微小疵病。**\n\n"
 "- 真实微小疵病：53、54、73、77（4例）。\n"
 "- 明显真实黑斑但被J5误列为SMALL：74（1例）。\n"
 "- 目视判断为噪声：19例；未审查是否漏检的无预测ROI：6处。\n"
 "- 原074检测面积24px²，Feret跨度9.8489px，导致尺寸档为绿色SMALL；"
 "在RAW图上可见的暗斑范围明显大于局部黄色框。需要复核真轮廓、暗核与晕染"
 "灰度边界的区分，不能仅凭视觉说其真实面积是多少。\n"
 "- 不能再使用“5处真实微小疵病”的措辞。应区分真实性、物理尺寸及显著程度，"
 "也要避免将该对象的黑斑可见范围直接当成算法真实分割范围。\n"
 f"- 真微小4例DoG中位数={meta['DoG_true_micro_median_DN']} DN；"
 f"5处真实（含明显黑斑）的DoG中位数={meta['DoG_all_real_including_obvious_median_DN']} DN；"
 f"噪声19例DoG中位数={meta['DoG_noise_median_DN']} DN。"
 "4例微小目标不足以确定普适筛噪阈值。\n\n"
 "当前**只更新人工标签和后验分析**，所有历史标签、源RAW、H/J4/J5"
 "分割结果、显示分级门限均保持原样。\n"
)
(OUT/"correction_notes.md").write_text(report,encoding="utf-8")
print("K0_LABEL_REVISION_SAVED",json.dumps(meta,ensure_ascii=False),flush=True)
