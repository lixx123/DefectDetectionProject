"""K8-C reversible triage invariants (label-free synthetic scenes)."""
import numpy as np
import cv2,pytest
from src.detection.case03k8c_noise_review import (
  K8CConfig,evaluate_binary_band,component_properties,classify_candidate)

CONF=K8CConfig()

def data():
    raw=np.full((150,150),700,np.uint16)
    core=np.zeros(raw.shape,bool);core[5:145,5:145]=True
    b=np.zeros(raw.shape,bool);a=np.zeros(raw.shape,bool)
    return raw,core,b,a

def test_no_candidate_is_discarded_and_micro_is_reversible():
    raw,core,b,a=data()
    b[20,20]=True
    b[90:100,90:100]=True
    raw[90:100,90:100]=470
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert len(rows)==2
    assert np.array_equal(p|r|m,b)
    assert m.sum()==1
    assert p.sum()+r.sum()==100
    assert raw[90,90]==470

def test_existing_A_candidate_never_counted_as_novel():
    raw,core,b,a=data()
    b[40:45,40:45]=True
    a[42,42]=True
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert len(rows)==1
    assert rows[0]["classification"]=="EXISTING_FIXED_H"
    assert rows[0]["source_A_fixed_overlap_px"]==1
    assert r.sum()==25 and p.sum()==m.sum()==0

def test_strong_raw_dark_core_is_promising_not_micro():
    raw,core,b,a=data()
    raw[47:73,47:73]=470
    b[53:67,53:67]=True
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert len(rows)==1
    o=rows[0]
    assert o["classification"]=="PROMISING_DARK_REVIEW",o
    assert o["raw_contrast_fraction"]>.07
    assert o["raw_MAD_significance_z"]>2
    assert o["dog_dark_core_p90_dn"]>=CONF.min_dog_dark_core_dn
    assert p.sum()==196 and r.sum()==m.sum()==0

def test_edge_candidate_review_even_high_raw_contrast():
    raw,core,b,a=data()
    b[6:14,49:65]=True
    raw[6:14,49:65]=380
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert len(rows)==1
    assert rows[0]["classification"]=="BOUNDARY_REVIEW"
    assert r.sum()==128

def test_unknown_contrast_is_not_deleted():
    raw,core,b,a=data()
    b[72:82,50:62]=True
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert rows[0]["classification"]=="UNCERTAIN_REVIEW"
    assert r.sum()==120

def test_intermediate_3_to_7_px_never_hard_deleted():
    raw,core,b,a=data()
    b[75:80,76]=True
    raw[75:80,76]=550
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert rows[0]["classification"]=="MICRO_REVIEW"
    assert r.sum()==5

def test_allows_no_candidates_empty():
    raw,core,b,a=data()
    rows,p,r,m=evaluate_binary_band(raw,b,a,core,CONF)
    assert len(rows)==0
    assert p.sum()==r.sum()==m.sum()==0

def test_errors_on_nonband_b_mask_or_different_shapes():
    raw,core,b,a=data()
    b[0,0]=True
    with pytest.raises(ValueError):
        evaluate_binary_band(raw,b,a,core,CONF)
    b[0,0]=False
    with pytest.raises(ValueError):
        evaluate_binary_band(raw,b[:100],a,core,CONF)

def test_status_rule_human_annotation_not_an_input():
    props={"band_core_min_edge_distance_px":60,
        "raw_reference_valid":True,"raw_contrast_fraction":.09,
        "raw_MAD_significance_z":2.7,"dog_dark_core_p90_dn":7.,
        "feature_reason":"VALID_ANNULUS"}
    assert classify_candidate(20,0,props,CONF)[0]=="PROMISING_DARK_REVIEW"
    assert classify_candidate(1,0,props,CONF)[0]=="MICRO_HIDE_SUGGESTION"
    assert classify_candidate(20,1,props,CONF)[0]=="EXISTING_FIXED_H"
    props["band_core_min_edge_distance_px"]=5
    assert classify_candidate(20,0,props,CONF)[0]=="BOUNDARY_REVIEW"

def test_no_mutation_of_raw_or_B_core_arrays():
    raw,core,b,a=data()
    b[43:56,44:56]=True
    raw[43:56,44:56]=450
    copies=[x.copy() for x in [raw,core,b,a]]
    evaluate_binary_band(raw,b,a,core,CONF)
    assert all(np.array_equal(x,y) for x,y in zip([raw,core,b,a],copies))
