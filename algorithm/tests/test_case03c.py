from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from src.detection.candidate_association import associate_s_to_h, build_label_raster
from src.detection.candidate_raw_features import TransitionProfiles, compute_raw_candidate_metrics
from src.detection.candidate_shape_features import compute_shape_features


def test_s_to_h_one_to_one_and_multi_core_weak_bridge(tmp_path):
    response = np.zeros((48, 64), dtype=np.uint16)
    support = np.zeros(response.shape, dtype=bool)
    support[20:22, 5:55] = True
    response[20:22, 5:10] = 260
    response[20:22, 50:55] = 260
    response[support & (response == 0)] = 170
    s_mask = response >= 230
    h_mask = support
    s = build_label_raster(s_mask, response, connectivity=8, tile_shape=(7, 11), temp_dir=tmp_path, name="s")
    h = build_label_raster(h_mask, response, connectivity=8, tile_shape=(7, 11), temp_dir=tmp_path, name="h")
    try:
        association = associate_s_to_h(s, h, s_mask, h_mask, tile_shape=(7, 11))
        assert len(s.components) == 2
        assert len(h.components) == 1
        assert len(association["h_core_components"][1]) == 2
        assert int(association["h_core_area"][1]) == int(s_mask.sum())
    finally:
        s.close()
        h.close()


def test_one_pixel_shape_is_retained_with_explicit_pca_reason(tmp_path):
    response = np.zeros((5, 5), dtype=np.uint16)
    response[0, 0] = 260
    raster_mask = response > 0
    raster = build_label_raster(raster_mask, response, connectivity=8, tile_shape=(2, 2), temp_dir=tmp_path, name="one")
    try:
        feature = compute_shape_features(raster.components[0], np.asarray([0]), np.asarray([0]), raster.shape)
        assert feature["shape_feature_valid"] is False
        assert feature["shape_feature_invalid_reason"] == "one_pixel_candidate"
    finally:
        raster.close()


def test_raw_reference_mad_zero_is_not_inflated(tmp_path):
    raw = np.full((32, 32), 1000, dtype=np.uint16)
    raw[15, 15] = 900
    response = np.zeros(raw.shape, dtype=np.uint16)
    response[15, 15] = 260
    raster = build_label_raster(response > 0, response, connectivity=8, tile_shape=(8, 8), temp_dir=tmp_path, name="raw")
    try:
        component = raster.components[0]
        profiles = TransitionProfiles(
            row_profile_dn=np.full(32, 1000.0),
            column_profile_dn=np.full(32, 1000.0),
            transition_rows=np.empty(0, dtype=np.int32),
            transition_columns=np.empty(0, dtype=np.int32),
            row_threshold_dn=0.0,
            column_threshold_dn=0.0,
        )
        result = compute_raw_candidate_metrics(
            component,
            np.asarray([15]),
            np.asarray([15]),
            raw,
            response > 0,
            profiles,
            reference_radius_px=4,
            max_reference_pixels=100,
            min_reference_pixels=4,
            transition_margin_px=2,
        )
        assert result["raw_reference_valid"] is True
        assert result["background_noise_mad_dn"] == 0.0
        assert result["contrast_to_noise_proxy"] == ""
        assert result["contrast_proxy_invalid_reason"] == "background_mad_zero"
    finally:
        raster.close()


def test_case03c_full_output_exact_counts_if_available():
    root = Path(__file__).resolve().parents[1]
    path = root / "outputs" / "case03c" / "run_20261008_"  # placeholder keeps test skip-friendly
    runs = sorted((root / "outputs" / "case03c").glob("run_*") if (root / "outputs" / "case03c").exists() else [])
    full_runs = [run for run in runs if (run / "hysteresis_candidate_features.csv").exists()]
    if not full_runs:
        return
    run = full_runs[-1]
    with (run / "hysteresis_candidate_features.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        h_rows = list(csv.DictReader(handle))
    with (run / "s230_candidate_features.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        s_rows = list(csv.DictReader(handle))
    assert len(h_rows) == 88043
    assert len(s_rows) == 91937
    assert sum(int(row["area_px"]) for row in h_rows) == 311790
    assert sum(int(row["area_px"]) for row in s_rows) == 121467
    assert all(row["manual_label"] == "" for row in h_rows + s_rows)
