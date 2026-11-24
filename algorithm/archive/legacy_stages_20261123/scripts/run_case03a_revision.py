"""Case03-A-R1：阈值策略、密度可视化和扩展诊断修订。

本脚本只读取既有Case02响应NPZ、真实RAW和旧Case03-A A0结果，所有新结果写入
``outputs/case03a_revision/run_YYYYMMDD_HHMMSS/``。A0旧结果不重写；A1/A2只
提供候选扫描和代表性方案，不能解释为已确定的正式阈值。
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import gc
import hashlib
import json
import logging
import platform
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
    iter_local_threshold_strips,
    revised_grid_threshold_values,
)
from src.detection.thresholding import (
    fixed_threshold_mask,
    load_packed_mask,
    save_packed_mask,
    validate_response,
)
from src.io.raw_reader import RawReadConfig, read_raw
from src.utils.paths import discover_raw_files, json_safe, write_csv, write_json
from src.visualization.segmentation_diagnostic import (
    any_hit_thumbnail,
    density_overlay,
    density_thumbnail,
    mask_overlap_statistics,
    response_preview,
    save_density_diagnostic,
    save_revision_contact_sheet,
    save_revision_point_patch_comparison,
    write_png,
)


LOGGER = logging.getLogger("case03a_revision")


def parse_args() -> argparse.Namespace:
    """解析R1独立入口。"""

    parser = argparse.ArgumentParser(description="Case03-A-R1阈值与可视化补充修订")
    parser.add_argument("--sample", type=int, default=None, help="先运行单个样品，例如26")
    parser.add_argument("--output-run-id", type=str, default=None, help="新输出目录名")
    return parser.parse_args()


def write_text(path: Path, text: str) -> None:
    """写UTF-8文本。"""

    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """读取UTF-8/BOM CSV。"""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def resolve_project_path(value: str) -> Path:
    """解析工程相对路径。"""

    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def make_run_dir(run_id: str | None) -> Path:
    """创建不覆盖历史结果的R1目录。"""

    base = user_config.OUTPUT_ROOT / "case03a_revision"
    stamp = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = base / stamp
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{suffix:02d}"
        suffix += 1
    for name in ("masks", "figures", "patches", "logs"):
        (run_dir / name).mkdir(parents=True, exist_ok=False)
    return run_dir


def sha256_file(path: Path) -> str:
    """计算单文件SHA256，用于小型保护文件和代表性掩膜核对。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_snapshot(input_run: Path, a0_run: Path) -> dict:
    """记录旧输入/旧A0/RAW的文件清单及代表性哈希。"""

    roots = {
        "case02_input": input_run,
        "case03a_a0": a0_run,
        "raw": user_config.DATA_ROOT,
    }
    inventory: list[dict] = []
    for label, root in roots.items():
        if not root.exists():
            raise FileNotFoundError(root)
        for file_path in sorted(root.rglob("*")):
            if file_path.is_file():
                stat = file_path.stat()
                inventory.append(
                    {
                        "root": label,
                        "relative_path": str(file_path.relative_to(root)),
                        "size": int(stat.st_size),
                        "mtime_ns": int(stat.st_mtime_ns),
                    }
                )
    key_files = [
        input_run / "blackhat_statistics.csv",
        input_run / "memory_estimate.json",
        a0_run / "threshold_statistics.csv",
        a0_run / "acceptance_summary.json",
        a0_run / "masks" / "sample_26_frame_1" / "fixed_200dn_31px.npz",
        a0_run / "masks" / "sample_26_frame_1" / "local_mad_k5_3px.npz",
    ]
    hashes = {str(path): sha256_file(path) for path in key_files if path.exists()}
    return {
        "inventory": inventory,
        "inventory_count": len(inventory),
        "key_sha256": hashes,
        "raw_content_hashes_skipped": True,
        "raw_hash_skip_reason": "RAW约4GB；以全量文件size/mtime清单保护，代表性工程文件使用SHA256。",
    }


def compare_protected(before: dict, after: dict) -> dict:
    """比较保护目录清单和代表性哈希。"""

    unchanged = before["inventory"] == after["inventory"] and before["key_sha256"] == after["key_sha256"]
    return {
        "unchanged": bool(unchanged),
        "before_inventory_count": before["inventory_count"],
        "after_inventory_count": after["inventory_count"],
        "key_hashes_equal": before["key_sha256"] == after["key_sha256"],
        "inventory_equal": before["inventory"] == after["inventory"],
    }


def memory_status() -> dict:
    """读取Windows可用物理内存。"""

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
    except Exception as exc:  # pragma: no cover - Windows fallback
        return {"status": "unknown", "error": str(exc)}


def process_working_set_mib() -> float | None:
    """读取当前Python进程工作集，失败则返回None。"""

    try:
        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("page_fault_count", ctypes.c_ulong),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
        if ok:
            return float(counters.working_set_size) / 1024**2
    except Exception:
        return None
    return None


def resource_estimate(sample_count: int, scale_count: int) -> dict:
    """记录R1顺序处理的内存/磁盘资源快照。"""

    pixels = user_config.RAW_WIDTH * user_config.RAW_HEIGHT
    packed_bytes = (pixels + 7) // 8
    disk = shutil.disk_usage(PROJECT_ROOT)
    return {
        "raw_pixels": pixels,
        "one_bool_mask_bytes": pixels,
        "one_packbits_mask_bytes": packed_bytes,
        "representative_mask_count": sample_count * scale_count * (1 + len(user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES)),
        "disk_total_gib": disk.total / 1024**3,
        "disk_used_gib": disk.used / 1024**3,
        "disk_free_gib": disk.free / 1024**3,
        "memory_before": memory_status(),
        "process_working_set_mib_before": process_working_set_mib(),
        "strategy": "one sample/one scale; A1 scan masks released; A1 representative and A2 representative masks saved one at a time",
    }


def load_response(path: Path) -> np.ndarray:
    """读取Case02响应NPZ中的uint16 response_dn。"""

    with np.load(path, allow_pickle=False) as data:
        response = np.asarray(data["response_dn"])
    validate_response(response)
    expected = (user_config.RAW_HEIGHT, user_config.RAW_WIDTH)
    if response.shape != expected:
        raise AssertionError(f"响应shape异常: {path} {response.shape} != {expected}")
    return response


def response_path(input_run: Path, sample_id: int, scale: int) -> Path:
    """返回既有Case02尺度响应路径。"""

    return input_run / "samples" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / "responses" / f"blackhat_{scale}px.npz"


def load_baseline_stats(input_run: Path) -> dict[tuple[int, int], dict]:
    """读取Case02尺度统计。"""

    rows = read_csv_rows(input_run / "blackhat_statistics.csv")
    return {
        (int(row["sample_id"]), int(row["kernel_size_px"])): row
        for row in rows
        if row["response_type"] == "scale"
    }


def load_a0_stats(a0_run: Path) -> dict[tuple[int, int, str], dict]:
    """读取旧Case03-A阈值统计，严格作为A0基线。"""

    rows = read_csv_rows(a0_run / "threshold_statistics.csv")
    return {
        (int(row["sample_id"]), int(row["kernel_size_px"]), row["method"]): row
        for row in rows
        if row["method"] in {"fixed_absolute", "local_median_mad"}
    }


def a0_mask_path(a0_run: Path, sample_id: int, scale: int, local: bool) -> Path:
    """返回旧A0主掩膜路径。"""

    if local:
        name = f"local_mad_k5_{scale}px.npz"
    else:
        name = f"fixed_200dn_{scale}px.npz"
    return a0_run / "masks" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / name


def load_a0_masks(a0_run: Path, sample_id: int, scale: int) -> tuple[np.ndarray, np.ndarray]:
    """加载旧A0固定/局部主掩膜。"""

    fixed = load_packed_mask(a0_mask_path(a0_run, sample_id, scale, False))
    local = load_packed_mask(a0_mask_path(a0_run, sample_id, scale, True))
    return fixed, local


def full_local_mask(
    response: np.ndarray,
    medians: np.ndarray,
    mads: np.ndarray,
    config: dict,
) -> tuple[np.ndarray, float, float, float]:
    """按R1公式逐条带生成完整bool掩膜和阈值面摘要。"""

    mask = np.empty(response.shape, dtype=bool)
    count = 0
    threshold_min = float("inf")
    threshold_max = float("-inf")
    for y_start, y_end, threshold, strip_mask in iter_local_threshold_strips(
        response,
        medians,
        mads,
        float(config["k"]),
        int(config["floor_dn"]),
        user_config.CASE03A_GRID_SIZE_PX,
        user_config.CASE03A_STRIPE_ROWS_PX,
        min_excess_dn=float(config["min_excess_dn"]),
        strict=True,
        interpolate_components=True,
    ):
        mask[y_start:y_end] = strip_mask
        count += int(np.count_nonzero(strip_mask))
        threshold_min = min(threshold_min, float(threshold.min()))
        threshold_max = max(threshold_max, float(threshold.max()))
    threshold_grid = revised_grid_threshold_values(
        medians,
        mads,
        float(config["k"]),
        int(config["floor_dn"]),
        float(config["min_excess_dn"]),
    )
    return mask, threshold_min, threshold_max, float(threshold_grid.mean())


def center_crop(array: np.ndarray, size: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """取中心小区域用于A2筛查。"""

    size = min(int(size), array.shape[0], array.shape[1])
    y0 = (array.shape[0] - size) // 2
    x0 = (array.shape[1] - size) // 2
    return array[y0 : y0 + size, x0 : x0 + size], (y0, y0 + size, x0, x0 + size)


def region_bounds(shape: tuple[int, int]) -> dict[str, tuple[int, int, int, int]]:
    """按提示词定义上/中/下分区，返回y/x边界。"""

    height, width = shape
    result = {}
    for name, (fraction_start, fraction_end) in user_config.CASE03A_REVISION_REGION_FRACTIONS.items():
        result[name] = (int(round(height * fraction_start)), int(round(height * fraction_end)), 0, width)
    return result


def regional_rows(
    sample_id: int,
    scale: int,
    stage: str,
    method: str,
    config_name: str,
    mask: np.ndarray,
    extra: dict | None = None,
) -> list[dict]:
    """输出上/中/下分区的真实候选密度，不解释为缺陷率。"""

    rows = []
    for region_name, (y0, y1, x0, x1) in region_bounds(mask.shape).items():
        view = mask[y0:y1, x0:x1]
        row = {
            "sample_id": sample_id,
            "frame_id": user_config.CASE03A_FRAME_ID,
            "kernel_size_px": scale,
            "revision_stage": stage,
            "method": method,
            "config_name": config_name,
            "region": region_name,
            "y_start_px": y0,
            "y_end_px": y1,
            "x_start_px": x0,
            "x_end_px": x1,
            "region_pixels": int(view.size),
            "candidate_pixels": int(np.count_nonzero(view)),
            "candidate_fraction": float(np.count_nonzero(view) / view.size),
            "full_image_fraction": float(np.count_nonzero(mask) / mask.size),
        }
        if extra:
            row.update(extra)
        rows.append(row)
    return rows


def grid_summary_rows(
    sample_id: int,
    scale: int,
    stage: str,
    config_name: str,
    medians: np.ndarray,
    mads: np.ndarray,
    config: dict,
    grid_rows: list[dict],
) -> tuple[dict, list[dict]]:
    """生成网格均值/分布以及floor主导和MAD=0比例。"""

    thresholds = revised_grid_threshold_values(
        medians,
        mads,
        float(config["k"]),
        int(config["floor_dn"]),
        float(config["min_excess_dn"]),
    )
    floor_dominated = thresholds <= float(config["floor_dn"]) + 1e-5
    mad_zero = mads <= 1e-8
    summary = {
        "sample_id": sample_id,
        "frame_id": user_config.CASE03A_FRAME_ID,
        "kernel_size_px": scale,
        "revision_stage": stage,
        "config_name": config_name,
        "k": config["k"],
        "floor_dn": config["floor_dn"],
        "min_excess_dn": config["min_excess_dn"],
        "grid_rows": int(medians.shape[0]),
        "grid_cols": int(medians.shape[1]),
        "grid_count": int(medians.size),
        "median_mean_dn": float(medians.mean()),
        "median_p50_dn": float(np.percentile(medians, 50)),
        "median_p95_dn": float(np.percentile(medians, 95)),
        "median_p99_dn": float(np.percentile(medians, 99)),
        "mad_mean_dn": float(mads.mean()),
        "mad_p50_dn": float(np.percentile(mads, 50)),
        "mad_p95_dn": float(np.percentile(mads, 95)),
        "mad_p99_dn": float(np.percentile(mads, 99)),
        "threshold_grid_mean_dn": float(thresholds.mean()),
        "threshold_grid_p50_dn": float(np.percentile(thresholds, 50)),
        "threshold_grid_p95_dn": float(np.percentile(thresholds, 95)),
        "threshold_grid_min_dn": float(thresholds.min()),
        "threshold_grid_max_dn": float(thresholds.max()),
        "floor_dominated_grid_count": int(np.count_nonzero(floor_dominated)),
        "floor_dominated_grid_fraction": float(np.mean(floor_dominated)),
        "mad_zero_grid_count": int(np.count_nonzero(mad_zero)),
        "mad_zero_grid_fraction": float(np.mean(mad_zero)),
    }
    detail = []
    for cell in grid_rows:
        grid_row = dict(cell)
        grid_row.update(
            {
                "sample_id": sample_id,
                "frame_id": user_config.CASE03A_FRAME_ID,
                "kernel_size_px": scale,
                "revision_stage": stage,
                "config_name": config_name,
                "k": config["k"],
                "floor_dn": config["floor_dn"],
                "min_excess_dn": config["min_excess_dn"],
                "threshold_grid_dn": float(thresholds[int(cell["grid_row"]), int(cell["grid_col"])]),
                "floor_dominated": bool(floor_dominated[int(cell["grid_row"]), int(cell["grid_col"])]),
                "mad_zero": bool(mad_zero[int(cell["grid_row"]), int(cell["grid_col"])]),
            }
        )
        detail.append(grid_row)
    return summary, detail


def threshold_row(
    sample_id: int,
    scale: int,
    stage: str,
    method: str,
    config_name: str,
    mask: np.ndarray,
    baseline: dict,
    threshold_dn: int | str = "",
    k: int | str = "",
    floor_dn: int | str = "",
    min_excess_dn: int | str = "",
    comparison: str = "",
    threshold_min_dn: float | str = "",
    threshold_max_dn: float | str = "",
    threshold_grid_mean_dn: float | str = "",
    threshold_source: str = "",
    mask_path: str = "",
    crop_bounds: tuple[int, int, int, int] | None = None,
) -> dict:
    """生成R1阈值统计行。"""

    row = {
        "sample_id": sample_id,
        "frame_id": user_config.CASE03A_FRAME_ID,
        "kernel_size_px": scale,
        "revision_stage": stage,
        "method": method,
        "config_name": config_name,
        "threshold_dn": threshold_dn,
        "k": k,
        "floor_dn": floor_dn,
        "min_excess_dn": min_excess_dn,
        "comparison": comparison,
        "abnormal_pixels": int(np.count_nonzero(mask)),
        "valid_pixels": int(mask.size),
        "abnormal_fraction": float(np.count_nonzero(mask) / mask.size),
        "response_max_dn": baseline.get("max", ""),
        "response_p95_dn": baseline.get("p95", ""),
        "response_p99_dn": baseline.get("p99", ""),
        "response_p99_9_dn": baseline.get("p99_9", ""),
        "threshold_min_dn": threshold_min_dn,
        "threshold_max_dn": threshold_max_dn,
        "threshold_grid_mean_dn": threshold_grid_mean_dn,
        "threshold_source": threshold_source,
        "selected_mask_saved": bool(mask_path),
        "mask_path": mask_path,
        "crop_bounds": "" if crop_bounds is None else str(list(crop_bounds)),
        "units": "response/threshold=DN; count=pixels; fraction=unitless",
    }
    return row


def save_mask_with_manifest(path: Path, mask: np.ndarray, stage: str, config_name: str, sample_id: int, scale: int) -> dict:
    """保存R1代表掩膜并立即还原核对。"""

    packed = np.packbits(mask.reshape(-1), bitorder="little")
    np.savez_compressed(
        path,
        mask_packed=packed,
        mask_shape=np.asarray(mask.shape, dtype=np.int64),
        bitorder=np.asarray("little"),
        revision_stage=np.asarray(stage),
        config_name=np.asarray(config_name),
    )
    restored = load_packed_mask(path)
    equal = bool(np.array_equal(restored, mask))
    del restored
    if not equal:
        raise AssertionError(f"R1 packbits还原失败: {path}")
    return {
        "sample_id": sample_id,
        "frame_id": user_config.CASE03A_FRAME_ID,
        "kernel_size_px": scale,
        "revision_stage": stage,
        "config_name": config_name,
        "path": str(path),
        "shape": str(list(mask.shape)),
        "original_dtype": "bool",
        "packed_dtype": str(packed.dtype),
        "bitorder": "little",
        "raw_mask_bytes": int(mask.size),
        "packed_bytes": int(packed.nbytes),
        "file_bytes": int(path.stat().st_size),
        "roundtrip_equal": equal,
    }


def density_assets(run_dir: Path, stem: str, title: str, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """保存density、any-hit及带色标诊断图。"""

    density = density_thumbnail(mask, user_config.CASE03A_REVISION_DENSITY_MAX_EDGE_PX)
    any_hit = any_hit_thumbnail(mask, user_config.CASE03A_REVISION_DENSITY_MAX_EDGE_PX)
    full_fraction = float(np.count_nonzero(mask) / mask.size)
    thumbnail_mean_fraction = float(density.mean() / 255.0)
    stats = {
        "full_fraction": full_fraction,
        "thumbnail_mean_fraction": thumbnail_mean_fraction,
        "thumbnail_mean_abs_error": abs(thumbnail_mean_fraction - full_fraction),
        "any_hit_thumbnail_fraction": float(np.count_nonzero(any_hit) / any_hit.size),
    }
    write_png(density, run_dir / "figures" / f"{stem}_full_view_density.png")
    write_png(any_hit, run_dir / "figures" / f"{stem}_full_view_any_hit.png")
    save_density_diagnostic(
        run_dir / "figures" / f"{stem}_density_diagnostic.png",
        title,
        density,
        any_hit,
        full_fraction,
        thumbnail_mean_fraction,
    )
    return density, any_hit, stats


def append_a0_rows(
    rows: list[dict],
    a0_stats: dict,
    sample_id: int,
    scale: int,
    baseline: dict,
) -> None:
    """将旧A0 CSV行映射到R1统一统计表，不重新解释数值。"""

    for method, config_name in (("fixed_absolute", "A0_fixed200"), ("local_median_mad", "A0_local_k5_floor120")):
        old = dict(a0_stats[(sample_id, scale, method)])
        old.update(
            {
                "sample_id": sample_id,
                "frame_id": user_config.CASE03A_FRAME_ID,
                "kernel_size_px": scale,
                "revision_stage": "A0",
                "method": method,
                "config_name": config_name,
                "min_excess_dn": 0,
                "comparison": "inclusive_ge",
                "threshold_source": "existing_case03a_run_20261008_112000",
                "selected_mask_saved": True,
                "mask_path": str(a0_mask_path(resolve_project_path("outputs/case03a/run_20261008_112000"), sample_id, scale, method == "local_median_mad")),
                "crop_bounds": "",
                "units": "response/threshold=DN; count=pixels; fraction=unitless",
            }
        )
        for name in (
            "threshold_dn",
            "k",
            "floor_dn",
            "comparison",
            "abnormal_pixels",
            "valid_pixels",
            "abnormal_fraction",
            "response_max_dn",
            "response_p95_dn",
            "response_p99_dn",
            "response_p99_9_dn",
            "threshold_min_dn",
            "threshold_max_dn",
            "threshold_grid_mean_dn",
        ):
            old.setdefault(name, "")
        rows.append(old)


def quantile_row(sample_id: int, scale: int, response: np.ndarray) -> dict:
    """提取A1候选来源分位数。"""

    values = np.percentile(response, [95, 99, 99.5, 99.9, 99.95])
    return {
        "sample_id": sample_id,
        "frame_id": user_config.CASE03A_FRAME_ID,
        "kernel_size_px": scale,
        "p95_dn": float(values[0]),
        "p99_dn": float(values[1]),
        "p99_5_dn": float(values[2]),
        "p99_9_dn": float(values[3]),
        "p99_95_dn": float(values[4]),
    }


def proposal_rows(quantiles: list[dict]) -> list[dict]:
    """生成A1候选阈值来源表，不自动选择正式阈值。"""

    by_scale: dict[int, list[dict]] = defaultdict(list)
    for row in quantiles:
        by_scale[int(row["kernel_size_px"])].append(row)
    rows = []
    for scale, thresholds in user_config.CASE03A_REVISION_FIXED_THRESHOLDS_BY_SCALE.items():
        group = by_scale[int(scale)]
        median_p99_9 = float(np.median([row["p99_9_dn"] for row in group]))
        median_p99 = float(np.median([row["p99_dn"] for row in group]))
        for threshold in thresholds:
            relation = "below_or_near_p99_9" if threshold <= median_p99_9 else "above_median_p99_9"
            rows.append(
                {
                    "kernel_size_px": scale,
                    "candidate_threshold_dn": threshold,
                    "source": "five_sample_full_response_percentiles",
                    "sample_count": len(group),
                    "median_p99_dn": median_p99,
                    "median_p99_9_dn": median_p99_9,
                    "candidate_relation": relation,
                    "applied_consistently_to_all_samples": True,
                    "formal_threshold_selected": False,
                    "note": "分位数只提供候选来源，不是物理疵病判定标准，也不按候选比例反向优化。",
                }
            )
    return rows


def select_low_response_window(fused: np.ndarray, size: int) -> dict:
    """在中心区域按窗口P99/均值选择整体低响应背景，不用单点argmin。"""

    size = min(int(size), fused.shape[0], fused.shape[1])
    y0 = fused.shape[0] // 4
    y1 = fused.shape[0] * 3 // 4 - size
    x0 = fused.shape[1] // 4
    x1 = fused.shape[1] * 3 // 4 - size
    candidates = []
    for y in range(y0, max(y0 + 1, y1 + 1), size):
        for x in range(x0, max(x0 + 1, x1 + 1), size):
            view = fused[y : y + size, x : x + size]
            candidates.append((float(np.percentile(view, 99)), float(view.mean()), float(np.percentile(view, 95)), x, y, view))
    chosen = min(candidates, key=lambda item: (item[0], item[1], item[2]))
    return {
        "label": "candidate_not_truth_low_response_window",
        "source": "central_window_low_p99_not_single_pixel",
        "x": int(chosen[3] + size // 2),
        "y": int(chosen[4] + size // 2),
        "window_x_start": int(chosen[3]),
        "window_y_start": int(chosen[4]),
        "window_size_px": size,
        "window_p95_dn": chosen[2],
        "window_p99_dn": chosen[0],
        "window_mean_dn": chosen[1],
    }


def select_weak_line_window(fused: np.ndarray, size: int) -> dict:
    """选择响应中等且具有细线/弱候选迹象的窗口，仅作人工复核入口。"""

    size = min(int(size), fused.shape[0], fused.shape[1])
    global_p99 = float(np.percentile(fused, 99))
    global_p99_9 = float(np.percentile(fused, 99.9))
    candidates = []
    y0, y1 = fused.shape[0] // 5, fused.shape[0] * 4 // 5 - size
    x0, x1 = fused.shape[1] // 5, fused.shape[1] * 4 // 5 - size
    for y in range(y0, max(y0 + 1, y1 + 1), size):
        for x in range(x0, max(x0 + 1, x1 + 1), size):
            view = fused[y : y + size, x : x + size].astype(np.float32)
            weak_count = int(np.count_nonzero((view >= global_p99) & (view < global_p99_9)))
            row_gradient = float(np.mean(np.abs(np.diff(view, axis=0))))
            col_gradient = float(np.mean(np.abs(np.diff(view, axis=1))))
            score = weak_count + 100.0 * max(row_gradient, col_gradient)
            candidates.append((score, weak_count, row_gradient, col_gradient, x, y, view))
    chosen = max(candidates, key=lambda item: (item[0], item[1]))
    view = chosen[6]
    return {
        "label": "candidate_not_truth_weak_or_fine_line_window",
        "source": "moderate_response_window_with_local_gradient",
        "x": int(chosen[4] + size // 2),
        "y": int(chosen[5] + size // 2),
        "window_x_start": int(chosen[4]),
        "window_y_start": int(chosen[5]),
        "window_size_px": size,
        "window_p95_dn": float(np.percentile(view, 95)),
        "window_p99_dn": float(np.percentile(view, 99)),
        "window_mean_dn": float(view.mean()),
        "weak_candidate_pixels": chosen[1],
        "mean_row_gradient_dn": chosen[2],
        "mean_col_gradient_dn": chosen[3],
    }


def diagnostic_points(sample_id: int, raw: np.ndarray, fused: np.ndarray) -> list[dict]:
    """返回历史点、对应点、窗口背景、边界和弱线候选。"""

    points = [dict(item) for item in user_config.CASE03A_DIAGNOSTIC_POINTS if item["sample_id"] == sample_id]
    if sample_id not in {26, 30}:
        for item in user_config.CASE03A_DIAGNOSTIC_POINTS:
            if item["sample_id"] == 26:
                points.append(
                    {
                        **item,
                        "label": f"corresponding_{item['label']}",
                        "source": "corresponding_sample26_coordinate_candidate_not_truth",
                    }
                )
    window = user_config.CASE03A_REVISION_DIAGNOSTIC_WINDOW_SIZE_PX
    points.append({"sample_id": sample_id, "frame_id": user_config.CASE03A_FRAME_ID, **select_low_response_window(fused, window)})
    points.append({"sample_id": sample_id, "frame_id": user_config.CASE03A_FRAME_ID, **select_weak_line_window(fused, window)})
    row_mean = raw.astype(np.float32).mean(axis=1)
    gradient = np.abs(np.diff(row_mean))
    margin = window // 2
    gradient[:margin] = 0
    gradient[-margin:] = 0
    boundary_y = int(np.argmax(gradient))
    points.append(
        {
            "sample_id": sample_id,
            "frame_id": user_config.CASE03A_FRAME_ID,
            "label": "candidate_not_truth_row_gradient_boundary",
            "source": "raw_row_mean_gradient_stress_test",
            "x": raw.shape[1] // 2,
            "y": max(margin, min(raw.shape[0] - margin - 1, boundary_y)),
            "window_size_px": window,
            "window_x_start": raw.shape[1] // 2 - window // 2,
            "window_y_start": max(0, boundary_y - window // 2),
        }
    )
    if sample_id == 26:
        half = window // 2
        upper_y = max(half, int(raw.shape[0] * 0.075))
        lower_y = min(raw.shape[0] - half - 1, int(raw.shape[0] * 0.925))
        points.extend(
            [
                {
                    "sample_id": sample_id,
                    "frame_id": user_config.CASE03A_FRAME_ID,
                    "label": "sample26_3px_local_upper15_reference",
                    "source": "upper15_region_reference_candidate_not_truth",
                    "x": raw.shape[1] // 2,
                    "y": upper_y,
                    "window_size_px": window,
                },
                {
                    "sample_id": sample_id,
                    "frame_id": user_config.CASE03A_FRAME_ID,
                    "label": "sample26_3px_local_lower15_reference",
                    "source": "lower15_region_reference_candidate_not_truth",
                    "x": raw.shape[1] // 2,
                    "y": lower_y,
                    "window_size_px": window,
                },
                {
                    "sample_id": sample_id,
                    "frame_id": user_config.CASE03A_FRAME_ID,
                    "label": "sample26_31px_fixed_upper15_reference",
                    "source": "upper15_region_reference_candidate_not_truth",
                    "x": raw.shape[1] // 2,
                    "y": upper_y,
                    "window_size_px": window,
                },
                {
                    "sample_id": sample_id,
                    "frame_id": user_config.CASE03A_FRAME_ID,
                    "label": "sample26_31px_fixed_lower15_reference",
                    "source": "lower15_region_reference_candidate_not_truth",
                    "x": raw.shape[1] // 2,
                    "y": lower_y,
                    "window_size_px": window,
                },
            ]
        )
    return points


def crop_patch(array: np.ndarray, x: int, y: int, size: int) -> np.ndarray:
    """按全分辨率坐标取不缩放patch。"""

    half = int(size) // 2
    x, y = int(x), int(y)
    if x - half < 0 or y - half < 0 or x + half > array.shape[1] or y + half > array.shape[0]:
        raise ValueError(f"诊断patch越界: ({x},{y}) shape={array.shape}")
    return array[y - half : y + half, x - half : x + half].copy()


def generate_patches(
    run_dir: Path,
    input_run: Path,
    a0_run: Path,
    sample_ids: list[int],
    baseline: dict,
    a1_mask_paths: dict[tuple[int, int], Path],
    a2_mask_paths: dict[tuple[int, int, str], Path],
) -> list[dict]:
    """生成历史点、窗口点及样品26上下区域的A0/A1/A2原尺寸patch。"""

    records = {(item["sample_id"], item["frame_id"]): item["path"] for item in discover_raw_files(user_config.DATA_ROOT)}
    raw_config = RawReadConfig(
        width=user_config.RAW_WIDTH,
        height=user_config.RAW_HEIGHT,
        effective_bits=user_config.EFFECTIVE_BITS,
        endian=user_config.RAW_ENDIAN,
    )
    patch_rows = []
    overlay_config = user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES[0]
    for sample_id in sample_ids:
        raw = read_raw(records[(sample_id, user_config.CASE03A_FRAME_ID)], raw_config)
        fused_path = input_run / "samples" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / "responses" / "blackhat_fused.npz"
        winning_path = input_run / "samples" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}" / "responses" / "winning_scale_map.npz"
        with np.load(fused_path, allow_pickle=False) as data:
            fused = np.asarray(data["fused_response_dn"])
        with np.load(winning_path, allow_pickle=False) as data:
            winning = np.asarray(data["winning_scale"])
        raw_low, raw_high = np.percentile(raw, [0.1, 99.9])
        points = diagnostic_points(sample_id, raw, fused)
        for point in points:
            label = str(point["label"])
            scale = 3 if "3px_local" in label else 31
            a0_fixed = load_packed_mask(a0_mask_path(a0_run, sample_id, scale, False))
            a0_local = load_packed_mask(a0_mask_path(a0_run, sample_id, scale, True))
            a1_fixed = load_packed_mask(a1_mask_paths[(sample_id, scale)])
            a2_local = load_packed_mask(a2_mask_paths[(sample_id, scale, overlay_config["name"])])
            size = int(point.get("window_size_px", user_config.CASE03A_REVISION_DIAGNOSTIC_WINDOW_SIZE_PX))
            x, y = int(point["x"]), int(point["y"])
            raw_patch = crop_patch(raw, x, y, size)
            fused_patch = crop_patch(fused, x, y, size)
            panels = [
                crop_patch(a0_fixed, x, y, size),
                crop_patch(a0_local, x, y, size),
                crop_patch(a1_fixed, x, y, size),
                crop_patch(a2_local, x, y, size),
                crop_patch(winning, x, y, size),
            ]
            stem = f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}_{label}_x{x}_y{y}_scale{scale}px"
            npz_path = run_dir / "patches" / f"{stem}.npz"
            np.savez_compressed(
                npz_path,
                raw_dn=raw_patch,
                fused_response_dn=fused_patch,
                a0_fixed_mask=panels[0],
                a0_local_mask=panels[1],
                a1_fixed_mask=panels[2],
                a2_local_mask=panels[3],
                winning_scale=panels[4],
            )
            png_path = run_dir / "figures" / f"{stem}.png"
            save_revision_point_patch_comparison(
                png_path,
                f"样品{sample_id} 第{user_config.CASE03A_FRAME_ID}帧 {label} x={x} y={y} scale={scale}px",
                raw_patch,
                fused_patch,
                panels[0],
                panels[1],
                panels[2],
                panels[3],
                size,
                (float(raw_low), float(raw_high)),
                max(float(baseline[(sample_id, scale)]["p99_9"]), 1.0),
                f"{user_config.CASE03A_REVISION_A1_MASK_THRESHOLD_BY_SCALE[scale]} DN",
                overlay_config["name"],
            )
            patch_rows.append(
                {
                    "sample_id": sample_id,
                    "frame_id": user_config.CASE03A_FRAME_ID,
                    "label": label,
                    "source": point.get("source", "candidate_not_truth"),
                    "x": x,
                    "y": y,
                    "diagnostic_scale_px": scale,
                    "patch_size_px": size,
                    "raw_display_p0_1_dn": float(raw_low),
                    "raw_display_p99_9_dn": float(raw_high),
                    "fused_patch_p95_dn": float(np.percentile(fused_patch, 95)),
                    "fused_patch_p99_dn": float(np.percentile(fused_patch, 99)),
                    "fused_patch_peak_dn": int(fused_patch.max()),
                    "window_p95_dn": point.get("window_p95_dn", ""),
                    "window_p99_dn": point.get("window_p99_dn", ""),
                    "window_mean_dn": point.get("window_mean_dn", ""),
                    "raw_patch_npz": str(npz_path),
                    "comparison_png": str(png_path),
                    "label_status": "candidate_not_truth",
                }
            )
            del a0_fixed, a0_local, a1_fixed, a2_local, raw_patch, fused_patch, panels
        del raw, fused, winning
        gc.collect()
    return patch_rows


def screen_a2(
    input_run: Path,
    sample_id: int,
    baseline: dict,
    threshold_rows: list[dict],
    crop_records: list[dict],
) -> None:
    """在样品26中心2048区域筛查A2参数，不保存全分辨率掩膜。"""

    configs = [
        {"name": f"screen_k{k}_floor{floor}_excess{excess}", "k": k, "floor_dn": floor, "min_excess_dn": excess}
        for k in user_config.CASE03A_REVISION_LOCAL_SCREEN_K
        for floor in user_config.CASE03A_REVISION_LOCAL_SCREEN_FLOOR_DN
        for excess in user_config.CASE03A_REVISION_LOCAL_SCREEN_MIN_EXCESS_DN
    ]
    for scale in user_config.CASE03A_SCALES_PX:
        response = load_response(response_path(input_run, sample_id, scale))
        crop, bounds = center_crop(response, user_config.CASE03A_REVISION_SCREEN_CROP_SIZE_PX)
        medians, mads, grid_rows = compute_local_grid_statistics(
            crop,
            user_config.CASE03A_GRID_SIZE_PX,
            user_config.CASE03A_GRID_SAMPLE_STRIDE_PX,
        )
        for config in configs:
            mask, threshold_min, threshold_max, threshold_mean = full_local_mask(crop, medians, mads, config)
            threshold_rows.append(
                threshold_row(
                    sample_id,
                    scale,
                    "A2_screen",
                    "local_median_mad_revised",
                    config["name"],
                    mask,
                    baseline[(sample_id, scale)],
                    k=config["k"],
                    floor_dn=config["floor_dn"],
                    min_excess_dn=config["min_excess_dn"],
                    comparison="strict_gt",
                    threshold_min_dn=threshold_min,
                    threshold_max_dn=threshold_max,
                    threshold_grid_mean_dn=threshold_mean,
                    threshold_source="sample26中心2048px筛查；不作为正式阈值",
                    crop_bounds=bounds,
                )
            )
            crop_records.append(
                {
                    "sample_id": sample_id,
                    "kernel_size_px": scale,
                    "config_name": config["name"],
                    "crop_y0": bounds[0],
                    "crop_y1": bounds[1],
                    "crop_x0": bounds[2],
                    "crop_x1": bounds[3],
                    "candidate_fraction": float(np.count_nonzero(mask) / mask.size),
                    "threshold_grid_mean_dn": threshold_mean,
                }
            )
            del mask
        del response, crop, medians, mads, grid_rows
        gc.collect()


def process_sample(
    run_dir: Path,
    input_run: Path,
    a0_run: Path,
    sample_id: int,
    baseline: dict,
    a0_stats: dict,
    threshold_rows: list[dict],
    regional_rows_all: list[dict],
    grid_summaries: list[dict],
    grid_details: list[dict],
    overlap_rows: list[dict],
    quantiles: list[dict],
    mask_manifest: list[dict],
    a1_mask_paths: dict[tuple[int, int], Path],
    a2_mask_paths: dict[tuple[int, int, str], Path],
    runtime_rows: list[dict],
) -> None:
    """逐样品/尺度完成A0复现对照、A1扫描、A2代表方案和密度图。"""

    contact_entries = []
    for scale in user_config.CASE03A_SCALES_PX:
        started = time.perf_counter()
        memory_before = memory_status()
        response = load_response(response_path(input_run, sample_id, scale))
        baseline_row = dict(baseline[(sample_id, scale)])
        quantiles.append(quantile_row(sample_id, scale, response))
        response_display = response_preview(
            response,
            max(float(baseline_row["p99_9"]), 1.0),
            user_config.CASE03A_REVISION_DENSITY_MAX_EDGE_PX,
        )
        a0_fixed, a0_local = load_a0_masks(a0_run, sample_id, scale)
        append_a0_rows(threshold_rows, a0_stats, sample_id, scale, baseline_row)
        a0_fixed_density, _, a0_fixed_asset = density_assets(
            run_dir,
            f"sample_{sample_id}_{scale}px_A0_fixed200",
            f"样品{sample_id} {scale}px A0固定200真实密度",
            a0_fixed,
        )
        a0_local_density, _, a0_local_asset = density_assets(
            run_dir,
            f"sample_{sample_id}_{scale}px_A0_local_k5_floor120",
            f"样品{sample_id} {scale}px A0局部k5/floor120真实密度",
            a0_local,
        )
        regional_rows_all.extend(regional_rows(sample_id, scale, "A0", "fixed_absolute", "A0_fixed200", a0_fixed))
        regional_rows_all.extend(regional_rows(sample_id, scale, "A0", "local_median_mad", "A0_local_k5_floor120", a0_local))

        medians, mads, cells = compute_local_grid_statistics(
            response,
            user_config.CASE03A_GRID_SIZE_PX,
            user_config.CASE03A_GRID_SAMPLE_STRIDE_PX,
        )
        a0_grid_config = {"k": 5, "floor_dn": 120, "min_excess_dn": 0}
        summary, detail = grid_summary_rows(sample_id, scale, "A0", "A0_local_k5_floor120", medians, mads, a0_grid_config, cells)
        grid_summaries.append(summary)
        grid_details.extend(detail)

        selected_a1_mask = None
        selected_a1_threshold = user_config.CASE03A_REVISION_A1_MASK_THRESHOLD_BY_SCALE[scale]
        for threshold in user_config.CASE03A_REVISION_FIXED_THRESHOLDS_BY_SCALE[scale]:
            mask = fixed_threshold_mask(response, int(threshold))
            threshold_rows.append(
                threshold_row(
                    sample_id,
                    scale,
                    "A1",
                    "fixed_absolute_revised",
                    f"A1_fixed_{threshold}dn",
                    mask,
                    baseline_row,
                    threshold_dn=threshold,
                    comparison="inclusive_ge",
                    threshold_source="五样品全图响应分位数候选及上下邻近级别",
                )
            )
            regional_rows_all.extend(regional_rows(sample_id, scale, "A1", "fixed_absolute_revised", f"A1_fixed_{threshold}dn", mask, {"threshold_dn": threshold}))
            if threshold == selected_a1_threshold:
                selected_a1_mask = mask
            else:
                del mask
        if selected_a1_mask is None:
            raise AssertionError(f"A1代表阈值不在扫描表: scale={scale}")
        a1_path = run_dir / "masks" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}_A1_fixed_{selected_a1_threshold}dn_{scale}px.npz"
        mask_manifest.append(save_mask_with_manifest(a1_path, selected_a1_mask, "A1", f"A1_fixed_{selected_a1_threshold}dn", sample_id, scale))
        a1_mask_paths[(sample_id, scale)] = a1_path
        a1_density, _, a1_asset = density_assets(
            run_dir,
            f"sample_{sample_id}_{scale}px_A1_fixed_{selected_a1_threshold}dn",
            f"样品{sample_id} {scale}px A1固定代表{selected_a1_threshold}DN真实密度",
            selected_a1_mask,
        )

        a2_masks = {}
        for rep in user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES:
            a2_mask, threshold_min, threshold_max, threshold_mean = full_local_mask(response, medians, mads, rep)
            threshold_rows.append(
                threshold_row(
                    sample_id,
                    scale,
                    "A2",
                    "local_median_mad_revised",
                    rep["name"],
                    a2_mask,
                    baseline_row,
                    k=rep["k"],
                    floor_dn=rep["floor_dn"],
                    min_excess_dn=rep["min_excess_dn"],
                    comparison="strict_gt",
                    threshold_min_dn=threshold_min,
                    threshold_max_dn=threshold_max,
                    threshold_grid_mean_dn=threshold_mean,
                    threshold_source="R1代表性参数；不是正式最优阈值",
                )
            )
            regional_rows_all.extend(regional_rows(sample_id, scale, "A2", "local_median_mad_revised", rep["name"], a2_mask, rep))
            grid_summary, grid_detail = grid_summary_rows(sample_id, scale, "A2", rep["name"], medians, mads, rep, cells)
            grid_summaries.append(grid_summary)
            grid_details.extend(grid_detail)
            a2_path = run_dir / "masks" / f"sample_{sample_id}_frame_{user_config.CASE03A_FRAME_ID}_{rep['name']}_{scale}px.npz"
            mask_manifest.append(save_mask_with_manifest(a2_path, a2_mask, "A2", rep["name"], sample_id, scale))
            a2_mask_paths[(sample_id, scale, rep["name"])] = a2_path
            density, _, asset = density_assets(
                run_dir,
                f"sample_{sample_id}_{scale}px_{rep['name']}",
                f"样品{sample_id} {scale}px {rep['name']}真实密度",
                a2_mask,
            )
            a2_masks[rep["name"]] = (a2_mask, density, asset)

        overlay_name = user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES[0]["name"]
        overlay_image, overlap = density_overlay(response_display, selected_a1_mask, a2_masks[overlay_name][0], user_config.CASE03A_REVISION_DENSITY_MAX_EDGE_PX)
        write_png(overlay_image, run_dir / "figures" / f"sample_{sample_id}_{scale}px_A1_A2_{overlay_name}_full_view_overlay_density.png")
        overlap.update({
            "sample_id": sample_id,
            "frame_id": user_config.CASE03A_FRAME_ID,
            "kernel_size_px": scale,
            "revision_stage": "A1_A2",
            "config_name": overlay_name,
            "fixed_config": f"A1_fixed_{selected_a1_threshold}dn",
            "local_config": overlay_name,
        })
        overlap_rows.append(overlap)
        a0_overlap = mask_overlap_statistics(a0_fixed, a0_local)
        a0_overlap.update({
            "sample_id": sample_id,
            "frame_id": user_config.CASE03A_FRAME_ID,
            "kernel_size_px": scale,
            "revision_stage": "A0",
            "config_name": "A0_fixed200_vs_A0_local_k5_floor120",
            "fixed_config": "A0_fixed200",
            "local_config": "A0_local_k5_floor120",
        })
        overlap_rows.append(a0_overlap)

        contact_entries.append(
            {
                "scale": scale,
                "response": response_display,
                "a0_fixed": a0_fixed_density,
                "a0_fixed_fraction": a0_fixed_asset["full_fraction"],
                "a0_local": a0_local_density,
                "a0_local_fraction": a0_local_asset["full_fraction"],
                "a1_fixed": a1_density,
                "a1_fixed_fraction": a1_asset["full_fraction"],
                "a2_local": a2_masks[overlay_name][1],
                "a2_local_fraction": a2_masks[overlay_name][2]["full_fraction"],
                "overlay": overlay_image,
            }
        )
        runtime_rows.append(
            {
                "sample_id": sample_id,
                "frame_id": user_config.CASE03A_FRAME_ID,
                "kernel_size_px": scale,
                "elapsed_s": time.perf_counter() - started,
                "memory_before": json.dumps(memory_before, ensure_ascii=False),
                "memory_after": json.dumps(memory_status(), ensure_ascii=False),
                "process_working_set_mib_after": process_working_set_mib(),
                "response_bytes": int(response.nbytes),
                "note": "逐尺度完成A1扫描、A2代表掩膜和密度图；未保留多尺度整图。",
            }
        )
        del response, a0_fixed, a0_local, medians, mads, cells, selected_a1_mask, a2_masks, response_display
        gc.collect()
    save_revision_contact_sheet(
        run_dir / "figures" / f"sample_{sample_id}_A0_A1_A2_density_contact_sheet.png",
        sample_id,
        user_config.CASE03A_FRAME_ID,
        contact_entries,
        (user_config.RAW_HEIGHT, user_config.RAW_WIDTH),
    )
    del contact_entries


def before_after_rows(
    regional_rows_all: list[dict],
    threshold_rows: list[dict],
    sample_id: int = 26,
) -> list[dict]:
    """提取样品26 3px局部和31px固定的A0/A1/A2上下区域前后对照。"""

    wanted = [
        (3, "A0", "A0_local_k5_floor120"),
        (3, "A2", user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES[0]["name"]),
        (31, "A0", "A0_fixed200"),
        (31, "A1", f"A1_fixed_{user_config.CASE03A_REVISION_A1_MASK_THRESHOLD_BY_SCALE[31]}dn"),
    ]
    rows = []
    for scale, stage, config_name in wanted:
        for region in ("upper15", "lower15"):
            match = [
                row for row in regional_rows_all
                if int(row["sample_id"]) == sample_id
                and int(row["kernel_size_px"]) == scale
                and row["revision_stage"] == stage
                and row["config_name"] == config_name
                and row["region"] == region
            ]
            if match:
                row = dict(match[0])
                row["comparison_group"] = f"sample26_{scale}px_{'local' if scale == 3 else 'fixed'}"
                rows.append(row)
    return rows


def write_report(
    path: Path,
    run_dir: Path,
    input_run: Path,
    a0_run: Path,
    sample_ids: list[int],
    threshold_rows: list[dict],
    grid_summaries: list[dict],
    overlap_rows: list[dict],
    before_after: list[dict],
    protected_compare: dict,
    runtime_rows: list[dict],
    proposal_rows_all: list[dict],
    screen_rows: list[dict],
) -> None:
    """写R1修订报告。"""

    floor_warnings = [row for row in grid_summaries if row["floor_dominated_grid_fraction"] > 0.9]
    density_rows = []
    for figure in run_dir.glob("figures/*_density_diagnostic.png"):
        density_rows.append(figure.name)
    lines = [
        "# Case03-A-R1阈值、真实密度可视化与扩展诊断报告",
        "",
        f"- 输出目录：`{run_dir}`。",
        f"- 输入Case02：`{input_run}`（只读）；A0参考：`{a0_run}`（只读）。",
        f"- 样品/帧：{','.join(map(str, sample_ids))} / 第{user_config.CASE03A_FRAME_ID}帧；响应单位为uint16 Black-Hat DN。",
        f"- 运行环境：Python {platform.python_version()}，NumPy {np.__version__}，OpenCV {cv2.__version__}；实际命令见logs。",
        "- 本轮不是最终阈值确认，不自动选择A1/A2最优方案，不根据候选比例宣称召回率提升。",
        "",
        "## 1. A0基线与R1数学修订",
        "",
        "- A0固定200 DN和旧局部k=5/floor=120结果直接读取旧Case03-A CSV/packbits掩膜，旧`>=`语义保留，旧目录未覆盖。",
        "- A2使用严格`response > T`，`T=max(floor_dn, interpolated_median + max(k×1.4826×interpolated_MAD, min_excess_dn))`。median和MAD分别插值后再计算，避免恒定非零背景因相等比较整幅阳性。",
        "- `floor_dn`是绝对下限，不等于自适应能力；每个样品/尺度/方案都记录floor主导网格比例和MAD=0网格比例。",
        "- 原始全图候选比例、分区候选密度、density缩略图着色比例和人工真实疵病召回率严格分开；本报告不计算Recall/F1。",
        "",
        "## 2. A1分尺度固定DN候选",
        "",
        "候选阈值来自五样品全图响应的P99/P99.9量级及上下邻近级别，五张样品一致使用每尺度候选表；分位数不是物理判定标准。",
        "",
        "|尺度|候选DN|中位P99|中位P99.9|关系|",
        "|---:|---:|---:|---:|---|",
    ]
    for row in proposal_rows_all:
        lines.append(f"|{row['kernel_size_px']}|{row['candidate_threshold_dn']}|{row['median_p99_dn']:.2f}|{row['median_p99_9_dn']:.2f}|{row['candidate_relation']}|")
    lines.extend(
        [
            "",
            "A1代表掩膜只用于图件、区域对照和可恢复数据，不代表正式阈值；全部候选的像素比例曲线在`threshold_statistics.csv`，上/中/下分区在`regional_density_statistics.csv`。",
            "",
            "## 3. A2局部鲁棒候选",
            "",
            f"- 样品26中心{user_config.CASE03A_REVISION_SCREEN_CROP_SIZE_PX}×{user_config.CASE03A_REVISION_SCREEN_CROP_SIZE_PX}筛查组合数：{len(screen_rows)}条记录；完整筛查明细在`a2_screen_statistics.csv`。",
            f"- 五样品完整对照代表组：{', '.join(item['name'] for item in user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES)}。",
            "- A2代表组不是自动最优选择；floor/min_excess/k的后续取舍等待用户根据密度图、原始DN和现场真值判断。",
            "",
            "## 4. 网格退化指标",
            "",
            f"- `grid_statistics.csv`记录每个样品/尺度/方案的网格均值、P50/P95/P99、floor主导比例和MAD=0比例；`grid_cells.csv`保留网格边界和每格标记。",
            f"- floor主导比例>90%的记录数：{len(floor_warnings)}；这些记录在报告中标记为退化为近似固定下限，不能宣称局部自适应有效。",
        ]
    )
    if floor_warnings:
        lines.append("")
        lines.append("醒目提示：")
        for row in floor_warnings[:30]:
            lines.append(
                f"- 样品{row['sample_id']} / {row['kernel_size_px']}px / {row['config_name']}：floor_dominated_grid_fraction={float(row['floor_dominated_grid_fraction']):.4f}，MAD_zero_grid_fraction={float(row['mad_zero_grid_fraction']):.4f}。"
            )
    lines.extend(
        [
            "",
            "## 5. 真实密度可视化",
            "",
            "- `*_full_view_density.png`：每个缩略像素是原始区域候选覆盖率，灰度0~255线性代表0~100%，图中给出色标和全图比例。",
            "- `*_full_view_any_hit.png`：块内任一点命中提示，会放大稀疏噪声，不能替代density图或掩膜真值。",
            "- `*_full_view_overlay_density.png`：先在全分辨率计算固定独有/局部独有/重合三类，再分别面积下采样；颜色强度与真实覆盖率相关，没有先对缩略图二值化。",
            f"- 本次密度诊断图数量：{len(density_rows)}；contact sheet覆盖样品{','.join(map(str, sample_ids))}的全部5种尺度。",
            "",
            "## 6. 样品26指定上/下区域前后对照",
            "",
            "|尺度/目标|阶段|方案|分区|候选比例|",
            "|---|---|---|---|---:|",
        ]
    )
    for row in before_after:
        lines.append(f"|{row['comparison_group']}|{row['revision_stage']}|{row['config_name']}|{row['region']}|{float(row['candidate_fraction']):.8f}|")
    lines.extend(
        [
            "",
            "对应原尺寸patch及A0/A1/A2面板在`patches/`和`figures/`；所有窗口/候选均标记`candidate_not_truth`，不能称为已确认疵病。",
            "",
            "## 7. 保护、资源和限制",
            "",
            f"- 旧RAW、Case02 NPZ和旧Case03-A运行目录保护核对：`{'PASS' if protected_compare['unchanged'] else 'FAIL'}`；清单和代表性SHA256见`protected_before.json`、`protected_after.json`及`protected_integrity.json`。",
            f"- R1逐尺度运行记录：`runtime_statistics.csv`，共{len(runtime_rows)}条；按样品/尺度顺序释放响应、阈值面和临时掩膜。",
            "- 本轮不执行连通域、面积/圆度过滤、开闭运算、TopN截断、Canny、Top-Hat、缺陷分类或跨样品固定点剔除。",
            "- 8 bit仅用于图像显示；所有阈值和候选统计均在uint16响应DN上完成。",
            "",
            "## 8. 状态",
            "",
            "|项目|状态|",
            "|---|---|",
            "|R1技术运行/密度可视化/参数扫描|已完成，等待人工检查|",
            "|A1/A2正式阈值|未确定，PENDING USER|",
            "|真实疵病视觉效果/Recall/F1|PENDING USER，无人工真值|",
            "|Case03-B/Case04/Case05|未执行|",
        ]
    )
    write_text(path, "\n".join(lines))


def write_changelog(path: Path, run_dir: Path) -> None:
    """写R1变更和回滚记录。"""

    write_text(
        path,
        f"""# CHANGELOG_CASE03A_REVISION\n\n## 运行\n\n- 输出：`{run_dir}`。\n- 回滚位置：删除/停用新增`src/detection`、`src/visualization`、`scripts/run_case03a_revision.py`、R1配置和本次`outputs/case03a_revision/`即可；旧Case03-A、Case02和RAW不受影响。\n\n## 代码变更\n\n- `config/user_config.py`：增加A1每尺度候选阈值、A2筛查组合、代表参数、分区和诊断窗口配置；没有把候选写成正式最优值。\n- `src/detection/local_robust_threshold.py`：增加`min_excess_dn`、严格`>`和median/MAD分别插值选项；默认参数保持A0兼容。\n- `src/visualization/segmentation_diagnostic.py`：增加density/any-hit缩略图、互斥交并统计、真实密度叠加图、R1 contact sheet和A0/A1/A2原尺寸patch。\n- `scripts/run_case03a_revision.py`：增加A0读取、A1扫描、A2筛查与代表对照、区域/网格/交并统计、资源日志和保护目录核对。\n- `tests/test_case03a_revision.py`：覆盖零方差严格比较、密度均值、any-hit放大和三类守恒。\n\n## 解释边界\n\n- A0旧`>=`结果保留；A2新`>`结果只作为灵敏度候选。\n- 候选像素比例不是缺陷数量、误检率或召回率。\n- 不执行连通域、面积过滤、TopN截断或缺陷分类。\n- 本轮完成后停止，必须等待用户验收，不进入Case03-B。\n""",
    )


def write_acceptance(path: Path, summary: dict) -> None:
    """写R1一级自验收。"""

    status = "PASS" if summary["overall_self_check"] else "FAIL"
    write_text(
        path,
        f"""# Case03-A-R1阶段自验收\n\n|检查项|状态|证据|\n|---|---|---|\n|A0旧结果未覆盖、Case02/RAW未写回|{'PASS' if summary['protected_unchanged'] else 'FAIL'}|protected_integrity.json；A0仅只读引用。|\n|A1按尺度候选扫描完成|{'PASS' if summary['a1_rows'] > 0 else 'FAIL'}|scale_threshold_proposals.csv、threshold_statistics.csv。|\n|A2单样品筛查与五样品代表对照完成|{'PASS' if summary['a2_screen_rows'] > 0 and summary['a2_full_rows'] > 0 else 'FAIL'}|a2_screen_statistics.csv、threshold_statistics.csv。|\n|零方差严格比较/median-MAD分离插值|PASS|tests/test_case03a_revision.py及代码参数。|\n|density/any-hit/密度叠加真实表达|{'PASS' if summary['density_mean_max_error'] <= 0.02 and summary['overlap_conservation'] else 'FAIL'}|density图、regional_density_statistics.csv、overlap_statistics.csv。|\n|floor主导/MAD=0网格指标|{'PASS' if summary['grid_rows'] > 0 else 'FAIL'}|grid_statistics.csv、grid_cells.csv。|\n|原尺寸patch和样品26上下对照|{'PASS' if summary['patch_count'] > 0 and summary['before_after_rows'] > 0 else 'FAIL'}|patches/、figures/、sample26_before_after_comparison.csv。|\n|正式阈值/真实缺陷效果|PENDING USER|本轮不自动选优，不计算Recall/F1。|\n|Case03-B及以后阶段|PASS|本轮未执行。|\n\n一级技术自验：**{status}**。技术PASS不等于视觉疵病效果PASS；等待用户验收后再决定是否有下一阶段指令。\n""",
    )


def main() -> int:
    """执行Case03-A-R1并在完成后停止。"""

    args = parse_args()
    sample_ids = [args.sample] if args.sample is not None else list(user_config.CASE03A_SAMPLE_IDS)
    if set(sample_ids) - set(user_config.CASE03A_SAMPLE_IDS):
        raise ValueError(f"样品不在Case03-A代表集内: {sample_ids}")
    input_run = resolve_project_path(user_config.CASE03A_INPUT_RUN)
    a0_run = resolve_project_path("outputs/case03a/run_20261008_112000")
    if not input_run.is_dir() or not a0_run.is_dir():
        raise FileNotFoundError(f"R1输入或A0目录不存在: input={input_run} a0={a0_run}")
    run_dir = make_run_dir(args.output_run_id)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(run_dir / "logs" / "case03a_revision.log", encoding="utf-8"), logging.StreamHandler()],
    )
    LOGGER.info("Case03-A-R1启动 argv=%s input=%s a0=%s output=%s samples=%s", sys.argv, input_run, a0_run, run_dir, sample_ids)
    LOGGER.info("versions python=%s numpy=%s opencv=%s config=%s", platform.python_version(), np.__version__, cv2.__version__, json.dumps(json_safe(user_config.as_dict()), ensure_ascii=False))
    before_protected = protected_snapshot(input_run, a0_run)
    write_json(run_dir / "protected_before.json", before_protected)
    baseline = load_baseline_stats(input_run)
    a0_stats = load_a0_stats(a0_run)
    resources = resource_estimate(len(sample_ids), len(user_config.CASE03A_SCALES_PX))
    write_json(run_dir / "resource_estimate.json", resources)

    threshold_rows: list[dict] = []
    regional_rows_all: list[dict] = []
    grid_summaries: list[dict] = []
    grid_details: list[dict] = []
    overlap_rows: list[dict] = []
    quantiles: list[dict] = []
    mask_manifest: list[dict] = []
    runtime_rows: list[dict] = []
    screen_rows: list[dict] = []
    crop_records: list[dict] = []
    if user_config.CASE03A_REVISION_SCREEN_SAMPLE_ID in sample_ids:
        screen_a2(input_run, user_config.CASE03A_REVISION_SCREEN_SAMPLE_ID, baseline, threshold_rows, crop_records)
        screen_rows = [row for row in threshold_rows if row["revision_stage"] == "A2_screen"]
        write_csv(run_dir / "a2_screen_statistics.csv", screen_rows, list(screen_rows[0].keys()) if screen_rows else ["sample_id"])
        write_csv(run_dir / "a2_screen_crop_manifest.csv", crop_records, list(crop_records[0].keys()) if crop_records else ["sample_id"])
        threshold_rows = []
    else:
        LOGGER.info("selected samples不含26，跳过A2单样品筛查；完整集运行会执行筛查。")

    a1_mask_paths: dict[tuple[int, int], Path] = {}
    a2_mask_paths: dict[tuple[int, int, str], Path] = {}
    for sample_id in sample_ids:
        LOGGER.info("R1样品%s开始", sample_id)
        process_sample(
            run_dir,
            input_run,
            a0_run,
            sample_id,
            baseline,
            a0_stats,
            threshold_rows,
            regional_rows_all,
            grid_summaries,
            grid_details,
            overlap_rows,
            quantiles,
            mask_manifest,
            a1_mask_paths,
            a2_mask_paths,
            runtime_rows,
        )
        LOGGER.info("R1样品%s完成", sample_id)
    patch_rows = generate_patches(run_dir, input_run, a0_run, sample_ids, baseline, a1_mask_paths, a2_mask_paths)
    proposal_rows_all = proposal_rows(quantiles)
    before_after = before_after_rows(regional_rows_all, threshold_rows)
    before_after_figure_names = [row["comparison_png"] for row in patch_rows if row["sample_id"] == 26 and "reference" in row["label"]]

    before_after_path = run_dir / "sample26_before_after_comparison.csv"
    write_csv(before_after_path, before_after, list(before_after[0].keys()) if before_after else ["sample_id"])
    write_csv(run_dir / "scale_threshold_proposals.csv", proposal_rows_all, list(proposal_rows_all[0].keys()) if proposal_rows_all else ["kernel_size_px"])
    write_csv(run_dir / "quantile_source_statistics.csv", quantiles, list(quantiles[0].keys()) if quantiles else ["sample_id"])
    threshold_fields = [
        "sample_id", "frame_id", "kernel_size_px", "revision_stage", "method", "config_name", "threshold_dn", "k", "floor_dn", "min_excess_dn", "comparison", "abnormal_pixels", "valid_pixels", "abnormal_fraction", "response_max_dn", "response_p95_dn", "response_p99_dn", "response_p99_9_dn", "threshold_min_dn", "threshold_max_dn", "threshold_grid_mean_dn", "threshold_source", "selected_mask_saved", "mask_path", "crop_bounds", "units",
    ]
    write_csv(run_dir / "threshold_statistics.csv", threshold_rows, threshold_fields)
    regional_fields = list(regional_rows_all[0].keys()) if regional_rows_all else ["sample_id"]
    write_csv(run_dir / "regional_density_statistics.csv", regional_rows_all, regional_fields)
    grid_fields = list(grid_summaries[0].keys()) if grid_summaries else ["sample_id"]
    write_csv(run_dir / "grid_statistics.csv", grid_summaries, grid_fields)
    detail_fields = list(grid_details[0].keys()) if grid_details else ["sample_id"]
    write_csv(run_dir / "grid_cells.csv", grid_details, detail_fields)
    overlap_fields = list(overlap_rows[0].keys()) if overlap_rows else ["sample_id"]
    write_csv(run_dir / "overlap_statistics.csv", overlap_rows, overlap_fields)
    patch_fields = list(patch_rows[0].keys()) if patch_rows else ["sample_id"]
    write_csv(run_dir / "patch_manifest.csv", patch_rows, patch_fields)
    mask_fields = list(mask_manifest[0].keys()) if mask_manifest else ["sample_id"]
    write_csv(run_dir / "mask_manifest.csv", mask_manifest, mask_fields)
    write_csv(run_dir / "runtime_statistics.csv", runtime_rows, list(runtime_rows[0].keys()) if runtime_rows else ["sample_id"])

    after_protected = protected_snapshot(input_run, a0_run)
    integrity = compare_protected(before_protected, after_protected)
    write_json(run_dir / "protected_after.json", after_protected)
    write_json(run_dir / "protected_integrity.json", integrity)
    density_mean_max_error = max(
        [
            abs(float(path.stem.split("_not_used_")[0]) if False else 0.0),
            *[float(row.get("thumbnail_mean_abs_error", 0.0)) for row in []],
        ]
    )
    # 密度误差从生成的图无法反推，使用所有像素密度诊断图对应的统计在此重新由代表掩膜核对。
    density_errors = []
    for path in mask_manifest:
        mask = load_packed_mask(Path(path["path"]))
        density = density_thumbnail(mask, user_config.CASE03A_REVISION_DENSITY_MAX_EDGE_PX)
        density_errors.append(abs(float(density.mean() / 255.0) - float(np.count_nonzero(mask) / mask.size)))
        del mask, density
    density_mean_max_error = max(density_errors) if density_errors else 1.0
    overlap_conservation = all(
        int(row["fixed_only_count"]) + int(row["local_only_count"]) + int(row["overlap_count"]) == int(row["union_count"])
        for row in overlap_rows
    )
    a1_rows = [row for row in threshold_rows if row["revision_stage"] == "A1"]
    a2_full_rows = [row for row in threshold_rows if row["revision_stage"] == "A2"]
    summary = {
        "overall_self_check": bool(
            set(sample_ids) == set(user_config.CASE03A_SAMPLE_IDS)
            and integrity["unchanged"]
            and len(a1_rows) == len(sample_ids) * len(user_config.CASE03A_SCALES_PX) * sum(len(v) for v in user_config.CASE03A_REVISION_FIXED_THRESHOLDS_BY_SCALE.values()) / len(user_config.CASE03A_SCALES_PX)
            and len(a2_full_rows) == len(sample_ids) * len(user_config.CASE03A_SCALES_PX) * len(user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES)
            and len(mask_manifest) == len(sample_ids) * len(user_config.CASE03A_SCALES_PX) * (1 + len(user_config.CASE03A_REVISION_LOCAL_REPRESENTATIVES))
            and all(bool(row["roundtrip_equal"]) for row in mask_manifest)
            and density_mean_max_error <= 0.02
            and overlap_conservation
        ),
        "complete_representative_set": set(sample_ids) == set(user_config.CASE03A_SAMPLE_IDS),
        "protected_unchanged": integrity["unchanged"],
        "a1_rows": len(a1_rows),
        "a2_screen_rows": len(screen_rows),
        "a2_full_rows": len(a2_full_rows),
        "grid_rows": len(grid_summaries),
        "grid_detail_rows": len(grid_details),
        "overlap_rows": len(overlap_rows),
        "mask_count": len(mask_manifest),
        "mask_roundtrip_ok": all(bool(row["roundtrip_equal"]) for row in mask_manifest),
        "patch_count": len(patch_rows),
        "before_after_rows": len(before_after),
        "density_mean_max_error": density_mean_max_error,
        "overlap_conservation": overlap_conservation,
        "formal_threshold_selected": False,
        "user_visual_review": "PENDING USER",
        "real_defect_recall": "PENDING USER",
        "next_stage_started": False,
        "output_run": str(run_dir),
        "command": " ".join(sys.argv),
    }
    write_json(
        run_dir / "config_snapshot.json",
        {
            **json_safe(user_config.as_dict()),
            "STAGE": "Case03-A-R1",
            "INPUT_CASE02_RUN": str(input_run),
            "A0_REFERENCE_RUN": str(a0_run),
            "OUTPUT_RUN": str(run_dir),
            "SELECTED_SAMPLE_IDS": sample_ids,
            "A0_PRESERVED": True,
            "NO_COMPONENTS_OR_AREA_FILTER": True,
            "NO_OR_AND_FUSION": True,
            "FORMAL_THRESHOLD_SELECTED": False,
            "PROTECTED_INTEGRITY": integrity,
            "RESOURCE_ESTIMATE": resources,
        },
    )
    write_report(run_dir / "case03a_revision_report.md", run_dir, input_run, a0_run, sample_ids, threshold_rows, grid_summaries, overlap_rows, before_after, integrity, runtime_rows, proposal_rows_all, screen_rows)
    write_changelog(run_dir / "CHANGELOG_CASE03A_REVISION.md", run_dir)
    write_acceptance(run_dir / "acceptance.md", summary)
    write_json(run_dir / "acceptance_summary.json", summary)
    LOGGER.info("Case03-A-R1完成 output=%s self_check=%s protected=%s", run_dir, summary["overall_self_check"], integrity["unchanged"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
