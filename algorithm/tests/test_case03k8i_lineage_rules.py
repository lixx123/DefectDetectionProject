"""Case03-K8I routing and candidate preservation regression."""
import pytest
from src.detection.case03k8i_lineage_rules import (
 parse_ids,source_key,j5_layer,b_layer,LAYERS,validate_lineage,audit_layer_counts)

def test_parse_group_members_from_varied_csv_types():
    assert parse_ids("1148;1161;1186")==(1148,1161,1186)
    assert parse_ids("658.0")== (658,)
    assert parse_ids(float("nan"))==()
    assert parse_ids("")==()
    assert parse_ids("626;626;658")== (626,658)

def test_complete_stage_specific_ids():
    assert source_key("J5",1,0,"DEFECT_01234")=="J5:F1:DEFECT_01234"
    assert source_key("K8B",2,2,1148)=="B:F2:B02:C0001148"
    with pytest.raises(ValueError):source_key("OTHER",1,0,9)

def test_j5_work_and_outside_remain_visible():
    assert j5_layer(2,"LARGE")=="J5_WORK_MEDLARGE"
    assert j5_layer(2,"SMALL")=="J5_WORK_SMALL"
    for x in (0,1,3):assert j5_layer(x,"MEDIUM")=="J5_OUTSIDE_WORK"

def test_micro_suggestion_is_routed_not_deleted():
    assert b_layer("MICRO_HIDE_SUGGESTION",True,"SMALL",[],set())=="B_NOVEL_MICRO"
    assert "B_NOVEL_MICRO" in LAYERS

def test_old_fixed_h_is_reference_not_assumed_j5():
    assert b_layer("EXISTING_FIXED_H",False,"LARGE",[],set())=="B_FIXED_H_REFERENCE"
    assert "B_FIXED_H_REFERENCE" in LAYERS

def test_approved_specific_group_but_only_single_membership():
    confirmed={"K8E_F2_B2_G006","K8E_F2_B2_G009"}
    assert b_layer("PROMISING_DARK_REVIEW",True,"LARGE",
                   ["K8E_F2_B2_G009"],confirmed)=="B_K8E_GROUP_CONFIRMED"
    assert b_layer("PROMISING_DARK_REVIEW",True,"LARGE",
                   ["K8E_F1_B2_G001"],confirmed)=="B_K8E_GROUP_PENDING"
    assert b_layer("PROMISING_DARK_REVIEW",True,"LARGE",
                   ["K8E_F2_B2_G006","K8E_F2_B2_G009"],confirmed)=="B_K8E_MULTIGROUP_CONFLICT"

def test_new_large_b_candidate_displayed_even_without_outer():
    assert b_layer("UNCERTAIN_REVIEW",True,"LARGE",[],set())=="B_NOVEL_MEDLARGE"
    assert b_layer("SMALL_REVIEW",True,"SMALL",[],set())=="B_NOVEL_SMALL"

def test_duplicate_source_lineage_blocks_complete_result():
    a={"candidate_source_uid":"A","primary_visibility_layer":"J5_WORK_SMALL",
       "size_grade":"SMALL","source_area_px2":1,
       "original_source_pixels_preserved":True,"stage":"J5",
       "is_user_confirmed":False}
    with pytest.raises(AssertionError,match="duplicate"):validate_lineage([a,a])

def test_unrouted_or_unapproved_candidate_blocks_result():
    a={"candidate_source_uid":"A","primary_visibility_layer":"HIDDEN_WITHOUT_REASON",
       "size_grade":"SMALL","source_area_px2":1,
       "original_source_pixels_preserved":True,"stage":"J5",
       "is_user_confirmed":False}
    with pytest.raises(AssertionError,match="unrouted"):validate_lineage([a])
    a["primary_visibility_layer"]="J5_WORK_SMALL"
    a["is_user_confirmed"]=True
    with pytest.raises(AssertionError,match="no user confirmed"):validate_lineage([a])

def test_exact_layer_count_invariant():
    items=[{"primary_visibility_layer":"J5_WORK_SMALL"},
           {"primary_visibility_layer":"B_NOVEL_MICRO"},
           {"primary_visibility_layer":"J5_WORK_SMALL"}]
    result=audit_layer_counts(items)
    assert sum(result.values())==3
    assert result["J5_WORK_SMALL"]==2 and result["B_NOVEL_MICRO"]==1
