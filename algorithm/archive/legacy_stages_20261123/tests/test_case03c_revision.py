"""Case03-C-R1 ring geometry and manual label separability protections."""
from types import SimpleNamespace

import numpy as np
import pytest

from src.detection.reference_ring_geometry import select_reference_pixels,project_reference_masks
from src.detection.candidate_raw_features import TransitionProfiles, compute_raw_candidate_metrics
from src.detection.feature_discrimination import unique_manual_labels, auc_positive_higher, exploratory_auc


def fake_component(x,y,w,h,image_shape=(20,23)):
    return SimpleNamespace(bbox_x=x,bbox_y=y,bbox_w=w,bbox_h=h,
                           touches_border=x==0 or y==0 or x+w==image_shape[1] or y+h==image_shape[0])


def fake_profiles(shape):
    return TransitionProfiles(np.zeros(shape[0]),np.zeros(shape[1]),
                              np.empty(0,dtype=np.int32),np.empty(0,dtype=np.int32),
                              10.,10.)


def test_reference_sampling_matches_original_ring_math_nonbyte_shape():
    raw=np.arange(20*23,dtype=np.uint16).reshape(20,23)+1000
    mask=np.zeros(raw.shape,dtype=bool)
    mask[7:9,8:10]=True
    mask[6,12]=True
    comp=fake_component(8,7,2,2)
    selected=select_reference_pixels(comp,mask,radius_px=3,max_reference_pixels=12)
    x0,y0,x1,y1=selected.bounds
    old_ring=np.ones((y1-y0,x1-x0),dtype=bool)
    old_ring[7-y0:9-y0,8-x0:10-x0]=False
    old_ring &=~mask[y0:y1,x0:x1]
    old_values=raw[y0:y1,x0:x1][old_ring]
    expected=old_values[np.linspace(0,len(old_values)-1,12,dtype=np.int64)]
    actual=raw[selected.sample_y,selected.sample_x]
    assert np.array_equal(actual,expected)
    assert selected.eligible_count==len(old_values)
    assert selected.sampled_count==12
    eligible,used=project_reference_masks(selected,image_bounds=(0,0,23,20),valid_reference=True)
    assert np.array_equal(eligible,old_ring if selected.bounds==(0,0,23,20) else mask_to_full(old_ring,selected.bounds,mask.shape))
    assert used.sum()==12
    assert not np.any(used & mask)


def mask_to_full(part,bounds,shape):
    arr=np.zeros(shape,bool)
    x0,y0,x1,y1=bounds
    arr[y0:y1,x0:x1]=part
    return arr


def test_reference_invalid_shows_no_used_pixels_and_partial_roi():
    mask=np.zeros((20,23),bool)
    mask[0,0]=True
    comp=fake_component(0,0,1,1)
    selection=select_reference_pixels(comp,mask,radius_px=4,max_reference_pixels=7)
    elig,used=project_reference_masks(selection,image_bounds=(0,0,8,8),valid_reference=False)
    assert elig.sum()>0
    assert used.sum()==0
    assert selection.eligible_count>7


def test_reference_helper_matches_actual_raw_metrics():
    raw=np.full((30,31),1000,dtype=np.uint16)
    raw[12:14,15:17]=800
    mask=np.zeros(raw.shape,bool)
    mask[12:14,15:17]=True
    comp=fake_component(15,12,2,2,raw.shape)
    xs=np.array([15,16,15,16])
    ys=np.array([12,12,13,13])
    m=compute_raw_candidate_metrics(comp,xs,ys,raw,mask,fake_profiles(raw.shape),
                                    reference_radius_px=5,max_reference_pixels=24,
                                    min_reference_pixels=5,transition_margin_px=2)
    selection=select_reference_pixels(comp,mask,radius_px=5,max_reference_pixels=24)
    assert m["raw_reference_valid"] is True
    assert m["raw_reference_pixel_count"]==selection.eligible_count
    assert m["raw_reference_sample_count"]==selection.sampled_count
    assert m["raw_background_median_dn"]==1000.0
    assert m["raw_delta_dn"]==200.0


def test_manual_labels_deduplicated_and_conflicts_error():
    rows=[{"candidate_id":"x","manual_label":"confirmed_dark_spot","review_status":"reviewed"},
          {"candidate_id":"x","manual_label":"confirmed_dark_spot","review_status":"reviewed"},
          {"candidate_id":"y","manual_label":"","review_status":"unreviewed"}]
    labels,status=unique_manual_labels(rows)
    assert labels=={"x":"confirmed_dark_spot"}
    assert status["unique_reviewed_candidates"]==1
    rows[1]["manual_label"]="background_artifact"
    with pytest.raises(ValueError,match="conflicting"):
        unique_manual_labels(rows)


def test_inconsistent_review_status_rejected():
    with pytest.raises(ValueError,match="review_status"):
        unique_manual_labels([{"candidate_id":"x","manual_label":"confirmed_dark_spot",
                               "review_status":"unreviewed"}])


def test_auc_requires_labeled_positive_and_negative_minimum():
    rows=[{"candidate_id":str(i),"area_px":str(i)} for i in range(10)]
    assert all(x["status"]=="PENDING_LABELS" for x in exploratory_auc(rows,{}))
    labels={str(i):("confirmed_dark_spot" if i>=5 else "background_artifact") for i in range(10)}
    result=exploratory_auc(rows,labels,bootstrap_iterations=5)
    feature=next(r for r in result if r["feature"]=="area_px")
    assert feature["status"]=="EXPLORATORY_ONLY"
    assert feature["auc_positive_higher"]==1.0
    assert auc_positive_higher(np.array([1,1]),np.array([1,1]))==.5

 
def test_existing_case03c_atlas_path_uses_only_actual_reference_samples():
    # 防止旧主入口重新运行时又将整个ROI背景误涂为参考环带。
    from scripts.run_case03c import _ring_patch
    from config import user_config
    h=np.zeros((40,47),dtype=bool)
    h[19:21,22:24]=True
    candidate=fake_component(22,19,2,2,h.shape)
    selection=select_reference_pixels(
        candidate,h,radius_px=12,
        max_reference_pixels=user_config.CASE03C_RAW_REFERENCE_MAX_PIXELS,
    )
    exp_eligible,expected=project_reference_masks(
        selection,image_bounds=(0,0,47,40),valid_reference=True,
    )
    actual=_ring_patch(candidate,h,(0,0,47,40),12,reference_valid=True)
    assert exp_eligible.sum()>expected.sum()
    assert np.array_equal(actual,expected)
    assert _ring_patch(candidate,h,(0,0,47,40),12,reference_valid=False).sum()==0
