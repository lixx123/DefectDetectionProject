"""Case03-J fragment association: protect source masks and reject nearby noise."""
import numpy as np
from src.detection.case03i_size_grade import SizeGradeConfig,extract_regions
from src.detection.case03j_fragment_association import (
    AssociationConfig,associate_fragments
)


def _associate(mask,raw):
    rows,lab=extract_regions(mask,SizeGradeConfig(),"SY",(50,70,
                                                  mask.shape[1]+50,
                                                  mask.shape[0]+70))
    for x in rows:
        x["_global_x0"]=50
        x["_global_y0"]=70
    return associate_fragments(lab,rows,raw.astype(np.uint16),
                               AssociationConfig(),SizeGradeConfig())


def test_dark_disjoint_collinear_scratch_is_one_object_without_filling_gap():
    raw=np.full((120,150),2300,np.uint16)
    raw[59:63,20:120]=1800
    mask=np.zeros((120,150),bool)
    mask[59:63,20:65]=True
    mask[59:63,77:120]=True
    objects,audit,members,grouped=_associate(mask,raw)
    assert len(objects)==1
    assert objects[0]["member_count"]==2
    assert any(x["accepted"] for x in audit)
    assert np.array_equal(grouped>0,mask)
    assert not grouped[60,70]  # interrupted physical mask remains empty
    assert objects[0]["area_union_original_pixels"]==mask.sum()
    assert objects[0]["size_grade"]=="LARGE"


def test_two_nearby_parallel_stripes_not_linked_on_proximity_alone():
    raw=np.full((120,150),2300,np.uint16)
    raw[40:43,30:100]=1800
    raw[55:58,30:100]=1800
    mask=np.zeros_like(raw,bool)
    mask[40:43,30:100]=True
    mask[55:58,30:100]=True
    objects,audit,_,m=_associate(mask,raw)
    assert len(objects)==2
    assert not any(x["accepted"] for x in audit)
    assert np.array_equal(mask,m>0)


def test_nearby_dark_blobs_do_not_merge_when_not_line_like():
    raw=np.full((120,150),2400,np.uint16)
    raw[50:55,45:50]=1900
    raw[50:55,53:58]=1900
    mask=np.zeros_like(raw,bool)
    mask[50:55,45:50]=True
    mask[50:55,53:58]=True
    objects,audit,_,grouped=_associate(mask,raw)
    assert len(objects)==2
    assert np.array_equal(mask,grouped>0)


def test_large_dark_scratch_not_connected_to_distant_noise():
    raw=np.full((120,150),2200,np.uint16)
    raw[65:70,25:70]=1600
    raw[65:70,101:146]=1600
    mask=np.zeros_like(raw,bool)
    mask[65:70,25:70]=True
    mask[65:70,101:146]=True
    objects,_,_,grouped=_associate(mask,raw)
    assert len(objects)==2
    assert np.count_nonzero(grouped)==np.count_nonzero(mask)


def test_empty_mask_and_single_region_keep_identity():
    r=np.full((100,100),1900,np.uint16)
    zero=np.zeros(r.shape,bool)
    o,a,mem,g=_associate(zero,r)
    assert len(o)==len(a)==len(mem)==0 and not g.any()
    x=zero.copy()
    x[30:45,40:47]=True
    o,a,mem,g=_associate(x,r)
    assert len(o)==1 and len(mem)==1 and not a
    assert np.array_equal(g>0,x)
