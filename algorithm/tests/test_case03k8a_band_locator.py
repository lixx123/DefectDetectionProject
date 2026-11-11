"""K8-A tests: count inferred from data, never hard-code 4/5.

All masks geometry-only, no J5 generation. Includes synthetic five-band
image with weak passband and bright top/bottom nonwork.
"""
from dataclasses import replace
import numpy as np
from src.detection.case03k8a_band_locator import (
    BandLocatorConfig,locate_transmission_bands,rasterize_region_masks,
    select_interior_bands,polygon_for_band)

CFG=BandLocatorConfig(
    y_stride=2,x_stride=5,smooth_sigma_rows=3,
    min_peak_prominence_dn=45,
    min_band_width_px=30,max_band_width_px=160,
    min_dark_shield_trough_gap_px=17,
    min_peak_spacing_px=70,
    allowed_shield_floor_offset_dn=35,
    min_band_contrast_dn=75,
    edge_local_max_displacement_px=50,
    max_edge_median_residual_px=20,
    max_edge_p90_residual_px=35,
    x_column_sample_count=12,
    local_column_halfwidth_px=28,
    local_x_stride=3,
    boundary_review_margin_px=4,
    horizontal_inner_margin_px=6)


def make_synthetic(n,shift=0,seed=19):
    rng=np.random.default_rng(seed)
    h,w=1000,420
    raw=np.full((h,w),120.,np.float32)
    raw[:110,:]=850;raw[875:,:]=900
    starts=[180,305,430,555,680]
    highs=[430,260,680,500,740]
    for y,val in zip(starts[:n],highs[:n]):
        # min 70px and normal intensity varies by waveband.
        raw[y+shift:y+shift+73,:]=val
    raw+=rng.normal(0,3,size=raw.shape).astype(np.float32)
    return np.uint16(np.clip(raw,0,4095))


def test_synthetic_five_bands_detected_without_fixed_number():
    raw=make_synthetic(5)
    out=locate_transmission_bands(raw,CFG)
    assert out["band_count_auto"]==5
    assert not out["band_count_fixed"]
    centers=[(b["profile_top_y"]+b["profile_bottom_y"])/2 for b in out["bands"]]
    assert all(abs(p-y-35)<=12 for p,y in zip(centers,[180,305,430,555,680]))
    region,ids=rasterize_region_masks(raw.shape,out["bands"],
                                    out["exterior"],CFG)
    assert np.array_equal(region==2,ids>0)
    assert set(np.unique(ids))==set(range(6))
    assert np.count_nonzero(region==1)>0
    assert np.count_nonzero(region==0)>0
    assert np.count_nonzero(region==3)>0
    for i in range(1,6):
        assert np.count_nonzero(ids==i)>0


def test_synthetic_four_bands_count_changes_with_input():
    raw=make_synthetic(4)
    out=locate_transmission_bands(raw,CFG)
    assert out["band_count_auto"]==4
    assert [b["band_id"] for b in out["bands"]]==[1,2,3,4]


def test_frame_shift_updates_masks_not_reused():
    original=make_synthetic(4)
    shifted=make_synthetic(4,shift=10)
    p=locate_transmission_bands(original,CFG)
    q=locate_transmission_bands(shifted,CFG)
    assert p["band_count_auto"]==q["band_count_auto"]==4
    a,_=rasterize_region_masks(original.shape,p["bands"],p["exterior"],CFG)
    b,_=rasterize_region_masks(shifted.shape,q["bands"],q["exterior"],CFG)
    assert np.any(a!=b)
    assert q["bands"][0]["peak_position_y"]>p["bands"][0]["peak_position_y"]


def test_guard_external_bright_plateau_not_counted_as_bands():
    raw=make_synthetic(5)
    out=locate_transmission_bands(raw,CFG)
    assert all(b["profile_top_y"]>=120 for b in out["bands"])
    assert all(b["profile_bottom_y"]<=870 for b in out["bands"])
    # Top/bottom NON_WORK never assigned work band IDs.
    region,ids=rasterize_region_masks(raw.shape,out["bands"],out["exterior"],CFG)
    assert np.all(ids[:100]==0) and np.all(ids[900:]==0)


def test_boundary_buffer_and_id_core_conservation():
    raw=make_synthetic(5)
    out=locate_transmission_bands(raw,CFG)
    region,ids=rasterize_region_masks(raw.shape,out["bands"],out["exterior"],CFG)
    assert np.array_equal(ids>0,region==2)
    for band in out["bands"]:
        full=polygon_for_band(band,raw.shape[1],CFG,False)
        core=polygon_for_band(band,raw.shape[1],CFG,True)
        assert int(core[:,0].min())>int(full[:,0].min())
        assert int(core[:,0].max())<int(full[:,0].max())
        assert np.min(core[:,1])>=np.min(full[:,1])+2
