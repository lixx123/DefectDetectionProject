"""Case03-K first-pass evidence summary with NO production change.

The 24 small candidates were area-STRATIFIED on purpose. Therefore overall
5/24 is NOT the prevalence in the full 14,884 green objects. Threshold
sensitivity is in-sample only; preserve confirmed true area-4 targets.
"""
from pathlib import Path
import pandas as pd,numpy as np,json
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
F=P/"first_pass_review_30_user_feedback_20261012.csv"
DEST=P/"first_pass_evidence_20261012.md"
RULES=P/"first_pass_hypothetical_rule_sensitivity.csv"
if DEST.exists() or RULES.exists():raise FileExistsError("never overwrite historical result")
df=pd.read_csv(F,encoding="utf-8-sig",keep_default_na=False)
cand=df[df.sample_kind=="SMALL_CANDIDATE"].copy()
for c in ["source_area_px2","target_blackhat_peak_DN",
          "target_DoG_median_DN","target_relative_dark_contrast","target_dark_z_MAD"]:
    cand[c]=pd.to_numeric(cand[c],errors="raise")
real=cand[cand.manual_candidate_label=="REAL_MICRO_DEFECT"]
noise=cand[cand.manual_candidate_label=="BACKGROUND_NOISE"]
assert len(real)==5 and len(noise)==19
assess=[]
for area_threshold in (1,2,3,4,5,8):
    kept=cand.source_area_px2>=area_threshold
    assess.append({
       "hypothesis":f"retain_if_area_at_least_{area_threshold}px2",
       "confirmed_real_retained":int((kept&(cand.manual_candidate_label=="REAL_MICRO_DEFECT")).sum()),
       "confirmed_real_removed":int((~kept&(cand.manual_candidate_label=="REAL_MICRO_DEFECT")).sum()),
       "visually_labeled_noise_retained":int((kept&(cand.manual_candidate_label=="BACKGROUND_NOISE")).sum()),
       "visually_labeled_noise_removed":int((~kept&(cand.manual_candidate_label=="BACKGROUND_NOISE")).sum()),
       "only_descriptive_on_selection_biased_first24":True
    })
pd.DataFrame(assess).to_csv(RULES,index=False,encoding="utf-8-sig")
areas={f"min_area_{r['hypothesis'].split('_')[-1]}":r for r in assess}
dogs=(real.target_DoG_median_DN.min(),real.target_DoG_median_DN.median(),
      noise.target_DoG_median_DN.median(),noise.target_DoG_median_DN.max())
positive_details=real[["sample_id","source_area_px2",
                        "target_blackhat_peak_DN","target_relative_dark_contrast",
                        "target_dark_z_MAD","target_DoG_median_DN"]].copy()
lines=[
 "# Case03-K：首轮24个小候选人工判断与误检特征分析",
 "",
 "## 1. 用户人工确认事实",
 "",
 "- **真实微小疵病**：K0_SMALL_053、054、073、074、077（5例）。",
 "- 首轮另19例SMALL_CANDIDATE依据“只有这五例”作为**用户目视判断的背景噪声**；尚非显微、精密独立真值。",
 "- 6个NO_J5_CANDIDATE_ROI只是预测为空，用户没有确认是否有真实疵病，**保持未评价**。",
 "- 还有另外72个抽出的SMALL_CANDIDATE未人工评价，不得直接当噪声。",
 "",
 "## 2. 人工标签按面积分布",
 "",
 "| 预测连通域源面积 | 人工真实 | 人工噪声 |",
 "|---|---:|---:|",
 ]
for band in ("A_1px2","B_2to3px2","C_4to7px2","D_8pluspx2"):
    sub=cand[cand.area_group==band]
    lines.append(f"| {band} | {(sub.manual_candidate_label=='REAL_MICRO_DEFECT').sum()} | {(sub.manual_candidate_label=='BACKGROUND_NOISE').sum()} |")
lines+=["", "## 3. 已确认微小疵病的原始数值","",
 "| 例号 | 面积(px²) | 黑帽峰值(DN) | 相对暗对比 | DoG中位(DN) |",
 "|---|---:|---:|---:|---:|"]
for r in positive_details.itertuples(index=False):
    lines.append(f"| {r.sample_id} | {r.source_area_px2:.0f} | {r.target_blackhat_peak_DN:.0f} | {r.target_relative_dark_contrast:.4f} | {r.target_DoG_median_DN:.2f} |")
lines+=["","## 4. 仅作探索的规则敏感性","",
 "| 仅要求源检测面积至少 | 人工真实保留/5 | 人工噪声剔除/19 |",
 "|---|---:|---:|"]
for v in assess:
    threshold=v["hypothesis"].split("_")[-1]
    lines.append(f"| {threshold} | {v['confirmed_real_retained']}/5 | {v['visually_labeled_noise_removed']}/19 |")
lines+=["",
"**这是刻意分层抽样的24例上的事后探索，不能将这些比例当作全图Precision/Recall，也不能据此立即启用面积阈值。**",
"",
"## 5. 技术判断",
"",
"- 1px²的6例和2～3px²的6例在本轮目视复核中全部属于噪声，值得进一步单独验证；但未证明所有类似单像素/双像素目标均为噪声。",
"- 已确认53号和54号都只有**4px²**。若简单将门限设为面积至少5px²，这两例就会被错误隐藏。",
f"- DoG暗核中位强度：真实5例中位数 **{dogs[1]:.2f} DN**，噪声19例中位数 **{dogs[2]:.2f} DN**，但真实最弱 **{dogs[0]:.2f} DN** 与噪声最强 **{dogs[3]:.2f} DN** 重叠；DoG不能直接一刀切。",
"- 黑帽峰值和相对暗对比也有明显重叠。仅用黑帽或相对对比度提高阈值会误删真实微小疵病。",
"- 按面积四档人为各抽6个，所以真实5/24不代表全图14884绿色候选的真实比例。整体中位数可能被面积分层构成影响，后续须在相同面积段内比较特征。",
"- 不修改固定170/230主算法、Case03-H或J5，不删除原有候选，只保留中大主图/绿色参考图分离。",
"",
"## 6. 下一步最节省时间的复核方案",
"",
"优先复核**尚未标注的4～7px²和8px²以上**样本，再抽一些1～3px²确认是否存在真实细微缺陷；此外至少检查部分NO_J5_CANDIDATE_ROI是否存在漏检。若条件允许，再用26号第二帧或其他未调参样本做完全独立验证。",
"",
"基于上述新增人工证据判断是否值得开发二次筛噪；未经独立验证不部署新的删除规则。",
"",
"审计材料：first_pass_review_30_user_feedback_20261012.csv，manual_labels_feature_comparison.csv，first_pass_hypothetical_rule_sensitivity.csv；首轮原模板保留未改变。"
]
DEST.write_text("\n".join(lines)+"\n",encoding="utf-8")
print("CASE03K_EVIDENCE_REPORT_DONE",json.dumps({
"confirmed_real_ids":sorted(real.sample_id.tolist()),
"human_noise":len(noise),"real_area_min":float(real.source_area_px2.min()),
"DoG_positive_median":round(float(dogs[1]),4),
"DoG_noise_median":round(float(dogs[2]),4),
"DoG_overlap":float(dogs[0])<float(dogs[3]),
"in_sample_area4_retains_real":next(r["confirmed_real_retained"] for r in assess if r["hypothesis"].endswith("_4px2")),
"output_report":str(DEST)
},ensure_ascii=False))
