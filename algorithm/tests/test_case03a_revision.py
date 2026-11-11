"""Case03-A-R1修订的合成测试。"""

import numpy as np

from src.detection.local_robust_threshold import local_threshold_mask
from src.detection.thresholding import fixed_threshold_mask
from src.visualization.segmentation_diagnostic import (
    any_hit_thumbnail,
    density_overlay,
    density_thumbnail,
    mask_overlap_statistics,
)


def test_revised_constant_regions_are_negative_and_strong_point_survives() -> None:
    for value in (0, 100, 130, 300):
        response = np.full((33, 35), value, dtype=np.uint16)
        mask, _, _, _ = local_threshold_mask(
            response,
            k=5,
            floor_dn=120,
            grid_size_px=16,
            sample_stride_px=2,
            min_excess_dn=10,
            strict=True,
            interpolate_components=True,
        )
        assert not np.any(mask)

    response = np.full((33, 35), 130, dtype=np.uint16)
    response[16, 17] = 400
    mask, _, _, _ = local_threshold_mask(
        response,
        k=5,
        floor_dn=120,
        grid_size_px=16,
        sample_stride_px=2,
        min_excess_dn=10,
        strict=True,
        interpolate_components=True,
    )
    assert mask[16, 17]
    assert np.count_nonzero(mask) < response.size * 0.01


def test_revised_point_lines_slope_and_grid_boundary_keep_shape() -> None:
    response = np.full((65, 73), 100, dtype=np.uint16)
    response[31, 33] = 400
    response[15:50, 40] = 280
    response[20:45, 20:45] += np.arange(25, dtype=np.uint16)[:, None]
    mask, _, _, rows = local_threshold_mask(
        response,
        k=3,
        floor_dn=120,
        grid_size_px=16,
        sample_stride_px=2,
        min_excess_dn=5,
        strict=True,
        interpolate_components=True,
    )
    assert mask.shape == response.shape
    assert len(rows) == 25
    assert mask[31, 33]
    assert np.count_nonzero(mask[:, 40]) > 0


def test_fixed_thresholds_are_scale_specific_and_inclusive() -> None:
    response = np.array([[149, 150, 200], [219, 220, 221]], dtype=np.uint16)
    low = fixed_threshold_mask(response, 150)
    high = fixed_threshold_mask(response, 220)
    assert np.count_nonzero(low) == 5
    assert np.count_nonzero(high) == 2
    assert low[0, 1] and high[1, 1]


def test_density_thumbnail_mean_and_any_hit_are_distinguishable() -> None:
    mask = np.zeros((64, 64), dtype=bool)
    mask[3, 5] = True
    density = density_thumbnail(mask, 8)
    any_hit = any_hit_thumbnail(mask, 8)
    full_fraction = float(mask.mean())
    density_fraction = float(density.mean() / 255.0)
    assert abs(density_fraction - full_fraction) < 0.005
    assert float(any_hit.mean() / 255.0) > full_fraction
    assert int(density.max()) < 255


def test_overlap_categories_are_mutually_exclusive_and_conserved() -> None:
    fixed = np.zeros((17, 19), dtype=bool)
    local = np.zeros_like(fixed)
    fixed[1:5, 1:4] = True
    local[3:7, 2:6] = True
    stats = mask_overlap_statistics(fixed, local)
    assert stats["fixed_only_count"] + stats["local_only_count"] + stats["overlap_count"] == stats["union_count"]
    overlay, overlay_stats = density_overlay(np.zeros_like(fixed, dtype=np.uint8), fixed, local, 8)
    assert overlay.shape == (7, 8, 3)
    assert overlay_stats["union_count"] == stats["union_count"]
