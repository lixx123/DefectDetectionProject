"""K8D multi-source contour stability and reversible review masks.

DATA POLICY: no source J5/B modification; a stable grouping is a hypothesis,
NOT a merge of defect IDs. All pixel area is detector-plane-equivalent.
"""
from dataclasses import dataclass
import cv2
import numpy as np

@dataclass(frozen=True)
class K8DConfig:
    min_seed_overlap_fraction:float=.60
    max_outer_px:int=2000
    max_ratio_3_to_2:float=1.35
    max_ratio_2_to_1p5:float=1.25
    max_nesting_loss:float=.07
    max_compact_aspect:float=2.8
    min_group_coverage:float=.80
    max_neighbor_groups:int=8
    min_group_component_area:int=3
    max_partial_overlap_px:int=3
    max_partial_overlap_fraction:float=.10
    min_growth_over_seed:float=1.12

def area(x):return int(np.count_nonzero(x))

def aspect(mask):
    yy,xx=np.nonzero(mask)
    if len(xx)<4:return 1.
    ev=np.linalg.eigvalsh(np.cov(np.column_stack([xx,yy]).astype(float).T))
    return float(np.sqrt(max(float(ev.max()),1.)/max(float(ev.min()),1.)))

def group_evidence(raw_mask,labels,all_areas,owner,conf):
    """Full global B-label areas prevent false grouping of cropped neighbors."""
    found=[]
    for k in np.unique(labels[raw_mask]):
        k=int(k)
        if not k or k==owner:continue
        count=area(raw_mask&(labels==k))
        if k>=len(all_areas) or all_areas[k]<=0:raise ValueError("missing global B area")
        total=int(all_areas[k]);fraction=count/total
        tiny=total<conf.min_group_component_area
        whole=not tiny and fraction>=conf.min_group_coverage
        conflict=not tiny and not whole and (
            count>conf.max_partial_overlap_px or
            fraction>conf.max_partial_overlap_fraction)
        found.append({"B_label":k,"source_full_px":total,
                      "inside_raw_px":count,"whole_overlap_fraction":round(fraction,5),
                      "micro_collision":bool(tiny),
                      "eligible_same_spot_review":bool(whole),
                      "partial_competitor":bool(conflict)})
    siblings=sorted(e["B_label"] for e in found if e["eligible_same_spot_review"])
    conflicts=sorted(e["B_label"] for e in found if e["partial_competitor"])
    return {"primary_B_label":int(owner),
            "proposed_review_B_member_labels":[int(owner)]+siblings,
            "eligible_siblings":siblings,"partial_competitors":conflicts,
            "microscopic_collisions":[e["B_label"] for e in found if e["micro_collision"]],
            "member_evidence":found,
            "too_many_siblings":len(siblings)>conf.max_neighbor_groups,
            "official_ID_merge_performed":False}

def resolve(seed,trials,audits,core,labels,all_areas,source_id,
            conf=K8DConfig()):
    """Select strongest credible RAW envelope, then relax only if stable.

    Important: may show a FULL orange ambiguity contour rather than revert to
    tiny B-seed. A missing/unsupported 3MAD anchor must NOT allow huge 1.5MAD.
    """
    seed=np.asarray(seed,bool);core=np.asarray(core,bool)
    labels=np.asarray(labels,np.int32)
    if not(seed.shape==core.shape==labels.shape==(128,128)):raise ValueError("128px geometry mismatch")
    if not seed.any() or np.any(seed&~core):raise ValueError("invalid source")
    if not np.all(labels[seed]==source_id):raise ValueError("source labels mismatch")
    masks={k:np.asarray(trials[k],bool) for k in (3.,2.,1.5)}
    if any(m.shape!=seed.shape for m in masks.values()):raise ValueError("invalid RAW trial shapes")
    sizes={str(k):area(mask) for k,mask in masks.items()}
    strict=masks[3.]
    coverage=area(strict&seed)/area(seed)
    audit={"old_source_area_px":area(seed),"raw_area_by_sigma":sizes,
           "raw_3mad_source_coverage":round(coverage,5),
           "any_source_pixels_deleted":False,
           "new_physical_boundary_certified":False}
    if area(strict)==0 or coverage<conf.min_seed_overlap_fraction:
        meta={"status":"SOURCE_ONLY_UNRELIABLE_3MAD","selected_k":None,
              "reasons":["NO_RELIABLE_STRICT_SOURCE_ANCHOR"],
              "stability":[],"group":group_evidence(seed,labels,all_areas,source_id,conf),**audit}
        return seed.copy(),meta
    safety=[]
    if area(strict)>conf.max_outer_px:safety.append("STRICT_ABSOLUTE_MAX_AREA")
    if np.any(strict&~core):safety.append("STRICT_CROSSES_WORK_BAND_CORE")
    if bool(audits[3.].get("raw_proposal_touches_roi_border")):
        safety.append("STRICT_TOUCHES_ROI_BORDER")
    if bool(audits[3.].get("raw_proposal_touches_radius_cap")):
        safety.append("STRICT_TOUCHES_RADIUS_CAP")
    if aspect(strict)>conf.max_compact_aspect:safety.append("STRICT_NONCOMPACT_SHAPE")
    if safety:
        # Full 3MAD may still be useful for human review, but never stable.
        full=strict|seed
        return full,{"status":"CENSORED_FULL_OUTER_REVIEW","selected_k":3.,
                     "reasons":safety,"stability":[],
                     "group":group_evidence(strict,labels,all_areas,source_id,conf),**audit}
    chosen=3.
    check=[]
    prior=3.
    for k,limit in ((2.,conf.max_ratio_3_to_2),(1.5,conf.max_ratio_2_to_1p5)):
        old=masks[prior];new=masks[k]
        rejected=[]
        if area(new)==0:rejected.append("RELAXED_CONTOUR_MISSING")
        else:
            if area(new)/max(area(old),1)>limit:rejected.append("UNSTABLE_GROWTH")
            if area(old&~new)/max(area(old),1)>conf.max_nesting_loss:
                rejected.append("NONNESTED_BOUNDARIES")
            if area(new)>conf.max_outer_px:rejected.append("ABSOLUTE_AREA_CAP")
            if aspect(new)>conf.max_compact_aspect:rejected.append("NONCOMPACT_SHAPE")
            if area(new&seed)/area(seed)<conf.min_seed_overlap_fraction:
                rejected.append("SEED_SUPPORT_LOSS")
            if np.any(new&~core):rejected.append("CROSSES_WORK_CORE")
            if bool(audits[k].get("raw_proposal_touches_roi_border")):
                rejected.append("TOUCHES_ROI_BORDER")
            if bool(audits[k].get("raw_proposal_touches_radius_cap")):
                rejected.append("TOUCHES_RADIUS_CAP")
        check.append({"from_k":prior,"to_k":k,
                      "area_growth_ratio":round(area(new)/max(area(old),1),5),
                      "nesting_loss":round(area(old&~new)/max(area(old),1),5),
                      "reasons":rejected})
        if rejected:break
        chosen=k;prior=k
    proposed=masks[chosen]|seed
    groups=group_evidence(masks[chosen],labels,all_areas,source_id,conf)
    reasons=[]
    if groups["too_many_siblings"]:reasons.append("TOO_MANY_SIBLINGS")
    if groups["partial_competitors"]:reasons.append("UNRESOLVED_PARTIAL_B_COMPONENTS")
    if area(proposed)<area(seed)*conf.min_growth_over_seed:
        status="SOURCE_ONLY_NO_MEANINGFUL_EXPANSION"
    elif np.any(proposed&~core):
        status="CENSORED_FULL_OUTER_REVIEW"
        reasons.append("SOURCE_UNION_OUTSIDE_WORK_CORE")
    elif reasons:
        status="AMBIGUOUS_FULL_OUTER_REVIEW"
    elif groups["eligible_siblings"]:
        status="STABLE_GROUP_OUTER_REVIEW"
    else:
        status="STABLE_SINGLE_OUTER_REVIEW"
    return proposed,{"status":status,"selected_k":chosen,"reasons":reasons,
                     "stability":check,"group":groups,**audit}
