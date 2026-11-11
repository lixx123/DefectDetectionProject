"""Case03-F：小面积候选 RAW 邻域统计试验，不修改任何源H或融合轮廓。

单位：12 bit 原始 DN、像素/像素²。分类为可逆显示建议，不是疵病真值。
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class NoiseTrialConfig:
    small_area_max_px: int = 5
    min_relative_contrast: float = 0.08
    min_significance_z: float = 3.0
    ring_outer_radius_px: int = 12
    ring_inner_guard_px: int = 2
    ring_min_count: int = 20
    sigma_floor_dn: float = 3.0
    protect_large_nearby_radius_px: int = 3
    protect_large_area_px: int = 30


def local_raw_statistics(raw: np.ndarray, all_h: np.ndarray, candidate_mask: np.ndarray,
                         bbox_xywh: tuple[int, int, int, int],
                         config: NoiseTrialConfig) -> dict:
    """计算候选与矩形邻域环带的原始 DN 统计；背景排除所有H像素和内保护带。
    raw 为窗口内原始RAW DN，返回候选/参考背景中位数、MAD、C和Z。
    窗口边界导致采样不完整时标记无效，不从被裁断的邻域推断噪声。
    """
    if raw.shape != all_h.shape or raw.shape != candidate_mask.shape:
        raise ValueError("raw, H and candidate mask must have identical shape")
    ysize, xsize = raw.shape
    x, y, w, h = (int(v) for v in bbox_xywh)
    if w < 1 or h < 1 or x < 0 or y < 0 or x+w > xsize or y+h > ysize:
        raise ValueError("invalid local bbox")
    candidate_vals = raw[candidate_mask].astype(float)
    if candidate_vals.size == 0:
        raise ValueError("candidate is empty")
    touches_roi_edge = (x == 0 or y == 0 or x+w == xsize or y+h == ysize)
    outer = config.ring_outer_radius_px
    x0, x1 = max(0, x-outer), min(xsize, x+w+outer)
    y0, y1 = max(0, y-outer), min(ysize, y+h+outer)
    sample = (~all_h[y0:y1, x0:x1]).copy()
    guard = config.ring_inner_guard_px
    ax, bx = max(x0, x-guard)-x0, min(x1, x+w+guard)-x0
    ay, by = max(y0, y-guard)-y0, min(y1, y+h+guard)-y0
    sample[ay:by, ax:bx] = False
    values = raw[y0:y1, x0:x1][sample].astype(float)
    candidate_dn = float(np.median(candidate_vals))
    result = {
        "candidate_median_dn": candidate_dn, "background_median_dn": np.nan,
        "background_mad_dn": np.nan, "raw_delta_dn": np.nan,
        "relative_contrast": np.nan, "significance_z": np.nan,
        "reference_count": int(values.size), "reference_valid": False,
        "reference_invalid_reason": "",
        "touches_roi_edge": bool(touches_roi_edge),
    }
    if touches_roi_edge:
        result["reference_invalid_reason"] = "cropped_roi_edge"
    elif values.size < config.ring_min_count:
        result["reference_invalid_reason"] = "too_few_background_pixels"
    elif not np.isfinite(candidate_dn) or not np.isfinite(values).all():
        result["reference_invalid_reason"] = "invalid_raw_values"
    else:
        background = float(np.median(values))
        mad = float(np.median(np.abs(values - background)))
        delta = float(background - candidate_dn)
        sigma = max(1.4826 * mad, float(config.sigma_floor_dn))
        result.update(background_median_dn=background, background_mad_dn=mad,
                      raw_delta_dn=delta,
                      relative_contrast=delta / max(abs(background), 1.0),
                      significance_z=delta / sigma, reference_valid=True)
    return result


def classify_candidate(area_px: int, bbox_w: int, bbox_h: int,
                       metrics: dict, protected_structure: bool,
                       config: NoiseTrialConfig) -> tuple[str, str]:
    """分类仅用于试验显示，永不删除候选记录和源掩膜。
    为避免误伤十字划痕：超过小面积门限或邻接大H结构者一律保留。
    """
    if area_px < 1 or bbox_w < 1 or bbox_h < 1:
        raise ValueError("invalid candidate dimensions")
    if area_px > config.small_area_max_px:
        return "keep", "area_above_trial_small_limit"
    if protected_structure:
        return "keep_review", "protected_near_larger_H_component"
    if not metrics.get("reference_valid", False):
        return "keep_review", "raw_background_reference_unreliable"
    c = float(metrics["relative_contrast"])
    z = float(metrics["significance_z"])
    if not np.isfinite(c) or not np.isfinite(z):
        return "keep_review", "raw_contrast_nonfinite"
    if c < config.min_relative_contrast or z < config.min_significance_z:
        return "suggest_hide", "tiny_candidate_low_relative_contrast_or_significance"
    return "keep", "tiny_candidate_strong_relative_contrast_and_significance"
