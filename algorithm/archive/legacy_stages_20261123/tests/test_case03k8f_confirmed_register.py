"""K8F unit guard tests for user-approved vs frozen J5 review register."""
from types import SimpleNamespace
import numpy as np
from scripts.run_case03k8f_approved_supplements_ledger import (
 APPROVALS,baseline_record,newly_approved_record,GRADE,PITCH)

def test_only_two_groups_explicitly_approved():
    assert set(APPROVALS)=={"K8E_F2_B2_G006","K8E_F2_B2_G009"}
    assert APPROVALS["K8E_F2_B2_G006"]["expected_member_ids"]=={626,658}
    assert APPROVALS["K8E_F2_B2_G009"]["expected_member_ids"]=={1148,1161,1186}
    assert sum(s["expected_area"] for s in APPROVALS.values())==718

def test_unreviewed_frozen_J5_stays_unconfirmed():
    obj=SimpleNamespace(global_defect_id="DEFECT_00022",
      center_x_global=100.,center_y_global=200.,
      source_bbox_x_global=99,source_bbox_y_global=197,
      source_bbox_width_px=5,source_bbox_height_px=7,
      source_area_px2=40,source_max_feret_px=8.4,grade="MEDIUM")
    out=baseline_record(2,obj)
    assert out["source_J5_global_defect_id"]=="DEFECT_00022"
    assert out["visual_defect_confirmed_by_user"] is False
    assert out["review_state"]=="EXISTING_J5_CANDIDATE_UNREVIEWED"
    assert out["area_detector_px2"]==40
    assert out["size_grade"]=="MEDIUM"
    assert out["regulatory_acceptance_decision"]==""
    assert out["source_masks_untouched"] is True

def test_approved_contour_has_source_ids_and_no_J5_id():
    item={
      "source_K8E_id":"K8E_F2_B2_G009",
      "source_selected":{1148,1161},"source_embedded":{1186},
      "bbox_global_xyxy_exclusive":[30,40,70,80],
      "center_global_x":50.1,"center_global_y":63.2,
      "area_px2":370,"length_px":23.4094,
      "area_detector_um2":370*PITCH**2,
      "length_detector_um":23.4094*PITCH,
      "grade":"LARGE"}
    rec=newly_approved_record(2,item)
    assert rec["source_J5_global_defect_id"]==""
    assert rec["supplement_K8E_group_id"]=="K8E_F2_B2_G009"
    assert rec["source_B_connected_components"]=="1148;1161"
    assert rec["source_B_embedded_components"]=="1186"
    assert rec["area_detector_px2"]==370
    assert rec["visual_defect_confirmed_by_user"] is True
    assert rec["size_grade"]=="LARGE"
    assert rec["physical_object_plane_size_calibrated"] is False

def test_grading_threshold_source_unchanged():
    assert GRADE.large_area_min_px2==250
    assert GRADE.medium_area_min_px2==40
    assert GRADE.large_length_min_px==45
    assert PITCH==3.2

def test_supplement_geometry_doesnt_make_physical_size_claim():
    item={
      "source_K8E_id":"K8E_F2_B2_G006",
      "source_selected":{626},"source_embedded":{658},
      "bbox_global_xyxy_exclusive":[100,100,120,120],
      "center_global_x":110.,"center_global_y":110.,
      "area_px2":348,"length_px":23.601,
      "area_detector_um2":348*PITCH**2,
      "length_detector_um":23.601*PITCH,"grade":"LARGE"
    }
    rec=newly_approved_record(2,item)
    assert rec["area_detector_image_um2"]==348*3.2**2
    assert rec["max_length_detector_image_um"]==round(23.601*3.2,3)
    assert rec["physical_object_plane_size_calibrated"] is False
