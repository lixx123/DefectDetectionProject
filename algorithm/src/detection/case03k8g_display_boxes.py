"""K8G annotation geometry and layout only. No segmentation or size changes.

One-pixel STROKE, exactly 1.5x continuous bbox dimensions around its center
except unavoidable full-image clipping. RAW and area/Feret remain untouched.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math

@dataclass(frozen=True)
class DisplayBoxConfig:
    scale_factor:float=1.5
    line_width_display_px:int=1
    display_stride_px:int=8
    border_padding_display_px:int=3
    label_gap_px:int=4

    def validate(self):
        if self.scale_factor<1 or self.scale_factor>5:raise ValueError("bad display bbox scaling")
        if self.line_width_display_px!=1:raise ValueError("1 display pixel thick requested")
        if self.display_stride_px<1:raise ValueError("bad display stride")

def expand_bbox_xyxy(box, image_size, factor=1.5):
    """Input/output continuous RAW pixel edge coordinates, x1/y1 EXCLUSIVE.

    Unclipped extent scales exactly by factor around original center. The
    clipped rectangle stays within [0,width] x [0,height].
    """
    x0,y0,x1,y1=[float(z) for z in box]
    W,H=map(int,image_size)
    if not (0<=x0<x1<=W and 0<=y0<y1<=H):
        raise ValueError("original bbox outside source RAW")
    if factor<1 or not math.isfinite(factor):raise ValueError("bad factor")
    cx=(x0+x1)/2;cy=(y0+y1)/2
    hw=(x1-x0)*factor/2;hh=(y1-y0)*factor/2
    result=(max(0.,cx-hw),max(0.,cy-hh),
            min(float(W),cx+hw),min(float(H),cy+hh))
    assert 0<=result[0]<result[2]<=W
    assert 0<=result[1]<result[3]<=H
    return result

def bbox_to_display_px(box, raw_size, display_size, stride):
    """Map source edges to output pixel inclusive strokes, not area stats."""
    W,H=map(int,raw_size)
    dw,dh=map(int,display_size)
    if dw<1 or dh<1 or stride<1:raise ValueError("bad display resolution")
    x0,y0,x1,y1=box
    sx=max(0,min(dw-1,int(math.floor(x0/stride))))
    sy=max(0,min(dh-1,int(math.floor(y0/stride))))
    ex=max(sx,min(dw-1,int(math.ceil(x1/stride)-1)))
    ey=max(sy,min(dh-1,int(math.ceil(y1/stride)-1)))
    return (sx,sy,ex,ey)

def overlap_area(box_a,box_b):
    a0,b0,a1,b1=box_a
    c0,d0,c1,d1=box_b
    return max(0,min(a1,c1)-max(a0,c0))*max(0,min(b1,d1)-max(b0,d0))

def arrange_labels(boxes, label_sizes, display_size, padding=3):
    """Place labels outside their own boxes and avoid ALL box interiors.

    Greedy deterministic cost minimization with a heavy penalty for overlap.
    Returns coordinates & flags; does not affect existing bboxes.
    """
    if len(boxes)!=len(label_sizes):raise ValueError("label count mismatch")
    W,H=map(int,display_size)
    placements=[]
    for i,(rect,(tw,th)) in enumerate(zip(boxes,label_sizes)):
        x0,y0,x1,y1=[int(v) for v in rect]
        tw,th=int(tw),int(th)
        candidate_xy=[]
        # First search near the associated source box; then progressively
        # widen the search so 1:8 overview labels can avoid dense bands.
        # This moves LABELS only, never rectangle geometry or RAW coordinates.
        for g in (padding,padding+12,padding+28,padding+48,
                  padding+74,padding+110,padding+155):
            for ax in (x0,x1-tw,(x0+x1-tw)//2):
                candidate_xy.extend([(ax,y0-th-g),(ax,y1+g)])
            for ay in (y0,y1-th,(y0+y1-th)//2):
                candidate_xy.extend([(x1+g,ay),(x0-tw-g,ay)])
        # Last resort: free side margins / background strips, avoid
        # covering a defect when two regions share almost the same row.
        for ay in range(0,max(H-th+1,1),max(12,th//2)):
            candidate_xy.extend([(0,ay),(W-tw,ay)])
        options=[]
        for rank,(x,y) in enumerate(candidate_xy):
            x=int(max(0,min(max(W-tw,0),x)))
            y=int(max(0,min(max(H-th,0),y)))
            labelrect=(x,y,x+tw,y+th)
            own_cross=overlap_area(labelrect,(x0-1,y0-1,x1+2,y1+2))
            other_cross=sum(overlap_area(labelrect,
                    (b[0]-1,b[1]-1,b[2]+2,b[3]+2))
                    for j,b in enumerate(boxes) if j!=i)
            old_cross=sum(overlap_area(labelrect,
                (a[0]-2,a[1]-2,a[2]+2,a[3]+2)) for a in placements)
            dist=abs(x-x0)+abs(y-(y0-th-padding))
            cost=(own_cross*100000+old_cross*10000+
                  other_cross*1000+dist*.15+rank*.01)
            options.append((cost,rank,labelrect,
                            own_cross,old_cross,other_cross))
        best=min(options,key=lambda q:(q[0],q[1]))
        placements.append(best[2])
    return placements

def font_sizes_for_stride(stride):
    if stride<=4:return {"main":18,"subtitle":15,"header":20}
    return {"main":12,"subtitle":11,"header":17}

def shortened_id(row):
    if row["source"]=="K8F_USER_APPROVED_K8E_OUTER":
        return str(row["supplement_K8E_group_id"]).split("_")[-1]+" ✓"
    return str(row["source_J5_global_defect_id"]).replace("DEFECT_","D")

def grade_text(grade):
    return {"LARGE":"大","MEDIUM":"中","SMALL":"小"}[str(grade)]

def label_lines(row):
    """Exact original AREA+length, suffix explicitly IMAGE PLANE."""
    identifier=shortened_id(row)
    a=int(row["area_detector_px2"])
    length=float(row["max_length_detector_image_um"])
    return (f"{identifier} {grade_text(row['size_grade'])} | A={a} px²",
            f"L={length:.1f} μm (像面)")
