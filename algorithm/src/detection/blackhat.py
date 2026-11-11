"""基于原始12 bit DN的形态学 Black-Hat 暗异常增强。"""

from __future__ import annotations

import cv2
import numpy as np


def create_structuring_element(kernel_size_px: int, shape: str = "ellipse") -> np.ndarray:
    """创建Black-Hat结构元。

    `kernel_size_px`是像素单位的奇数尺寸；`shape`当前支持`ellipse`、`rect`和
    `cross`。返回值只描述形态学邻域，不涉及灰度单位。
    """

    if kernel_size_px <= 0 or kernel_size_px % 2 == 0:
        raise ValueError(f"Black-Hat结构元尺寸必须为正奇数: {kernel_size_px}")
    shapes = {
        "ellipse": cv2.MORPH_ELLIPSE,
        "rect": cv2.MORPH_RECT,
        "cross": cv2.MORPH_CROSS,
    }
    if shape not in shapes:
        raise ValueError(f"不支持的结构元形状: {shape}")
    return cv2.getStructuringElement(shapes[shape], (kernel_size_px, kernel_size_px))


def black_hat_uint16(image_dn: np.ndarray, kernel_size_px: int, shape: str = "ellipse") -> np.ndarray:
    """对单张原始12 bit DN图计算一个尺度的Black-Hat响应。

    输入：二维`uint16`原始DN数组，不允许是8 bit显示图或增强图。
    输出：二维`uint16`非负DN差值数组，定义为
    `Closing(image_dn) - image_dn`，单位仍为DN。响应只用于定位暗点/暗线，
    不代表最终缺陷判定。
    """

    if image_dn.ndim != 2 or image_dn.dtype != np.uint16:
        raise TypeError(f"Black-Hat输入必须是二维uint16原始DN数组: shape={image_dn.shape}, dtype={image_dn.dtype}")
    kernel = create_structuring_element(kernel_size_px, shape)
    closed = cv2.morphologyEx(image_dn, cv2.MORPH_CLOSE, kernel)
    # cv2.subtract按饱和规则计算，避免uint16减法下溢；理论上closing不低于原图。
    response = cv2.subtract(closed, image_dn)
    if response.dtype != np.uint16 or response.min() < 0:
        raise RuntimeError("Black-Hat响应dtype或非负约束失败")
    return response


def response_statistics(response_dn: np.ndarray) -> dict:
    """统计Black-Hat原始DN响应，不使用显示PNG。

    返回min/max/mean/median/std、p90/p95/p99/p99.5/p99.9和非零比例，所有
    数值的灰度单位均为DN。
    """

    if response_dn.ndim != 2 or response_dn.dtype != np.uint16:
        raise TypeError("响应统计要求二维uint16数组")
    values = response_dn.ravel()
    percentiles = np.percentile(values, [90, 95, 99, 99.5, 99.9])
    return {
        "min": int(values.min()),
        "max": int(values.max()),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "std": float(values.std()),
        "p90": float(percentiles[0]),
        "p95": float(percentiles[1]),
        "p99": float(percentiles[2]),
        "p99_5": float(percentiles[3]),
        "p99_9": float(percentiles[4]),
        "nonzero_fraction": float(np.count_nonzero(values) / values.size),
        "finite": bool(np.isfinite(values).all()),
        "nonnegative": bool(values.min() >= 0),
        "dtype": str(response_dn.dtype),
    }


def estimate_memory_bytes(width: int, height: int) -> dict:
    """估算逐尺度处理时的主要数组内存，单位为Byte。

    估算假设原始图、closing临时数组、单尺度响应和融合响应同时存在；不把
    五个尺度响应同时常驻内存。实际OpenCV内部工作区可能额外占用内存。
    """

    pixels = width * height
    raw_uint16 = pixels * np.dtype(np.uint16).itemsize
    winner_uint8 = pixels * np.dtype(np.uint8).itemsize
    return {
        "pixels": pixels,
        "raw_uint16_bytes": raw_uint16,
        "closing_uint16_bytes": raw_uint16,
        "single_response_uint16_bytes": raw_uint16,
        "fused_uint16_bytes": raw_uint16,
        "winning_scale_uint8_bytes": winner_uint8,
        "estimated_peak_bytes": raw_uint16 * 4 + winner_uint8,
        "estimated_peak_mib": (raw_uint16 * 4 + winner_uint8) / (1024 * 1024),
        "strategy": "sequential_scale_release",
    }
