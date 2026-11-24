"""Case03-K5 experimental: noise-adaptive halo and conservative J5 sibling association.

* All candidates are anchored to existing J5 IDs (NO newly discovered defects).
* Never uses manual labels or changes frozen J5 global IDs, source masks/grades.
* Group proposals are review-only. Their old IDs stay distinct until human
  approval and independent evaluation; the outer mask is NOT physical truth.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import cv2,numpy as np
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,raw_outer_envelope,aspect_and_bbox
)


@dataclass(frozen=True)
class AdaptiveConfig:
    floor_sweep:tuple[float,...]=(3.0,2.0,1.5)
    max_initial_raw_to_h61:float=1.8
    max_relaxed_vs_initial:float=2.5
    max_low_floor_vs_middle:float=1.22
    max_proposed_area_px:int=2200
    max_extra_connected_neighbors:int=8
    min_sibling_inside_fraction:float=.85
    max_one_sibling_area_px:int=160
    max_group_source_fraction:float=.30
    max_envelope_aspect:float=2.6
    min_center_seed_coverage:float=.6
    # Candidate edge must remain within cropped RAW and original ROI limits.
    min_envelope_area_over_h61:float=1.

    def validate(self):
        assert self.floor_sweep==(3.0,2.0,1.5)
        if not 0<self.min_sibling_inside_fraction<=1:raise ValueError("bad coverage")
        if self.max_extra_connected_neighbors<0:raise ValueError("bad neighbor count")
        if self.max_envelope_aspect<=1:raise ValueError("bad aspect")


def choose_adaptive_envelope(
    raw128:np.ndarray,source128:np.ndarray,center:tuple[float,float],
    h61_area:int,old_config:PilotConfig,conf:AdaptiveConfig,
    extractor:Callable|None=None
)->tuple[np.ndarray,dict,dict]:
    """Compare RAW contour stability while varying only the local MAD floor.

    Rule is predeclared, label-free: keep k=3 unless weak relative expansion
    (area/H61 <=1.8), 1.5sigma plateau vs 2sigma, and finite growth from
    the initial 3sigma result. Prevents simply dropping threshold globally.
    """
    conf.validate()
    extraction=extractor or raw_outer_envelope
    cases={}
    for floor in conf.floor_sweep:
        from dataclasses import replace
        trial=replace(old_config,raw_noise_sigma_multiplier=floor)
        mask,audit=extraction(raw128,source128,center,trial)
        assert mask.shape==source128.shape
        cases[floor]=(mask,audit)
    first,first_audit=cases[3.]
    middle,middle_audit=cases[2.]
    low,low_audit=cases[1.5]
    area0=int(first.sum());area2=int(middle.sum());area1=int(low.sum())
    reasons=[]
    if area0==0: reasons.append("NO_RELIABLE_3SIGMA_SEED")
    if h61_area<=0: reasons.append("H61_AREA_ZERO")
    if area0/max(h61_area,1)>conf.max_initial_raw_to_h61:
        reasons.append("INITIAL_ENVELOPE_SUFFICIENT_RELATIVE_TO_H61")
    if area2==0 or area1==0:
        reasons.append("RELAXED_ENVELOPE_MISSING")
    elif area1/area2>conf.max_low_floor_vs_middle:
        reasons.append("LOW_FLOOR_CONTOUR_NOT_STABLE")
    if area0 and area1>conf.max_relaxed_vs_initial*area0:
        reasons.append("LOW_FLOOR_GROWTH_TOO_AGGRESSIVE")
    if area1>conf.max_proposed_area_px:
        reasons.append("LOW_FLOOR_AREA_UNBOUNDED")
    if low_audit["raw_proposal_touches_roi_border"] or low_audit[
        "raw_proposal_touches_radius_cap"]:
        reasons.append("LOW_FLOOR_GEOMETRY_CENSORED")
    if low_audit["raw_proposal_seed_overlap_fraction"]<conf.min_center_seed_coverage:
        reasons.append("LOW_FLOOR_SEED_LOST")
    # In selecting k, NO ground truth or neighbor grouping evidence is used.
    chosen=1.5 if not reasons else 3.
    mask,meta=cases[chosen]
    summary={
       "rule":"3sigma unless underexpanded vs H61 and 1.5sigma stable after 2sigma",
       "floor_selected_sigma":chosen,
       "floor_3_area_px2":area0,
       "floor_2_area_px2":area2,
       "floor_1p5_area_px2":area1,
       "floor_2_to_1p5_area_ratio":round(area1/max(area2,1),4),
       "floor_3_to_1p5_area_ratio":round(area1/max(area0,1),4),
       "raw3_to_H61_area_ratio":round(area0/max(h61_area,1),4),
       "adaptive_kept_strict_reasons":";".join(reasons),
       "original_source_untouched":True
    }
    return mask,meta,summary


def audit_object_membership(
    proposed:np.ndarray,
    primary_id:str,
    label_id_map:np.ndarray,
    area_by_id:dict[str,int],
    audit:dict,
    conf:AdaptiveConfig
)->dict:
    """Assess all J5 objects touched by ONE connected RAW envelope.

    Competing source objects are eligible only if almost all their *global*
    source pixels are within the same envelope, and no one is a large/line
    object. Returns a proposed review group, NEVER automatic ID union.
    Label grid is string/object, None = no prior J5 pixel.
    """
    if proposed.shape!=label_id_map.shape:
        raise ValueError("pixel map and proposal must have same geometry")
    if not primary_id:raise ValueError("primary ID missing")
    present=[v for v in np.unique(label_id_map[proposed])
             if v is not None and v!="" and str(v).lower()!="nan"]
    # np.unique on None + str object-array isn't ordered across Python types;
    # see label grid construction: all labels encoded as fixed-length unicode.
    present=[str(v) for v in present]
    if primary_id not in present:
        return {
          "group_status":"REJECTED_SEED_ABSENT",
          "proposed_review_group_ids":[],
          "competing_J5_ids":sorted(v for v in present if v!=primary_id),
          "group_reject_reasons":["OWN_J5_SOURCE_NOT_IN_RAW_ENVELOPE"],
          "member_evidence":[]
        }
    siblings=sorted(x for x in present if x!=primary_id)
    rejections=[]
    if len(siblings)>conf.max_extra_connected_neighbors:
        rejections.append("TOO_MANY_COMPETING_J5_IDS")
    if audit.get("raw_proposal_touches_roi_border",False) or audit.get(
        "raw_proposal_touches_radius_cap",False):
        rejections.append("CONTOUR_TOUCHES_LIMIT")
    ratio,_=aspect_and_bbox(proposed)
    if np.isfinite(ratio) and ratio>conf.max_envelope_aspect:
        rejections.append("LONG_THIN_ENVELOPE_NOT_A_SPOT")
    evidence=[]
    all_total=int(area_by_id.get(primary_id,0))
    if not all_total:rejections.append("UNKNOWN_PRIMARY_SOURCE_AREA")
    for id_ in siblings:
        matched=int(np.count_nonzero(proposed & (label_id_map==id_)))
        total=int(area_by_id.get(id_,0))
        share=matched/max(total,1)
        evidence.append({
           "global_defect_id":id_,
           "source_total_area_px2":total,
           "source_pixels_inside_candidate":matched,
           "source_coverage_fraction":round(share,4),
           "whole_object_covered":share>=conf.min_sibling_inside_fraction
        })
        all_total+=total
        if total==0:rejections.append("UNKNOWN_SIBLING_SOURCE_AREA:"+id_)
        if share<conf.min_sibling_inside_fraction:
            rejections.append("INCOMPLETE_SIBLING_COVERAGE:"+id_)
        if total>conf.max_one_sibling_area_px:
            rejections.append("LARGE_SIBLING_NOT_AUTO_GROUPABLE:"+id_)
    if proposed.sum()==0:rejections.append("NO_OUTER_CONTOUR")
    elif all_total/proposed.sum()>conf.max_group_source_fraction:
        rejections.append("GROUP_SOURCE_DENSITY_TOO_HIGH")
    if len(siblings)==0:
        status="NO_SIBLING_CONFLICT"
    elif rejections:
        status="CONFLICT_UNRESOLVED_REVIEW"
    else:
        status="COHERENT_GROUP_REVIEW"  # STILL NEEDS MANUAL CONFIRMATION
    return {
        "group_status":status,
        "proposed_review_group_ids":sorted([primary_id]+siblings) if
          status=="COHERENT_GROUP_REVIEW" else [],
        "competing_J5_ids":siblings,
        "group_reject_reasons":rejections,
        "member_evidence":evidence,
        "candidate_pixel_count":int(proposed.sum()),
        "source_pixels_accounted":int(all_total),
        "new_global_ID_created":False,
        "official_membership_changed":False,
        "human_review_required_for_merging":True
    }


def render_status(
    original:np.ndarray,raw_candidate:np.ndarray,outer_audit:dict,
    grouping:dict,other_gate_reasons:list[str]
)->tuple[str,np.ndarray]:
    """Never erase a valid computed candidate just because a guard failed.

    Approved = cyan suggested outline (still provisional).
    Group = amber/yellow proposed collective outline (not merged).
    Others = amber review-only outline; original red core retained separately.
    """
    if not np.any(raw_candidate):
        return "NO_RAW_OUTER_KEEP_J5",original.copy()
    if other_gate_reasons:
        return "REJECTED_HALO_DISPLAY_REVIEW_ONLY",raw_candidate|original
    if grouping["group_status"]=="COHERENT_GROUP_REVIEW":
        return "GROUP_OUTER_PENDING_HUMAN_REVIEW",raw_candidate|original
    if grouping["group_status"]=="CONFLICT_UNRESOLVED_REVIEW":
        return "CONFLICT_OUTER_PENDING_HUMAN_REVIEW",raw_candidate|original
    if grouping["group_status"]=="NO_SIBLING_CONFLICT":
        return "PROVISIONAL_OUTER_SINGLE",raw_candidate|original
    return "REJECTED_HALO_DISPLAY_REVIEW_ONLY",raw_candidate|original
