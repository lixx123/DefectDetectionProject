"""Case03-J2 regression: reconstructed display topology, provenance, no false merges."""
import numpy as np
from src.detection.case03i_size_grade import SizeGradeConfig,extract_regions
from src.detection.case03j_fragment_association import AssociationConfig
from src.detection.case03j_continuous_contour import (
    ContinuousConfig,reconstruct_continuous_visual
)


def fixture(bright_gap=False):
    raw=np.full((140,155),2300,np.uint16)
    # Five detected portions of a single dark cross.
    # Gap darkness independently controls context completion.
    raw[58:62,18:120]=1850
    raw[18:118,79:82]=1850
    # Independent thin dark ridge in the unsegmented lateral gap.
    raw[59,86:103]=1000
    if bright_gap:
        raw[55:66,86:103]=2300
    lab=np.zeros_like(raw,np.int32)
    lab[58:63,10:73]=1       # long horizontal anchor, >60px
    lab[55:68,76:86]=2       # central knot
    lab[21:50,78:83]=3       # vertical upper
    lab[75:101,78:83]=4      # vertical lower
    lab[58:63,102:118]=5    # disconnected horizontal extension
    mask=lab>0
    # Extract the actual connected components (guaranteed separate).
    records,_=extract_regions(mask,SizeGradeConfig(),
                             "X",(100,200,255,340))
    # connected-component IDs may differ from the manually numbered
    # local lab; construct a pixel-verified map using extraction instead.
    records,labeled=extract_regions(mask,SizeGradeConfig(),
                                   "X",(100,200,255,340))
    for r in records:
        r["_global_x0"]=100
        r["_global_y0"]=200
        r["frame"]="synthetic"
    def id_at(x,y):return int(labeled[y,x])
    center=id_at(80,59)
    left=id_at(30,59)
    top=id_at(80,25)
    bottom=id_at(80,85)
    right=id_at(105,59)
    edges=[
        {"a":left,"b":center,"accepted":True,
         "reason":"linked_dark_aligned_gap"},
        {"a":top,"b":center,"accepted":True,
         "reason":"linked_dark_aligned_gap"},
        {"a":center,"b":bottom,"accepted":True,
         "reason":"linked_dark_aligned_gap"},
    ]
    return raw,labeled,records,edges,(left,center,top,bottom,right)


def test_cross_has_single_continuous_contour_after_context_extension():
    raw,lab,records,edges,ids=fixture(False)
    objects,old,bridge,full,alls,audit=reconstruct_continuous_visual(
        lab,raw,records,edges)
    assert len(objects)==1
    assert objects[0]["member_count"]==5
    assert len([e for e in alls if e["reason"]=="context_long_scratch_dark_ridge"])==1
    assert objects[0]["continuous_display_components"]==1
    assert int(np.count_nonzero(bridge))>0
    assert np.array_equal(old>0,lab>0)
    assert np.array_equal(full>0,(lab>0)|(bridge>0))
    assert not np.any((bridge>0)&(lab>0))
    # Both the original detector and its pixel-based measured area are intact.
    assert int(objects[0]["original_area_px2"])==int(np.count_nonzero(lab))


def test_context_must_not_bridge_bright_unverified_gap():
    raw,lab,records,edges,ids=fixture(True)
    objects,old,bridge,full,alls,audit=reconstruct_continuous_visual(
        lab,raw,records,edges)
    assert len(objects)==2
    assert len([e for e in alls if e["reason"]=="context_long_scratch_dark_ridge"])==0
    assert sorted(o["member_count"] for o in objects)==[1,4]
    assert np.array_equal(old>0,lab>0)


def test_no_data_or_inferred_pixels_for_singlet():
    raw=np.full((120,140),2000,np.uint16)
    mask=np.zeros_like(raw,dtype=bool)
    mask[40:50,50:60]=True
    regs,lab=extract_regions(mask,SizeGradeConfig(),"I",(0,0,140,120))
    for r in regs:
        r["_global_x0"]=r["_global_y0"]=0
    objs,old,bridges,full,edges,audit=reconstruct_continuous_visual(
        lab,raw,regs,[])
    assert len(objs)==1 and objs[0]["member_count"]==1
    assert not np.any(bridges)
    assert np.array_equal(full,old)
    assert objs[0]["original_area_px2"]==100
