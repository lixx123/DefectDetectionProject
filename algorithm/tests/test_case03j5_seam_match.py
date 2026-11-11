"""Case03-J5: exact seam continuity vs dangerous false joining; Feret and DSU."""
from __future__ import annotations
import math
import numpy as np
from src.detection.case03j5_seam_match import (
    UnionFind,J5Config,neighboring_pairs,decide_pair,resolve_ambiguous_near_links,
    axes_from_source
)
from scripts.run_case03j5_global_merge import full_diameter


def test_direct_adjacent_vertical_continuity_exact():
    A=np.zeros((32,32),np.int32);B=np.zeros((32,32),np.int32)
    A[11:16,30:32]=12
    B[12:17,0:3]=6
    pairs=neighboring_pairs(A,B,(0,0,32,32),(32,0,64,32),
                             "vertical","left","right",18)
    assert len(pairs)==1
    assert pairs[0]["a_local"]==12 and pairs[0]["b_local"]==6
    assert pairs[0]["gap_px"]==1
    m={"area":10,"feret":5,"axis":np.array((1.,0.)),"reliable":False}
    z=decide_pair(pairs[0],m,m,np.zeros((64,128),dtype=np.uint16),J5Config())
    assert z["accepted"] and z["direct_connected"]


def test_touching_diagonally_over_both_corners():
    A=np.zeros((32,32),np.int32);B=np.zeros((32,32),np.int32)
    A[31,31]=11;B[0,0]=12
    edge=neighboring_pairs(A,B,(0,0,32,32),(32,32,64,64),
                         "diagonal","bottom-right","top-left",math.sqrt(2)+.002)
    assert len(edge)==1
    assert math.isclose(edge[0]["gap_px"],math.sqrt(2),abs_tol=1.e-5)


def test_parallel_near_stripes_without_axis_alignment_not_joined():
    raw=np.full((120,150),2300,dtype=np.uint16)
    p={"a_local":1,"b_local":2,"gap_px":10.,
       "p0":(65,60),"p1":(65,70)}
    m={"area":100,"feret":50.,"axis":np.array((1.,0.)),"reliable":True}
    r=decide_pair(p,m,m,raw,J5Config())
    assert not r["accepted"] and r["reason"]=="incompatible_scratch_direction"


def test_dark_line_with_gap_and_axis_is_allowed_if_evidence():
    raw=np.full((120,150),2300,dtype=np.uint16)
    raw[59:62,45:98]=1700
    p={"a_local":1,"b_local":2,"gap_px":16.,
       "p0":(64,60),"p1":(80,60)}
    m={"area":100,"feret":30.,"axis":np.array((1.,0.)),"reliable":True}
    r=decide_pair(p,m,m,raw,J5Config())
    assert r["accepted"] and not r["direct_connected"]
    assert r["bridge_dog_median_dn"]>=16.


def test_bright_gap_must_not_merge_when_not_touching():
    raw=np.full((120,150),2300,dtype=np.uint16)
    p={"a_local":1,"b_local":2,"gap_px":16.,
       "p0":(64,60),"p1":(80,60)}
    m={"area":100,"feret":30.,"axis":np.array((1.,0.)),"reliable":True}
    r=decide_pair(p,m,m,raw,J5Config())
    assert not r["accepted"]


def test_ambiguous_inferred_competing_edges_veto():
    e=[{"a_id":"a","b_id":"b","gap_px":8.,
        "accepted":True,"direct_connected":False,"reason":"gap"},
       {"a_id":"a","b_id":"c","gap_px":8.7,
        "accepted":True,"direct_connected":False,"reason":"gap"},
       {"a_id":"d","b_id":"e","gap_px":1.,
        "accepted":True,"direct_connected":True,"reason":"direct"}]
    resolve_ambiguous_near_links(e,J5Config())
    assert not e[0]["accepted"] and not e[1]["accepted"]
    assert e[2]["accepted"]


def test_global_union_preserves_single_identity():
    uf=UnionFind(["a","b","c","d"])
    assert uf.join("a","b")
    assert uf.join("b","c")
    assert not uf.join("a","c")
    assert uf.find("a")==uf.find("c")
    assert uf.find("d")!=uf.find("a")


def test_calipers_exact_agrees_with_pairwise_brute():
    rng=np.random.default_rng(774)
    for n in (1,2,3,5,8,15,100):
        for _ in range(5):
            pts=rng.integers(-1000,1000,(n,2))
            d=np.linalg.norm(pts[:,None,:]-pts[None,:,:],axis=-1).max()
            assert abs(full_diameter(pts)-max(1.,float(d)))<1e-4
