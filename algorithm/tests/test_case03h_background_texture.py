"""Case03-H experimental medium-texture veto tests."""
import cv2
import numpy as np
import pytest
from src.detection.case03h_background_texture import (
    TextureTrialConfig, extend_gate,
)


def common():
    mask=np.zeros((100,100),np.uint8)
    mask[30:34,30:34]=1  # area16 with weak RAW: should be hide suggestion
    mask[50:54,50:54]=1  # area16 strong RAW: keep
    mask[70:78,70:78]=1  # area64 always kept
    n,lab,stats,_=cv2.connectedComponentsWithStats(mask,8)
    assert n==4
    rec=[
        dict(area_px=16,reference_valid=True,relative_contrast=.03,
             significance_z=1.6,fused_blackhat_peak_dn=240),
        dict(area_px=16,reference_valid=True,relative_contrast=.12,
             significance_z=4.0,fused_blackhat_peak_dn=280),
        dict(area_px=64,reference_valid=True,relative_contrast=.03,
             significance_z=1.0,fused_blackhat_peak_dn=260),
    ]
    return lab,stats,rec


def test_suppress_only_weak_medium_not_dark_spot():
    lab,stats,rec=common()
    states,reasons=extend_gate(lab,stats,["keep"]*3,
                               ["raw_kept"]*3,rec,TextureTrialConfig())
    assert states==["hide_suggestion","keep","keep"]
    assert reasons[0]=="medium_weak_RAW_contrast_and_significance"


def test_keep_weak_candidate_near_large_H_anchor():
    lab,stats,rec=common()
    cfg=TextureTrialConfig(protect_big_radius_px=30)
    states,_=extend_gate(lab,stats,["keep"]*3,["a"]*3,rec,cfg)
    assert states[0]=="hide_suggestion"
    assert states[1]=="protected_review"


def test_protect_strong_peak_and_invalid_reference():
    lab,stats,rec=common()
    rec[0]["fused_blackhat_peak_dn"]=400
    rec[1]["reference_valid"]=False
    states,_=extend_gate(lab,stats,["keep"]*3,["a"]*3,rec,
                        TextureTrialConfig())
    assert states==["keep","protected_review","keep"]


def test_existing_old_hide_stays_hide_and_never_unhides():
    lab,stats,rec=common()
    states,_=extend_gate(lab,stats,["hide_suggestion","keep","keep"],
                         ["a"]*3,rec,TextureTrialConfig())
    assert states[0]=="hide_suggestion"


def test_scratch_like_shape_protected():
    mask=np.zeros((80,80),np.uint8)
    mask[30:32,10:25]=1
    n,lab,st,_=cv2.connectedComponentsWithStats(mask,8)
    features=[dict(area_px=30,reference_valid=True,relative_contrast=.001,
                   significance_z=.01,fused_blackhat_peak_dn=240)]
    states,reasons=extend_gate(lab,st,["keep"],["a"],features,
                               TextureTrialConfig())
    assert states==["protected_review"]
    assert reasons[0]=="medium_line_shape_protected"


def test_reject_invalid_catalogue():
    lab,stats,rec=common()
    with pytest.raises(ValueError):
        extend_gate(lab,stats,["keep"],["a"],rec,TextureTrialConfig())


def test_protect_coherent_dark_aggregate_dog():
    lab,stats,rec=common()
    rec[0]["dog_median_dn"]=22.0
    rec[1]["dog_median_dn"]=4.0
    rec[2]["dog_median_dn"]=100.0
    states,reasons=extend_gate(lab,stats,["keep"]*3,["a"]*3,rec,
                               TextureTrialConfig())
    assert states==["protected_review","keep","keep"]
    assert reasons[0]=="medium_coherent_dark_DoG_protected"
