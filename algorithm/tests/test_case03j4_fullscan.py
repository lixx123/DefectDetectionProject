"""Tests for J4 deterministic partition, halo edge rules and grouped outer boxes."""
import numpy as np
from scripts.run_case03j4_fullscan import core_axis,tiles,halo_rect
from src.visualization.case03j_object_boxes import (
    measure_visual_bbox,render_grouped_box_comparison,BoxStyle
)


def test_exact_full_frame_partition_and_boundary_tail():
    shape=(9200,11276)
    all_tiles=tiles(shape,256)
    assert len(all_tiles)==1620
    assert all_tiles[0]["core_xyxy"]==[0,0,256,256]
    assert all_tiles[-1]["core_xyxy"]==[11264,8960,11276,9200]
    assert sum((t["core_xyxy"][2]-t["core_xyxy"][0])*
               (t["core_xyxy"][3]-t["core_xyxy"][1]) for t in all_tiles)==9200*11276
    assert len(set(t["tile_id"] for t in all_tiles))==1620


def test_halo_grows_into_valid_source_at_narrow_right_edge():
    shape=(9200,11276)
    rect=tiles(shape,256)[-1]["core_xyxy"]
    l,t,r,b=halo_rect(rect,shape,64)
    assert r==11276 and b==9200
    assert r-l>=192 and b-t>=192
    assert l<=rect[0]<rect[2]<=r and t<=rect[1]<rect[3]<=b


def test_one_bbox_covering_three_disconnected_source_parts():
    obj=np.zeros((100,120),np.int32)
    bridge=np.zeros_like(obj)
    for y0,y1,x0,x1 in [(10,20,40,47),(40,45,10,100),(68,85,40,47)]:
        obj[y0:y1,x0:x1]=1
    bridge[20:40,42:45]=1
    bridge[45:68,42:45]=1
    bridge[41:43,40:50]=1
    comp=obj.copy()
    comp[(comp==0)&(bridge>0)]=1
    objects=[{"object_id":"T000_000_C0001","window_id":"T000_000",
              "size_grade":"LARGE","member_count":3,
              "original_area_px2":int(np.count_nonzero(obj)),
              "original_max_feret_px":84.,
              "inferred_bridge_pixels":int(np.count_nonzero(bridge)),
            }]
    rec=measure_visual_bbox(comp,obj,objects,(1000,2000,1120,2100))
    assert len(rec)==1
    assert rec[0]["display_bbox_x_global"]==1010
    assert rec[0]["display_bbox_y_global"]==2010
    assert rec[0]["display_bbox_width_px"]==90
    assert rec[0]["display_bbox_height_px"]==75
    assert not rec[0]["bbox_may_be_truncated"]
    raw=np.full(comp.shape,2000,np.uint16)
    fig=render_grouped_box_comparison(raw,obj,comp,bridge,rec,
          (1000,2000,1120,2100),"TEST",style=BoxStyle(zoom=1))
    assert fig.shape==(182,120*4,3)


def test_bbox_border_flag_and_never_count_bridge_as_area():
    orig=np.zeros((32,50),np.int32)
    orig[9:18,0:6]=1
    linked=orig.copy();linked[9:18,6:9]=1
    rows=measure_visual_bbox(linked,orig,[{
        "object_id":"T_C001","window_id":"T","size_grade":"MEDIUM",
        "member_count":1,"original_area_px2":54,
        "original_max_feret_px":9.,
        "inferred_bridge_pixels":27}],(15,20,65,52))
    assert rows[0]["bbox_may_be_truncated"]
    assert rows[0]["area_px2_original"]==54
    assert rows[0]["display_bbox_width_px"]==9
    assert rows[0]["source_bbox_width_px"]==6
