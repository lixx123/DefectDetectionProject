"""Case03-I size grade correctness / no deletion or fake physical size tests."""
import numpy as np,cv2,pytest
from src.detection.case03i_size_grade import (
    SizeGradeConfig,grade_size,max_feret_centers_px,extract_regions,
    render_marked_raw,
)


def test_provisional_grade_area_or_length():
    p=SizeGradeConfig()
    assert grade_size(5,2.,p)[0]=="SMALL"
    assert grade_size(40,2.,p)[0]=="MEDIUM"
    assert grade_size(4,15.,p)[0]=="MEDIUM"
    assert grade_size(250,3.,p)[0]=="LARGE"
    assert grade_size(4,45.,p)[0]=="LARGE"


def test_long_thin_scratches_grade_by_length():
    mask=np.zeros((100,100),dtype=bool)
    mask[15,10:70]=True
    cfg=SizeGradeConfig(medium_area_min_px2=200,
                        large_area_min_px2=500,
                        medium_length_min_px=15.,large_length_min_px=45.)
    records,lab=extract_regions(mask,cfg,"X",(200,400,300,500))
    assert len(records)==1
    assert records[0]["area_px2"]==60
    assert records[0]["max_feret_centers_px"]==59
    assert records[0]["size_grade"]=="LARGE"
    assert records[0]["grade_trigger"]=="length"
    assert records[0]["bbox_x_global"]==210
    assert records[0]["bbox_y_global"]==415
    assert np.count_nonzero(lab)==60


def test_pixel_components_not_physical_merged():
    m=np.zeros((50,60),bool)
    m[10:15,10:15]=True
    m[10:15,17:22]=True
    regions,_=extract_regions(m,SizeGradeConfig(),"R",(0,0,60,50))
    assert len(regions)==2
    assert sum(r["area_px2"] for r in regions)==50


def test_image_render_and_border_flag():
    m=np.zeros((100,100),bool)
    m[0:8,0:8]=True
    raw=np.full((100,100),2000,dtype=np.uint16)
    raw[m]=1600
    rs,lab=extract_regions(m,SizeGradeConfig(),"B",(900,500,1000,600))
    assert rs[0]["touches_window_border"]
    assert rs[0]["bbox_x_global"]==900
    img=render_marked_raw(raw,m,rs,lab,"RAW / B",roi_origin_xy=(900,500),zoom=2)
    assert img.shape==(278,200,3)
    assert int(img.max())>0


def test_foolproof_grade_input():
    with pytest.raises(ValueError):
        SizeGradeConfig(medium_area_min_px2=250,large_area_min_px2=40).validate()
    with pytest.raises(TypeError):
        extract_regions(np.zeros((20,20),dtype=np.uint8),SizeGradeConfig(),
                        "A",(0,0,20,20))


def test_single_pixel_length_and_zero_regions():
    assert max_feret_centers_px(np.array([[12,32]]))==1.
    m=np.zeros((20,20),bool)
    regs,lab=extract_regions(m,SizeGradeConfig(),"Z",(40,30,60,50))
    assert not regs and not np.count_nonzero(lab)
