"""Candidate initial geometry is the sole crop anchor; final geometry is optional context."""
from PySide6.QtGui import QImage
from .defect_detail_view_model import DefectDetailViewModel, LocalView
from .result_view_model import DisplayFrame, Overlay, display_bbox


class CandidateDetailViewModel:
    # Reuse the existing checked, bounded artifact reader, without inventing a Defect.
    _path = DefectDetailViewModel._path
    _png_crop = DefectDetailViewModel._png_crop

    def __init__(self, result_vm, candidate):
        self.result_vm, self.candidate = result_vm, candidate

    def fields(self):
        c = self.candidate
        fields = {name:getattr(c,name) for name in ('candidate_id','source','current_stage','disposition',
                  'filter_reason','filter_message','merged_into','final_defect_id')}
        g = c.initial_geometry
        fields['bbox（初始测量）'] = None if g is None or g.bbox is None else f'[{g.bbox.x0}, {g.bbox.y0}, {g.bbox.x1}, {g.bbox.y1})'
        fields['center'] = None if g is None or g.center is None else f'({g.center.x}, {g.center.y})'
        for name in ('area_px','area_um2','length_px','length_um','width_px','width_um','equivalent_diameter_px','equivalent_diameter_um'):
            fields[name] = getattr(g,name) if g else None
        return fields

    def local_view(self, mode, raw=None, margin=40):
        c, vm = self.candidate, self.result_vm
        b = c.initial_geometry.bbox if c.initial_geometry else None
        if b is None:
            return self.empty('无候选初始几何，局部图不可用')
        rect = (max(0,b.x0-margin),max(0,b.y0-margin),min(vm.width,b.x1+margin),min(vm.height,b.y1+margin))
        x0,y0,x1,y1=rect
        width,height=x1-x0,y1-y0
        if width<=0 or height<=0 or width*height>4_000_000:
            return self.empty('候选局部显示范围超过限制')
        source='真实 RAW 像素' if raw else '原图 preview（DN 不可用）'
        base=raw.crop(*rect) if raw else self._png_crop(vm.result.intermediate_results.original_preview,rect)
        if base is None and raw is None:
            base=self._png_crop(vm.result.intermediate_results.candidate_preview,rect)
            source='候选预览资源（非原始 RAW，DN 不可用）'
        if base is None:
            base=QImage(width,height,QImage.Format.Format_Grayscale8);base.fill(28)
            source='局部原图不可用 · 中性底图'
        overlays=[]
        if mode:
            local=(b.x0-x0,b.y0-y0,b.x1-x0,b.y1-y0)
            overlays.append(Overlay('Candidate',local,display_bbox(local,width,height),'UNKNOWN'))
        if mode==2 and c.final_defect_id in vm.by_id:
            f=vm.defects[vm.by_id[c.final_defect_id]].geometry.bbox
            if f:
                local=(f.x0-x0,f.y0-y0,f.x1-x0,f.y1-y0)
                overlays.append(Overlay('Final',local,local,'UNKNOWN'))
        return LocalView(DisplayFrame(base,width,height),tuple(overlays),(x0,y0),source)

    @staticmethod
    def empty(message):
        image=QImage(240,140,QImage.Format.Format_Grayscale8);image.fill(28)
        return LocalView(DisplayFrame(image,240,140,message),(),(0,0),message)
