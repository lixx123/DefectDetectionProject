"""Case03-K8D: synthetic regression tests for new stable/grouped RAW outlines."""
import numpy as np,pytest
from src.detection.case03k8d_group_stability import K8DConfig,group_evidence,resolve

C=K8DConfig()
def disk(radius,x=64,y=64):
    yy,xx=np.mgrid[:128,:128]
    return (xx-x)**2+(yy-y)**2<=radius**2

def scene(seed_count=48,neighbor=False,competitor=False):
    primary=np.zeros((128,128),bool)
    ys,xs=np.where(disk(5,63,64))
    for y,x in list(zip(ys,xs))[:seed_count]:primary[y,x]=True
    labels=np.zeros((128,128),np.int32);labels[primary]=1
    totals=[0,int(primary.sum()),0,0]
    if neighbor:
        o=disk(2,69,67)&~primary
        labels[o]=2
        totals[2]=int(o.sum())
    if competitor:
        o=disk(8,75,64)&~primary&~(labels>0)
        labels[o]=3
        totals[3]=int(o.sum())
    raw={3.:disk(10),2.:disk(11),1.5:disk(11.5)}
    audit={k:{"raw_proposal_touches_roi_border":False,
               "raw_proposal_touches_radius_cap":False} for k in raw}
    return primary,raw,audit,np.ones((128,128),bool),labels,np.asarray(totals)

def test_tiny48_expands_to_full_369_without_fivefold_cap():
    seed,trials,audits,core,lab,counts=scene()
    full,meta=resolve(seed,trials,audits,core,lab,counts,1)
    assert meta["status"]=="STABLE_SINGLE_OUTER_REVIEW"
    assert meta["selected_k"]==1.5
    assert full.sum()>5*seed.sum()
    assert not np.any(seed&~full)

def test_valid_group_proposed_without_any_official_id_merge():
    seed,raw,au,work,lab,counts=scene(neighbor=True)
    full,meta=resolve(seed,raw,au,work,lab,counts,1)
    assert meta["status"]=="STABLE_GROUP_OUTER_REVIEW"
    assert meta["group"]["eligible_siblings"]==[2]
    assert meta["group"]["official_ID_merge_performed"] is False
    assert full.sum()>seed.sum()

def test_partial_competitor_marks_full_orange_not_seed():
    s,m,a,c,l,n=scene(neighbor=True,competitor=True)
    out,meta=resolve(s,m,a,c,l,n,1)
    assert out.sum()>5*s.sum()
    if meta["group"]["partial_competitors"]:
        assert meta["status"]=="AMBIGUOUS_FULL_OUTER_REVIEW"
    assert not np.any(s&~out)

def test_failed_3mad_cannot_accept_large_1p5_jump():
    s,m,a,c,l,n=scene()
    m[3.]=np.zeros((128,128),bool)
    m[2.]=np.zeros((128,128),bool)
    m[1.5]=disk(30)
    out,meta=resolve(s,m,a,c,l,n,1)
    assert meta["status"]=="SOURCE_ONLY_UNRELIABLE_3MAD"
    assert np.array_equal(out,s)

def test_relaxed_growth_instability_chooses_prior_envelope():
    s,m,a,c,l,n=scene(34)
    m[1.5]=disk(27)
    out,meta=resolve(s,m,a,c,l,n,1)
    assert meta["selected_k"]==2.
    assert out.sum()>5*s.sum()

def test_strict_3mad_outside_work_core_only_amber():
    s,m,a,c,l,n=scene()
    core=c.copy();core[:,70:]=False
    assert np.all(s<=core)
    out,meta=resolve(s,m,a,core,l,n,1)
    assert meta["status"]=="CENSORED_FULL_OUTER_REVIEW"
    assert out.sum()>s.sum()
    assert np.any(out&~core)

def test_strict_radius_limit_amber_but_preserves_whole():
    s,m,a,c,l,n=scene()
    a[3.]["raw_proposal_touches_radius_cap"]=True
    out,meta=resolve(s,m,a,c,l,n,1)
    assert meta["status"]=="CENSORED_FULL_OUTER_REVIEW"
    assert out.sum()>5*s.sum()

def test_nonanchored_raw_does_not_hijack_seed():
    s,m,a,c,l,n=scene()
    m[3.]=disk(10,30,30)
    out,meta=resolve(s,m,a,c,l,n,1)
    assert np.array_equal(out,s)
    assert meta["status"].startswith("SOURCE_ONLY_")

def test_missing_or_incorrect_source_mapping_rejected():
    s,m,a,c,l,n=scene()
    with pytest.raises(ValueError):
        resolve(s,m,a,c,l,n,2)
    with pytest.raises(ValueError):
        resolve(s,m,a,np.zeros((50,50),bool),l,n,1)

def test_global_full_neighbor_area_not_local_fragment_denom():
    s,m,a,c,l,n=scene(neighbor=True)
    n[2]=500
    g=group_evidence(m[3.],l,n,1,C)
    assert 2 not in g["eligible_siblings"]
    assert g["member_evidence"][0]["whole_overlap_fraction"]<.80

def test_input_arrays_preserved_byte_for_byte():
    s,m,a,c,l,n=scene(neighbor=True)
    original=[s.copy(),c.copy(),l.copy(),n.copy()]+[v.copy() for v in m.values()]
    resolve(s,m,a,c,l,n,1)
    after=[s,c,l,n]+list(m.values())
    assert all(np.array_equal(x,y) for x,y in zip(original,after))
