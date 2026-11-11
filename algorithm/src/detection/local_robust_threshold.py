"""Case03-A局部Median/MAD鲁棒阈值面。"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from .thresholding import validate_response


ROBUST_MAD_SCALE = 1.4826


def _grid_bounds(length: int, grid_size_px: int) -> list[tuple[int, int]]:
    """返回完整覆盖一维图像的网格边界，最后一个网格允许不足整格。"""

    if length <= 0 or grid_size_px <= 0:
        raise ValueError("图像长度和网格尺寸必须为正数")
    return [(start, min(start + grid_size_px, length)) for start in range(0, length, grid_size_px)]


def _grid_centers(bounds: list[tuple[int, int]]) -> np.ndarray:
    """以像素坐标表示网格中心，边缘网格也有确定中心。"""

    return np.asarray([(start + end - 1) / 2.0 for start, end in bounds], dtype=np.float32)


def compute_local_grid_statistics(
    response_dn: np.ndarray,
    grid_size_px: int = 256,
    sample_stride_px: int = 4,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """按网格抽样计算局部中位数和MAD。

    抽样只用于估计阈值面；最终掩膜仍逐像素比较完整分辨率响应。每个网格的
    起止坐标和抽样数量都会返回，便于复核边界覆盖和MAD=0情况。
    """

    validate_response(response_dn)
    if int(grid_size_px) <= 0 or int(sample_stride_px) <= 0:
        raise ValueError("grid_size_px和sample_stride_px必须为正整数")
    grid_size_px = int(grid_size_px)
    sample_stride_px = int(sample_stride_px)
    height, width = response_dn.shape
    y_bounds = _grid_bounds(height, grid_size_px)
    x_bounds = _grid_bounds(width, grid_size_px)
    medians = np.empty((len(y_bounds), len(x_bounds)), dtype=np.float32)
    mads = np.empty_like(medians)
    rows: list[dict] = []
    for grid_row, (y_start, y_end) in enumerate(y_bounds):
        for grid_col, (x_start, x_end) in enumerate(x_bounds):
            samples = response_dn[y_start:y_end:sample_stride_px, x_start:x_end:sample_stride_px].reshape(-1)
            if samples.size == 0:
                raise RuntimeError("局部统计网格出现空抽样")
            median_dn = float(np.median(samples))
            mad_dn = float(np.median(np.abs(samples.astype(np.float32) - median_dn)))
            medians[grid_row, grid_col] = median_dn
            mads[grid_row, grid_col] = mad_dn
            rows.append(
                {
                    "grid_row": grid_row,
                    "grid_col": grid_col,
                    "y_start_px": y_start,
                    "y_end_px": y_end,
                    "x_start_px": x_start,
                    "x_end_px": x_end,
                    "center_y_px": (y_start + y_end - 1) / 2.0,
                    "center_x_px": (x_start + x_end - 1) / 2.0,
                    "sample_count": int(samples.size),
                    "median_dn": median_dn,
                    "mad_dn": mad_dn,
                    "robust_sigma_dn": ROBUST_MAD_SCALE * mad_dn,
                }
            )
    return medians, mads, rows


def _interpolate_grid_strip(
    grid: np.ndarray,
    y_centers: np.ndarray,
    x_centers: np.ndarray,
    y_start: int,
    y_end: int,
    width: int,
) -> np.ndarray:
    """对一个像素条带做双线性插值，边缘坐标采用最近网格中心值。"""

    if grid.shape != (len(y_centers), len(x_centers)):
        raise ValueError("grid与中心坐标长度不一致")
    ys = np.arange(y_start, y_end, dtype=np.float32)
    xs = np.arange(width, dtype=np.float32)
    if len(y_centers) == 1:
        y0 = y1 = np.zeros_like(ys, dtype=np.int64)
        wy = np.zeros_like(ys)
    else:
        y_clipped = np.clip(ys, y_centers[0], y_centers[-1])
        y0 = np.searchsorted(y_centers, y_clipped, side="right") - 1
        y0 = np.clip(y0, 0, len(y_centers) - 2)
        y1 = y0 + 1
        denominator = y_centers[y1] - y_centers[y0]
        wy = (y_clipped - y_centers[y0]) / np.where(denominator == 0, 1, denominator)
    if len(x_centers) == 1:
        x0 = x1 = np.zeros_like(xs, dtype=np.int64)
        wx = np.zeros_like(xs)
    else:
        x_clipped = np.clip(xs, x_centers[0], x_centers[-1])
        x0 = np.searchsorted(x_centers, x_clipped, side="right") - 1
        x0 = np.clip(x0, 0, len(x_centers) - 2)
        x1 = x0 + 1
        denominator = x_centers[x1] - x_centers[x0]
        wx = (x_clipped - x_centers[x0]) / np.where(denominator == 0, 1, denominator)

    top = grid[y0[:, None], x0[None, :]] * (1.0 - wx[None, :]) + grid[y0[:, None], x1[None, :]] * wx[None, :]
    bottom = grid[y1[:, None], x0[None, :]] * (1.0 - wx[None, :]) + grid[y1[:, None], x1[None, :]] * wx[None, :]
    return (top * (1.0 - wy[:, None]) + bottom * wy[:, None]).astype(np.float32, copy=False)


def iter_local_threshold_strips(
    response_dn: np.ndarray,
    medians: np.ndarray,
    mads: np.ndarray,
    k: float,
    floor_dn: int,
    grid_size_px: int = 256,
    stripe_rows_px: int = 256,
    min_excess_dn: float = 0.0,
    strict: bool = False,
    interpolate_components: bool = False,
) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """逐条带生成`(y0,y1,threshold_surface,mask)`，避免常驻整图float阈值面。

    默认保持Case03-A旧版A0语义：`max(floor, median+kσ)`并使用`>=`。
    Case03-A-R1可传入`min_excess_dn`并将`strict=True`，此时阈值为
    `max(floor, median+max(kσ,min_excess_dn))`，使用严格`response > threshold`，
    防止恒定非零背景因响应等于局部median而整幅入选。若同时传入
    `interpolate_components=True`，则先分别插值median/MAD连续场，再计算公式；
    默认False保留A0旧版“先算网格阈值再插值”的兼容语义。
    """

    validate_response(response_dn)
    if medians.ndim != 2 or mads.shape != medians.shape:
        raise ValueError("medians/mads必须是同shape二维网格")
    if not np.isfinite(float(k)) or float(k) < 0:
        raise ValueError("k必须为非负有限数")
    if int(floor_dn) < 0 or int(floor_dn) > np.iinfo(np.uint16).max:
        raise ValueError("floor_dn超出uint16范围")
    if not np.isfinite(float(min_excess_dn)) or float(min_excess_dn) < 0:
        raise ValueError("min_excess_dn必须为非负有限数")
    if int(grid_size_px) <= 0 or int(stripe_rows_px) <= 0:
        raise ValueError("grid_size_px和stripe_rows_px必须为正数")
    height, width = response_dn.shape
    y_bounds = _grid_bounds(height, int(grid_size_px))
    x_bounds = _grid_bounds(width, int(grid_size_px))
    y_centers = _grid_centers(y_bounds)
    x_centers = _grid_centers(x_bounds)
    if not interpolate_components:
        excess_grid = np.maximum(
            float(k) * ROBUST_MAD_SCALE * mads,
            float(min_excess_dn),
        )
        threshold_grid = np.maximum(float(floor_dn), medians + excess_grid).astype(np.float32)
    for y_start in range(0, height, int(stripe_rows_px)):
        y_end = min(height, y_start + int(stripe_rows_px))
        if interpolate_components:
            median_surface = _interpolate_grid_strip(medians, y_centers, x_centers, y_start, y_end, width)
            mad_surface = _interpolate_grid_strip(mads, y_centers, x_centers, y_start, y_end, width)
            threshold = np.maximum(
                float(floor_dn),
                median_surface + np.maximum(
                    float(k) * ROBUST_MAD_SCALE * mad_surface,
                    float(min_excess_dn),
                ),
            ).astype(np.float32, copy=False)
        else:
            threshold = _interpolate_grid_strip(threshold_grid, y_centers, x_centers, y_start, y_end, width)
        if strict:
            mask = response_dn[y_start:y_end] > threshold
        else:
            mask = response_dn[y_start:y_end] >= threshold
        yield y_start, y_end, threshold, mask


def local_threshold_mask(
    response_dn: np.ndarray,
    k: float,
    floor_dn: int,
    grid_size_px: int = 256,
    sample_stride_px: int = 4,
    min_excess_dn: float = 0.0,
    strict: bool = False,
    interpolate_components: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """计算小图或主方案的完整局部鲁棒阈值掩膜。

    默认公式为`max(floor_dn, median_local + k*1.4826*MAD_local)`并使用`>=`。
    传入`min_excess_dn`和`strict=True`即可使用Case03-A-R1的严格超额公式。
    大图主流程应使用`compute_local_grid_statistics`和`iter_local_threshold_strips`逐条带处理。
    """

    medians, mads, grid_rows = compute_local_grid_statistics(response_dn, grid_size_px, sample_stride_px)
    mask = np.empty(response_dn.shape, dtype=bool)
    for y_start, y_end, _threshold, strip_mask in iter_local_threshold_strips(
        response_dn,
        medians,
        mads,
        k,
        floor_dn,
        grid_size_px,
        stripe_rows_px=grid_size_px,
        min_excess_dn=min_excess_dn,
        strict=strict,
        interpolate_components=interpolate_components,
    ):
        mask[y_start:y_end] = strip_mask
    return mask, medians, mads, grid_rows


def grid_threshold_values(medians: np.ndarray, mads: np.ndarray, k: float, floor_dn: int) -> np.ndarray:
    """返回网格中心处的阈值，用于阈值分布摘要和显示。"""

    if medians.shape != mads.shape:
        raise ValueError("medians/mads必须同shape")
    return np.maximum(float(floor_dn), medians + float(k) * ROBUST_MAD_SCALE * mads).astype(np.float32)


def revised_grid_threshold_values(
    medians: np.ndarray,
    mads: np.ndarray,
    k: float,
    floor_dn: int,
    min_excess_dn: float,
) -> np.ndarray:
    """返回Case03-A-R1连续阈值网格，不执行像素比较。"""

    if medians.shape != mads.shape:
        raise ValueError("medians/mads必须同shape")
    if not np.isfinite(float(min_excess_dn)) or float(min_excess_dn) < 0:
        raise ValueError("min_excess_dn必须为非负有限数")
    excess = np.maximum(float(k) * ROBUST_MAD_SCALE * mads, float(min_excess_dn))
    return np.maximum(float(floor_dn), medians + excess).astype(np.float32)
