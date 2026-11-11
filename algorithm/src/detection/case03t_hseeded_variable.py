"""Case03-E2-H: ONLY original H170/230 connected components may create targets.

Gaussian22/Closing61 CANNOT produce standalone proposals. They can only
propose a bounded extension connected to an existing H candidate. Unsafe
response (large black band, crop-edge bridge, competing H seeds, overgrowth)
is rejected for the final contour while original H pixels remain intact.

No manual click, polygon, or hand-approved target ID enters the algorithm.
This module originated as a selected-window development pilot; its H-seeded
refinement kernel is now reused unchanged by J4 for every scheduled core+halo
window. It remains a detector-image-pixel algorithm, not a physical-size
calibration.
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np

from src.detection.case03e2_multicandidate import (
    FusionConfig,ObjectRegion,Proposal,stats_mask,
    _robust_thresholds,
)
from src.detection.local_boundary_refinement import (
    compute_local_residual,max_hull_distance
)

SOURCE_NAMES=("gaussian22","closing61")


@dataclass(frozen=True)
class HSeedConfig:
    max_extension_radius_px:int=12
    min_h_pixels_for_refinement:int=3
    min_local_peak_above_low_DN:float=10.
    max_extended_to_H_area_ratio:float=12.
    max_area_fraction_of_window:float=.10
    max_source_component_window_fraction:float=.08
    min_competing_H_area_px:int=8
    max_competing_H_overlap_px:int=5
    max_method_area_ratio:float=3.
    max_output_regions_per_window:int=3000
    high_H_only_area_min_px:int=12
    high_H_only_peak_dn:int=350
    enable_bounded_extension_fallback:bool=False
    bounded_fallback_radius_px:int=7
    bounded_fallback_max_area_ratio:float=3.0


def _H_component_catalog(H:np.ndarray,S:np.ndarray,fused:np.ndarray):
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(
        np.uint8(H),connectivity=8,ltype=cv2.CV_32S
    )
    Hh,Hw=H.shape
    audit=[]
    for label in range(1,count):
        x,y,w,h,area=(int(z) for z in stats[label,:5])
        inbbox=labels[y:y+h,x:x+w]==label
        peak=int(fused[y:y+h,x:x+w][inbbox].max())
        numseed=int(np.count_nonzero(S[y:y+h,x:x+w]&inbbox))
        audit.append({
            "local_H_id":f"Hlocal_{label:04d}",
            "bbox_x":x,"bbox_y":y,"bbox_w":w,"bbox_h":h,
            "area_px":area,"fused_blackhat_peak_dn":peak,
            "S230_seed_pixel_count":numseed,
            "promoted_to_fusion_pool":True,
            "low_area_H_retained_in_original_mask":bool(area<3),
            "is_strong_peak_H_only_possible":bool(peak>=350),
            "H_hysteresis_proposal_always_retained":True,
        })
    return labels,stats,centroids,audit


def _refinement_by_H_seed(
    raw:np.ndarray,H:np.ndarray,labels:np.ndarray,
    Hlabel:int,hmask:np.ndarray,
    source:str,response:np.ndarray,
    local_labels:np.ndarray,local_stats:np.ndarray,
    low:float,high:float,
    cfg:FusionConfig,policy:HSeedConfig
)->tuple[np.ndarray|None,dict]:
    """Retrieve an already-computed LOCAL method component from an H anchor."""
    info={"source":source,"H_local_label":Hlabel,
          "threshold_low_DN":float(low),"threshold_high_DN":float(high),
          "status":"not_refined"}
    area=int(hmask.sum())
    if area<policy.min_h_pixels_for_refinement:
        info["status"]="H_too_small_to_refine_but_retained"
        return None,info
    seedindex=np.flatnonzero(hmask)
    if not len(seedindex):raise AssertionError("missing H label pixels")
    peak_response=float(response.flat[seedindex].max())
    info["H_anchor_local_peak_dn"]=peak_response
    if peak_response<low+policy.min_local_peak_above_low_DN:
        info["status"]="H_present_but_local_response_too_weak"
        return None,info
    seedindex=seedindex[np.argmax(response.flat[seedindex])]
    y,x=np.unravel_index(seedindex,H.shape)
    region=int(local_labels[y,x])
    if region==0:
        info["status"]="H_anchor_not_within_low_response_region"
        return None,info
    bx,by,bw,bh,bgarea=(int(x) for x in local_stats[region,:5])
    info["source_component_raw_area_px"]=bgarea
    touch=(bx==0 or by==0 or bx+bw>=H.shape[1] or by+bh>=H.shape[0])
    if touch:
        info["status"]="rejected_source_component_touches_window_edge"
        return None,info
    if bgarea>=policy.max_source_component_window_fraction*H.size:
        info["status"]="rejected_large_background_component"
        return None,info

    # Prevent a local low-threshold component linking to another independent
    # H marker. Use statistically meaningful competing H regions only;
    # 1px H noise should not break every valid target.
    full_component=(local_labels==region)
    other_labels=labels[full_component & ~hmask]
    others=other_labels[other_labels>0]
    if len(others):
        competitor_ids,competitor_counts=np.unique(
            others,return_counts=True)
        is_competing=np.any(
            (competitor_ids!=Hlabel) &
            (local_stats_competitor_area(labels,competitor_ids)>=
               policy.min_competing_H_area_px) &
            (competitor_counts>=policy.max_competing_H_overlap_px))
        if is_competing:
            info["status"]="rejected_bridge_between_independent_H_seeds"
            info["competing_H_ids_count"]=int(np.count_nonzero(
                (competitor_ids!=Hlabel) &
                (competitor_counts>=policy.max_competing_H_overlap_px)))
            return None,info

    # Clip the local component to a strict bounded neighborhood of the source H
    # geometry, NOT an arbitrary large window-wide dark band.
    radius=policy.max_extension_radius_px
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (2*radius+1,2*radius+1))
    near=cv2.dilate(np.uint8(hmask),kernel).astype(bool)
    extension=full_component & near & ~H
    candidate=hmask|extension
    extended_area=int(candidate.sum())
    info["candidate_area_px"]=extended_area
    info["added_non_H_pixels"]=extended_area-area
    if extended_area>=policy.max_area_fraction_of_window*H.size:
        info["status"]="rejected_oversized_refined_component"
        return None,info
    if extended_area>max(area+15.,area*policy.max_extended_to_H_area_ratio):
        info["status"]="rejected_unbounded_area_ratio"
        return None,info
    ys,xs=np.nonzero(candidate)
    if not len(xs):return None,info
    if (ys.min()==0 or xs.min()==0 or ys.max()==H.shape[0]-1
        or xs.max()==H.shape[1]-1):
        info["status"]="rejected_refined_component_at_crop_edge"
        return None,info
    if not extension.any():
        info["status"]="no_added_pixels_H_retained"
        return None,info
    info["status"]="accepted_H_seeded_extension"
    return candidate,info


def local_stats_competitor_area(labels:np.ndarray,indices:np.ndarray)->np.ndarray:
    """Return original H CC pixel counts for competitor IDs in the small ROI."""
    sizes=np.bincount(labels.reshape(-1))
    return sizes[indices]


def detect_window_H_seeded(
    raw:np.ndarray,H:np.ndarray,S:np.ndarray,fused:np.ndarray,
    *,
    cfg:FusionConfig=FusionConfig(),
    policy:HSeedConfig=HSeedConfig(),
    h_low_threshold_dn:float=170.,
    h_high_threshold_dn:float=230.,
    h_low_threshold_map:np.ndarray|None=None,
    h_high_threshold_map:np.ndarray|None=None,
)->dict:
    """Detect ALL H components, refine each independently where safely possible.

    This public API does NOT take human seed points or polygons.
    """
    if raw.ndim!=2 or raw.dtype!=np.uint16:
        raise TypeError("RAW must be 2D uint16 real DN")
    if not (raw.shape==H.shape==S.shape==fused.shape):
        raise ValueError("RAW/H/S/BlackHat shape mismatch")
    if raw.shape[0]<190 or raw.shape[1]<190:
        raise ValueError("at least 190px cropped RAW required")
    if np.any(S&~H):
        raise ValueError("strong H seed pixels must be contained by H support")
    if h_low_threshold_map is None:
        if np.any(H&(fused<float(h_low_threshold_dn))):
            raise ValueError("H support below its BlackHat low threshold")
    else:
        if h_low_threshold_map.shape!=H.shape:
            raise ValueError("H low threshold map shape mismatch")
        if np.any(H&(fused<h_low_threshold_map)):
            raise ValueError("H support below local low threshold surface")
    if h_high_threshold_map is None:
        if np.any(S&(fused<float(h_high_threshold_dn))):
            raise ValueError("H seeds below its BlackHat high threshold")
    else:
        if h_high_threshold_map.shape!=H.shape:
            raise ValueError("H high threshold map shape mismatch")
        if np.any(S&(fused<h_high_threshold_map)):
            raise ValueError("H seeds below local high threshold surface")
    labels,Hstats,centroids,Haudit=_H_component_catalog(H,S,fused)
    count=len(Haudit)
    if count>policy.max_output_regions_per_window:
        raise RuntimeError(f"H seed overflow {count}: refusing silent truncation")

    methods={}
    for source in SOURCE_NAMES:
        response=compute_local_residual(raw,source)
        low,high,stats=_robust_thresholds(response,cfg)
        binary=np.uint8(response>=low)
        n,cc,CCstats,_=cv2.connectedComponentsWithStats(
            binary,connectivity=8,ltype=cv2.CV_32S
        )
        methods[source]={"response":response,"low":low,"high":high,
                         "CClabels":cc,"CCstats":CCstats,
                         "diagnostic":{
                             **stats,"low_threshold_DN":low,
                             "high_threshold_DN":high,
                             "source_low_components":int(n-1),
                             "independent_candidates_allowed":False,
                         }}
    hprops=[]
    proposals=[]
    raw_audit=[]
    source_props=[]
    output=[]
    links=[]
    for j in range(1,count+1):
        a=Haudit[j-1]
        x,y,w,h=(int(a[k]) for k in ("bbox_x","bbox_y","bbox_w","bbox_h"))
        Hmask=(labels==j)
        area=int(a["area_px"])
        edge=bool(x==0 or y==0 or x+w==raw.shape[1] or y+h==raw.shape[0])
        peak=float(a["fused_blackhat_peak_dn"])
        Huid=a["local_H_id"]
        hprop=Proposal(
            source="H170_230",mask=Hmask,
            center_x=float(centroids[j,0]),center_y=float(centroids[j,1]),
            bbox=(x,y,w,h),area_px=area,
            response_peak_dn=peak,edge=edge,
            overgrown=bool(area>=cfg.max_mask_area_fraction*H.size),
            raw_h_overlap_px=area,
            low_threshold_dn=(float(h_low_threshold_dn) if h_low_threshold_map is None
                              else float(np.median(h_low_threshold_map[Hmask]))),
            high_threshold_dn=(float(h_high_threshold_dn) if h_high_threshold_map is None
                               else float(np.median(h_high_threshold_map[Hmask]))),
            excluded_from_safe_fusion=False,uid=Huid
        )
        hprops.append(hprop)
        candidates=[Hmask]
        accepted={}
        rejected=[]
        bounded_methods=[]
        for source in SOURCE_NAMES:
            method=methods[source]
            mask,log=_refinement_by_H_seed(
                raw,H,labels,j,Hmask,source,method["response"],
                method["CClabels"],method["CCstats"],method["low"],
                method["high"],cfg,policy)
            if (policy.enable_bounded_extension_fallback and mask is None
                and area>=3 and log["status"] in {
                    "rejected_source_component_touches_window_edge",
                    "rejected_large_background_component",
                    "rejected_bridge_between_independent_H_seeds",
                }):
                from src.detection.case03e2_bounded_rescue import (
                    rescue_bounded_H_extension
                )
                rescued,diag=rescue_bounded_H_extension(
                    H,Hmask,labels,method["response"],method["low"],
                    owner_label=j,
                    radius_px=policy.bounded_fallback_radius_px,
                    max_area_multiplier=policy.bounded_fallback_max_area_ratio
                )
                log["source_global_rejection_status"]=log["status"]
                log.update({"bounded_"+k:v for k,v in diag.items()})
                if rescued is not None:
                    mask=rescued
                    log["status"]="accepted_bounded_H_extension_REVIEW"
                    bounded_methods.append(source)
                else:
                    log["status"]=log["source_global_rejection_status"]
            log["H_local_id"]=Huid
            raw_audit.append(log)
            if mask is not None:
                accepted[source]=mask
                candidates.append(mask)
                box,cx,cy,ar,areaedge=stats_mask(mask)
                proposal=Proposal(
                    source=source,mask=mask,center_x=cx,center_y=cy,
                    bbox=box,area_px=ar,
                    response_peak_dn=float(method["response"][mask].max()),
                    edge=areaedge,overgrown=False,
                    raw_h_overlap_px=area,
                    low_threshold_dn=float(method["low"]),
                    high_threshold_dn=float(method["high"]),
                    excluded_from_safe_fusion=False,
                    uid=f"{source}__{Huid}",
                    meta={"associated_H_source":Huid,
                          "cannot_create_independent_candidate":True}
                )
                proposals.append(proposal)
                source_props.append(proposal)
                links.append({
                    "proposal_id":proposal.uid,
                    "action":"H_seeded_refinement_only",
                    "target_H_id":Huid,"method":source,
                    "source_added_pixels":int(ar-area)
                })
            elif log["status"].startswith("rejected"):
                rejected.append(log["status"])
        if bounded_methods and len(accepted)>=2:
            # When both local estimators were connected to an unsafe global
            # background, their *independently bounded* predictions may
            # disagree on how far the lateral dark halo extends.
            # Use consensus support for added pixels, never a loose union.
            # H core remains fully intact under this operation.
            combined=Hmask|np.logical_and.reduce(list(accepted.values()))
        else:
            combined=np.logical_or.reduce(candidates)
        # Manual outline never participates. Preserve EVERY ORIGINAL H PIXEL,
        # regardless of how noisy local background methods may be.
        if not np.all(combined[Hmask]):
            raise AssertionError("H component lost during fusion")
        box,cx,cy,region_area,cropedge=stats_mask(combined)
        flags=list(dict.fromkeys(rejected))
        if bounded_methods:
            flags.append("bounded_H_extension_requires_independent_review")
        if cropedge or edge:
            flags.append("H_candidate_or_fused_region_crop_edge")
        if region_area>=cfg.max_mask_area_fraction*H.size:
            flags.append("H_source_area_excessive")
        if ("gaussian22" in accepted and "closing61" in accepted):
            aa=int(accepted["gaussian22"].sum())
            bb=int(accepted["closing61"].sum())
            ratio=max(aa,bb)/max(1,min(aa,bb))
            if ratio>policy.max_method_area_ratio:
                flags.append("local_methods_disagree_over_area")
        if cropedge or edge or any(z.startswith("rejected_large_background")
                                   or z.startswith("rejected_source_component_touches")
                                   or z.startswith("rejected_bridge")
                                   for z in rejected):
            status="needs_review_unsafe_context"
        elif bounded_methods:
            status="needs_review_bounded_extension"
        elif any(z in flags for z in (
            "local_methods_disagree_over_area",
            "H_source_area_excessive",
        )):
            status="needs_review_refinement_unstable"
        elif accepted:
            status="provisional_fused"
        elif area<3 and peak<400:
            # Keep the exact original pixel/coordinate in H and lossless
            # outputs, but avoid requiring manual review of hundreds of
            # 1-2px low-priority specks in every crop.
            status="audit_only_H_micro"
        elif area<3:
            status="needs_review_H_micro_high_peak"
        elif area>=policy.high_H_only_area_min_px and peak>=policy.high_H_only_peak_dn:
            status="provisional_H_only"
        else:
            status="needs_review_H_only"
        sources=["H170_230"]+list(accepted)
        output.append(ObjectRegion(
            mask=combined,
            center_x=cx,center_y=cy,area_px=region_area,bbox=box,
            sources=sources,source_proposal_ids=[Huid]+[
                f"{s}__{Huid}" for s in accepted],
            source_count=len(sources),
            H_only=len(accepted)==0,
            status=status,flags=flags,
            max_span_px=max_hull_distance(combined),
            eq_diameter_px=float(2*np.sqrt(region_area/np.pi)),
            source_H_candidate_areas_px=[area],
            excluded_bridge_proposal_count=len(rejected),
            object_id=f"local_object_{j:04d}"
        ))
    # Resolve cross-component added-only pixels without EVER losing original
    # H ownership: all H pixels (every size including one) belong to their
    # original H connected component. Among overlapping extensions allocate
    # each pixel once, deterministic by H pixel area then local CC ID.
    owner=np.zeros_like(labels,dtype=np.int32)
    for j,obj in enumerate(output,1):
        own_h=(labels==j)
        if not np.all(obj.mask[own_h]):
            raise AssertionError("own H pixels disappeared")
        obj.mask[labels>0]=own_h[labels>0]
    # Mark disputed candidate extensions explicitly. Only additions may
    # collide, original H masks are disjoint by connected-component geometry.
    extras=sum((np.uint16(o.mask & ~H) for o in output),
               start=np.zeros_like(H,dtype=np.uint16))
    for j,obj in enumerate(output,1):
        if np.any(extras[obj.mask & ~H]>1):
            obj.flags.append("overlapping_refined_extensions")
            obj.status="needs_review_overlap"
        obj.mask=(obj.mask & ((owner==0) | (owner==j))) # no earlier assignment reused
        owner[obj.mask]=j
        # Do not remove H pixels by the overlay order.
        assert np.all(obj.mask[labels==j])
        if not obj.mask.any():
            raise AssertionError("each H seed must preserve nonempty output")
        box,cx,cy,area,_=stats_mask(obj.mask)
        obj.bbox=box;obj.center_x=cx;obj.center_y=cy;obj.area_px=area
        obj.max_span_px=max_hull_distance(obj.mask)
        obj.eq_diameter_px=float(2*np.sqrt(area/np.pi))

    if not np.array_equal(np.logical_or.reduce(
        [o.mask for o in output]) & H,H) if output else bool(H.any()):
        raise AssertionError("all H pixels must be exactly preserved")
    for source in SOURCE_NAMES:
        methods[source]["diagnostic"]["H_seeded_refined_count"]=sum(
            a["source"]==source and
            a["status"]=="accepted_H_seeded_extension" for a in raw_audit)
        methods[source]["diagnostic"]["rejected_count"]=sum(
            a["source"]==source and a["status"].startswith("rejected") for a in raw_audit)
    return {
        "objects":output,
        "H_audit":Haudit,
        "H_source_proposal_count":len(hprops),
        "H_low_area_audit_only_count":0, # all H now retained in object catalog
        "H_full_window_pixels":int(H.sum()),
        "local_source_diagnostics":{
            s:v["diagnostic"] for s,v in methods.items()
        },
        "local_proposal_audit":raw_audit,
        "association_audit":links,
        "num_source_proposals":len(hprops)+len(proposals),
        "num_output_objects":len(output),
        "num_review_objects":sum(o.status.startswith("needs_review")
                                 for o in output),
        "window_incomplete_due_to_overflow":False,
        "all_proposal_masks":hprops+proposals,
        "image_shape":[int(v) for v in raw.shape],
        "candidate_discovery_mode":"H170230_only",
        "independent_gaussian_morph_candidates":0,
        "H_pixel_conservation":True
    }
