from __future__ import annotations

import numpy as np
from scipy import ndimage

from src.detection.tiled_components import extract_tiled_components


def _reference_hysteresis(support: np.ndarray, seed: np.ndarray) -> tuple[np.ndarray, int]:
    labels, count = ndimage.label(support, structure=np.ones((3, 3), dtype=np.uint8))
    active = np.unique(labels[seed])
    active = active[active > 0]
    return np.isin(labels, active), int(active.size)


def test_tiled_8_connectivity_matches_scipy_across_diagonal_tile_corner(tmp_path):
    mask = np.zeros((19, 23), dtype=bool)
    mask[7, 7] = True
    mask[8, 8] = True
    mask[9:12, 9:13] = True
    response = np.where(mask, 250, 0).astype(np.uint16)
    result = extract_tiled_components(mask, response, tile_shape=(8, 8), temp_dir=tmp_path)
    reference, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    assert np.array_equal(result.final_mask, reference > 0)
    assert result.active_component_count == int(count)
    assert sum(row["area_px"] for row in result.components) == int(mask.sum())


def test_hysteresis_keeps_weak_bridge_and_reports_low_only(tmp_path):
    support = np.zeros((40, 45), dtype=bool)
    response = np.zeros((40, 45), dtype=np.uint16)
    support[20:22, 3:40] = True
    response[20:22, 3:40] = 170
    response[20:22, 3:6] = 260
    response[20:22, 35:40] = 260
    seed = response >= 230
    result = extract_tiled_components(support, response, seed, tile_shape=(7, 9), temp_dir=tmp_path)
    expected, count = _reference_hysteresis(support, seed)
    assert np.array_equal(result.final_mask, expected)
    assert result.active_component_count == count == 1
    assert int(result.low_only_mask.sum()) == 0
    assert np.all(~seed | result.final_mask)
    assert np.all(~result.final_mask | support)


def test_low_only_support_is_not_promoted_to_candidate(tmp_path):
    support = np.zeros((24, 24), dtype=bool)
    response = np.zeros((24, 24), dtype=np.uint16)
    support[2:5, 2:5] = True
    response[2:5, 2:5] = 175
    support[15:18, 15:18] = True
    response[15:18, 15:18] = 260
    result = extract_tiled_components(support, response, response >= 230, tile_shape=(5, 6), temp_dir=tmp_path)
    assert int(result.final_mask.sum()) == 9
    assert int(result.low_only_mask.sum()) == 9
    assert result.active_component_count == 1
    assert result.support_component_count == 2


def test_four_connectivity_small_comparison(tmp_path):
    mask = np.zeros((13, 13), dtype=bool)
    mask[5, 5] = True
    mask[6, 6] = True
    result = extract_tiled_components(mask, np.where(mask, 250, 0).astype(np.uint16), connectivity=4, tile_shape=(4, 4), temp_dir=tmp_path)
    reference, count = ndimage.label(mask, structure=np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8))
    assert np.array_equal(result.final_mask, reference > 0)
    assert result.active_component_count == int(count) == 2

