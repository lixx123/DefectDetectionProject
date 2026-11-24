"""K8F independent audit: workband candidate index and exact visual approval.

Only frame2 G006/G009 approved; frame1 no manual confirmations. Verify
all legacy WORK J5 source areas and IDs exactly unchanged, masks bitexact,
geometry/physical units clearly qualified, no double count.
"""
from pathlib import Path
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,max_feret_centers_px
OUT=C.OUTPUT_ROOT/"case03k8f_confirmed_group_register/run_20261014_F26_2_two_user_approved_G006_G009_v2"
SRC=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"

def qa():
    report=[]
    expected={
      1:{"old":683,"new":0,"pending":13},
      2:{"old":398,"new":2,"pending":16}
    }
    for frame in (1,2):
        folder=OUT/f"frame26_{frame}"
        orig=pd.read_csv(B/f"frame26_{frame}"/
              "original_J5_object_center_workband_classification.csv",encoding="utf-8-sig")
        work=orig[orig.K8A_region_code_by_original_J5_center==2]
        record=pd.read_csv(folder/"workband_unified_candidate_review_register.csv",
                           encoding="utf-8-sig")
        old=record[record.source=="FROZEN_J5_WORK"]
        newer=record[record.source=="K8F_USER_APPROVED_K8E_OUTER"]
        x=expected[frame]
        assert len(record)==x["old"]+x["new"]
        assert len(old)==len(work)==x["old"]
        assert len(newer)==x["new"]
        assert record.work_candidate_review_ID.is_unique
        assert record.official_original_J5_global_ID_preserved.all()
        assert record.source_masks_untouched.all()
        assert (~record.physical_object_plane_size_calibrated).all()
        assert (~record.is_certified_production_defect_register).all()
        assert old.source_J5_global_defect_id.is_unique
        assert set(old.source_J5_global_defect_id)==set(work.global_defect_id)
        joined=old.merge(work,left_on="source_J5_global_defect_id",
                          right_on="global_defect_id",validate="one_to_one")
        assert len(joined)==len(work)
        assert (joined.area_detector_px2==joined.source_area_px2).all()
        assert (joined.size_grade==joined.grade).all()
        assert np.allclose(joined.max_length_detector_px,
                           joined.source_max_feret_px,atol=.0002)
        assert int((old.size_grade!="SMALL").sum())==(25 if frame==1 else 26)
        assert pd.isna(newer.source_J5_global_defect_id).all()
        assert pd.isna(old.supplement_K8E_group_id).all()
        assert not old.visual_defect_confirmed_by_user.any()
        assert newer.visual_defect_confirmed_by_user.all()
        assert newer.size_grade.eq("LARGE").all()
        pending=pd.read_csv(folder/"other_K8E_groups_pending_manual_review.csv")
        assert len(pending)==x["pending"]
        assert pending.not_added_to_unified_workband_register.all()
        members=pd.read_csv(folder/"all_K8E_source_B_members_with_exact_user_approval.csv")
        assert int(members.confirmed_by_user_as_one_darkspot.sum())==(
              5 if frame==2 else 0)
        assert members.source_physical_ID_deleted_or_changed.eq(False).all()
        if frame==2:
            assert set(newer.supplement_K8E_group_id)=={
                "K8E_F2_B2_G006","K8E_F2_B2_G009"}
            assert set(newer.area_detector_px2)=={348,370}
            assert int(newer.area_detector_px2.sum())==718
            assert abs(float(newer.area_detector_image_um2.sum())-718*3.2**2)<1e-5
            assert sorted(newer.source_B_connected_components)==["1148;1161","626"]
            assert set(newer.source_B_embedded_components.astype(int))=={1186,658}
            # Independently compare every exported mask PNG with original K8E
            for t in newer.itertuples(index=False):
                gid=str(t.supplement_K8E_group_id)
                with np.load(SRC/"frame26_2"/"group_detail"/(
                    gid+"_EXACT_GROUP_MASK.npz"),allow_pickle=False) as z:
                    box=tuple(int(v) for v in z["roi_xyxy"])
                    m=z["review_outer"].astype(bool)
                im=cv2.imdecode(np.frombuffer(
                    (folder/(gid+"_outer_mask_128p.png")).read_bytes(),np.uint8),
                    cv2.IMREAD_UNCHANGED)
                assert np.array_equal(im>0,m)
                assert int(m.sum())==t.area_detector_px2
                yy,xx=np.where(m)
                feret=float(max_feret_centers_px(np.column_stack([xx,yy])))
                newgrade,_=grade_size(len(xx),feret,SizeGradeConfig())
                assert newgrade==t.size_grade
                assert np.isclose(feret,t.max_length_detector_px,atol=.0001)
                # Conservative legacy J5 collision: check ALL J5 bbox, not
                # just WORK region. Half-open box rules avoid edge ambiguity.
                xmin,xmax=box[0]+int(xx.min()),box[0]+int(xx.max())+1
                ymin,ymax=box[1]+int(yy.min()),box[1]+int(yy.max())+1
                collisions=orig[
                    (orig.display_bbox_x_global<xmax)&
                    (orig.display_bbox_xmax_inclusive>=xmin)&
                    (orig.display_bbox_y_global<ymax)&
                    (orig.display_bbox_ymax_inclusive>=ymin)]
                assert len(collisions)==0
        else:
            assert newer.empty
        for p in folder.glob("0?_*.png"):
            img=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),1)
            assert img is not None and img.shape[1]>1000
        s=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
        assert s["unified_review_candidate_count"]==len(record)
        assert s["newly_approved_J5_bbox_collision_count"]==0
        assert s["true_defect_count_or_qualification_not_calculated"]
        report.append({"frame":frame,"old_work_J5_unverified":len(old),
                      "new_user_visually_confirmed":len(newer),
                      "unified_review_rows":len(record),
                      "other_K8E_groups_pending":len(pending),
                      "original_source_records_unchanged":True})
    response={"stage":"K8F_INDEPENDENT_QA_PASS",
        "human_confirmation_only_two_secondframe_K8E_group_ids":True,
        "source_J5_full_register_not_modified":True,
        "no_physical_object_plane_calibration":True,
        "no_precision_recall_or_qualification_claims":True,
        "frames":report}
    dest=OUT/"independent_QA.json"
    if dest.exists():raise FileExistsError(dest)
    dest.write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8F_INDEPENDENT_QA_PASS",json.dumps(response,ensure_ascii=False),flush=True)

if __name__=="__main__":qa()
