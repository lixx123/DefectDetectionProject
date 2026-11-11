"""Case03-T adaptive double-threshold generation regression tests."""
from __future__ import annotations
import numpy as np,pytest
from src.detection.case03t_adaptive_hysteresis import (
    AdaptiveConfig,robust_stats,global_thresholds,local_grids,
    local_window_thresholds,hysteresis_window
)


def test_bright_anomaly_resists_median_trim():
    data=np.full((80,80),45,dtype=np.uint16)
    data[::2,::2]=65
    data[:5,:5]=1000  # < 2% anomaly, exclude from robust background
    m,s,cap=robust_stats(data,AdaptiveConfig())
    assert m>=40
    assert cap<1000
    assert s>=0


def test_double_threshold_order_separated():
    frame=np.full((160,192),20,dtype=np.uint16)
    frame[30:35,35:40]=255
    c=AdaptiveConfig()
    stat=global_thresholds(frame,c)
    assert stat["low_dn"]>=c.low_floor_dn
    assert stat["high_dn"]>stat["low_dn"]
    assert stat["high_dn"]-stat["low_dn"]>=c.min_hysteresis_gap_dn-.001


def test_hysteresis_only_seeds_keep_the_low_support():
    a=np.zeros((30,40),dtype=np.uint16)
    a[4,5]=255
    a[5,5]=200  # 8-connected to strong pixel
    a[20,30]=200 # low without a strong seed: excluded
    h,s,n=hysteresis_window(a,150,230)
    assert n==1
    assert int(h.sum())==2 and int(s.sum())==1
    assert not h[20,30]


def test_hysteresis_equal_boundary_and_invalid_high():
    a=np.array([[170,230],[0,0]],dtype=np.uint16)
    h,s,n=hysteresis_window(a,170,230)
    assert int(h.sum())==2
    assert int(s.sum())==1
    with pytest.raises(ValueError):
        hysteresis_window(a,300,200)


def test_local_surface_varies_with_background_and_preserves_order():
    arr=np.full((512,512),30,dtype=np.uint16)
    arr[:,256:]=100
    arr[110,105]=255
    cfg=AdaptiveConfig(grid_size_px=128,sample_stride_px=4)
    med,sig,cap,audit=local_grids(arr,cfg)
    assert len(audit)==16
    lo,hi=local_window_thresholds(med,sig,(150,0,350,200),arr.shape,cfg)
    assert lo.shape==(200,200)
    assert np.all(hi>lo)
    assert float(lo[:,-1].mean())>float(lo[:,0].mean())


def test_constant_grid_floors_not_fake_local_adaptation():
    arr=np.zeros((256,256),dtype=np.uint16)
    cfg=AdaptiveConfig(grid_size_px=128)
    med,sig,_,audit=local_grids(arr,cfg)
    assert all(v["low_floor_dominates"] for v in audit)
    low,high=local_window_thresholds(med,sig,(0,0,100,100),arr.shape,cfg)
    assert np.all(low==cfg.low_floor_dn)
    assert np.all(high==cfg.high_floor_dn)


def test_variable_threshold_adapter_fixed_path_matches_frozen_production():
    from src.detection.blackhat import black_hat_uint16
    from src.detection.case03e2_hseeded import (
        detect_window_H_seeded as frozen
    )
    from src.detection.case03t_hseeded_variable import (
        detect_window_H_seeded as adapted
    )
    from src.detection.case03e2_multicandidate import FusionConfig
    from src.detection.case03e2_hseeded import HSeedConfig
    rng=np.random.default_rng(21)
    raw=rng.integers(2200,2300,size=(256,256),dtype=np.uint16)
    raw[104:120,100:122]=np.uint16(1800)
    R=black_hat_uint16(raw,31)
    H,S,_=hysteresis_window(R,170.,230.)
    old=frozen(raw,H,S,R,cfg=FusionConfig(),policy=HSeedConfig())
    new=adapted(raw,H,S,R,cfg=FusionConfig(),policy=HSeedConfig(),
                h_low_threshold_dn=170.,h_high_threshold_dn=230.)
    assert len(old["objects"])==len(new["objects"])
    for left,right in zip(old["objects"],new["objects"]):
        assert np.array_equal(left.mask,right.mask)
        assert left.status==right.status and left.sources==right.sources


def test_variable_threshold_adapter_checks_local_surface():
    from src.detection.blackhat import black_hat_uint16
    from src.detection.case03t_hseeded_variable import detect_window_H_seeded
    raw=np.full((256,256),2200,dtype=np.uint16)
    raw[50:65,50:65]=1800
    R=black_hat_uint16(raw,31)
    low=np.full(R.shape,130.,np.float32)
    high=np.full(R.shape,200.,np.float32)
    H,S,_=hysteresis_window(R,low,high)
    out=detect_window_H_seeded(raw,H,S,R,
             h_low_threshold_map=low,h_high_threshold_map=high)
    assert len(out["objects"])>=1
    # Deliberately wrong threshold surface must be rejected.
    with pytest.raises(ValueError):
        detect_window_H_seeded(raw,H,S,R,
              h_low_threshold_map=low+500,h_high_threshold_map=high)
