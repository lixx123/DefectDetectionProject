"""Black-Hat响应显示和Top-N patch提取。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np

from src.io.image_writer import make_display_preview


def _write_png(image: np.ndarray, path: Path) -> None:
    """兼容Windows中文路径地编码并写出PNG。"""

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise IOError(f"PNG编码失败: {path}")
    path.write_bytes(encoded.tobytes())


def _save_response_preview_range(
    response_dn: np.ndarray,
    path: Path,
    low_dn: float,
    high_dn: float,
) -> dict:
    """按给定DN范围保存响应显示图；范围只影响PNG显示。"""

    if high_dn <= low_dn:
        high_dn = low_dn + 1.0
    display = np.clip((response_dn.astype(np.float32) - low_dn) / (high_dn - low_dn) * 255.0, 0, 255).astype(np.uint8)
    _write_png(display, path)
    return {"path": str(path), "display_low_dn": float(low_dn), "display_high_dn": float(high_dn)}


def save_response_preview(
    response_dn: np.ndarray,
    path: Path,
    percentile_low: float,
    percentile_high: float,
) -> dict:
    """保存Black-Hat响应8 bit显示图，定量数组不被修改。"""

    values = response_dn.ravel()
    low = float(np.percentile(values, percentile_low))
    high = float(np.percentile(values, percentile_high))
    if high <= low:
        high = float(values.max())
    if high <= low:
        high = low + 1.0
    return _save_response_preview_range(response_dn, path, low, high)


def save_winning_scale_preview(winning_scale: np.ndarray, path: Path, scale_count: int) -> None:
    """保存尺度胜出图的离散伪彩色预览；原始尺度图另存为NPZ。"""

    if winning_scale.dtype != np.uint8:
        raise TypeError("winning_scale必须为uint8")
    normalized = np.clip(winning_scale.astype(np.float32) / max(1, scale_count) * 255.0, 0, 255).astype(np.uint8)
    color = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
    color[winning_scale == 0] = 0
    _write_png(color, path)


def save_raw_preview_patch(image_dn: np.ndarray, path: Path, effective_bits: int) -> None:
    """保存原始DN patch的8 bit显示图；不保存为定量输入。"""

    _write_png(make_display_preview(image_dn, effective_bits, max(image_dn.shape)), path)


def _write_patch_arrays(
    patch_dir: Path,
    index: int,
    original_patch_dn: np.ndarray,
    blackhat_patch_dn: np.ndarray,
    winning_patch: np.ndarray,
    effective_bits: int,
    blackhat_low: float,
    blackhat_high: float,
    center_x: int,
    center_y: int,
    peak_dn: int,
    winning_kernel_size_px: int,
) -> dict:
    """保存单个Top patch的原始DN、响应DN和显示图。"""

    stem = f"patch_{index:02d}"
    np.savez_compressed(patch_dir / f"{stem}_original_dn.npz", original_dn=original_patch_dn)
    np.savez_compressed(patch_dir / f"{stem}_blackhat_dn.npz", blackhat_dn=blackhat_patch_dn)
    np.savez_compressed(patch_dir / f"{stem}_winning_scale.npz", winning_scale=winning_patch)
    save_raw_preview_patch(original_patch_dn, patch_dir / f"{stem}_original_preview.png", effective_bits)
    _save_response_preview_range(
        blackhat_patch_dn,
        patch_dir / f"{stem}_blackhat_preview.png",
        blackhat_low,
        blackhat_high,
    )
    high_level = float(np.percentile(blackhat_patch_dn, 99.0))
    high_pixels = blackhat_patch_dn >= high_level
    row_fraction = float(high_pixels.sum(axis=1).max() / high_pixels.shape[1])
    col_fraction = float(high_pixels.sum(axis=0).max() / high_pixels.shape[0])
    if max(row_fraction, col_fraction) >= 0.5:
        review_category = "boundary_like_proxy"
    elif int(np.count_nonzero(blackhat_patch_dn)) > 0:
        review_category = "local_response_proxy"
    else:
        review_category = "manual_review_required"
    return {
        "patch_id": index,
        "center_x_px": center_x,
        "center_y_px": center_y,
        "peak_response_dn": peak_dn,
        "winning_kernel_size_px": winning_kernel_size_px,
        "row_high_response_fraction": row_fraction,
        "col_high_response_fraction": col_fraction,
        "review_category_proxy": review_category,
        "original_dn_npz": str(patch_dir / f"{stem}_original_dn.npz"),
        "blackhat_dn_npz": str(patch_dir / f"{stem}_blackhat_dn.npz"),
        "winning_scale_npz": str(patch_dir / f"{stem}_winning_scale.npz"),
        "original_preview": str(patch_dir / f"{stem}_original_preview.png"),
        "blackhat_preview": str(patch_dir / f"{stem}_blackhat_preview.png"),
    }


def extract_top_patches(
    original_dn: np.ndarray,
    fused_response_dn: np.ndarray,
    winning_scale: np.ndarray,
    kernel_sizes_px: list[int],
    patch_dir: Path,
    top_count: int,
    patch_size_px: int,
    min_distance_px: int,
    effective_bits: int,
    preview_low: float,
    preview_high: float,
) -> list[dict]:
    """从融合响应提取带最小距离约束的Top-N patch。

    Top-N仅供人工观察；候选的响应峰值来自原始`uint16` Black-Hat数组，不能
    直接解释为最终缺陷判定。
    """

    if patch_size_px <= 0 or patch_size_px % 2 != 0:
        raise ValueError("patch_size_px必须为正偶数")
    patch_dir.mkdir(parents=True, exist_ok=True)
    height, width = fused_response_dn.shape
    half = patch_size_px // 2
    # 使用uint16工作副本，避免为了屏蔽候选额外占用一张400 MB的float32图。
    working = fused_response_dn.copy()
    working[:half, :] = 0
    working[height - half :, :] = 0
    working[:, :half] = 0
    working[:, width - half :] = 0
    patch_rows: list[dict] = []
    blackhat_values = fused_response_dn.ravel()
    global_low = float(np.percentile(blackhat_values, preview_low))
    global_high = float(np.percentile(blackhat_values, preview_high))
    if global_high <= global_low:
        global_high = max(global_low + 1.0, float(blackhat_values.max()))

    for index in range(1, top_count + 1):
        flat_index = int(np.argmax(working))
        peak = float(working.ravel()[flat_index])
        if peak <= 0:
            break
        center_y, center_x = np.unravel_index(flat_index, working.shape)
        y0, y1 = center_y - half, center_y + half
        x0, x1 = center_x - half, center_x + half
        original_patch = original_dn[y0:y1, x0:x1]
        blackhat_patch = fused_response_dn[y0:y1, x0:x1]
        winning_patch = winning_scale[y0:y1, x0:x1]
        winning_index = int(winning_scale[center_y, center_x])
        winning_kernel = kernel_sizes_px[winning_index - 1] if winning_index > 0 else 0
        patch_rows.append(
            _write_patch_arrays(
                patch_dir,
                index,
                original_patch,
                blackhat_patch,
                winning_patch,
                effective_bits,
                global_low,
                global_high,
                int(center_x),
                int(center_y),
                int(peak),
                int(winning_kernel),
            )
        )
        yy, xx = np.ogrid[:height, :width]
        suppression = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= min_distance_px**2
        working[suppression] = 0

    with (patch_dir / "top_patches.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "patch_id", "center_x_px", "center_y_px", "peak_response_dn",
            "winning_kernel_size_px", "row_high_response_fraction", "col_high_response_fraction",
            "review_category_proxy", "original_dn_npz", "blackhat_dn_npz",
            "winning_scale_npz", "original_preview", "blackhat_preview",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(patch_rows)
    return patch_rows
