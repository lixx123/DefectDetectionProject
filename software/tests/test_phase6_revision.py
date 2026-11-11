"""Display-only revision QA; original Phase 6 tests remain unchanged."""
import hashlib
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_phase6_ui import qapp, window, vm, wait
from ui.models.result_view_model import ViewMode, ResultViewModel, display_bbox
from ui.raw_image_provider import RawImageProvider
from domain.common import ArtifactReference, BoundingBox


@pytest.fixture(autouse=True)
def isolate_mouse_position(qapp):
    """Do not leave an identical global cursor position for older QTest cases."""
    from PySide6.QtGui import QCursor
    QCursor.setPos(0, 0)
    yield
    QCursor.setPos(0, 0)
    qapp.processEvents()


def add_raw_and_mask(window, vm, tmp_path):
    path = tmp_path/'display_only.raw'
    values = np.full((800, 1000), 1234, dtype='>u2')
    path.write_bytes(values.tobytes())
    raw = RawImageProvider(path, 1000, 800)
    window.raw, window.raw_path = raw, path
    mask = QImage(1000, 800, QImage.Format.Format_Grayscale8)
    mask.fill(255)
    dest = tmp_path/'mask.png'
    assert mask.save(str(dest))
    vm.result.intermediate_results.final_mask = ArtifactReference(
        path='mask.png', sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    window.display_result(vm)
    return raw


@pytest.mark.parametrize('mode', [ViewMode.ORIGINAL, ViewMode.FINAL])
def test_detail_real_pixels_and_dn_in_both_modes(window, vm, tmp_path, qapp, mode):
    raw = add_raw_and_mask(window, vm, tmp_path)
    if mode == ViewMode.ORIGINAL:
        window.view_selector.setCurrentText(mode)
        wait(qapp, lambda: not window.controller.busy)
    window.viewer.actual_size()
    window.viewer._refresh_raw_detail()
    wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
    item = window.viewer.detail_item
    assert item is not None and item.zValue() == -9
    assert item.pixmap().toImage().pixelColor(0, 0).red() == int(1234*255/4095)
    if mode == ViewMode.FINAL:
        assert window.viewer.mask_items and all(i.isVisible() for i in window.viewer.mask_items)
        assert -10 < item.zValue() < window.viewer.mask_items[0].zValue() < window.viewer.overlays['physical-object-B'].zValue()
    QTest.mouseMove(window.viewer.viewport(), window.viewer.mapFromScene(400, 400))
    qapp.processEvents()
    wait(qapp, lambda: not window.controller.busy and 'DN：1234' in window.pointer.text())
    assert 'DN：1234' in window.pointer.text()
    assert raw.dn(400, 400) == 1234


def test_mask_toggle_keeps_final_raw_detail(window, vm, tmp_path, qapp):
    add_raw_and_mask(window, vm, tmp_path)
    window.viewer.actual_size()
    window.viewer._refresh_raw_detail()
    wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
    assert window.viewer.mask_items and window.viewer.detail_item is not None
    window.mask_action.setChecked(False)
    wait(qapp, lambda: not window.controller.busy)
    window.viewer._refresh_raw_detail()
    wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
    assert not window.viewer.mask_items and window.viewer.detail_item is not None
    window.mask_action.setChecked(True)
    wait(qapp, lambda: not window.controller.busy)
    window.viewer._refresh_raw_detail()
    wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
    assert window.viewer.mask_items and window.viewer.detail_item is not None


def test_final_without_raw_is_still_displayable(window, vm):
    window.display_result(vm)
    window.viewer.actual_size()
    window.viewer._refresh_raw_detail()
    assert window.viewer.detail_item is None
    assert window.viewer.overlays and window.viewer.base_item is not None
    assert '原图不可用' in window.resource_status.text()


def test_display_scale_one_point_five():
    assert display_bbox((100, 100, 120, 110), 1000, 800) == (95, 97.5, 125, 112.5)


@pytest.mark.parametrize('size', [1, 2])
def test_tiny_display_six_pixels_detail_retains_measurement(window, vm, size):
    vm.defects[0].geometry.bbox = BoundingBox(100, 100, 100+size, 100+size)
    window.display_result(vm)
    overlay = vm.overlays[0]
    assert overlay.display_bbox[2]-overlay.display_bbox[0] == 6
    assert overlay.display_bbox[3]-overlay.display_bbox[1] == 6
    assert overlay.measurement_bbox == overlay.bbox == (100, 100, 100+size, 100+size)
    assert f'100, 100, {100+size}, {100+size}' in vm.detail('physical-object-B')


@pytest.mark.parametrize('bbox', [(0,0,1,1), (999,799,1000,800), (0,799,1,800), (999,0,1000,1)])
def test_display_clamped_to_image(bbox):
    x0,y0,x1,y1 = display_bbox(bbox, 1000, 800)
    assert 0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 800


def test_selection_uses_measurement_center_even_when_display_clamped(window, vm, monkeypatch):
    vm.defects[0].geometry.bbox = BoundingBox(0, 0, 1, 1)
    window.display_result(vm)
    calls=[]
    monkeypatch.setattr(window.viewer, 'centerOn', lambda x,y: calls.append((x,y)))
    window.viewer.select_defect('physical-object-B', center=True)
    assert calls == [(0.5,0.5)]


def test_overlay_interaction_leaves_full_measurements_unchanged(window, vm, qapp):
    before = deepcopy(vm.result.to_dict())
    values, detail = vm.values(0), vm.detail('physical-object-B')
    window.display_result(vm)
    item = window.viewer.overlays['physical-object-B']
    assert item.rect().width() == 60 and item.rect().height() == 45
    window.viewer.actual_size()
    QTest.mouseClick(window.viewer.viewport(), Qt.MouseButton.LeftButton,
                     pos=window.viewer.mapFromScene(item.rect().topLeft()))
    window.viewer.zoom_by(1.25)
    window.viewer.select_defect('physical-object-B', center=True)
    qapp.processEvents()
    assert vm.result.to_dict() == before and vm.values(0) == values and vm.detail('physical-object-B') == detail


def test_refresh_replaces_detail_and_large_crop_keeps_thumbnail(window, vm, tmp_path, monkeypatch, qapp):
    add_raw_and_mask(window, vm, tmp_path)
    v=window.viewer
    v.actual_size()
    for _ in range(20):
        v._refresh_raw_detail()
        wait(qapp, lambda: not window.controller.busy and v.detail_item is not None)
        assert v.detail_item is not None
        assert sum(i.zValue()==-9 for i in v.scene().items()) == 1
    # Force an oversized visible region, without allocating a large image.
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QRectF
    v.image_rect = QRectF(0,0,10000,10000)
    window.raw.width=window.raw.height=10000
    monkeypatch.setattr(v,'mapToScene',lambda _: QPolygonF(QRectF(0,0,5000,5000)))
    monkeypatch.setattr(window.raw,'crop',lambda *_: pytest.fail('oversized crop attempted'))
    v._refresh_raw_detail()
    assert v.detail_item is None and v.base_item is not None


@pytest.mark.parametrize('mode',[ViewMode.BAND, ViewMode.ROI])
def test_band_roi_never_load_raw_detail(window, vm, tmp_path, qapp, mode):
    add_raw_and_mask(window, vm, tmp_path)
    window.viewer.actual_size()
    window.viewer._refresh_raw_detail()
    wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
    assert window.viewer.detail_item is not None
    window.view_selector.setCurrentText(mode)
    wait(qapp,lambda:not window.controller.busy)
    window.viewer._refresh_raw_detail()
    assert not window.viewer.detail_enabled and window.viewer.detail_item is None


def test_formal_window_and_application_names(window):
    assert window.windowTitle() == '滤光片表面疵病自动检测与分析软件 V1.0.0'
    assert QApplication.applicationName() == '滤光片表面疵病自动检测与分析软件'


@pytest.mark.golden
@pytest.mark.parametrize('mode', [ViewMode.ORIGINAL, ViewMode.FINAL])
def test_synthetic_gradient_raw_detail_golden(window, vm, tmp_path, qapp, mode):
    """Permanent coverage uses generated pixels, never an external large RAW."""
    from regression.golden import no_engine_execution
    with no_engine_execution():
        add_raw_and_mask(window, vm, tmp_path)
        window.raw.clear()
        path=tmp_path/'gradient.raw'
        ys,xs=np.indices((800,1000),dtype=np.uint16)
        values=((xs*3+ys*5)%4096).astype('>u2')
        path.write_bytes(values.tobytes())
        original_hash=hashlib.sha256(path.read_bytes()).hexdigest()  # Small synthetic fixture only.
        window.raw=RawImageProvider(path,1000,800)
        before=deepcopy(vm.result.to_dict())
        window.display_result(vm)
        window.view_selector.setCurrentText(mode)
        wait(qapp,lambda:not window.controller.busy)
        window.viewer.actual_size()
        window.viewer.select_defect('physical-object-B',center=True)
        window.viewer._refresh_raw_detail()
        wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
        item=window.viewer.detail_item
        assert item is not None
        image=item.pixmap().toImage()
        x,y=int(item.pos().x()),int(item.pos().y())
        for dx,dy in [(0,0),(7,11),(image.width()-1,image.height()-1)]:
            dn=int(values[y+dy,x+dx])
            assert window.raw.dn(x+dx,y+dy)==dn
            assert image.pixelColor(dx,dy).red()==int(dn*255/4095)
        if mode==ViewMode.FINAL:
            assert window.viewer.mask_items and item.zValue()<window.viewer.mask_items[0].zValue()<10
            window.mask_action.setChecked(False)
            wait(qapp,lambda:not window.controller.busy)
            window.viewer._refresh_raw_detail()
            wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
            assert not window.viewer.mask_items and window.viewer.detail_item is not None
            window.mask_action.setChecked(True)
            wait(qapp,lambda:not window.controller.busy)
            window.viewer._refresh_raw_detail()
            wait(qapp, lambda: not window.controller.busy and window.viewer.detail_item is not None)
            assert window.viewer.mask_items and window.viewer.detail_item is not None
        QTest.mouseMove(window.viewer.viewport(),window.viewer.mapFromScene(400,400))
        qapp.processEvents()
        wait(qapp, lambda: not window.controller.busy and f'DN：{int(values[400,400])}' in window.pointer.text())
        assert f'DN：{int(values[400,400])}' in window.pointer.text()
        assert vm.result.to_dict()==before
        assert hashlib.sha256(path.read_bytes()).hexdigest()==original_hash
