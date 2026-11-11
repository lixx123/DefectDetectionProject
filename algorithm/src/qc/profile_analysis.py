"""行/列平均曲线计算和可视化。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def compute_profiles(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """从原始DN图计算行平均和列平均曲线，单位为DN。"""

    row_mean = image.mean(axis=1, dtype=np.float64)
    col_mean = image.mean(axis=0, dtype=np.float64)
    return row_mean, col_mean


def save_profiles(
    row_mean: np.ndarray,
    col_mean: np.ndarray,
    csv_path: Path,
    plot_path: Path,
    frame_title: str,
    dpi: int,
) -> None:
    """保存行/列平均CSV和双面板PNG曲线。"""

    with csv_path.open("w", encoding="utf-8-sig") as handle:
        handle.write("row_index,row_mean_dn\n")
        for index, value in enumerate(row_mean):
            handle.write(f"{index},{value:.8f}\n")
        handle.write("\ncol_index,col_mean_dn\n")
        for index, value in enumerate(col_mean):
            handle.write(f"{index},{value:.8f}\n")

    figure, axes = plt.subplots(2, 1, figsize=(14, 7), constrained_layout=True)
    axes[0].plot(np.arange(row_mean.size), row_mean, linewidth=0.6)
    axes[0].set_title(f"{frame_title} - row mean DN")
    axes[0].set_xlabel("row index")
    axes[0].set_ylabel("mean DN")
    axes[1].plot(np.arange(col_mean.size), col_mean, linewidth=0.6)
    axes[1].set_title(f"{frame_title} - column mean DN")
    axes[1].set_xlabel("column index")
    axes[1].set_ylabel("mean DN")
    figure.savefig(plot_path, dpi=dpi)
    plt.close(figure)
