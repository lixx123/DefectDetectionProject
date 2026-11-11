"""Case02验证诊断函数的轻量测试。"""

import numpy as np

from scripts.validate_case02 import extract_ranked_candidates, match_candidate_positions


def test_validation_candidate_coordinates_and_edge_rule() -> None:
    response = np.zeros((64, 64), dtype=np.uint16)
    response[3, 3] = 999  # patch_size=8时位于边缘排除区
    response[20, 20] = 100
    response[20, 40] = 90
    candidates = extract_ranked_candidates(response, top_count=2, patch_size_px=8, min_distance_px=8)
    assert [(row["x"], row["y"]) for row in candidates] == [(20, 20), (40, 20)]
    assert candidates[0]["edge_distance_px"] == 20


def test_validation_cross_scale_matching_uses_pixel_radius() -> None:
    scale_rows = [{"rank": 1, "x": 100, "y": 200, "peak_response_dn": 30, "edge_distance_px": 100}]
    fusion_rows = [{"rank": 4, "x": 112, "y": 204, "peak_response_dn": 40, "edge_distance_px": 100}]
    matched = match_candidate_positions(scale_rows, fusion_rows, radius_px=16)
    assert matched[0]["matched_fusion_rank"] == 1
    assert matched[0]["match_distance_px"] == 12.649


def test_validation_cross_scale_matching_rejects_outside_radius() -> None:
    scale_rows = [{"rank": 1, "x": 100, "y": 200, "peak_response_dn": 30, "edge_distance_px": 100}]
    fusion_rows = [{"rank": 4, "x": 120, "y": 204, "peak_response_dn": 40, "edge_distance_px": 100}]
    matched = match_candidate_positions(scale_rows, fusion_rows, radius_px=16)
    assert matched[0]["matched_fusion_rank"] == ""
    assert matched[0]["match_distance_px"] == ""
