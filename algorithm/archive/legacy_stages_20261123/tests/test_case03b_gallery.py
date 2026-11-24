"""样品26局部图册：packbits ROI索引和全图包含关系回归测试。"""
import numpy as np
import pytest

from scripts.build_case03b_sample26_gallery import (
    bounds_for_roi, make_overlay, packed_roi, stats_for_roi
)


@pytest.mark.parametrize("bitorder", ["little","big"])
def test_mask_crop_matches_full_resolution_restore(bitorder):
    rng = np.random.default_rng(20261008)
    shape=(19,23)  # 宽度非8整数倍，跨行字节边界
    original=rng.random(shape)<0.14
    packed=np.packbits(original.reshape(-1),bitorder=bitorder)
    for roi in ((0,0,8,8),(5,4,17,14),(18,12,23,19),(0,0,23,19)):
        x0,y0,x1,y1=roi
        expected=original[y0:y1,x0:x1]
        actual=packed_roi(packed,bitorder,shape,roi)
        assert np.array_equal(actual,expected)


def test_bounds_move_patch_without_resampling():
    assert bounds_for_roi(0,0,8,(19,23)) == (0,0,8,8)
    assert bounds_for_roi(22,18,8,(19,23)) == (15,11,23,19)


def test_overlay_nested_masks_and_statistics():
    shape=(32,35)
    s=np.zeros(shape,bool)
    s[5,5]=True
    h170=s.copy()
    h170[5:7,5:7]=True
    h150=h170.copy()
    h150[7:10,7:10]=True
    raw=np.full(shape,1800,dtype=np.uint16)
    response=np.zeros(shape,dtype=np.uint16)
    response[s]=300
    overlay=make_overlay(np.full(shape,.5,dtype=np.float32),s,h170,h150)
    stats=stats_for_roi("example","not_truth",18,16,32,(1,1,36,33),raw,response,s,h170,h150)
    assert overlay.shape==(32,35,3)
    assert stats["S230_pixels"]==1
    assert stats["H170_230_pixels"]==4
    assert stats["H150_230_pixels"]==13
    assert stats["H170_added_pixels"]==3
    assert stats["H150_additional_pixels"]==9
    assert not np.array_equal(overlay[5,5],overlay[6,6])


def test_overlay_rejects_mask_nesting_violation():
    s=np.zeros((8,8),bool)
    a=np.zeros_like(s)
    b=np.zeros_like(s)
    s[3,3]=True
    with pytest.raises(ValueError):
        make_overlay(np.zeros((8,8)),s,a,b)
