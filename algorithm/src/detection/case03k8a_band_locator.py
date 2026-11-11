"""Case03-K8-A automatic interior transmission band localization.

No fixed number of bands: a band must have a prominent plateau bounded on
BOTH sides by low-DN shielding troughs, plus sufficient width/contrast.
Bright non-work top and bottom plateaus are rejected by construction.
Detects bands from row-wise robust image statistics, not a saved frame mask.
Conservative work/core edges with a REVIEW buffer around stripe boundaries.

K8A does not alter Black-Hat values, H170/230 thresholds, J4/J5 detection
kernels, or final measurement rules. In the current two-level ``roi-bh``
pipeline, however, its validated geometry is used upstream to schedule which
original J4 tiles and Black-Hat regions are computed. If the geometry is not
trusted, the caller must fail closed to the configured full-frame fallback;
unknown geometry must never be interpreted as defect-free NON_WORK.
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2,numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


@dataclass(frozen=True)
class BandLocatorConfig:
    y_stride:int=4
    x_stride:int=12
    central_fraction:float=.76
    smooth_sigma_rows:float=17.0  # ~68 original pixels at stride=4
    min_peak_prominence_dn:float=75.0
    min_band_width_px:int=170
    max_band_width_px:int=1300
    min_dark_shield_trough_gap_px:int=80
    min_peak_spacing_px:int=220
    boundary_height_fraction:float=.27
    allowed_shield_floor_offset_dn:float=55.
    valley_allowance_contrast_fraction:float=.18
    min_band_contrast_dn:float=90.
    boundary_review_margin_px:int=12
    horizontal_inner_margin_px:int=24
    x_column_sample_count:int=30
    local_column_halfwidth_px:int=155
    local_x_stride:int=8
    edge_local_max_displacement_px:int=130
    max_edge_median_residual_px:int=30
    max_edge_p90_residual_px:int=85
    outside_plateau_fraction:float=.50

    def validate(self):
        if self.y_stride<1 or self.x_stride<1:raise ValueError("strides must be positive")
        if not 0<self.central_fraction<=1:raise ValueError("center width")
        if not 0<self.boundary_height_fraction<1:raise ValueError("band crossing fraction")
        if self.min_band_width_px<=2*self.boundary_review_margin_px:raise ValueError("band too short")


def robust_profile(raw:np.ndarray,cfg:BandLocatorConfig):
    """Raw can be uint16 memmap or small uint16 synthetic ndarray."""
    cfg.validate()
    h,w=raw.shape
    l=max(0,round(w*(1-cfg.central_fraction)/2))
    r=min(w,round(w*(1+cfg.central_fraction)/2))
    chosen=np.asarray(raw[::cfg.y_stride,l:r:cfg.x_stride],dtype=np.float32)
    med=np.median(chosen,axis=1)
    smoothed=gaussian_filter1d(med,cfg.smooth_sigma_rows)
    p10=np.percentile(chosen,10,axis=1)
    p90=np.percentile(chosen,90,axis=1)
    return {"row_median_dn":med,"row_profile_smooth_dn":smoothed,
            "row_p10_dn":p10,"row_p90_dn":p90,
            "shield_floor_dn":float(np.percentile(smoothed,9)),
            "sampled_columns":int(chosen.shape[1]),
            "profile_stride_px":cfg.y_stride}


def interp_crossing(p:np.ndarray,left:int,right:int,t:float,direction:str)->float|None:
    lo=max(0,min(left,right));hi=min(len(p)-1,max(left,right))
    v=np.asarray(p[lo:hi+1],float)
    if direction=="rising":cross=np.where((v[:-1]<t)&(v[1:]>=t))[0]
    else:cross=np.where((v[:-1]>=t)&(v[1:]<t))[0]
    if len(cross)==0:return None
    # Only one flank per candidate in well-formed plateau; use relevant outermost.
    j=int(cross[-1] if direction=="rising" else cross[0])+lo
    denom=float(p[j+1]-p[j])
    return float(j+(t-p[j])/denom) if abs(denom)>1e-8 else float(j)


def select_interior_bands(p:np.ndarray,cfg:BandLocatorConfig,
                          stride:int,shield_floor:float)->tuple[list[dict],list[dict]]:
    """Enforce two DARK separating troughs; no assumptions on 4 vs 5 count."""
    peaks,pdetail=find_peaks(p,prominence=cfg.min_peak_prominence_dn,
              distance=max(1,cfg.min_peak_spacing_px//stride))
    valleys,_=find_peaks(-p,prominence=min(cfg.min_peak_prominence_dn,70.),
              distance=max(1,cfg.min_dark_shield_trough_gap_px//stride))
    bands=[];rejected=[]
    for i,pk in enumerate(peaks):
        pk=int(pk)
        left=valleys[valleys<pk];right=valleys[valleys>pk]
        info={"candidate_peak_row":round(float(pk*stride),1),
              "peak_dn":round(float(p[pk]),2),
              "prominence_dn":round(float(pdetail["prominences"][i]),2)}
        reasons=[]
        if not len(left) or not len(right):
            reasons.append("NOT_BOUNDED_BY_TWO_TROUGHS")
        else:
            L=int(left[-1]);R=int(right[0])
            bgr=float(np.median([p[L],p[R]]))
            contrast=float(p[pk]-bgr)
            t=bgr+cfg.boundary_height_fraction*contrast
            begin=interp_crossing(p,L,pk,t,"rising")
            end=interp_crossing(p,pk,R,t,"falling")
            if begin is None or end is None:
                reasons.append("UNSTABLE_PROFILE_BOUNDARY")
            else:
                top,bottom=float(begin*stride),float(end*stride)
                span=bottom-top
                dark_threshold=shield_floor+max(
                    cfg.allowed_shield_floor_offset_dn,
                    cfg.valley_allowance_contrast_fraction*contrast)
                # Both troughs must be near the global dark shield floor.
                if p[L]>dark_threshold or p[R]>dark_threshold:
                    reasons.append("NON_SHIELD_TROUGH_OR_EXTERNAL_BRIGHT_PLATEAU")
                if contrast<cfg.min_band_contrast_dn:
                    reasons.append("CONTRAST_TOO_LOW")
                if span<cfg.min_band_width_px or span>cfg.max_band_width_px:
                    reasons.append("WIDTH_OUT_OF_RANGE")
                if (pk-L)*stride<cfg.min_dark_shield_trough_gap_px or (
                    R-pk)*stride<cfg.min_dark_shield_trough_gap_px:
                    reasons.append("INSUFFICIENT_SHIELD_SEPARATION")
                info.update({
                    "profile_top_y":round(top,2),
                    "profile_bottom_y":round(bottom,2),
                    "profile_width_y":round(span,2),
                    "left_trough_row":int(L*stride),
                    "right_trough_row":int(R*stride),
                    "left_trough_dn":round(float(p[L]),2),
                    "right_trough_dn":round(float(p[R]),2),
                    "local_shield_background_dn":round(bgr,2),
                    "local_band_contrast_dn":round(contrast,2),
                    "threshold_dn":round(float(t),2),
                    "peak_position_y":round(float(pk*stride),2),
                })
        if reasons:
            info["rejection_reasons"]=reasons
            rejected.append(info)
        else:
            bands.append(info)
    bands.sort(key=lambda v:v["peak_position_y"])
    for i,b in enumerate(bands,1):b["band_id"]=i
    return bands,rejected


def _outer_nonwork_boundaries(p:np.ndarray,bands:list[dict],cfg:BandLocatorConfig,
                              stride:int,baseline:float)->tuple[int,int,dict]:
    """Top/bottom bright plateaus are outside region of interest."""
    h=len(p)*stride
    if not bands:raise ValueError("No interior bands. Do not generate production mask.")
    top_med=float(np.median(p[:max(6,int(len(p)*.07))]))
    bottom_med=float(np.median(p[int(len(p)*.84):int(len(p)*.94)]))
    k=int(bands[0]["left_trough_row"]//stride)
    L=max(1,round((top_med-baseline)*cfg.outside_plateau_fraction+baseline))
    # detect falling high plateau -> upper shield, BEFORE first true band
    falling=np.where((p[:-1]>=L)&(p[1:]<L))[0]
    falling=falling[falling<k]
    top_end=int((falling[-1]+1)*stride) if len(falling) else 0
    k2=int(bands[-1]["right_trough_row"]//stride)
    R=max(1,round((bottom_med-baseline)*cfg.outside_plateau_fraction+baseline))
    rising=np.where((p[:-1]<R)&(p[1:]>=R))[0]
    rising=rising[rising>k2]
    bottom_start=int(rising[0]*stride) if len(rising) else h
    if top_end>=bands[0]["profile_top_y"] or bottom_start<=bands[-1]["profile_bottom_y"]:
        raise RuntimeError("Exterior NON_WORK boundaries invalid; manual review")
    return top_end,min(h,bottom_start),{
        "top_exterior_median_dn":top_med,"bottom_exterior_median_dn":bottom_med,
        "top_nonwork_transition_y":top_end,"bottom_nonwork_transition_y":bottom_start,
        "top_exterior_boundary_found":bool(len(falling)),
        "bottom_exterior_boundary_found":bool(len(rising))}


def _column_boundary_samples(raw:np.ndarray,band:dict,cfg:BandLocatorConfig)->dict:
    """Use many independent broad columns; avoid one scratch moving boundaries."""
    h,w=raw.shape;stride=cfg.y_stride
    xx=np.linspace(max(20,int(w*.035)),min(w-21,int(w*.965)),
                   cfg.x_column_sample_count).astype(int)
    samples=[]
    for x in xx:
        x0=max(0,int(x-cfg.local_column_halfwidth_px))
        x1=min(w,int(x+cfg.local_column_halfwidth_px))
        sample=np.asarray(raw[::stride,x0:x1:cfg.local_x_stride],np.float32)
        med=gaussian_filter1d(np.median(sample,axis=1),cfg.smooth_sigma_rows)
        L=int(band["left_trough_row"]//stride)
        R=int(band["right_trough_row"]//stride)
        peak=int(round(band["peak_position_y"]/stride))
        ldn=float(med[max(0,L)]);rdn=float(med[min(len(med)-1,R)])
        base=(ldn+rdn)/2
        top=max(0,peak-12);bottom=min(len(med),peak+13)
        height=float(np.percentile(med[top:bottom],85))
        contrast=height-base
        if contrast<cfg.min_band_contrast_dn*.65:continue
        threshold=base+cfg.boundary_height_fraction*contrast
        l=interp_crossing(med,L,peak,threshold,"rising")
        r=interp_crossing(med,peak,R,threshold,"falling")
        if l is None or r is None:continue
        yl=l*stride;yr=r*stride
        if abs(yl-band["profile_top_y"])>cfg.edge_local_max_displacement_px:continue
        if abs(yr-band["profile_bottom_y"])>cfg.edge_local_max_displacement_px:continue
        samples.append({"x":int(x),"top_y":float(yl),"bottom_y":float(yr),
                        "bg_dn":base,"peak_dn":height})
    return {"samples":samples,"attempted":len(xx)}


def robust_linear_edge(samples:list[dict],edge:str,ref:float,w:int,cfg:BandLocatorConfig):
    if len(samples)<min(10,math_ceil_half(cfg.x_column_sample_count)):
        return (0.,float(ref)),{"edge_samples":len(samples),
                               "linear_model_used":False,
                               "edge_p90_residual_px":None,
                               "edge_median_residual_px":None}
    x=np.array([s["x"] for s in samples],np.float64)
    y=np.array([s[edge+"_y"] for s in samples],np.float64)
    m,b=np.polyfit(x,y,1)
    for _ in range(4):
        e=y-(m*x+b)
        t=max(7.,3*1.4826*np.median(np.abs(e-np.median(e))))
        keep=np.abs(e)<t
        if keep.sum()<10:break
        m,b=np.polyfit(x[keep],y[keep],1)
    resid=np.abs(y-(m*x+b))
    median=float(np.median(resid));p90=float(np.percentile(resid,90))
    okay=(median<=cfg.max_edge_median_residual_px and
          p90<=cfg.max_edge_p90_residual_px and
          abs(m)*w<=2*cfg.edge_local_max_displacement_px)
    if not okay: m,b=0.,float(ref)
    return (float(m),float(b)),{
        "edge_samples":len(samples),"linear_model_used":bool(okay),
        "edge_median_residual_px":round(median,2),
        "edge_p90_residual_px":round(p90,2),
        "edge_full_width_tilt_px":round(float(m*w),2)}


def math_ceil_half(x:int)->int:
    return (x+1)//2


def locate_transmission_bands(raw:np.ndarray,cfg:BandLocatorConfig)->dict:
    """Returns metadata only; rasterization/saving are separate operations."""
    h,w=raw.shape
    profile=robust_profile(raw,cfg)
    p=profile["row_profile_smooth_dn"]
    found,rejected=select_interior_bands(
        p,cfg,cfg.y_stride,profile["shield_floor_dn"])
    if not found:
        return {"bands":[],"rejected_candidates":rejected,
                "profile":profile,"status":"MANUAL_REVIEW_NO_BANDS",
                "exterior":None,"image_shape":(h,w)}
    top,bottom,outer=_outer_nonwork_boundaries(p,found,cfg,cfg.y_stride,
                                                profile["shield_floor_dn"])
    for b in found:
        samples=_column_boundary_samples(raw,b,cfg)
        b["x_sample_count"]=len(samples["samples"])
        b["x_sample_attempted"]=samples["attempted"]
        (mt,bt),qa_top=robust_linear_edge(samples["samples"],"top",
                     b["profile_top_y"],w,cfg)
        (mb,bb),qa_bottom=robust_linear_edge(samples["samples"],"bottom",
                     b["profile_bottom_y"],w,cfg)
        b["top_line_y_at_x0"]=round(bt,3)
        b["top_line_slope_y_per_x"]=round(mt,8)
        b["bottom_line_y_at_x0"]=round(bb,3)
        b["bottom_line_slope_y_per_x"]=round(mb,8)
        b["top_edge_quality"]=qa_top
        b["bottom_edge_quality"]=qa_bottom
        b["core_x_min"]=cfg.horizontal_inner_margin_px
        b["core_x_max_exclusive"]=w-cfg.horizontal_inner_margin_px
        b["boundary_review_margin_px"]=cfg.boundary_review_margin_px
        b["work_area_status"]="UNREVIEWED_AUTO_PROPOSAL"
        b["validation_flags"]=[]
        if len(samples["samples"])<math_ceil_half(cfg.x_column_sample_count):
            b["validation_flags"].append("INSUFFICIENT_COLUMN_GEOMETRY_SAMPLES")
        if not qa_top["linear_model_used"] or not qa_bottom["linear_model_used"]:
            b["validation_flags"].append("EDGE_FIT_FALLBACK_ROW_PROFILE")
    for i in range(1,len(found)):
        prev=found[i-1];current=found[i]
        if (prev["bottom_line_y_at_x0"]+cfg.boundary_review_margin_px>=
            current["top_line_y_at_x0"]-cfg.boundary_review_margin_px):
            prev["validation_flags"].append("POSSIBLE_ADJACENT_BAND_OVERLAP")
            current["validation_flags"].append("POSSIBLE_ADJACENT_BAND_OVERLAP")
    # Explicitly do not assume 4. Some arrays can contain 5, 6 or more.
    status="AUTOMATIC_CANDIDATE_REVIEW_REQUIRED"
    return {"bands":found,"rejected_candidates":rejected,
            "profile":profile,"status":status,
            "exterior":{"top_nonwork_end":int(top),
                        "bottom_nonwork_start":int(bottom),**outer},
            "image_shape":(h,w),
            "band_count_auto":len(found),"band_count_fixed":False}


def polygon_for_band(band:dict,w:int,cfg:BandLocatorConfig,
                     core:bool)->np.ndarray:
    """Full-frame points; 4-corner linear edge, not fixed y coordinates."""
    mx=cfg.horizontal_inner_margin_px
    xL=mx if core else 0
    xR=w-1-mx if core else w-1
    add=cfg.boundary_review_margin_px if core else 0
    m1=band["top_line_slope_y_per_x"]
    b1=band["top_line_y_at_x0"]
    m2=band["bottom_line_slope_y_per_x"]
    b2=band["bottom_line_y_at_x0"]
    coords=np.array([
       [xL,round(m1*xL+b1+add)],
       [xR,round(m1*xR+b1+add)],
       [xR,round(m2*xR+b2-add)],
       [xL,round(m2*xL+b2-add)]
    ],np.int32)
    if coords[0,1]>=coords[3,1] or coords[1,1]>=coords[2,1]:
        raise RuntimeError("Band polygon edges reversed")
    return coords


def rasterize_region_masks(shape:tuple[int,int],b:list[dict],
                           outer:dict,cfg:BandLocatorConfig):
    """Codes 0 NON_WORK, 1 SHIELD, 2 WORK_CORE, 3 BAND_EDGE_REVIEW.

    Each work band id 1..N preserved as uint8; no unknown areas silently
    counted as WORK. Mask values refer to original pixel coordinates.
    """
    h,w=shape
    if len(b)>250:raise ValueError("too many bands for uint8 mask")
    region=np.zeros((h,w),np.uint8)
    bandids=np.zeros_like(region)
    sy=int(outer["top_nonwork_end"]);ey=int(outer["bottom_nonwork_start"])
    if sy<0 or ey>h or sy>=ey:raise ValueError("bad exterior filter bounds")
    region[sy:ey,:]=1
    for item in b:
        outerpolygon=polygon_for_band(item,w,cfg,core=False)
        corepolygon=polygon_for_band(item,w,cfg,core=True)
        cv2.fillPoly(region,[outerpolygon],3)
        cv2.fillPoly(region,[corepolygon],2)
        cv2.fillPoly(bandids,[corepolygon],int(item["band_id"]))
    if not np.array_equal(bandids>0,region==2):
        raise AssertionError("band id vs WORK mask inconsistent")
    assert not np.any((region[:sy]==2)) and not np.any(region[ey:]==2)
    return region,bandids
