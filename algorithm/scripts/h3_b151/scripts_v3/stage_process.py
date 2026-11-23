"""J4 window post-processor for the official B151-H3 chain.

One core+halo work window in: per-pixel H3 threshold surfaces drive hysteresis,
then Case03-E2 H-seeded refinement and the Case03-F/G/H gates run on that same
window. Thresholds are always arrays supplied by stage_j4; there is no scalar
fixed-threshold route here. Every decision is recomputed from the current RAW
window, so no frame-specific manual label enters detection.
"""
from __future__ import annotations
import sys
from pathlib import Path
import cv2,numpy as np
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03t_adaptive_hysteresis import (
    hysteresis_window
)
# Experimental adapter is separate; the production Case03E2 API stays frozen.
from stage_refine import (
    detect_window_H_seeded,HSeedConfig,H_SOURCE
)
from src.detection.case03e2_multicandidate import FusionConfig
from src.detection.candidate_local_noise import (
    NoiseTrialConfig,local_raw_statistics,classify_candidate
)
from src.detection.case03g_joint_gate import JointGateConfig,decide_gate,build_joint_maps
from src.detection.case03h_background_texture import TextureTrialConfig,extend_gate


def policies():
    refine=FusionConfig(
        source_min_region_area_px=cfg.CASE03E2_MIN_LOCAL_COMPONENT_AREA_PX,
        background_high_floor_dn=cfg.CASE03E2_GAUSSIAN_MORPH_HIGH_FLOOR_DN,
        background_low_floor_dn=cfg.CASE03E2_GAUSSIAN_MORPH_LOW_FLOOR_DN,
        high_noise_k=cfg.CASE03E2_GAUSSIAN_MORPH_HIGH_K_MAD,
        low_noise_k=cfg.CASE03E2_GAUSSIAN_MORPH_LOW_K_MAD,
        max_mask_area_fraction=cfg.CASE03E2_MAX_LOCAL_REGION_AREA_FRACTION,
        keep_H_if_area_at_least_px=cfg.CASE03E2_KEEP_H_REGION_MIN_AREA_PX,
        keep_H_if_peak_at_least_dn=cfg.CASE03E2_KEEP_H_REGION_STRONG_PEAK_DN,
        H_only_provisional_min_area_px=cfg.CASE03E2_H_ONLY_PROVISIONAL_AREA_MIN_PX,
        H_only_provisional_peak_DN=cfg.CASE03E2_H_ONLY_PROVISIONAL_PEAK_DN,
    )
    seed=HSeedConfig(
        max_extension_radius_px=cfg.CASE03E2_HSEED_MAX_EXTENSION_RADIUS_PX,
        min_h_pixels_for_refinement=cfg.CASE03E2_HSEED_MIN_H_PIXELS_FOR_REFINEMENT,
        max_extended_to_H_area_ratio=cfg.CASE03E2_HSEED_MAX_AREA_RATIO,
        max_source_component_window_fraction=cfg.CASE03E2_HSEED_MAX_RAW_COMPONENT_FRACTION,
        enable_bounded_extension_fallback=cfg.CASE03E2_HSEED_BOUNDED_FALLBACK_ENABLED,
        bounded_fallback_radius_px=cfg.CASE03E2_HSEED_BOUNDED_RADIUS_PX,
        bounded_fallback_max_area_ratio=cfg.CASE03E2_HSEED_BOUNDED_MAX_AREA_RATIO,
    )
    f=NoiseTrialConfig(
        small_area_max_px=cfg.CASE03F_SMALL_AREA_MAX_PX,
        min_relative_contrast=cfg.CASE03F_MIN_RELATIVE_CONTRAST,
        min_significance_z=cfg.CASE03F_MIN_SIGNIFICANCE_Z,
        ring_outer_radius_px=cfg.CASE03F_RING_OUTER_RADIUS_PX,
        ring_inner_guard_px=cfg.CASE03F_RING_INNER_GUARD_PX,
        ring_min_count=cfg.CASE03F_RING_MIN_COUNT,
        sigma_floor_dn=cfg.CASE03F_SIGMA_FLOOR_DN,
        protect_large_nearby_radius_px=cfg.CASE03F_PROTECT_LARGE_NEARBY_RADIUS_PX,
        protect_large_area_px=cfg.CASE03F_PROTECT_LARGE_AREA_PX,
    )
    g=JointGateConfig(
        protect_support_area_min_px=cfg.CASE03G_PROTECT_STRUCTURE_MIN_AREA_PX,
        protect_support_radius_px=cfg.CASE03G_PROTECT_STRUCTURE_RADIUS_PX,
        protect_any_existing_refinement=cfg.CASE03G_PROTECT_EXISTING_REFINEMENT,
    )
    h=TextureTrialConfig(
        medium_min_area_px=cfg.CASE03H_MEDIUM_MIN_AREA_PX,
        medium_max_area_px=cfg.CASE03H_MEDIUM_MAX_AREA_PX,
        min_relative_contrast=cfg.CASE03H_MIN_RELATIVE_CONTRAST,
        min_significance_z=cfg.CASE03H_MIN_SIGNIFICANCE_Z,
        protect_peak_dn=cfg.CASE03H_PROTECT_BLACKHAT_PEAK_DN,
        protect_dog_median_dn=cfg.CASE03H_PROTECT_DOG_MEDIAN_DN,
        dog_small_sigma_px=cfg.CASE03H_DOG_SMALL_SIGMA_PX,
        dog_large_sigma_px=cfg.CASE03H_DOG_LARGE_SIGMA_PX,
        protect_big_area_px=cfg.CASE03H_PROTECT_BIG_AREA_PX,
        protect_big_radius_px=cfg.CASE03H_PROTECT_BIG_RADIUS_PX,
        protect_stroke_min_length_px=cfg.CASE03H_PROTECT_STROKE_MIN_LENGTH_PX,
        protect_stroke_aspect=cfg.CASE03H_PROTECT_STROKE_ASPECT,
    )
    return refine,seed,f,g,h




def process_one(raw:np.ndarray,response:np.ndarray,
                low:np.ndarray,high:np.ndarray,
                refine:FusionConfig,seed:HSeedConfig,
                f:NoiseTrialConfig,g:JointGateConfig,h:TextureTrialConfig,
                *,context_provider=None
                )->dict:
    # Empty and all-filtered windows leave through early exits, so the
    # mandatory per-pixel threshold contract is asserted before them.
    if not (isinstance(low,np.ndarray) and isinstance(high,np.ndarray)):
        raise TypeError('H3 per-pixel threshold maps are mandatory; no fixed scalar route exists')
    if low.shape!=response.shape or high.shape!=response.shape:
        raise ValueError('threshold maps must cover the whole work window')
    H,S,original_seeds=hysteresis_window(response,low,high)
    n,labels,stats,_=cv2.connectedComponentsWithStats(H.astype(np.uint8),8)
    if n-1>seed.max_output_regions_per_window:
        raise RuntimeError("candidate overflow; do not truncate")
    from fast_state import STATE
    from early_rules import before_refinement
    skip_ids=before_refinement(labels,stats,seed) if STATE.early else set()
    if STATE.early and n>1 and len(skip_ids)==n-1:
        maps=build_joint_maps(labels,labels,["hide_suggestion"]*(n-1))
        STATE.count("all_safe_window_filter_exit")
        return {"candidate_count":n-1,"H_pixel_count":int(H.sum()),"seed_count":int(original_seeds),"suggest_hidden":n-1,"protected_review":0,"display_H_pixels":0,"display_refined_pixels":0,"refined_objects":0,"maps":maps,"candidate_audit":[],"H_component_labels":labels,"refined_component_labels":labels,"empty_tile_early_exit":False,"dog_mode":"skipped_all_safe_small"}
    if n==1:
        # Zero H candidate: refinement/gating/DoG cannot produce any output;
        # preserve the exact empty-result contract of the full path.
        fused_labels=np.zeros_like(labels,dtype=np.int32)
        maps=build_joint_maps(labels,fused_labels,[])
        return {
            "candidate_count":0,
            "H_pixel_count":0,
            "seed_count":0,
            "suggest_hidden":0,
            "protected_review":0,
            "display_H_pixels":0,
            "display_refined_pixels":0,
            "refined_objects":0,
            "maps":maps,
            "candidate_audit":[],
            "H_component_labels":labels,
            "refined_component_labels":fused_labels,
            "empty_tile_early_exit":True,
            "dog_mode":"skipped_empty_H",
        }
    # Historical Case03-E2 bounded Gaussian22/Closing61 refinement is reused
    # here and recomputed on the current core+halo RAW window from its own H seeds.
    external=None if context_provider is None else context_provider()
    kw={"cfg":refine,"policy":seed,"skip_ids":skip_ids}
    if external is not None:kw["residuals"]=external["residuals"]
    kw.update(h_low_threshold_map=low,h_high_threshold_map=high)
    detected=detect_window_H_seeded(raw,H,S,response,**kw)
    objects=detected["objects"]
    if len(objects)!=n-1:
        raise AssertionError("missing H object under shared refinement")
    fused_labels=np.zeros_like(labels,dtype=np.int32)
    for j,obj in enumerate(objects,1):
        if obj is None:
            fused_labels[labels==j]=j
            continue
        if np.any(fused_labels[obj.mask]!=0):
            raise AssertionError("refined regions overlap")
        fused_labels[obj.mask]=j
    if np.any(H&(labels!=fused_labels)):
        raise AssertionError("refined mask lost H pixel ownership")
    large_ids=np.flatnonzero(stats[:,cv2.CC_STAT_AREA]>=f.protect_large_area_px)
    large_ids=large_ids[large_ids>0]
    rr=f.protect_large_nearby_radius_px
    near=cv2.dilate(np.isin(labels,large_ids).astype(np.uint8),
                    np.ones((2*rr+1,2*rr+1),np.uint8)).astype(bool)
    old_status=[];features=[]
    # First-stage local RAW median and MAD decisions are recomputed from the
    # current core+halo RAW window; no frame-specific manual label enters them.
    for j in range(1,n):
        x,y,bw,bh,area=(int(v) for v in stats[j,:5])
        if j in skip_ids:
            old_status.append("suggest_hide");features.append({"area_px":area});continue
        hmask=labels==j
        fm=local_raw_statistics(raw,H,hmask,(x,y,bw,bh),f)
        protected=bool(np.any(near[hmask]))
        status,_=classify_candidate(area,bw,bh,fm,protected,f)
        fm.update(area_px=area,
                  fused_blackhat_peak_dn=detected["H_audit"][j-1]["fused_blackhat_peak_dn"])
        old_status.append(status);features.append(fm)
    sources=[tuple(o.sources) if o is not None else (H_SOURCE,) for o in objects]
    gstatus,greasons=decide_gate(labels,stats,old_status,sources,g)
    afloat=raw.astype(np.float32)
    dog=(cv2.GaussianBlur(afloat,(0,0),h.dog_large_sigma_px)-
         cv2.GaussianBlur(afloat,(0,0),h.dog_small_sigma_px)) if external is None else external["dog"]
    if dog.shape!=raw.shape or dog.dtype!=np.float32 or not np.isfinite(dog).all():
        raise ValueError("invalid external DoG")
    for j in range(1,n):
        if j in skip_ids:continue
        features[j-1]["dog_median_dn"]=float(np.median(dog[labels==j]))
    hstatus,hreasons=extend_gate(labels,stats,gstatus,greasons,features,h)
    maps=build_joint_maps(labels,fused_labels,hstatus)
    audit=[dict(local_H_id=j,area_px=int(stats[j,4]),bbox_x=int(stats[j,0]),bbox_y=int(stats[j,1]),bbox_w=int(stats[j,2]),bbox_h=int(stats[j,3]),F_status=old_status[j-1],G_status=gstatus[j-1],G_reason=greasons[j-1],H_status=hstatus[j-1],H_reason=hreasons[j-1],sources=list(sources[j-1]),features=features[j-1]) for j in range(1,n) if j not in skip_ids]
    if not np.array_equal(maps["h_original"],H):
        raise AssertionError("H original incorrectly altered")
    # n=1 means no candidate (valid result).
    return {
        "candidate_count":int(n-1),
        "H_pixel_count":int(H.sum()),
        "seed_count":int(original_seeds),
        "suggest_hidden":hstatus.count("hide_suggestion"),
        "protected_review":hstatus.count("protected_review"),
        "display_H_pixels":int(maps["h_kept_display"].sum()),
        "display_refined_pixels":int(maps["fused_joint_display"].sum()),
        "refined_objects":sum(not o.H_only for o in objects if o is not None),
        "maps":maps,
        "candidate_audit":audit,
        "refinement_audit":detected["local_proposal_audit"],
        "H_component_labels":labels,
        "refined_component_labels":fused_labels,
        "empty_tile_early_exit":False,
        "dog_mode":"full_window",
    }
