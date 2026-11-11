"""Case03-H pilot: suppress weak, medium-size background texture proposals.

Consumes existing Case03-F RAW metrics, Case03-G conservative gate and Case03-E2
bounded Gaussian/Closing contours. Never takes manual positions as detector input.
All "hide" states apply only to visualization and keep a full audit.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import cv2
import numpy as np

@dataclass(frozen=True)
class TextureTrialConfig:
    medium_min_area_px: int = 6
    medium_max_area_px: int = 30
    min_relative_contrast: float = 0.06
    min_significance_z: float = 2.5
    protect_peak_dn: float = 320.0
    # DoG=GaussianBlur(RAW,sigma=8)-GaussianBlur(RAW,sigma=2), DN.
    # Sufficient coherent dark-core support protects weak aggregated H spots.
    protect_dog_median_dn: float = 16.0
    dog_small_sigma_px: float = 2.0
    dog_large_sigma_px: float = 8.0
    protect_big_area_px: int = 40
    protect_big_radius_px: int = 5
    protect_stroke_min_length_px: int = 12
    protect_stroke_aspect: float = 3.5


def extend_gate(
    labels:np.ndarray,stats:np.ndarray,
    old_states:list[str],old_reasons:list[str],
    feature_rows:list[dict],config:TextureTrialConfig,
)->tuple[list[str],list[str]]:
    """Only re-evaluate 6..30px H objects that old Case03-G kept.

    The two independent RAW signal checks must BOTH be weak, and the BlackHat
    peak must be below a conservative high-response safeguard. Nearby major
    structures and elongated fine scratches are protected. Invalid RAW
    references retain review status. All categories remain reversible.
    """
    if labels.ndim!=2 or len(feature_rows)!=stats.shape[0]-1 or len(old_states)!=len(feature_rows):
        raise ValueError("case03h H and audit dimensions mismatch")
    if len(old_reasons)!=len(old_states):
        raise ValueError("case03h reason cardinality mismatch")
    if config.medium_min_area_px < 2 or config.medium_max_area_px < config.medium_min_area_px:
        raise ValueError("medium area bounds invalid")
    if config.protect_big_area_px<=config.medium_max_area_px:
        raise ValueError("support anchor must be larger than medium candidate")
    if not (0 < config.dog_small_sigma_px < config.dog_large_sigma_px):
        raise ValueError("DoG scales must satisfy 0 < small < large")
    if config.protect_big_radius_px<0 or config.protect_stroke_aspect<=1:
        raise ValueError("invalid structure protection settings")
    anchor_ids=np.flatnonzero(stats[:,cv2.CC_STAT_AREA]>=config.protect_big_area_px)
    anchor_ids=anchor_ids[anchor_ids>0]
    anchor=np.isin(labels,anchor_ids).astype(np.uint8)
    radius=config.protect_big_radius_px
    nearmask=cv2.dilate(anchor,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                 (2*radius+1,2*radius+1))).astype(bool)
    out=[];reasons=[]
    for j,(old,reason,record) in enumerate(zip(old_states,old_reasons,feature_rows),1):
        x,y,w,h,area=(int(v) for v in stats[j,:5])
        if area!=int(record["area_px"]):
            raise AssertionError("component area mismatch")
        if not config.medium_min_area_px<=area<=config.medium_max_area_px:
            out.append(old);reasons.append(reason);continue
        if old!="keep":
            out.append(old);reasons.append(reason);continue
        if not record["reference_valid"]:
            out.append("protected_review");reasons.append("medium_RAW_reference_unreliable");continue
        c=float(record["relative_contrast"])
        z=float(record["significance_z"])
        peak=float(record["fused_blackhat_peak_dn"])
        dog=float(record.get("dog_median_dn",float("nan")))
        if not all(math.isfinite(v) for v in (c,z,peak)): 
            out.append("protected_review");reasons.append("medium_feature_nonfinite");continue
        if peak>=config.protect_peak_dn:
            out.append("keep");reasons.append("medium_high_BlackHat_peak_protected");continue
        if math.isfinite(dog) and dog>=config.protect_dog_median_dn:
            out.append("protected_review");reasons.append("medium_coherent_dark_DoG_protected");continue
        if max(w,h)>=config.protect_stroke_min_length_px and max(w,h)/max(1,min(w,h))>=config.protect_stroke_aspect:
            out.append("protected_review");reasons.append("medium_line_shape_protected");continue
        if np.any(nearmask[labels==j]):
            out.append("protected_review");reasons.append("medium_near_major_H_structure");continue
        if c<config.min_relative_contrast and z<config.min_significance_z:
            out.append("hide_suggestion")
            reasons.append("medium_weak_RAW_contrast_and_significance")
        else:
            out.append("keep");reasons.append("medium_not_consistently_weak")
    assert len(out)==len(old_states)
    return out,reasons
