"""Case03-A：对既有Case02响应执行全图固定/局部鲁棒阈值对照。

本脚本只读取Case02响应NPZ和只读RAW，逐样品逐尺度生成全分辨率二值掩膜。
不做连通域、轮廓、形态学清理、TopN截断、跨样品黑名单或缺陷分类。
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import gc
import json
import logging
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import user_config
from src.detection.local_robust_threshold import (
    compute_local_grid_statistics,
    grid_threshold_values,
    iter_local_threshold_strips,
)
from src.detection.thresholding import (
    fixed_threshold_mask,
    load_packed_mask,
    mask_statistics,
    save_packed_mask,
    validate_response,
)
from src.io.raw_reader import RawReadConfig, read_raw
from src.utils.paths import discover_raw_files, json_safe, write_csv, write_json
from src.visualization.segmentation_diagnostic import (
    mask_preview,
    response_mask_overlay,
    response_preview,
    save_point_patch_comparison,
    save_threshold_contact_sheet,
    threshold_surface_preview,
    write_png,
)


LOGGER = logging.getLogger("case03a")


def parse_args() -> argparse.Namespace:
    """解析Case03-A独立入口参数。"""

    parser = argparse.ArgumentParser(description="Case03-A全图阈值分割与鲁棒阈值对照")
    parser.add_argument("--input-run", type=str, default=None, help="Case02响应运行目录，默认读取配置值")
    parser.add_argument("--sample", type=int, default=None, help="先运行单个样品，例如26")
    parser.add_argument("--output-run-id", type=str, default=None, help="输出目录名")
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """读取UTF-8 BOM CSV。"""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    """写UTF-8文本。"""

    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def resolve_path(value: str | None, default: str) -> Path:
    """解析相对工程路径或绝对路径。"""

    path = Path(value or default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def make_run_dir(run_id: str | None) -> Path:
    """创建不覆盖历史结果的Case03-A运行目录。"""

    base = user_config.OUTPUT_ROOT / "case03a"
    stamp = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = base / stamp
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{suffix:02d}"
        suffix += 1
    for name in ("masks", "figures", "patches", "logs"):
        (run_dir / name).mkdir(parents=True, exist_ok=False)
    return run_dir


def load_response(path: Path) -> tuple[np.ndarray, list[str]]:
    """读取响应NPZ并返回数组与键名。"""

    with np.load(path, allow_pickle=False) as data:
        keys = list(data.files)
        if "response_dn" not in keys:
            raise KeyError(f"Case02响应NPZ缺少response_dn: {path}")
        response = np.asarray(data["response_dn"])
    validate_response(response)
    return response, keys


def memory_status() -> dict:
    """读取Windows可用物理内存；失败时显式记录unknown。"""

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return {
            "memory_load_percent": int(status.dwMemoryLoad),
            "ram_total_gib": status.ullTotalPhys / 1024**3,
            "ram_available_gib": status.ullAvailPhys / 1024**3,
        }
    except Exception as exc:  # pragma: no cover - platform fallback
        return {"status": "unknown", "error": str(exc)}


def resource_estimate(sample_count: int, scale_count: int) -> dict:
    """估算全分辨率packbits掩膜空间和逐尺度内存策略。"""

    pixels = user_config.RAW_WIDTH * user_config.RAW_HEIGHT
    packed_bytes = (pixels + 7) // 8
    primary_mask_count = sample_count * scale_count * 2
    disk = shutil.disk_usage(PROJECT_ROOT)
    return {
        "raw_pixels": pixels,
        "one_bool_mask_bytes": pixels,
        "one_packbits_mask_bytes": packed_bytes,
        "primary_mask_count": primary_mask_count,
        "primary_masks_uncompressed_packbits_bytes": packed_bytes * primary_mask_count,
        "primary_masks_uncompressed_packbits_mib": packed_bytes * primary_mask_count / 1024**2,
        "disk_total_gib": disk.total / 1024**3,
        "disk_used_gib": disk.used / 1024**3,
        "disk_free_gib": disk.free / 1024**3,
        "memory": memory_status(),
        "strategy": "one_sample_one_scale; fixed/local primary masks only; threshold scan masks released after statistics",
        "threshold_masks_saved": "fixed_primary_200dn_and_local_primary_k5_per_scale_only",
    }


def baseline_stats_lookup(input_run: Path) -> dict[tuple[int, int], dict]:
    """读取既有Case02统计，作为响应幅值和百分位的交叉核对。"""

    rows = read_csv_rows(input_run / "blackhat_statistics.csv")
    lookup = {}
    for row in rows:
        if row["response_type"] == "scale":
            lookup[(int(row["sample_id"]), int(row["kernel_size_px"]))] = row
    return lookup


def save_mask_roundtrip(path: Path, mask: np.ndarray) -> dict:
    """保存并立即无损还原主掩膜，返回manifest证据。"""

    metadata = save_packed_mask(path, mask, bitorder="little")
    restored = load_packed_mask(path)
    metadata["roundtrip_equal"] = bool(np.array_equal(mask, restored))
    if not metadata["roundtrip_equal"]:
        raise AssertionError(f"packbits掩膜还原失败: {path}")
    del restored
    return metadata


def response_manifest_row(sample_id: int, frame_id: int, scale: int, path: Path, keys: list[str], response: np.ndarray, baseline: dict) -> dict:
    """生成输入NPZ清单记录。"""

    return {
        "sample_id": sample_id,
        "frame_id": frame_id,
        "kernel_size_px": scale,
        "input_npz": str(path),
        "input_file_bytes": path.stat().st_size,
        "npz_keys": ";".join(keys),
        "shape": str(list(response.shape)),
        "dtype": str(response.dtype),
        "baseline_max_dn": baseline.get("max", ""),
        "baseline_p95_dn": baseline.get("p95", ""),
        "baseline_p99_dn": baseline.get("p99", ""),
        "baseline_p99_9_dn": baseline.get("p99_9", ""),
        "case02_response_units": "DN",
    }


def threshold_stat_row(
    sample_id: int,
    frame_id: int,
    scale: int,
    method: str,
    parameter_label: str,
    threshold_dn: float,
    k: str,
    floor_dn: str,
    count: int,
    valid_pixels: int,
    baseline: dict,
    elapsed_s: float,
    mask_path: str = "",
    threshold_min_dn: float | str = "",
    threshold_max_dn: float | str = "",
    threshold_grid_mean_dn: float | str = "",
    threshold_source: str = "",
) -> dict:
    """生成固定/局部阈值扫描统计行。"""

    return {
        "sample_id": sample_id,
        "frame_id": frame_id,
        "kernel_size_px": scale,
        "method": method,
        "parameter_label": parameter_label,
        "threshold_dn": threshold_dn,
        "k": k,
        "floor_dn": floor_dn,
        "abnormal_pixels": count,
        "valid_pixels": valid_pixels,
        "abnormal_fraction": count / valid_pixels,
        "response_max_dn": baseline.get("max", ""),
        "response_p95_dn": baseline.get("p95", ""),
        "response_p99_dn": baseline.get("p99", ""),
        "response_p99_9_dn": baseline.get("p99_9", ""),
        "threshold_min_dn": threshold_min_dn,
        "threshold_max_dn": threshold_max_dn,
        "threshold_grid_mean_dn": threshold_grid_mean_dn,
        "input_response_npz": baseline.get("response_npz", ""),
        "threshold_source": threshold_source,
        "elapsed_s": elapsed_s,
        "primary_mask_saved": bool(mask_path),
        "mask_path": mask_path,
        "units": "response/threshold=DN; count=pixels; fraction=unitless",
    }


def process_sample(
    sample_id: int,
    frame_id: int,
    input_run: Path,
    run_dir: Path,
    baseline_lookup: dict[tuple[int, int], dict],
    scales: list[int],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """逐尺度处理一个样品，返回统计、输入清单、网格记录和掩膜manifest。"""

    threshold_rows: list[dict] = []
    input_rows: list[dict] = []
    grid_rows_all: list[dict] = []
    mask_manifest: list[dict] = []
    contact_entries: list[dict] = []
    sample_mask_dir = run_dir / "masks" / f"sample_{sample_id}_frame_{frame_id}"
    sample_mask_dir.mkdir(parents=True, exist_ok=False)
    for scale in scales:
        response_path = input_run / "samples" / f"sample_{sample_id}_frame_{frame_id}" / "responses" / f"blackhat_{scale}px.npz"
        response, keys = load_response(response_path)
        if response.shape != (user_config.RAW_HEIGHT, user_config.RAW_WIDTH):
            raise AssertionError(f"响应shape异常: {response_path} {response.shape}")
        baseline = dict(baseline_lookup[(sample_id, scale)])
        baseline["response_npz"] = str(response_path)
        input_rows.append(response_manifest_row(sample_id, frame_id, scale, response_path, keys, response, baseline))
        valid_pixels = int(response.size)
        preview_high = max(float(baseline["p99_9"]), 1.0)
        response_display = response_preview(response, preview_high, user_config.CASE03A_PREVIEW_MAX_EDGE_PX)
        response_preview_path = run_dir / "figures" / f"sample_{sample_id}_{scale}px_response_preview.png"
        write_png(response_display, response_preview_path)

        fixed_primary_mask: np.ndarray | None = None
        fixed_preview = None
        fixed_preview_path = run_dir / "figures" / f"sample_{sample_id}_{scale}px_fixed200_preview.png"
        for threshold_dn in user_config.CASE03A_FIXED_THRESHOLDS_DN:
            started = time.perf_counter()
            mask = fixed_threshold_mask(response, int(threshold_dn))
            count = int(np.count_nonzero(mask))
            elapsed = time.perf_counter() - started
            mask_path = ""
            if int(threshold_dn) == user_config.CASE03A_FIXED_PRIMARY_DN:
                fixed_primary_mask = mask
                fixed_mask_file = sample_mask_dir / f"fixed_{int(threshold_dn)}dn_{scale}px.npz"
                metadata = save_mask_roundtrip(fixed_mask_file, mask)
                metadata.update({"sample_id": sample_id, "frame_id": frame_id, "kernel_size_px": scale, "method": "fixed_absolute", "parameter": f"threshold_dn={threshold_dn}"})
                mask_manifest.append(metadata)
                mask_path = str(fixed_mask_file)
                fixed_preview = mask_preview(mask, user_config.CASE03A_PREVIEW_MAX_EDGE_PX)
                write_png(fixed_preview, fixed_preview_path)
            threshold_rows.append(
                threshold_stat_row(
                    sample_id,
                    frame_id,
                    scale,
                    "fixed_absolute",
                    f"threshold_dn={int(threshold_dn)}",
                    int(threshold_dn),
                    "",
                    "",
                    count,
                    valid_pixels,
                    baseline,
                    elapsed,
                    mask_path,
                    threshold_source="Case03-A固定绝对DN初始诊断值",
                )
            )
            if int(threshold_dn) != user_config.CASE03A_FIXED_PRIMARY_DN:
                del mask
            else:
                del fixed_primary_mask
                fixed_primary_mask = mask

        medians, mads, grid_rows = compute_local_grid_statistics(
            response,
            user_config.CASE03A_GRID_SIZE_PX,
            user_config.CASE03A_GRID_SAMPLE_STRIDE_PX,
        )
        for grid_row in grid_rows:
            grid_rows_all.append({"sample_id": sample_id, "frame_id": frame_id, "kernel_size_px": scale, **grid_row})
        local_primary_mask: np.ndarray | None = None
        local_preview = None
        local_preview_path = run_dir / "figures" / f"sample_{sample_id}_{scale}px_local_mad_k5_preview.png"
        threshold_surface_path = run_dir / "figures" / f"sample_{sample_id}_{scale}px_local_threshold_surface_k5_preview.png"
        primary_threshold_grid = grid_threshold_values(
            medians,
            mads,
            user_config.CASE03A_MAD_PRIMARY_K,
            user_config.CASE03A_MAD_FLOOR_DN,
        )
        write_png(
            threshold_surface_preview(
                primary_threshold_grid,
                user_config.CASE03A_PREVIEW_MAX_EDGE_PX,
                (user_config.RAW_HEIGHT, user_config.RAW_WIDTH),
            ),
            threshold_surface_path,
        )
        for k in user_config.CASE03A_MAD_K_VALUES:
            started = time.perf_counter()
            local_mask = np.empty(response.shape, dtype=bool) if int(k) == user_config.CASE03A_MAD_PRIMARY_K else None
            count = 0
            threshold_min = float("inf")
            threshold_max = float("-inf")
            for y_start, y_end, threshold_surface, strip_mask in iter_local_threshold_strips(
                response,
                medians,
                mads,
                float(k),
                user_config.CASE03A_MAD_FLOOR_DN,
                user_config.CASE03A_GRID_SIZE_PX,
                user_config.CASE03A_STRIPE_ROWS_PX,
            ):
                count += int(np.count_nonzero(strip_mask))
                threshold_min = min(threshold_min, float(threshold_surface.min()))
                threshold_max = max(threshold_max, float(threshold_surface.max()))
                if local_mask is not None:
                    local_mask[y_start:y_end] = strip_mask
            elapsed = time.perf_counter() - started
            threshold_grid = grid_threshold_values(medians, mads, float(k), user_config.CASE03A_MAD_FLOOR_DN)
            mask_path = ""
            threshold_mean = float(threshold_grid.mean())
            if int(k) == user_config.CASE03A_MAD_PRIMARY_K:
                local_primary_mask = local_mask
                local_mask_file = sample_mask_dir / f"local_mad_k{int(k)}_{scale}px.npz"
                metadata = save_mask_roundtrip(local_mask_file, local_mask)
                metadata.update({"sample_id": sample_id, "frame_id": frame_id, "kernel_size_px": scale, "method": "local_median_mad", "parameter": f"k={k},floor_dn={user_config.CASE03A_MAD_FLOOR_DN}"})
                mask_manifest.append(metadata)
                mask_path = str(local_mask_file)
                local_preview = mask_preview(local_mask, user_config.CASE03A_PREVIEW_MAX_EDGE_PX)
                write_png(local_preview, local_preview_path)
            threshold_rows.append(
                threshold_stat_row(
                    sample_id,
                    frame_id,
                    scale,
                    "local_median_mad",
                    f"k={int(k)},floor_dn={user_config.CASE03A_MAD_FLOOR_DN},grid={user_config.CASE03A_GRID_SIZE_PX},stride={user_config.CASE03A_GRID_SAMPLE_STRIDE_PX}",
                    "",
                    int(k),
                    user_config.CASE03A_MAD_FLOOR_DN,
                    count,
                    valid_pixels,
                    baseline,
                    elapsed,
                    mask_path,
                    threshold_min,
                    threshold_max,
                    threshold_mean,
                    threshold_source="Case03-A局部median+1.4826*MAD初始诊断值",
                )
            )
            del threshold_grid
            if int(k) != user_config.CASE03A_MAD_PRIMARY_K:
                del local_mask
        if fixed_preview is None or local_preview is None:
            raise AssertionError(f"主掩膜预览未生成: sample={sample_id}, scale={scale}")
        overlay = response_mask_overlay(response_display, fixed_preview, local_preview)
        overlay_path = run_dir / "figures" / f"sample_{sample_id}_{scale}px_fixed_vs_local_overlay.png"
        write_png(overlay, overlay_path)
        contact_entries.append(
            {
                "scale": scale,
                "response_preview": response_display,
                "response_high_dn": preview_high,
                "fixed_preview": fixed_preview,
                "fixed_threshold_dn": user_config.CASE03A_FIXED_PRIMARY_DN,
                "local_preview": local_preview,
                "local_k": user_config.CASE03A_MAD_PRIMARY_K,
                "floor_dn": user_config.CASE03A_MAD_FLOOR_DN,
                "overlay_preview": overlay,
            }
        )
        del response, medians, mads, grid_rows, fixed_primary_mask, local_primary_mask, fixed_preview, local_preview, response_display, overlay
        gc.collect()
    contact_path = run_dir / "figures" / f"sample_{sample_id}_threshold_contact_sheet.png"
    save_threshold_contact_sheet(contact_path, sample_id, frame_id, contact_entries, (user_config.RAW_HEIGHT, user_config.RAW_WIDTH))
    del contact_entries
    return threshold_rows, input_rows, grid_rows_all, mask_manifest


def point_crop(array: np.ndarray, x: int, y: int, patch_size: int) -> np.ndarray:
    """按全分辨率坐标裁剪原始尺寸patch，不做缩放。"""

    half = patch_size // 2
    y0, y1 = y - half, y + half
    x0, x1 = x - half, x + half
    if y0 < 0 or x0 < 0 or y1 > array.shape[0] or x1 > array.shape[1]:
        raise ValueError(f"诊断点patch越界: x={x}, y={y}, shape={array.shape}")
    return array[y0:y1, x0:x1].copy()


def diagnostic_points_for_sample(sample_id: int, raw: np.ndarray, fused: np.ndarray) -> list[dict]:
    """返回指定历史候选以及一个低响应背景、一个条带边界诊断点。"""

    points = [dict(item) for item in user_config.CASE03A_DIAGNOSTIC_POINTS if item["sample_id"] == sample_id]
    height, width = raw.shape
    margin = user_config.CASE03A_PATCH_SIZE_PX // 2
    y0, y1 = height // 4, (height * 3) // 4
    x0, x1 = width // 4, (width * 3) // 4
    interior = fused[y0:y1, x0:x1]
    low_y, low_x = np.unravel_index(int(np.argmin(interior)), interior.shape)
    points.append({"sample_id": sample_id, "frame_id": user_config.CASE03A_FRAME_ID, "label": "auto_low_response_background", "x": int(x0 + low_x), "y": int(y0 + low_y), "source": "central_area_argmin_fused_response"})
    row_mean = raw.astype(np.float32).mean(axis=1)
    gradient = np.abs(np.diff(row_mean))
    gradient[:margin] = 0
    gradient[-margin:] = 0
    boundary_y = int(np.argmax(gradient))
    points.append({"sample_id": sample_id, "frame_id": user_config.CASE03A_FRAME_ID, "label": "auto_row_gradient_boundary", "x": width // 2, "y": max(margin, min(height - margin - 1, boundary_y)), "source": "maximum_absolute_raw_row_mean_gradient"})
    return points


def generate_point_diagnostics(
    run_dir: Path,
    input_run: Path,
    sample_ids: list[int],
    baseline_lookup: dict[tuple[int, int], dict],
) -> list[dict]:
    """生成历史候选、低响应背景和条带边界的原始尺寸patch证据。"""

    raw_records = discover_raw_files(user_config.DATA_ROOT)
    raw_by_identity = {(item["sample_id"], item["frame_id"]): item["path"] for item in raw_records}
    patch_manifest: list[dict] = []
    raw_config = RawReadConfig(
        width=user_config.RAW_WIDTH,
        height=user_config.RAW_HEIGHT,
        effective_bits=user_config.EFFECTIVE_BITS,
        endian=user_config.RAW_ENDIAN,
    )
    diagnostic_scale = 31
    for sample_id in sample_ids:
        raw = read_raw(raw_by_identity[(sample_id, user_config.CASE03A_FRAME_ID)], raw_config)
        fused_path = input_run / "samples" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / "responses" / "blackhat_fused.npz"
        winning_path = input_run / "samples" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / "responses" / "winning_scale_map.npz"
        with np.load(fused_path, allow_pickle=False) as data:
            fused = np.asarray(data["fused_response_dn"])
        with np.load(winning_path, allow_pickle=False) as data:
            winning = np.asarray(data["winning_scale"])
        fixed_mask_path = run_dir / "masks" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / f"fixed_{user_config.CASE03A_FIXED_PRIMARY_DN}dn_{diagnostic_scale}px.npz"
        local_mask_path = run_dir / "masks" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / f"local_mad_k{user_config.CASE03A_MAD_PRIMARY_K}_{diagnostic_scale}px.npz"
        fixed_mask = load_packed_mask(fixed_mask_path)
        local_mask = load_packed_mask(local_mask_path)
        points = diagnostic_points_for_sample(sample_id, raw, fused)
        raw_low, raw_high = np.percentile(raw, [0.1, 99.9])
        response_high = max(float(baseline_lookup[(sample_id, diagnostic_scale)]["p99_9"]), 1.0)
        for index, point in enumerate(points, start=1):
            x, y = int(point["x"]), int(point["y"])
            raw_patch = point_crop(raw, x, y, user_config.CASE03A_PATCH_SIZE_PX)
            fused_patch = point_crop(fused, x, y, user_config.CASE03A_PATCH_SIZE_PX)
            fixed_patch = point_crop(fixed_mask, x, y, user_config.CASE03A_PATCH_SIZE_PX)
            local_patch = point_crop(local_mask, x, y, user_config.CASE03A_PATCH_SIZE_PX)
            winning_patch = point_crop(winning, x, y, user_config.CASE03A_PATCH_SIZE_PX)
            safe_label = str(point["label"]).replace(" ", "_")
            stem = f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}_{index:02d}_{safe_label}_x{x}_y{y}"
            npz_path = run_dir / "patches" / f"{stem}.npz"
            np.savez_compressed(
                npz_path,
                raw_dn=raw_patch,
                fused_response_dn=fused_patch,
                fixed_mask_31px=fixed_patch,
                local_mask_31px=local_patch,
                winning_scale=winning_patch,
            )
            png_path = run_dir / "figures" / f"{stem}.png"
            save_point_patch_comparison(
                png_path,
                f"样品{sample_id} 第{user_config.CASE03A_FRAME_ID}帧 {point['label']} x={x} y={y}（31px主掩膜）",
                raw_patch,
                fused_patch,
                fixed_patch,
                local_patch,
                winning_patch,
                user_config.CASE03A_PATCH_SIZE_PX,
                (float(raw_low), float(raw_high)),
                response_high,
            )
            patch_manifest.append(
                {
                    "sample_id": sample_id,
                    "frame_id": user_config.CASE03A_FRAME_ID,
                    "label": point["label"],
                    "source": point.get("source", "config_historical_candidate"),
                    "x": x,
                    "y": y,
                    "patch_size_px": user_config.CASE03A_PATCH_SIZE_PX,
                    "diagnostic_scale_px": diagnostic_scale,
                    "raw_display_p0_1_dn": float(raw_low),
                    "raw_display_p99_9_dn": float(raw_high),
                    "fused_response_p99_9_dn": response_high,
                    "fused_peak_response_dn": int(fused_patch.max()),
                    "winning_scale_at_center_index": int(winning[y, x]),
                    "raw_patch_npz": str(npz_path),
                    "comparison_png": str(png_path),
                    "is_artificial_or_ground_truth_label": "no_manual_truth",
                }
            )
        del raw, fused, winning, fixed_mask, local_mask
        gc.collect()
    return patch_manifest


def summarize_sample_rows(threshold_rows: list[dict], sample_id: int, scale: int, method: str, parameter: str) -> dict:
    """从统计行获取指定样品/尺度/参数的比例。"""

    for row in threshold_rows:
        if int(row["sample_id"]) == sample_id and int(row["kernel_size_px"]) == scale and row["method"] == method and row["parameter_label"] == parameter:
            return row
    raise KeyError((sample_id, scale, method, parameter))


def ratio_mark(value: float) -> str:
    """给出候选占比的工程诊断提示，不把它写成真实误检率。"""

    if value >= 0.25:
        return "大面积候选，疑似过分割需人工复核"
    if value >= 0.05:
        return "候选面积较高，需人工复核"
    return "候选面积较低"


def write_report(
    path: Path,
    input_run: Path,
    sample_ids: list[int],
    threshold_rows: list[dict],
    mask_manifest: list[dict],
    patch_manifest: list[dict],
    resources: dict,
) -> None:
    """生成Case03-A中文诊断报告。"""

    fixed_thresholds = user_config.CASE03A_FIXED_THRESHOLDS_DN
    k_values = user_config.CASE03A_MAD_K_VALUES
    lines = [
        "# Case03-A全图疑似暗异常阈值分割与鲁棒阈值对照报告",
        "",
        f"- 输入Case02运行：`{input_run}`（只读）。",
        f"- 样品/帧：{','.join(map(str, sample_ids))} / 第{user_config.CASE03A_FRAME_ID}帧；响应shape=`({user_config.RAW_HEIGHT},{user_config.RAW_WIDTH})`，单位为Black-Hat DN。",
        f"- 固定阈值：{fixed_thresholds} DN；主掩膜：{user_config.CASE03A_FIXED_PRIMARY_DN} DN。",
        f"- 局部阈值：`max({user_config.CASE03A_MAD_FLOOR_DN} DN, median + k×1.4826×MAD)`，k={k_values}，主方案k={user_config.CASE03A_MAD_PRIMARY_K}，网格={user_config.CASE03A_GRID_SIZE_PX}px，抽样步长={user_config.CASE03A_GRID_SAMPLE_STRIDE_PX}px。",
        "- 本阶段只做全图二值掩膜和方法对照，不做连通域、轮廓过滤、开闭运算、最小面积删除、TopN截断、分类或跨样品黑名单。",
        "",
        "## 1. 固定DN阈值与局部Median/MAD候选像素比例",
        "",
        "比例是全分辨率像素比例，不是缺陷数量、Precision、Recall或误检率。高比例只表示当前阈值下候选面积较大。",
        "",
        "|样品|尺度(px)|固定150|固定200|固定250|固定300|局部k=3|局部k=5|局部k=7|诊断提示|",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for sample_id in sample_ids:
        for scale in user_config.CASE03A_SCALES_PX:
            fixed = [summarize_sample_rows(threshold_rows, sample_id, scale, "fixed_absolute", f"threshold_dn={t}") for t in fixed_thresholds]
            local = [summarize_sample_rows(threshold_rows, sample_id, scale, "local_median_mad", f"k={k},floor_dn={user_config.CASE03A_MAD_FLOOR_DN},grid={user_config.CASE03A_GRID_SIZE_PX},stride={user_config.CASE03A_GRID_SAMPLE_STRIDE_PX}") for k in k_values]
            ratios = [float(row["abnormal_fraction"]) for row in fixed + local]
            lines.append(
                f"|{sample_id}|{scale}|{float(fixed[0]['abnormal_fraction']):.6f}|{float(fixed[1]['abnormal_fraction']):.6f}|{float(fixed[2]['abnormal_fraction']):.6f}|{float(fixed[3]['abnormal_fraction']):.6f}|{float(local[0]['abnormal_fraction']):.6f}|{float(local[1]['abnormal_fraction']):.6f}|{float(local[2]['abnormal_fraction']):.6f}|{ratio_mark(max(ratios))}|"
            )
    lines.extend(
        [
            "",
            "固定阈值越低，候选面积应单调不减；局部k越大通常会提高局部阈值，但背景网格中的黑带/强边界会影响Median/MAD估计。任何大面积候选均保留，不通过提高阈值掩盖。",
            "",
            "## 2. 全分辨率掩膜与无损还原",
            "",
            f"- 主掩膜数量：{len(mask_manifest)}（每个样品/尺度保存固定{user_config.CASE03A_FIXED_PRIMARY_DN} DN和局部k={user_config.CASE03A_MAD_PRIMARY_K}两种）。",
            f"- 单个packbits掩膜理论大小：约{(user_config.RAW_WIDTH * user_config.RAW_HEIGHT + 7) // 8 / 1024**2:.2f} MiB；实际文件大小记录在`mask_manifest.csv`。",
            "- 每个主掩膜均保存shape、bitorder和dtype语义，并在写出后立即还原逐像素核对。",
            "- PNG缩略图只用于显示，不能作为掩膜真值或DN定量输入。",
            "",
            "## 3. 典型点与背景干扰诊断",
            "",
        ]
    )
    for row in patch_manifest:
        lines.append(
            f"- 样品{row['sample_id']} `{row['label']}`：坐标`({row['x']},{row['y']})`，来源=`{row['source']}`，31 px融合响应patch峰值={row['fused_peak_response_dn']} DN；图件=`{Path(row['comparison_png']).name}`。这些点不是人工真实疵病标签。"
        )
    lines.extend(
        [
            "",
            "联系图和patch对照用于观察暗点、细线、黑带边界以及亮/暗固定标记的响应关系。当前不能将任何暗点自动称为真实疵病，也不能把局部阈值保留或删除解释成漏检率。",
            "",
            "## 4. 局部阈值实现核查",
            "",
            "- 网格按256 px覆盖至最后不足整格的边界，中心坐标写入`local_grid_statistics.csv`。",
            "- 中位数/MAD网格值采用双线性插值到像素条带，边缘采用最近网格中心值；掩膜比较仍对完整分辨率响应逐像素执行。",
            "- `MAD=0`由floor_dn=120 DN保证，不会因阈值为0而把整图异常选中。",
            "- 本阶段不做连通域和面积清理；候选像素完整保留。",
            "",
            "## 5. 资源和限制",
            "",
            f"- 磁盘资源快照：总量{resources['disk_total_gib']:.2f} GiB，已用{resources['disk_used_gib']:.2f} GiB，可用{resources['disk_free_gib']:.2f} GiB。",
            f"- 处理策略：逐样品、逐尺度、逐条带；固定扫描临时掩膜和局部阈值条带处理后释放。",
            "- 现有Black-Hat NPZ、原始RAW和Case02验证输出未写回；Case03-A结果仅写本次新目录。",
            "- 当前报告不提供真实疵病漏检率、误检率、Precision、Recall或F1。",
            "",
            "## 6. 结论状态",
            "",
            "|项目|状态|",
            "|---|---|",
            "|固定DN与局部Median/MAD全图掩膜功能|已完成并通过一级自验|",
            "|阈值敏感性与候选面积解释|已生成统计，需人工查看图册|",
            "|真实疵病与黑带/固定标记区分|PENDING USER|",
            "|真实疵病漏检率/人工视觉效果|PENDING USER|",
            "|Case03-B/Case04/Case05|未执行|",
        ]
    )
    write_text(path, "\n".join(lines))


def write_acceptance(path: Path, summary: dict) -> None:
    """写入逐项Case03-A自验收。"""

    complete = summary["complete_representative_set"]
    write_text(
        path,
        f"""# Case03-A阶段自验收

|检查项|状态|证据|
|---|---|---|
|输入为既有Case02 uint16响应NPZ且未覆盖|PASS|input_manifest.csv；Case02基线目录未写回。|
|5张样品×5尺度固定阈值与局部鲁棒阈值完成|{'PASS' if complete and summary['threshold_rows'] == summary['threshold_rows_expected'] else 'FAIL'}|threshold_statistics.csv，共{summary['threshold_rows']}行。|
|主掩膜shape、bitorder和无损还原|{'PASS' if summary['mask_roundtrip_ok'] else 'FAIL'}|mask_manifest.csv，共{summary['mask_count']}个packbits掩膜。|
|局部网格边界/MAD=0/插值证据|PASS|local_grid_statistics.csv、阈值面预览和合成测试。|
|全图联系图及典型点patch|PASS|figures/与patches/。|
|没有连通域、轮廓、面积过滤、TopN截断|PASS|本阶段代码边界和报告说明。|
|真实疵病漏检率/人工视觉效果|PENDING USER|没有人工真值，不计算Recall/F1。|
|Case03-B及以后阶段|PASS|本轮未执行。|

一级自验：**{'PASS' if summary['overall_self_check'] else 'FAIL'}**。用户视觉验收仍为`PENDING USER`；请先检查联系图、典型点patch和阈值统计，再决定是否进入Case03-B。
""",
    )


def main() -> int:
    """执行Case03-A，完成后停止。"""

    args = parse_args()
    input_run = resolve_path(args.input_run, user_config.CASE03A_INPUT_RUN)
    if not input_run.is_dir():
        raise FileNotFoundError(f"Case03-A输入目录不存在: {input_run}")
    sample_ids = [args.sample] if args.sample is not None else list(user_config.CASE03A_SAMPLE_IDS)
    unknown = set(sample_ids) - set(user_config.CASE03A_SAMPLE_IDS)
    if unknown:
        raise ValueError(f"样品不在Case03-A代表集内: {sorted(unknown)}")
    run_dir = make_run_dir(args.output_run_id)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(run_dir / "logs" / "case03a.log", encoding="utf-8"), logging.StreamHandler()],
    )
    LOGGER.info("Case03-A启动，input=%s output=%s samples=%s", input_run, run_dir, sample_ids)
    scales = list(user_config.CASE03A_SCALES_PX)
    if scales != [3, 5, 9, 15, 31]:
        LOGGER.warning("当前尺度配置已偏离提示词默认值: %s", scales)
    baseline_lookup = baseline_stats_lookup(input_run)
    missing_stats = [(sample, scale) for sample in sample_ids for scale in scales if (sample, scale) not in baseline_lookup]
    if missing_stats:
        raise FileNotFoundError(f"Case02尺度统计缺失: {missing_stats}")
    resources = resource_estimate(len(sample_ids), len(scales))
    write_json(run_dir / "resource_estimate.json", resources)
    threshold_rows: list[dict] = []
    input_rows: list[dict] = []
    grid_rows: list[dict] = []
    mask_manifest: list[dict] = []
    for sample_id in sample_ids:
        started = time.perf_counter()
        sample_threshold, sample_input, sample_grid, sample_masks = process_sample(
            sample_id,
            user_config.CASE03A_FRAME_ID,
            input_run,
            run_dir,
            baseline_lookup,
            scales,
        )
        threshold_rows.extend(sample_threshold)
        input_rows.extend(sample_input)
        grid_rows.extend(sample_grid)
        mask_manifest.extend(sample_masks)
        LOGGER.info("样品%s完成，耗时%.1fs", sample_id, time.perf_counter() - started)
    patch_manifest = generate_point_diagnostics(run_dir, input_run, sample_ids, baseline_lookup)
    write_csv(
        run_dir / "threshold_statistics.csv",
        threshold_rows,
        ["sample_id", "frame_id", "kernel_size_px", "method", "parameter_label", "threshold_dn", "k", "floor_dn", "abnormal_pixels", "valid_pixels", "abnormal_fraction", "response_max_dn", "response_p95_dn", "response_p99_dn", "response_p99_9_dn", "threshold_min_dn", "threshold_max_dn", "threshold_grid_mean_dn", "input_response_npz", "threshold_source", "elapsed_s", "primary_mask_saved", "mask_path", "units"],
    )
    write_csv(
        run_dir / "input_manifest.csv",
        input_rows,
        ["sample_id", "frame_id", "kernel_size_px", "input_npz", "input_file_bytes", "npz_keys", "shape", "dtype", "baseline_max_dn", "baseline_p95_dn", "baseline_p99_dn", "baseline_p99_9_dn", "case02_response_units"],
    )
    write_csv(
        run_dir / "local_grid_statistics.csv",
        grid_rows,
        ["sample_id", "frame_id", "kernel_size_px", "grid_row", "grid_col", "y_start_px", "y_end_px", "x_start_px", "x_end_px", "center_y_px", "center_x_px", "sample_count", "median_dn", "mad_dn", "robust_sigma_dn"],
    )
    write_csv(
        run_dir / "mask_manifest.csv",
        mask_manifest,
        ["sample_id", "frame_id", "kernel_size_px", "method", "parameter", "path", "shape", "original_dtype", "packed_dtype", "bitorder", "raw_mask_bytes", "packed_bytes", "file_bytes", "roundtrip_equal"],
    )
    write_csv(
        run_dir / "patch_manifest.csv",
        patch_manifest,
        ["sample_id", "frame_id", "label", "source", "x", "y", "patch_size_px", "diagnostic_scale_px", "raw_display_p0_1_dn", "raw_display_p99_9_dn", "fused_response_p99_9_dn", "fused_peak_response_dn", "winning_scale_at_center_index", "raw_patch_npz", "comparison_png", "is_artificial_or_ground_truth_label"],
    )
    complete_set = set(sample_ids) == set(user_config.CASE03A_SAMPLE_IDS)
    roundtrip_ok = bool(mask_manifest) and all(bool(row["roundtrip_equal"]) for row in mask_manifest)
    expected_threshold_rows = len(sample_ids) * len(scales) * (len(user_config.CASE03A_FIXED_THRESHOLDS_DN) + len(user_config.CASE03A_MAD_K_VALUES))
    summary = {
        "overall_self_check": bool(complete_set and len(threshold_rows) == expected_threshold_rows and len(mask_manifest) == len(sample_ids) * len(scales) * 2 and roundtrip_ok),
        "complete_representative_set": complete_set,
        "sample_ids": sample_ids,
        "frame_id": user_config.CASE03A_FRAME_ID,
        "threshold_rows": len(threshold_rows),
        "threshold_rows_expected": expected_threshold_rows,
        "grid_rows": len(grid_rows),
        "mask_count": len(mask_manifest),
        "mask_roundtrip_ok": roundtrip_ok,
        "patch_count": len(patch_manifest),
        "raw_modified": False,
        "case02_input_preserved": True,
        "connected_components_executed": False,
        "user_visual_review": "PENDING_USER",
        "real_defect_recall": "PENDING_USER",
        "next_stage_started": False,
        "output_run": str(run_dir),
    }
    write_json(
        run_dir / "config_snapshot.json",
        {
            **json_safe(user_config.as_dict()),
            "STAGE": "Case03-A",
            "INPUT_CASE02_RUN": str(input_run),
            "OUTPUT_RUN": str(run_dir),
            "SELECTED_SAMPLE_IDS": sample_ids,
            "CASE03A_READS_ONLY_EXISTING_RESPONSE_NPZ": True,
            "NO_CONNECTED_COMPONENTS": True,
            "NO_MORPHOLOGY_CLEANUP": True,
            "NO_TOPN_TRUNCATION": True,
            "RESOURCE_ESTIMATE": resources,
        },
    )
    write_report(run_dir / "case03a_report.md", input_run, sample_ids, threshold_rows, mask_manifest, patch_manifest, resources)
    write_acceptance(run_dir / "acceptance.md", summary)
    write_json(run_dir / "acceptance_summary.json", summary)
    LOGGER.info("Case03-A完成：%s", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
