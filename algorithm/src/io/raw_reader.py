"""260624 大端 RAW 读取和统计。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class RawReadConfig:
    """RAW解析所需参数。尺寸单位为像素，位深为bit。"""

    width: int
    height: int
    effective_bits: int
    endian: str = "big"

    @property
    def expected_bytes(self) -> int:
        """返回期望的文件字节数。"""

        return self.width * self.height * 2


def read_raw(path: Path, config: RawReadConfig) -> np.ndarray:
    """读取16 bit大端RAW并返回原始DN数组。

    输入：无文件头、每像素2字节的RAW文件。
    输出：形状为 `(height, width)`、dtype为原生 `uint16` 的数组；数组值仍是
    原始12 bit DN，不做8 bit压缩、Gamma或其他会改变定量意义的增强。
    目的：为后续所有统计和定量步骤提供可重复的原始DN输入。
    """

    actual_bytes = path.stat().st_size
    if actual_bytes != config.expected_bytes:
        raise ValueError(
            f"RAW文件大小不符: {path.name}, actual={actual_bytes}, expected={config.expected_bytes}"
        )
    dtype = np.dtype(">u2" if config.endian.lower() == "big" else "<u2")
    raw = np.fromfile(path, dtype=dtype)
    expected_pixels = config.width * config.height
    if raw.size != expected_pixels:
        raise ValueError(f"RAW像素数不符: {path.name}, actual={raw.size}, expected={expected_pixels}")
    return raw.astype(np.uint16, copy=False).reshape((config.height, config.width))


def summarize_raw(image: np.ndarray, config: RawReadConfig) -> dict:
    """计算原始DN体检统计，不使用显示预览参与计算。

    输出包含最小/最大值、均值、中位数、标准差、指定分位数和有效12 bit范围
    检查。所有DN指标单位均为原始 DN。
    """

    max_dn = (1 << config.effective_bits) - 1
    values = image.ravel()
    quantiles = np.percentile(values, [0.1, 1.0, 50.0, 99.0, 99.9])
    overflow_count = int(np.count_nonzero(values > max_dn))
    zero_count = int(np.count_nonzero(values == 0))
    saturated_count = int(np.count_nonzero(values == max_dn))
    return {
        "min_dn": int(values.min()),
        "max_dn": int(values.max()),
        "mean_dn": float(values.mean()),
        "median_dn": float(np.median(values)),
        "std_dn": float(values.std()),
        "p0_1_dn": float(quantiles[0]),
        "p1_dn": float(quantiles[1]),
        "p50_dn": float(quantiles[2]),
        "p99_dn": float(quantiles[3]),
        "p99_9_dn": float(quantiles[4]),
        "zero_count": zero_count,
        "saturated_4095_count": saturated_count,
        "overflow_gt_4095_count": overflow_count,
        "pixel_count": int(values.size),
        "finite": bool(np.isfinite(values).all()),
        "within_effective_range": bool(values.max() <= max_dn),
        "nonconstant": bool(values.min() != values.max()),
    }
