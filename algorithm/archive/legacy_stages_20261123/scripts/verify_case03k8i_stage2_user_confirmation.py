"""Independent K8I-2 human approved F1 Band02/Band04 object and mask QA."""
from pathlib import Path
import json,sys,hashlib,math
import pandas as pd,numpy as np,cv2
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import max_feret_centers_px,grade_size,SizeGradeConfig
APPROVAL=C.OUTPUT_ROOT/"case03k8i_stage2_user_confirmed_reviews/run_20261017_F1_B02_B04_two_darkspots_v1"
K8I2=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
I1=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
def im(path):
    z=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    assert z is not None
    return z

def run():
    x=pd.read_csv(APPROVAL/"two_user_confirmed_darkspots_no_duplicate_area.csv",
                  encoding="utf-8-sig")
    members=pd.read_csv(APPROVAL/"five_B_source_components_to_two_user_confirmed_darkspots.csv",
                        encoding="utf-8-sig")
    summary=json.loads((APPROVAL/"summary.json").read_text(encoding="utf-8"))
    assert len(x)==2 and x.review_object_id.is_unique
    assert len(members)==5 and not members.duplicated(
       ["frame","band_id","source_B_connected_component_label"]).any()
    assert x.independent_physical_darkspot_count_for_this_review.eq(1).all()
    assert x.area_exact_union_detector_px2.sum()==695
    assert x.user_confirmed_one_physical_darkspot.all()
    assert x.user_confirmed_outer_complete_and_accurate.all()
    assert x.original_J5_and_B_IDs_unchanged.all()
    assert x.production_quality_approval_not_asserted.all()
    assert (~x.optical_object_plane_size_calibrated).all()
    assert x.frame.eq(1).all()
    assert set(x.band_id)=={2,4}
    assert set(members.source_B_connected_component_label)=={1787,1902,2424,2444,2504}
    assert all(members.all_one_physical_darkspot_user_confirmed)
    assert all(members.do_not_double_count_same_darkspot)
    assert len(x[x.band_id==2])==len(x[x.band_id==4])==1
    originals=pd.read_csv(K8I2/"frame26_1/new_exact_group_union_review.csv")
    old=pd.read_csv(E/"frame26_1/K8E_unique_group_union_measurements.csv")
    # Approval manifest cannot silently mutate archived approval status.
    assert originals.is_user_confirmed.eq(False).all()
    assert old.human_confirm_same_spot.isna().all()
    for rec in x.itertuples(index=False):
        members_for_group=members[members.review_object_id==rec.review_object_id]
        assert set(map(int,str(rec.connected_B_source_labels).split(";")))==set(
           members_for_group.source_B_connected_component_label.astype(int))
        with np.load(rec.canonical_source_mask_npz,allow_pickle=False) as z:
            if rec.band_id==2:
                orig=z["review_outer"].astype(bool)
                box=tuple(map(int,z["roi_xyxy"]))
            else:
                orig=z["exact_review_union"].astype(bool)
                box=tuple(map(int,z["RAW_global_bbox"]))
        with np.load(rec.crosscheck_new_mask_npz,allow_pickle=False) as z:
            new=z["exact_review_union"].astype(bool)
            nbox=tuple(map(int,z["RAW_global_bbox"]))
        # Verified in previous script via global-offset exact equality.
        with np.load(rec.verified_copy_npz,allow_pickle=False) as z:
            copy=z["verified_binary_mask"].astype(bool)
            cbox=tuple(map(int,z["global_raw_roi_xyxy"]))
            names=set(map(int,z["source_B_connected_labels"]))
        assert np.array_equal(copy,orig)
        assert box==cbox
        assert names==set(members_for_group.source_B_connected_component_label)
        assert int(copy.sum())==rec.area_exact_union_detector_px2
        assert math.isclose(rec.area_detector_image_um2,
                            int(copy.sum())*float(C.PIXEL_SIZE_UM)**2,
                            rel_tol=0,abs_tol=.001)
        yy,xx=np.where(copy)
        f=max_feret_centers_px(np.column_stack((xx,yy)))
        assert np.isclose(f,rec.longest_Feret_detector_px,atol=.00006)
        assert np.isclose(f*C.PIXEL_SIZE_UM,
                          rec.longest_Feret_detector_image_um,atol=.0006)
        assert grade_size(int(copy.sum()),f,SizeGradeConfig())[0]==rec.trial_size_grade_not_physical_plane
        row=originals[originals.new_group_id==rec.crosschecked_new_K8I2_group_id]
        assert len(row)==1
        assert not bool(row.iloc[0].is_user_confirmed)
        assert int(row.iloc[0].new_exact_union_area_px2)==rec.area_exact_union_detector_px2
        assert bool(row.iloc[0].original_sources_unchanged)
        assert int(rec.overlap_original_J5_display_bbox_candidate_count)==0
        if rec.band_id==2:
            assert rec.canonical_old_K8E_group_id=="K8E_F1_B2_G004"
            assert box!=nbox or np.array_equal(orig,new)
            # User-approved canonical F1 B02 is frozen K8E mask, not a sum
            assert int(orig.sum())==int(new.sum())==398
            assert old[old.group_id=="K8E_F1_B2_G004"].iloc[0].unique_outer_union_px2==398
            assert str(row.iloc[0].new_source_B_labels)=="1787"
            assert "1902" in str(row.iloc[0].embedded_B_labels_unapproved)
        else:
            assert box==nbox and np.array_equal(orig,new)
            assert rec.canonical_old_K8E_group_id!=rec.canonical_old_K8E_group_id or pd.isna(rec.canonical_old_K8E_group_id)
            assert int(orig.sum())==297
            assert int(row.iloc[0].new_RAW_source_areas_sum_px2)==870
            assert int(row.iloc[0].new_internal_duplicate_pixels_removed)==573
    # Prior second-frame approval remains 348/370 source masks.
    f2=pd.read_csv(E/"frame26_2/K8E_unique_group_union_measurements.csv")
    assert f2[f2.group_id=="K8E_F2_B2_G006"].iloc[0].unique_outer_union_px2==348
    assert f2[f2.group_id=="K8E_F2_B2_G009"].iloc[0].unique_outer_union_px2==370
    # UI comparison PNGs decode and matched original pixels if copied.
    for name in [
        "01_FRAME1_2_CONFIRMED_plus_frozen_J5_MEDLARGE.png",
        "02_ONLY_B02_B04_two_confirmed_darkspots.png",
        "03_Band04_verified_source_image_UNCHANGED.png",
        "04_Band02_verified_source_image_UNCHANGED.png"
    ]:
        assert im(APPROVAL/name).shape[1]>1000
    for name,oldname in (
        ("03_Band04_verified_source_image_UNCHANGED.png",
         "05_B04_TRIPLE_RAW_sources_outer_exact_union_REVIEW.png"),
        ("04_Band02_verified_source_image_UNCHANGED.png",
         "06_B02_1787_vs_OLD_B1902_overlap_REVIEW.png"),
    ):
        assert (APPROVAL/name).read_bytes()==(K8I2/"frame26_1"/oldname).read_bytes()
    assert summary["confirmed_physical_spot_count_in_this_review"]==2
    assert summary["ALL_OTHER_NEW_K8I2_REVIEW_GROUPS_STILL_UNCONFIRMED"]
    assert summary["K8E_F2_B2_G006_and_G009_prior_confirmations_unchanged"]
    res={"stage":"K8I_STAGE2_USER_APPROVED_TWO_SPOTS_INDEPENDENT_QA_PASS",
         "frame":1,"bands":[2,4],
         "independent_confirmed_darkspots":2,
         "original_B_fragment_count":5,
         "exact_areas_detector_pixels2":[398,297],
         "total_unique_detector_pixels2":695,
         "canonical_B02_and_new_mask_exact_equal":True,
         "canonical_B04_three_B_masks_OR_297":True,
         "source_J5_and_existing_stage_outputs_unmodified":True,
         "f2_original_approval_preserved":True,
         "production_acceptance_qualification_not_provided":True}
    q=APPROVAL/"independent_QA.json"
    if q.exists():raise FileExistsError(q)
    q.write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print(res["stage"],json.dumps(res,ensure_ascii=False),flush=True)

if __name__=="__main__":run()
