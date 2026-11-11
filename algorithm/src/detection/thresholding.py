"""Case03-A固定DN阈值、掩膜统计和无损packbits存取。"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def validate_response(response_dn: np.ndarray) -> None:
    """检查Case02 Black-Hat响应的二维uint16语义。"""

    if not isinstance(response_dn, np.ndarray) or response_dn.ndim != 2:
        raise TypeError("响应必须是二维numpy数组")
    if response_dn.dtype != np.uint16:
        raise TypeError(f"响应必须是uint16 DN数组，实际为{response_dn.dtype}")
    if not np.isfinite(response_dn).all():
        raise ValueError("响应包含非有限值")


def fixed_threshold_mask(response_dn: np.ndarray, threshold_dn: int) -> np.ndarray:
    """按`response_dn >= threshold_dn`生成全分辨率布尔掩膜。

    输入响应单位为Black-Hat DN，不接受8 bit PNG；等于阈值的像素明确保留。
    """

    validate_response(response_dn)
    if not isinstance(threshold_dn, (int, np.integer)):
        raise TypeError("固定DN阈值必须为整数")
    if threshold_dn < 0 or threshold_dn > np.iinfo(np.uint16).max:
        raise ValueError(f"固定DN阈值超出uint16范围: {threshold_dn}")
    return response_dn >= int(threshold_dn)


def mask_statistics(mask: np.ndarray) -> dict:
    """返回全分辨率二值掩膜统计，不执行连通域或候选裁剪。"""

    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.bool_:
        raise TypeError("掩膜统计要求二维bool数组")
    valid_pixels = int(mask.size)
    abnormal_pixels = int(np.count_nonzero(mask))
    return {
        "abnormal_pixels": abnormal_pixels,
        "valid_pixels": valid_pixels,
        "abnormal_fraction": float(abnormal_pixels / valid_pixels),
        "shape": [int(mask.shape[0]), int(mask.shape[1])],
        "dtype": str(mask.dtype),
    }


def pack_mask(mask: np.ndarray, bitorder: str = "little") -> np.ndarray:
    """将二维bool掩膜按行展平并packbits，保留全像素信息。"""

    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.bool_:
        raise TypeError("pack_mask要求二维bool数组")
    if bitorder not in {"little", "big"}:
        raise ValueError(f"不支持的bitorder: {bitorder}")
    return np.packbits(mask.reshape(-1), bitorder=bitorder)


def restore_packed_mask(
    packed: np.ndarray,
    shape: tuple[int, int] | list[int],
    bitorder: str = "little",
) -> np.ndarray:
    """从packbits数组无损还原二维bool掩膜并裁去补齐位。"""

    if not isinstance(packed, np.ndarray) or packed.ndim != 1 or packed.dtype != np.uint8:
        raise TypeError("packed掩膜必须是一维uint8数组")
    if len(shape) != 2 or int(shape[0]) <= 0 or int(shape[1]) <= 0:
        raise ValueError(f"非法掩膜shape: {shape}")
    if bitorder not in {"little", "big"}:
        raise ValueError(f"不支持的bitorder: {bitorder}")
    pixels = int(shape[0]) * int(shape[1])
    restored = np.unpackbits(packed, bitorder=bitorder)[:pixels]
    return restored.astype(bool, copy=False).reshape((int(shape[0]), int(shape[1])))


def save_packed_mask(path: Path, mask: np.ndarray, bitorder: str = "little") -> dict:
    """压缩保存掩膜、shape和bitorder，并返回可写入manifest的元数据。"""

    packed = pack_mask(mask, bitorder)
    np.savez_compressed(
        path,
        mask_packed=packed,
        mask_shape=np.asarray(mask.shape, dtype=np.int64),
        bitorder=np.asarray(bitorder),
    )
    return {
        "path": str(path),
        "shape": [int(mask.shape[0]), int(mask.shape[1])],
        "original_dtype": "bool",
        "packed_dtype": str(packed.dtype),
        "bitorder": bitorder,
        "raw_mask_bytes": int(mask.size),
        "packed_bytes": int(packed.nbytes),
        "file_bytes": int(path.stat().st_size),
    }


def load_packed_mask(path: Path) -> np.ndarray:
    """读取Case03-A掩膜文件并无损还原。"""

    with np.load(path, allow_pickle=False) as data:
        packed = np.asarray(data["mask_packed"])
        shape = tuple(int(value) for value in np.asarray(data["mask_shape"]).tolist())
        bitorder = str(np.asarray(data["bitorder"]).item())
    return restore_packed_mask(packed, shape, bitorder)
