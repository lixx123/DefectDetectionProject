"""Experimental Case03-T: global/local adaptive double Black-Hat hysteresis.

No defect labels or manual positions enter threshold estimation. Background
is approximated by clipping upper 2% of grid response samples. Both threshold
surface and historical fixed 170/230 use the SAME fused raw-DN response.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np, cv2


@dataclass(frozen=True)
class AdaptiveConfig:
    grid_size_px:int=256
    sample_stride_px:int=4
    global_sample_stride_px:int=16
    background_trim_percentile:float=98.
    k_low:float=3.5
    k_high:float=5.0
    noise_sigma_floor_dn:float=3.
    low_floor_dn:float=20.
    high_floor_dn:float=40.
    min_hysteresis_gap_dn:float=15.


def robust_stats(values:np.ndarray, cfg:AdaptiveConfig)->tuple[float,float,float]:
    a=np.asarray(values,dtype=np.float32).reshape(-1)
    if len(a)<40 or not np.isfinite(a).all():
        raise ValueError("insufficient finite response pixels for background estimate")
    cap=float(np.percentile(a,cfg.background_trim_percentile))
    t=a[a<=cap]
    if len(t)<40:raise ValueError("background trim removed too many samples")
    med=float(np.median(t))
    mad=float(np.median(np.abs(t-med)))
    return med,1.4826*mad,cap


def _thresholds(median:np.ndarray|float,sigma:np.ndarray|float,
                cfg:AdaptiveConfig)->tuple[np.ndarray,np.ndarray]:
    med=np.asarray(median,dtype=np.float32)
    noise=np.maximum(np.asarray(sigma,dtype=np.float32),
                     cfg.noise_sigma_floor_dn)
    low=np.maximum(cfg.low_floor_dn,med+cfg.k_low*noise)
    high=np.maximum.reduce([
        np.broadcast_to(cfg.high_floor_dn,np.shape(low)),
        np.asarray(med+cfg.k_high*noise,dtype=np.float32),
        np.asarray(low+cfg.min_hysteresis_gap_dn,dtype=np.float32),
    ])
    return low,high


def global_thresholds(fused:np.ndarray,cfg:AdaptiveConfig)->dict:
    med,sigma,cap=robust_stats(
        fused[::cfg.global_sample_stride_px,::cfg.global_sample_stride_px],cfg)
    l,h=_thresholds(med,sigma,cfg)
    return {"median_dn":med,"sigma_mad_dn":sigma,"cap98_dn":cap,
            "low_dn":float(l),"high_dn":float(h),
            "floor_low_used":bool(cfg.low_floor_dn>=med+cfg.k_low*max(sigma,cfg.noise_sigma_floor_dn)),
            "floor_high_used":bool(cfg.high_floor_dn>=med+cfg.k_high*max(sigma,cfg.noise_sigma_floor_dn))}


def local_grids(fused:np.ndarray,cfg:AdaptiveConfig)->tuple[np.ndarray,np.ndarray,np.ndarray,list[dict]]:
    H,W=fused.shape
    row_bounds=[(i,min(i+cfg.grid_size_px,H)) for i in range(0,H,cfg.grid_size_px)]
    col_bounds=[(i,min(i+cfg.grid_size_px,W)) for i in range(0,W,cfg.grid_size_px)]
    med=np.empty((len(row_bounds),len(col_bounds)),np.float32)
    sig=np.empty_like(med)
    caps=np.empty_like(med)
    audit=[]
    for iy,(y0,y1) in enumerate(row_bounds):
        for ix,(x0,x1) in enumerate(col_bounds):
            data=fused[y0:y1:cfg.sample_stride_px,
                       x0:x1:cfg.sample_stride_px]
            m,s,c=robust_stats(data,cfg)
            med[iy,ix],sig[iy,ix],caps[iy,ix]=m,s,c
            audit.append({
                "grid_y":iy,"grid_x":ix,
                "x0":x0,"y0":y0,"x1":x1,"y1":y1,
                "median_dn":m,"sigma_mad_dn":s,"trim_cap_dn":c,
                "sample_count":int(data.size),
                "low_floor_dominates":bool(cfg.low_floor_dn >=m+cfg.k_low*max(s,cfg.noise_sigma_floor_dn)),
                "high_floor_dominates":bool(cfg.high_floor_dn >=m+cfg.k_high*max(s,cfg.noise_sigma_floor_dn)),
            })
    return med,sig,caps,audit


def interpolate_window(grid:np.ndarray,rect:tuple[int,int,int,int],
                       full_shape:tuple[int,int],cfg:AdaptiveConfig)->np.ndarray:
    """Bilinear grid interpolation evaluated only for selected windows."""
    x0,y0,x1,y1=rect
    H,W=full_shape
    ycoords=np.array([(a+min(a+cfg.grid_size_px,H)-1)/2
                      for a in range(0,H,cfg.grid_size_px)],np.float32)
    xcoords=np.array([(a+min(a+cfg.grid_size_px,W)-1)/2
                      for a in range(0,W,cfg.grid_size_px)],np.float32)
    if grid.shape!=(len(ycoords),len(xcoords)):
        raise ValueError("grid sizes do not match")
    x=np.arange(x0,x1,dtype=np.float32)
    y=np.arange(y0,y1,dtype=np.float32)
    # Interpolate x grid onto each selected x, then y onto image rows.
    xinterp=np.empty((len(ycoords),len(x)),np.float32)
    for i in range(len(ycoords)):
        xinterp[i]=np.interp(x,xcoords,grid[i]).astype(np.float32)
    full=np.empty((len(y),len(x)),np.float32)
    for col in range(len(x)):
        full[:,col]=np.interp(y,ycoords,xinterp[:,col])
    return full


def local_window_thresholds(medians:np.ndarray,sigmas:np.ndarray,
                            rect:tuple[int,int,int,int],
                            full_shape:tuple[int,int],cfg:AdaptiveConfig
                            )->tuple[np.ndarray,np.ndarray]:
    m=interpolate_window(medians,rect,full_shape,cfg)
    s=interpolate_window(sigmas,rect,full_shape,cfg)
    return _thresholds(m,s,cfg)


def hysteresis_window(response:np.ndarray,low:np.ndarray|float,
                      high:np.ndarray|float)->tuple[np.ndarray,np.ndarray,int]:
    """8-connected support >= low linked to >= high; no area suppression."""
    if np.any(np.asarray(high)<np.asarray(low)):
        raise ValueError("high threshold must exceed low threshold")
    support=response>=low
    seeds=response>=high
    if not np.any(seeds & support):
        return np.zeros_like(support),np.zeros_like(seeds),int(seeds.sum())
    n,lab,stats,_=cv2.connectedComponentsWithStats(
        support.astype(np.uint8),connectivity=8)
    active=np.unique(lab[seeds & support])
    active=active[active>0]
    out=np.isin(lab,active)
    return out,seeds & out,int(seeds.sum())
