"""Case03-D protected invariants: no candidate deletion and no label leakage."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.detection.candidate_priority import build_priority,evaluate_review_budget
from scripts.run_case03d import load_labels


def _toy():
    return pd.DataFrame({
        "candidate_id":["C","A","B","D","E","F","G","H","I","J"],
        "area_px":[1,1,2,2,3,3,12,1,8,15],
        "peak_response_dn":[231,250,245,250,310,260,400,230,240,460],
        "human_manual_label":["positive","negative","negative","negative",
                             "negative","negative","positive","unknown","unknown","unknown"],
        "raw_reference_valid":[True,False]*5,
    })


def test_toy_every_id_retained_and_one_to_n_rank_with_ties():
    inp=_toy()
    out=build_priority(inp,first_tier_fraction=.2,second_tier_cumulative_fraction=.5)
    assert list(out["candidate_id"])==list(inp["candidate_id"])
    assert set(out["priority_rank"])==set(range(1,len(inp)+1))
    assert out["review_tier"].value_counts().to_dict()=={
        "A_first_review":2,"B_second_review":3,"C_later_review":5
    }
    assert out.set_index("candidate_id").loc["J","priority_rank"]==1
    assert out.set_index("candidate_id").loc["G","priority_rank"]==2
    assert out["review_score"].between(0,1).all()
    assert len(set(out["baseline_peak_only_rank"]))==len(inp)
    assert len(set(out["baseline_area_only_rank"]))==len(inp)


def test_no_label_leakage_even_if_all_labels_reversed():
    inp=_toy()
    ranks=build_priority(inp).drop(columns=["candidate_id"])
    inp["human_manual_label"]=["background"]*len(inp)
    inp["raw_reference_valid"]=[False]*len(inp)
    new=build_priority(inp).drop(columns=["candidate_id"])
    pd.testing.assert_frame_equal(ranks,new)


def test_ranks_invariant_under_input_row_permutation():
    inp=_toy()
    original=build_priority(inp).set_index("candidate_id").sort_index()
    permuted=build_priority(inp.sample(frac=1,random_state=44)).set_index("candidate_id").sort_index()
    pd.testing.assert_frame_equal(original,permuted)


def test_one_pixel_always_ranked_never_dropped_and_ties_average():
    inp=pd.DataFrame({"candidate_id":["z","x","a","b"],
                      "area_px":[1,1,1,1],"peak_response_dn":[230,230,230,230]})
    out=build_priority(inp,first_tier_fraction=.25,second_tier_cumulative_fraction=.5)
    assert len(out)==4
    assert len(set(out["review_score"]))==1
    assert out.set_index("candidate_id").loc["a","priority_rank"]==1
    assert all(out["review_tier"].notna())


def test_reject_invalid_features_duplicate_ids_bad_budgets():
    with pytest.raises(ValueError,match="IDs"):
        build_priority(pd.DataFrame({"candidate_id":["x","x"],
                                     "area_px":[1,2],"peak_response_dn":[230,250]}))
    a=_toy()
    a.loc[0,"peak_response_dn"]=np.nan
    with pytest.raises(ValueError,match="missing|invalid|nonfinite"):
        build_priority(a)
    with pytest.raises(ValueError,match="tier"):
        build_priority(_toy(),first_tier_fraction=.10,
                       second_tier_cumulative_fraction=.05)
    with pytest.raises(ValueError,match="weights"):
        build_priority(_toy(),area_weight=.8,peak_weight=.8)


def test_budget_counts_are_among_labeled_only_and_expose_all_methods():
    inp=_toy()
    ranks=build_priority(inp,first_tier_fraction=.2,
                         second_tier_cumulative_fraction=.5)
    labels={"A":"background_artifact","J":"confirmed_dark_spot",
            "G":"confirmed_dark_spot"}
    detail,summary=evaluate_review_budget(ranks,labels,budgets=(2,4))
    assert len(detail)==3
    assert len(summary)==3*4  # 2/4, ceil10pct=1, ceil1pct=1, and all=10 -> 4 unique budgets
    assert all(x["label_positive_coverage"]<=1 for x in summary)
    assert all(x["warning"].startswith("Coverage of labeled") for x in summary)
    assert all(x["label_positive_in_top_n"]<=2 for x in summary)
    with pytest.raises(ValueError,match="missing"):
        evaluate_review_budget(ranks,{"missing":"confirmed_dark_spot"})


def test_human_labels_from_original_files_strict_and_provisional_distinct():
    root=Path(__file__).resolve().parents[1]
    d=root/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2"
    strict=load_labels(d/"candidate_labels_verified.csv",14,39)
    extra=load_labels(d/"candidate_labels_sensitivity_plus_boxes_v2.csv",18,39)
    assert len(strict)==53
    assert len(extra)==57
    assert set(strict)<=set(extra)
    new=set(extra)-set(strict)
    assert new=={"H_sample26_0411912","H_sample26_0417866",
                 "H_sample26_0444566","H_sample26_0457655"}
    assert all(extra[x]=="confirmed_dark_spot" for x in new)


def test_main_cli_accepts_3d_option():
    import main
    from unittest.mock import patch
    with patch("sys.argv",["main.py","--case","3d","--run-id","dry_run"]), \
         patch("scripts.run_case03d.run_from_main",return_value=0) as runner:
        assert main.main()==0
        runner.assert_called_once_with("dry_run")


def test_full_real_case03d_run_all_88043_candidates_and_no_deleted_one_px():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d/run_20261009_190000"
    src=root/"outputs/case03c/run_20261008_174000/hysteresis_candidate_features.csv"
    full=pd.read_csv(run/"candidate_priority_full.csv",dtype={"candidate_id":str},low_memory=False)
    source=pd.read_csv(src,dtype={"candidate_id":str},low_memory=False)
    assert len(full)==len(source)==88043
    assert set(full["candidate_id"])==set(source["candidate_id"])
    assert (full["candidate_id"].to_numpy()==source["candidate_id"].to_numpy()).all()
    assert full["area_px"].sum()==source["area_px"].sum()==311790
    assert (full["area_px"]==1).sum()==(source["area_px"]==1).sum()==35678
    assert (full["review_tier"]=="C_later_review").sum()==79238
    assert (full["review_tier"]=="B_second_review").sum()==7924
    assert (full["review_tier"]=="A_first_review").sum()==881
    assert set(full["priority_rank"])==set(range(1,len(full)+1))
    assert full["manual_label_strict"].fillna("").ne("").sum()==53
    assert full["manual_label_plus_provisional"].fillna("").ne("").sum()==57


def test_existing_case03d_verified_positives_include_low_queue_spot():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d/run_20261009_190000"
    import json
    stats=json.loads((run/"label_review_summary.json").read_text(encoding="utf-8"))
    assert stats["strict"]["positive_C_later_review"]==1
    assert stats["strict"]["positive_A_first_review"]==12
    assert stats["strict"]["positive_B_second_review"]==1
    label=pd.read_csv(run/"labeled_strict_review.csv")
    weak=label[label["candidate_id"]=="H_sample26_0379819"].iloc[0]
    assert int(weak["primary_rank"])==54778
    assert weak["manual_label"]=="confirmed_dark_spot"


def test_case03d_gallery_real_evidence_and_provisional_status():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d/run_20261009_190000"
    img=run/"figures"
    for name in ("atlas_A_top_ranked.png",
                 "atlas_known_positive_low_priority.png",
                 "atlas_known_negative_high_priority.png",
                 "atlas_provisional_box_matches.png",
                 "priority_map_A_only.png","priority_map_A_and_B.png"):
        assert (img/name).is_file(),name
    selections=pd.read_csv(run/"atlas_selection.csv")
    assert len(selections)==76
    provisional=selections[selections["group"]=="provisional_box_matches"]
    assert len(provisional)==4
    assert (provisional["manual_evidence_status"]=="PROVISIONAL_BOX__NOT_PIXEL_GT").all()


def test_micro_safety_lane_keeps_all_35678_one_pixel_candidates_in_C():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d/run_20261009_190000"
    import json
    summary=json.loads((run/"micro_safety_summary.json").read_text(encoding="utf-8"))
    assert summary["one_pixel_total_count"]==35678
    assert summary["one_pixel_all_in_C"]
    assert summary["micro_review_topN"]==100
    assert summary["known_strict_positive_one_pixel_count"]==0
    assert summary["no_candidate_deletion_or_reranking"]
    full=pd.read_csv(run/"micro_single_pixel_full_audit.csv",low_memory=False)
    top=pd.read_csv(run/"micro_single_pixel_top100.csv")
    assert len(full)==35678
    assert len(top)==100
    assert full["candidate_id"].is_unique
    assert full["area_px"].eq(1).all()
    assert full["review_tier"].eq("C_later_review").all()
    assert full["micro_audit_rank"].tolist()==list(range(1,35678+1))
    assert full["peak_response_dn"].is_monotonic_decreasing
    assert set(top["candidate_id"])==set(full.iloc[:100]["candidate_id"])
    assert (run/"figures/atlas_single_pixel_high_peak_audit.png").exists()
