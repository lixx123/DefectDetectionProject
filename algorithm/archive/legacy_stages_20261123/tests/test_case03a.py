"""Case03-A固定阈值、局部Median/MAD与掩膜存取合成测试。"""

from pathlib import Path

import numpy as np
import pytest

from src.detection.local_robust_threshold import (
    compute_local_grid_statistics,
    local_threshold_mask,
)
from src.detection.thresholding import (
    fixed_threshold_mask,
    load_packed_mask,
    pack_mask,
    restore_packed_mask,
    save_packed_mask,
)


def test_fixed_threshold_inclusive_and_uint16_validation() -> None:
    response = np.array([[149, 150], [151, 0]], dtype=np.uint16)
    mask = fixed_threshold_mask(response, 150)
    assert mask.tolist() == [[False, True], [True, False]]
    with pytest.raises(TypeError):
        fixed_threshold_mask(response.astype(np.uint8), 150)
    with pytest.raises(TypeError):
        fixed_threshold_mask(response[:, :1], 150.5)
    with pytest.raises(ValueError):
        fixed_threshold_mask(response, -1)


def test_zero_and_constant_local_mad_do_not_select_zero_response() -> None:
    zero = np.zeros((17, 19), dtype=np.uint16)
    mask, medians, mads, rows = local_threshold_mask(zero, k=5, floor_dn=120, grid_size_px=8, sample_stride_px=2)
    assert not np.any(mask)
    assert np.all(medians == 0)
    assert np.all(mads == 0)
    assert len(rows) == 9

    constant = np.full((17, 19), 130, dtype=np.uint16)
    constant_mask, _, constant_mads, _ = local_threshold_mask(constant, k=5, floor_dn=120, grid_size_px=8, sample_stride_px=2)
    assert np.all(constant_mads == 0)
    assert np.all(constant_mask)


def test_local_point_line_gradient_and_cross_grid_have_full_shape() -> None:
    height, width = 65, 73
    response = np.full((height, width), 100, dtype=np.uint16)
    response[31, 33] = 400
    response[15:50, 40] = 280
    response += np.arange(width, dtype=np.uint16)[None, :] // 8
    mask, _, _, rows = local_threshold_mask(response, k=3, floor_dn=120, grid_size_px=16, sample_stride_px=2)
    assert mask.shape == response.shape
    assert len(rows) == 5 * 5
    assert mask[31, 33]
    assert np.count_nonzero(mask[:, 40]) > 0


def test_grid_statistics_cover_odd_boundary_without_empty_cells() -> None:
    response = np.arange(35, dtype=np.uint16).reshape(5, 7)
    medians, mads, rows = compute_local_grid_statistics(response, grid_size_px=4, sample_stride_px=2)
    assert medians.shape == (2, 2)
    assert mads.shape == medians.shape
    assert len(rows) == 4
    assert {(row["y_start_px"], row["y_end_px"]) for row in rows} == {(0, 4), (4, 5)}
    assert {(row["x_start_px"], row["x_end_px"]) for row in rows} == {(0, 4), (4, 7)}


def test_packbits_roundtrip_and_threshold_union() -> None:
    response = np.array([[0, 150, 200], [250, 300, 301]], dtype=np.uint16)
    masks = [fixed_threshold_mask(response, threshold) for threshold in (150, 200, 300)]
    packed = pack_mask(masks[0])
    restored = restore_packed_mask(packed, response.shape, "little")
    assert np.array_equal(restored, masks[0])
    with pytest.raises(ValueError):
        restore_packed_mask(packed, (2, 5), "little")
    union = np.logical_or.reduce(masks)
    assert np.array_equal(union, response >= 150)


def test_saved_packed_mask_contains_shape_and_restores(tmp_path: Path) -> None:
    mask = np.zeros((9, 11), dtype=bool)
    mask[2, 3] = True
    path = tmp_path / "mask.npz"
    metadata = save_packed_mask(path, mask)
    assert metadata["shape"] == [9, 11]
    restored = load_packed_mask(path)
    assert np.array_equal(restored, mask)
