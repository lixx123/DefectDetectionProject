"""Offscreen interaction and lifecycle QA, with no reference engine execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from copy import deepcopy
from pathlib import Path
import threading
import numpy as np
import pytest
from PySide6.QtCore import Qt, QPoint, QTimer, QThread
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication
from domain import InspectionResult, Defect, DefectIdentity, DefectGeometry, BandInfo, ROIInfo
from domain.common import BoundingBox, Point
from domain.enums import SizeGrade, PipelineMode, FallbackReason
from ui.main_window import MainWindow, HistoryDialog
from ui.image_viewer import ImageViewer
from ui.models.result_view_model import ResultViewModel, DisplayFrame, ViewMode, ImageCache
from ui.models.defect_table_model import DefectTableModel
from ui.raw_image_provider import RawImageProvider
from ui.controllers.inspection_controller import InspectionController
from infrastructure.repositories import JsonResultRepository


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


def wait(qapp, predicate, timeout=60000):
    end = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)  # Release Python's GIL while workers perform Python I/O.
    assert predicate(), 'Qt operation did not finish'


@pytest.fixture
def vm(tmp_path):
    r = InspectionResult(task_id='ui-fixture')
    r.input_info.width_px, r.input_info.height_px = 1000, 800
    d = Defect(identity=DefectIdentity(defect_id='physical-object-B'),
               geometry=DefectGeometry(bbox=BoundingBox(200, 150, 240, 180),
                  center=Point(220, 165), area_px=20, area_um2=204.8, length_px=12, length_um=38.4))
    d.location.image_x, d.location.image_y = 220, 165
    d.classification.size_grade = SizeGrade.SMALL
    r.defects = [d]
    r.roi_info = ROIInfo(band_count=4, band_list=[BandInfo(band_id=str(i)) for i in range(1, 5)])
    r.statistics.total_defects = 1
    return ResultViewModel(r, tmp_path)


@pytest.fixture
def window(qapp, tmp_path):
    c = InspectionController(JsonResultRepository(tmp_path/'formal'), runtime_root=tmp_path/'runtime')
    w = MainWindow(c)
    w.show()
    qapp.processEvents()
    yield w
    wait(qapp, lambda: not c.busy)
    w.close()
    qapp.processEvents()


def image_frame():
    image = QImage(1000, 800, QImage.Format.Format_Grayscale8)
    image.fill(75)
    return DisplayFrame(image, 1000, 800)


def test_main_window_empty_smoke(window):
    assert window.isVisible() and isinstance(window.viewer, ImageViewer)
    assert window.table_model.rowCount() == 0
    assert '打开 RAW' in window.summary.text()
    assert not window.start_action.isEnabled() and not window.save_action.isEnabled()
    assert window.open_action.shortcut().toString() == 'Ctrl+O'
    assert window.save_action.shortcut().toString() == 'Ctrl+S'


@pytest.mark.parametrize('operation', ['fit', 'actual_size', 'zoom_in', 'zoom_out', 'coordinate'])
def test_viewer_coordinates_and_zoom(window, operation):
    v = window.viewer
    v.set_frame(image_frame(), fit=True)
    if operation == 'fit':
        assert 0 < v.zoom <= 2
    elif operation == 'actual_size':
        v.actual_size()
        assert v.zoom == 1
        assert '100.0%' in window.pointer.text()
    elif operation == 'zoom_in':
        old = v.zoom
        v.zoom_by(1.25)
        assert v.zoom == pytest.approx(old * 1.25)
    elif operation == 'zoom_out':
        old = v.zoom
        v.zoom_by(0.8)
        assert v.zoom == pytest.approx(old * 0.8)
    else:
        v.actual_size()
        p = v.mapFromScene(220, 165)
        point = v.mapToScene(p)
        assert abs(point.x() - 220) <= 1 and abs(point.y() - 165) <= 1


def test_wheel_anchor_and_drag(window, qapp):
    v = window.viewer
    v.set_frame(image_frame(), fit=True)
    v.actual_size()
    anchor = v.viewport().rect().center() + QPoint(20, 15)
    before = v.mapToScene(anchor)
    v.zoom_by(1.25, anchor)
    after = v.mapToScene(anchor)
    assert abs(before.x()-after.x()) < 2 and abs(before.y()-after.y()) < 2
    old = v.horizontalScrollBar().value()
    QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, pos=anchor)
    QTest.mouseMove(v.viewport(), anchor + QPoint(30, 0), 20)
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, pos=anchor + QPoint(30, 0))
    assert v.horizontalScrollBar().value() != old


def test_overlay_add_select_clear_and_measurement_immutable(window, vm):
    before = deepcopy(vm.result.to_dict())
    window.display_result(vm, image_frame())
    v = window.viewer
    assert len(v.overlays) == 1
    v._clicked('physical-object-B')
    assert v.selected_id == 'physical-object-B'
    v.show_boxes(False)
    assert not v.overlays['physical-object-B'].isVisible()
    v.show_ids(True)
    assert v.id_labels['physical-object-B'].isVisible()
    v.select_defect('physical-object-B', center=True)
    assert vm.result.to_dict() == before
    window.clear_result()
    assert not v.overlays and not v.id_labels and not v.scene().items()
    assert window.table_model.rowCount() == 0 and window.cache.frame is None


def test_table_fields_none_numeric_sort_and_id(window, vm):
    m = window.table_model
    m.set_result(vm)
    assert m.rowCount() == 1 and m.columnCount() == 11
    assert m.data(m.index(0, 1)) == '—'
    assert m.data(m.index(0, 5), m.SortRole) == 20
    assert m.data(m.index(0, 8)) == '38.4'
    assert m.data(m.index(0, 0), m.DefectIdRole) == 'physical-object-B'
    assert m.headerData(7, Qt.Orientation.Horizontal) == 'Feret px'


@pytest.mark.parametrize('valid', [True, False])
def test_historical_calibration_not_global_setting(window, vm, valid):
    vm.result.calibration_info.spatial_scale_um_per_px = 2.8
    vm.result.calibration_info.valid = valid
    window.display_result(vm, image_frame())
    # Stored 38.4 is displayed verbatim, not recalculated using either 2.8 or current YAML.
    assert window.table_model.data(window.table_model.index(0, 8)) == ('38.4' if valid else '—')
    assert ('2.800' if valid else '尺度：—') in window.calibration.text()
    assert '划痕中心线' not in vm.detail('physical-object-B')


def test_table_viewer_bidirectional_actual_click(window, vm, qapp):
    window.display_result(vm, image_frame())
    window.table.setCurrentIndex(window.proxy.index(0, 0))
    assert window.viewer.selected_id == 'physical-object-B'
    assert 'Max Feret' in window.detail.text()
    window.table.clearSelection()
    v = window.viewer
    item = v.overlays['physical-object-B']
    pos = v.mapFromScene(item.rect().topLeft())
    spy = QSignalSpy(v.defect_selected)
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    qapp.processEvents()
    assert spy.count() == 1
    assert window.table.selectionModel().selectedRows()
    assert 'physical-object-B' in window.detail.text()


@pytest.mark.parametrize('mode', list(ViewMode))
def test_all_views_missing_resources_and_no_raw(window, vm, mode, qapp):
    window.display_result(vm, image_frame())
    window.view_selector.setCurrentText(mode)
    if mode == ViewMode.FINAL:
        window._switch_view(mode)
    wait(qapp, lambda: not window.controller.busy)
    text = window.resource_status.text()
    assert '原始图像不可用' in text if mode == ViewMode.ORIGINAL else '该资源不可用' in text
    assert len(window.viewer.overlays) == 1
    window._pointer(10, 20, None, 1)
    assert 'DN：—' in window.pointer.text()


@pytest.mark.parametrize('count', [3, 4, 5])
def test_dynamic_band_count_and_labels(window, vm, count):
    vm.result.roi_info = ROIInfo(band_count=count, band_list=[
        BandInfo(band_id=str(i), bbox=BoundingBox(10, 10*i, 200, 10*i+9)) for i in range(1, count+1)])
    frame = vm.frame(ViewMode.BAND)
    window.display_result(vm, frame)
    assert len(window.viewer.band_labels) == count
    assert f'{count} Bands' in window.summary.text()
    for word in ('WORK', 'NONWORK', 'REVIEW'):
        assert word in window.bands.text()


def test_fallback_is_success_ui(window, vm):
    e = vm.result.execution_info
    e.final_mode, e.fallback_used, e.fallback_reason = PipelineMode.FULL, True, FallbackReason.QA_FAILED
    window.display_result(vm, image_frame())
    assert '已自动切换至全图模式' in window.summary.text()
    assert 'FULL' in window.summary.text() and 'QA_FAILED' in window.summary.text()


def test_switch_result_clears_selection_detail_and_cache(window, vm):
    window.display_result(vm, image_frame())
    window.viewer._clicked('physical-object-B')
    new = deepcopy(vm.result)
    new.defects = []
    window.display_result(ResultViewModel(new, vm.package_dir), image_frame())
    assert not window.viewer.overlays and window.viewer.selected_id is None
    assert not window.table.selectionModel().selectedRows()
    assert 'physical-object-B' not in window.detail.text()
    window.cache.clear()
    assert window.cache.frame is None


def test_final_mask_independent_layer_toggle_and_integrity(window, vm, tmp_path):
    import hashlib
    from domain.common import ArtifactReference
    p = tmp_path/'final.png'
    mask = QImage(1000, 800, QImage.Format.Format_Grayscale8)
    mask.fill(255)
    assert mask.save(str(p))
    ref = ArtifactReference(path='final.png', sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    vm.result.intermediate_results.final_mask = ref
    frame = vm.frame(ViewMode.FINAL)
    assert frame.image.pixelColor(10, 10).red() == 28
    assert len(frame.layers) == 1
    window.display_result(vm, frame)
    assert len(window.viewer.mask_items) == 1
    off = vm.frame(ViewMode.FINAL, final_mask=False)
    assert not off.layers
    window._apply_frame(off)
    assert not window.viewer.mask_items
    p.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='校验失败'):
        vm.frame(ViewMode.FINAL)


def test_raw_original_detail_crop_and_pointer_dn(window, tmp_path, qapp):
    path = tmp_path/'small.raw'
    path.write_bytes(np.full((800, 1000), 1234, dtype='>u2').tobytes())
    raw = RawImageProvider(path, 1000, 800)
    window.raw = raw
    v = window.viewer
    v.raw_provider = raw
    v.detail_enabled = True
    v.set_frame(DisplayFrame(raw.thumbnail(), 1000, 800), fit=True)
    v.actual_size()
    v._refresh_raw_detail()
    wait(qapp, lambda: not window.controller.busy and v.detail_item is not None)
    assert v.detail_item is not None
    assert v.detail_item.pixmap().width() <= 1000
    QTest.mouseMove(v.viewport(), v.mapFromScene(400, 400))
    qapp.processEvents()
    wait(qapp, lambda: not window.controller.busy and ('DN：1,234' in window.pointer.text() or 'DN：1234' in window.pointer.text()))
    assert 'DN：1,234' in window.pointer.text() or 'DN：1234' in window.pointer.text()


def test_raw_readonly_dn_thumbnail_clear(tmp_path):
    path = tmp_path/'mini.raw'
    data = np.arange(144, dtype='>u2').tobytes()
    path.write_bytes(data)
    provider = RawImageProvider(path, 12, 12)
    assert provider.dn(2, 3) == 38
    assert provider.dn(-1, 2) is None
    assert provider.thumbnail().format() == QImage.Format.Format_Grayscale8
    assert path.read_bytes() == data
    assert provider.crop(2, 3, 4, 5).size().width() == 2
    provider.clear()
    assert provider.dn(2, 3) is None
    with pytest.raises(ValueError):
        RawImageProvider(path)


@pytest.mark.parametrize('fail', [False, True])
def test_worker_signals_responsive_buttons_and_close_safety(window, qapp, fail):
    c = window.controller
    ids, ticks = [], []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    ok, bad = QSignalSpy(c.completed), QSignalSpy(c.error)
    def slow():
        ids.append(threading.get_ident())
        time.sleep(0.15)
        if fail:
            raise ValueError('fixture failure')
        return 'done'
    assert c.submit('fixture', slow)
    assert not c.submit('duplicate', slow)
    assert not window.open_action.isEnabled() and not window.save_action.isEnabled()
    assert not window.close()
    wait(qapp, lambda: not c.busy)
    timer.stop()
    assert ids == [ids[0]] and ids[0] != threading.get_ident()
    assert len(ticks) >= 2
    assert ok.count() == (0 if fail else 1) and bad.count() == (1 if fail else 0)
    assert window.open_action.isEnabled() and not window.progress.isVisible()
    if fail:
        assert 'fixture failure' in window.resource_status.text()
        assert 'Traceback' not in window.resource_status.text()
        assert (c.runtime_root/'gui_errors.log').is_file()


def test_detection_service_staging_then_explicit_formal_save(window, qapp, tmp_path):
    from test_phase3_adapter import detector
    from application.inspection_service import InspectionService
    from domain.configuration import InspectionConfig
    raw = tmp_path/'26 (1).raw'
    raw.write_bytes(np.arange(144, dtype='>u2').tobytes())
    detector_root = tmp_path/'fake'
    detector_root.mkdir()
    d, adapter = detector(detector_root)
    thread_ids = []
    ui_thread_ids = []
    class FakeService:
        def __init__(self, repository):
            self.service = InspectionService(d, repository)
        def inspect_and_save(self, path):
            thread_ids.append(threading.get_ident())
            return self.service.inspect_and_save(path, InspectionConfig())
    c = window.controller
    c.completed.connect(lambda *_: ui_thread_ids.append(threading.get_ident()))
    c.service_factory = FakeService
    c.detect(raw)
    wait(qapp, lambda: not c.busy)
    assert window.view_model is not None and window.table_model.rowCount() == 1
    assert not c.repository.list_results() and not window.saved
    first_id = window.view_model.result.result_id
    assert thread_ids[0] != threading.get_ident()
    assert ui_thread_ids == [threading.get_ident()]
    window._request_filter_metadata=lambda:("QA_FILTER", "")
    window._save()
    wait(qapp, lambda: not c.busy)
    assert window.saved and len(c.repository.list_results()) == 1
    assert c.repository.verify(first_id).status == 'PASS'
    c.detect(raw)
    wait(qapp, lambda: not c.busy)
    assert window.view_model.result.result_id != first_id
    assert len(c.repository.list_results()) == 1
    assert adapter.calls == [PipelineMode.ROI_BH, PipelineMode.ROI_BH]  # fake adapter only


@pytest.mark.golden
@pytest.mark.parametrize('result_id,count', [
    ('8a363da8-7a3b-4c77-84cf-d13a375c3b15', 36),
    ('f15a42a0-c022-47eb-93d8-d0d191939589', 35)])
def test_real_history_repository_display_without_raw(qapp, tmp_path, result_id, count):
    root = Path(__file__).resolve().parents[1]
    repo = JsonResultRepository(root/'output/phase4_validation/repository')
    c = InspectionController(repo, runtime_root=tmp_path/'runtime')
    window = MainWindow(c)
    window.show()
    try:
        window.load_history(result_id)
        wait(qapp, lambda: not c.busy, timeout=90000)
        assert window.table_model.rowCount() == count
        assert len(window.viewer.overlays) == count
        assert len(window.view_model.result.roi_info.band_list) == 4
        assert window.raw is None
        for mode in (ViewMode.BAND, ViewMode.ROI):
            window.view_selector.setCurrentText(mode)
            wait(qapp, lambda: not c.busy, timeout=90000)
            assert '该资源不可用' not in window.resource_status.text()
        window.table.setCurrentIndex(window.proxy.index(0, 0))
        assert window.viewer.selected_id is not None and 'Max Feret' in window.detail.text()
        assert window.calibration.text().startswith('尺度：3.200')
    finally:
        wait(qapp, lambda: not c.busy, timeout=90000)
        window.close()
