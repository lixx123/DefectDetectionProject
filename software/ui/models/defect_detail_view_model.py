"""Final defect fields and original-pixel local images, without measurements."""
from dataclasses import dataclass
import hashlib
import json
import math
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QImageReader
from .result_view_model import DisplayFrame, Overlay, display_bbox, shown


def text(value):
    return '—' if value is None or str(value)=='UNKNOWN' else shown(value)


@dataclass
class LocalView:
    frame: DisplayFrame
    overlays: tuple
    origin: tuple
    source: str


class DefectDetailViewModel:
    def __init__(self, result_vm, defect_id):
        self.result_vm = result_vm
        self.defect_id = defect_id
        self.defect = result_vm.defects[result_vm.by_id[defect_id]]

    def groups(self):
        d = self.defect
        g,c,m,p,l = d.geometry,d.classification,d.morphology,d.photometry,d.location
        valid = self.result_vm.result.calibration_info.valid
        b,center = g.bbox,g.center
        physical = lambda value: value if valid else None
        return {
            '基本身份': [('Defect ID',d.identity.defect_id),('类型',c.defect_type),('子类型',c.defect_subtype),
                ('尺寸等级',c.size_grade),('严重度等级',c.severity_grade),('置信度',c.confidence),('算法方法',c.classification_method)],
            '几何与形态': [('bbox（测量）',f'[{b.x0}, {b.y0}, {b.x1}, {b.y1})' if b else None),
                ('中心位置',f'({text(center.x)}, {text(center.y)})' if center else None),
                ('面积 px²',g.area_px),('面积 μm²',physical(g.area_um2)),('Max Feret px',g.length_px),
                ('Max Feret μm',physical(g.length_um)),('宽度 px',g.width_px),('宽度 μm',physical(g.width_um)),
                ('等效直径 px',g.equivalent_diameter_px),('等效直径 μm',physical(g.equivalent_diameter_um)),
                ('长宽比',m.aspect_ratio),('圆度',m.circularity),('方向角 °',m.orientation_deg),
                ('solidity',m.solidity),('eccentricity',m.eccentricity)],
            '灰度 / 光度': [('mean DN',p.mean_gray_dn),('min DN',p.min_gray_dn),('max DN',p.max_gray_dn),
                ('背景 mean DN',p.background_mean_dn),('背景 std DN',p.background_std_dn),('灰度差 DN',p.gray_difference_dn),
                ('灰度比',p.gray_ratio),('局部对比度',p.local_contrast),('Black-Hat 响应',p.blackhat_response)],
            '空间归属': [('Band ID',l.band_id),('ROI ID',l.roi_id),('图像 X',l.image_x),('图像 Y',l.image_y),
                ('传感器 X',l.sensor_x),('传感器 Y',l.sensor_y),('物理 X '+l.physical_coordinate_unit,physical(l.physical_x)),
                ('物理 Y '+l.physical_coordinate_unit,physical(l.physical_y))],
            '检测与审计摘要（只读）': [('source channels',', '.join(d.detection.source_channels) or None),
                ('candidate IDs',', '.join(d.detection.candidate_ids) or None),('detection stage',d.detection.detection_stage),
                ('merge history',json.dumps(d.detection.merge_history,ensure_ascii=False) if d.detection.merge_history else None),
                ('algorithm decision',d.review.algorithm_decision),('review status',d.review.review_status)]}

    def _path(self, ref):
        if ref is None:
            return None
        root = self.result_vm.package_dir
        path = (root/ref.path).resolve()
        if not path.is_relative_to(root): raise ValueError('局部图资源越出结果目录')
        if not path.is_file(): return None
        if ref.sha256:
            h=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
            if h.hexdigest()!=ref.sha256: raise ValueError('局部图资源 SHA256 校验失败')
        return path

    def _png_crop(self, ref, rect):
        path=self._path(ref)
        if path is None: return None
        reader=QImageReader(str(path)); reader.setAllocationLimit(512)
        size=reader.size()
        if not size.isValid(): raise ValueError('局部图资源无法解码')
        vm=self.result_vm
        # Preview may be reduced; image coordinates still refer to the original.
        x0,y0,x1,y1=rect
        sx,sy=size.width()/vm.width,size.height()/vm.height
        clip=QRect(math.floor(x0*sx),math.floor(y0*sy),max(1,math.ceil(x1*sx)-math.floor(x0*sx)),
                   max(1,math.ceil(y1*sy)-math.floor(y0*sy)))
        reader.setClipRect(clip)
        image=reader.read()
        if image.isNull(): raise ValueError('局部图资源无法读取')
        return image.scaled(x1-x0,y1-y0,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)

    def local_view(self, mode, raw=None, margin=40):
        vm=self.result_vm; b=self.defect.geometry.bbox
        if b is None: raise ValueError('该疵病没有可用 bbox，局部图不可用')
        x0,y0=max(0,b.x0-margin),max(0,b.y0-margin)
        x1,y1=min(vm.width,b.x1+margin),min(vm.height,b.y1+margin)
        width,height=x1-x0,y1-y0
        if width<=0 or height<=0 or width*height>4_000_000: raise ValueError('局部显示范围超过限制')
        base=raw.crop(x0,y0,x1,y1) if raw else self._png_crop(vm.result.intermediate_results.original_preview,(x0,y0,x1,y1))
        source='真实 RAW 像素' if raw else '正式包 preview（DN 不可用）'
        message=''
        if base is None:
            base=QImage(width,height,QImage.Format.Format_Grayscale8); base.fill(28)
            source='不可用'; message='局部原图不可用'
        layers=[]
        if mode==2:
            path=self._path(self.defect.geometry.mask_reference)
            mask_image=None
            if path is not None and path.suffix.lower()=='.npz':
                with np.load(path,allow_pickle=False) as data:
                    mask=np.asarray(data['mask'])
                    if mask.shape!=(b.y1-b.y0,b.x1-b.x0): raise ValueError('局部 mask 与测量 bbox 尺寸不一致')
                    rgba=np.zeros((height,width,4),np.uint8)
                    region=rgba[b.y0-y0:b.y1-y0,b.x0-x0:b.x1-x0]
                    region[:,:,:3]=(255,70,93); region[:,:,3]=np.where(mask>0,130,0)
                    mask_image=QImage(rgba.data,width,height,rgba.strides[0],QImage.Format.Format_RGBA8888).copy()
            else:
                image=self._png_crop(vm.result.intermediate_results.final_mask,(x0,y0,x1,y1))
                if image is not None:
                    gray=image.convertToFormat(QImage.Format.Format_Grayscale8)
                    pixels=np.frombuffer(gray.constBits(),np.uint8).reshape(height,gray.bytesPerLine())[:,:width]
                    rgba=np.zeros((height,width,4),np.uint8); rgba[:,:,:3]=(255,70,93)
                    rgba[:,:,3]=np.where(pixels>0,130,0)
                    mask_image=QImage(rgba.data,width,height,rgba.strides[0],QImage.Format.Format_RGBA8888).copy()
            if mask_image is not None: layers.append(mask_image)
            else: message+=' · final mask 资源不可用'
        local=(b.x0-x0,b.y0-y0,b.x1-x0,b.y1-y0)
        overlay=Overlay(self.defect_id,local,display_bbox(local,width,height),str(self.defect.classification.size_grade))
        return LocalView(DisplayFrame(base,width,height,message,layers=tuple(layers)),
                         (overlay,) if mode else (),(x0,y0),source)
