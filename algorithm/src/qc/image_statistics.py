"""Case00直方图和统计结果输出。"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def compute_histogram(image: np.ndarray, effective_bits: int) -> tuple[np.ndarray, int]:
    """计算原始DN直方图和溢出像素数。

    直方图覆盖 `0..2**effective_bits-1` 的原始DN；超出有效位深的值不被
    截断，而是单独返回，便于识别字节序或采集异常。
    """

    max_dn = (1 << effective_bits) - 1
    values = image.ravel()
    histogram = np.bincount(values[values <= max_dn], minlength=max_dn + 1)[: max_dn + 1]
    overflow = int(np.count_nonzero(values > max_dn))
    return histogram.astype(np.int64), overflow


def save_histogram_csv(path: Path, histogram: np.ndarray, overflow: int, frame_key: str) -> None:
    """追加写出单帧直方图CSV，计数单位为pixel。"""

    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        if path.stat().st_size == 0:
            handle.write("frame_key,dn,count\n")
        for dn, count in enumerate(histogram):
            handle.write(f"{frame_key},{dn},{int(count)}\n")
        handle.write(f"{frame_key},OVERFLOW_GT_EFFECTIVE_MAX,{overflow}\n")
