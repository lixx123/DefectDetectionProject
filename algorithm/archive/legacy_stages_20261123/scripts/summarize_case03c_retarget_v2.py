"""Human ROI box-dominant association sensitivity only; NO new exact truth.

The source annotation and masks are not modified. This script reads already
audited global 8-connected H overlaps. Provisional H membership is retained
separately from exact click membership and cannot enter production evaluation.
review_056 status is human-confirmed no issue, NOT a candidate-level negative.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from src.detection.feature_discrimination import read_csv_rows, exploratory_auc

RUN=ROOT/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2"
CASE=ROOT/"outputs/case03c/run_20261008_174000"
EXPECTED_BOX_COUNT=7


def write_csv(path,rows):
    if not rows:return
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        cols=list(dict.fromkeys(k for row in rows for k in row))
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)


def main():
    allbox=read_csv_rows(RUN/"box_retarget_diagnostics_v2.csv")
    components=read_csv_rows(RUN/"box_overlapping_H_components_v2.csv")
    exact=read_csv_rows(RUN/"candidate_labels_verified.csv")
    hfeatures=read_csv_rows(CASE/"hysteresis_candidate_features.csv")
    assert len(allbox)==EXPECTED_BOX_COUNT
    assert len(exact)==53
    groups=defaultdict(list)
    for comp in components:
        groups[comp["annotation_id"]].append(comp)
    exact_map={r["candidate_id"]:r["manual_label"] for r in exact}
    negative={cid for cid,lab in exact_map.items() if lab=="background_artifact"}
    candidates=[]
    audit=[]
    for box in allbox:
        c=groups.get(box["annotation_id"],[])
        n=int(box["H170_230_count"])
        best=max(c,key=lambda x:int(x["H_pixels_in_human_rectangle"])) if c else None
        if not best:
            audit.append({"review_id":box["review_id"],"annotation_id":box["annotation_id"],"candidate_id":"",
                          "box_H_pixels":0,"dominant_H_overlap_fraction":0,
                          "candidate_assignment":"BOX_NO_H__MISS_OR_UNDERSEGMENTED",
                          "human_confirmation_level":"ROI_AFFECTED_ONLY"})
            continue
        count=int(best["H_pixels_in_human_rectangle"])
        frac=count/n
        cid=best["component_id"]
        if n>=15 and frac>=0.90:
            category="PROVISIONAL_BOX_DOMINANT"
            assert cid not in negative, f"candidate unexpectedly previously manually negative: {cid}"
            assert cid.startswith("H_sample26_")
            if cid not in exact_map:
                candidates.append(cid)
            else:category="EXACT_CLICK_ALREADY_PRESENT" if exact_map[cid]=="confirmed_dark_spot" else "UNKNOWN"
        else:
            category="MULTIPLE_H_OR_LOW_PIXEL_OVERLAP__NEEDS_MORE_PRECISE_MARKING"
        audit.append({"review_id":box["review_id"],"annotation_id":box["annotation_id"],
                      "candidate_id":cid,"box_H_pixels":n,
                      "dominant_H_pixels_in_box":count,
                      "dominant_H_overlap_fraction":round(frac,5),
                      "distinct_H_components_in_box":len(c),
                      "candidate_assignment":category,
                      "human_confirmation_level":"BOX_REGION_NOT_EXACT_H_GT"})
    candidates=set(candidates)
    assert len(candidates)==4 and len(negative)==39 and not(candidates & set(exact_map))
    write_csv(RUN/"box_candidate_association_audit_v2.csv",audit)
    exploratory={**exact_map}
    for cid in candidates:exploratory[cid]="confirmed_dark_spot"
    augmented=[{"candidate_id":cid,"manual_label":lab,"review_status":"reviewed",
                 "provenance":"PROVISIONAL_BOX_DOMINANT__REVIEW_REQUIRED" if cid in candidates else "PRIOR_EXACT_OR_REVIEWED"}
                for cid,lab in sorted(exploratory.items())]
    write_csv(RUN/"candidate_labels_sensitivity_plus_boxes_v2.csv",augmented)
    results=exploratory_auc(hfeatures,exploratory)
    write_csv(RUN/"feature_auc_sensitivity_plus_boxes_v2.csv",results)
    from pathlib import Path
    summary={
      "exact_click_or_previous_reviewed_positive":14,
      "original_negative":39,
      "provisional_added_positive_by_box_majority":len(candidates),
      "provisional_added_positive_ids":sorted(candidates),
      "sensitivity_positive_total":18,
      "sensitivity_negative_total":39,
      "review_056_user_confirmed":"NO_ISSUE_AS_NEW_ROI",
      "review_056_in_negative_candidate_set":False,
      "claim_limit":"AUC sensitivity only; box dominant != per-pixel lesion GT, user confirmed visual anomaly in ROI not physical filter defect",
      "no_auto_deletion_or_threshold_change":True
    }
    (RUN/"box_candidate_provisional_summary_v2.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("AUDIT",json.dumps(audit,ensure_ascii=False,indent=2),flush=True)
    print("SUMMARY",json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    for feature in ("area_px","seed_area_px","peak_response_dn","raw_delta_dn","background_noise_mad_dn","growth_ratio_px"):
        item=next(r for r in results if r["feature"]==feature)
        print("AUC",feature,item["auc_positive_higher"],item["positive_n"],item["negative_n"])
if __name__=="__main__":main()
