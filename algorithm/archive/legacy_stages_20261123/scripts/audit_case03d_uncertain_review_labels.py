"""Read-only audit of user-exported 100 uncertain-candidate labels and backup.

Protect original annotations. Distinguish *selected H candidate* from a different
visible defect elsewhere in the same 160x160 RAW crop. Do not train/re-tune the
classifier using ROI-level positives assigned to wrong component IDs.

Saved materials are diagnostic copies and audit analyses only.
"""
from __future__ import annotations
import hashlib,json,sys
from collections import Counter
from pathlib import Path
import cv2,numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

DOWNLOADS=Path(r"C:\Users\lixia\Downloads")
CSV=DOWNLOADS/"case03d_uncertain_review_batch01.csv"
JSON=DOWNLOADS/"case03d_uncertain_review_backup.json"
RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
ORIGINAL=RUN/"uncertain_manual_review_batch01"
OUTPUT=ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200"
FEATURE=RUN/"candidate_decisions_full.csv"
MANIFEST=ORIGINAL/"review_batch_100_manifest.csv"
OLD=ROOT/"outputs/case03d/run_20261009_190000/manual_label_revision_after_review045/strict_corrected_labels.csv"

# Positive label appears to refer to another RAW feature / another connected
# H object in the crop, not the selected red-crosshair component.
POSITIVE_SCOPE_CONFLICT={
 "H_sample26_0402953",
 "H_sample26_0449491",
 "H_sample26_0377872",
 "H_sample26_0386652",
 "H_sample26_0410470",
}
# Negative is about currently selected H object, but note explicitly says
# that a *different nearby location* contains a visible defect.
NEGATIVE_NEARBY_DEFECT={
 "H_sample26_0452019",
 "H_sample26_0409762",
 "H_sample26_0448781",
 "H_sample26_0452065",
 "H_sample26_0400019",
}


def md_table(frame:pd.DataFrame)->str:
    """Small Markdown table without optional third-party tabulate package."""
    names=list(frame.columns)
    def safe(value):
        return str(value).replace("|",r"\|").replace("\n"," ")
    rows=["| "+" | ".join(map(safe,names))+" |",
          "| "+" | ".join(["---"]*len(names))+" |"]
    for row in frame.itertuples(index=False,name=None):
        rows.append("| "+" | ".join(map(safe,row))+" |")
    return "\n".join(rows)


def montage(items:pd.DataFrame,name:str,width:int=500,columns:int=4)->None:
    if len(items)==0:return
    dimheight=260
    header_h=46
    pitchx=width+12
    pitchy=dimheight+header_h+12
    nrows=(len(items)+columns-1)//columns
    sheet=np.full((nrows*pitchy+40,columns*pitchx,3),246,np.uint8)
    for idx,row in enumerate(items.itertuples(index=False)):
        p=ORIGINAL/row.source_image
        data=np.fromfile(str(p),dtype=np.uint8)
        image=cv2.imdecode(data,cv2.IMREAD_COLOR)
        if image is None:raise IOError(p)
        scale=min(width/image.shape[1],dimheight/image.shape[0])
        display=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
        x=idx%columns*pitchx
        y=idx//columns*pitchy
        # UTF-8 annotation is represented by candidate ID and group here;
        # detailed Chinese user notes remain in audit CSV and README.
        label=f"{idx+1:02d} {row.candidate_id} / {row.manual_label}"
        second=f"{row.selection_group} / {row.scope_audit_status}"
        cv2.putText(sheet,label[:72],(x+5,y+16),
                    cv2.FONT_HERSHEY_SIMPLEX,.42,(20,35,48),1,cv2.LINE_AA)
        cv2.putText(sheet,second[:70],(x+5,y+35),
                    cv2.FONT_HERSHEY_SIMPLEX,.34,(80,65,58),1,cv2.LINE_AA)
        sheet[y+header_h:y+header_h+display.shape[0],
              x:x+display.shape[1]]=display
    ok,output=cv2.imencode(".jpg",sheet,[cv2.IMWRITE_JPEG_QUALITY,85])
    if not ok:raise IOError(name)
    (OUTPUT/name).write_bytes(output.tobytes())


def hashfile(p):
    sha=hashlib.sha256()
    with p.open("rb") as handle:
        while chunk:=handle.read(1024*1024):
            sha.update(chunk)
    stat=p.stat()
    return {"path":str(p),"size_bytes":stat.st_size,
            "modified_ns":stat.st_mtime_ns,"sha256":sha.hexdigest()}


def main():
    # Recover only from a previously incomplete run; never overwrite an
    # established audit or any user-owned input.
    if (OUTPUT/"audit_report.md").exists():
        raise FileExistsError("completed audit run already exists")
    OUTPUT.mkdir(parents=True,exist_ok=True)
    tracked=[CSV,JSON,MANIFEST,FEATURE,OLD]
    before=[hashfile(p) for p in tracked]
    u=pd.read_csv(CSV,encoding="utf-8-sig",dtype=str,keep_default_na=False)
    backup=json.loads(JSON.read_text(encoding="utf-8-sig"))
    if backup.get("schema")!=1 or backup.get("source")!="case03d_r2_uncertain_batch01":
        raise ValueError("Unexpected JSON backup schema/source")
    j=pd.DataFrame(backup["marks"]).fillna("")
    cols=["candidate_id","manual_label","review_status","source_case",
          "selection_group","note","source_image"]
    if len(u)!=100 or len(j)!=100 or set(u.columns)!=set(cols):
        raise ValueError("Expected exactly 100 labeled cases in both inputs")
    for data in (u,j):
        if data["candidate_id"].duplicated().any() or data[cols].isna().any().any():
            raise ValueError("duplicate or missing candidate IDs")
        if not data["review_status"].eq("reviewed").all():
            raise ValueError("some records are unreviewed")
        if not data["source_case"].eq("case03d_r2_sample26_uncertain").all():
            raise ValueError("wrong source_case")
    assert len(set(u["candidate_id"]))==100
    assert u.sort_values("candidate_id").reset_index(drop=True)[cols].equals(
        j.sort_values("candidate_id").reset_index(drop=True)[cols]
    ),"JSON and CSV differ"
    allowed={
        "confirmed_dark_spot","confirmed_fine_line",
        "background_artifact","uncertain"
    }
    if set(u["manual_label"])-allowed:raise ValueError("unrecognized label")
    if set(u["selection_group"])!={"micro_high_response","interior_spotlike",
        "elongated_line_like","band_transition_context","other_uncertain"}:
        raise ValueError("wrong strata")
    if not u["selection_group"].value_counts().eq(20).all():
        raise ValueError("not 20 per stratum")
    if set(u.loc[u["note"].ne(""),"candidate_id"])!=(
        POSITIVE_SCOPE_CONFLICT|NEGATIVE_NEARBY_DEFECT
    ):
        raise AssertionError("Unexpected set of Chinese notes; manual review needed")
    raw_manifest=pd.read_csv(MANIFEST,dtype=str,keep_default_na=False)
    merged=u.merge(raw_manifest,how="left",left_on="candidate_id",
                   right_on="candidate_id",validate="one_to_one")
    if len(merged)!=100 or merged["review_group"].eq("").any() or \
       not merged["selection_group"].eq(merged["review_group"]).all() or \
       not merged["source_image"].eq(merged["image_rel"]).all():
        raise AssertionError("manual annotations do not match all 100 original exported image IDs")
    feature_cols=[
        "candidate_id","triage_status","area_px","peak_response_dn",
        "bbox_x","bbox_y","bbox_w","bbox_h",
        "centroid_x","centroid_y","near_band_transition",
        "raw_reference_valid","raw_delta_dn","linearity_proxy",
        "morphology_hint","decision_reason"
    ]
    f=pd.read_csv(FEATURE,usecols=feature_cols,dtype={"candidate_id":str},
                  low_memory=False)
    if f["candidate_id"].duplicated().any():raise AssertionError("source feature ID duplication")
    with_features=u.merge(f,how="left",on="candidate_id",validate="one_to_one")
    if with_features["triage_status"].isna().any() or not \
       with_features["triage_status"].eq("uncertain_review").all():
        raise AssertionError("one or more labels not from uncertain candidate")
    prior=pd.read_csv(OLD,dtype=str,keep_default_na=False)
    if set(prior["candidate_id"])&set(u["candidate_id"]):
        raise AssertionError("repeat of previously reviewed IDs was not expected")
    if not all((ORIGINAL/x).is_file() for x in u["source_image"]):
        raise FileNotFoundError("Missing one or more original ROI image files")
    backup_notes=backup.get("noteCache",{})
    if set(backup_notes)!=set(u["candidate_id"]):
        raise AssertionError("noteCache does not cover all 100 annotated candidates")
    diffnotes=[
        x for x in u.to_dict("records")
        if backup_notes[x["candidate_id"]]!=x["note"]
    ]
    if diffnotes:raise AssertionError(f"noteCache disagrees with human export: {len(diffnotes)}")

    status=[]
    for r in with_features.to_dict("records"):
        cid=r["candidate_id"]
        if cid in POSITIVE_SCOPE_CONFLICT:
            state="positive_ROI_anomaly_not_selected_H"
            train_action="EXCLUDE_POSITIVE_TARGET_ID_PENDING_RETARGET"
        elif cid in NEGATIVE_NEARBY_DEFECT:
            state="selected_H_negative_but_other_ROI_anomaly"
            train_action="KEEP_NEGATIVE_PROVISIONALLY_REVIEW_OTHER_ROI"
        elif r["manual_label"]=="uncertain":
            state="human_uncertain"
            train_action="EXCLUDE_UNRESOLVED"
        else:
            state="selected_H_label_by_UI_assumed_not_independent_pixel_truth"
            train_action="ELIGIBLE_AFTER_TARGET_SCOPE_QA"
        status.append((state,train_action))
    with_features["scope_audit_status"]=[r[0] for r in status]
    with_features["recommended_training_use"]=[r[1] for r in status]
    with_features.to_csv(OUTPUT/"human_review_joined_100.csv",index=False,encoding="utf-8-sig")
    exception=with_features[with_features["note"].ne("")].copy()
    exception.to_csv(OUTPUT/"ROI_annotation_scope_exceptions_10.csv",
                      index=False,encoding="utf-8-sig")
    positives=with_features[with_features["manual_label"].isin(
        ("confirmed_dark_spot","confirmed_fine_line"))]
    positives.to_csv(OUTPUT/"human_positive_ROI_screens_19.csv",
                     index=False,encoding="utf-8-sig")
    montage(positives,"positive_19_context_montage.jpg")
    montage(exception,"10_scope_exception_montage.jpg",columns=2)

    label_counts=u["manual_label"].value_counts()
    pivot=pd.crosstab(u["selection_group"],u["manual_label"])
    pivot.to_csv(OUTPUT/"by_stratum_confusion_descriptive.csv",encoding="utf-8-sig")
    feats=with_features.groupby("manual_label")[["area_px","peak_response_dn"]].median()
    medians=feats.round(2).to_dict(orient="index")
    summary={
        "status":"DATA_AUDIT_PASS_BUT_SCOPE_CORRECTION_REQUIRED",
        "manual_export_rows":len(u),"backup_mark_rows":len(j),
        "csv_json_exactly_same_seven_export_fields":True,
        "strata_20_each":True,
        "reviewed_all_100":True,"duplicate_IDs":0,
        "source_decision_status":"uncertain_review_for_all",
        "previous_review_overlap":0,
        "label_counts":{key:int(label_counts.get(key,0)) for key in [
            "background_artifact","confirmed_dark_spot",
            "confirmed_fine_line","uncertain"]},
        "strata_count_table":pivot.astype(int).to_dict(orient="index"),
        "positive_label_total":len(positives),
        "positive_label_other_ROI_in_explicit_note":len(POSITIVE_SCOPE_CONFLICT),
        "negative_labels_with_explicit_nearby_defect_note":len(NEGATIVE_NEARBY_DEFECT),
        "positive_labels_without_explicit_scope_mismatch_note":
          len(positives)-len(POSITIVE_SCOPE_CONFLICT),
        "unresolved_human_label":int(label_counts.get("uncertain",0)),
        "safe_training_claim":"NOT_READY; notes mention different ROI objects",
        "median_area_peak_by_label":medians,
        "positive_scope_conflicts":sorted(POSITIVE_SCOPE_CONFLICT),
        "negative_nearby_anomaly_notes":sorted(NEGATIVE_NEARBY_DEFECT),
        "noteCache_exactly_matches_CSV_notes":True,
        "normal_positive_without_notes_must_still_be_considered_provisional":True,
        "stratified_targeted_not_random_sample":True,
        "no_accuracy_recall_precision_claim":True,
        "no_training_or_parameter_modifications":True
    }
    (OUTPUT/"audit_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),
        encoding="utf-8"
    )
    notes=exception[["candidate_id","manual_label","selection_group",
                     "note","scope_audit_status"]].copy()
    notes.columns=["候选ID","原始标签","组别","人工备注","核查范围"]
    report="\n".join([
        "# Case03-D 人工复核100例：导出一致性与目标对应审计",
        "",
        "## 结论",
        "",
        "- CSV、JSON均含100条已reviewed记录；所有候选ID、人工标签、标注备注、图像路径及5组分层相同；没有重复。",
        "- **标签：80个background_artifact，16个confirmed_dark_spot，3个confirmed_fine_line，1个uncertain。**",
        "- 仅针对当前Case03-D-R2 **6685个uncertain_review候选**抽取5类各20个进行主动复核，"
        "数据不是随机或独立验证集，不可据此声称自动识别精度、真正误检率或全图召回率。",
        "- **关键数据质量问题**：人工备注中的局部RAW其他位置异常可能并不对应绿色选中候选。"
        "用户可能在正确地指出另一处真正疵病，但候选ID不一定是它。"
        "因此当前不能把19个正标签不加区分直接作为独立正样本训练。",
        f"- 19个正标签中**{len(POSITIVE_SCOPE_CONFLICT)}条**有明确选中ID与备注位置不对应的风险，"
        f"其余**{len(positives)-len(POSITIVE_SCOPE_CONFLICT)}条**没有明确这种备注，但并非已做精确目标对应复核。",
        f"- 80个负标签中**{len(NEGATIVE_NEARBY_DEFECT)}条**注明了RAW其他位置存在异常，"
        "不能把该整个160px ROI当作纯负图像；所选连通域本身可能仍为负。",
        "",
        "## 五类采样分组人工标签数",
        "",
        md_table(pivot.rename(columns={
            "background_artifact":"背景伪影",
            "confirmed_dark_spot":"暗点异常",
            "confirmed_fine_line":"细线异常",
            "uncertain":"无法确定"
        }).reset_index()),
        "",
        "## 10条涉及其他ROI位置的人工备注（原文保留）",
        "",
        md_table(notes),
        "",
        "## 下一步建议",
        "",
        "1. **先完成目标对应关系，而不是直接训练分类器**。对5条明确的正样本位置不匹配，应在RAW上点击真正异常的位置，得到原始RAW像素坐标；与Case03-B原H连通域及Case03-D分类结果匹配。没有匹配则需要分析阈值/连通域生成漏检。",
        "2. 对5条“绿色当前候选负、但同一图存在另一处疵病”的备注，"
        "保留当前候选的负判断（暂定），把旁边真实异常单独定位记录，不得把整个ROI作为负训练片。",
        "3. 其他14个无明确备注冲突的正标签也应抽样检查**绿色选中是否确实覆盖被判为疵病的结构**；"
        "单像素的真实疵病需要更强的证据，不能因为RAW同一视野存在大暗点就将旁边1px判为真实目标。",
        "4. 建立独立样品验证，含未进入现有H阈值掩膜的弱小缺陷、细划痕、不同黑带背景。"
        "当前的19/100是有目的抽样中包含异常的比例，不是检测召回率或准确率。",
        "5. 本次数据审计**不修改**Case03-D判别规则、已经输出的139/6685/81219候选结果和任何原标注；"
        "只提供一份可审计的数据映射表与待确认范围。",
        "",
        "## 产物",
        "",
        "- human_review_joined_100.csv：100个原标签与候选原特征的完整对应、潜在ID范围风险。",
        "- ROI_annotation_scope_exceptions_10.csv：10条带备注的空间范围问题。",
        "- human_positive_ROI_screens_19.csv：19个正标签及其对应候选特征（其中5条需重新定位）。",
        "- positive_19_context_montage.jpg、10_scope_exception_montage.jpg：辅助复核图册，"
        "显示原RAW、all S/H和当前选中的真实连通域，暂不重新指认真实目标。",
        "- audit_summary.json、source_manifest.json：统计、源文件哈希及保护记录。",
    ])
    (OUTPUT/"audit_report.md").write_text(report+"\n",encoding="utf-8")
    after=[hashfile(p) for p in tracked]
    if before!=after:
        raise AssertionError("Audited originals changed during work")
    (OUTPUT/"source_manifest.json").write_text(
        json.dumps({"before":before,"after":after,"unchanged":True},
                   ensure_ascii=False,indent=2),encoding="utf-8"
    )
    print("CASE03D_LABEL_ANALYSIS_PATH",OUTPUT)
    print("CASE03D_LABEL_ANALYSIS",json.dumps(summary,ensure_ascii=True))
    print("CASE03D_ANALYSIS_FILES",len(list(OUTPUT.iterdir())))


if __name__=="__main__":
    main()
