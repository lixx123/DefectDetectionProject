"""Bounded rescue for a H170/230-seeded candidate whose wide low-threshold
Gaussian/Closing component was rejected for touching a crop edge or for
connecting multiple H seeds.

Avoid the bad implication:
    global background component unsafe -> every small nearby RAW pixel unsafe.
This algorithm never creates a new candidate. It ONLY adds locally supported
pixels around an existing H connected component, with a competitor exclusion
moat, contrast threshold, distance/area limits, and full audit. Any rescued
mask is marked REVIEW, not yet independently validated as an accurate contour.
"""
from __future__ import annotations
import cv2
import numpy as np


def rescue_bounded_H_extension(
    H:np.ndarray, Hmask:np.ndarray, label_map:np.ndarray,
    response:np.ndarray, original_low_DN:float, *,
    owner_label:int, radius_px:int=7,
    strong_other_H_moat_px:int=2,
    min_competitor_area_px:int=8,
    min_new_pixels:int=3,
    max_area_multiplier:float=3.0,
    max_window_fraction:float=.10,
    seed_response_quantile:float=20.,
    seed_quantile_scale:float=.50,
)->tuple[np.ndarray|None,dict]:
    """Return candidate mask containing original H or (None, reason).

    Contrast support threshold = max(existing low response threshold,
    0.5*(20th percentile response at original H pixels)).
    This threshold is in local RAW-background residual DN, NOT H170/230 DN.
    All threshold/distance/area criteria are predeclared per run and must be
    evaluated against independent manual geometry after prediction.
    """
    info={
        "fallback_algorithm":"bounded_H_seed_only",
        "seed_H_label":int(owner_label),
        "max_growth_radius_px":int(radius_px),
        "original_low_threshold_DN":float(original_low_DN),
    }
    if (H.shape!=Hmask.shape or H.shape!=response.shape or
        H.shape!=label_map.shape or H.ndim!=2):
        raise ValueError("shape mismatch")
    if not (1<=radius_px<=32):
        raise ValueError("invalid local radius")
    if not Hmask.any() or not np.all(label_map[Hmask]==owner_label):
        raise ValueError("invalid H owner")
    nH=int(Hmask.sum())
    if nH<3:
        return None,{**info,"status":"reject_insufficient_H_anchor"}
    bx,by,bw,bh=cv2.boundingRect(np.uint8(Hmask))
    margin=radius_px+strong_other_H_moat_px+3
    x0=max(0,bx-margin);y0=max(0,by-margin)
    x1=min(H.shape[1],bx+bw+margin)
    y1=min(H.shape[0],by+bh+margin)
    roi=np.s_[y0:y1,x0:x1]
    owner=Hmask[roi]
    local_response=response[roi]
    labels=label_map[roi]
    # Competing original H targets are protected even if they have no
    # Gaussian response. For many scattered 1px H noise specks the
    # exclusion moat is triggered only for statistically meaningful
    # connected H components, but every other H pixel is ALWAYS blocked.
    competing=(labels>0)&(labels!=owner_label)
    cc_sizes=np.bincount(label_map.ravel())
    strong_competing=competing & (
        cc_sizes[np.minimum(labels,cc_sizes.size-1)]>=min_competitor_area_px
    )
    if strong_other_H_moat_px>0 and strong_competing.any():
        k=2*strong_other_H_moat_px+1
        kernel_comp=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k))
        moat=cv2.dilate(np.uint8(strong_competing),kernel_comp)>0
    else:
        moat=strong_competing
    # Create a distance-limited search region around the same source H.
    k=2*radius_px+1
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k))
    near=cv2.dilate(np.uint8(owner),kernel)>0
    h_q=float(np.percentile(local_response[owner],seed_response_quantile))
    floor=max(float(original_low_DN),h_q*seed_quantile_scale)
    info["H_local_response_q_DN"]=h_q
    info["bounded_threshold_DN"]=float(floor)
    additional=(
       (local_response>=floor)&near&
       (~competing)&(~moat)&(~owner)
    )
    binary=np.uint8(owner|additional)
    # The owner original H is one 8-connected component by design; discard
    # isolated local-response islands even if they lie near it geometrically.
    n,component,stats,_=cv2.connectedComponentsWithStats(
        binary,connectivity=8,ltype=cv2.CV_32S
    )
    sy,sx=np.argwhere(owner)[0]
    seed_component=int(component[sy,sx])
    if seed_component<=0:return None,{**info,"status":"reject_no_connected_H_component"}
    keep=(component==seed_component)
    if not np.all(keep[owner]):
        raise AssertionError("bounded fallback lost original H pixels")
    area=int(keep.sum());extra=area-nH
    info["area_original_H_px"]=nH
    info["area_bounded_px"]=area
    info["added_pixels"]=extra
    info["bounded_growth_area_ratio"]=round(area/max(nH,1),4)
    if extra<min_new_pixels:
        return None,{**info,"status":"reject_no_meaningful_added_pixels"}
    if area>max_window_fraction*H.size or area>max_area_multiplier*nH:
        return None,{**info,"status":"reject_bounded_area_overgrowth"}
    ly,lx=np.nonzero(keep)
    if (x0+lx.min()==0 or y0+ly.min()==0 or
        x0+lx.max()==H.shape[1]-1 or
        y0+ly.max()==H.shape[0]-1):
        return None,{**info,"status":"reject_bounded_mask_touches_ROI_edge"}
    out=np.zeros_like(Hmask,bool)
    out[roi]=keep
    if np.any(out&competing_global(label_map,owner_label)):
        raise AssertionError("bounded mask touches other H seeds")
    return out,{**info,"status":"bounded_extension_preliminary_review"}


def competing_global(labels:np.ndarray,owner_label:int)->np.ndarray:
    return (labels>0)&(labels!=owner_label)
