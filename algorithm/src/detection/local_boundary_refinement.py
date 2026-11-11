"""Case03-E: seeded *local* boundary refinement, engineering pilot only.

Uses one manually clicked RAW center and local pixel intensities, never the
manual polygon to select a seed, threshold, ROI size or growth bound. Manual
polygon must be reserved for post-hoc diagnostic comparison.

Not an end-to-end defect detector. The segmented region is NOT proven to be
the physical defect boundary. Reject/flag excessive local growth; do not infer
object-plane micrometres from detector pitch.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import cv2
import numpy as np

METHODS=("closing61","closing101","gaussian22")
LEVELS=("liberal","conservative")
STATUS=("ok","no_reliable_seed","overgrown_needs_review","touches_crop_boundary")


@dataclass(frozen=True)
class Refinement:
    mask: np.ndarray
    method: str
    level: str
    status: str
    seed_x: int
    seed_y: int
    seed_shift_px: float
    initial_seed_response_dn: float
    threshold_dn: float
    background_response_median_dn: float
    background_response_mad_sigma_dn: float
    area_px: int
    bbox_xywh: tuple[int,int,int,int]|None
    max_hull_span_px: float
    equivalent_diameter_px: float
    touches_crop_edge: bool


def max_hull_distance(mask:np.ndarray)->float:
    """Maximum distance among convex-hull vertices (Feret proxy, pixel units)."""
    yy,xx=np.nonzero(mask)
    if len(xx)<2:
        return 0.0
    contour=np.column_stack((xx,yy)).astype(np.float32)
    hull=cv2.convexHull(contour).reshape(-1,2)
    # For 256 px patch hull count normally tiny, but cap pathological shapes
    # by evaluating convex hull point pairs chunkwise to avoid N^2 allocation.
    maximum=0.0
    for start in range(0,len(hull),100):
        differences=hull[start:start+100,None,:]-hull[None,:,:]
        maximum=max(maximum,float((differences*differences).sum(axis=2).max()))
    return float(np.sqrt(maximum))


def compute_local_residual(raw:np.ndarray,method:str)->np.ndarray:
    """Bright-background minus RAW denoised intensity, in DN, no display scaling."""
    if raw.dtype!=np.uint16 or raw.ndim!=2:
        raise TypeError("RAW crop must be two-dimensional uint16 DN")
    if method not in METHODS:raise ValueError("unknown local refinement method")
    denoised=cv2.medianBlur(raw,3)
    if method.startswith("closing"):
        k=int(method[7:])
        se=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k))
        bg=cv2.morphologyEx(denoised,cv2.MORPH_CLOSE,se)
    else:
        bg=cv2.GaussianBlur(denoised,(0,0),sigmaX=22,sigmaY=22)
    residual=np.maximum(bg.astype(np.float32)-denoised.astype(np.float32),0)
    # 1px response fluctuations are not a physical target boundary
    return cv2.GaussianBlur(residual,(0,0),sigmaX=.85)


def _strict_seed(response:np.ndarray,clicked_xy:tuple[int,int]):
    x,y=map(int,clicked_xy)
    h,w=response.shape
    if not(0<=x<w and 0<=y<h):raise ValueError("user-clicked center outside RAW crop")
    Y,X=np.ogrid[:h,:w]
    d2=(X-x)**2+(Y-y)**2
    search=(d2<=12**2)
    indexed=np.where(search,response,-1)
    seed_i=int(np.argmax(indexed))
    sy,sx=np.unravel_index(seed_i,response.shape)
    return int(sx),int(sy),float(np.sqrt((sx-x)**2+(sy-y)**2))


def grow_from_clicked_center(
    raw:np.ndarray,clicked_xy:tuple[int,int],
    *,
    method:str="closing61",
    level:str="liberal",
    max_area_fraction:float=.25
)->Refinement:
    """Return one seed-connected dark anomaly mask or a flagged empty result.

    Threshold from RESPONSE in an outer fixed-distance annulus and a search
    within 12px of clicked center. No manual polygon enters this function.
    """
    if raw.shape[0]<190 or raw.shape[1]<190:
        raise ValueError("use at least 190x190 raw with background context")
    if level not in LEVELS:raise ValueError("bad threshold level")
    if not(0<max_area_fraction<=1):raise ValueError("bad area cap")
    response=compute_local_residual(raw,method)
    sx,sy,dist=_strict_seed(response,clicked_xy)
    h,w=raw.shape
    # Noise/background response from a broad outer annulus about the click.
    cx,cy=map(int,clicked_xy)
    Y,X=np.ogrid[:h,:w]
    rad2=(X-cx)**2+(Y-cy)**2
    ring=(rad2>=65**2)&(rad2<=116**2)
    if np.count_nonzero(ring)<300:
        raise ValueError("ROI lacks support for noise statistics")
    vals=response[ring]
    med=float(np.median(vals))
    mad_sigma=1.4826*float(np.median(np.abs(vals-med)))
    seed=float(response[sy,sx])
    k,frac=(1.1,.22) if level=="liberal" else (1.8,.37)
    threshold=max(20.,med+k*mad_sigma,seed*frac)
    details=dict(method=method,level=level,seed_x=sx,seed_y=sy,
        seed_shift_px=dist,initial_seed_response_dn=seed,
        threshold_dn=float(threshold),background_response_median_dn=med,
        background_response_mad_sigma_dn=mad_sigma)
    zeros=np.zeros_like(raw,dtype=bool)
    def empty(reason):
        return Refinement(zeros,reason if False else method,level,reason,sx,sy,dist,
            seed,threshold,med,mad_sigma,0,None,0.,0.,False)
    if seed<=threshold or seed<30:
        return empty("no_reliable_seed")

    binary=np.uint8(response>=threshold)
    # Closing can connect 1-2 px fragmented dark pixels, but does not choose
    # a far-away component. This remains an experimental assumption to test.
    se=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,se)
    if not binary[sy,sx]:return empty("no_reliable_seed")
    count,labels,stats,_centroids=cv2.connectedComponentsWithStats(
        binary,connectivity=8,ltype=cv2.CV_32S
    )
    target=int(labels[sy,sx])
    if target<=0 or target>=count:return empty("no_reliable_seed")
    component=(labels==target)
    area=int(stats[target,cv2.CC_STAT_AREA])
    bbox=(int(stats[target,cv2.CC_STAT_LEFT]),
          int(stats[target,cv2.CC_STAT_TOP]),
          int(stats[target,cv2.CC_STAT_WIDTH]),
          int(stats[target,cv2.CC_STAT_HEIGHT]))
    border=bool(component[0].any() or component[-1].any() or
                component[:,0].any() or component[:,-1].any())
    maximum=max_hull_distance(component)
    eq=float(2*np.sqrt(area/np.pi))
    if area>max_area_fraction*h*w:
        return Refinement(component,method,level,"overgrown_needs_review",
            sx,sy,dist,seed,threshold,med,mad_sigma,area,bbox,maximum,eq,border)
    return Refinement(component,method,level,
        "touches_crop_boundary" if border else "ok",
        sx,sy,dist,seed,threshold,med,mad_sigma,area,bbox,maximum,eq,border)


def image_crop_at_target(
    raw_memmap:np.ndarray,clicked_global_xy:tuple[int,int],size:int=256
)->tuple[np.ndarray,tuple[int,int]]:
    """Clamped crop of full RAW; coordinates remain true zero-based RAW pixels."""
    H,W=raw_memmap.shape
    x,y=clicked_global_xy
    if not (0<=x<W and 0<=y<H):raise ValueError("clicked coordinates out of RAW")
    if size>min(H,W) or size<190:raise ValueError("invalid ROI size")
    x0=int(np.clip(x-size//2,0,W-size))
    y0=int(np.clip(y-size//2,0,H-size))
    return np.ascontiguousarray(raw_memmap[y0:y0+size,x0:x0+size],
                                  dtype=np.uint16),(x0,y0)
