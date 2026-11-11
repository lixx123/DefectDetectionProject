"""Raw 12-bit DN reference-ring features for Case03-C.

Black-Hat responses are never substituted for RAW values here.  The reference
ring excludes every known H candidate, is bounded by the image, and is marked
invalid when it touches a detected strong row/column transition or the image
boundary.  Invalid values remain blank rather than being replaced by a large
score.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.detection.candidate_association import LabelComponent
from src.detection.reference_ring_geometry import select_reference_pixels


@dataclass(frozen=True)
class TransitionProfiles:
    row_profile_dn: np.ndarray
    column_profile_dn: np.ndarray
    transition_rows: np.ndarray
    transition_columns: np.ndarray
    row_threshold_dn: float
    column_threshold_dn: float


def _row_medians(raw: np.ndarray, chunk_rows: int) -> np.ndarray:
    values = np.empty(raw.shape[0], dtype=np.float64)
    for y0 in range(0, raw.shape[0], chunk_rows):
        y1 = min(raw.shape[0], y0 + chunk_rows)
        values[y0:y1] = np.median(np.asarray(raw[y0:y1]), axis=1)
    return values


def _column_medians(raw: np.ndarray, sample_rows: int) -> np.ndarray:
    stride = max(1, raw.shape[0] // max(1, sample_rows))
    rows = np.arange(0, raw.shape[0], stride, dtype=np.int64)[:sample_rows]
    return np.median(np.asarray(raw[rows]), axis=0).astype(np.float64, copy=False)


def detect_transition_profiles(
    raw: np.ndarray,
    *,
    row_chunk_rows: int = 256,
    column_sample_rows: int = 512,
    percentile: float = 99.5,
) -> TransitionProfiles:
    """Detect strong row/column profile transitions for reference-ring caution."""

    row_profile = _row_medians(raw, row_chunk_rows)
    column_profile = _column_medians(raw, column_sample_rows)
    row_delta = np.abs(np.diff(row_profile, prepend=row_profile[:1]))
    column_delta = np.abs(np.diff(column_profile, prepend=column_profile[:1]))
    row_threshold = float(np.percentile(row_delta[1:] if row_delta.size > 1 else row_delta, percentile))
    column_threshold = float(np.percentile(column_delta[1:] if column_delta.size > 1 else column_delta, percentile))
    transition_rows = np.flatnonzero(row_delta >= row_threshold).astype(np.int32)
    transition_columns = np.flatnonzero(column_delta >= column_threshold).astype(np.int32)
    return TransitionProfiles(
        row_profile_dn=row_profile,
        column_profile_dn=column_profile,
        transition_rows=transition_rows,
        transition_columns=transition_columns,
        row_threshold_dn=row_threshold,
        column_threshold_dn=column_threshold,
    )


def _interval_distance(start: int, end: int, positions: np.ndarray) -> int | None:
    if positions.size == 0:
        return None
    index = int(np.searchsorted(positions, start, side="left"))
    candidates = []
    if index < positions.size:
        candidates.append(int(positions[index] - end if positions[index] > end else 0))
    if index > 0:
        candidates.append(int(start - positions[index - 1] if positions[index - 1] < start else 0))
    return max(0, min(candidates)) if candidates else None


def transition_distance(
    component: LabelComponent,
    profiles: TransitionProfiles,
    margin_px: int,
) -> tuple[int | None, bool]:
    """Return nearest transition distance and conservative near-transition flag."""

    row_distance = _interval_distance(component.bbox_y, component.bbox_y + component.bbox_h - 1, profiles.transition_rows)
    column_distance = _interval_distance(component.bbox_x, component.bbox_x + component.bbox_w - 1, profiles.transition_columns)
    distances = [value for value in (row_distance, column_distance) if value is not None]
    distance = min(distances) if distances else None
    return distance, bool(distance is not None and distance <= margin_px)


def compute_raw_candidate_metrics(
    component: LabelComponent,
    xs: np.ndarray,
    ys: np.ndarray,
    raw: np.ndarray,
    all_candidate_mask: np.ndarray,
    profiles: TransitionProfiles,
    *,
    reference_radius_px: int,
    max_reference_pixels: int,
    min_reference_pixels: int,
    transition_margin_px: int,
    max_bbox_area_px: int = 1_000_000,
) -> dict:
    """Compute exact candidate RAW values and a guarded rectangular annulus."""

    candidate_values = np.asarray(raw[ys, xs], dtype=np.uint16)
    candidate_median = float(np.median(candidate_values)) if candidate_values.size else ""
    candidate_mean = float(np.mean(candidate_values)) if candidate_values.size else ""
    transition_distance_px, near_transition = transition_distance(component, profiles, transition_margin_px)
    selection = select_reference_pixels(
        component, all_candidate_mask,
        radius_px=reference_radius_px,
        max_reference_pixels=max_reference_pixels,
    )
    x0, y0, x1, y1 = selection.bounds
    ring_values = np.asarray(raw[selection.sample_y, selection.sample_x], dtype=np.uint16)
    ring_count = selection.eligible_count
    ring_sample_count = selection.sampled_count
    invalid_reasons: list[str] = []
    if component.touches_border:
        invalid_reasons.append("candidate_touches_image_border")
    if component.bbox_w * component.bbox_h > max_bbox_area_px:
        invalid_reasons.append("bbox_too_large")
    if near_transition:
        invalid_reasons.append("near_band_transition")
    if ring_count < min_reference_pixels:
        invalid_reasons.append("reference_ring_too_small")
    if ring_count == 0:
        invalid_reasons.append("reference_ring_contaminated_or_empty")
    reference_valid = not invalid_reasons
    background_median = ""
    background_mad = ""
    raw_delta = ""
    contrast_proxy = ""
    contrast_invalid_reason = ""
    if reference_valid:
        background_median = float(np.median(ring_values))
        background_mad = float(np.median(np.abs(ring_values.astype(np.float64) - background_median)))
        raw_delta = float(background_median - candidate_median)
        if background_mad > 0:
            contrast_proxy = float(raw_delta / (1.4826 * background_mad))
        else:
            contrast_invalid_reason = "background_mad_zero"
    return {
        "raw_candidate_median_dn": candidate_median,
        "raw_candidate_mean_dn": candidate_mean,
        "raw_background_median_dn": background_median,
        "raw_delta_dn": raw_delta,
        "background_noise_mad_dn": background_mad,
        "contrast_to_noise_proxy": contrast_proxy,
        "raw_candidate_pixel_count": int(candidate_values.size),
        "raw_reference_pixel_count": ring_count,
        "raw_reference_sample_count": ring_sample_count,
        "raw_reference_valid": reference_valid,
        "raw_reference_invalid_reason": ";".join(invalid_reasons),
        "contrast_proxy_invalid_reason": contrast_invalid_reason,
        "near_band_transition": near_transition,
        "transition_distance_px": transition_distance_px if transition_distance_px is not None else "",
        "raw_reference_rule": "rectangular annulus outside exact candidate bbox; exclude all H candidate pixels; clip to image; deterministic linspace cap",
        "reference_outer_bbox_x": x0,
        "reference_outer_bbox_y": y0,
        "reference_outer_bbox_w": x1 - x0,
        "reference_outer_bbox_h": y1 - y0,
    }

