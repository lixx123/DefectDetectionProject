"""K8G display geometry: box width 1.5x but true size untouched."""
import math
import pytest
from src.detection.case03k8g_display_boxes import (
    DisplayBoxConfig,expand_bbox_xyxy,bbox_to_display_px,
    overlap_area,arrange_labels,shortened_id,label_lines)

def test_rectangle_1p5_center_and_width_height():
    old=(110.,220.,150.,240.)
    a=expand_bbox_xyxy(old,(1200,1000),1.5)
    assert a==(100.,215.,160.,245.)
    assert a[2]-a[0]==1.5*(old[2]-old[0])
    assert a[3]-a[1]==1.5*(old[3]-old[1])
    assert (a[0]+a[2])/2==(old[0]+old[2])/2
    assert (a[1]+a[3])/2==(old[1]+old[3])/2

def test_near_border_clipping_keeps_bbox_inside_source():
    a=expand_bbox_xyxy((0,0,10,20),(100,100),1.5)
    assert a==(0.,0.,12.5,25.)
    assert a[2]-a[0]<15 # clipping is allowed when original touches RAW edge
    assert a[3]-a[1]<30

def test_reject_invalid_source_or_factor():
    with pytest.raises(ValueError):expand_bbox_xyxy((-1,1,5,5),(100,100))
    with pytest.raises(ValueError):expand_bbox_xyxy((1,1,5,5),(100,100),float("nan"))
    with pytest.raises(ValueError):expand_bbox_xyxy((1,1,5,5),(100,100),.5)

def test_display_rectangle_rasterization_clipped():
    r=bbox_to_display_px((0.,0.,11276.,9200.),(11276,9200),(1410,1150),8)
    assert r==(0,0,1409,1149)
    tiny=bbox_to_display_px((10,10,11,11),(11276,9200),(1410,1150),8)
    assert tiny[2]>=tiny[0] and tiny[3]>=tiny[1]

def test_line_width_restriction():
    cfg=DisplayBoxConfig()
    cfg.validate()
    with pytest.raises(ValueError):DisplayBoxConfig(line_width_display_px=3).validate()

def test_label_place_no_overlap_when_space_available():
    rects=[(100,90,130,113),(300,200,350,250),(490,470,530,510)]
    labels=arrange_labels(rects,[(170,40)]*3,(1000,800))
    assert len(labels)==3
    assert all(overlap_area(a,b)==0 for a,b in zip(rects,labels))
    assert all(overlap_area(labels[i],labels[j])==0
               for i in range(3) for j in range(i+1,3))

def test_source_size_label_uses_existing_area_and_length_only():
    x={"source":"K8F_USER_APPROVED_K8E_OUTER",
       "supplement_K8E_group_id":"K8E_F2_B2_G006","size_grade":"LARGE",
       "area_detector_px2":348,"max_length_detector_image_um":75.523}
    l1,l2=label_lines(x)
    assert "G006" in l1 and "348 px²" in l1
    assert "75.5 μm" in l2 and "像面" in l2
    assert shortened_id(x).startswith("G006")

def test_frozen_j5_label_is_candidate_not_approved():
    x={"source":"FROZEN_J5_WORK","source_J5_global_defect_id":"DEFECT_01509",
       "size_grade":"MEDIUM","area_detector_px2":65,
       "max_length_detector_image_um":54.4}
    assert shortened_id(x)=="D01509"
    assert "中" in label_lines(x)[0]
