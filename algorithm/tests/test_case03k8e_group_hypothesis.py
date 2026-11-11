"""K8E deterministic pixel-union, grouping, source-lineage unit regression."""
import numpy as np,pytest
from src.detection.case03k8e_group_hypothesis import (
    GroupPolicy,global_intersection,union_global,make_groups)

def item(label,x0=0,y0=0,w=32,h=32,part=(5,5,17,17),band=2,status="STABLE_GROUP_OUTER_REVIEW",embedded=None):
    m=np.zeros((h,w),bool)
    ax,ay,bx,by=part
    m[ay:by,ax:bx]=True
    return {"band_id":band,"label":label,"box":(x0,y0,x0+w,y0+h),
            "mask":m,"status":status,
            "partial_competitors":[],
            "embedded_evidence":embedded or []}

def test_group_very_nearly_same_contour_exact_union_not_sum():
    a=item(1148,0,0,32,32,(5,5,20,20))
    b=item(1161,1,1,32,32,(4,4,20,20))
    # a extents global 5:20, b global 5:21 -> overlap225 union256
    metrics=global_intersection(a,b)
    assert metrics["intersection_px2"]==225
    assert metrics["union_px2"]==256
    assert metrics["min_containment"]==1.0
    grouped=make_groups([a,b])
    assert len(grouped)==1
    obj=grouped[0]
    assert obj["exact_group_union_px2"]==256
    assert obj["deduplicated_pixels"]==225
    assert obj["selected_candidate_labels"]==[1148,1161]
    assert obj["review_status"]=="MULTI_PROPOSAL_ASSOCIATION_REVIEW"
    assert obj["original_B_J5_ids_merged"] is False

def test_disjoint_stays_separate():
    a=item(4,x0=0)
    b=item(5,x0=200)
    g=make_groups([a,b])
    assert len(g)==2
    assert all(e["deduplicated_pixels"]==0 for e in g)

def test_no_cross_band_grouping_even_same_contour():
    a=item(1,band=2)
    b=item(2,band=3)
    g=make_groups([a,b])
    assert len(g)==2

def test_group_embedded_full_B_component_pending_not_automerge():
    emb=[{"B_label":658,"source_full_px":20,"whole_overlap_fraction":.92,
         "eligible_same_spot_review":True}]
    single=item(626,embedded=emb)
    groups=make_groups([single])
    assert len(groups)==1
    o=groups[0]
    assert o["selected_candidate_labels"]==[626]
    assert o["embedded_B_source_evidence"][0]["B_label"]==658
    assert o["review_status"]=="EMBEDDED_B_SOURCE_REVIEW"
    assert o["original_B_J5_ids_merged"] is False

def test_partial_overlap_not_embedded():
    emb=[{"B_label":658,"source_full_px":70,"whole_overlap_fraction":.35,
         "eligible_same_spot_review":False}]
    g=make_groups([item(626,embedded=emb)])
    assert g[0]["embedded_B_source_evidence"]==[]
    assert g[0]["review_status"]=="SINGLE_STABLE_REVIEW"

def test_partial_competitor_requires_amber_group_review():
    a=item(1)
    a["partial_competitors"]=[9]
    out=make_groups([a])
    assert out[0]["review_status"]=="GROUP_CONFLICT_REVIEW"

def test_unstable_raw_cannot_promote_stable_group():
    a=item(1,status="CENSORED_FULL_OUTER_REVIEW")
    assert make_groups([a])[0]["review_status"]=="RAW_SAFETY_UNRESOLVED"

def test_no_merge_from_small_inside_a_gigantic_shape():
    a=item(1,part=(0,0,29,29))
    b=item(2,part=(5,5,8,8))
    # min containment=1 but IoU very tiny; should not connect by size only.
    g=make_groups([a,b])
    assert len(g)==2

def test_pairwise_union_exact_coordinates_and_does_not_mutate():
    a=item(1,x0=12,y0=22)
    b=item(2,x0=20,y0=30)
    aa=a["mask"].copy();bb=b["mask"].copy()
    bounds,mask=union_global([a,b])
    assert bounds==(12,22,52,62)
    assert mask.sum()==a["mask"].sum()+b["mask"].sum()-global_intersection(a,b)["intersection_px2"]
    assert np.array_equal(a["mask"],aa) and np.array_equal(b["mask"],bb)

def test_invalid_roi_is_rejected():
    a=item(1)
    a["box"]=(0,0,16,16)
    with pytest.raises(ValueError):
        make_groups([a])
