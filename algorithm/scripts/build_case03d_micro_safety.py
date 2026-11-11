"""Case03-D supplementary single-pixel review lane: DO NOT delete or boost ranks.

The main area+peak queue systematically puts 1-pixel H objects into C.
A second independent *audit list* is therefore offered for selective manual
review of high peak one-pixel anomalies, without any classification claims.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from scripts.build_case03d_gallery import render_tile,save_png,math_ceil

CASE03B=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"


def build_micro_safety_lane(directory:Path,top_n:int=100,atlas_k:int=12):
    full_path=directory/"candidate_priority_full.csv"
    if not full_path.is_file():raise FileNotFoundError(full_path)
    fields=["candidate_id","area_px","peak_response_dn","priority_rank",
            "review_tier","centroid_x","centroid_y","bbox_x","bbox_y",
            "bbox_w","bbox_h","near_band_transition","manual_evidence_status",
            "manual_label_strict"]
    frame=pd.read_csv(full_path,usecols=fields,dtype={"candidate_id":str},low_memory=False)
    if len(frame)!=cfg.CASE03D_EXPECTED_H_COUNT:
        raise AssertionError("expected complete ranking")
    micro=frame.loc[frame["area_px"].eq(1)].copy()
    if len(micro)!=cfg.CASE03D_EXPECTED_ONE_PIXEL_H_COUNT:
        raise AssertionError("micro candidate census does not match Case03-C")
    if set(micro["review_tier"])!={"C_later_review"}:
        raise AssertionError("unexpected 1px review tier; diagnostics must be recomputed")
    micro=micro.sort_values(["peak_response_dn","candidate_id"],
                            ascending=[False,True],kind="mergesort").reset_index(drop=True)
    micro.insert(0,"micro_audit_rank",np.arange(1,len(micro)+1))
    micro["watchlist_purpose"]="independent_micro_review__not_probable_defect"
    micro.to_csv(directory/"micro_single_pixel_full_audit.csv",index=False,encoding="utf-8-sig")
    selected=micro.head(top_n)
    selected.to_csv(directory/"micro_single_pixel_top100.csv",index=False,encoding="utf-8-sig")
    folder=directory/"figures"
    folder.mkdir(parents=True,exist_ok=True)
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",dtype=">u2",mode="r",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    S=load_packed_mask(CASE03B/"fused_S_TL230_TH230.npz")
    H=load_packed_mask(CASE03B/"fused_H_TL170_TH230.npz")
    if not (S.shape==H.shape==raw.shape):
        raise ValueError("shape mismatch")
    size=int(cfg.CASE03D_ATLAS_PATCH_SIZE_PX)
    k=min(atlas_k,len(selected))
    tile_w=size*2+5
    tile_h=size+51
    cols=3;gap=12
    canvas=np.full((math_ceil(k,cols)*(tile_h+gap)+60,cols*(tile_w+gap),3),245,np.uint8)
    cv2.putText(canvas,"Independent 1px audit: strongest Black-Hat pixels (ALL stay in C)",
                (18,25),cv2.FONT_HERSHEY_SIMPLEX,.58,(34,42,52),1,cv2.LINE_AA)
    cv2.putText(canvas,"No one-pixel candidate is confirmed a defect; RAW vs S/H overlay",
                (18,47),cv2.FONT_HERSHEY_SIMPLEX,.46,(74,74,74),1,cv2.LINE_AA)
    for i,item in enumerate(selected.head(k).to_dict("records")):
        tile=render_tile(item,raw,S,H,size)
        x=(i%cols)*(tile_w+gap)
        y=60+(i//cols)*(tile_h+gap)
        canvas[y:y+tile_h,x:x+tile_w]=tile
    save_png(folder/"atlas_single_pixel_high_peak_audit.png",canvas)
    summary={
        "source_ranking":str(full_path),
        "total_candidate_count":len(frame),
        "one_pixel_total_count":len(micro),
        "one_pixel_all_in_C":True,
        "micro_review_topN":min(top_n,len(micro)),
        "atlas_count":k,
        "micro_peak_max_dn":int(micro["peak_response_dn"].max()),
        "micro_peak_p99_dn":float(micro["peak_response_dn"].quantile(.99)),
        "known_strict_positive_one_pixel_count":int(micro["manual_label_strict"].fillna("").eq("confirmed_dark_spot").sum()),
        "purpose":"EXPLORATORY_AUDIT_ONLY__not_priority_tier_upgrade_not_defect_detection",
        "no_candidate_deletion_or_reranking":True
    }
    (directory/"micro_safety_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    (directory/"micro_safety_report.md").write_text(
        "# Case03-D微小候选防盲区补充审查\n\n"
        "- 主排序已经完成，本补充**不改变**88,043个候选的review_score、priority_rank或review_tier。\n"
        f"- 单像素H候选 {len(micro)}个，全部处于C组；只用面积+峰值的主排序会让微小点统一后置。\n"
        f"- 从单像素候选按原始Black-Hat峰值DN降序列出前{top_n}个，供人工**抽查**；"
        "不把高响应单像素当成已确认疵病，也不直接赋予A/B组身份。\n"
        "- 当前已标注保守正候选中尚无面积=1px的例子，故无法根据已有标注验证单像素真实疵病的排序质量。\n"
        "- 后续需人工验证微小点、细划痕及不同背景区域，并建立独立样品测试；在此之前不得删除C组。\n"
        "- 文件：micro_single_pixel_full_audit.csv（全部单像素），"
        "micro_single_pixel_top100.csv（人工抽查队列），"
        "figures/atlas_single_pixel_high_peak_audit.png（真实RAW局部图）。\n",
        encoding="utf-8")
    print("MICRO_SAFETY_SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",default="outputs/case03d/run_20261009_190000")
    args=parser.parse_args()
    out=Path(args.output_dir)
    if not out.is_absolute():out=ROOT/out
    build_micro_safety_lane(out)
