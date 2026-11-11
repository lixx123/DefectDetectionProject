"""Case03-G: reversible noise-gate for EXISTING H-seeded Gaussian/Closing contours.

Input objects are precomputed Case03-E2-H5 H-origin masks. This module never
creates independent Gaussian/morphological detections or changes the original
H, fused contours, or per-object archival records.
"""
from __future__ import annotations

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass(frozen=True)
class JointGateConfig:
    protect_support_area_min_px: int = 6
    protect_support_radius_px: int = 8
    protect_any_existing_refinement: bool = True


def decide_gate(
    h_labels: np.ndarray,
    h_stats: np.ndarray,
    trial_states: list[str],
    refined_sources: list[tuple[str, ...]],
    config: JointGateConfig,
) -> tuple[list[str], list[str]]:
    """Return a one-to-one classification for each original H component.

    Allowed input trial states: keep / keep_review / suggest_hide.
    A small component with refinement evidence or neighboring stronger H
    structures is protected regardless of its weak RAW local contrast.
    Source H labels are never changed. No manual annotations are accepted.
    """
    if h_labels.ndim != 2 or h_stats.shape[0] != len(trial_states) + 1:
        raise ValueError("label catalogue mismatch")
    if len(refined_sources) != len(trial_states):
        raise ValueError("refined-object catalogue mismatch")
    if config.protect_support_radius_px < 0 or config.protect_support_area_min_px < 2:
        raise ValueError("invalid guard radius or area")
    acceptable = {"keep", "keep_review", "suggest_hide"}
    if set(trial_states) - acceptable:
        raise ValueError("unknown trial state")
    large_ids = np.flatnonzero(
        h_stats[:, cv2.CC_STAT_AREA] >= config.protect_support_area_min_px)
    large_ids = large_ids[large_ids > 0]
    support = np.isin(h_labels, large_ids).astype(np.uint8)
    r = config.protect_support_radius_px
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*r+1, 2*r+1))
    near_support = cv2.dilate(support, kernel).astype(bool)
    result, reasons = [], []
    for i, (old, sources) in enumerate(zip(trial_states, refined_sources), 1):
        if old == "keep":
            state, reason = "keep", "raw_screen_kept"
        elif old == "keep_review":
            state, reason = "protected_review", "raw_screen_already_protected"
        elif config.protect_any_existing_refinement and any(
            s in {"gaussian22", "closing61"} for s in sources
        ):
            state, reason = "protected_review", "existing_H_anchored_refinement"
        elif np.any(near_support[h_labels == i]):
            state, reason = "protected_review", "near_larger_H_structure"
        else:
            state, reason = "hide_suggestion", "isolated_small_weak_raw_candidate"
        result.append(state)
        reasons.append(reason)
    return result, reasons


def build_joint_maps(
    h_labels: np.ndarray,
    refined_labels: np.ndarray,
    gate: list[str],
) -> dict[str, np.ndarray]:
    """Construct reversible masks from exact origin IDs; no new object creation."""
    if h_labels.shape != refined_labels.shape or len(gate)+1 != int(h_labels.max())+1:
        raise ValueError("label shape/count mismatch")
    if np.any((h_labels > 0) & (refined_labels != h_labels)):
        raise AssertionError("H-to-refined ID ownership changed")
    all_h = h_labels > 0
    keep_ids = np.array([i for i,x in enumerate(gate,1) if x!="hide_suggestion"])
    hide_ids = np.array([i for i,x in enumerate(gate,1) if x=="hide_suggestion"])
    raw_kept = np.isin(h_labels, keep_ids)
    raw_hidden = np.isin(h_labels, hide_ids)
    fused_kept = np.isin(refined_labels, keep_ids)
    full_fused = refined_labels > 0
    if not np.array_equal(raw_kept | raw_hidden, all_h):
        raise AssertionError("H pixels lost from reversible partitions")
    if np.any(fused_kept & ~full_fused):
        raise AssertionError("refinement pixel outside source fusion")
    if not np.array_equal((fused_kept & all_h), raw_kept):
        raise AssertionError("H pixel lost during gated refinement")
    return {
        "h_original": all_h, "h_kept_display": raw_kept,
        "h_hidden_suggestion": raw_hidden,
        "fused_original": full_fused,
        "fused_joint_display": fused_kept,
    }
