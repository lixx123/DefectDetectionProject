"""Lossless per-component mask and contour extraction from stored Case03-B H mask.

BBox overlap does not justify taking the entire cropped mask as the target.
Recover the exact 8-connected component matching the source CSV's global bbox
AND true H area. Each uncertain/detected candidate has a unique ID.
"""
from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage


def exact_candidate_submask(
    full_mask:np.ndarray,row:dict
)->tuple[np.ndarray,tuple[int,int,int,int]]:
    """Return exact H-component pixel mask inside its own global bbox."""
    x,y,w,h=(int(row[k]) for k in ("bbox_x","bbox_y","bbox_w","bbox_h"))
    area=int(row["area_px"])
    H,W=full_mask.shape
    if not (0<=x<W and 0<=y<H and w>=1 and h>=1 and x+w<=W and y+h<=H):
        raise ValueError(f"invalid candidate bbox for {row.get('candidate_id')}")
    cut=np.ascontiguousarray(full_mask[y:y+h,x:x+w].astype(np.uint8))
    if area>int(cut.sum()):
        raise ValueError("reported component area larger than all mask pixels in ROI")
    # Component bbox implies touching all four sides of the region.
    if w*h==area:
        if not cut.all():
            raise ValueError("solid H bbox misses some expected pixels")
        return cut,(x,y,w,h)
    # SciPy ndimage handles degenerate 1xN/Nx1 cases consistently.
    labels,count=ndimage.label(cut,structure=np.ones((3,3),dtype=np.uint8))
    matching=[]
    for component in range(1,count+1):
        mask=(labels==component)
        if mask.sum()!=area:
            continue
        yy,xx=np.nonzero(mask)
        if xx.min()==0 and yy.min()==0 and xx.max()==w-1 and yy.max()==h-1:
            matching.append(mask.astype(np.uint8))
    if len(matching)!=1:
        raise ValueError(
            f"bbox/area unable to uniquely identify H connected component: "
            f"{row.get('candidate_id')} bbox={x,y,w,h} area={area}, matches={len(matching)}"
        )
    return np.ascontiguousarray(matching[0]),(x,y,w,h)


def describe_exact_contour(
    full_mask:np.ndarray,row:dict
)->tuple[dict,np.ndarray,tuple[int,int,int,int]]:
    """JSON-serializable true mask and outlines. For 1px/lines prefer packed mask.

    OpenCV contour outlines for one/two-pixel components are not nonzero-area
    polygons. Represent those explicitly by exact bitpacked component masks.
    """
    mask,(x,y,w,h)=exact_candidate_submask(full_mask,row)
    if int(mask.sum())!=int(row["area_px"]):
        raise AssertionError("exact-pixel mask area mismatch")
    boundary,hierarchy=cv2.findContours(mask.copy(),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    polygons=[]
    hole_count=0
    if hierarchy is not None:
        for i,c in enumerate(boundary):
            coords=c.reshape(-1,2)
            pts=[[int(px+x),int(py+y)] for px,py in coords]
            hole=bool(int(hierarchy[0][i][3])>=0)
            hole_count+=int(hole)
            polygons.append({"xy":pts,"is_inner_hole":hole,"is_real_area_polygon":len(pts)>=3})
    bits=np.packbits(mask.reshape(-1),bitorder="little").tobytes()
    record={
        "candidate_id":str(row["candidate_id"]),
        "triage_status":str(row["triage_status"]),
        "morphology_hint":str(row["morphology_hint"]),
        "bbox_global_xywh":[x,y,w,h],
        "centroid_global_xy":[float(row["centroid_x"]),float(row["centroid_y"])],
        "exact_pixel_area":int(mask.sum()),
        "peak_response_dn":int(row["peak_response_dn"]),
        "bitpacked_mask_encoding":"base64__np.packbits__little_bitorder__rowmajor",
        "bbox_binary_mask_base64":base64.b64encode(bits).decode("ascii"),
        "boundary_contours":polygons,
        "hole_count":hole_count,
        "nonpolygon_1px_or_line_mask":int(mask.sum())<=2,
        "physical_defect_truth":False
    }
    return record,mask,(x,y,w,h)
