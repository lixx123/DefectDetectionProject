"""Read-only projection; no segmentation, measurement, or result mutation."""
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import hashlib
import math
import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QColor, QPainter

MISSING = '—'


def shown(value):
    if value is None:
        return MISSING
    if isinstance(value, float):
        return f'{value:,.3f}'.rstrip('0').rstrip('.')
    return str(value)


class ViewMode(StrEnum):
    ORIGINAL = '原图'
    FINAL = '最终检测图'
    BAND = '工作区 / Band'
    ROI = 'ROI 掩膜'


@dataclass(frozen=True)
class Overlay:
    defect_id: str
    measurement_bbox: tuple
    display_bbox: tuple
    grade: str

    @property
    def bbox(self):
        """Compatibility alias: bbox always means the original measurement."""
        return self.measurement_bbox


def display_bbox(measurement, width, height, *, scale=1.5, minimum=6):
    """GUI-only enlargement in original pixel coordinates; never writes domain."""
    x0, y0, x1, y1 = measurement
    cx, cy = (x0+x1)/2, (y0+y1)/2
    half_w = max((x1-x0)*scale, minimum)/2
    half_h = max((y1-y0)*scale, minimum)/2
    return (max(0, cx-half_w), max(0, cy-half_h),
            min(width, cx+half_w), min(height, cy+half_h))


@dataclass
class DisplayFrame:
    image: QImage
    width: int
    height: int
    message: str = ''
    labels: tuple = ()
    layers: tuple = ()


class ImageCache:
    """Only the current bounded display image is retained, never full RGB rasters."""
    def __init__(self):
        self.key = None
        self.frame = None

    def clear(self):
        self.key = self.frame = None


class ResultViewModel:
    columns = ('ID', '类型', '尺寸等级', 'X', 'Y', '面积 px²', '面积 μm²',
               'Feret px', 'Feret μm', 'Band', 'ROI')

    def __init__(self, result, package_dir, *, formal_binding=None):
        self.result = result
        from .human_review.evidence import ReviewAccess
        self.review_access=ReviewAccess(formal_binding)
        self.is_formal_result=formal_binding is not None
        self.package_dir = Path(package_dir).resolve()
        self.defects = tuple(result.defects)
        self.by_id = {d.identity.defect_id: i for i, d in enumerate(self.defects)}
        self.width = result.input_info.width_px or 1
        self.height = result.input_info.height_px or 1

    @property
    def overlays(self):
        overlays = []
        for d in self.defects:
            b = d.geometry.bbox
            if b is not None:
                measurement = (b.x0, b.y0, b.x1, b.y1)
                overlays.append(Overlay(d.identity.defect_id, measurement,
                    display_bbox(measurement, self.width, self.height), str(d.classification.size_grade)))
        return overlays

    def values(self, row):
        d = self.defects[row]
        g, c, loc = d.geometry, d.classification, d.location
        valid = self.result.calibration_info.valid
        return (d.identity.defect_id, c.defect_type, str(c.size_grade), loc.image_x, loc.image_y,
                g.area_px, g.area_um2 if valid else None, g.length_px,
                g.length_um if valid else None, loc.band_id, loc.roi_id)

    def detail(self, defect_id):
        d = self.defects[self.by_id[defect_id]]
        vals = self.values(self.by_id[defect_id])
        lines = [f'{key}：{shown(val)}' for key, val in zip(self.columns, vals)]
        b, p = d.geometry.bbox, d.geometry.center
        lines += [f'bbox：[ {b.x0}, {b.y0}, {b.x1}, {b.y1} )' if b else 'bbox：—',
                  f'中心：({shown(p.x)}, {shown(p.y)})' if p else '中心：—',
                  f'算法决定：{d.review.algorithm_decision}', f'审核状态：{d.review.review_status}（只读）',
                  '长度语义：Max Feret']
        return '\n'.join(lines)

    @property
    def calibration_text(self):
        c = self.result.calibration_info
        scale = f'{c.spatial_scale_um_per_px:.3f} μm/px' if c.valid and c.spatial_scale_um_per_px is not None else MISSING
        return f'尺度：{scale}\n来源：{c.scale_source}\n有效：{c.valid}'

    @property
    def summary(self):
        e = self.result.execution_info
        prefix = '检测完成（已自动切换至全图模式）' if e.fallback_used else '检测完成'
        mode = str(e.final_mode).upper().replace('-', '_') if e.final_mode is not None else MISSING
        return (f'{prefix}：{len(self.defects)} 个疵病 | {mode} | '
                f'{len(self.result.roi_info.band_list)} Bands\n'
                f'总面积：{shown(self.result.statistics.total_defect_area_px)} px² | '
                f'回退：{"是" if e.fallback_used else "否"}'
                + (f'\n回退原因：{e.fallback_reason}' if e.fallback_used else ''))

    @property
    def bands_text(self):
        lines = [f'几何状态：{self.result.roi_info.status}', 'WORK 绿 · NONWORK 灰 · REVIEW 橙']
        for b in self.result.roi_info.band_list:
            box = b.bbox
            lines.append(f'Band {b.band_id} · valid={b.valid}\n'
                         f'DN mean/min/max：{shown(b.mean_gray_dn)} / {shown(b.min_gray_dn)} / {shown(b.max_gray_dn)}\n'
                         f'bbox：{(box.x0, box.y0, box.x1, box.y1) if box else MISSING}')
        return '\n\n'.join(lines)

    def _image(self, ref, size):
        if ref is None:
            return None
        path = (self.package_dir / ref.path).resolve()
        if not path.is_relative_to(self.package_dir) or not path.is_file():
            return None
        if ref.sha256:
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            if h.hexdigest() != ref.sha256:
                raise ValueError(f'显示资源校验失败：{path.name}')
        reader = QImageReader(str(path))
        # Full-resolution grayscale masks exceed Qt's default allocation cap.
        # Decoding is sequential, bounded thumbnails are the only retained data.
        reader.setAllocationLimit(512)
        reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            raise ValueError(f'无法读取显示资源：{path.name}')
        return image.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)

    def frame(self, mode, raw=None, final_mask=True):
        factor = min(1, 2800 / max(self.width, self.height))
        size = QSize(max(1, math.ceil(self.width * factor)), max(1, math.ceil(self.height * factor)))
        inter = self.result.intermediate_results
        base = raw.thumbnail() if raw else self._image(inter.original_preview, size)
        if base is not None:
            base = base.scaled(size)
        message = ''
        if base is None:
            base = QImage(size, QImage.Format.Format_Grayscale8)
            base.fill(28)
            message = '原始图像不可用' if mode == ViewMode.ORIGINAL else '原图不可用；显示结果资源与独立疵病框'
        if mode == ViewMode.ORIGINAL:
            return DisplayFrame(base, self.width, self.height, message)
        output = base.convertToFormat(QImage.Format.Format_RGB32)
        labels = []
        missing = []
        layers = []

        def tint(ref, color, name):
            mask = self._image(ref, size)
            if mask is None:
                missing.append(name)
                return
            gray = mask.convertToFormat(QImage.Format.Format_Grayscale8)
            values = np.frombuffer(gray.constBits(), np.uint8).reshape(gray.height(), gray.bytesPerLine())[:, :gray.width()]
            rgba = np.empty((gray.height(), gray.width(), 4), np.uint8)
            rgba[:, :, :3] = QColor(color).getRgb()[:3]
            rgba[:, :, 3] = np.where(values > 0, 130, 0)
            layer = QImage(rgba.data, gray.width(), gray.height(), rgba.strides[0], QImage.Format.Format_RGBA8888)
            if mode == ViewMode.FINAL:
                layers.append(layer.copy())
            else:
                painter = QPainter(output)
                painter.drawImage(0, 0, layer)
                painter.end()

        if mode == ViewMode.FINAL and final_mask:
            tint(inter.final_mask, '#ff465d', 'final mask')
        if mode in (ViewMode.ROI, ViewMode.BAND):
            roi = self.result.roi_info
            for region, fallback, color, name in (
                (roi.nonwork_region, inter.nonwork_mask, '#707a8c', 'NONWORK'),
                (roi.work_region, inter.work_mask, '#34d399', 'WORK'),
                (roi.review_region, inter.review_mask, '#ffa640', 'REVIEW')):
                tint(region.mask_reference if region and region.mask_reference else fallback, color, name)
            if mode == ViewMode.BAND:
                colors = ('#38bdf8', '#a78bfa', '#f472b6', '#facc15', '#2dd4bf')
                for i, band in enumerate(roi.band_list):
                    tint(band.mask_reference or inter.band_masks.get(band.band_id), colors[i % len(colors)], f'Band {band.band_id}')
                    if band.bbox:
                        labels.append((f'Band {band.band_id}', band.bbox.x0, band.bbox.y0))
        if missing:
            message += ' · 该资源不可用：' + ', '.join(missing)
        return DisplayFrame(output, self.width, self.height, message, tuple(labels), tuple(layers))
