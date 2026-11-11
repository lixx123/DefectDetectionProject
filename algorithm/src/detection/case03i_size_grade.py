"""Case03-I: per-connected-region pixel metrics and provisional size grades.

- Input is the chosen reversible Case03-H displayed mask on the original
  12bit RAW (or Case03-T fixed170/230 + same Case03-H gate).
- Grade means geometric scale ONLY, not industrial acceptance or confidence.
- Physically separate H fragments are NOT joined by arbitrary morphology.
- Size in detector IMAGE pixels; do not convert with 3.2um pixel pitch
  into object-plane size without an optical magnification calibration.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import cv2
import numpy as np


@dataclass(frozen=True)
class SizeGradeConfig:
    medium_area_min_px2: int=40
    large_area_min_px2: int=250
    medium_length_min_px: float=15.0
    large_length_min_px: float=45.0
    connectivity: int=8
    max_per_window: int=3000

    def validate(self)->None:
        if not (1<=self.medium_area_min_px2 < self.large_area_min_px2):
            raise ValueError("invalid area limits")
        if not (0 < self.medium_length_min_px < self.large_length_min_px):
            raise ValueError("invalid length limits")
        if self.connectivity not in (4,8) or self.max_per_window<1:
            raise ValueError("invalid component settings")


def grade_size(area_px2:int,length_px:float,cfg:SizeGradeConfig)->tuple[str,str]:
    """Highest-risk size band from area OR projected maximum Feret diameter."""
    cfg.validate()
    if area_px2>=cfg.large_area_min_px2 or length_px>=cfg.large_length_min_px:
        return "LARGE","area" if area_px2>=cfg.large_area_min_px2 else "length"
    if area_px2>=cfg.medium_area_min_px2 or length_px>=cfg.medium_length_min_px:
        return "MEDIUM","area" if area_px2>=cfg.medium_area_min_px2 else "length"
    return "SMALL","none"


def max_feret_centers_px(points_xy:np.ndarray)->float:
    """Largest Euclidean distance among convex hull pixel-center positions.

    One pixel returns 1px as a minimum effective spatial extent (not a
    calibrated edge-to-edge Feret length). For extended regions, no fragile
    PCA axis or diagonal bounding-box approximation is used.
    """
    points=np.asarray(points_xy,dtype=np.float64).reshape(-1,2)
    if len(points)==0:raise ValueError("empty region")
    if len(points)==1:return 1.0
    hull=cv2.convexHull(points.astype(np.float32).reshape(-1,1,2))
    pts=hull.reshape(-1,2).astype(np.float64)
    if len(pts)==1:return 1.
    # Handle possibly long irregular contour without huge pairwise matrix.
    best=0.
    for start in range(0,len(pts),128):
        v=pts[start:start+128,None,:]-pts[None,:,:]
        best=max(best,float(np.square(v).sum(axis=2).max()))
    return max(1.,float(np.sqrt(best)))


def extract_regions(mask:np.ndarray,cfg:SizeGradeConfig,
                    window_id:str,roi_xyxy:tuple[int,int,int,int]
                    )->tuple[list[dict[str,Any]],np.ndarray]:
    cfg.validate()
    if mask.ndim!=2 or mask.dtype!=np.bool_:
        raise TypeError("expected 2D boolean segmentation mask")
    x0,y0,x1,y1=(int(v) for v in roi_xyxy)
    if mask.shape!=(y1-y0,x1-x0):
        raise ValueError("ROI and mask dimensions differ")
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(
        np.uint8(mask),connectivity=cfg.connectivity)
    if n-1>cfg.max_per_window:
        raise RuntimeError(f"{window_id}: {n-1} regions exceeded max; refusing silent truncation")
    regions=[]
    for j in range(1,n):
        x,y,w,h,area=(int(v) for v in stats[j,:5])
        patch=(labels[y:y+h,x:x+w]==j)
        ys,xs=np.nonzero(patch)
        coordinates=np.column_stack((xs+x,ys+y))
        length=max_feret_centers_px(coordinates)
        grade,reason=grade_size(area,length,cfg)
        contours,_=cv2.findContours(patch.astype(np.uint8),
                                    cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not contours:raise RuntimeError("nonempty region has no contour")
        touches=bool(x==0 or y==0 or x+w==mask.shape[1] or y+h==mask.shape[0])
        regions.append({
            "window_id":window_id,"local_region_id":j,
            "region_id":f"{window_id}_D{j:04d}",
            "area_px2":area,
            "max_feret_centers_px":round(length,4),
            "equivalent_diameter_px":round(float(2*np.sqrt(area/np.pi)),4),
            "bbox_x_global":x0+x,"bbox_y_global":y0+y,
            "bbox_width_px":w,"bbox_height_px":h,
            "center_x_global":round(x0+float(centroids[j,0]),3),
            "center_y_global":round(y0+float(centroids[j,1]),3),
            "touches_window_border":touches,
            "size_grade":grade,"grade_trigger":reason,
            "grade_is_provisional":True,
            "pixel_unit":"detector_image_pixel",
            "grade_is_not_quality_acceptance":True,
            "source_is_candidate_not_confirmed_defect":True,
        })
    if sum(int(x["area_px2"]) for x in regions)!=int(mask.sum()):
        raise AssertionError("region count did not cover all displayed pixels")
    return regions,labels


# OpenCV BGR annotation colors: smaller GREEN, medium YELLOW, larger RED.
GRADE_COLORS_BGR={
    "SMALL":(35,215,65),
    "MEDIUM":(25,230,240),
    "LARGE":(40,45,240),
}


def render_marked_raw(raw_uint16:np.ndarray,mask:np.ndarray,
                      regions:list[dict],labels:np.ndarray,
                      title:str,roi_origin_xy:tuple[int,int]=(0,0),
                      draw_small_numbers:bool=False,
                      zoom:int=3)->np.ndarray:
    if (raw_uint16.shape!=mask.shape or labels.shape!=mask.shape
        or raw_uint16.dtype!=np.uint16 or mask.dtype!=np.bool_):
        raise ValueError("RAW/mask/label mismatch")
    if zoom<1:raise ValueError("zoom must be >=1")
    raw=raw_uint16.astype(np.float32)
    lo,hi=np.percentile(raw,[1,99.5])
    hi=max(float(hi),float(lo)+1.)
    vis=np.clip((raw-lo)/(hi-lo)*255.,0.,255.).astype(np.uint8)
    bgr=cv2.cvtColor(vis,cv2.COLOR_GRAY2BGR)
    # Semi-transparent fills, but original RAW remains visible for assessment.
    overlay=bgr.copy()
    for r in regions:
        color=np.array(GRADE_COLORS_BGR[r["size_grade"]],dtype=np.uint8)
        overlay[labels==int(r["local_region_id"])]=color
    bgr=cv2.addWeighted(overlay,.23,bgr,.77,0)
    # Contours, ids and length; no crossing connections introduced.
    for r in regions:
        j=int(r["local_region_id"])
        region=np.uint8(labels==j)
        contours,_=cv2.findContours(region,cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
        color=GRADE_COLORS_BGR[r["size_grade"]]
        cv2.drawContours(bgr,contours,-1,color,1,lineType=cv2.LINE_8)
        if r["size_grade"]=="SMALL" and not draw_small_numbers:
            continue
        x=int(r["bbox_x_global"]-roi_origin_xy[0])
        y=int(r["bbox_y_global"]-roi_origin_xy[1])
        text=f"{j:03d}"
        # Keep labels inside tile, display 2 groups as many as possible.
        tx=max(1,min(bgr.shape[1]-34,x))
        ty=max(12,min(bgr.shape[0]-3,y-2))
        cv2.putText(bgr,text,(tx,ty),cv2.FONT_HERSHEY_SIMPLEX,
                    .32,(10,10,10),2,cv2.LINE_AA)
        cv2.putText(bgr,text,(tx,ty),cv2.FONT_HERSHEY_SIMPLEX,
                    .32,color,1,cv2.LINE_AA)
    if zoom>1:
        bgr=cv2.resize(bgr,None,fx=zoom,fy=zoom,
                       interpolation=cv2.INTER_NEAREST)
    pad=78
    out=cv2.copyMakeBorder(bgr,pad,0,0,0,cv2.BORDER_CONSTANT,
                           value=(29,29,29))
    counts={name:sum(r["size_grade"]==name for r in regions)
            for name in ("SMALL","MEDIUM","LARGE")}
    cv2.putText(out,title[:85],(12,24),cv2.FONT_HERSHEY_SIMPLEX,
                .61,(235,235,235),1,cv2.LINE_AA)
    cv2.putText(out,"PROVISIONAL size / pixel only; not quality grade",
                (12,47),cv2.FONT_HERSHEY_SIMPLEX,.43,
                (185,185,185),1,cv2.LINE_AA)
    count_line="SMALL "+str(counts["SMALL"])+               "  MED "+str(counts["MEDIUM"])+               "  LARGE "+str(counts["LARGE"])
    cv2.putText(out,count_line,(12,68),cv2.FONT_HERSHEY_SIMPLEX,
                .48,(230,230,230),1,cv2.LINE_AA)
    for i,name in enumerate(("SMALL","MEDIUM","LARGE")):
        cv2.circle(out,(415+i*95,62),5,GRADE_COLORS_BGR[name],-1)
    return out
