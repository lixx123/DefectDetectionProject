"""K3 isolated seeded expansion and conservative veto unit tests."""
import numpy as np,cv2
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,component_seeded_H,raw_outer_envelope,decision
)

def test_component_anchor_cannot_propose_independent_noise():
    cfg=PilotConfig()
    a=np.zeros((128,128),np.uint16)
    a[30:35,30:35]=210;a[31,31]=235
    a[90:100,95:105]=240
    source=np.zeros(a.shape,bool);source[32,32]=True
    got=component_seeded_H(a,source,cfg)
    assert got.sum()==25
    assert not got[95,100]

def test_anchor_must_have_high_seed_and_positive_source_overlap():
    cfg=PilotConfig()
    a=np.zeros((64,64),np.uint16);a[18:28,18:28]=210
    source=np.zeros(a.shape,bool);source[20,20]=True
    assert not component_seeded_H(a,source,cfg).any()
    a[19,19]=240
    assert component_seeded_H(a,source,cfg).sum()==100
    far=np.zeros_like(source);far[50,50]=True
    assert not component_seeded_H(a,far,cfg).any()

def test_guard_prevents_crossing_another_original_j5_object():
    cfg=PilotConfig()
    src=np.zeros((128,128),bool);src[60:64,60:64]=True
    h=src.copy();enh=np.zeros_like(src);enh[52:77,52:77]=True
    raw=enh.copy();other=np.zeros_like(src);other[70,70]=True
    audit={
      "raw_proposal_seed_overlap_fraction":1.,
      "raw_proposal_touches_roi_border":False,
      "raw_proposal_touches_radius_cap":False
    }
    verdict,why=decision(src,h,enh,raw,other,audit,cfg)
    assert verdict=="KEEP_ORIGINAL_REVIEW_ONLY"
    assert "RAW_intersects_competing_J5_object" in why

def test_deep_black_spot_can_generate_seeded_outer_hypothesis():
    cfg=PilotConfig()
    y,x=np.mgrid[:128,:128]
    rr=(x-64)**2+(y-64)**2
    raw=np.clip(2000-220*np.exp(-rr/(2*10**2)),0,4095).astype(np.uint16)
    seed=np.zeros(raw.shape,bool);seed[62:66,62:66]=True
    envelope,stats=raw_outer_envelope(raw,seed,(64,64),cfg)
    assert envelope.sum()>seed.sum()
    assert np.any(envelope&seed)
    assert stats["raw_proposal_area_px2"]==int(envelope.sum())
    assert not stats["raw_proposal_touches_roi_border"]
