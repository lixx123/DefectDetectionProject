"""仅用于显示的8 bit预览图写出。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def make_display_preview(image_dn: np.ndarray, effective_bits: int, max_size: int) -> np.ndarray:
    """把原始DN转换为8 bit显示预览并按最大边长缩小。

    输入为原始12 bit DN；输出为 `uint8`。转换只用于视觉检查，不返回或覆盖
    原始数组，也不得用于任何后续DN定量。映射为线性 `DN / (2**bits-1) * 255`。
    """

    max_dn = (1 << effective_bits) - 1
    preview = np.clip(image_dn.astype(np.float32) / max_dn * 255.0, 0, 255).round().astype(np.uint8)
    height, width = preview.shape
    scale = min(1.0, max_size / max(height, width))
    if scale < 1.0:
        resized = cv2.resize(
            preview,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
        return resized
    return preview


def save_preview(image_dn: np.ndarray, path: Path, effective_bits: int, max_size: int) -> dict:
    """保存8 bit PNG预览并返回输出信息。"""

    preview = make_display_preview(image_dn, effective_bits, max_size)
    # Windows 下 OpenCV 直接使用含中文的路径可能写出失败；先在内存编码，
    # 再由 pathlib 写入，可保留工程中文路径且不改变图像内容。
    encoded_ok, encoded = cv2.imencode(".png", preview)
    if not encoded_ok:
        raise IOError(f"预览图写入失败: {path}")
    path.write_bytes(encoded.tobytes())
    return {
        "path": str(path),
        "dtype": str(preview.dtype),
        "height": int(preview.shape[0]),
        "width": int(preview.shape[1]),
        "min_display": int(preview.min()),
        "max_display": int(preview.max()),
        "std_display": float(preview.std()),
    }
