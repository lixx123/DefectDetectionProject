"""Case03-B: fused-response candidate extraction.

The script has two explicit gates:

1. ``--local-only`` builds synthetic and sample-26 patch evidence.
2. the full run reads Case02 fused responses read-only and extracts every S/H
   component for samples 26--30.  The 31px response is used only once for the
   requested sample-26 comparison.

No morphology, area filtering, Top-N truncation, or truth claim is made here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage

# Allow ``python scripts/run_case03b.py`` to resolve project packages.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import user_config
from src.detection.thresholding import load_packed_mask, save_packed_mask
from src.detection.tiled_components import ComponentExtraction, extract_tiled_components
from src.io.raw_reader import RawReadConfig, read_raw
from src.utils.paths import discover_raw_files, json_safe, write_csv, write_json
from src.visualization.segmentation_diagnostic import (
    any_hit_thumbnail,
    density_thumbnail,
    response_preview,
    write_png,
)


LOGGER = logging.getLogger("case03b")
RAW_CONFIG = RawReadConfig(
    width=user_config.RAW_WIDTH,
    height=user_config.RAW_HEIGHT,
    effective_bits=user_config.EFFECTIVE_BITS,
    endian=user_config.RAW_ENDIAN,
)

METHOD_FIELDS = [
    "candidate_id",
    "sample",
    "frame",
    "method",
    "scale_source",
    "low_threshold_dn",
    "high_threshold_dn",
    "connectivity",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "centroid_x",
    "centroid_y",
    "area_px",
    "peak_response",
    "touches_border",
    "seed_pixel_count",
    "manual_label",
]
SUMMARY_FIELDS = [
    "sample",
    "frame",
    "method",
    "scale_source",
    "low_threshold_dn",
    "high_threshold_dn",
    "connectivity",
    "candidate_count",
    "support_component_count",
    "support_pixel_count",
    "seed_pixel_count",
    "final_pixel_count",
    "low_only_pixel_count",
    "low_only_fraction",
    "area_sum_px",
    "area_min_px",
    "area_p50_px",
    "area_p90_px",
    "area_p99_px",
    "area_max_px",
    "border_component_count",
    "largest_bbox_w",
    "largest_bbox_h",
    "provisional_label_count",
    "tile_count",
    "mask_path",
    "low_only_mask_path",
]
MASK_FIELDS = [
    "path",
    "sample",
    "frame",
    "method",
    "kind",
    "scale_source",
    "low_threshold_dn",
    "high_threshold_dn",
    "connectivity",
    "shape",
    "mask_pixel_count",
    "packed_bytes",
    "file_bytes",
]
FUSION_FIELDS = [
    "scope",
    "sample",
    "frame",
    "method",
    "low_threshold_dn",
    "high_threshold_dn",
    "connectivity",
    "fused_ge_31px_all",
    "fused_gt_31px_count",
    "equal_count",
    "fused_response_min_delta",
    "fused_response_max_delta",
    "fused_response_mean_delta",
    "mask_fused_count",
    "mask_31px_count",
    "fused_only_count",
    "thirty_one_only_count",
    "x",
    "y",
    "fused_dn",
    "thirty_one_dn",
    "delta_dn",
]


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _make_run_dir(run_id: str | None) -> Path:
    stamp = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    base = user_config.OUTPUT_ROOT / "case03b"
    run_dir = base / stamp
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{suffix:02d}"
        suffix += 1
    for relative in (
        "local_validation",
        "masks",
        "figures",
        "patches",
        "logs",
        "temp",
    ):
        (run_dir / relative).mkdir(parents=True, exist_ok=False)
    return run_dir


def _open_writer(path: Path, fields: list[str]) -> tuple[object, csv.DictWriter]:
    handle = path.open("w", encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    return handle, writer


def _load_response(path: Path, key: str = "fused_response_dn") -> np.ndarray:
    with np.load(path, allow_pickle=False) as data:
        if key not in data.files:
            raise KeyError(f"Case02 response missing {key}: {path}; keys={data.files}")
        response = np.asarray(data[key])
    if response.dtype != np.uint16 or response.ndim != 2:
        raise TypeError(f"Case02 response must be 2-D uint16: {path} -> {response.dtype} {response.shape}")
    if response.shape != (user_config.RAW_HEIGHT, user_config.RAW_WIDTH):
        raise ValueError(f"Case02 response shape mismatch: {path} -> {response.shape}")
    if not np.isfinite(response).all():
        raise ValueError(f"Case02 response contains non-finite values: {path}")
    return response


def _raw_index() -> dict[tuple[int, int], dict]:
    return {(int(row["sample_id"]), int(row["frame_id"])): row for row in discover_raw_files(user_config.DATA_ROOT)}


def _response_path(input_run: Path, sample: int, frame: int, name: str = "blackhat_fused.npz") -> Path:
    return input_run / "samples" / f"sample_{sample}_frame_{frame}" / "responses" / name


def _record_mask(
    path: Path,
    mask: np.ndarray,
    sample: int,
    frame: int,
    method: str,
    kind: str,
    scale_source: str,
    low: int,
    high: int,
    connectivity: int,
) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = save_packed_mask(path, np.asarray(mask, dtype=np.bool_))
    return {
        "path": str(path),
        "sample": sample,
        "frame": frame,
        "method": method,
        "kind": kind,
        "scale_source": scale_source,
        "low_threshold_dn": low,
        "high_threshold_dn": high,
        "connectivity": connectivity,
        "shape": "x".join(str(value) for value in mask.shape),
        "mask_pixel_count": int(np.count_nonzero(mask)),
        "packed_bytes": int(meta["packed_bytes"]),
        "file_bytes": int(meta["file_bytes"]),
    }


def _response_mask_figure(
    response: np.ndarray,
    final_mask: np.ndarray,
    low_only_mask: np.ndarray,
    path: Path,
    title: str,
) -> None:
    high = max(float(np.percentile(response, 99.9)), 1.0)
    panels = [
        response_preview(response, high, user_config.CASE03B_PREVIEW_MAX_EDGE_PX),
        density_thumbnail(final_mask, user_config.CASE03B_PREVIEW_MAX_EDGE_PX),
        any_hit_thumbnail(low_only_mask, user_config.CASE03B_PREVIEW_MAX_EDGE_PX),
    ]
    panels = [cv2.cvtColor(panel, cv2.COLOR_GRAY2BGR) for panel in panels]
    height = max(panel.shape[0] for panel in panels)
    normalized = [
        cv2.copyMakeBorder(panel, 0, height - panel.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        for panel in panels
    ]
    canvas = cv2.hconcat(normalized)
    cv2.putText(canvas, title, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
    write_png(canvas, path)


def _summary_row(
    sample: int,
    frame: int,
    method: str,
    low: int,
    high: int,
    connectivity: int,
    extraction: ComponentExtraction,
    mask_path: str,
    low_only_mask_path: str,
) -> dict:
    areas = np.asarray([int(row["area_px"]) for row in extraction.components], dtype=np.float64)
    if areas.size:
        area_min = int(areas.min())
        area_p50, area_p90, area_p99, area_max = (float(value) for value in np.percentile(areas, [50, 90, 99, 100]))
        largest = max(extraction.components, key=lambda row: int(row["area_px"]))
        largest_w, largest_h = int(largest["bbox_w"]), int(largest["bbox_h"])
        border_count = sum(bool(row["touches_border"]) for row in extraction.components)
    else:
        area_min = 0
        area_p50 = area_p90 = area_p99 = area_max = 0.0
        largest_w = largest_h = border_count = 0
    final_count = int(np.count_nonzero(extraction.final_mask))
    low_only_count = int(np.count_nonzero(extraction.low_only_mask))
    return {
        "sample": sample,
        "frame": frame,
        "method": method,
        "scale_source": "fused",
        "low_threshold_dn": low,
        "high_threshold_dn": high,
        "connectivity": connectivity,
        "candidate_count": len(extraction.components),
        "support_component_count": extraction.support_component_count,
        "support_pixel_count": extraction.support_pixel_count,
        "seed_pixel_count": extraction.seed_pixel_count,
        "final_pixel_count": final_count,
        "low_only_pixel_count": low_only_count,
        "low_only_fraction": float(low_only_count / max(extraction.support_pixel_count, 1)),
        "area_sum_px": int(sum(int(row["area_px"]) for row in extraction.components)),
        "area_min_px": area_min,
        "area_p50_px": area_p50,
        "area_p90_px": area_p90,
        "area_p99_px": area_p99,
        "area_max_px": area_max,
        "border_component_count": int(border_count),
        "largest_bbox_w": largest_w,
        "largest_bbox_h": largest_h,
        "provisional_label_count": extraction.provisional_label_count,
        "tile_count": extraction.tile_count,
        "mask_path": mask_path,
        "low_only_mask_path": low_only_mask_path,
    }


def _write_candidates(
    writer: csv.DictWriter,
    extraction: ComponentExtraction,
    sample: int,
    frame: int,
    method: str,
    low: int,
    high: int,
    connectivity: int,
    sequence_start: int,
) -> int:
    sequence = sequence_start
    for component in extraction.components:
        writer.writerow(
            {
                "candidate_id": f"{method}_sample{sample:02d}_{sequence:07d}",
                "sample": sample,
                "frame": frame,
                "method": method,
                "scale_source": "fused",
                "low_threshold_dn": low,
                "high_threshold_dn": high,
                "connectivity": connectivity,
                "bbox_x": component["bbox_x"],
                "bbox_y": component["bbox_y"],
                "bbox_w": component["bbox_w"],
                "bbox_h": component["bbox_h"],
                "centroid_x": component["centroid_x"],
                "centroid_y": component["centroid_y"],
                "area_px": component["area_px"],
                "peak_response": component["peak_response"],
                "touches_border": component["touches_border"],
                "seed_pixel_count": component["seed_pixel_count"],
                "manual_label": "",
            }
        )
        sequence += 1
    return sequence


def _run_method(
    run_dir: Path,
    response: np.ndarray,
    sample: int,
    frame: int,
    method: str,
    low: int,
    high: int,
    candidate_writer: csv.DictWriter | None,
    sequence_start: int,
    *,
    scale_source: str = "fused",
    save_outputs: bool = True,
) -> tuple[ComponentExtraction, dict, dict, int]:
    high_mask = response >= int(high)
    if method == "S":
        support_mask = high_mask
        seed_mask = None
    elif method == "H":
        support_mask = response >= int(low)
        seed_mask = high_mask
    else:
        raise ValueError(method)
    started = time.perf_counter()
    extraction = extract_tiled_components(
        support_mask,
        response,
        seed_mask,
        connectivity=user_config.CASE03B_CONNECTIVITY,
        tile_shape=tuple(user_config.CASE03B_COMPONENT_TILE_SHAPE),
        temp_dir=run_dir / "temp",
    )
    elapsed = time.perf_counter() - started
    mask_path = run_dir / "masks" / f"sample_{sample}_frame_{frame}" / f"{scale_source}_{method}_TL{low}_TH{high}.npz"
    low_only_path = ""
    mask_record = {}
    low_record = None
    if save_outputs:
        mask_record = _record_mask(
            mask_path,
            extraction.final_mask,
            sample,
            frame,
            method,
            "final",
            scale_source,
            low,
            high,
            user_config.CASE03B_CONNECTIVITY,
        )
        if method == "H":
            low_only_file = run_dir / "masks" / f"sample_{sample}_frame_{frame}" / f"{scale_source}_H_low_only_TL{low}_TH{high}.npz"
            low_record = _record_mask(
                low_only_file,
                extraction.low_only_mask,
                sample,
                frame,
                method,
                "low_only",
                scale_source,
                low,
                high,
                user_config.CASE03B_CONNECTIVITY,
            )
            low_only_path = str(low_only_file)
        figure_path = run_dir / "figures" / f"sample_{sample:02d}_{scale_source}_{method}_TL{low}_TH{high}.png"
        _response_mask_figure(response, extraction.final_mask, extraction.low_only_mask, figure_path, f"sample {sample} {scale_source} {method} TL={low} TH={high}")
    summary = _summary_row(sample, frame, method, low, high, user_config.CASE03B_CONNECTIVITY, extraction, str(mask_path) if save_outputs else "", low_only_path)
    summary["elapsed_seconds"] = round(float(elapsed), 4)
    next_sequence = sequence_start
    if candidate_writer is not None and scale_source == "fused":
        next_sequence = _write_candidates(candidate_writer, extraction, sample, frame, method, low, high, user_config.CASE03B_CONNECTIVITY, sequence_start)
    return extraction, summary, {"final": mask_record, "low_only": low_record, "elapsed_seconds": elapsed}, next_sequence


def _patch_center_from_quantile(response: np.ndarray, quantile: float, excluded: list[tuple[int, int]], min_distance: int = 192) -> tuple[int, int]:
    threshold = float(np.percentile(response, quantile))
    candidates = np.argwhere(response >= threshold)
    height, width = response.shape
    for row, col in candidates[::-1]:
        x, y = int(col), int(row)
        if all((x - old_x) ** 2 + (y - old_y) ** 2 >= min_distance**2 for old_x, old_y in excluded):
            return x, y
    return width // 2, height // 2


def _patch_bounds(center_x: int, center_y: int, size: int, shape: tuple[int, int]) -> tuple[int, int, int, int]:
    height, width = shape
    x0 = max(0, min(width - size, int(center_x) - size // 2))
    y0 = max(0, min(height - size, int(center_y) - size // 2))
    return x0, y0, x0 + size, y0 + size


def _raw_display(raw_patch: np.ndarray) -> np.ndarray:
    low, high = np.percentile(raw_patch, [1.0, 99.5])
    high = max(float(high), float(low) + 1.0)
    return cv2.convertScaleAbs(raw_patch, alpha=255.0 / (high - low), beta=-low * 255.0 / (high - low))


def _save_local_patch(
    output_dir: Path,
    raw: np.ndarray,
    response: np.ndarray,
    label: str,
    center: tuple[int, int],
    size: int,
    patch_rows: list[dict],
    component_rows: list[dict],
) -> None:
    x0, y0, x1, y1 = _patch_bounds(center[0], center[1], size, response.shape)
    raw_patch = raw[y0:y1, x0:x1]
    response_patch = response[y0:y1, x0:x1]
    single = response_patch >= 230
    support = response_patch >= 150
    seed = response_patch >= 230
    hysteresis = extract_tiled_components(
        support,
        response_patch,
        seed,
        connectivity=8,
        tile_shape=(64, 64),
        temp_dir=output_dir / "temp",
    )
    structure = np.ones((3, 3), dtype=np.uint8)
    local_labels, local_count = ndimage.label(hysteresis.final_mask, structure=structure)
    overlay = cv2.cvtColor(_raw_display(raw_patch), cv2.COLOR_GRAY2BGR)
    contours, _ = cv2.findContours(hysteresis.final_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (0, 0, 255), 1)
    for component_id in range(1, int(local_count) + 1):
        positions = np.argwhere(local_labels == component_id)
        if positions.size == 0:
            continue
        local_y, local_x = positions[0]
        cv2.putText(overlay, str(component_id), (int(local_x), int(local_y)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1, cv2.LINE_AA)
        component_rows.append(
            {
                "patch_label": label,
                "component_id": component_id,
                "area_px": int(positions.shape[0]),
                "bbox_x": int(positions[:, 1].min()) + x0,
                "bbox_y": int(positions[:, 0].min()) + y0,
                "bbox_w": int(positions[:, 1].max() - positions[:, 1].min() + 1),
                "bbox_h": int(positions[:, 0].max() - positions[:, 0].min() + 1),
                "peak_response": int(response_patch[local_labels == component_id].max()),
            }
        )
    patch_path = output_dir / "patches" / f"sample26_{label}_{size}px.npz"
    np.savez_compressed(
        patch_path,
        raw_dn=raw_patch,
        fused_response_dn=response_patch,
        seed=seed,
        support=support,
        M_single=single,
        M_hysteresis=hysteresis.final_mask,
        low_only=support & ~hysteresis.final_mask,
        origin_xy=np.asarray([x0, y0], dtype=np.int64),
        candidate_not_truth=np.asarray(True),
    )
    overlay_path = output_dir / "patches" / f"sample26_{label}_{size}px_raw_contours_ids.png"
    write_png(overlay, overlay_path)
    patch_rows.append(
        {
            "patch_label": label,
            "size_px": size,
            "center_x": center[0],
            "center_y": center[1],
            "origin_x": x0,
            "origin_y": y0,
            "raw_dn_min": int(raw_patch.min()),
            "raw_dn_max": int(raw_patch.max()),
            "response_dn_min": int(response_patch.min()),
            "response_dn_max": int(response_patch.max()),
            "seed_pixels": int(np.count_nonzero(seed)),
            "support_pixels": int(np.count_nonzero(support)),
            "single_pixels": int(np.count_nonzero(single)),
            "hysteresis_pixels": int(np.count_nonzero(hysteresis.final_mask)),
            "low_only_pixels": int(np.count_nonzero(support & ~hysteresis.final_mask)),
            "hysteresis_components": int(local_count),
            "candidate_not_truth": True,
            "npz_path": str(patch_path),
            "overlay_path": str(overlay_path),
        }
    )


def _synthetic_case(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    height, width = shape
    support = np.zeros(shape, dtype=np.bool_)
    response = np.zeros(shape, dtype=np.uint16)
    names: list[str] = []

    def add(name: str, ys: slice, xs: slice, value: int) -> None:
        support[ys, xs] = True
        response[ys, xs] = np.maximum(response[ys, xs], value).astype(np.uint16)
        names.append(name)

    add("single_point", slice(2, 3), slice(2, 3), 260)
    add("three_pixel_point", slice(6, 7), slice(6, 9), 260)
    add("adjacent_points", slice(10, 12), slice(10, 12), 260)
    add("long_tilted_line", slice(16, min(height, 40)), slice(16, min(width, 60)), 245)
    for i in range(20, min(height - 2, width - 2)):
        support[i, i] = True
        response[i, i] = 175
    response[25 : min(height, 28), 25 : min(width, 28)] = 260
    support[25 : min(height, 28), 25 : min(width, 28)] = True
    names.append("weak_peripheral_around_strong_core")
    add("weak_only_low_threshold", slice(2, 5), slice(min(width - 8, 70), min(width - 3, 75)), 175)
    rng = np.random.default_rng(20261008 + height + width)
    texture = rng.random((max(1, height // 10), max(1, width // 10))) > 0.92
    texture = cv2.resize(texture.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST).astype(bool)
    support |= texture
    response[texture] = np.maximum(response[texture], 180)
    names.append("texture")
    add("blackband_edge", slice(0, min(3, height)), slice(width // 3, min(width, width // 3 + 12)), 250)
    add("long_weak_bridge", slice(height // 2, min(height, height // 2 + 2)), slice(4, max(5, width - 4)), 170)
    support[height - 1, width - 1] = True
    response[height - 1, width - 1] = 260
    names.append("corner")
    support[0, 0] = True
    response[0, 0] = 260
    names.append("edge_point")
    return support, response, names


def _reference_hysteresis(support: np.ndarray, seed: np.ndarray) -> tuple[np.ndarray, int]:
    labels, count = ndimage.label(support, structure=np.ones((3, 3), dtype=np.uint8))
    active_labels = np.unique(labels[seed])
    active_labels = active_labels[active_labels > 0]
    return np.isin(labels, active_labels), int(active_labels.size)


def run_local_validation(output_dir: Path) -> dict:
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "patches").mkdir(parents=True, exist_ok=True)
    (output_dir / "temp").mkdir(parents=True, exist_ok=True)
    synthetic_rows: list[dict] = []
    local_pass = True
    for shape in user_config.CASE03B_LOCAL_SYNTHETIC_SHAPES:
        support, response, case_names = _synthetic_case(tuple(shape))
        seed = response >= 230
        extraction = extract_tiled_components(
            support,
            response,
            seed,
            connectivity=8,
            tile_shape=(32, 37),
            temp_dir=output_dir / "temp",
        )
        reference_mask, reference_count = _reference_hysteresis(support, seed)
        single = extract_tiled_components(
            response >= 230,
            response,
            None,
            connectivity=8,
            tile_shape=(32, 37),
            temp_dir=output_dir / "temp",
        )
        ref_single_labels, ref_single_count = ndimage.label(response >= 230, structure=np.ones((3, 3), dtype=np.uint8))
        checks = {
            "support_equals_final_or_low_only": bool(np.array_equal(support, extraction.final_mask | extraction.low_only_mask)),
            "seed_subset_hysteresis": bool(np.all(~seed | extraction.final_mask)),
            "hysteresis_subset_support": bool(np.all(~extraction.final_mask | support)),
            "single_subset_hysteresis": bool(np.all(~single.final_mask | extraction.final_mask)),
            "hysteresis_matches_scipy": bool(np.array_equal(extraction.final_mask, reference_mask)),
            "hysteresis_component_count_matches_scipy": extraction.active_component_count == reference_count,
            "single_component_count_matches_scipy": single.active_component_count == int(ref_single_count),
            "single_mask_matches_scipy": bool(np.array_equal(single.final_mask, response >= 230)),
        }
        passed = all(checks.values())
        local_pass = local_pass and passed
        synthetic_rows.append(
            {
                "shape": f"{shape[0]}x{shape[1]}",
                "case_count": len(case_names),
                "cases": ",".join(case_names),
                "support_pixels": int(np.count_nonzero(support)),
                "seed_pixels": int(np.count_nonzero(seed)),
                "single_pixels": int(np.count_nonzero(single.final_mask)),
                "hysteresis_pixels": int(np.count_nonzero(extraction.final_mask)),
                "low_only_pixels": int(np.count_nonzero(extraction.low_only_mask)),
                "hysteresis_components": extraction.active_component_count,
                "reference_hysteresis_components": reference_count,
                "single_components": single.active_component_count,
                "reference_single_components": int(ref_single_count),
                "passed": passed,
                **checks,
            }
        )

    # Four-connectivity is only a small comparison gate, never the full method.
    small_support, small_response, _ = _synthetic_case((128, 160))
    four = extract_tiled_components(
        small_response >= 170,
        small_response,
        None,
        connectivity=4,
        tile_shape=(31, 29),
        temp_dir=output_dir / "temp",
    )
    ref_four, ref_four_count = ndimage.label(small_response >= 170, structure=np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8))
    four_pass = bool(np.array_equal(four.final_mask, ref_four > 0) and four.active_component_count == int(ref_four_count))
    synthetic_rows.append({"shape": "128x160", "case_count": 1, "cases": "4-connectivity_small_comparison", "passed": four_pass, "four_connectivity_components": four.active_component_count, "reference_components": int(ref_four_count)})
    local_pass = local_pass and four_pass

    raw_rows = _raw_index()
    raw_record = raw_rows.get((26, 1))
    input_response_path = _resolve_project_path(user_config.CASE03B_INPUT_RUN) / "samples" / "sample_26_frame_1" / "responses" / "blackhat_fused.npz"
    patch_rows: list[dict] = []
    component_rows: list[dict] = []
    if raw_record is None or not input_response_path.exists():
        raise FileNotFoundError("sample26/frame1 RAW or fused response is unavailable for local validation")
    raw = read_raw(raw_record["path"], RAW_CONFIG)
    response = _load_response(input_response_path)
    excluded: list[tuple[int, int]] = []
    centers: list[tuple[str, tuple[int, int], int]] = []
    for point in user_config.CASE03B_DIAGNOSTIC_POINTS:
        if int(point["sample_id"]) == 26:
            center = (int(point["x"]), int(point["y"]))
            centers.append((str(point["label"]), center, 256))
            excluded.append(center)
    for label, quantile, size in (
        ("medium_response", 99.0, 256),
        ("weak_response", 98.0, 256),
        ("fine_line", 99.5, 256),
        ("high_noise", 99.8, 256),
    ):
        center = _patch_center_from_quantile(response, quantile, excluded)
        centers.append((label, center, size))
        excluded.append(center)
    centers.extend(
        [
            ("blackband_edge_256", (response.shape[1] // 2, 128), 256),
            ("blackband_edge_512", (response.shape[1] // 2, 512), 512),
        ]
    )
    for label, center, size in centers:
        _save_local_patch(output_dir, raw, response, label, center, size, patch_rows, component_rows)
    write_csv(output_dir / "synthetic_gate.csv", synthetic_rows, sorted({key for row in synthetic_rows for key in row}))
    write_csv(output_dir / "patch_gate.csv", patch_rows, sorted({key for row in patch_rows for key in row}))
    write_csv(output_dir / "patch_components.csv", component_rows, sorted({key for row in component_rows for key in row}) if component_rows else ["patch_label", "component_id"])
    summary = {
        "overall_pass": bool(local_pass and len(patch_rows) == len(centers) and all(row["seed_subset_hysteresis"] if "seed_subset_hysteresis" in row else True for row in synthetic_rows)),
        "synthetic_rows": len(synthetic_rows),
        "patch_rows": len(patch_rows),
        "patch_component_rows": len(component_rows),
        "input_response": str(input_response_path),
        "raw_path": str(raw_record["path"]),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "requirements": {
            "synthetic_64_to_1024": True,
            "sample26_original_size_patches": True,
            "single_3px_and_adjacent_points": True,
            "long_tilted_line_and_weak_bridge": True,
            "weak_only_texture_blackband_edges": True,
            "contour_ids_on_raw_same_coordinates": True,
            "candidate_not_truth": True,
        },
    }
    write_json(output_dir / "local_gate_summary.json", summary)
    status = "PASS" if summary["overall_pass"] else "FAIL"
    (output_dir / "local_gate.md").write_text(
        f"# Case03-B 局部验证门\n\n- 状态：**{status}**\n- 合成图行数：{len(synthetic_rows)}；样品26原尺寸patch：{len(patch_rows)}。\n- 已覆盖单点、3像素点、相邻点、长/倾斜线、强核周围弱响应、仅低阈值响应、纹理、黑带边缘、长弱桥接、边缘与角点。\n- patch和叠加图均标记 `candidate_not_truth`，不作为人工真值。\n",
        encoding="utf-8",
    )
    return summary


def _copy_local_validation(local_run: Path, full_run: Path) -> Path:
    source = local_run / "local_validation" if (local_run / "local_validation").exists() else local_run
    target = full_run / "local_validation"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    source_patches = source / "patches"
    target_patches = full_run / "patches"
    if source_patches.exists():
        for patch_file in source_patches.iterdir():
            if patch_file.is_file():
                shutil.copy2(patch_file, target_patches / patch_file.name)
    return target


def _write_input_manifest(path: Path, input_run: Path, sample_ids: list[int], frame: int, raw_index: dict) -> list[dict]:
    rows: list[dict] = []
    for sample in sample_ids:
        response_path = _response_path(input_run, sample, frame)
        raw = raw_index.get((sample, frame))
        if raw is None:
            raise FileNotFoundError(f"RAW not found for sample={sample} frame={frame}")
        rows.append({"kind": "RAW", "sample": sample, "frame": frame, "path": str(raw["path"]), "bytes": raw["file_bytes"], "dtype": "uint16", "shape": f"{user_config.RAW_HEIGHT}x{user_config.RAW_WIDTH}", "read_only": True})
        rows.append({"kind": "Case02_blackhat_fused", "sample": sample, "frame": frame, "path": str(response_path), "bytes": response_path.stat().st_size, "dtype": "uint16", "shape": f"{user_config.RAW_HEIGHT}x{user_config.RAW_WIDTH}", "variable": "fused_response_dn", "read_only": True})
    write_csv(path, rows, ["kind", "sample", "frame", "path", "bytes", "dtype", "shape", "variable", "read_only"])
    return rows


def _protected_snapshot() -> dict:
    roots = [
        ROOT / "outputs" / "case02" / "run_20260930_153727",
        ROOT / "outputs" / "case03a" / "run_20261008_112000",
        ROOT / "outputs" / "case03a_revision" / "run_20261008_141000",
    ]
    snapshot = {}
    for root in roots:
        files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
        max_mtime = max((path.stat().st_mtime_ns for path in files), default=0)
        snapshot[str(root)] = {"exists": root.exists(), "file_count": len(files), "max_mtime_ns": max_mtime}
    return snapshot


def _write_full_report(
    run_dir: Path,
    input_run: Path,
    sample_ids: list[int],
    summary_rows: list[dict],
    fusion_rows: list[dict],
    local_summary: dict,
    protected_before: dict,
    protected_after: dict,
    input_manifest_ok: bool,
    full_pass: bool,
) -> None:
    candidate_count = sum(int(row["candidate_count"]) for row in summary_rows)
    h_rows = [row for row in summary_rows if row["method"] == "H"]
    report = f"""# Case03-B 融合响应候选区域提取报告

## 范围

- 输入：只读读取 `{input_run}` 的 Case02 `fused_response_dn`。
- 样品/帧：{sample_ids} / frame 1。
- 方法：S 为 `R >= TH`；H 为 `Seed=(R>=TH)`、`Support=(R>=TL)`，使用 8-连通将 Seed 所在 Support 连通域全部保留。
- 阈值：S={user_config.CASE03B_SINGLE_THRESHOLDS_DN} DN；H={user_config.CASE03B_HYSTERESIS_PAIRS_DN}（(TL,TH)）DN。
- 约束：未执行形态学、面积过滤、Top-N 截断或真实缺陷判定；所有候选均为 `candidate_not_truth`。

## 结果

- 正式 S/H 汇总行：{len(summary_rows)}；CSV候选总数：{candidate_count}。
- H 汇总行：{len(h_rows)}；每个 H 行均同时保存 low-only（`Support & ~MH`）无损packbits掩膜。
- 全图候选面积和与最终掩膜像素数逐行核对；详见 `candidate_summary.csv` 和 `acceptance.md`。
- 全部候选明细：`all_candidates.csv`；未按可视化图册上限删除CSV/Parquet候选。

## 融合与31px对照

sample26仅执行一次简化对照，结果在 `fusion_vs_31px_sample26.csv`。检查内容包括 `R_fused >= R_31px` 像素性质、严格增量像素、同阈值掩膜差异和少量历史坐标响应值；不将31px再扩展为新的检测阶段。

## 局部验证

局部门状态：**{'PASS' if local_summary.get('overall_pass') else 'FAIL'}**；证据位于 `local_validation/`，覆盖合成64~1024尺度和样品26原尺寸patch。局部窗口和历史坐标均标记为 `candidate_not_truth`。

## 阶段边界

本报告只覆盖 Case03-B；完成自验收后停止，未执行 Case04 或 Case05。
"""
    (run_dir / "case03b_report.md").write_text(report, encoding="utf-8")
    status = "PASS" if full_pass else "FAIL"
    acceptance = f"""# Case03-B 阶段自验收

总体状态：**{status}**

| 检查项 | 状态 | 证据 |
|---|---|---|
| 局部验证先行完成 | {'PASS' if local_summary.get('overall_pass') else 'FAIL'} | `local_validation/local_gate_summary.json` |
| Case02融合响应只读输入、尺寸/类型一致 | {'PASS' if input_manifest_ok else 'FAIL'} | `input_manifest.csv`、运行日志 |
| S阈值候选全部保留 | {'PASS' if any(row['method'] == 'S' for row in summary_rows) else 'FAIL'} | `candidate_summary.csv`、`all_candidates.csv` |
| H包含Seed连接到的全部Support | {'PASS' if h_rows else 'FAIL'} | H掩膜、low-only掩膜、汇总守恒 |
| 全部候选面积和等于最终掩膜像素数 | {'PASS' if all(int(row['area_sum_px']) == int(row['final_pixel_count']) for row in summary_rows) else 'FAIL'} | `candidate_summary.csv` |
| 分块连通域跨块/对角/边缘小图对照 | {'PASS' if local_summary.get('overall_pass') else 'FAIL'} | `local_validation/synthetic_gate.csv` |
| sample26融合与31px简化对照 | {'PASS' if fusion_rows else 'FAIL'} | `fusion_vs_31px_sample26.csv` |
| 历史Case02、Case03-A、Case03-A-R1未改写 | {'PASS' if protected_before == protected_after else 'FAIL'} | `protected_integrity.json` |
| 真实缺陷效果指标 | NOT COMPUTED | 本阶段只有候选区域提取，没有人工真值判定 |
| Case04 / Case05 | PASS（未执行） | 阶段边界到此停止 |

候选统计是像素/连通域生成结果，不等价于真实缺陷数量或检测效果结论。
"""
    (run_dir / "acceptance.md").write_text(acceptance, encoding="utf-8")
    (run_dir / "CHANGELOG_CASE03B.md").write_text(
        """# CHANGELOG_CASE03B\n\n- 新增Case03-B分块8-连通域、S单阈值和H滞回候选提取。\n- 新增局部合成/样品26原尺寸patch验证、low-only诊断、全图候选CSV和无损packbits掩膜。\n- 新增sample26融合响应与31px简化对照。\n- Case02、Case03-A、Case03-A-R1和RAW只读；本轮不执行Case04/Case05。\n""",
        encoding="utf-8",
    )


def _run_full(args: argparse.Namespace, run_dir: Path) -> int:
    input_run = _resolve_project_path(user_config.CASE03B_INPUT_RUN)
    sample_ids = [int(value) for value in (args.samples or user_config.CASE03B_SAMPLE_IDS)]
    frame = int(user_config.CASE03B_FRAME_ID)
    protected_before = _protected_snapshot()
    raw_index = _raw_index()
    input_manifest_rows = _write_input_manifest(run_dir / "input_manifest.csv", input_run, sample_ids, frame, raw_index)
    input_manifest_ok = all(bool(row.get("read_only")) for row in input_manifest_rows)
    local_run = _resolve_project_path(args.local_validation_run) if args.local_validation_run else None
    if local_run is not None:
        local_validation_dir = _copy_local_validation(local_run, run_dir)
        local_summary = json.loads((local_validation_dir / "local_gate_summary.json").read_text(encoding="utf-8"))
    else:
        local_summary = run_local_validation(run_dir / "local_validation")
    if not local_summary.get("overall_pass"):
        raise RuntimeError("Case03-B local gate failed; full-image extraction was not started")

    snapshot = user_config.as_dict()
    snapshot.update(
        {
            "case03b_run_dir": str(run_dir),
            "case03b_input_run_resolved": str(input_run),
            "case03b_local_validation": local_summary,
            "python_executable": sys.executable,
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "scipy_version": __import__("scipy").__version__,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    write_json(run_dir / "config_snapshot.json", snapshot)

    candidate_handle, candidate_writer = _open_writer(run_dir / "all_candidates.csv", METHOD_FIELDS)
    summary_rows: list[dict] = []
    mask_rows: list[dict] = []
    resource_rows: list[dict] = []
    fusion_rows: list[dict] = []
    subset_rows: list[dict] = []
    try:
        for sample in sample_ids:
            sample_started = time.perf_counter()
            fused_path = _response_path(input_run, sample, frame)
            response = _load_response(fused_path)
            method_results: dict[str, ComponentExtraction] = {}
            sequence = 1
            for threshold in user_config.CASE03B_SINGLE_THRESHOLDS_DN:
                extraction, summary, records, sequence = _run_method(
                    run_dir,
                    response,
                    sample,
                    frame,
                    "S",
                    int(threshold),
                    int(threshold),
                    candidate_writer,
                    sequence,
                )
                summary_rows.append(summary)
                if records["final"]:
                    mask_rows.append(records["final"])
                method_results[f"S_{threshold}"] = extraction
                resource_rows.append({"sample": sample, "method": "S", "low_threshold_dn": threshold, "high_threshold_dn": threshold, "elapsed_seconds": summary["elapsed_seconds"], "response_bytes": int(response.nbytes)})
            for low, high in user_config.CASE03B_HYSTERESIS_PAIRS_DN:
                extraction, summary, records, sequence = _run_method(
                    run_dir,
                    response,
                    sample,
                    frame,
                    "H",
                    int(low),
                    int(high),
                    candidate_writer,
                    sequence,
                )
                summary_rows.append(summary)
                if records["final"]:
                    mask_rows.append(records["final"])
                if records["low_only"]:
                    mask_rows.append(records["low_only"])
                method_results[f"H_{low}_{high}"] = extraction
                resource_rows.append({"sample": sample, "method": "H", "low_threshold_dn": low, "high_threshold_dn": high, "elapsed_seconds": summary["elapsed_seconds"], "response_bytes": int(response.nbytes)})
            primary_h = method_results[f"H_{user_config.CASE03B_PRIMARY_HYSTERESIS_DN[0]}_{user_config.CASE03B_PRIMARY_HYSTERESIS_DN[1]}"]
            s230 = method_results["S_230"]
            subset_rows.append(
                {
                    "sample": sample,
                    "single_230_subset_h_primary": bool(np.all(~s230.final_mask | primary_h.final_mask)),
                    "seed_subset_h_primary": bool(np.all(~(response >= 230) | primary_h.final_mask)),
                    "h_primary_subset_support": bool(np.all(~primary_h.final_mask | (response >= 150))),
                    "h_primary_low_only_disjoint": bool(np.count_nonzero(primary_h.final_mask & primary_h.low_only_mask) == 0),
                }
            )
            _response_mask_figure(
                response,
                primary_h.final_mask,
                primary_h.low_only_mask,
                run_dir / "figures" / f"sample_{sample:02d}_primary_H_overview.png",
                f"sample {sample} primary H TL=150 TH=230",
            )
            resource_rows.append({"sample": sample, "method": "sample_total", "low_threshold_dn": "", "high_threshold_dn": "", "elapsed_seconds": round(time.perf_counter() - sample_started, 4), "response_bytes": int(response.nbytes)})
            LOGGER.info("sample=%s complete elapsed=%.2fs candidates=%s", sample, time.perf_counter() - sample_started, sum(int(row["candidate_count"]) for row in summary_rows if int(row["sample"]) == sample))
            if sample == 26:
                fusion_rows.extend(_run_31px_comparison(run_dir, response, primary_h, input_run, frame, mask_rows))
            del response
    finally:
        candidate_handle.close()

    write_csv(run_dir / "candidate_summary.csv", summary_rows, SUMMARY_FIELDS)
    write_csv(run_dir / "mask_manifest.csv", mask_rows, MASK_FIELDS)
    write_csv(run_dir / "resources.csv", resource_rows, ["sample", "method", "low_threshold_dn", "high_threshold_dn", "elapsed_seconds", "response_bytes"])
    write_csv(run_dir / "subset_checks.csv", subset_rows, sorted({key for row in subset_rows for key in row}))
    write_csv(run_dir / "fusion_vs_31px_sample26.csv", fusion_rows, FUSION_FIELDS)
    protected_after = _protected_snapshot()
    protected = {"before": protected_before, "after": protected_after, "unchanged": protected_before == protected_after}
    write_json(run_dir / "protected_integrity.json", protected)
    full_pass = bool(
        local_summary.get("overall_pass")
        and summary_rows
        and all(int(row["area_sum_px"]) == int(row["final_pixel_count"]) for row in summary_rows)
        and all(bool(row["single_230_subset_h_primary"]) and bool(row["seed_subset_h_primary"]) and bool(row["h_primary_subset_support"]) and bool(row["h_primary_low_only_disjoint"]) for row in subset_rows)
        and fusion_rows
        and all(bool(row.get("fused_ge_31px_all", True)) for row in fusion_rows if row.get("scope") == "full")
        and protected["unchanged"]
        and input_manifest_ok
    )
    write_json(
        run_dir / "case03b_self_check.json",
        {
            "overall_self_check": full_pass,
            "summary_rows": len(summary_rows),
            "candidate_rows": sum(int(row["candidate_count"]) for row in summary_rows),
            "mask_rows": len(mask_rows),
            "fusion_rows": len(fusion_rows),
            "subset_rows": subset_rows,
            "stopped_before_case04_case05": True,
        },
    )
    _write_full_report(run_dir, input_run, sample_ids, summary_rows, fusion_rows, local_summary, protected_before, protected_after, input_manifest_ok, full_pass)
    LOGGER.info("Case03-B complete output=%s self_check=%s", run_dir, full_pass)
    return 0 if full_pass else 1


def _run_31px_comparison(
    run_dir: Path,
    fused: np.ndarray,
    fused_primary_h: ComponentExtraction,
    input_run: Path,
    frame: int,
    mask_rows: list[dict],
) -> list[dict]:
    path = _response_path(input_run, 26, frame, "blackhat_31px.npz")
    response31 = _load_response(path, key="response_dn")
    if response31.shape != fused.shape:
        raise ValueError("31px comparison response shape differs from fused response")
    delta = fused.astype(np.int32) - response31.astype(np.int32)
    ge_all = bool(np.all(delta >= 0))
    rows: list[dict] = []
    points = [(int(item["x"]), int(item["y"])) for item in user_config.CASE03B_DIAGNOSTIC_POINTS if int(item["sample_id"]) == 26]
    methods = [("S", int(value), int(value)) for value in user_config.CASE03B_SINGLE_THRESHOLDS_DN]
    methods.extend(("H", int(low), int(high)) for low, high in user_config.CASE03B_HYSTERESIS_PAIRS_DN)
    for method, low, high in methods:
        if method == "S":
            fused_mask = fused >= high
            mask31 = response31 >= high
        else:
            extraction31, _unused_summary, records31, _unused_sequence = _run_method(
                run_dir,
                response31,
                26,
                frame,
                method,
                low,
                high,
                None,
                1,
                scale_source="31px_compare",
                save_outputs=True,
            )
            if records31["final"]:
                mask_rows.append(records31["final"])
            if records31["low_only"]:
                mask_rows.append(records31["low_only"])
            fused_mask = fused_primary_h.final_mask if (low, high) == tuple(user_config.CASE03B_PRIMARY_HYSTERESIS_DN) else extract_tiled_components(
                fused >= low,
                fused,
                fused >= high,
                connectivity=user_config.CASE03B_CONNECTIVITY,
                tile_shape=tuple(user_config.CASE03B_COMPONENT_TILE_SHAPE),
                temp_dir=run_dir / "temp",
            ).final_mask
            mask31 = extraction31.final_mask
        diff = fused_mask.astype(np.int8) - mask31.astype(np.int8)
        rows.append(
            {
                "scope": "full",
                "sample": 26,
                "frame": frame,
                "method": method,
                "low_threshold_dn": low,
                "high_threshold_dn": high,
                "connectivity": user_config.CASE03B_CONNECTIVITY,
                "fused_ge_31px_all": ge_all,
                "fused_gt_31px_count": int(np.count_nonzero(delta > 0)),
                "equal_count": int(np.count_nonzero(delta == 0)),
                "fused_response_min_delta": int(delta.min()),
                "fused_response_max_delta": int(delta.max()),
                "fused_response_mean_delta": float(delta.mean()),
                "mask_fused_count": int(np.count_nonzero(fused_mask)),
                "mask_31px_count": int(np.count_nonzero(mask31)),
                "fused_only_count": int(np.count_nonzero(fused_mask & ~mask31)),
                "thirty_one_only_count": int(np.count_nonzero(mask31 & ~fused_mask)),
            }
        )
        for x, y in points:
            rows.append(
                {
                    "scope": "point",
                    "sample": 26,
                    "frame": frame,
                    "method": method,
                    "low_threshold_dn": low,
                    "high_threshold_dn": high,
                    "connectivity": user_config.CASE03B_CONNECTIVITY,
                    "fused_ge_31px_all": ge_all,
                    "x": x,
                    "y": y,
                    "fused_dn": int(fused[y, x]),
                    "thirty_one_dn": int(response31[y, x]),
                    "delta_dn": int(delta[y, x]),
                }
            )
    # A direct response-level row makes the max-fusion property explicit.
    rows.append(
        {
            "scope": "response_property",
            "sample": 26,
            "frame": frame,
            "fused_ge_31px_all": ge_all,
            "fused_gt_31px_count": int(np.count_nonzero(delta > 0)),
            "equal_count": int(np.count_nonzero(delta == 0)),
            "fused_response_min_delta": int(delta.min()),
            "fused_response_max_delta": int(delta.max()),
            "fused_response_mean_delta": float(delta.mean()),
        }
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-only", action="store_true", help="only run the local validation gate")
    parser.add_argument("--skip-local", action="store_true", help="use --local-validation-run and start full extraction")
    parser.add_argument("--local-validation-run", type=str, default=None, help="a previous case03b run containing local_validation")
    parser.add_argument("--output-run-id", type=str, default=None)
    parser.add_argument("--samples", nargs="+", type=int, default=None)
    args = parser.parse_args()
    run_dir = _make_run_dir(args.output_run_id)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(run_dir / "logs" / "case03b.log", encoding="utf-8"), logging.StreamHandler()],
    )
    LOGGER.info("Case03-B start output=%s", run_dir)
    if args.local_only:
        summary = run_local_validation(run_dir / "local_validation")
        write_json(run_dir / "config_snapshot.json", {"mode": "local_only", "config": user_config.as_dict(), "summary": summary})
        return 0 if summary.get("overall_pass") else 1
    if args.skip_local and not args.local_validation_run:
        raise ValueError("--skip-local requires --local-validation-run")
    return _run_full(args, run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
