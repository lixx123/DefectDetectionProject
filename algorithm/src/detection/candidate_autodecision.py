"""Case03-D-R2 engineering rule baseline for triaging existing H170/230 candidates.

The rules are intentionally label-independent, interpretable and conservative.
Not a validated classifier, probability, ground truth, or a license to delete
potential defects. Any "noise_like" object remains in the complete ledger.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


REVIEW_STATES=("detected_provisional","uncertain_review","noise_like_retained")
TYPE_STATES=("spot_like","line_like","unclassified")


def classify_candidates(frame:pd.DataFrame, *,
    auto_min_area:int=20,auto_min_peak:int=270,
    auto_min_raw_delta:float=20.,
    auto_min_fill:float=.23,
    review_min_area:int=12,review_min_peak:int=275,
    tiny_high_peak:int=275,
)->pd.DataFrame:
    """Assign provisional triage states from predeclared physical morphology rules.

    All rows and all candidate IDs preserved. No human annotation is an input.
    RAW reference is used as veto only for reliable reference data: invalid
    references do not create a fake delta; they move apparent defects to review.
    """
    required={
        "candidate_id","area_px","peak_response_dn","bbox_w","bbox_h",
        "bbox_aspect_ratio","bbox_fill_ratio","linearity_proxy",
        "near_band_transition","raw_reference_valid","raw_delta_dn",
        "touches_border","seed_area_px","core_component_count"
    }
    if required-set(frame):
        raise ValueError(f"feature schema missing {sorted(required-set(frame))}")
    if frame["candidate_id"].isna().any() or frame["candidate_id"].duplicated().any():
        raise ValueError("candidate IDs must be unique")
    if min(auto_min_area,auto_min_peak,review_min_area,review_min_peak,tiny_high_peak)<=0:
        raise ValueError("threshold parameters must be positive")
    n=len(frame)
    area=pd.to_numeric(frame["area_px"],errors="raise").to_numpy(dtype=float)
    peak=pd.to_numeric(frame["peak_response_dn"],errors="raise").to_numpy(dtype=float)
    width=pd.to_numeric(frame["bbox_w"],errors="raise").to_numpy(dtype=float)
    height=pd.to_numeric(frame["bbox_h"],errors="raise").to_numpy(dtype=float)
    fill=pd.to_numeric(frame["bbox_fill_ratio"],errors="raise").to_numpy(dtype=float)
    longness=pd.to_numeric(frame["linearity_proxy"],errors="coerce").fillna(0).to_numpy(dtype=float)
    aspect=np.divide(width,np.maximum(height,1))
    raw_delta=pd.to_numeric(frame["raw_delta_dn"],errors="coerce").to_numpy(dtype=float)
    def as_bool(column:str)->np.ndarray:
        s=frame[column].astype(str).str.strip().str.lower()
        if not s.isin(("true","false")).all():
            raise ValueError(f"unrecognized boolean values in {column}")
        return s.eq("true").to_numpy(dtype=bool)
    transition=as_bool("near_band_transition")
    raw_valid=as_bool("raw_reference_valid")
    border=as_bool("touches_border")
    if np.any(area<1) or np.any(width<1) or np.any(height<1) or \
       np.any((fill<=0)|(fill>1)) or not np.isfinite(peak).all():
        raise ValueError("nonphysical candidate geometry/response")
    if np.any(raw_valid & (~np.isfinite(raw_delta))):
        raise ValueError("valid RAW reference must have a finite delta DN")
    if np.any(np.isfinite(raw_delta)&~raw_valid):
        # In source data invalid RAW background must not be silently trusted.
        raw_delta=np.where(raw_valid,raw_delta,np.nan)
    # Source failures that are strongly suggestive of long bright/dark band
    # edge filaments: separate from genuine horizontal long fine scratches.
    stripe_edge=(
        transition &
        (height>=80) & (width<=20) & (aspect<.20) &
        (longness>=.96) & (area>=80)
    )
    compact_spot=(
        (aspect>=.30)&(aspect<=3.5)&(longness<=.90)&(fill>=auto_min_fill)
    )
    extended_line=(
        (area>=25)&(np.maximum(aspect,1/np.maximum(aspect,1e-9))>=2)&
        (longness>=.75)&(np.minimum(width,height)>=2)
    )
    basic_strength=(area>=auto_min_area)&(peak>=auto_min_peak)
    morphology=compact_spot|extended_line
    raw_pass=raw_valid&(raw_delta>=auto_min_raw_delta)
    # Confidence is deliberately NOT assigned as a calibrated probability.
    direct=(
        basic_strength & morphology & raw_pass &
        ~stripe_edge & ~transition & ~border
    )
    # Give weak spots and fine strokes a route to human audit instead of
    # silently suppressing them with a hard size/peak cutoff.
    line_review=(longness>=.90)&(np.maximum(width,height)>=8)&(peak>=240)
    possible=(
        (area>=review_min_area) |
        ((area<=3)&(peak>=tiny_high_peak)) |
        ((area>3)&(peak>=review_min_peak)) |
        ((area>=4)&(peak>=260)) |
        line_review |
        ((area>=8)&transition)
    )
    state=np.where(
        direct,"detected_provisional",
        np.where(possible & ~stripe_edge,"uncertain_review","noise_like_retained")
    )
    kind=np.where(extended_line,"line_like",np.where(compact_spot,"spot_like","unclassified"))
    # All row output stays in input order; each H component has exactly 1 state.
    reason=np.select(
        [
            direct & extended_line,
            direct & compact_spot,
            stripe_edge,
            possible & ~raw_valid,
            possible & raw_valid & (raw_delta<auto_min_raw_delta),
            possible & transition,
            possible & border,
            possible,
        ],
        [
            "strong_shape_and_valid_raw_dark_line",
            "strong_shape_and_valid_raw_dark_spot",
            "tall_filament_near_band_transition",
            "potential_anomaly_raw_reference_unavailable",
            "potential_anomaly_raw_delta_below_auto_rule",
            "potential_anomaly_near_band_transition",
            "potential_anomaly_touching_border",
            "potential_anomaly_other_uncertainty",
        ],
        default="weak_or_small_signal_keep_in_archive"
    )
    if not len(state)==n or not np.isin(state,REVIEW_STATES).all():
        raise AssertionError("some candidates lost classification")
    out=pd.DataFrame({
        "candidate_id":frame["candidate_id"].to_numpy(copy=True),
        "triage_status":state,
        "morphology_hint":kind,
        "decision_reason":reason,
        "band_edge_artifact_signature":stripe_edge,
        "raw_contrast_check_valid":raw_valid,
        "raw_contrast_passes_auto_rule":raw_pass,
        "review_flag":state=="uncertain_review",
        "candidate_retained":np.ones(n,dtype=bool),
    })
    if not out["candidate_id"].equals(frame["candidate_id"].reset_index(drop=True)):
        raise AssertionError("output H order changed")
    return out


def inspect_reviewed_against_triage(results:pd.DataFrame,labels:dict[str,str])->list[dict]:
    """Selected candidate diagnostics only; *never* fit or tune rules here."""
    idx=results.set_index("candidate_id")
    if not idx.index.is_unique:
        raise ValueError("candidate IDs not unique")
    if set(labels)-set(idx.index):
        raise ValueError("reviewed labels not in candidate dataset")
    rows=[]
    for label in ("confirmed_dark_spot","background_artifact"):
        keys=[key for key,val in labels.items() if val==label]
        for status in REVIEW_STATES:
            rows.append({
                "manual_label":label,
                "triage_status":status,
                "count":int(idx.loc[keys,"triage_status"].eq(status).sum()) if keys else 0,
                "total_manual_labeled":len(keys),
                "interpretation":"same-image manually selected candidates; not image recall or field accuracy"
            })
    return rows
