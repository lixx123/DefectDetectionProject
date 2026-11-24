"""Independent QA and deduplicated GROUP_REVIEW records for Case03-K5.

K5 is only a display/review trial: no current J5 ID, source mask, physical
area or quality grade is overwritten. Overlapping proposal rows pointing to
the same exact frozen global IDs are one group for review, NEVER a new
official defect.
"""
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,Counter
import json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/case03k_adaptive_group_trial/run_20261012_K5_adaptive_and_J5_group_review_v2"
J5=ROOT/"outputs/case03j5_global/run_20261012_frame26_1_global_j5_v1"
SOURCE=ROOT/"outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1"


def global_mask_overlap(sample_a:str,sample_b:str)->dict:
    """IoU between pixel coordinates of two alternative group contours."""
    def load(sample):
        with np.load(BASE/"reversible_masks"/(sample+".npz"),allow_pickle=False) as f:
            mask=f["raw_adaptive"]>0
            rect=[int(v) for v in f["global_roi_xyxy"]]
        return mask,rect
    am,ar=load(sample_a);bm,br=load(sample_b)
    x0=min(ar[0],br[0]);y0=min(ar[1],br[1])
    x1=max(ar[2],br[2]);y1=max(ar[3],br[3])
    maska=np.zeros((y1-y0,x1-x0),bool)
    maskb=np.zeros_like(maska)
    maska[ar[1]-y0:ar[3]-y0,ar[0]-x0:ar[2]-x0]|=am
    maskb[br[1]-y0:br[3]-y0,br[0]-x0:br[2]-x0]|=bm
    intersection=int((maska&maskb).sum())
    union=int((maska|maskb).sum())
    return {
        "intersection_px":intersection,
        "union_px":union,
        "contour_IoU":round(intersection/max(union,1),5),
        "different_proposals_do_not_imply_separate_defects":True
    }


def verify()->dict:
    frame=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    byid=frame.set_index("global_defect_id")
    attempts=pd.read_csv(BASE/"k5_23_case_adaptive_and_group_audit.csv",
                         encoding="utf-8-sig",keep_default_na=False)
    assert len(attempts)==23 and attempts.sample_id.is_unique
    assert attempts.loc[attempts.sample_id.str.startswith("K4S_")].shape[0]==22
    assert attempts.loc[attempts.sample_id=="K0_SMALL_074"].shape[0]==1
    assert attempts.official_J5_unchanged.all()
    assert attempts.human_label_used_by_algorithm.eq(False).all()
    assert attempts.loc[attempts.sample_id=="K4S_079","floor_selected_sigma"].iloc[0]==1.5
    assert attempts.loc[attempts.sample_id=="K0_SMALL_074","floor_selected_sigma"].iloc[0]==3.
    assert attempts.loc[attempts.sample_id=="K4S_079","adaptive_outer_area_px2"].iloc[0]==314
    assert attempts.loc[attempts.sample_id=="K0_SMALL_074","adaptive_outer_area_px2"].iloc[0]==1203
    assert (attempts.floor_selected_sigma==1.5).sum()==4
    assert (attempts.group_status=="COHERENT_GROUP_REVIEW").sum()==7
    source=pd.read_csv(SOURCE/"fixed_unlabeled_selection.csv")
    selection=dict(zip(source.global_defect_id,source.source_area_px2))
    assert set(attempts.frozen_J5_ID).issubset(set(byid.index))
    assert attempts.frozen_J5_ID.isin(byid.index).all()
    bysample=attempts.set_index("sample_id")
    audit_group=json.loads((BASE/"provisional_group_membership_review.json").read_text(encoding="utf-8"))
    assert len(audit_group)==23
    groups=defaultdict(list)
    checks=[]
    for row in attempts.itertuples(index=False):
        path=BASE/"reversible_masks"/(row.sample_id+".npz")
        with np.load(path,allow_pickle=False) as f:
            src=f["original_J5_source"]>0
            comp=f["original_competing_J5"]>0
            orig_h=f["original_H31"]>0
            plus=f["expanded_blackhat_H61"]>0
            o3=f["raw_initial_k3"]>0
            adaptive=f["raw_adaptive"]>0
            shown=f["displayed_review_mask"]>0
            rect=f["global_roi_xyxy"]
            assert all(im.shape==(128,128) for im in
                       (src,comp,orig_h,plus,o3,adaptive,shown))
            assert np.all(shown[src])
            assert not np.any(src&comp)
            assert int(src.sum())==int(row.original_J5_source_pixels)
            assert int(src.sum())==int(byid.loc[row.frozen_J5_ID,"source_area_px2"])
            assert int(o3.sum())==int(row.floor_3_area_px2)
            assert int(adaptive.sum())==int(row.adaptive_outer_area_px2)
            assert int(plus.sum())==int(row.h61_source_anchor_pixels)
            if not adaptive.any():
                assert np.array_equal(shown,src)
            else:
                assert np.array_equal(shown,src|adaptive)
            assert int((adaptive&comp).sum())==int(row.raw_conflicting_J5_pixels)
        if row.group_status=="COHERENT_GROUP_REVIEW":
            ids=tuple(sorted(row.proposed_group_member_IDs.split(";")))
            assert row.frozen_J5_ID in ids
            assert len(ids)>1 and all(id_ in byid.index for id_ in ids)
            groups[ids].append(row.sample_id)
        elif row.proposed_group_member_IDs:
            raise AssertionError("unapproved membership suggestions present")
        path=BASE/"review_figures"/(row.sample_id+"_6panel.png")
        img=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        assert img is not None and img.shape==(343,1680,3)
    # Deduplicate IDENTICAL frozen J5 global-membership groups.
    assert len(groups)==6 and sum(len(k) for k in groups.values())==7
    proposal_records=[]
    for i,(members,sample_ids) in enumerate(sorted(groups.items()),1):
        compare=None
        if len(sample_ids)>1:
            assert len(sample_ids)==2
            compare=global_mask_overlap(sample_ids[0],sample_ids[1])
        proposed_group={
            "review_group_id":f"K5_GROUP_REVIEW_{i:03d}",
            "J5_member_IDs":list(members),
            "J5_member_count":len(members),
            "source_area_sum_only_px2":int(byid.loc[list(members),"source_area_px2"].sum()),
            "K5_supporting_anchor_samples":sample_ids,
            "candidate_outer_areas_px2":[int(bysample.loc[s,"adaptive_outer_area_px2"])
                                          for s in sample_ids],
            "different_seed_proposals":len(sample_ids)>1,
            "proposal_overlap_comparison":compare,
            "human_decision_needed":"SAME_PHYSICAL_DARK_SPOT / DISTINCT_SPOTS / UNCERTAIN",
            "human_annotation_status":"UNREVIEWED",
            "official_J5_grouping_performed":False,
            "estimated_outer_area_is_not_physical_truth":True,
        }
        proposal_records.append(proposed_group)
    dst=BASE/"deduplicated_group_review.json"
    if dst.exists():raise FileExistsError(dst)
    dst.write_text(json.dumps(proposal_records,ensure_ascii=False,indent=2),encoding="utf-8")
    table=pd.DataFrame([{
        "review_group_id":v["review_group_id"],
        "frozen_member_IDs":";".join(v["J5_member_IDs"]),
        "frozen_member_count":v["J5_member_count"],
        "review_anchor_ids":";".join(v["K5_supporting_anchor_samples"]),
        "sum_measured_original_source_area_px2":v["source_area_sum_only_px2"],
        "estimated_outer_areas_px2":";".join(map(str,v["candidate_outer_areas_px2"])),
        "alternative_contour_IoU":v["proposal_overlap_comparison"]["contour_IoU"]
                                     if v["proposal_overlap_comparison"] else "",
        "human_confirmed_same_spot":"",
        "review_notes":"",
        "official_source_membership_changed":False
    } for v in proposal_records])
    csv=BASE/"deduplicated_group_review_blank.csv"
    if csv.exists():raise FileExistsError(csv)
    table.to_csv(csv,index=False,encoding="utf-8-sig")
    pngs=list(BASE.glob("*.png"))
    for p in pngs:
        assert cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR) is not None,p
    answer={
       "stage":"CASE03K5_QA_PASS",
       "tested_samples":23,
       "added_adaptive_floor_suggestions":4,
       "previous_079_alpha15_k3_px2":179,
       "new_079_alpha15_k1p5_px2":314,
       "previous_074_px2":1203,
       "new_074_px2":1203,
       "group_candidate_anchor_rows":7,
       "distinct_groups_for_manual_review":len(proposal_records),
       "duplicate_group_proposals_deduplicated":1,
       "old_J5_source_pixels_and_IDs_unchanged":True,
       "all_23_6panel_images_verified":True,
       "review_prior_K5_024_057_086_pending":True,
       "independent_frame_validated":False,
       "true_physical_contours_confirmed":False
    }
    print("K5_INDEPENDENT_QA",json.dumps(answer,ensure_ascii=False),flush=True)
    print("K5_DEDUPLICATED_GROUPS")
    print(table.to_string(index=False),flush=True)
    return answer
if __name__=="__main__":verify()
