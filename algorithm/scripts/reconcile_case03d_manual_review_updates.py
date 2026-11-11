"""Reconcile confirmed Case03-D labels, without rewriting previous runs."""
import csv,json,sys
from pathlib import Path
from collections import Counter

import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.detection.candidate_priority import evaluate_review_budget

RUN=ROOT/"outputs/case03d/run_20261009_190000"
LABELS=ROOT/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2"
DEST=RUN/"manual_label_revision_after_review045"

def load(path):
    with path.open("r",newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def export(path,rows):
    columns=list(dict.fromkeys(k for x in rows for k in x))
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader();w.writerows(rows)

def count_group(df,labels):
    index=df.set_index("candidate_id")
    out={}
    for typ,value in [("positive","confirmed_dark_spot"),("negative","background_artifact")]:
        sub=index.loc[[k for k,v in labels.items() if v==value]]
        out[typ+"_total"]=len(sub)
        for tier in ["A_first_review","B_second_review","C_later_review"]:
            out[typ+"_"+tier]=int(sub["review_tier"].eq(tier).sum())
    return out

def main():
    if DEST.exists():raise FileExistsError(DEST)
    changes=load(RUN/"case03d_incremental_human_reviews.csv")
    update={r["candidate_id"]:r for r in changes}
    expected={"H_sample26_0428940","H_sample26_0425919","H_sample26_0379819"}
    if set(update)!=expected or len(changes)!=3:raise ValueError("unexpected user update set")
    if any(r["manual_label"]!="background_artifact" or r["review_status"]!="reviewed" for r in changes):
        raise ValueError("unreviewed/unsupported label")
    ranking=pd.read_csv(RUN/"review_order.csv",dtype={"candidate_id":str})
    rank=ranking.set_index("candidate_id")
    for cid in expected:
        if cid not in rank.index:raise KeyError(cid)
    DEST.mkdir(parents=True)
    cohorts={}
    for cohort,src in [("strict",LABELS/"candidate_labels_verified.csv"),
                       ("provisional",LABELS/"candidate_labels_sensitivity_plus_boxes_v2.csv")]:
        original=load(src)
        original_by_id={r["candidate_id"]:r for r in original}
        labels={cid:r["manual_label"] for cid,r in original_by_id.items()}
        if labels.get("H_sample26_0379819")!="confirmed_dark_spot":
            raise AssertionError("unexpected original positive 045")
        if any(x in labels for x in expected-{"H_sample26_0379819"}):
            raise AssertionError("unexpected previous label for rank2/5")
        ledger=[]
        for cid,confirm in update.items():
            old=labels.get(cid,"unlabeled")
            labels[cid]="background_artifact"
            ledger.append({"candidate_id":cid,"prior_label":old,
                           "corrected_label":"background_artifact",
                           "priority_rank_unchanged":int(rank.loc[cid,"priority_rank"]),
                           "user_review_note":confirm["review_note"],
                           "source_figure":confirm["source_figure"]})
        rows=[]
        for cid,label in sorted(labels.items()):
            orig=original_by_id.get(cid)
            rows.append({"candidate_id":cid,"manual_label":label,"review_status":"reviewed",
                         "provenance":("manual_update_review045" if cid=="H_sample26_0379819"
                                        else "manual_update_A_rank_negative" if cid in expected
                                        else orig["provenance"]),
                         "previous_label":orig["manual_label"] if orig else "unlabeled",
                         "priority_rank_unchanged":int(rank.loc[cid,"priority_rank"])})
        export(DEST/(cohort+"_corrected_labels.csv"),rows)
        export(DEST/(cohort+"_change_log.csv"),ledger)
        details,budget=evaluate_review_budget(ranking,labels,budgets=(100,500,1000,5000))
        export(DEST/(cohort+"_labeled_review_ranks.csv"),details)
        export(DEST/(cohort+"_budget_statistics.csv"),budget)
        cohorts[cohort]=count_group(ranking,labels)
    assert cohorts["strict"]=={
      "positive_total":13,"positive_A_first_review":12,
      "positive_B_second_review":1,"positive_C_later_review":0,
      "negative_total":42,"negative_A_first_review":3,
      "negative_B_second_review":7,"negative_C_later_review":32}
    assert cohorts["provisional"]["positive_total"]==17
    assert cohorts["provisional"]["negative_total"]==42
    summary={"corrected_review_045":"H_sample26_0379819 -> background_artifact",
             "confirmed_background_A_ranks":[2,5],"strict":cohorts["strict"],
             "provisional":cohorts["provisional"],"main_priority_rank_changed":False,
             "original_source_files_overwritten":False,
             "limits":"selected-label ranking analysis only; not full-image detection performance"}
    (DEST/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    (DEST/"README.md").write_text(
      "# Case03-D新增人工标签更正\n\n"
      "review_045改判背景伪影，A组第2、第5也已人工确认背景伪影。\n"
      "旧评分、排名、原人工Excel和历史分析均未覆盖。\n"
      "保守组13正42负：12正A、1正B、0正C；3负A、7负B、32负C。\n"
      "暂定框选组17正42负，保留4条框选对应关系的不确定性。\n"
      "这些是人工选择样本的描述性统计，不能外推整图召回率或误检率。\n",encoding="utf-8")
    print("RESULT_DIRECTORY",DEST)
    print("SUMMARY",json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
