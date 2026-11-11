"""Case03-D: all-candidate non-destructive ranking and human-label audit.

Score is fixed BEFORE reading manual labels. It is neither a defect probability
nor an estimate of full-image recall or generalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from config import user_config as cfg
from src.detection.candidate_priority import build_priority,evaluate_review_budget

LOGGER=logging.getLogger("case03d")


def to_csv(rows,path):
    pd.DataFrame(rows).to_csv(path,index=False,encoding="utf-8-sig")


def fingerprint(path:Path)->dict:
    sha=hashlib.sha256()
    with path.open("rb") as f:
        while block:=f.read(4*1024*1024):
            sha.update(block)
    stat=path.stat()
    return {"absolute_path":str(path),"bytes":stat.st_size,
            "mtime_ns":stat.st_mtime_ns,"sha256":sha.hexdigest()}


def load_labels(path:Path, positive:int, negative:int)->dict:
    data=pd.read_csv(path,dtype=str,keep_default_na=False)
    if not {"candidate_id","manual_label","review_status","provenance"}.issubset(data):
        raise ValueError("missing label fields")
    if data["candidate_id"].duplicated().any() or (data["candidate_id"]=="").any():
        raise ValueError("duplicate/blank candidate ID")
    if not data["review_status"].eq("reviewed").all():
        raise ValueError("unreviewed label found")
    if not set(data["manual_label"]).issubset({"confirmed_dark_spot","background_artifact"}):
        raise ValueError("unknown label type")
    labels=dict(zip(data["candidate_id"],data["manual_label"]))
    counts=Counter(labels.values())
    if counts!={"confirmed_dark_spot":positive,"background_artifact":negative}:
        raise ValueError(f"unexpected human label counts {counts}")
    return labels


def tier_descriptive(full):
    n=len(full)
    out=[]
    for tier,group in full.groupby("review_tier",sort=False):
        centroid_y=group["centroid_y"].to_numpy(dtype=float)
        near=group["near_band_transition"].astype(str).str.lower().eq("true")
        valid=group["raw_reference_valid"].astype(str).str.lower().eq("true")
        out.append({
            "review_tier":tier,"count":len(group),"population_fraction":len(group)/n,
            "area_median_px":float(group["area_px"].median()),
            "area_p90_px":float(group["area_px"].quantile(.90)),
            "peak_median_dn":float(group["peak_response_dn"].median()),
            "peak_p90_dn":float(group["peak_response_dn"].quantile(.90)),
            "one_pixel_fraction":float(group["area_px"].eq(1).mean()),
            "near_transition_count":int(near.sum()),
            "near_transition_fraction":float(near.mean()),
            "raw_reference_valid_fraction":float(valid.mean()),
            "upper15_count":int((centroid_y<cfg.RAW_HEIGHT*.15).sum()),
            "middle40_count":int(((centroid_y>=cfg.RAW_HEIGHT*.30)&(centroid_y<cfg.RAW_HEIGHT*.70)).sum()),
            "lower15_count":int((centroid_y>=cfg.RAW_HEIGHT*.85).sum()),
            "not_defect_truth":True
        })
    return pd.DataFrame(out)


def summarize_label_ranks(rank,labels,source):
    index=rank.set_index("candidate_id")
    if not index.index.is_unique:
        raise ValueError("duplicate ranked candidate IDs")
    positives=[k for k,v in labels.items() if v=="confirmed_dark_spot"]
    negatives=[k for k,v in labels.items() if v=="background_artifact"]
    out={"label_source":source,"positive_count":len(positives),
         "negative_count":len(negatives)}
    for groupname,keys in (("positive",positives),("negative",negatives)):
        r=index.loc[keys,"priority_rank"].to_numpy(dtype=int)
        out[groupname+"_rank_min"]=int(r.min())
        out[groupname+"_rank_median"]=float(np.median(r))
        out[groupname+"_rank_max"]=int(r.max())
        for tier in ("A_first_review","B_second_review","C_later_review"):
            out[groupname+"_"+tier]=int(index.loc[keys,"review_tier"].eq(tier).sum())
    out["not_full_image_recall"]=True
    return out


def make_report(out,strict,extra,tier,budget):
    n=cfg.CASE03D_EXPECTED_H_COUNT
    na=math.ceil(n*cfg.CASE03D_FIRST_TIER_FRACTION)
    nb=math.ceil(n*cfg.CASE03D_SECOND_TIER_CUMULATIVE_FRACTION)
    lines=[
        "# Case03-D：样品26候选特征复核优先级报告",
        "",
        "## 目标与运行边界",
        "",
        "- 对所有88,043个H170/230候选建立复核顺序，零删减，原有Case02/03-B/03-C不修改。",
        "- 按样品26全部候选的经验百分位，给面积和峰值响应各50%的权重；以原始DN特征而非显示灰度排序。",
        "- 评分完全不读取人工标签；人工标签只用于事后探索性复核与比较。",
        f"- A前1%= {na}个；B接下来的9%= {nb-na}个；C最后90%= {n-nb}个。这里的A/B/C表示人工复核先后顺序，不是疵病真实性概率。",
        "- RAW对比度、MAD及增长倍率仅保留作辅助诊断，因RAW参考无效的候选不会被自动降权。",
        "- 与仅面积、仅峰值两套基线排序对照，不用本批人工标签拟合权重和阈值。",
        "- review_031/046/056本阶段不作为目标缺陷或负候选真值，不继续处理局部漏检。",
        "",
        "## 分级对象数量与特征构成",
        "",
        "| 复核组 | 数量 | 面积中位数px | 峰值DN中位数 | 单像素占比 | 亮暗过渡邻近比例 | RAW参考有效比例 |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for _,r in tier.iterrows():
        lines.append(f"| {r['review_tier']} | {int(r['count'])} | {r['area_median_px']:.2f} | {r['peak_median_dn']:.2f} | {r['one_pixel_fraction']:.1%} | {r['near_transition_fraction']:.1%} | {r['raw_reference_valid_fraction']:.1%} |")
    lines+=["","## 已标注候选的复核顺序（并非全图检出率）","","| 标签组 | 正候选 | 负候选 | A组正候选数 | B组正候选数 | C组正候选数 | 正候选最靠后排名 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for r in (strict,extra):
        lines.append(f"| {r['label_source']} | {r['positive_count']} | {r['negative_count']} | {r['positive_A_first_review']} | {r['positive_B_second_review']} | {r['positive_C_later_review']} | {r['positive_rank_max']} |")
    lines+=["","## 复核预算对照（严格标签14正39负，仅评价已标注候选）","","| 方法 | Top-N个候选 | 已标注正候选覆盖 | 已标注负候选覆盖 |",
            "|---|---:|---:|---:|"]
    for _,r in budget.iterrows():
        if int(r["budget_rank_top_n"]) in [100,500,1000,5000,na,nb]:
            lines.append(f"| {r['method']} | {int(r['budget_rank_top_n'])} | {int(r['label_positive_in_top_n'])}/14 | {int(r['label_negative_in_top_n'])}/39 |")
    lines+=["",
         "## 使用边界与下一步验收",
         "",
         "1. Score表示样品26内部的人工复核优先级，不是缺陷概率、产品质量分级或光学透过率。",
         "2. 完整结果包含每个候选原有全部特征与新排序，C组依然保留；不得直接删除C组或单像素候选。",
         "3. 面积、峰值、种子数之间并非独立证据；强黑带边缘等结构可占据A组，必须结合空间背景统计和RAW图册人工检查。",
         "4. 14/39严格组和18/39框选暂定组是人工定向选取的已检测候选，不能估计全图误检率、召回率、真实细线检出率或跨样品泛化性能。",
         "5. 对错误排序的已标注正负候选进行人工诊断，后续再研究更合理的复核策略；不得根据本组标签反复调参数宣称提升。",
         "6. 样品27～30、模型训练、局部MAD和后续Case04/05均未执行；待用户验收Case03-D首轮。",
         "",
         "## 主要交付",
         "",
         "- candidate_priority_full.csv：88,043条全部候选及所有源特征/排序；review_order.csv为按排序顺序全量索引。",
         "- review_tier_statistics.csv：A/B/C组描述性统计及背景位置分布。",
         "- labeled_strict_review.csv、labeled_provisional_sensitivity.csv：人工标注候选的排名。",
         "- review_budget_strict.csv、review_budget_provisional_sensitivity.csv：预算对照。",
         "- label_review_summary.json、config_snapshot.json、source_manifest.json、acceptance.json。",
         "- figures下的候选RAW对照图册与全图优先复核散点预览，如已生成。",
         "",
         "**最终状态：工程可通过，但真实候选筛选效果及独立样品泛化仍须用户复核。**"]
    (out/"case03d_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def run_case03d(run_id:str|None=None)->Path:
    timer=perf_counter()
    outbase=cfg.OUTPUT_ROOT/"case03d"
    outbase.mkdir(parents=True,exist_ok=True)
    out=outbase/(run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    if out.exists():
        raise FileExistsError(f"refuse overwrite run: {out}")
    (out/"logs").mkdir(parents=True)
    handler=logging.FileHandler(out/"logs"/"case03d.log",encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    paths=[ROOT/cfg.CASE03D_SOURCE_FEATURE_CSV,
           ROOT/cfg.CASE03D_SOURCE_LABELS_VERIFIED_CSV,
           ROOT/cfg.CASE03D_SOURCE_LABELS_PROVISIONAL_CSV]
    before=[fingerprint(x) for x in paths]
    data=pd.read_csv(paths[0],dtype={"candidate_id":"string"},low_memory=False)
    if len(data)!=cfg.CASE03D_EXPECTED_H_COUNT or data["candidate_id"].duplicated().any():
        raise AssertionError("source H count/ID invalid")
    if int(data["area_px"].sum())!=cfg.CASE03D_EXPECTED_H_TOTAL_PIXELS:
        raise AssertionError("H candidate area conservation")
    checks={"sample":cfg.CASE03D_SAMPLE_ID,"frame":cfg.CASE03D_FRAME_ID,
            "method":"H","scale_source":"fused",
            "low_threshold_dn":170,"high_threshold_dn":230,"connectivity":8}
    for field,val in checks.items():
        if not data[field].eq(val).all():
            raise AssertionError(f"unexpected source {field}")
    LOGGER.info("Loaded %d H components, computing LABEL-BLIND score",len(data))
    rank=build_priority(data,
            area_weight=cfg.CASE03D_AREA_RANK_WEIGHT,
            peak_weight=cfg.CASE03D_PEAK_RANK_WEIGHT,
            first_tier_fraction=cfg.CASE03D_FIRST_TIER_FRACTION,
            second_tier_cumulative_fraction=cfg.CASE03D_SECOND_TIER_CUMULATIVE_FRACTION)
    if not (rank["candidate_id"].to_numpy()==data["candidate_id"].astype(str).to_numpy()).all():
        raise AssertionError("score ordering not aligned to source candidate order")
    LOGGER.info("Now (after scoring) read manual labels for exploratory evaluation")
    conservative=load_labels(paths[1],14,39)
    provisional=load_labels(paths[2],18,39)
    if not set(conservative).issubset(provisional) or \
       any(provisional[k]!=val for k,val in conservative.items()):
        raise AssertionError("strict labels must be subset of provisional")
    added=set(provisional)-set(conservative)
    if len(added)!=4 or any(provisional[k]!="confirmed_dark_spot" for k in added):
        raise AssertionError("expected precisely four provisional box candidates")
    joined=data.copy()
    for column in rank:
        if column!="candidate_id":
            joined[column]=rank[column].to_numpy()
    joined["manual_label_strict"]=joined["candidate_id"].map(conservative).fillna("")
    joined["manual_label_plus_provisional"]=joined["candidate_id"].map(provisional).fillna("")
    joined["manual_evidence_status"]=np.where(joined["candidate_id"].isin(added),
                      "PROVISIONAL_BOX__NOT_PIXEL_GT",
                      np.where(joined["candidate_id"].isin(conservative),"HUMAN_REVIEWED","UNLABELED"))
    joined.to_csv(out/"candidate_priority_full.csv",index=False,encoding="utf-8-sig")
    rank.sort_values("priority_rank").to_csv(out/"review_order.csv",index=False,encoding="utf-8-sig")
    tier=tier_descriptive(joined)
    tier.to_csv(out/"review_tier_statistics.csv",index=False,encoding="utf-8-sig")
    strict_details,strict_budget=evaluate_review_budget(rank,conservative,budgets=tuple(cfg.CASE03D_REVIEW_BUDGETS))
    provisional_details,provisional_budget=evaluate_review_budget(rank,provisional,budgets=tuple(cfg.CASE03D_REVIEW_BUDGETS))
    for row in provisional_details:
        row["evidence_level"]="PROVISIONAL_BOX" if row["candidate_id"] in added else "REVIEWED_CANDIDATE"
    to_csv(strict_details,out/"labeled_strict_review.csv")
    to_csv(provisional_details,out/"labeled_provisional_sensitivity.csv")
    to_csv(strict_budget,out/"review_budget_strict.csv")
    to_csv(provisional_budget,out/"review_budget_provisional_sensitivity.csv")
    strict_sum=summarize_label_ranks(rank,conservative,"strict_human_review")
    provisional_sum=summarize_label_ranks(rank,provisional,"provisional_box_sensitivity")
    (out/"label_review_summary.json").write_text(json.dumps({
        "strict":strict_sum,"provisional_sensitivity":provisional_sum,
        "provisional_only_ids":sorted(added),
        "non_target_roi_31_46_56":"not negative candidate truth",
    },ensure_ascii=False,indent=2),encoding="utf-8")
    keys=["CASE03D_SOURCE_FEATURE_CSV","CASE03D_SOURCE_LABELS_VERIFIED_CSV",
          "CASE03D_SOURCE_LABELS_PROVISIONAL_CSV","CASE03D_SAMPLE_ID","CASE03D_FRAME_ID",
          "CASE03D_AREA_RANK_WEIGHT","CASE03D_PEAK_RANK_WEIGHT",
          "CASE03D_FIRST_TIER_FRACTION","CASE03D_SECOND_TIER_CUMULATIVE_FRACTION",
          "CASE03D_REVIEW_BUDGETS","CASE03D_PRIMARY_RANKING_METHOD",
          "CASE03D_ATLAS_PATCH_SIZE_PX","CASE03D_ATLAS_CANDIDATES_PER_GROUP",
          "CASE03D_FULL_GALLERY_ENABLED","CASE03D_EXPECTED_H_COUNT",
          "CASE03D_EXPECTED_H_TOTAL_PIXELS","CASE03D_REVIEW_031_046_056_STATUS",
          "CASE03D_EXPECTED_ONE_PIXEL_H_COUNT","CASE03D_MICRO_AUDIT_TOP_N",
          "CASE03D_MICRO_AUDIT_ATLAS_COUNT"]
    (out/"config_snapshot.json").write_text(json.dumps({k:getattr(cfg,k) for k in keys},
                    ensure_ascii=False,indent=2),encoding="utf-8")
    n=len(rank)
    if set(rank["priority_rank"].to_numpy(dtype=int))!=set(range(1,n+1)):
        raise AssertionError("priority ranks not complete")
    tier_counts=dict(Counter(joined["review_tier"]))
    expected={
        "A_first_review":math.ceil(n*cfg.CASE03D_FIRST_TIER_FRACTION),
        "B_second_review":math.ceil(n*cfg.CASE03D_SECOND_TIER_CUMULATIVE_FRACTION)-
                          math.ceil(n*cfg.CASE03D_FIRST_TIER_FRACTION),
        "C_later_review":n-math.ceil(n*cfg.CASE03D_SECOND_TIER_CUMULATIVE_FRACTION)}
    if tier_counts!=expected:
        raise AssertionError(f"review-tier counts wrong {tier_counts}")
    make_report(out,strict_sum,provisional_sum,tier,pd.DataFrame(strict_budget))
    if cfg.CASE03D_FULL_GALLERY_ENABLED:
        from scripts.build_case03d_gallery import build_gallery
        build_gallery(out,joined,strict_ids=set(conservative),provisional_ids=added)
    # Independently audit high-response 1px candidates that area+peak ranking
    # postpones to C; no change to the main ranking or truth labels.
    from scripts.build_case03d_micro_safety import build_micro_safety_lane
    build_micro_safety_lane(
        out,top_n=cfg.CASE03D_MICRO_AUDIT_TOP_N,
        atlas_k=cfg.CASE03D_MICRO_AUDIT_ATLAS_COUNT,
    )
    after=[fingerprint(x) for x in paths]
    if before!=after:
        raise AssertionError("protected inputs modified")
    (out/"source_manifest.json").write_text(json.dumps({
            "before":before,"after":after,"source_unchanged":True
        },ensure_ascii=False,indent=2),encoding="utf-8")
    acceptance={
        "status":"PASS_ENGINEERING__PENDING_INDEPENDENT_VALIDATION",
        "candidate_count":n,"area_sum_pixels":int(joined["area_px"].sum()),
        "all_source_IDs_preserved":True,"no_candidate_deleted":True,
        "label_blind_ranking":True,
        "tier_counts":tier_counts,
        "reviewed_positive_count":14,"reviewed_negative_count":39,
        "provisional_plus_positive_count":18,"provisional_plus_negative_count":39,
        "provisional_not_pixel_truth":True,
        "raw_reference_missing_does_not_penalize":True,
        "31_46_56_non_target_not_reclassified_as_negative":True,
        "source_unchanged":True,
        "runtime_seconds":round(perf_counter()-timer,3)}
    (out/"acceptance.json").write_text(json.dumps(acceptance,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"acceptance.md").write_text(
        "# Case03-D 工程验收\n\n"+json.dumps(acceptance,indent=2,ensure_ascii=False)+
        "\n\n仅工程自验通过，真实检测效果仍待独立人工核验。\n",encoding="utf-8")
    LOGGER.info("PASS output=%s duration=%ss",out,acceptance["runtime_seconds"])
    print("CASE03D_OUTPUT",out)
    print("CASE03D_ACCEPTANCE",json.dumps(acceptance,ensure_ascii=False))
    print("CASE03D_HUMAN_LABEL_RANKS",json.dumps({"strict":strict_sum,"provisional":provisional_sum},ensure_ascii=False))
    return out


def run_from_main(run_id:str|None=None)->int:
    run_case03d(run_id)
    return 0


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",default=None)
    args=parser.parse_args()
    run_case03d(args.run_id)
