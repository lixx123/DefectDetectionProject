"""Descriptive geometry and response features for Case03-C candidates."""

from __future__ import annotations

import numpy as np

from src.detection.candidate_association import LabelComponent


def compute_shape_features(
    component: LabelComponent,
    xs: np.ndarray,
    ys: np.ndarray,
    image_shape: tuple[int, int] = (9200, 11276),
) -> dict:
    """Return geometry features from exact candidate pixels, never contour area.

    ``xs`` and ``ys`` are full-image integer coordinates for one candidate.
    PCA-derived fields are left blank with an explicit reason when a one-pixel
    or otherwise degenerate candidate cannot support a stable estimate.
    """

    area = int(component.area_px)
    bbox_area = int(component.bbox_w * component.bbox_h)
    height, width = int(image_shape[0]), int(image_shape[1])
    result = {
        "bbox_aspect_ratio": float(component.bbox_w / max(component.bbox_h, 1)),
        "bbox_fill_ratio": float(area / max(bbox_area, 1)),
        "raw_edge_distance_px": int(min(component.bbox_x, component.bbox_y, width - 1 - (component.bbox_x + component.bbox_w - 1), height - 1 - (component.bbox_y + component.bbox_h - 1))),
        "shape_feature_valid": False,
        "shape_feature_invalid_reason": "",
        "principal_orientation_deg": "",
        "principal_major_variance_px2": "",
        "principal_minor_variance_px2": "",
        "pca_eccentricity": "",
        "linearity_proxy": "",
    }
    if area < 2:
        result["shape_feature_invalid_reason"] = "one_pixel_candidate"
        return result
    centered_x = xs.astype(np.float64) - float(xs.mean())
    centered_y = ys.astype(np.float64) - float(ys.mean())
    covariance = np.asarray(
        [
            [float(np.mean(centered_x * centered_x)), float(np.mean(centered_x * centered_y))],
            [float(np.mean(centered_x * centered_y)), float(np.mean(centered_y * centered_y))],
        ],
        dtype=np.float64,
    )
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, 0.0)
    minor, major = float(eigenvalues[0]), float(eigenvalues[1])
    direction = eigenvectors[:, 1]
    orientation = float(np.degrees(np.arctan2(direction[1], direction[0])))
    denominator = major + minor
    result.update(
        {
            "shape_feature_valid": True,
            "principal_orientation_deg": orientation,
            "principal_major_variance_px2": major,
            "principal_minor_variance_px2": minor,
            "pca_eccentricity": float(np.sqrt(max(0.0, 1.0 - minor / max(major, 1e-12)))),
            "linearity_proxy": float((major - minor) / max(denominator, 1e-12)),
        }
    )
    return result


def component_base_features(component: LabelComponent) -> dict:
    """Convert stable geometry into CSV-ready scalar fields."""

    return {
        "area_px": component.area_px,
        "bbox_x": component.bbox_x,
        "bbox_y": component.bbox_y,
        "bbox_w": component.bbox_w,
        "bbox_h": component.bbox_h,
        "centroid_x": component.centroid_x,
        "centroid_y": component.centroid_y,
        "peak_response_dn": component.peak_response_dn,
        "touches_border": component.touches_border,
    }
