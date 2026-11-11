"""Case03-E local segmentation engineering regressions.

These assert reproducibility, exact RAW pixel geometry and that a hand polygon
is excluded from the segmenter input, not physical-defect accuracy.
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
import pytest

from src.detection.local_boundary_refinement import (
    METHODS,LEVELS,compute_local_residual,grow_from_clicked_center,
    image_crop_at_target,max_hull_distance
)
from scripts.run_case03e_local_boundary_pilot import (
    pixel_agreement,manual_polygon_mask
)

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"outputs/case03e/run_20261010_10roi_boundary_pilot_v1"


def sample_raw(size=256,spot=(110,125),radius=9):
    image=np.full((size,size),2200,dtype=np.uint16)
    cv2.circle(image,spot,radius,1800,-1)
    return image


@pytest.mark.parametrize("method",METHODS)
@pytest.mark.parametrize("level",LEVELS)
def test_dark_disc_seeded_connected_compact_region(method,level):
    raw=sample_raw()
    out=grow_from_clicked_center(raw,(110,125),method=method,level=level)
    assert out.mask.shape==raw.shape
    assert out.mask.dtype==bool
    assert out.mask[125,110]
    assert out.status=="ok"
    assert 100<=out.area_px<=900
    assert not out.touches_crop_edge
    assert out.seed_shift_px<=12
    assert out.bbox_xywh is not None
    assert np.isfinite(out.threshold_dn)


def test_raw_crop_keeps_zero_based_true_pixel_coordinates_near_border():
    raw=np.arange(500*400,dtype=np.uint16).reshape(500,400)
    crop,(x0,y0)=image_crop_at_target(raw,(389,6),size=256)
    assert crop.shape==(256,256) and crop.dtype==np.uint16
    assert (x0,y0)==(144,0)
    assert crop[6,245]==raw[6,389]


def test_reject_invalid_raw_and_nonexistent_click():
    with pytest.raises(TypeError):
        compute_local_residual(np.ones((256,256),dtype=np.uint8),"closing61")
    with pytest.raises(ValueError):
        grow_from_clicked_center(sample_raw(),(260,120))
    with pytest.raises(ValueError):
        grow_from_clicked_center(sample_raw(),(110,120),level="unknown")
    with pytest.raises(ValueError):
        grow_from_clicked_center(sample_raw(),(110,120),method="unknown")


def test_noise_free_blank_raw_does_not_create_false_synthetic_defect():
    background=np.full((256,256),2100,dtype=np.uint16)
    out=grow_from_clicked_center(background,(123,123))
    assert out.area_px==0
    assert out.status=="no_reliable_seed"
    assert not out.mask.any()


def test_manual_polygon_is_used_for_evaluation_not_segmentation():
    raw=sample_raw()
    a=grow_from_clicked_center(raw,(110,125),method="closing61")
    manual1,_=manual_polygon_mask(
        [[98,110],[125,110],[125,142],[98,142]],(0,0),256
    )
    manual2,_=manual_polygon_mask(
        [[1,1],[20,1],[20,20],[1,20]],(0,0),256
    )
    one=pixel_agreement(a.mask,manual1)
    two=pixel_agreement(a.mask,manual2)
    assert one["coverage_of_manual_polygon"]>0
    assert two["coverage_of_manual_polygon"]==0
    assert a.area_px==a.mask.sum()


def test_max_convex_hull_span_is_pixel_geometry_not_object_plane_um():
    m=np.zeros((256,256),bool)
    m[17,10]=True;m[21,13]=True
    assert max_hull_distance(m)==pytest.approx(5)
    assert max_hull_distance(np.zeros((256,256),bool))==0


def test_actual_60_experiments_all_10_proposals_and_masks():
    frame=pd.read_csv(RUN/"all_60_pilot_experiments.csv")
    assert len(frame)==60 and frame.user_target_id.nunique()==10
    assert set(frame.method)==set(METHODS)
    assert set(frame.threshold_level)==set(LEVELS)
    assert frame.groupby("user_target_id").size().eq(6).all()
    assert not frame.used_manual_polygon_to_fit.any()
    assert frame.source_manual_human_area_approx_only.all()
    assert frame.size_grade.eq("NOT_DEFINED").all()
    assert not frame.user_target_id.str.contains("MANUAL_005").any()
    for row in frame.iloc[[0,8,31,44,59]].to_dict("records"):
        path=RUN/"masks"/f"{row['user_target_id']}_{row['method']}_{row['threshold_level']}.npz"
        assert path.is_file()
        with np.load(path,allow_pickle=False) as d:
            mask=d["binary_mask"]
            origin=d["crop_origin_xy"]
        assert mask.shape==(256,256)
        assert set(np.unique(mask))<={0,1}
        assert mask.sum()==row["predicted_area_px"]
        assert len(origin)==2


def test_actual_crop_leakage_is_flagged_not_sold_as_precision():
    a=pd.read_csv(RUN/"all_60_pilot_experiments.csv")
    for uid in ("RAW26_MANUAL_003","RAW26_MANUAL_010"):
        d=a[(a.user_target_id==uid)&(a.method=="closing61")]
        assert d.segmentation_status.eq("touches_crop_boundary").all()
        assert d.predicted_area_px.min()>5000
        assert d.fraction_predicted_inside_manual.max()<0.5
    s=json.loads((RUN/"summary.json").read_text(encoding="utf-8"))
    assert s["not_full_image_detection"]
    assert s["cannot_use_same_10_hand_polygons_as_independent_accuracy_test"]
    assert not s["algorithms_may_under_or_over_segment"] is False
    assert (RUN/"source_manifest.json").is_file()
