"""多尺度Black-Hat逐尺度计算、融合和尺度胜出图。"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .blackhat import black_hat_uint16, response_statistics


def iter_scale_responses(
    image_dn: np.ndarray,
    kernel_sizes_px: Iterable[int],
    kernel_shape: str,
):
    """逐尺度生成`(kernel_size_px, response_uint16, statistics)`。

    调用方应在保存当前响应和统计后删除响应数组，再进入下一尺度，避免多张
    1亿像素响应图同时驻留内存。
    """

    for kernel_size_px in kernel_sizes_px:
        response = black_hat_uint16(image_dn, int(kernel_size_px), kernel_shape)
        yield int(kernel_size_px), response, response_statistics(response)


def fuse_max_responses(
    scale_responses: Iterable[tuple[int, np.ndarray]],
    shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """按逐像素最大值融合多尺度响应并记录胜出尺度。

    返回：`fused_uint16`和`winning_scale_map_uint8`。尺度图使用输入尺度列表的
    1-based索引，0表示没有任何正响应；并列最大值保留最先出现的尺度。
    """

    fused = np.zeros(shape, dtype=np.uint16)
    winning = np.zeros(shape, dtype=np.uint8)
    for index, (kernel_size_px, response) in enumerate(scale_responses, start=1):
        if response.shape != shape or response.dtype != np.uint16:
            raise ValueError("多尺度响应形状或dtype不一致")
        update = response > fused
        fused[update] = response[update]
        winning[update] = index
    return fused, winning
