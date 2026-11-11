"""Case03-K8-C: reversible RAW-evidence triage of K8-B work-band hypotheses.

K8-C NEVER changes the frozen J5 masks/IDs, nor its G/H refinements.
Source blackhat B mask itself is retained. Candidate triage uses no labels:
- fixed A branch -> EXISTING_FIXED_H (not novel by this experiment);
- area 1-2px -> MICRO_HIDE_SUGGESTION (still archived, could be genuine);
- >=3px evaluate local RAW annulus contrast and MAD, positive DoG core,
  geometry and band edge proximity;
- strong dark candidates -> PROMISING_DARK_REVIEW; weak/edge -> REVIEW.
User annotations may be joined only in POSTHOC evaluation after scoring.
"""
from dataclasses import dataclass,asdict
import cv2,numpy as np


@dataclass(frozen=True)
class K8CConfig:
    # conservative review triage, not a validated quality acceptance rule
    min_promising_area_px:int=8
    micro_suggest_hide_max_area_px:int=2
    local_annulus_inner_radius_px:int=6
    local_annulus_outer_radius_px:int=24
    min_valid_annulus_pixels:int=70
    raw_relative_darkness_min:float=.07
    raw_mad_z_min:float=2.0
    min_dog_dark_core_dn:float=3.
    edge_review_distance_px:float=32.
    max_local_feature_width_px:int=360
    max_local_feature_height_px:int=360
    noise_sigma_floor_dn:float=3.
    pixel_pitch_um:float=3.2
    dog_small_sigma:float=2.
    dog_large_sigma:float=8.

def mask_at_size(mask:np.ndarray,shape:tuple[int,int]):
    assert mask.shape==shape
    return np.asarray(mask,bool)

def component_properties(raw:np.ndarray,labels:np.ndarray,id_:int,
                         stats:np.ndarray,all_b:np.ndarray,
                         core:np.ndarray,distance:np.ndarray,
                         cfg:K8CConfig)->dict:
    """Samples only local RAW pixels, excluding ALL already proposed BH dark pixels
    from annulus; uses candidate median RAW and robust annular DN distribution.
    """
    x,y,w,h,area=[int(i) for i in stats[id_,:5]]
    x0=max(0,x-cfg.local_annulus_outer_radius_px-4)
    y0=max(0,y-cfg.local_annulus_outer_radius_px-4)
    x1=min(raw.shape[1],x+w+cfg.local_annulus_outer_radius_px+4)
    y1=min(raw.shape[0],y+h+cfg.local_annulus_outer_radius_px+4)
    candidate=labels[y0:y1,x0:x1]==id_
    overlap_count=int(np.count_nonzero(candidate))
    assert overlap_count==area,(id_,overlap_count,area)
    dst=float(distance[y0:y1,x0:x1][candidate].min())
    metrics={
       "raw_reference_valid":False,
       "raw_contrast_dn":None,"raw_contrast_fraction":None,
       "raw_annulus_MADsigma_dn":None,"raw_MAD_significance_z":None,
       "dog_dark_core_median_dn":None,"dog_dark_core_p90_dn":None,
       "band_core_min_edge_distance_px":round(dst,2),
       "valid_background_annulus_pixels":0,
       "raw_object_median_dn":None,"raw_annulus_median_dn":None,
    }
    if w>cfg.max_local_feature_width_px or h>cfg.max_local_feature_height_px:
        metrics["feature_reason"]="VERY_LARGE_OR_LONG_OBJECT_MANUAL_REVIEW"
        return metrics
    xobj=np.asarray(raw[y0:y1,x0:x1],np.float32)
    # L2 annulus around actual disconnected-shape extent, not bounding centroid.
    # Dilation annulus excludes the target and B proposals and SHIELD/nonwork.
    kouter=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
        (2*cfg.local_annulus_outer_radius_px+1,)*2)
    kinner=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
        (2*cfg.local_annulus_inner_radius_px+1,)*2)
    outer=cv2.dilate(candidate.astype(np.uint8),kouter)>0
    inner=cv2.dilate(candidate.astype(np.uint8),kinner)>0
    others=all_b[y0:y1,x0:x1]
    good=core[y0:y1,x0:x1] & outer & ~inner & ~others
    goodcount=int(good.sum())
    metrics["valid_background_annulus_pixels"]=goodcount
    if goodcount<cfg.min_valid_annulus_pixels:
        metrics["feature_reason"]="ANNULUS_INVALID_OR_BORDER_TOO_CLOSE"
        return metrics
    ref=np.asarray(xobj[good],np.float64)
    val=np.asarray(xobj[candidate],np.float64)
    refmedian=float(np.median(ref))
    obsmedian=float(np.median(val))
    sigma=max(cfg.noise_sigma_floor_dn,
              1.4826*float(np.median(np.abs(ref-refmedian))))
    delta=refmedian-obsmedian
    metrics.update({
        "raw_reference_valid":True,
        "raw_object_median_dn":round(obsmedian,3),
        "raw_annulus_median_dn":round(refmedian,3),
        "raw_contrast_dn":round(delta,3),
        "raw_contrast_fraction":round(delta/max(refmedian,1.),6),
        "raw_annulus_MADsigma_dn":round(sigma,4),
        "raw_MAD_significance_z":round(delta/sigma,4),
        "feature_reason":"VALID_ANNULUS"
    })
    # coherence: in a broad dark patch the 8px Gaussian is brighter than 2px
    # Gaussian near a DARK NUCLEUS. This is a feature, not an independent seed.
    small=cv2.GaussianBlur(xobj,(0,0),cfg.dog_small_sigma,
                           borderType=cv2.BORDER_REFLECT)
    big=cv2.GaussianBlur(xobj,(0,0),cfg.dog_large_sigma,
                         borderType=cv2.BORDER_REFLECT)
    dark=(big-small)[candidate]
    metrics["dog_dark_core_median_dn"]=round(float(np.median(dark)),4)
    metrics["dog_dark_core_p90_dn"]=round(float(np.percentile(dark,90)),4)
    return metrics

def classify_candidate(area:int,overlap_with_A:int,props:dict,
                       cfg:K8CConfig)->tuple[str,str]:
    """No human labels or prior J5 IDs are consulted here."""
    if overlap_with_A>0:
        return "EXISTING_FIXED_H","SHARES_FIXED_170_230_H_SEED"
    if area<=cfg.micro_suggest_hide_max_area_px:
        return "MICRO_HIDE_SUGGESTION","AREA_1_OR_2PX_PROVISIONAL_NO_DELETE"
    if props["band_core_min_edge_distance_px"]<cfg.edge_review_distance_px:
        return "BOUNDARY_REVIEW","WITHIN_32PX_OF_WORK_CORE_EDGE"
    if not props["raw_reference_valid"]:
        return "UNCERTAIN_REVIEW",props["feature_reason"]
    if area<cfg.min_promising_area_px:
        return "MICRO_REVIEW","AREA_3_TO_7PX_NOT_PROVEN_NOISE"
    if (props["raw_contrast_fraction"]>=cfg.raw_relative_darkness_min
       and props["raw_MAD_significance_z"]>=cfg.raw_mad_z_min
       and props["dog_dark_core_p90_dn"]>=cfg.min_dog_dark_core_dn):
        return "PROMISING_DARK_REVIEW","RAW_DARK_CONTRAST_MAD_AND_DOG_SUPPORTED"
    # NEVER hide medium/large candidates solely from uncertain RAW features.
    return "UNCERTAIN_REVIEW","DARK_SPOT_EVIDENCE_NOT_SUFFICIENT"

def evaluate_binary_band(raw:np.ndarray,bmask:np.ndarray,
                         amask:np.ndarray,core:np.ndarray,cfg:K8CConfig,
                         dist:np.ndarray|None=None)->tuple[list[dict],np.ndarray,np.ndarray,np.ndarray]:
    """Returns rows and 3 per-pixel reversible masks:
    promising, under-review (incl fixed-H), hide-SUGGESTION-only.
    """
    if not (raw.shape==bmask.shape==amask.shape==core.shape):raise ValueError("shape mismatch")
    if raw.dtype!=np.uint16:raise TypeError("RAW must be uint16")
    if np.any(bmask&~core) or np.any(amask&~bmask):
        raise ValueError("unexpected B or A outside mask / missing A from B")
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(
        bmask.astype(np.uint8),connectivity=8,ltype=cv2.CV_32S)
    if dist is None:dist=cv2.distanceTransform(core.astype(np.uint8),cv2.DIST_L2,3)
    if dist.shape!=core.shape:raise ValueError("distance shape")
    overlap=np.bincount(labels[amask].reshape(-1),minlength=n)
    overlap[0]=0
    rows=[]
    state=np.zeros(n,np.uint8) # 0 background, 1 promising, 2 review, 3 suggest hide
    for i in range(1,n):
        area=int(stats[i,cv2.CC_STAT_AREA])
        status="MICRO_HIDE_SUGGESTION"
        props={
            "raw_reference_valid":False,
            "raw_contrast_dn":None,"raw_contrast_fraction":None,
            "raw_annulus_MADsigma_dn":None,
            "raw_MAD_significance_z":None,
            "dog_dark_core_median_dn":None,"dog_dark_core_p90_dn":None,
            "band_core_min_edge_distance_px":None,
            "valid_background_annulus_pixels":0,
            "raw_object_median_dn":None,"raw_annulus_median_dn":None,
            "feature_reason":"EVIDENCE_NOT_EVALUATED_MICRO_ONLY"}
        if overlap[i]>0:
            status="EXISTING_FIXED_H"
            reason="SHARES_FIXED_170_230_H_SEED"
        elif area<=cfg.micro_suggest_hide_max_area_px:
            reason="AREA_1_OR_2PX_PROVISIONAL_NO_DELETE"
        else:
            props=component_properties(raw,labels,i,stats,bmask,core,dist,cfg)
            status,reason=classify_candidate(area,int(overlap[i]),props,cfg)
        state[i]=1 if status=="PROMISING_DARK_REVIEW" else (
            3 if status=="MICRO_HIDE_SUGGESTION" else 2)
        x,y,w,h=[int(z) for z in stats[i,:4]]
        rows.append({
            "band_component_label":i,
            "source_A_fixed_overlap_px":int(overlap[i]),
            "is_independent_of_fixed_H":bool(overlap[i]==0),
            "candidate_area_px2":area,
            "candidate_area_detector_equiv_um2":round(area*cfg.pixel_pitch_um**2,3),
            "candidate_center_local_x":round(float(centroids[i,0]),3),
            "candidate_center_local_y":round(float(centroids[i,1]),3),
            "bbox_local_x":x,"bbox_local_y":y,
            "bbox_width_px":w,"bbox_height_px":h,
            "classification":status,"reason":reason,
            **props,
            "no_actual_candidate_pixels_deleted":True,
            "no_official_J5_area_or_ID_modified":True,
            "unconfirmed_candidate_not_physically_calibrated":True
        })
    assert len(rows)==n-1
    promising=(state[labels]==1)
    review=(state[labels]==2)
    suggested_hide=(state[labels]==3)
    assert np.array_equal(promising|review|suggested_hide,bmask)
    assert not np.any((promising&review)|(review&suggested_hide)|(promising&suggested_hide))
    return rows,promising,review,suggested_hide
