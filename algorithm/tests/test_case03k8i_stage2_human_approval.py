"""Non-destructive user-approved F1 B02 & B04 darkspot manifest tests."""
from pathlib import Path
import json
import numpy as np,pandas as pd
from config import user_config as C

ROOT=C.OUTPUT_ROOT/"case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1"

def test_two_separate_physical_spots_with_exclusive_source_members():
    o=pd.read_csv(ROOT/"two_user_confirmed_darkspots_no_duplicate_area.csv")
    refs=pd.read_csv(ROOT/"five_B_source_components_to_two_user_confirmed_darkspots.csv")
    assert len(o)==2 and len(refs)==5
    assert set(o.band_id)=={2,4}
    assert set(o.area_exact_union_detector_px2)=={398,297}
    assert o.independent_physical_darkspot_count_for_this_review.sum()==2
    assert int(o.area_exact_union_detector_px2.sum())==695
    assert refs.source_B_connected_component_label.is_unique

def test_b02_record_selects_frozen_K8E_and_does_not_double_count():
    o=pd.read_csv(ROOT/"two_user_confirmed_darkspots_no_duplicate_area.csv").set_index("band_id")
    q=o.loc[2]
    assert q.canonical_old_K8E_group_id=="K8E_F1_B2_G004"
    assert q.crosschecked_new_K8I2_group_id=="K8I2_F1_B02_G0021"
    assert q.connected_B_source_labels=="1787;1902"
    with np.load(q.verified_copy_npz,allow_pickle=False) as z:
        assert int(z["verified_binary_mask"].sum())==398
        assert set(z["source_B_connected_labels"])=={1787,1902}

def test_b04_three_fragments_exact_one_union_not_sum():
    o=pd.read_csv(ROOT/"two_user_confirmed_darkspots_no_duplicate_area.csv").set_index("band_id")
    q=o.loc[4]
    assert q.crosschecked_new_K8I2_group_id=="K8I2_F1_B04_G0096"
    assert q.connected_B_source_labels=="2424;2444;2504"
    with np.load(q.verified_copy_npz,allow_pickle=False) as z:
        assert int(z["verified_binary_mask"].sum())==297
        assert set(z["source_B_connected_labels"])=={2424,2444,2504}

def test_manual_truth_only_two_approved_not_production_or_object_plane():
    a=json.loads((ROOT/"summary.json").read_text(encoding="utf-8"))
    o=pd.read_csv(ROOT/"two_user_confirmed_darkspots_no_duplicate_area.csv")
    assert a["confirmed_physical_spot_count_in_this_review"]==2
    assert a["ALL_OTHER_NEW_K8I2_REVIEW_GROUPS_STILL_UNCONFIRMED"]
    assert a["K8E_F2_B2_G006_and_G009_prior_confirmations_unchanged"]
    assert o.user_confirmed_one_physical_darkspot.eq(True).all()
    assert o.user_confirmed_outer_complete_and_accurate.eq(True).all()
    assert o.production_quality_approval_not_asserted.eq(True).all()
    assert o.optical_object_plane_size_calibrated.eq(False).all()
    assert o.original_J5_and_B_IDs_unchanged.eq(True).all()
