"""Second user CSV regression: exact annotations and box majority never conflated."""
import csv
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
V2=ROOT/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2"

def records(name):
    with (V2/name).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def test_new_csv_20_annotations_and_56_explicitly_no_issue():
    summary=json.loads((V2/"summary.json").read_text(encoding="utf-8"))
    box_summary=json.loads((V2/"box_analysis_status_v2.json").read_text(encoding="utf-8"))
    ann=records("pixel_retarget_associations.csv")
    assert len(ann)==20
    assert summary["unique_review_ids"]==8
    assert summary["missing_review_056"] is True
    assert box_summary["review_056_user_confirmed"]=="NO_ANOMALY_NEEDS_FOLLOWUP"
    assert not box_summary["review_056_as_specific_negative_candidate"]
    assert not any(r["review_id"]=="review_056" for r in ann)

def test_boxes_current_S_and_H_equal_actual_case03b():
    boxes=records("box_retarget_diagnostics_v2.csv")
    assert len(boxes)==7
    assert Counter(r["review_id"] for r in boxes)=={
        "review_031":1,"review_046":1,"review_018":1,"review_019":1,"review_024":3
    }
    assert all(int(r["H170_230_count"])<=int(r["blackhat_n_above170"]) for r in boxes)
    assert all(int(r["S230_count"])==int(r["blackhat_n_above230"]) for r in boxes)
    missed={r["review_id"]:r for r in boxes if r["review_id"] in ["review_031","review_046"]}
    assert int(missed["review_031"]["H170_230_count"])==0
    assert int(missed["review_031"]["S230_count"])==0
    assert int(missed["review_031"]["blackhat_max_dn"])==216
    assert int(missed["review_046"]["H170_230_count"])==0
    assert int(missed["review_046"]["S230_count"])==0
    assert int(missed["review_046"]["blackhat_max_dn"])==194

def test_box_associations_do_not_claim_exact_truth():
    proposals=records("box_candidate_association_audit_v2.csv")
    selected={x["candidate_id"] for x in proposals if x["candidate_assignment"]=="PROVISIONAL_BOX_DOMINANT"}
    assert selected=={
      "H_sample26_0444566",
      "H_sample26_0457655",
      "H_sample26_0411912",
      "H_sample26_0417866"
    }
    labels=records("candidate_labels_sensitivity_plus_boxes_v2.csv")
    assert len(labels)==57
    positives=[x for x in labels if x["manual_label"]=="confirmed_dark_spot"]
    negatives=[x for x in labels if x["manual_label"]=="background_artifact"]
    assert len(positives)==18
    assert len(negatives)==39
    assert all(x["provenance"]=="PROVISIONAL_BOX_DOMINANT__REVIEW_REQUIRED"
               for x in positives if x["candidate_id"] in selected)
    assert all("BOX_REGION_NOT_EXACT_H_GT"==x["human_confirmation_level"]
               for x in proposals if x["candidate_id"])

def test_024_three_separate_boxes_and_one_exact_click_candidate():
    audits=[x for x in records("box_candidate_association_audit_v2.csv") if x["review_id"]=="review_024"]
    assert len(audits)==3
    assert {a["candidate_id"] for a in audits}=={
      "H_sample26_0411912","H_sample26_0411534","H_sample26_0417866"
    }
    assert any(a["candidate_assignment"]=="EXACT_CLICK_ALREADY_PRESENT" for a in audits)

def test_provisional_AUC_not_overstated():
    auc=records("feature_auc_sensitivity_plus_boxes_v2.csv")
    assert len(auc)==12
    assert all(x["status"]=="EXPLORATORY_ONLY" for x in auc)
    assert all("selected sample" in x["limitations"] for x in auc)
