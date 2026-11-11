"""Case03-E2 automated multiple candidates inside a RAW window (NO user seeds).

Existing H170/230 and two independent RAW-background residuals are discovery
sources. H-only seeds must remain recoverable, never treated as definite defects.

The workflow is explicitly not a trained anomaly classifier. All proposals
are provisional; unsafe/background-connected masks are isolated from
measurement output. No human polygon or manual target point is accepted by
the detection API. Windows are selected by the evaluation runner; this is not
yet an exhaustive whole-image detector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import cv2
import numpy as np
from skimage.segmentation import watershed

from src.detection.local_boundary_refinement import (
    compute_local_residual, max_hull_distance
)

METHOD_SOURCES=("gaussian22","closing61")
CANDIDATE_SOURCES=("H170_230",)+METHOD_SOURCES


@dataclass(frozen=True)
class FusionConfig:
    source_min_region_area_px: int=5
    background_high_floor_dn: float=65.
    background_low_floor_dn: float=24.
    high_noise_k: float=4.
    low_noise_k: float=1.8
    max_mask_area_fraction: float=.10
    large_window_span_fraction: float=.80
    max_association_centroid_dist_px: float=25.
    association_intersection_min_px: int=2
    association_small_overlap_fraction: float=.45
    promote_main_min_area_px: int=12
    H_only_provisional_min_area_px: int=12
    H_only_provisional_peak_DN: float=350.
    keep_H_if_area_at_least_px: int=3
    keep_H_if_peak_at_least_dn: int=280
    max_independent_proposals_per_method: int=350
    max_fusion_objects_per_window: int=600


@dataclass
class Proposal:
    source: str
    mask: np.ndarray
    center_x: float
    center_y: float
    bbox: tuple[int,int,int,int]
    area_px: int
    response_peak_dn: float
    edge: bool
    overgrown: bool
    raw_h_overlap_px: int
    low_threshold_dn: float
    high_threshold_dn: float
    excluded_from_safe_fusion: bool=False
    uid: str=""
    meta: dict[str,Any]=field(default_factory=dict)


@dataclass
class ObjectRegion:
    mask: np.ndarray
    center_x: float
    center_y: float
    area_px: int
    bbox: tuple[int,int,int,int]
    sources: list[str]
    source_proposal_ids: list[str]
    source_count: int
    H_only: bool
    status: str
    flags: list[str]
    max_span_px: float
    eq_diameter_px: float
    source_H_candidate_areas_px: list[int]
    excluded_bridge_proposal_count: int
    object_id: str=""


def stats_mask(mask:np.ndarray)->tuple[tuple[int,int,int,int],float,float,int,bool]:
    ys,xs=np.nonzero(mask)
    if len(xs)==0:raise ValueError("empty component")
    H,W=mask.shape
    bx=int(xs.min());by=int(ys.min())
    bbox=(bx,by,int(xs.max()-bx+1),int(ys.max()-by+1))
    edge=bool(bx==0 or by==0 or bx+bbox[2]>=W or by+bbox[3]>=H)
    return bbox,float(xs.mean()),float(ys.mean()),int(len(xs)),edge


def _robust_thresholds(response:np.ndarray,cfg:FusionConfig)->tuple[float,float,dict]:
    """Fixed noise model; no manual labels or polygons, no P99.9 scaling."""
    h,w=response.shape
    # Boundary bands often contain strong geometric transitions; trim
    # samples at 98 percentile to estimate mostly-background variations.
    sub=response[8:max(9,h-8):4,8:max(9,w-8):4].reshape(-1)
    if len(sub)<100:raise ValueError("window too small for robust threshold")
    cap=np.percentile(sub,98)
    clean=sub[sub<=cap]
    med=float(np.median(clean))
    mad=float(1.4826*np.median(np.abs(clean-med)))
    # A strict high/low hysteresis separation is maintained for every source.
    high=max(cfg.background_high_floor_dn,
             med+cfg.high_noise_k*max(mad,1.))
    low=max(cfg.background_low_floor_dn,
            med+cfg.low_noise_k*max(mad,1.))
    if low>=high:
        low=min(high-1,max(cfg.background_low_floor_dn,high*.6))
    return low,high,{"background_median_DN":med,
                     "background_sigma_MAD_DN":mad,
                     "percentile98_response_DN":float(cap)}


def extract_h_proposals(H:np.ndarray,S:np.ndarray,fused:np.ndarray,
                        cfg:FusionConfig)->tuple[list[Proposal],list[dict]]:
    """All H CCs are audited, including low-area noise-like candidates.

    Only H components with ≥3 pixels or sufficiently strong peak are forwarded
    for fusion. The rest remain in all_H_components audit records with intact
    source pixel geometry in the frozen H mask (not deleted).
    """
    h,w=H.shape
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(
        np.uint8(H),connectivity=8,ltype=cv2.CV_32S
    )
    props=[]
    audit=[]
    for label in range(1,count):
        x,y,bw,bh,area=(int(v) for v in stats[label,:5])
        box=labels[y:y+bh,x:x+bw]==label
        peak=int(fused[y:y+bh,x:x+bw][box].max())
        seeds=int(np.count_nonzero(S[y:y+bh,x:x+bw]&box))
        included=bool(area>=cfg.keep_H_if_area_at_least_px
                      or peak>=cfg.keep_H_if_peak_at_least_dn)
        uid=f"Hlocal_{label:04d}"
        audit.append({
            "local_H_id":uid,"bbox_x":x,"bbox_y":y,"bbox_w":bw,"bbox_h":bh,
            "area_px":area,"fused_blackhat_peak_dn":peak,
            "S230_seed_pixel_count":seeds,
            "promoted_to_fusion_pool":included,
            "low_area_H_retained_in_original_mask":not included,
        })
        if not included:continue
        m=np.zeros((h,w),bool)
        m[y:y+bh,x:x+bw]=box
        edge=(x==0 or y==0 or x+bw==w or y+bh==h)
        unsafe=edge or area>cfg.max_mask_area_fraction*h*w
        props.append(Proposal(
            source="H170_230",mask=m,center_x=float(centroids[label,0]),
            center_y=float(centroids[label,1]),bbox=(x,y,bw,bh),area_px=area,
            response_peak_dn=float(peak),edge=edge,
            overgrown=area>cfg.max_mask_area_fraction*h*w,
            raw_h_overlap_px=area,low_threshold_dn=170,
            high_threshold_dn=230,excluded_from_safe_fusion=unsafe,uid=uid,
            meta={"S230_seed_pixels":seeds,"fused_peak_exact_dn":peak}
        ))
    return props,audit


def extract_local_proposals(raw:np.ndarray,H:np.ndarray,source:str,
                            cfg:FusionConfig)->tuple[list[Proposal],dict,list[dict]]:
    """Adaptive high-seed/low-mask watershed to keep independent local spots.

    Marker-controlled watershed prevents a low-response bridge automatically
    merging separately identifiable high-response peaks. Results reaching a
    crop edge or oversized regions are retained as UNSAFE evidence, not used
    to inflate a physical contour or join independent detections.
    """
    if source not in METHOD_SOURCES:raise ValueError("bad source")
    response=compute_local_residual(raw,source)
    low,high,noise=_robust_thresholds(response,cfg)
    lowmask=(response>=low)
    strong=(response>=high)
    # Light 3x3 morphological opening on high markers suppresses scattered
    # isolated noise *at the local-source layer only*; H covers micro-spots.
    strong=cv2.morphologyEx(np.uint8(strong),cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))).astype(bool)
    _,markers,stats,_=cv2.connectedComponentsWithStats(
        np.uint8(strong),connectivity=8,ltype=cv2.CV_32S
    )
    if np.count_nonzero(markers)==0:
        return [],{**noise,"low_threshold_DN":low,"high_threshold_DN":high,
                   "seed_count":0,"raw_proposal_count":0,"retained_count":0},[]
    seeds=int(markers.max())
    # Watershed markers should not include strong regions that have area<3,
    # because H-alone candidate catalog still preserves such micro peaks.
    marker_mask=np.zeros_like(markers,dtype=np.int32)
    n=0
    for j in range(1,seeds+1):
        if stats[j,cv2.CC_STAT_AREA]<3:continue
        n+=1
        marker_mask[markers==j]=n
    if n==0:
        return [],{**noise,"low_threshold_DN":low,"high_threshold_DN":high,
                   "seed_count":0,"raw_proposal_count":0,"retained_count":0},[]
    zones=watershed(-response,markers=marker_mask,mask=lowmask,
                    watershed_line=False).astype(np.int32)
    candidates=[]
    audit=[]
    h,w=raw.shape
    for sid in range(1,n+1):
        pixel=(zones==sid)
        area=int(pixel.sum())
        if not area:continue
        box,cx,cy,count,edge=stats_mask(pixel)
        peak=float(response[pixel].max())
        over=area>cfg.max_mask_area_fraction*h*w
        span=box[2]>=cfg.large_window_span_fraction*w or box[3]>=cfg.large_window_span_fraction*h
        unsafe=bool(edge or over or span)
        keep=area>=cfg.source_min_region_area_px
        uid=f"{source}_{sid:04d}"
        audit.append({"proposal_id":uid,"area_px":area,"peak_DN":peak,
                      "bbox":list(box),"forwarded":keep,
                      "edge":edge,"overgrown":over,
                      "long_background_span":span})
        if not keep:continue
        candidates.append(Proposal(
            source=source,mask=pixel,center_x=cx,center_y=cy,
            bbox=box,area_px=area,response_peak_dn=peak,
            edge=edge,overgrown=over,raw_h_overlap_px=int((pixel&H).sum()),
            low_threshold_dn=low,high_threshold_dn=high,
            excluded_from_safe_fusion=unsafe,uid=uid,
            meta={"background_span_flag":bool(span)}
        ))
    if len(candidates)>cfg.max_independent_proposals_per_method:
        # No silent truncation: caller gets explicit unsafe count and
        # must never claim complete local candidate discovery.
        return candidates,{
            **noise,"low_threshold_DN":low,"high_threshold_DN":high,
            "seed_count":n,"raw_proposal_count":len(audit),
            "retained_count":len(candidates),
            "over_limit_requires_review":True
        },audit
    return candidates,{
        **noise,"low_threshold_DN":low,"high_threshold_DN":high,
        "seed_count":n,"raw_proposal_count":len(audit),
        "retained_count":len(candidates),
        "over_limit_requires_review":False
    },audit


def _intersection_size(a:Proposal,b:Proposal)->int:
    ax,ay,aw,ah=a.bbox
    bx,by,bw,bh=b.bbox
    x0=max(ax,bx);y0=max(ay,by)
    x1=min(ax+aw,bx+bw);y1=min(ay+ah,by+bh)
    if x0>=x1 or y0>=y1:return 0
    return int(np.count_nonzero(a.mask[y0:y1,x0:x1] &
                                 b.mask[y0:y1,x0:x1]))


def _association(a:Proposal,b:Proposal,cfg:FusionConfig)->tuple[bool,int,float]:
    # Avoid same-source self-merging: watershed / H CC identities are separate.
    if a.source==b.source or a.excluded_from_safe_fusion or b.excluded_from_safe_fusion:
        return False,0,0.
    delta=np.hypot(a.center_x-b.center_x,a.center_y-b.center_y)
    if delta>cfg.max_association_centroid_dist_px:return False,0,0.
    inter=_intersection_size(a,b)
    overlap=inter/min(a.area_px,b.area_px) if min(a.area_px,b.area_px) else 0.
    return (inter>=cfg.association_intersection_min_px and
            overlap>=cfg.association_small_overlap_fraction),inter,overlap


def _labels_to_objects(
    proposals:list[Proposal],cfg:FusionConfig
)->tuple[list[ObjectRegion],list[dict]]:
    """One-owner conservative matching; cannot bridge two independent H seeds.

    Each Gaussian/closing proposal can attach to at most one H target, and a
    single H target can have one contributor per method. Other regions remain
    independent candidates, NOT forcibly joined by transitive union.
    """
    safe_H=[p for p in proposals if p.source=="H170_230"
            and not p.excluded_from_safe_fusion]
    unsafe=[p for p in proposals if p.excluded_from_safe_fusion]
    local=[p for p in proposals if p.source!="H170_230"
           and not p.excluded_from_safe_fusion]
    groups:[[Proposal]]=[[h] for h in safe_H]
    links=[]
    for p in sorted(local,key=lambda r:(-r.area_px,-r.response_peak_dn,r.uid)):
        ranked=[]
        for i,group in enumerate(groups):
            if any(g.source==p.source for g in group):continue
            for existing in group:
                matched,n,ratio=_association(existing,p,cfg)
                if matched:
                    ranked.append((i,n,ratio,existing.uid))
        if ranked:
            by_group={}
            for i,n,ratio,uid in ranked:
                if i not in by_group or n>by_group[i][0]:
                    by_group[i]=(n,ratio,uid)
            best=sorted(by_group.items(),key=lambda kv:(-kv[1][0],-kv[1][1],kv[0]))
            if len(best)>1:
                # If a new method mask bridges multiple H seed objects,
                # DO NOT fuse; flag it and preserve as separate review evidence.
                h_groups=[i for i,v in best if any(
                    member.source=="H170_230" for member in groups[i])]
                if len(h_groups)>1:
                    p.meta["multi_H_conflict_groups"]=len(h_groups)
                    groups.append([p])
                    links.append({"proposal_id":p.uid,
                        "action":"separate_bridge_review","H_groups":h_groups})
                    continue
            gidx=best[0][0]
            groups[gidx].append(p)
            links.append({"proposal_id":p.uid,"action":"associated",
                          "target_group":gidx,
                          "overlap_pixels":best[0][1][0]})
        else:
            groups.append([p])
            links.append({"proposal_id":p.uid,"action":"new_unassociated"})
    # Edge / oversized regions are retained but MUST NOT force
    # neighborhoods into one fused contour.
    for p in unsafe:
        groups.append([p])
        links.append({"proposal_id":p.uid,"action":"unsafe_standalone_review"})
    result=[]
    for group in groups:
        sources=sorted(set(p.source for p in group))
        # Exclude risky members from the measured union, except if the
        # entire object is risky: retain pixels and flag no-final-size.
        flags=[]
        if any(p.edge for p in group):flags.append("crop_edge")
        if any(p.overgrown for p in group):flags.append("overgrown")
        if any(p.meta.get("background_span_flag") for p in group):
            flags.append("wide_background_bridge")
        if any(p.meta.get("multi_H_conflict_groups") for p in group):
            flags.append("multiple_H_seed_bridge")
        union=np.zeros_like(group[0].mask,dtype=bool)
        safe=[p for p in group if not p.excluded_from_safe_fusion]
        for p in (safe if safe else group):
            union|=p.mask
        box,cx,cy,area,edge=stats_mask(union)
        # Multi-source overlap is never 'proved physical' just from support.
        h_members=[p for p in group if p.source=="H170_230"]
        H_only=len(sources)==1 and sources[0]=="H170_230"
        if flags:
            status="needs_review_unsafe_boundary"
        elif H_only:
            # H-only micro responses are scientifically valuable for recall,
            # but most 3-5px isolated structures are noise. Retain in the
            # review catalog, do not auto-accept hundreds as measured defects.
            hpeak=max((p.response_peak_dn for p in h_members),default=0.)
            if area>=cfg.H_only_provisional_min_area_px and hpeak>=cfg.H_only_provisional_peak_DN:
                status="provisional_H_only"
            else:
                status="needs_review_H_only"
        elif area>=cfg.promote_main_min_area_px and len(sources)>=2:
            status="provisional_fused"
        else:
            status="needs_review_single_method"
        if edge and "crop_edge" not in flags:
            flags.append("crop_edge")
            status="needs_review_unsafe_boundary"
        if area>cfg.max_mask_area_fraction*union.size:
            if "overgrown" not in flags:flags.append("overgrown")
            status="needs_review_unsafe_boundary"
        result.append(ObjectRegion(
            mask=union,center_x=cx,center_y=cy,area_px=area,
            bbox=box,sources=sources,
            source_proposal_ids=[p.uid for p in group],
            source_count=len(sources),
            H_only=H_only,status=status,flags=flags,
            max_span_px=max_hull_distance(union),
            eq_diameter_px=float(2*np.sqrt(area/np.pi)),
            source_H_candidate_areas_px=[p.area_px for p in h_members],
            excluded_bridge_proposal_count=sum(
                bool(p.meta.get("multi_H_conflict_groups")) for p in group
            )
        ))
    # Unsafe local responses (large background bridges or edge-connected
    # dark bands) must not be ignored merely because the safe H-only core
    # stayed separate. Propagate nearby overlapping bridge risk without ever
    # merging the unsafe pixels into the measured mask.
    unsafe_bridge=[p for p in unsafe if
        p.area_px>cfg.max_mask_area_fraction*p.mask.size or
        p.meta.get("background_span_flag")]
    for o in result:
        if o.area_px<=0 or o.status.startswith("needs_review"):
            continue
        matched=[p.uid for p in unsafe_bridge
                 if p.bbox[0]<o.bbox[0]+o.bbox[2]
                 and o.bbox[0]<p.bbox[0]+p.bbox[2]
                 and p.bbox[1]<o.bbox[1]+o.bbox[3]
                 and o.bbox[1]<p.bbox[1]+p.bbox[3]
                 and int(np.count_nonzero(o.mask&p.mask))>=
                      max(3,int(np.ceil(.20*o.area_px)))]
        if matched:
            o.flags.append("unsafe_local_background_bridge_evidence")
            o.status="needs_review_unsafe_context"
    # One target can include many pixels, but unrelated targets should never
    # share measured pixels in this ROI; resolve overlaps by provenance priority.
    # Preserve rejected overlap in logs; prevent invalid doubled measurement.
    result.sort(key=lambda o:(o.status.startswith("needs_review"),
                              -o.source_count,-o.area_px,o.center_y,o.center_x))
    occupied=np.zeros_like(result[0].mask,dtype=bool) if result else np.zeros((0,0),bool)
    for idx,obj in enumerate(result,1):
        collision=int(np.count_nonzero(obj.mask&occupied))
        if collision:
            obj.flags.append("shared_pixels_with_other_proposal")
            obj.status="needs_review_overlap"
            obj.mask=obj.mask&~occupied
            if not obj.mask.any():
                obj.area_px=0
                obj.bbox=(0,0,0,0)
                obj.max_span_px=0.
                obj.eq_diameter_px=0.
            else:
                obj.bbox,obj.center_x,obj.center_y,obj.area_px,_=stats_mask(obj.mask)
                obj.max_span_px=max_hull_distance(obj.mask)
                obj.eq_diameter_px=float(2*np.sqrt(obj.area_px/np.pi))
        occupied|=obj.mask
        obj.object_id=f"local_object_{idx:04d}"
    return result,links


def detect_window(
    raw:np.ndarray,H:np.ndarray,S:np.ndarray,fused:np.ndarray,
    *,cfg:FusionConfig=FusionConfig()
)->dict:
    """Fully automatic multiple-candidate detector for ONE image crop.

    Exactly four image arrays are passed; no manual center, polygon,
    annotated defect size or manually approved candidate-ID is an input.
    """
    if not (raw.shape==H.shape==S.shape==fused.shape):
        raise ValueError("source window sizes mismatch")
    if raw.ndim!=2 or raw.dtype!=np.uint16:
        raise TypeError("raw window must be original uint16 DN")
    if raw.shape[0]<190 or raw.shape[1]<190:
        raise ValueError("window must be >=190 in both dimensions")
    if np.any(S&~H):
        raise ValueError("H170/230 must contain every S230 strong pixel")
    hprops,haudit=extract_h_proposals(H,S,fused,cfg)
    allprops=list(hprops)
    local_details={}
    all_local_audit=[]
    for method in METHOD_SOURCES:
        props,diagnostic,audit=extract_local_proposals(raw,H,method,cfg)
        allprops.extend(props)
        local_details[method]=diagnostic
        all_local_audit.extend([{"source":method,**a} for a in audit])
    objects,association_audit=_labels_to_objects(allprops,cfg)
    unsafe_count=sum(o.status.startswith("needs_review") for o in objects)
    global_unsafe=any(
        local_details[method].get("over_limit_requires_review",False)
        for method in METHOD_SOURCES
    ) or len(objects)>cfg.max_fusion_objects_per_window
    if global_unsafe:
        # Annotate every proposal; do not silently cap or drop any candidate.
        for o in objects:
            if "candidate_overflow" not in o.flags:
                o.flags.append("candidate_overflow")
            o.status="needs_review_candidate_overflow"
    # Returned source+objects can be rendered with per-object numbers and
    # saved as bbox-local lossless masks.  No auto "defect count" claim.
    return {
        "objects":objects,
        "H_audit":haudit,
        "H_source_proposal_count":len(hprops),
        "H_low_area_audit_only_count":sum(
            not a["promoted_to_fusion_pool"] for a in haudit),
        "H_full_window_pixels":int(H.sum()),
        "local_source_diagnostics":local_details,
        "local_proposal_audit":all_local_audit,
        "association_audit":association_audit,
        "num_source_proposals":len(allprops),
        "num_output_objects":len(objects),
        "num_review_objects":unsafe_count,
        "window_incomplete_due_to_overflow":bool(global_unsafe),
        "all_proposal_masks":allprops,
        "image_shape":[int(v) for v in raw.shape]
    }
