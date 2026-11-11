"""Read-only detail/statistics/filter QA, using synthetic pixels and frozen packages."""
from copy import deepcopy
from pathlib import Path
import hashlib
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QCursor
from test_phase6_ui import qapp,window,vm,wait,image_frame
from domain import BandInfo,ROIInfo
from domain.common import BoundingBox,Point,ArtifactReference
from domain.enums import SizeGrade,GeometryStatus
from ui.models.result_view_model import ResultViewModel
from ui.models.statistics_view_model import StatisticsViewModel
from ui.models.defect_detail_view_model import DefectDetailViewModel
from ui.raw_image_provider import RawImageProvider


@pytest.fixture(autouse=True)
def isolate_cursor(qapp):
    QCursor.setPos(0,0)
    yield
    QCursor.setPos(0,0);qapp.processEvents()


@pytest.fixture
def multi(vm):
    base=vm.defects[0];result=vm.result
    rows=[('id-D',20,12,SizeGrade.SMALL,'1',None,'WORK'),
          ('id-A',100,40,SizeGrade.LARGE,'2','DARKSPOT','WORK'),
          ('id-C',30,7,SizeGrade.MEDIUM,'3','SCRATCH','REVIEW'),
          ('id-B',4,2,SizeGrade.SMALL,None,None,None)]
    defects=[]
    for i,(key,area,length,grade,band,kind,roi) in enumerate(rows):
        d=deepcopy(base);d.identity.defect_id=key
        d.geometry.bbox=BoundingBox(100+i*100,100+i*10,120+i*100,110+i*10)
        d.geometry.center=Point(110+i*100,105+i*10)
        d.geometry.area_px=area;d.geometry.area_um2=area*10.24
        d.geometry.length_px=length;d.geometry.length_um=length*3.2
        d.classification.size_grade=grade;d.classification.defect_type=kind
        d.location.band_id=band;d.location.roi_id=roi
        d.location.image_x,d.location.image_y=d.geometry.center.x,d.geometry.center.y
        defects.append(d)
    result.defects=defects
    s=result.statistics;s.total_defects=4;s.total_defect_area_px=154;s.total_defect_area_um2=1576.96
    s.count_by_type={'UNKNOWN':2,'DARKSPOT':1,'SCRATCH':1}
    s.count_by_size_grade={'SMALL':2,'MEDIUM':1,'LARGE':1}
    s.count_by_band={'1':1,'2':1,'3':1,'UNKNOWN':1}
    s.count_by_roi={'WORK':2,'REVIEW':1,'UNKNOWN':1}
    return ResultViewModel(result,vm.package_dir)


def show(window,multi):
    window.display_result(multi,image_frame())
    return window


def test_tabs_and_empty_states(window):
    assert [window.tabs.tabText(i) for i in range(3)]==['检测','疵病详情','统计分析']
    assert '请选择' in window.detail_page.position.text()
    assert '暂无检测结果' in window.statistics_page.status.text()
    assert window.table_model.rowCount()==0


@pytest.mark.parametrize('key,expected',[
 ('Defect ID','id-A'),('bbox（测量）','[200, 110, 220, 120)'),('面积 px²','100'),
 ('面积 μm²','1,024'),('Max Feret px','40'),('Max Feret μm','128'),
 ('Band ID','2'),('ROI ID','WORK'),('严重度等级','—')])
def test_selected_detail_fields(window,multi,key,expected):
    show(window,multi);window._viewer_selected('id-A')
    assert window.selection.defect_id=='id-A'
    assert window.detail_page.fields[key].text()==expected
    assert window.viewer.selected_id=='id-A'
    assert len(window.detail_page.group_boxes)==5


def test_none_type_missing_photometry_and_scale_explanation(window,multi):
    show(window,multi);window._viewer_selected('id-D')
    fields=window.detail_page.fields
    assert fields['类型'].text()==fields['mean DN'].text()==fields['宽度 px'].text()=='—'
    assert '非独立计量标定' in window.detail_page.calibration.text()
    assert 'Feret' in fields['Max Feret px'].toolTip()
    assert '显示框' in fields['面积 px²'].toolTip()


def test_invalid_calibration_hides_detail_and_statistics_physical_values(window,multi):
    multi.result.calibration_info.valid=False
    show(window,multi);window._viewer_selected('id-A')
    for key in ('面积 μm²','Max Feret μm','宽度 μm','等效直径 μm'):
        assert window.detail_page.fields[key].text()=='—'
    assert window.statistics_page.cards['total_area_um2'].text()=='—'
    assert window.detail_page.fields['面积 px²'].text()=='100'
    assert all(row['area_um2'] is None for row in window.statistics_page.models['size'].rows)


def test_statistics_summary_groups_and_percentages(window,multi):
    show(window,multi);stats=window.statistics_page.view_model
    assert stats.consistent
    s=stats.summary()
    assert s['total_defects']==4 and s['total_area_px']==154 and s['total_area_um2']==pytest.approx(1576.96)
    assert s['max_area_px']==100 and s['max_feret_px']==40
    assert s['defect_area_ratio'] is None
    for rows in (stats.by_size_grade(),stats.by_band(),stats.by_type(),stats.by_roi()):
        assert sum(r['count'] for r in rows)==4
        assert sum(r['percentage'] for r in rows)==pytest.approx(100)
        assert sum(r['area_px'] for r in rows)==154
    assert next(r['count'] for r in stats.by_type() if r['label']=='未分类')==2
    assert len(window.statistics_page.charts)==2


@pytest.mark.parametrize('count',[3,4,5])
def test_dynamic_band_statistics(window,multi,count):
    multi.result.roi_info=ROIInfo(band_count=count,band_list=[BandInfo(band_id=str(i+1)) for i in range(count)])
    show(window,multi);rows=window.statistics_page.view_model.by_band()
    assert len([r for r in rows if r['key']!='UNKNOWN'])==count
    assert sum(r['count'] for r in rows)==4


def test_statistics_detects_inconsistency_without_mutation(multi):
    multi.result.statistics.total_defect_area_px=1
    before=deepcopy(multi.result.to_dict())
    stats=StatisticsViewModel(multi.result)
    assert not stats.consistent and 'total_defect_area_px' in stats.errors[0]
    assert stats.summary()['total_area_px']==1
    assert multi.result.to_dict()==before


def test_work_ratio_uses_work_pixels_and_raw_precision(multi):
    from domain.roi import RegionInfo
    multi.result.roi_info.status=GeometryStatus.VALID
    multi.result.roi_info.work_region=RegionInfo(region_id='WORK',pixel_count=1000)
    assert StatisticsViewModel(multi.result).summary()['defect_area_ratio']==pytest.approx(.154)
    multi.result.roi_info.status=GeometryStatus.INVALID
    assert StatisticsViewModel(multi.result).summary()['defect_area_ratio'] is None


def test_all_none_types_are_one_unclassified_group(multi):
    for defect in multi.defects:defect.classification.defect_type=None
    multi.result.statistics.count_by_type={'UNKNOWN':4}
    stats=StatisticsViewModel(multi.result)
    assert stats.consistent and stats.by_type()[0]['label']=='未分类'
    assert stats.by_type()[0]['count']==4 and stats.by_type()[0]['percentage']==100


def test_missing_group_measurement_is_not_zero_filled(multi):
    multi.defects[0].geometry.area_px=None
    multi.result.statistics.total_defect_area_px=None
    stats=StatisticsViewModel(multi.result)
    assert stats.summary()['total_area_px'] is None
    assert next(r for r in stats.by_size_grade() if r['key']=='SMALL')['area_px'] is None


def test_local_mask_hash_mismatch_is_rejected(multi,tmp_path):
    path=tmp_path/'bad.npz';path.write_bytes(b'corrupt')
    multi.defects[0].geometry.mask_reference=ArtifactReference(path='bad.npz',sha256='0'*64)
    with pytest.raises(ValueError,match='SHA256'):
        DefectDetailViewModel(multi,'id-D').local_view(2)


@pytest.mark.parametrize('filter_name,value,expected',[
 ('grade','SMALL',{'id-D','id-B'}),('band','2',{'id-A'}),('defect_type','UNKNOWN',{'id-D','id-B'})])
def test_filter_table_overlay_and_clear(window,multi,filter_name,value,expected):
    before=deepcopy(multi.result.to_dict());show(window,multi)
    window.proxy.set_filters(**{filter_name:value})
    assert set(window._visible_ids())==set(window.viewer.overlays)==expected
    assert window.statistics_page.view_model.summary()['total_defects']==4
    window.clear_filters()
    assert window.proxy.rowCount()==4 and len(window.viewer.overlays)==4
    assert multi.result.to_dict()==before


@pytest.mark.parametrize('column',[0,2,5,7,9])
def test_sorting_selection_and_detail_navigation(window,multi,column):
    show(window,multi);window.proxy.sort(column,Qt.SortOrder.AscendingOrder)
    ids=window._visible_ids()
    window.table.setCurrentIndex(window.proxy.index(0,0))
    assert window.selection.defect_id==ids[0] and window.viewer.selected_id==ids[0]
    window._navigate_defect(1)
    assert window.selection.defect_id==ids[1] and window.detail_page.fields['Defect ID'].text()==ids[1]
    window._navigate_defect(-1)
    assert window.selection.defect_id==ids[0]
    if column==5:assert ids==['id-B','id-D','id-C','id-A']


def test_navigation_uses_filtered_order_and_retains_selection_across_tabs(window,multi,qapp):
    show(window,multi);window.proxy.set_filters(grade='SMALL');window.proxy.sort(5,Qt.SortOrder.DescendingOrder)
    window.table.setCurrentIndex(window.proxy.index(0,0))
    assert window.selection.defect_id=='id-D'
    window.tabs.setCurrentIndex(1);wait(qapp,lambda:not window.controller.busy)
    assert window.selection.defect_id=='id-D'
    window._navigate_defect(1);wait(qapp,lambda:not window.controller.busy)
    assert window.selection.defect_id=='id-B'
    assert not window.detail_page.next.isEnabled()
    window.tabs.setCurrentIndex(0)
    assert window.table.currentIndex().data(window.table_model.DefectIdRole)=='id-B'


def test_filter_hiding_selected_object_clears_stale_detail(window,multi):
    show(window,multi);window._viewer_selected('id-A')
    window.proxy.set_filters(grade='MEDIUM')
    assert window.selection.defect_id in (None,'id-C')
    assert 'id-A' not in window.detail_page.position.text()
    assert set(window.viewer.overlays)=={'id-C'}


def test_single_object_navigation_and_zero_defects(window,vm):
    window.display_result(vm,image_frame());window.table.setCurrentIndex(window.proxy.index(0,0))
    assert not window.detail_page.previous.isEnabled() and not window.detail_page.next.isEnabled()
    result=deepcopy(vm.result);result.defects=[];result.statistics.total_defects=0
    result.statistics.total_defect_area_px=0;result.statistics.total_defect_area_um2=0
    result.statistics.count_by_size_grade={}
    window.display_result(ResultViewModel(result,vm.package_dir),image_frame())
    assert window.statistics_page.cards['total_defects'].text()=='0'
    assert '暂无疵病' in window.detail_page.position.text()
    assert not window.statistics_page.charts['size'].rows
    assert window.proxy.rowCount()==0


@pytest.mark.parametrize('mode',[0,1,2])
def test_local_raw_pixels_mask_and_measurement_immutability(window,multi,tmp_path,mode):
    raw_path=tmp_path/'synthetic.raw'
    ys,xs=np.indices((800,1000),dtype=np.uint16);pixels=((xs+3*ys)%4096).astype('>u2')
    raw_path.write_bytes(pixels.tobytes());raw=RawImageProvider(raw_path,1000,800)
    window.raw=raw
    defect=multi.defects[0];path=tmp_path/'mask.npz'
    mask=np.ones((10,20),np.uint8);np.savez_compressed(path,mask=mask)
    defect.geometry.mask_reference=ArtifactReference(path='mask.npz',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    before=deepcopy(multi.result.to_dict())
    model=DefectDetailViewModel(multi,'id-D');local=model.local_view(mode,raw)
    x,y=local.origin
    assert local.source=='真实 RAW 像素'
    assert local.frame.image.pixelColor(3,7).red()==int(int(pixels[y+7,x+3])*255/4095)
    assert bool(local.overlays)==(mode>0) and bool(local.frame.layers)==(mode==2)
    if mode==2:
        assert local.frame.layers[0].pixelColor(40,40).alpha()==130
        assert local.frame.layers[0].pixelColor(0,0).alpha()==0
    assert multi.result.to_dict()==before


def test_local_no_raw_preview_and_missing_resources(multi,tmp_path):
    detail=DefectDetailViewModel(multi,'id-A')
    local=detail.local_view(2)
    assert '局部原图不可用' in local.frame.message
    assert 'mask 资源不可用' in local.frame.message
    path=tmp_path/'preview.png';image=QImage(1000,800,QImage.Format.Format_Grayscale8);image.fill(77);image.save(str(path))
    multi.result.intermediate_results.original_preview=ArtifactReference(path='preview.png',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    local=detail.local_view(0)
    assert 'preview' in local.source and local.frame.image.pixelColor(0,0).red()==77


def test_detail_page_async_load_and_clear(window,multi,qapp):
    show(window,multi);window._viewer_selected('id-A');window.tabs.setCurrentIndex(1)
    wait(qapp,lambda:not window.controller.busy)
    assert window.detail_page.viewer.base_item is not None
    assert '局部原图不可用' in window.detail_page.image_status.text()
    window.clear_result()
    assert window.selection.defect_id is None and window.detail_page.detail_vm is None
    assert window.statistics_page.view_model is None and not window.detail_page.viewer.scene().items()


def test_rapid_selection_hides_old_field_groups_immediately(window,multi):
    from PySide6.QtWidgets import QGroupBox
    show(window,multi)
    for key in ['id-A','id-B','id-C','id-D']*3:window._viewer_selected(key)
    current=set(window.detail_page.group_boxes)
    assert len(current)==5
    old=[box for box in window.detail_page.fields_widget.findChildren(QGroupBox) if box not in current]
    assert old and all(box.isHidden() for box in old)


@pytest.mark.golden
@pytest.mark.parametrize('result_id,count,area',[
 ('8a363da8-7a3b-4c77-84cf-d13a375c3b15',36,20356),
 ('f15a42a0-c022-47eb-93d8-d0d191939589',35,17709)])
def test_real_history_detail_statistics_and_filters(qapp,tmp_path,result_id,count,area):
    from infrastructure.repositories import JsonResultRepository
    from ui.controllers.inspection_controller import InspectionController
    from ui.main_window import MainWindow
    from regression.golden import no_engine_execution
    from regression.comparator import digest
    root=Path(__file__).resolve().parents[1];repo=JsonResultRepository(root/'output/phase4_validation/repository')
    w=MainWindow(InspectionController(repo,runtime_root=tmp_path/'runtime'));w.show()
    with no_engine_execution():
        try:
            w.load_history(result_id);wait(qapp,lambda:not w.controller.busy,timeout=120000)
            result=w.view_model.result;before=digest(result.to_dict())
            s=w.statistics_page.view_model
            assert s.consistent and s.summary()['total_defects']==count and s.summary()['total_area_px']==area
            assert sum(r['count'] for r in s.by_band())==sum(r['count'] for r in s.by_size_grade())==sum(r['count'] for r in s.by_type())==count
            w.proxy.sort(5,Qt.SortOrder.AscendingOrder)
            # Read every final defect's fields through the shared selection.
            for i in range(count):
                w.table.setCurrentIndex(w.proxy.index(i,0))
                assert w.detail_page.fields['Defect ID'].text()==w.selection.defect_id
            w.tabs.setCurrentIndex(1);wait(qapp,lambda:not w.controller.busy)
            assert w.detail_page.viewer.mask_items and '局部原图不可用' in w.detail_page.image_status.text()
            w.tabs.setCurrentIndex(0);w.proxy.set_filters(grade='LARGE')
            assert w.proxy.rowCount()==result.statistics.count_by_size_grade['LARGE']
            assert len(w.viewer.overlays)==w.proxy.rowCount()
            w.clear_filters();assert w.proxy.rowCount()==count
            assert digest(result.to_dict())==before
        finally:
            wait(qapp,lambda:not w.controller.busy,timeout=120000);w.close()
