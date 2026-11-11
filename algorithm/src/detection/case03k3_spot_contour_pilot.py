"""Experimental Case03-K3 spot contour pilot. No production gate/mask update.

Two independent stages:
  (A) extra Black-Hat 61px response, still H170/230, anchored to a
      previously detected J5 object (never proposes new objects);
  (B) when shape/context agree, estimate outer RAW contrast via robust
      plane and seeded region, with conservative spatial/competition guards.
Output ALWAYS distinguishes original pixels / BH provisional / RAW estimated
envelope. The estimated extent is NOT a physical certified defect boundary.
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2,numpy as np


@dataclass(frozen=True)
class PilotConfig:
    bh61_kernel_px:int=61
    low_dn:int=170
    high_dn:int=230
    min_h61_area_px:int=60
    min_h61_growth_ratio:float=2.0
    max_h61_axis_aspect:float=2.5
    h61_max_fraction_of_roi:float=.18
    bg_outer_ring_inner_px:float=38.0
    bg_outer_ring_outer_px:float=58.0
    raw_smooth_sigma_px:float=1.3
    raw_alpha_peak:float=.15
    raw_noise_sigma_multiplier:float=3.
    radial_max_px:float=49.
    raw_max_area_px:int=2000
    min_raw_seed_overlap_fraction:float=.6
    min_raw_envelope_to_H61_ratio:float=1.
    max_raw_envelope_to_H61_ratio:float=12.
    border_margin_px:int=3

    def validate(self):
        if not (self.bh61_kernel_px>31 and self.bh61_kernel_px%2):
            raise ValueError("blackhat 61 scale should be odd and >31")
        if self.low_dn>=self.high_dn or self.low_dn<0:
            raise ValueError("bad hysteresis thresholds")
        if not 0<self.raw_alpha_peak<1:raise ValueError("bad alpha")
        if not 1<=self.radial_max_px<64:
            raise ValueError("radial cap exceeds ROI")
        if self.bg_outer_ring_inner_px>=self.bg_outer_ring_outer_px:
            raise ValueError("ring invalid")


def component_seeded_H(response:np.ndarray,seed:np.ndarray,
                       cfg:PilotConfig)->np.ndarray:
    if response.shape!=seed.shape:raise ValueError("H/source shape mismatch")
    lo=response>=cfg.low_dn
    n,ids,_,_=cv2.connectedComponentsWithStats(np.uint8(lo),8)
    if n<=1:return np.zeros_like(seed,dtype=bool)
    hist=np.bincount(ids[seed].ravel(),minlength=n);hist[0]=0
    winner=int(hist.argmax())
    if not winner or hist[winner]==0:return np.zeros_like(seed,bool)
    obj=ids==winner
    if not np.any(obj&(response>=cfg.high_dn)):
        return np.zeros_like(seed,bool)
    return obj


def aspect_and_bbox(mask:np.ndarray)->tuple[float,tuple[int,int,int,int]|None]:
    y,x=np.where(mask)
    if len(x)==0:return float("nan"),None
    box=(int(x.min()),int(y.min()),int(np.ptp(x)+1),int(np.ptp(y)+1))
    if len(x)<4:return 1.,box
    coords=np.column_stack((x,y)).astype(float)
    cov=np.cov(coords.T)
    values=np.linalg.eigvalsh(cov)
    aspect=float(np.sqrt(max(float(values.max()),1.)/max(float(values.min()),1.)))
    return aspect,box


def robust_outer_plane(f:np.ndarray,xx:np.ndarray,yy:np.ndarray,
                       ring:np.ndarray)->np.ndarray:
    A=np.stack((np.ones_like(xx)[ring],xx[ring],yy[ring]),axis=1).astype(np.float64)
    vals=f[ring].astype(np.float64)
    if len(vals)<500:raise ValueError("insufficient outer background pixels")
    beta=np.linalg.lstsq(A,vals,rcond=None)[0]
    for _ in range(6):
        err=vals-A@beta
        sig=1.4826*np.median(np.abs(err-np.median(err)))
        c=max(3.,1.5*sig)
        w=np.minimum(1.,c/np.maximum(np.abs(err),1e-6))
        beta=np.linalg.lstsq(A.T@(A*w[:,None]),A.T@(w*vals),rcond=None)[0]
    return (beta[0]+beta[1]*xx+beta[2]*yy).astype(np.float32)


def raw_outer_envelope(raw128:np.ndarray,seed128:np.ndarray,
                       center:tuple[float,float],
                       cfg:PilotConfig)->tuple[np.ndarray,dict]:
    """One connected RAW response around original detector mask only.

    Returns a hypothesis even if guard rejects it; subsequent caller must
    distinguish raw proposal from authorized display suggestion.
    """
    if raw128.shape!=(128,128) or seed128.shape!=raw128.shape:
        raise ValueError("RAW K3 pilot only supports 128x128")
    y,x=np.mgrid[:128,:128]
    dx=x-center[0];dy=y-center[1]
    rad=np.hypot(dx,dy)
    ring=(rad>=cfg.bg_outer_ring_inner_px)&(rad<=cfg.bg_outer_ring_outer_px)
    raw=raw128.astype(np.float32)
    baseline=robust_outer_plane(raw,dx,dy,ring)
    smooth=cv2.GaussianBlur(raw,(0,0),cfg.raw_smooth_sigma_px)
    delta=baseline-smooth
    vals=delta[ring]
    sigma=1.4826*float(np.median(np.abs(vals-np.median(vals))))
    peak=float(np.percentile(delta[rad<=9],99))
    threshold=max(cfg.raw_noise_sigma_multiplier*sigma,cfg.raw_alpha_peak*peak)
    active=(delta>=threshold)&(rad<=cfg.radial_max_px)
    n,labels,_,_=cv2.connectedComponentsWithStats(np.uint8(active),8)
    if n<=1 or not seed128.any():
        prop=np.zeros_like(seed128,bool)
    else:
        hist=np.bincount(labels[seed128].ravel(),minlength=n);hist[0]=0
        best=int(hist.argmax())
        prop=(labels==best) if best>0 and hist[best]>0 else np.zeros_like(seed128,bool)
    aspects,bbox=aspect_and_bbox(prop)
    inside=int((prop&seed128).sum())
    checks={
       "raw_bg_ring_mad_sigma_DN":round(sigma,4),
       "raw_local_peak_DN":round(peak,4),
       "raw_boundary_threshold_DN":round(threshold,4),
       "raw_proposal_area_px2":int(prop.sum()),
       "raw_proposal_seed_overlap_px":inside,
       "raw_proposal_seed_overlap_fraction":round(inside/max(int(seed128.sum()),1),4),
       "raw_proposal_aspect":round(aspects,4) if np.isfinite(aspects) else None,
       "raw_proposal_bbox":bbox,
       "raw_proposal_touches_roi_border":bool(
            np.any(prop[:cfg.border_margin_px,:]) or
            np.any(prop[-cfg.border_margin_px:,:]) or
            np.any(prop[:,:cfg.border_margin_px]) or
            np.any(prop[:,-cfg.border_margin_px:])),
       "raw_proposal_touches_radius_cap":bool(np.any(prop&(rad>=cfg.radial_max_px-1))),
       "raw_foreground_component_count":int(n-1),
       "estimated_area_not_physical_truth":True
    }
    return prop,checks


def decision(source128:np.ndarray,H31:np.ndarray,H61:np.ndarray,
             rawproposal:np.ndarray,other_detected:np.ndarray,
             audit:dict,cfg:PilotConfig)->tuple[str,list[str]]:
    """Deterministic approval only for experimental visualization, never J5."""
    reasons=[]
    source_area=int(source128.sum())
    h31=int(H31.sum())
    h61=int(H61.sum())
    rawarea=int(rawproposal.sum())
    axis,_=aspect_and_bbox(H61)
    if h61<cfg.min_h61_area_px:reasons.append("H61_region_too_small")
    if h61/max(source_area,1)<cfg.min_h61_growth_ratio:
        reasons.append("H61_not_multiscale_extended")
    if axis>cfg.max_h61_axis_aspect:
        reasons.append("H61_line_like_not_spot")
    if h61>cfg.h61_max_fraction_of_roi*source128.size:
        reasons.append("H61_large_uncontrolled")
    if rawarea<max(h61*cfg.min_raw_envelope_to_H61_ratio,source_area):
        reasons.append("RAW_envelope_below_H61")
    if rawarea>cfg.raw_max_area_px or rawarea>cfg.max_raw_envelope_to_H61_ratio*max(1,h61):
        reasons.append("RAW_envelope_unbounded")
    if audit["raw_proposal_seed_overlap_fraction"]<cfg.min_raw_seed_overlap_fraction:
        reasons.append("RAW_seed_mismatch")
    if audit["raw_proposal_touches_roi_border"] or audit["raw_proposal_touches_radius_cap"]:
        reasons.append("RAW_contour_censored")
    if np.any(rawproposal & other_detected):
        reasons.append("RAW_intersects_competing_J5_object")
    return ("PROVISIONAL_OUTER_SUGGESTION" if not reasons else
            "KEEP_ORIGINAL_REVIEW_ONLY"),reasons
