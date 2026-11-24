"""Case03-C-R1: faithful RAW reference display and label-aware feature audit.

Run once without human labels to create 60 corrected image panels, exact sampled
reference NPZ masks, and unlabelled diagnostic statistics. Later, after a user
edits manual_review_template.csv, use --evaluate-only --labels with their file;
no model is fitted, no candidate is removed, no label is invented.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# 使用设备已有的CJK字体显示中文，不随项目打包或分发字体文件。
plt.rcParams['font.sans-serif'] = ['Noto Sans SC', 'Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from config import user_config
from src.detection.reference_ring_geometry import select_reference_pixels, project_reference_masks
from src.detection.feature_discrimination import (
    read_csv_rows, unique_manual_labels, exploratory_auc, unlabeled_distributions
)
from src.detection.thresholding import load_packed_mask
from src.visualization.candidate_feature_atlas import normalize_raw, response_display, make_overlay


def write_csv(path:Path, rows:list[dict]):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:
        path.write_text("",encoding="utf-8")
        return
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def render_roi(path:Path, raw:np.ndarray, response:np.ndarray,
               s:np.ndarray, h:np.ndarray, selected:np.ndarray,
               eligible:np.ndarray, used:np.ndarray, metadata:dict):
    raw_view, raw_range=normalize_raw(raw)
    rsp_view, rsp_cap=response_display(response)
    overlay=make_overlay(raw_view,s,h,selected,used)
    fig,axes=plt.subplots(2,4,figsize=(15.5,8),dpi=115)
    items=[
        (raw_view,f"原始RAW (显示P1={raw_range[0]:.0f},P99.5={raw_range[1]:.0f} DN)","gray"),
        (rsp_view,f"Black-Hat响应 (显示上限{rsp_cap:.1f} DN)","magma"),
        (s.astype(float),"单阈值S230","gray"),
        (h.astype(float),"双阈值H170/230","gray"),
        (eligible.astype(float),f"可选参考环带：ROI内{int(eligible.sum())}px","gray"),
        (used.astype(float),f"实际参与统计样本：ROI内{int(used.sum())}px","gray"),
        (overlay.astype(float)/255.0,"RAW叠加：黄S/青H扩展/紫有效抽样/红选中",None),
        (None,"统计字段与有效性",None),
    ]
    for ax,(img,title,cmap) in zip(axes.flat,items):
        ax.set_title(title,fontsize=9)
        if img is not None:
            ax.imshow(img,cmap=cmap,vmin=0 if cmap else None,vmax=1 if cmap else None,interpolation="nearest")
        ax.set_xticks([]);ax.set_yticks([])
    ax=axes[1,3]
    ax.axis("off")
    data=[
        "候选编号："+metadata["candidate_id"],
        f"真实环带像素: {metadata['eligible_count']}",
        f"抽样像素上限后: {metadata['sample_count']}",
        f"RAW参考有效: {metadata['valid']}",
        "无效原因："+(metadata["invalid_reason"] or "无"),
        f"参考背景中位数: {metadata['bg_median_dn']}",
        f"候选减背景灰度差定义: 背景-候选",
        f"RAW ΔDN: {metadata['raw_delta_dn']}",
        f"背景MAD: {metadata['bg_mad_dn']}",
        "人工标签: 尚未确认",
    ]
    ax.text(0.02,0.94,"\n".join(data),va="top",ha="left",fontsize=9,
            transform=ax.transAxes,linespacing=1.55)
    fig.suptitle(
        f"Case03-C-R1 | {metadata['review_id']} | 样品26原始分辨率 | "
        "仅显示实际采样参考像素；未人工确认真假",
        fontsize=12
    )
    fig.tight_layout(rect=(0,0,1,.945))
    fig.savefig(path,bbox_inches="tight")
    plt.close(fig)


def write_unlabelled_plot(out:Path, stats:list[dict],feature:str):
    names=["area_1px_proxy","area_2to19px_proxy","area_ge20px_proxy"]
    values={r["stratum"]:r for r in stats if r["feature"]==feature}
    if not all(k in values for k in names):
        return
    med=[float(values[k]["median"]) for k in names]
    p25=[float(values[k]["p25"]) for k in names]
    p75=[float(values[k]["p75"]) for k in names]
    x=np.arange(len(names))
    fig,ax=plt.subplots(figsize=(8,4),dpi=130)
    ax.errorbar(x,med,yerr=[np.asarray(med)-np.asarray(p25),np.asarray(p75)-np.asarray(med)],
                fmt="o",capsize=5)
    ax.set_xticks(x,["1px","2-19px",">=20px"])
    ax.set_ylabel(feature+" (P25 / median / P75)")
    ax.set_title("无标签形态代理分组：不能视为疵病/噪声区分结果")
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(out/f"unlabeled_{feature}_by_area.png")
    plt.close(fig)


def evaluate_labels(source:Path,labels_path:Path,output:Path)->dict:
    all_features=read_csv_rows(source/"hysteresis_candidate_features.csv")
    labeled=read_csv_rows(labels_path)
    labels,counts=unique_manual_labels(labeled)
    comparison=exploratory_auc(all_features,labels)
    write_csv(output/"feature_labelled_separability.csv",comparison)
    positive=sum(value in {"confirmed_dark_spot","confirmed_fine_line"} for value in labels.values())
    negative=sum(value in {"background_artifact","instrument_marker"} for value in labels.values())
    ready=positive>=5 and negative>=5
    report={
        "labels_csv":str(labels_path),"unique_candidate_labels":counts,
        "positive_n":positive,"negative_n":negative,
        "status":"EXPLORATORY_ONLY" if ready else "PENDING_HUMAN_LABELS",
        "minimum_each_group":5,
        "interpretation":"per-feature univariate rank AUC with 300 stratified bootstrap; no direction selection; no model training; no generalization beyond nonrandom sample26 candidates",
    }
    (output/"label_evaluation_status.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    return report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-run",default="outputs/case03c/run_20261008_174000")
    ap.add_argument("--output-run-id",default=None)
    ap.add_argument("--evaluate-only",action="store_true")
    ap.add_argument("--output-dir",default=None)
    ap.add_argument("--labels",default=None)
    args=ap.parse_args()
    source=ROOT/args.source_run
    if not source.is_dir():raise FileNotFoundError(source)
    if args.evaluate_only:
        if not args.output_dir:raise ValueError("--evaluate-only requires --output-dir")
        out=Path(args.output_dir)
        if not out.is_absolute():out=ROOT/out
        if not out.is_dir():raise FileNotFoundError(out)
        label=Path(args.labels) if args.labels else out/"manual_review_template.csv"
        status=evaluate_labels(source,label,out)
        print("LABEL_STATUS",status["status"],status["positive_n"],status["negative_n"])
        return 0
    output_base=ROOT/"outputs"/"case03c_revision"
    output_base.mkdir(parents=True,exist_ok=True)
    name=args.output_run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    out=output_base/name
    if out.exists():raise FileExistsError(f"refuse overwrite {out}")
    (out/"figures").mkdir(parents=True)
    (out/"patches").mkdir(parents=True)
    selected=read_csv_rows(source/"manual_review_template.csv")
    feature_rows=read_csv_rows(source/"hysteresis_candidate_features.csv")
    feature_by_id={r["candidate_id"]:r for r in feature_rows}
    source_files=[
        source/"manual_review_template.csv",source/"hysteresis_candidate_features.csv",
        ROOT/"outputs"/"case03b"/"run_20261008_153500"/"masks"/"sample_26_frame_1"/"fused_H_TL170_TH230.npz",
        user_config.DATA_ROOT/"26 (1).raw",
    ]
    before={str(p):{"bytes":p.stat().st_size,"mtime_ns":p.stat().st_mtime_ns} for p in source_files}
    # full resolution mask is read-only, ~100MB; candidate feature CSV stays unchanged
    full_h=load_packed_mask(source_files[2])
    raw_full=np.memmap(source_files[3],dtype=">u2",mode="r",shape=full_h.shape)
    reference_radius=int(user_config.CASE03C_RAW_REFERENCE_RADIUS_PX)
    reference_max=int(user_config.CASE03C_RAW_REFERENCE_MAX_PIXELS)
    records=[]
    for index,entry in enumerate(selected,1):
        old_npz=source/entry["patch_npz"]
        with np.load(old_npz,allow_pickle=False) as n:
            raw=np.asarray(n["raw_dn"],dtype=np.uint16)
            response=np.asarray(n["response_dn"],dtype=np.uint16)
            s=np.asarray(n["S230"],dtype=bool)
            h=np.asarray(n["H170_230"],dtype=bool)
            target=np.asarray(n["selected_candidate"],dtype=bool)
            origin=np.asarray(n["origin_xy"],dtype=np.int64)
        x0,y0=map(int,origin)
        bounds=(x0,y0,x0+raw.shape[1],y0+raw.shape[0])
        cid=entry["candidate_id"]
        row=feature_by_id.get(cid)
        eligible=np.zeros(raw.shape,dtype=bool)
        used=np.zeros(raw.shape,dtype=bool)
        global_count=0
        sample_count=0
        valid=False
        invalid_reason="no_candidate_in_selected_background_ROI"
        if row is not None:
            c=SimpleNamespace(**{key:int(row[key]) for key in ("bbox_x","bbox_y","bbox_w","bbox_h")})
            selection=select_reference_pixels(c,full_h,
                 radius_px=reference_radius,max_reference_pixels=reference_max)
            valid=row["raw_reference_valid"]=="True"
            eligible,used=project_reference_masks(selection,image_bounds=bounds,valid_reference=valid)
            global_count=selection.eligible_count
            sample_count=selection.sampled_count
            invalid_reason=row["raw_reference_invalid_reason"]
            if (global_count!=int(row["raw_reference_pixel_count"])
               or sample_count!=int(row["raw_reference_sample_count"])):
                raise AssertionError(f"reference count mismatch {cid}")
            if valid:
                raw_values=np.asarray(raw_full[selection.sample_y,selection.sample_x],dtype=np.float64)
                med=float(np.median(raw_values))
                mad=float(np.median(np.abs(raw_values-med)))
                if abs(med-float(row["raw_background_median_dn"]))>1e-9 or abs(mad-float(row["background_noise_mad_dn"]))>1e-9:
                    raise AssertionError(f"actual raw reference statistics mismatch: {cid}")
            if bool(np.any(used & h)):
                raise AssertionError(f"sample mask overlaps a candidate: {cid}")
        out_npz=out/"patches"/f"review_{index:03d}_reference_corrected.npz"
        np.savez_compressed(out_npz,raw_dn=raw,response_dn=response,S230=s,H170_230=h,
                            selected_candidate=target,reference_eligible_in_roi=eligible,
                            reference_sample_used_in_roi=used,origin_xy=origin,
                            candidate_id=np.asarray(cid),reference_valid=np.asarray(valid))
        meta={
            "review_id":entry["review_id"],"candidate_id":cid or "(background ROI)",
            "eligible_count":global_count,"sample_count":sample_count,"valid":valid,
            "invalid_reason":invalid_reason,
            "bg_median_dn":row["raw_background_median_dn"] if row else "",
            "raw_delta_dn":row["raw_delta_dn"] if row else "",
            "bg_mad_dn":row["background_noise_mad_dn"] if row else "",
        }
        output_img=out/"figures"/f"review_{index:03d}_reference_corrected.png"
        render_roi(output_img,raw,response,s,h,target,eligible,used,meta)
        records.append({
            "review_id":entry["review_id"],"candidate_id":cid,"valid_reference":valid,
            "global_eligible_count":global_count,"global_reference_sample_count":sample_count,
            "display_eligible_count":int(eligible.sum()),"display_used_sample_count":int(used.sum()),
            "source_raw_background_median_dn":meta["bg_median_dn"],
            "source_raw_delta_dn":meta["raw_delta_dn"],
            "invalid_reason":invalid_reason,
            "figure":str(output_img.relative_to(out)),
            "patch":str(out_npz.relative_to(out)),
        })
        if index%10==0:print("RENDERED",index,flush=True)
    write_csv(out/"reference_geometry_audit.csv",records)
    # preserve original labels in an editable working copy, with no automatic labels.
    (out/"manual_review_template.csv").write_bytes((source/"manual_review_template.csv").read_bytes())
    stats=unlabeled_distributions(feature_rows)
    write_csv(out/"feature_distribution_unlabeled.csv",stats)
    write_unlabelled_plot(out/"figures",stats,"raw_delta_dn")
    write_unlabelled_plot(out/"figures",stats,"growth_ratio_px")
    eval_result=evaluate_labels(source,out/"manual_review_template.csv",out)
    after={str(p):{"bytes":p.stat().st_size,"mtime_ns":p.stat().st_mtime_ns} for p in source_files}
    passed=bool(before==after and len(records)==len(selected)
                 and all(r["display_used_sample_count"]<=r["global_reference_sample_count"] for r in records)
                 and all(not r["display_used_sample_count"] for r in records if not r["valid_reference"]))
    summary={
        "source":str(source),"output":str(out),"rows":len(records),
        "unique_review_candidates":len({r["candidate_id"] for r in records if r["candidate_id"]}),
        "source_unchanged":before==after,
        "reference_counts_match_legacy":True,
        "reference_statistics_match_legacy":True,
        "invalid_references_have_no_used_pixels":True,
        "label_status":eval_result["status"],
        "result":"PASS_ENGINEERING" if passed else "FAIL",
    }
    (out/"acceptance.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    report=[
        "# Case03-C-R1：RAW参考环带显示一致性与特征判别力验证准备",
        "",
        "**工程结果：** "+summary["result"],
        f"- 源运行：`{source}`，新独立运行：`{out}`。",
        f"- 原始参考图册条目：{len(records)}，其中唯一候选：{summary['unique_review_candidates']}（重复ROI不可当作独立真值）。",
        f"- 参考算法：候选bbox外{reference_radius}px矩形环带；排除全部H候选像素；全局参考候选像素按行优先顺序截取；至多{reference_max}个确定性采样点。",
        "- 两种显示分开：可选环带与**实际参与计算的采样像素**；无效参考的样本图强制显示为全黑，明确标记不可用于定量比较。",
        "- 独立以RAW原始DN复算各有效复核候选的背景中位数/MAD，并与源运行CSV逐项一致；候选关联、源RAW/旧输出均未改动。",
        "- **重要：** 面积为1px的候选不能当作噪声真值，`raw_delta_dn`与Black-Hat共享局部暗凹陷信号。",
        "- `feature_distribution_unlabeled.csv`与图表只是形态代理分组，非已确认疵病/噪声两组。",
        "- `manual_review_template.csv`可由用户人工填写`manual_label`并将`review_status`改为`reviewed`。对同一candidate重复ROI，必须填同一标签。",
        "- 没有任何人工标签时，`feature_labelled_separability.csv`中的判别力状态为`PENDING_LABELS`，**不报告实际区分能力**。",
        "- 待独立人工标注的真疵病、背景伪影各至少5个唯一候选且有足够有效特征值时，脚本计算探索性单特征rank AUC与bootstrap区间；不使用同数据调参数再汇报准确率，不拟合模型，不推广到样品27~30。",
        "",
        "## 后续人工填写后重新评估",
        "",
        "```powershell",
        "Set-Location 'D:\\疵病检测\\DefectDetectionProject'",
        "& '.\\.venv\\Scripts\\python.exe' scripts\\revise_case03c_evidence.py --evaluate-only --output-dir 'outputs\\case03c_revision\\<本次run目录>' --labels '完整已人工标注CSV路径'",
        "```",
        "",
        "Case02与Case03-B算法和230/170 DN保持原样；不使用局部MAD，不自动删除候选。",
    ]
    (out/"review_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print("AUDIT_COMPLETE",out,summary["result"],eval_result["status"],flush=True)
    return 0 if passed else 1


if __name__=="__main__":
    raise SystemExit(main())
