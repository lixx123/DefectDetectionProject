"""K5 safe grouping and adaptive halo: synthetic adversarial tests."""
import cv2,numpy as np
from src.detection.case03k3_spot_contour_pilot import PilotConfig
from src.detection.case03k5_adaptive_grouping import (
    AdaptiveConfig,choose_adaptive_envelope,audit_object_membership,
    render_status
)

def fake_extract(shape,area,seed,cutoff,seed_cover=1.,border=False):
    m=np.zeros(shape,bool);m.reshape(-1)[:area]=True
    if seed_cover:
        m|=seed
    return m,{"raw_proposal_touches_roi_border":border,
              "raw_proposal_touches_radius_cap":False,
              "raw_proposal_seed_overlap_fraction":seed_cover}

def test_adaptive_picks_low_noise_floor_on_plateau_for_079():
    seed=np.zeros((128,128),bool);seed[45:47,45:49]=True
    maps={3.:179,2.:272,1.5:314}
    def fetch(raw,s,center,cfg):
        return fake_extract(s.shape,maps[cfg.raw_noise_sigma_multiplier],s,0)
    _,meta,decision=choose_adaptive_envelope(
        np.zeros((128,128),np.uint16),seed,(50,50),127,PilotConfig(),
        AdaptiveConfig(),fetch)
    assert decision["floor_selected_sigma"]==1.5
    assert decision["floor_1p5_area_px2"]>=314

def test_adaptive_keeps_strict_on_already_large_ratio_for_074():
    seed=np.zeros((128,128),bool);seed[45:47,45:49]=True
    maps={3.:1203,2.:1501,1.5:1659}
    def fetch(raw,s,center,cfg):
        return fake_extract(s.shape,maps[cfg.raw_noise_sigma_multiplier],s,0)
    _,_,decision=choose_adaptive_envelope(
        np.zeros((128,128),np.uint16),seed,(50,50),215,PilotConfig(),
        AdaptiveConfig(),fetch)
    assert decision["floor_selected_sigma"]==3.
    assert "INITIAL_ENVELOPE_SUFFICIENT_RELATIVE_TO_H61" in decision["adaptive_kept_strict_reasons"]

def test_unstable_low_threshold_rejected():
    seed=np.zeros((128,128),bool);seed[50:54,50:54]=True
    maps={3.:110,2.:170,1.5:800}
    def fetch(raw,s,center,cfg):
        return fake_extract(s.shape,maps[cfg.raw_noise_sigma_multiplier],s,0)
    _,_,meta=choose_adaptive_envelope(
        np.zeros((128,128),np.uint16),seed,(55,55),100,PilotConfig(),
        AdaptiveConfig(),fetch)
    assert meta["floor_selected_sigma"]==3.

def test_coherent_source_fragments_result_review_group_only():
    g=np.full((128,128),"",dtype="<U32")
    prop=np.zeros(g.shape,bool);prop[40:80,40:80]=True
    g[60,60]="DEFECT_11170"
    g[50:53,54:59]="DEFECT_11166"
    g[70:72,70:74]="DEFECT_11172"
    meta=audit_object_membership(prop,"DEFECT_11170",g,
        {"DEFECT_11170":1,"DEFECT_11166":15,"DEFECT_11172":8},
        {"raw_proposal_touches_roi_border":False,
         "raw_proposal_touches_radius_cap":False},AdaptiveConfig())
    assert meta["group_status"]=="COHERENT_GROUP_REVIEW"
    assert len(meta["proposed_review_group_ids"])==3
    assert not meta["official_membership_changed"]

def test_partial_foreign_object_cannot_be_grouped():
    g=np.full((128,128),"",dtype="<U32")
    prop=np.zeros(g.shape,bool);prop[40:80,40:80]=True
    g[60,60]="DEFECT_11170"
    g[78:90,60:63]="DEFECT_11166"
    # 6 of 36 foreign source pixels fall within candidate.
    meta=audit_object_membership(prop,"DEFECT_11170",g,
        {"DEFECT_11170":1,"DEFECT_11166":36},
        {"raw_proposal_touches_roi_border":False,
         "raw_proposal_touches_radius_cap":False},AdaptiveConfig())
    assert meta["group_status"]=="CONFLICT_UNRESOLVED_REVIEW"

def test_competing_large_or_slender_source_forbids_auto_group():
    g=np.full((128,128),"",dtype="<U32")
    prop=np.zeros(g.shape,bool);prop[30:100,30:100]=True
    g[50,50]="DEFECT_A"
    g[51:61,55:75]="DEFECT_B"
    m=audit_object_membership(prop,"DEFECT_A",g,
        {"DEFECT_A":1,"DEFECT_B":200},
        {"raw_proposal_touches_roi_border":False,
         "raw_proposal_touches_radius_cap":False},AdaptiveConfig())
    assert m["group_status"]=="CONFLICT_UNRESOLVED_REVIEW"
    assert any("LARGE_SIBLING" in e for e in m["group_reject_reasons"])

def test_display_retains_provisional_contour_even_if_review_rejected():
    source=np.zeros((128,128),bool);source[60,60]=True
    cand=np.zeros_like(source);cand[40:80,40:80]=True
    status,visible=render_status(source,cand,{},
        {"group_status":"CONFLICT_UNRESOLVED_REVIEW"},[])
    assert status=="CONFLICT_OUTER_PENDING_HUMAN_REVIEW"
    assert int(visible.sum())==1600
    status,visible=render_status(source,cand,{},
        {"group_status":"NO_SIBLING_CONFLICT"},["RAW_envelope_below_H61"])
    assert status=="REJECTED_HALO_DISPLAY_REVIEW_ONLY"
    assert int(visible.sum())==1600
    status,visible=render_status(source,np.zeros_like(source),{},
        {"group_status":"NO_SIBLING_CONFLICT"},[])
    assert status=="NO_RAW_OUTER_KEEP_J5"
    assert np.array_equal(visible,source)

def test_thin_scratch_source_not_grouped_as_spot():
    g=np.full((128,128),"",dtype="<U32")
    p=np.zeros(g.shape,bool);p[61:65,5:120]=True
    g[62,60]="DEFECT_A"
    g[62,70]="DEFECT_B"
    v=audit_object_membership(p,"DEFECT_A",g,
        {"DEFECT_A":1,"DEFECT_B":1},
        {"raw_proposal_touches_roi_border":False,
         "raw_proposal_touches_radius_cap":False},AdaptiveConfig())
    assert v["group_status"]=="CONFLICT_UNRESOLVED_REVIEW"
    assert "LONG_THIN_ENVELOPE_NOT_A_SPOT" in v["group_reject_reasons"]
