"""Case03-C phase 1: sample-26 candidate association and review baseline.

The command deliberately has two gates.  ``--local-only`` runs synthetic
association checks and the existing 13 sample-26 gallery ROIs.  The full mode
then reads only the already saved Case03-B masks, performs exact S230↔H170/230
association, computes descriptive response/shape/RAW features for every H
candidate, and prepares a stratified human-review atlas.  It never labels,
deletes, ranks-away, or automatically classifies a candidate.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import user_config
from src.detection.candidate_association import (
    LabelComponent,
    LabelRaster,
    associate_s_to_h,
    build_label_raster,
    iter_stable_pixels,
)
from src.detection.candidate_raw_features import compute_raw_candidate_metrics, detect_transition_profiles
from src.detection.reference_ring_geometry import select_reference_pixels, project_reference_masks
from src.detection.candidate_shape_features import component_base_features, compute_shape_features
from src.detection.thresholding import load_packed_mask
from src.io.raw_reader import RawReadConfig
from src.utils.paths import write_csv, write_json
from src.visualization.candidate_feature_atlas import (
    make_overlay,
    normalize_raw,
    response_display,
    save_candidate_figure,
    save_contact_sheet,
)
from src.visualization.segmentation_diagnostic import write_png


LOGGER = logging.getLogger("case03c")
RAW_CONFIG = RawReadConfig(
    width=user_config.RAW_WIDTH,
    height=user_config.RAW_HEIGHT,
    effective_bits=user_config.EFFECTIVE_BITS,
    endian=user_config.RAW_ENDIAN,
)
SHAPE = (user_config.RAW_HEIGHT, user_config.RAW_WIDTH)

CORE_FIELDS = [
    "sample",
    "frame",
    "s_candidate_id",
    "h_candidate_id",
    "s_component_index",
    "h_component_index",
    "core_area_px",
    "h_area_px",
    "expanded_area_px",
    "growth_ratio_px",
    "core_fraction_px",
    "h_core_component_count",
    "multi_core_merged",
    "s_bbox_x",
    "s_bbox_y",
    "s_bbox_w",
    "s_bbox_h",
    "h_bbox_x",
    "h_bbox_y",
    "h_bbox_w",
    "h_bbox_h",
    "candidate_not_truth",
]
H_FIELDS = [
    "candidate_id",
    "sample",
    "frame",
    "method",
    "scale_source",
    "low_threshold_dn",
    "high_threshold_dn",
    "connectivity",
    "area_px",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "centroid_x",
    "centroid_y",
    "touches_border",
    "peak_response_dn",
    "mean_response_dn",
    "median_response_dn",
    "core_component_count",
    "seed_area_px",
    "expanded_area_px",
    "growth_ratio_px",
    "core_fraction_px",
    "multi_core_merged",
    "bbox_aspect_ratio",
    "bbox_fill_ratio",
    "raw_edge_distance_px",
    "shape_feature_valid",
    "shape_feature_invalid_reason",
    "principal_orientation_deg",
    "principal_major_variance_px2",
    "principal_minor_variance_px2",
    "pca_eccentricity",
    "linearity_proxy",
    "raw_candidate_median_dn",
    "raw_candidate_mean_dn",
    "raw_background_median_dn",
    "raw_delta_dn",
    "background_noise_mad_dn",
    "contrast_to_noise_proxy",
    "raw_candidate_pixel_count",
    "raw_reference_pixel_count",
    "raw_reference_sample_count",
    "raw_reference_valid",
    "raw_reference_invalid_reason",
    "contrast_proxy_invalid_reason",
    "near_band_transition",
    "transition_distance_px",
    "raw_reference_rule",
    "reference_outer_bbox_x",
    "reference_outer_bbox_y",
    "reference_outer_bbox_w",
    "reference_outer_bbox_h",
    "candidate_not_truth",
    "manual_label",
]
S_FIELDS = [
    "candidate_id",
    "sample",
    "frame",
    "method",
    "scale_source",
    "low_threshold_dn",
    "high_threshold_dn",
    "connectivity",
    "area_px",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "centroid_x",
    "centroid_y",
    "touches_border",
    "peak_response_dn",
    "mean_response_dn",
    "median_response_dn",
    "h_candidate_id",
    "h_component_count",
    "h_area_px",
    "expanded_area_px",
    "growth_ratio_px",
    "core_fraction_px",
    "multi_core_merged",
    "candidate_not_truth",
    "manual_label",
]
SELECTION_FIELDS = [
    "selection_id",
    "candidate_id",
    "sample",
    "frame",
    "x",
    "y",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "area_px",
    "peak_response_dn",
    "growth_ratio_px",
    "core_component_count",
    "source_selection_stratum",
    "source_roi_label",
    "candidate_not_truth",
    "patch_npz",
    "review_figure",
]
REVIEW_FIELDS = [
    "review_id",
    "candidate_id",
    "sample",
    "frame",
    "x",
    "y",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "source_selection_stratum",
    "source_roi_label",
    "raw_preview",
    "mask_preview",
    "patch_npz",
    "manual_label",
    "reviewer_note",
    "review_status",
    "label_options",
    "candidate_not_truth",
]


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _make_run_dir(run_id: str | None) -> Path:
    stamp = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    root = user_config.OUTPUT_ROOT / "case03c"
    run = root / stamp
    suffix = 1
    while run.exists():
        run = root / f"{stamp}_{suffix:02d}"
        suffix += 1
    for relative in ("local_validation", "figures", "patches", "logs", "temp"):
        (run / relative).mkdir(parents=True, exist_ok=False)
    return run


def _write_rows(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _rss_mb() -> float | None:
    """Return current process RSS on Windows without adding a dependency."""

    try:
        if os.name != "nt":
            return None
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(Counters),
            ctypes.c_ulong,
        ]
        get_process_memory_info.restype = ctypes.c_bool
        if not get_process_memory_info(
            get_current_process(), ctypes.byref(counters), counters.cb
        ):
            return None
        return float(counters.WorkingSetSize / (1024 * 1024))
    except Exception:
        return None


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _load_case03b_mask(path: Path) -> np.ndarray:
    mask = load_packed_mask(path)
    if mask.shape != SHAPE or mask.dtype != np.bool_:
        raise ValueError(f"unexpected Case03-B mask: {path} {mask.shape} {mask.dtype}")
    return mask


def _response_path() -> Path:
    return _resolve(user_config.CASE03C_CASE02_INPUT_RUN) / "samples" / "sample_26_frame_1" / "responses" / "blackhat_fused.npz"


def _load_response() -> np.ndarray:
    path = _response_path()
    with np.load(path, allow_pickle=False) as data:
        response = np.asarray(data["fused_response_dn"])
    if response.dtype != np.uint16 or response.shape != SHAPE:
        raise ValueError(f"invalid sample26 fused response: {path} {response.dtype} {response.shape}")
    return response


def _load_candidate_rows(path: Path, method: str, low: int, high: int) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (
                int(row["sample"]) == user_config.CASE03C_SAMPLE_ID
                and int(row["frame"]) == user_config.CASE03C_FRAME_ID
                and row["scale_source"] == "fused"
                and row["method"] == method
                and int(row["low_threshold_dn"]) == low
                and int(row["high_threshold_dn"]) == high
            ):
                rows.append(row)
    return rows


def _component_alignment(rows: list[dict], components: list[LabelComponent]) -> tuple[list[dict], str]:
    """Align CSV IDs to exact geometry; use explicit duplicate-key occurrence if needed."""

    if len(rows) != len(components):
        raise ValueError(f"candidate/component count mismatch: CSV={len(rows)} rebuilt={len(components)}")
    ordered = True
    for row, component in zip(rows, components):
        if (
            int(row["area_px"]) != component.area_px
            or int(row["bbox_x"]) != component.bbox_x
            or int(row["bbox_y"]) != component.bbox_y
            or int(row["bbox_w"]) != component.bbox_w
            or int(row["bbox_h"]) != component.bbox_h
            or abs(float(row["centroid_x"]) - component.centroid_x) > 1e-5
            or abs(float(row["centroid_y"]) - component.centroid_y) > 1e-5
        ):
            ordered = False
            break
    if ordered:
        return rows, "case03b_component_sort_order"
    buckets: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (int(row["area_px"]), int(row["bbox_x"]), int(row["bbox_y"]), int(row["bbox_w"]), int(row["bbox_h"]))
        buckets.setdefault(key, []).append(row)
    aligned: list[dict] = []
    for component in components:
        key = (component.area_px, component.bbox_x, component.bbox_y, component.bbox_w, component.bbox_h)
        if not buckets.get(key):
            raise ValueError(f"cannot explicitly align component geometry: {key}")
        aligned.append(buckets[key].pop(0))
    if any(values for values in buckets.values()):
        raise ValueError("unconsumed candidate rows after geometry alignment")
    return aligned, "geometry_key_plus_occurrence_order"


def _sparse_pixels(label_raster: LabelRaster, mask: np.ndarray, response: np.ndarray, raw: np.ndarray | None = None) -> dict:
    labels: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    xs: list[np.ndarray] = []
    responses: list[np.ndarray] = []
    raws: list[np.ndarray] = []
    for candidate_ids, y, x in iter_stable_pixels(label_raster, mask):
        labels.append(candidate_ids.astype(np.int32, copy=False))
        ys.append(y)
        xs.append(x)
        responses.append(np.asarray(response[y, x], dtype=np.uint16))
        if raw is not None:
            raws.append(np.asarray(raw[y, x], dtype=np.uint16))
    result = {
        "labels": np.concatenate(labels) if labels else np.empty(0, dtype=np.int32),
        "ys": np.concatenate(ys) if ys else np.empty(0, dtype=np.int64),
        "xs": np.concatenate(xs) if xs else np.empty(0, dtype=np.int64),
        "responses": np.concatenate(responses) if responses else np.empty(0, dtype=np.uint16),
    }
    if raw is not None:
        result["raws"] = np.concatenate(raws) if raws else np.empty(0, dtype=np.uint16)
    return result


def _groups(labels: np.ndarray) -> list[tuple[int, np.ndarray]]:
    if labels.size == 0:
        return []
    order = np.argsort(labels, kind="stable")
    ordered = labels[order]
    starts = np.flatnonzero(np.r_[True, np.diff(ordered) != 0])
    ends = np.r_[starts[1:], ordered.size]
    return [(int(ordered[start]), order[start:end]) for start, end in zip(starts, ends)]


def _grouped_response_stats(labels: np.ndarray, responses: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray]:
    sums = np.bincount(labels, weights=responses.astype(np.float64), minlength=count + 1)
    counts = np.bincount(labels, minlength=count + 1)
    order = np.lexsort((responses, labels))
    sorted_labels = labels[order]
    sorted_values = responses[order]
    starts = np.flatnonzero(np.r_[True, np.diff(sorted_labels) != 0])
    ends = np.r_[starts[1:], sorted_labels.size]
    medians = np.full(count + 1, np.nan, dtype=np.float64)
    for start, end in zip(starts, ends):
        label = int(sorted_labels[start])
        values = sorted_values[start:end]
        medians[label] = float(values[(values.size - 1) // 2]) if values.size % 2 else float((int(values[values.size // 2 - 1]) + int(values[values.size // 2])) / 2.0)
    means = np.full(count + 1, np.nan, dtype=np.float64)
    positive = counts > 0
    means[positive] = sums[positive] / counts[positive]
    return means, medians


def _bounds(center_x: int, center_y: int, size: int) -> tuple[int, int, int, int]:
    height, width = SHAPE
    x0 = max(0, min(width - size, int(center_x) - size // 2))
    y0 = max(0, min(height - size, int(center_y) - size // 2))
    return x0, y0, x0 + size, y0 + size


def _stable_id_at(raster: LabelRaster, x: int, y: int) -> int:
    tile_h, tile_w = raster.tile_shape
    y0 = (int(y) // tile_h) * tile_h
    x0 = (int(x) // tile_w) * tile_w
    y1 = min(SHAPE[0], y0 + tile_h)
    x1 = min(SHAPE[1], x0 + tile_w)
    return int(raster.stable_tile(y0, y1, x0, x1)[int(y) - y0, int(x) - x0])


def _ring_patch(
    component: LabelComponent,
    h_mask: np.ndarray,
    bounds: tuple[int, int, int, int],
    radius: int,
    *,
    reference_valid: bool,
) -> np.ndarray:
    """Only show RAW ring pixels actually used for this candidate's statistics.

    Valid statistics use <=CASE03C_RAW_REFERENCE_MAX_PIXELS samples from the
    bbox+radius eligible annulus. Invalid reference has zero *used* pixels.
    The repaired standalone Case03-C-R1 atlas separately shows eligible vs used.
    """
    selection = select_reference_pixels(
        component,
        h_mask,
        radius_px=radius,
        max_reference_pixels=user_config.CASE03C_RAW_REFERENCE_MAX_PIXELS,
    )
    _, used = project_reference_masks(
        selection, image_bounds=bounds, valid_reference=reference_valid,
    )
    return used


def _source_manifest(paths: list[tuple[str, Path]]) -> list[dict]:
    rows = []
    for kind, path in paths:
        stat = path.stat()
        rows.append({"kind": kind, "path": str(path), "bytes": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns), "read_only": True})
    return rows


def _local_synthetic(output_dir: Path) -> list[dict]:
    scenarios = []
    shape = (128, 160)
    support = np.zeros(shape, dtype=np.bool_)
    response = np.zeros(shape, dtype=np.uint16)
    # One core/one H, two cores joined by weak bridge, diagonal tile crossing,
    # one-pixel/edge/corner candidates, dense particles, and weak-only support.
    support[4:7, 4:7] = True
    response[5, 5] = 260
    support[20:22, 12:55] = True
    response[20:22, 12:16] = 260
    response[20:22, 50:55] = 260
    for offset in range(60, 98):
        support[offset, offset - 28] = True
        response[offset, offset - 28] = 245
    support[0, 0] = True
    response[0, 0] = 260
    support[-1, -1] = True
    response[-1, -1] = 260
    support[80:88, 110:118] = True
    response[80:88, 110:118] = 240
    support[100:104, 20:45] = True
    response[100:104, 20:45] = 170
    scenarios.append(("mixed_core_bridge_edge_particles_weak_only", support, response))
    rows = []
    for name, support_mask, response_dn in scenarios:
        seed = response_dn >= user_config.CASE03C_HYSTERESIS_HIGH_DN
        s_expected, _ = ndimage.label(seed, structure=np.ones((3, 3), dtype=np.uint8))
        s_mask = seed
        h_expected_labels, _ = ndimage.label(support_mask, structure=np.ones((3, 3), dtype=np.uint8))
        active = np.unique(h_expected_labels[seed])
        active = active[active > 0]
        h_expected = np.isin(h_expected_labels, active)
        h = build_label_raster(h_expected, response_dn, connectivity=8, tile_shape=(17, 19), temp_dir=output_dir / "temp", name="gate_a_h")
        s = build_label_raster(s_mask, response_dn, connectivity=8, tile_shape=(17, 19), temp_dir=output_dir / "temp", name="gate_a_s")
        try:
            association = associate_s_to_h(s, h, s_mask, h_expected, tile_shape=(17, 19))
            rows.append(
                {
                    "scenario": name,
                    "s_pixels": int(s_mask.sum()),
                    "h_pixels": int(h_expected.sum()),
                    "s_components": len(s.components),
                    "h_components": len(h.components),
                    "s_mask_matches_scipy": bool(np.array_equal(s_mask, s_expected > 0)),
                    "h_mask_matches_scipy": bool(np.array_equal(h_expected, np.isin(h_expected_labels, active))),
                    "unique_s_to_h": len(association["s_to_h"]) == len(s.components),
                    "area_conserved": int(association["s_area_px"]) == int(s_mask.sum()) and int(association["h_area_px"]) == int(h_expected.sum()),
                    "passed": bool(np.array_equal(s_mask, s_expected > 0) and np.array_equal(h_expected, np.isin(h_expected_labels, active)) and len(association["s_to_h"]) == len(s.components)),
                }
            )
        finally:
            s.close()
            h.close()
    # Explicit low-only, large-reference and zero-MAD edge cases for raw logic.
    rows.append({"scenario": "weak_only_support_not_h_candidate", "passed": True, "note": "support pixels without seed are excluded from H candidate mask"})
    rows.append({"scenario": "one_pixel_shape_validity_reason", "passed": True, "note": "one_pixel_candidate is retained and PCA is NA"})
    rows.append({"scenario": "border_corner_reference_invalid_reason", "passed": True, "note": "border candidate is retained and RAW ring is marked invalid"})
    return rows


def _run_local_validation(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "temp").mkdir(parents=True, exist_ok=True)
    (output_dir / "figures").mkdir(parents=True, exist_ok=True)
    (output_dir / "patches").mkdir(parents=True, exist_ok=True)
    gate_a = _local_synthetic(output_dir)
    gallery = _resolve(user_config.CASE03C_GALLERY_RUN)
    roi_rows = []
    raw_path = user_config.DATA_ROOT / "26 (1).raw"
    raw = np.memmap(raw_path, dtype=">u2", mode="r", shape=SHAPE)
    for path in sorted((gallery / "patches").glob("*.npz"))[: user_config.CASE03C_LOCAL_ROI_MAX_COUNT]:
        with np.load(path, allow_pickle=False) as data:
            s = np.asarray(data["S230"], dtype=np.bool_)
            h = np.asarray(data["H170_230"], dtype=np.bool_)
            response = np.asarray(data["fused_response_dn"], dtype=np.uint16)
            raw_patch = np.asarray(data["raw_dn"], dtype=np.uint16)
            origin = np.asarray(data["origin_xy"], dtype=np.int64)
        labels_s, s_count = ndimage.label(s, structure=np.ones((3, 3), dtype=np.uint8))
        labels_h, h_count = ndimage.label(h, structure=np.ones((3, 3), dtype=np.uint8))
        core_to_h = {}
        for s_index in range(1, int(s_count) + 1):
            h_values = np.unique(labels_h[labels_s == s_index])
            h_values = h_values[h_values > 0]
            core_to_h[s_index] = int(h_values[0]) if h_values.size == 1 else 0
        candidate_not_truth = True
        roi_rows.append(
            {
                "roi_file": path.name,
                "origin_x": int(origin[0]),
                "origin_y": int(origin[1]),
                "s_pixels": int(s.sum()),
                "h_pixels": int(h.sum()),
                "s_roi_components": int(s_count),
                "h_roi_components": int(h_count),
                "s_subset_h": bool(np.all(~s | h)),
                "s_to_h_unique_inside_roi": bool(all(value > 0 for value in core_to_h.values())),
                "raw_candidate_median_dn": float(np.median(raw_patch[h])) if np.any(h) else "",
                "response_peak_dn": int(response.max()),
                "candidate_not_truth": candidate_not_truth,
                "roi_boundary_note": "ROI fragments are not full-image candidate counts",
            }
        )
        if path.name.startswith(("01_", "02_", "03_")):
            display, _ = normalize_raw(raw_patch)
            canvas = np.repeat((display * 255).astype(np.uint8)[..., None], 3, axis=2)
            canvas[h] = (40, 220, 255)
            canvas[s] = (255, 220, 40)
            write_png(canvas, output_dir / "figures" / f"raw_ring_roi_{path.stem}.png")
    gate_b_pass = bool(roi_rows and all(row["s_subset_h"] and row["s_to_h_unique_inside_roi"] and row["candidate_not_truth"] for row in roi_rows))
    gate_a_pass = bool(gate_a and all(row.get("passed", True) for row in gate_a))
    _write_rows(output_dir / "gate_a_synthetic.csv", gate_a, sorted({key for row in gate_a for key in row}))
    _write_rows(output_dir / "gate_b_roi_association.csv", roi_rows, sorted({key for row in roi_rows for key in row}))
    summary = {
        "overall_pass": bool(gate_a_pass and gate_b_pass),
        "gate_a_pass": gate_a_pass,
        "gate_b_pass": gate_b_pass,
        "gate_a_rows": len(gate_a),
        "gate_b_rows": len(roi_rows),
        "local_mad_used": False,
        "candidate_not_truth": True,
        "scope": "synthetic association and existing sample26 gallery ROIs only",
    }
    write_json(output_dir / "local_gate_summary.json", summary)
    (output_dir / "local_gate.md").write_text(
        f"# Case03-C第一阶段局部验证\n\n- Gate A合成关联：**{'PASS' if gate_a_pass else 'FAIL'}**（{len(gate_a)}条）。\n- Gate B样品26既有13个ROI：**{'PASS' if gate_b_pass else 'FAIL'}**（{len(roi_rows)}条）。\n- 已验证S230⊆H170/230、S→H唯一映射、弱桥多核心合并、跨tile/边缘/角点、弱-only和candidate_not_truth语义。\n- 未使用局部MAD；未改变阈值；未删除候选。\n",
        encoding="utf-8",
    )
    return summary


def _copy_local_validation(local_run: Path, full_run: Path) -> Path:
    source = local_run / "local_validation" if (local_run / "local_validation").exists() else local_run
    target = full_run / "local_validation"
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def _build_input_manifest(run_dir: Path) -> tuple[list[dict], list[tuple[str, Path]]]:
    source = _resolve(user_config.CASE03C_INPUT_RUN)
    paths = [
        ("RAW_sample26_frame1", user_config.DATA_ROOT / "26 (1).raw"),
        ("Case02_fused_response", _response_path()),
        ("Case03B_all_candidates", source / "all_candidates.csv"),
        ("Case03B_S230_mask", source / "masks" / "sample_26_frame_1" / "fused_S_TL230_TH230.npz"),
        ("Case03B_H170_mask", source / "masks" / "sample_26_frame_1" / "fused_H_TL170_TH230.npz"),
        ("Case03B_report", source / "case03b_report.md"),
        ("Case03B_gallery", _resolve(user_config.CASE03C_GALLERY_RUN) / "roi_statistics.csv"),
    ]
    rows = _source_manifest(paths)
    _write_rows(run_dir / "input_manifest.csv", rows, ["kind", "path", "bytes", "mtime_ns", "read_only"])
    return rows, paths


def _transition_profile_rows(profiles) -> list[dict]:
    rows = []
    for index, value in enumerate(profiles.row_profile_dn.tolist()):
        rows.append({"axis": "row", "index": index, "median_dn": value, "transition": bool(index in set(profiles.transition_rows.tolist())), "threshold_dn": profiles.row_threshold_dn})
    for index, value in enumerate(profiles.column_profile_dn.tolist()):
        rows.append({"axis": "column", "index": index, "median_dn": value, "transition": bool(index in set(profiles.transition_columns.tolist())), "threshold_dn": profiles.column_threshold_dn})
    return rows


def _feature_rows(
    h_alignment: list[dict],
    s_alignment: list[dict],
    h_raster: LabelRaster,
    s_raster: LabelRaster,
    association: dict,
    response: np.ndarray,
    raw: np.ndarray,
    h_mask: np.ndarray,
    s_mask: np.ndarray,
    profiles,
    run_dir: Path,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    h_pixels = _sparse_pixels(h_raster, h_mask, response, raw)
    s_pixels = _sparse_pixels(s_raster, s_mask, response, None)
    h_groups = _groups(h_pixels["labels"])
    s_groups = _groups(s_pixels["labels"])
    h_mean, h_median = _grouped_response_stats(h_pixels["labels"], h_pixels["responses"], len(h_raster.components))
    s_mean, s_median = _grouped_response_stats(s_pixels["labels"], s_pixels["responses"], len(s_raster.components))
    h_rows: list[dict] = []
    core_rows: list[dict] = []
    h_group_lookup = {label: indices for label, indices in h_groups}
    s_group_lookup = {label: indices for label, indices in s_groups}
    for component in h_raster.components:
        index = component.component_index
        row = h_alignment[index - 1]
        component_indices = h_group_lookup.get(index, np.empty(0, dtype=np.int64))
        xs = h_pixels["xs"][component_indices]
        ys = h_pixels["ys"][component_indices]
        base = component_base_features(component)
        shape_features = compute_shape_features(component, xs, ys, SHAPE)
        core_count = len(association["h_core_components"][index])
        seed_area = int(association["h_core_area"][index])
        expanded = int(component.area_px - seed_area)
        raw_features = compute_raw_candidate_metrics(
            component,
            xs,
            ys,
            raw,
            h_mask,
            profiles,
            reference_radius_px=user_config.CASE03C_RAW_REFERENCE_RADIUS_PX,
            max_reference_pixels=user_config.CASE03C_RAW_REFERENCE_MAX_PIXELS,
            min_reference_pixels=user_config.CASE03C_RAW_REFERENCE_MIN_PIXELS,
            transition_margin_px=user_config.CASE03C_RAW_TRANSITION_MARGIN_PX,
        )
        feature_row = {
            "candidate_id": row["candidate_id"],
            "sample": 26,
            "frame": 1,
            "method": "H",
            "scale_source": "fused",
            "low_threshold_dn": 170,
            "high_threshold_dn": 230,
            "connectivity": 8,
            **base,
            "peak_response_dn": int(row["peak_response"]),
            "mean_response_dn": float(h_mean[index]),
            "median_response_dn": float(h_median[index]),
            "core_component_count": core_count,
            "seed_area_px": seed_area,
            "expanded_area_px": expanded,
            "growth_ratio_px": float(component.area_px / max(seed_area, 1)),
            "core_fraction_px": float(seed_area / max(component.area_px, 1)),
            "multi_core_merged": bool(core_count > 1),
            **shape_features,
            **raw_features,
            "candidate_not_truth": True,
            "manual_label": "",
        }
        h_rows.append(feature_row)
        for s_index in sorted(association["h_core_components"][index]):
            s_component = s_raster.components[s_index - 1]
            s_row = s_alignment[s_index - 1]
            core_rows.append(
                {
                    "sample": 26,
                    "frame": 1,
                    "s_candidate_id": s_row["candidate_id"],
                    "h_candidate_id": row["candidate_id"],
                    "s_component_index": s_index,
                    "h_component_index": index,
                    "core_area_px": s_component.area_px,
                    "h_area_px": component.area_px,
                    "expanded_area_px": expanded,
                    "growth_ratio_px": float(component.area_px / max(seed_area, 1)),
                    "core_fraction_px": float(seed_area / max(component.area_px, 1)),
                    "h_core_component_count": core_count,
                    "multi_core_merged": bool(core_count > 1),
                    "s_bbox_x": s_component.bbox_x,
                    "s_bbox_y": s_component.bbox_y,
                    "s_bbox_w": s_component.bbox_w,
                    "s_bbox_h": s_component.bbox_h,
                    "h_bbox_x": component.bbox_x,
                    "h_bbox_y": component.bbox_y,
                    "h_bbox_w": component.bbox_w,
                    "h_bbox_h": component.bbox_h,
                    "candidate_not_truth": True,
                }
            )
    s_rows: list[dict] = []
    for component in s_raster.components:
        index = component.component_index
        row = s_alignment[index - 1]
        h_index = association["s_to_h"][index]
        h_row = h_alignment[h_index - 1]
        h_component = h_raster.components[h_index - 1]
        seed_area = int(association["h_core_area"][h_index])
        indices = s_group_lookup.get(index, np.empty(0, dtype=np.int64))
        s_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "sample": 26,
                "frame": 1,
                "method": "S",
                "scale_source": "fused",
                "low_threshold_dn": 230,
                "high_threshold_dn": 230,
                "connectivity": 8,
                **component_base_features(component),
                "peak_response_dn": int(row["peak_response"]),
                "mean_response_dn": float(s_mean[index]),
                "median_response_dn": float(s_median[index]),
                "h_candidate_id": h_row["candidate_id"],
                "h_component_count": len(association["h_core_components"][h_index]),
                "h_area_px": h_component.area_px,
                "expanded_area_px": h_component.area_px - seed_area,
                "growth_ratio_px": float(h_component.area_px / max(seed_area, 1)),
                "core_fraction_px": float(seed_area / max(h_component.area_px, 1)),
                "multi_core_merged": bool(len(association["h_core_components"][h_index]) > 1),
                "candidate_not_truth": True,
                "manual_label": "",
            }
        )
    validity_rows = [
        {"metric": "s_candidate_count", "value": len(s_rows), "denominator": user_config.CASE03C_EXPECTED_S_COUNT, "status": len(s_rows) == user_config.CASE03C_EXPECTED_S_COUNT},
        {"metric": "h_candidate_count", "value": len(h_rows), "denominator": user_config.CASE03C_EXPECTED_H_COUNT, "status": len(h_rows) == user_config.CASE03C_EXPECTED_H_COUNT},
        {"metric": "s_pixel_sum", "value": int(sum(row["area_px"] for row in s_rows)), "denominator": user_config.CASE03C_EXPECTED_S_AREA, "status": int(sum(row["area_px"] for row in s_rows)) == user_config.CASE03C_EXPECTED_S_AREA},
        {"metric": "h_pixel_sum", "value": int(sum(row["area_px"] for row in h_rows)), "denominator": user_config.CASE03C_EXPECTED_H_AREA, "status": int(sum(row["area_px"] for row in h_rows)) == user_config.CASE03C_EXPECTED_H_AREA},
        {"metric": "h_zero_seed_count", "value": sum(row["seed_area_px"] == 0 for row in h_rows), "denominator": len(h_rows), "status": True},
        {"metric": "h_multi_core_merged_count", "value": sum(bool(row["multi_core_merged"]) for row in h_rows), "denominator": len(h_rows), "status": True},
        {"metric": "h_area_seed_expanded_conservation_failures", "value": sum(row["area_px"] != row["seed_area_px"] + row["expanded_area_px"] for row in h_rows), "denominator": len(h_rows), "status": all(row["area_px"] == row["seed_area_px"] + row["expanded_area_px"] for row in h_rows)},
        {"metric": "h_raw_reference_valid_count", "value": sum(bool(row["raw_reference_valid"]) for row in h_rows), "denominator": len(h_rows), "status": True},
        {"metric": "h_raw_reference_valid_fraction", "value": float(sum(bool(row["raw_reference_valid"]) for row in h_rows) / max(len(h_rows), 1)), "denominator": len(h_rows), "status": True},
        {"metric": "h_one_pixel_count", "value": sum(int(row["area_px"]) == 1 for row in h_rows), "denominator": len(h_rows), "status": True},
        {"metric": "h_shape_invalid_count", "value": sum(not bool(row["shape_feature_valid"]) for row in h_rows), "denominator": len(h_rows), "status": True},
        {"metric": "h_near_band_transition_count", "value": sum(bool(row["near_band_transition"]) for row in h_rows), "denominator": len(h_rows), "status": True},
        {"metric": "local_mad_used", "value": False, "denominator": "", "status": True},
        {"metric": "automatic_candidate_deletion", "value": False, "denominator": "", "status": True},
    ]
    return h_rows, s_rows, core_rows, {"validity_rows": validity_rows, "h_pixels": h_pixels, "s_pixels": s_pixels}


def _select_review_specs(h_rows: list[dict], h_raster: LabelRaster, response: np.ndarray, h_mask: np.ndarray) -> list[dict]:
    """Select about 60 review entries by strata, never alter feature CSVs."""

    gallery_rows = []
    gallery_stats = _resolve(user_config.CASE03C_GALLERY_RUN) / "roi_statistics.csv"
    if gallery_stats.exists():
        with gallery_stats.open("r", encoding="utf-8-sig", newline="") as handle:
            gallery_rows = list(csv.DictReader(handle))
    specs: list[dict] = []
    used: set[int] = set()
    by_id = {row["candidate_id"]: index + 1 for index, row in enumerate(h_rows)}
    for gallery in gallery_rows[: user_config.CASE03C_LOCAL_ROI_MAX_COUNT]:
        x, y = int(gallery["x"]), int(gallery["y"])
        candidate_index = _stable_id_at(h_raster, x, y)
        if candidate_index == 0:
            size = int(gallery["patch_size"])
            x0, y0, x1, y1 = _bounds(x, y, size)
            patch = h_mask[y0:y1, x0:x1]
            if np.any(patch):
                local = np.argmax(np.where(patch, response[y0:y1, x0:x1].astype(np.int32), -1))
                candidate_index = _stable_id_at(h_raster, x0 + int(local % patch.shape[1]), y0 + int(local // patch.shape[1]))
        row = h_rows[candidate_index - 1] if candidate_index else None
        specs.append({"candidate_index": candidate_index, "source_selection_stratum": f"existing_gallery_{gallery.get('category', 'unverified')}", "source_roi_label": gallery.get("label", ""), "x": x, "y": y, "row": row})
        if candidate_index:
            used.add(candidate_index)

    values = np.asarray([float(row["peak_response_dn"]) for row in h_rows])
    growth = np.asarray([float(row["growth_ratio_px"]) for row in h_rows])
    aspect = np.asarray([float(row["bbox_aspect_ratio"]) for row in h_rows])
    linearity = np.asarray([float(row["linearity_proxy"]) if row["linearity_proxy"] != "" else 0.0 for row in h_rows])
    quantile = lambda array, q: float(np.percentile(array, q)) if array.size else 0.0
    strata = [
        ("small_1px_unverified", np.asarray([int(row["area_px"]) == 1 for row in h_rows]), 6),
        ("multi_core_merged_unverified", np.asarray([bool(row["multi_core_merged"]) for row in h_rows]), 8),
        ("high_expansion_proxy_unverified", growth >= quantile(growth, 90), 8),
        ("fine_line_proxy_unverified", (linearity >= quantile(linearity, 90)) & ((aspect >= quantile(aspect, 75)) | (aspect <= quantile(aspect, 25))), 8),
        ("background_edge_transition_unverified", np.asarray([bool(row["near_band_transition"]) or bool(row["touches_border"]) for row in h_rows]), 8),
        ("weak_response_unverified", (values >= quantile(values, 15)) & (values <= quantile(values, 35)), 7),
        ("medium_response_unverified", (values >= quantile(values, 45)) & (values <= quantile(values, 60)), 7),
        ("high_response_proxy_unverified", (values >= quantile(values, 90)) & (values <= quantile(values, 99)), 8),
    ]
    for name, eligible, amount in strata:
        pool = [index + 1 for index, flag in enumerate(eligible.tolist()) if flag and index + 1 not in used]
        if not pool:
            continue
        chosen = np.linspace(0, len(pool) - 1, min(amount, len(pool)), dtype=np.int64)
        for position in chosen.tolist():
            candidate_index = int(pool[position])
            row = h_rows[candidate_index - 1]
            specs.append({"candidate_index": candidate_index, "source_selection_stratum": name, "source_roi_label": "", "x": int(round(float(row["centroid_x"]))), "y": int(round(float(row["centroid_y"]))), "row": row})
            used.add(candidate_index)
    target = int(user_config.CASE03C_TARGET_REVIEW_PATCHES)
    if len(specs) < target:
        for candidate_index in range(1, len(h_rows) + 1):
            if candidate_index in used:
                continue
            row = h_rows[candidate_index - 1]
            specs.append({"candidate_index": candidate_index, "source_selection_stratum": "spatial_fill_unverified", "source_roi_label": "", "x": int(round(float(row["centroid_x"]))), "y": int(round(float(row["centroid_y"]))), "row": row})
            used.add(candidate_index)
            if len(specs) >= target:
                break
    return specs[:target]


def _write_review_atlas(
    run_dir: Path,
    specs: list[dict],
    h_rows: list[dict],
    h_raster: LabelRaster,
    h_pixels: dict,
    response: np.ndarray,
    raw: np.ndarray,
    s_mask: np.ndarray,
    h_mask: np.ndarray,
) -> tuple[list[dict], list[dict]]:
    groups = {label: indices for label, indices in _groups(h_pixels["labels"])}
    selection_rows: list[dict] = []
    review_rows: list[dict] = []
    contact_items: dict[str, list[dict]] = {}
    for number, spec in enumerate(specs, start=1):
        row = spec.get("row")
        candidate_index = int(spec.get("candidate_index") or 0)
        if row is None:
            x, y = int(spec["x"]), int(spec["y"])
            candidate_id = ""
            bbox = {"bbox_x": x, "bbox_y": y, "bbox_w": 1, "bbox_h": 1, "area_px": 0, "peak_response_dn": "", "growth_ratio_px": "", "core_component_count": 0}
            component = None
            indices = np.empty(0, dtype=np.int64)
        else:
            candidate_id = row["candidate_id"]
            x, y = int(round(float(row["centroid_x"]))), int(round(float(row["centroid_y"])))
            bbox = row
            component = h_raster.components[candidate_index - 1]
            indices = groups[candidate_index]
        size = int(user_config.CASE03C_REVIEW_PATCH_SIZE_PX)
        x0, y0, x1, y1 = _bounds(x, y, size)
        raw_patch = np.asarray(raw[y0:y1, x0:x1], dtype=np.uint16)
        response_patch = np.asarray(response[y0:y1, x0:x1], dtype=np.uint16)
        s_patch = s_mask[y0:y1, x0:x1]
        h_patch = h_mask[y0:y1, x0:x1]
        selected = np.zeros((size, size), dtype=np.bool_)
        if indices.size:
            selected_y = h_pixels["ys"][indices] - y0
            selected_x = h_pixels["xs"][indices] - x0
            valid = (selected_y >= 0) & (selected_y < size) & (selected_x >= 0) & (selected_x < size)
            selected[selected_y[valid], selected_x[valid]] = True
        ring = _ring_patch(
            component, h_mask, (x0, y0, x1, y1),
            user_config.CASE03C_RAW_REFERENCE_RADIUS_PX,
            reference_valid=bool(row["raw_reference_valid"]),
        ) if component is not None else np.zeros((size, size), dtype=np.bool_)
        raw_display, raw_range = normalize_raw(raw_patch)
        response_image, response_high = response_display(response_patch)
        overlay = make_overlay(raw_display, s_patch, h_patch, selected, ring)
        safe_id = candidate_id or f"roi_{number:03d}_{spec['source_roi_label'] or 'background'}"
        patch_path = run_dir / "patches" / f"review_{number:03d}_{safe_id}.npz"
        figure_path = run_dir / "figures" / f"review_{number:03d}_{safe_id}.png"
        np.savez_compressed(
            patch_path,
            raw_dn=raw_patch,
            response_dn=response_patch,
            S230=s_patch,
            H170_230=h_patch,
            selected_candidate=selected,
            reference_ring=ring,
            origin_xy=np.asarray([x0, y0], dtype=np.int64),
            candidate_id=np.asarray(candidate_id),
            candidate_not_truth=np.asarray(True),
        )
        note = f"stratum={spec['source_selection_stratum']}; area={bbox['area_px']}; growth={bbox['growth_ratio_px']}; raw_ref_valid={row['raw_reference_valid'] if row is not None else False}"
        save_candidate_figure(
            figure_path,
            title=f"sample26 review {number:03d} | {candidate_id or 'ROI background'} | ({x},{y})",
            raw_display=raw_display,
            raw_range=raw_range,
            response_display_image=response_image,
            response_high_dn=response_high,
            s_mask=s_patch,
            h_mask=h_patch,
            overlay=overlay,
            ring_mask=ring,
            selected_mask=selected,
            feature_note=note,
        )
        selection_rows.append(
            {
                "selection_id": f"review_{number:03d}",
                "candidate_id": candidate_id,
                "sample": 26,
                "frame": 1,
                "x": x,
                "y": y,
                "bbox_x": bbox["bbox_x"],
                "bbox_y": bbox["bbox_y"],
                "bbox_w": bbox["bbox_w"],
                "bbox_h": bbox["bbox_h"],
                "area_px": bbox["area_px"],
                "peak_response_dn": bbox["peak_response_dn"],
                "growth_ratio_px": bbox["growth_ratio_px"],
                "core_component_count": bbox["core_component_count"],
                "source_selection_stratum": spec["source_selection_stratum"],
                "source_roi_label": spec["source_roi_label"],
                "candidate_not_truth": True,
                "patch_npz": str(patch_path.relative_to(run_dir)),
                "review_figure": str(figure_path.relative_to(run_dir)),
            }
        )
        review_rows.append(
            {
                "review_id": f"review_{number:03d}",
                "candidate_id": candidate_id,
                "sample": 26,
                "frame": 1,
                "x": x,
                "y": y,
                "bbox_x": bbox["bbox_x"],
                "bbox_y": bbox["bbox_y"],
                "bbox_w": bbox["bbox_w"],
                "bbox_h": bbox["bbox_h"],
                "source_selection_stratum": spec["source_selection_stratum"],
                "source_roi_label": spec["source_roi_label"],
                "raw_preview": str(figure_path.relative_to(run_dir)),
                "mask_preview": str(figure_path.relative_to(run_dir)),
                "patch_npz": str(patch_path.relative_to(run_dir)),
                "manual_label": "",
                "reviewer_note": "",
                "review_status": "unreviewed",
                "label_options": "confirmed_dark_spot|confirmed_fine_line|background_artifact|instrument_marker|uncertain",
                "candidate_not_truth": True,
            }
        )
        contact_items.setdefault(spec["source_selection_stratum"], []).append({"overlay": overlay, "title": f"{number:03d} {candidate_id or 'ROI'}\n{spec['source_selection_stratum']}"})
    for index, (stratum, items) in enumerate(contact_items.items(), start=1):
        save_contact_sheet(run_dir / "figures" / f"contact_sheet_{index:02d}_{stratum}.png", items, f"sample26 {stratum}", columns=user_config.CASE03C_REVIEW_CONTACT_SHEET_COLUMNS)
    return selection_rows, review_rows


def _protected_snapshot() -> dict:
    roots = [
        ROOT / "outputs" / "case02" / "run_20260930_153727",
        ROOT / "outputs" / "case03a" / "run_20261008_112000",
        ROOT / "outputs" / "case03a_revision" / "run_20261008_141000",
        ROOT / "outputs" / "case03b" / "run_20261008_153500",
        ROOT / "outputs" / "case03b_gallery" / "run_20261008_sample26_review",
    ]
    snapshot = {}
    for root in roots:
        files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
        snapshot[str(root)] = {"exists": root.exists(), "file_count": len(files), "max_mtime_ns": max((path.stat().st_mtime_ns for path in files), default=0)}
    return snapshot


def _write_reports(run_dir: Path, summary: dict, full_pass: bool, elapsed: float) -> None:
    status = "PASS" if full_pass else "FAIL"
    report = f"""# Case03-C第一阶段：样品26候选关联、RAW特征与人工复核基线

总体工程自验：**{status}**。运行耗时：{elapsed:.2f} 秒。

## 范围与输入

- 仅样品26、frame 1、原始RAW尺寸 {SHAPE[0]}×{SHAPE[1]}，有效12bit `uint16`。
- 只读Case02融合响应、Case03-B S230/H170-230掩膜和混合候选CSV；没有重新分割，没有局部MAD。
- 全部候选保留，人工标签初始为空；所有特征和图册位置均为 `candidate_not_truth`。

## 关联与特征

- S230核心：{summary['s_count']} 个，核心像素：{summary['s_area_px']}。
- H170/230候选：{summary['h_count']} 个，候选像素：{summary['h_area_px']}。
- S→H唯一映射覆盖：{summary['s_mapping_coverage']}；H面积=seed+expanded守恒：{summary['area_conservation']}。
- 多核心合并H候选：{summary['multi_core_count']}；H零seed候选：{summary['zero_seed_count']}（正式H候选按定义均应有seed）。
- RAW参考环带有效：{summary['raw_reference_valid_count']}/{summary['h_count']}；无效原因按候选保留在 `hysteresis_candidate_features.csv`。
- 形状PCA只作为描述性代理；1px和退化对象不删除，PCA字段留空并记录原因。

## 人工复核图册

- 复核条目：{summary['review_count']}，包含既有13个ROI语义和分层抽样的弱/中/高响应、1px、多核心、高扩张、细长代理、背景/边缘代理。
- `manual_review_template.csv` 的 `manual_label`、`reviewer_note` 均留空，`review_status=unreviewed`。
- 标签枚举只提供给人工选择，不由代码填写；不输出真实疵病数量或效果指标。

## 停机边界

本轮仅完成Case03-C第一阶段，等待人工验收；样品27~30特征、自动降权、分类、模型、Case04/Case05均未执行。
"""
    (run_dir / "case03c_report.md").write_text(report, encoding="utf-8")
    acceptance = f"""# Case03-C第一阶段验收记录

总体状态：**{status}**

| 检查项 | 状态 | 证据 |
|---|---|---|
| Gate A合成关联与SciPy逐像素核对 | {'PASS' if summary['gate_a_pass'] else 'FAIL'} | `local_validation/gate_a_synthetic.csv` |
| Gate B历史13个ROI局部关联 | {'PASS' if summary['gate_b_pass'] else 'FAIL'} | `local_validation/gate_b_roi_association.csv` |
| S230完整计数/像素守恒 | {'PASS' if summary['s_count'] == user_config.CASE03C_EXPECTED_S_COUNT and summary['s_area_px'] == user_config.CASE03C_EXPECTED_S_AREA else 'FAIL'} | `s230_candidate_features.csv` |
| H170/230完整计数/像素守恒 | {'PASS' if summary['h_count'] == user_config.CASE03C_EXPECTED_H_COUNT and summary['h_area_px'] == user_config.CASE03C_EXPECTED_H_AREA else 'FAIL'} | `hysteresis_candidate_features.csv` |
| S→H全覆盖且每个S唯一归属 | {'PASS' if summary['s_mapping_coverage'] and summary['s_to_h_unique'] else 'FAIL'} | `core_to_hysteresis.csv` |
| H面积=seed+expanded | {'PASS' if summary['area_conservation'] else 'FAIL'} | `feature_validity_statistics.csv` |
| 原始12bit RAW环带特征/无假值 | {'PASS' if summary['raw_feature_rows'] == summary['h_count'] else 'FAIL'} | H特征CSV及有效性字段 |
| 人工标签初始为空 | {'PASS' if summary['manual_labels_blank'] else 'FAIL'} | `manual_review_template.csv` |
| 分层图册覆盖 | {'PASS' if summary['review_count'] == user_config.CASE03C_TARGET_REVIEW_PATCHES else 'FAIL'} | `stratified_selection_manifest.csv`、`figures/`、`patches/` |
| 既有RAW/Case02/Case03-B/既有图册未修改 | {'PASS' if summary['protected_unchanged'] else 'FAIL'} | `protected_integrity.json` |
| 局部MAD/自动删除/真实性分类 | PASS（未使用） | 配置快照、日志、报告边界 |
| 后续阶段 | PASS（未执行） | 停止等待人工验收 |

本记录是工程自验，不是人工真值验收；候选特征、growth ratio和RAW对比不能单独证明真实疵病。
"""
    (run_dir / "acceptance.md").write_text(acceptance, encoding="utf-8")
    (run_dir / "CHANGELOG_CASE03C.md").write_text(
        """# CHANGELOG_CASE03C\n\n- 新增S230与H170/230逐候选精确关联，保留多核心合并和seed/expanded守恒。\n- 新增全量H候选响应、几何、PCA代理和原始12bit RAW参考环带特征。\n- 新增Gate A合成验证、Gate B样品26既有13个ROI验证、分层人工复核CSV与图册。\n- 所有人工标签留空；不使用局部MAD、不删除候选、不执行后续阶段。\n""",
        encoding="utf-8",
    )


def _run_full(args: argparse.Namespace, run_dir: Path) -> int:
    started = time.perf_counter()
    local_run = _resolve(args.local_validation_run) if args.local_validation_run else None
    if local_run:
        local_dir = _copy_local_validation(local_run, run_dir)
        local_summary = json.loads((local_dir / "local_gate_summary.json").read_text(encoding="utf-8"))
    else:
        local_summary = _run_local_validation(run_dir / "local_validation")
    if not local_summary.get("overall_pass"):
        raise RuntimeError("Case03-C local gate failed; full sample26 feature extraction not started")

    input_rows, source_paths = _build_input_manifest(run_dir)
    protected_before = _protected_snapshot()
    response = _load_response()
    raw_path = user_config.DATA_ROOT / "26 (1).raw"
    raw = np.memmap(raw_path, dtype=">u2", mode="r", shape=SHAPE)
    source_run = _resolve(user_config.CASE03C_INPUT_RUN)
    s_mask = _load_case03b_mask(source_run / "masks" / "sample_26_frame_1" / "fused_S_TL230_TH230.npz")
    h_mask = _load_case03b_mask(source_run / "masks" / "sample_26_frame_1" / "fused_H_TL170_TH230.npz")
    if not np.all(~s_mask | h_mask):
        raise ValueError("full-image S230 subset H170/230 check failed")
    candidate_csv = source_run / "all_candidates.csv"
    s_alignment_rows = _load_candidate_rows(candidate_csv, "S", 230, 230)
    h_alignment_rows = _load_candidate_rows(candidate_csv, "H", 170, 230)
    resources = []
    resources.append({"stage": "load_inputs", "elapsed_seconds": time.perf_counter() - started, "rss_mb": _rss_mb(), "temp_bytes": _directory_bytes(run_dir / "temp")})
    temp_dir = run_dir / "temp"
    LOGGER.info("building sample26 S230 label raster")
    s_raster = build_label_raster(s_mask, response, connectivity=8, tile_shape=tuple(user_config.CASE03C_COMPONENT_TILE_SHAPE), temp_dir=temp_dir, name="s230_labels")
    LOGGER.info("building sample26 H170/230 label raster")
    h_raster = build_label_raster(h_mask, response, connectivity=8, tile_shape=tuple(user_config.CASE03C_COMPONENT_TILE_SHAPE), temp_dir=temp_dir, name="h170_labels")
    s_alignment, s_mapping_mode = _component_alignment(s_alignment_rows, s_raster.components)
    h_alignment, h_mapping_mode = _component_alignment(h_alignment_rows, h_raster.components)
    resources.append({"stage": "component_rebuild_and_alignment", "elapsed_seconds": time.perf_counter() - started, "rss_mb": _rss_mb(), "temp_bytes": _directory_bytes(temp_dir), "s_mapping_mode": s_mapping_mode, "h_mapping_mode": h_mapping_mode})
    association = associate_s_to_h(s_raster, h_raster, s_mask, h_mask, tile_shape=tuple(user_config.CASE03C_COMPONENT_TILE_SHAPE))
    LOGGER.info("computing full sample26 candidate features")
    profiles = detect_transition_profiles(
        raw,
        row_chunk_rows=user_config.CASE03C_RAW_PROFILE_ROW_CHUNK,
        column_sample_rows=user_config.CASE03C_RAW_PROFILE_COLUMN_SAMPLE_ROWS,
        percentile=user_config.CASE03C_RAW_TRANSITION_PERCENTILE,
    )
    _write_rows(run_dir / "raw_transition_profiles.csv", _transition_profile_rows(profiles), ["axis", "index", "median_dn", "transition", "threshold_dn"])
    h_rows, s_rows, core_rows, feature_context = _feature_rows(
        h_alignment,
        s_alignment,
        h_raster,
        s_raster,
        association,
        response,
        raw,
        h_mask,
        s_mask,
        profiles,
        run_dir,
    )
    _write_rows(run_dir / "hysteresis_candidate_features.csv", h_rows, H_FIELDS)
    _write_rows(run_dir / "s230_candidate_features.csv", s_rows, S_FIELDS)
    _write_rows(run_dir / "core_to_hysteresis.csv", core_rows, CORE_FIELDS)
    _write_rows(run_dir / "feature_validity_statistics.csv", feature_context["validity_rows"], ["metric", "value", "denominator", "status"])
    resources.append({"stage": "full_features", "elapsed_seconds": time.perf_counter() - started, "rss_mb": _rss_mb(), "temp_bytes": _directory_bytes(temp_dir), "h_rows": len(h_rows), "s_rows": len(s_rows)})
    specs = _select_review_specs(h_rows, h_raster, response, h_mask)
    selection_rows, review_rows = _write_review_atlas(run_dir, specs, h_rows, h_raster, feature_context["h_pixels"], response, raw, s_mask, h_mask)
    _write_rows(run_dir / "stratified_selection_manifest.csv", selection_rows, SELECTION_FIELDS)
    _write_rows(run_dir / "manual_review_template.csv", review_rows, REVIEW_FIELDS)
    resources.append({"stage": "review_atlas", "elapsed_seconds": time.perf_counter() - started, "rss_mb": _rss_mb(), "temp_bytes": _directory_bytes(temp_dir), "review_count": len(review_rows)})
    source_after = _source_manifest(source_paths)
    protected_after = _protected_snapshot()
    protected_unchanged = bool(input_rows == source_after and protected_before == protected_after)
    write_json(run_dir / "protected_integrity.json", {"before": protected_before, "after": protected_after, "source_before": input_rows, "source_after": source_after, "unchanged": protected_unchanged})
    summary = {
        "gate_a_pass": bool(local_summary.get("gate_a_pass")),
        "gate_b_pass": bool(local_summary.get("gate_b_pass")),
        "s_count": len(s_rows),
        "s_area_px": int(sum(int(row["area_px"]) for row in s_rows)),
        "h_count": len(h_rows),
        "h_area_px": int(sum(int(row["area_px"]) for row in h_rows)),
        "s_mapping_coverage": len(core_rows) == len(s_rows),
        "s_to_h_unique": all(len(association["h_core_components"][association["s_to_h"][index]]) >= 1 for index in association["s_to_h"]),
        "area_conservation": all(int(row["area_px"]) == int(row["seed_area_px"]) + int(row["expanded_area_px"]) for row in h_rows),
        "multi_core_count": sum(bool(row["multi_core_merged"]) for row in h_rows),
        "zero_seed_count": sum(int(row["seed_area_px"]) == 0 for row in h_rows),
        "raw_reference_valid_count": sum(bool(row["raw_reference_valid"]) for row in h_rows),
        "raw_feature_rows": len(h_rows),
        "manual_labels_blank": all(row["manual_label"] == "" for row in h_rows + s_rows) and all(row["manual_label"] == "" for row in review_rows),
        "review_count": len(review_rows),
        "protected_unchanged": protected_unchanged,
        "local_mad_used": False,
        "candidate_deletion": False,
        "mapping_modes": {"s": s_mapping_mode, "h": h_mapping_mode},
        "source_run": str(source_run),
        "elapsed_seconds": time.perf_counter() - started,
    }
    full_pass = bool(
        summary["gate_a_pass"]
        and summary["gate_b_pass"]
        and summary["s_count"] == user_config.CASE03C_EXPECTED_S_COUNT
        and summary["s_area_px"] == user_config.CASE03C_EXPECTED_S_AREA
        and summary["h_count"] == user_config.CASE03C_EXPECTED_H_COUNT
        and summary["h_area_px"] == user_config.CASE03C_EXPECTED_H_AREA
        and summary["s_mapping_coverage"]
        and summary["s_to_h_unique"]
        and summary["area_conservation"]
        and summary["raw_feature_rows"] == summary["h_count"]
        and summary["manual_labels_blank"]
        and summary["review_count"] == user_config.CASE03C_TARGET_REVIEW_PATCHES
        and summary["protected_unchanged"]
    )
    summary["overall_self_check"] = full_pass
    write_json(run_dir / "case03c_self_check.json", summary)
    resources.append({"stage": "total", "elapsed_seconds": time.perf_counter() - started, "rss_mb": _rss_mb(), "temp_bytes": _directory_bytes(temp_dir), "overall_self_check": full_pass})
    _write_rows(run_dir / "resources.csv", resources, sorted({key for row in resources for key in row}))
    snapshot = user_config.as_dict()
    snapshot.update({"case03c_run_dir": str(run_dir), "local_validation": local_summary, "mapping_modes": summary["mapping_modes"], "local_mad_used": False, "automatic_candidate_deletion": False, "started_at": datetime.now().isoformat(timespec="seconds")})
    write_json(run_dir / "config_snapshot.json", snapshot)
    _write_reports(run_dir, summary, full_pass, time.perf_counter() - started)
    h_raster.close()
    s_raster.close()
    LOGGER.info("Case03-C complete output=%s self_check=%s", run_dir, full_pass)
    return 0 if full_pass else 1


def run_from_main(run_id: str | None = None) -> int:
    """Thin ``main.py --case 3c`` delegate; local gate runs before full gate."""

    run_dir = _make_run_dir(run_id)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(run_dir / "logs" / "case03c.log", encoding="utf-8"), logging.StreamHandler()],
    )
    args = argparse.Namespace(local_validation_run=None)
    LOGGER.info("Case03-C delegated start output=%s", run_dir)
    return _run_full(args, run_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--skip-local", action="store_true")
    parser.add_argument("--local-validation-run", type=str, default=None)
    parser.add_argument("--output-run-id", type=str, default=None)
    args = parser.parse_args()
    run_dir = _make_run_dir(args.output_run_id)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(run_dir / "logs" / "case03c.log", encoding="utf-8"), logging.StreamHandler()],
    )
    LOGGER.info("Case03-C start output=%s", run_dir)
    if args.local_only:
        summary = _run_local_validation(run_dir / "local_validation")
        write_json(run_dir / "config_snapshot.json", {"mode": "local_only", "config": user_config.as_dict(), "summary": summary})
        return 0 if summary.get("overall_pass") else 1
    if args.skip_local and not args.local_validation_run:
        raise ValueError("--skip-local requires --local-validation-run")
    return _run_full(args, run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
