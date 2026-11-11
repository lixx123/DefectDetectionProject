"""Case03-K8-B guard tests: exact H threshold behavior and source masks."""
import numpy as np
import pytest
from src.detection.case03k8b_perband_trial import (
    PerBandTrial,stats_median_mad,threshold_params,hysteresis_on_work)


def test_reference_band_keeps_frozen_170_230():
    config=PerBandTrial()
    stat={
        1:{"blackhat_background_median_dn":90,"blackhat_background_MADsigma_dn":52},
        2:{"blackhat_background_median_dn":35,"blackhat_background_MADsigma_dn":19},
        3:{"blackhat_background_median_dn":69,"blackhat_background_MADsigma_dn":39}}
    out=threshold_params(stat,config,1)
    assert (out[1]["band_trial_low_dn"],out[1]["band_trial_high_dn"])==(170.,230.)
    assert 60<out[2]["band_trial_low_dn"]<75
    assert 80<out[2]["band_trial_high_dn"]<95
    assert out[2]["band_trial_low_dn"]<out[2]["band_trial_high_dn"]


def test_reject_unstable_negative_anchor_scores():
    with pytest.raises(ValueError,match="Invalid anchor"):
        threshold_params({1:{"blackhat_background_median_dn":200,
                             "blackhat_background_MADsigma_dn":20}},
                         PerBandTrial(),1)


def test_robust_background_statistics_not_deformed_by_one_giant_defect():
    x=np.full((30,30),42.,np.float64)
    x[:3,:]=220
    stats=stats_median_mad(x,2.)
    assert stats["blackhat_background_median_dn"]==42
    assert stats["blackhat_background_MADsigma_dn"]>=2


def test_hysteresis_requires_high_seed_and_work_core():
    a=np.zeros((80,80),np.uint16)
    area=np.zeros_like(a,bool)
    area[8:71,8:71]=True
    a[10:25,10:25]=195
    a[13,13]=235
    a[37:52,37:52]=195   # low response without high seed
    a[71:76,10:20]=250   # high response outside approved work core
    mask,st=hysteresis_on_work(a,area,170,230)
    assert st["hysteresis_candidate_components"]==1
    assert int(mask.sum())==225
    assert np.all(mask[10:25,10:25])
    assert not np.any(mask[37:52,37:52])
    assert not np.any(mask[71:76,10:20])


def test_band_transfer_detects_low_contrast_in_same_work_pixels():
    a=np.zeros((60,60),np.uint16)
    core=np.zeros_like(a,bool);core[4:55,4:55]=True
    a[20:30,20:30]=73
    a[24,24]=90
    fixed,_=hysteresis_on_work(a,core,170,230)
    adaptive,_=hysteresis_on_work(a,core,60,85)
    assert fixed.sum()==0
    assert adaptive.sum()==100
    assert not np.any(adaptive&~core)


def test_dont_mutate_fused_response_or_mask_when_thresholding():
    response=np.zeros((30,30),np.uint16)
    region=np.ones_like(response,bool)
    response[10:15,10:15]=200
    response[12,12]=255
    old=response.copy();copy=region.copy()
    res,_=hysteresis_on_work(response,region,170,230)
    assert res.any()
    assert np.array_equal(old,response) and np.array_equal(region,copy)


def test_duplicate_components_single_hysteresis_object():
    response=np.zeros((35,35),np.uint16)
    response[5:12,5:12]=190
    response[7,7]=235
    response[10,9]=245
    work=np.ones_like(response,bool)
    m,s=hysteresis_on_work(response,work,170,230)
    assert s["hysteresis_candidate_components"]==1
    assert s["high_seed_pixels"]==2


def test_invalid_hysteresis_settings_or_arrays():
    with pytest.raises(ValueError):
        hysteresis_on_work(np.zeros((8,8),np.uint8),
                           np.ones((8,8),bool),170,230)
    with pytest.raises(ValueError):
        hysteresis_on_work(np.zeros((8,8),np.uint16),
                           np.ones((8,8),bool),240,230)
    with pytest.raises(ValueError):
        hysteresis_on_work(np.zeros((8,8),np.uint16),
                           np.zeros((7,8),bool),170,230)
