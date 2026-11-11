"""Case03-A阈值掩膜显示、全图联系图和原始尺寸patch诊断。"""

from __future__ import annotations

from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

matplotlib.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False


def write_png(image: np.ndarray, path: Path) -> None:
    """使用内存编码写PNG，兼容Windows中文路径。"""

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise IOError(f"PNG编码失败: {path}")
    path.write_bytes(encoded.tobytes())


def resize_display(image: np.ndarray, max_edge_px: int) -> np.ndarray:
    """仅为显示缩放，不作为掩膜真值。"""

    if max(image.shape[:2]) <= max_edge_px:
        return image.copy()
    scale = max_edge_px / max(image.shape[:2])
    return cv2.resize(
        image,
        (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )


def response_preview(response_dn: np.ndarray, high_dn: float, max_edge_px: int) -> np.ndarray:
    """按DN上限生成Black-Hat显示图；不参与定量。"""

    high_dn = max(float(high_dn), 1.0)
    display = cv2.convertScaleAbs(response_dn, alpha=255.0 / high_dn, beta=0)
    return resize_display(display, max_edge_px)


def mask_preview(mask: np.ndarray, max_edge_px: int) -> np.ndarray:
    """生成二值掩膜缩略图，白色表示异常像素。"""

    if mask.ndim != 2 or mask.dtype != np.bool_:
        raise TypeError("mask_preview要求二维bool掩膜")
    display = (mask.astype(np.uint8) * 255)
    return resize_display(display, max_edge_px)


def _thumbnail_shape(shape: tuple[int, int], max_edge_px: int) -> tuple[int, int]:
    """返回显示缩略图的(height,width)，不改变原始掩膜。"""

    height, width = int(shape[0]), int(shape[1])
    if height <= 0 or width <= 0 or max_edge_px <= 0:
        raise ValueError("图像尺寸和max_edge_px必须为正数")
    scale = min(1.0, float(max_edge_px) / max(height, width))
    return max(1, round(height * scale)), max(1, round(width * scale))


def density_thumbnail(mask: np.ndarray, max_edge_px: int) -> np.ndarray:
    """按面积平均生成真实候选覆盖率图，灰度0~255对应0~100%。

    输入为全分辨率bool掩膜；每个输出像素是其对应原始区域的平均覆盖率。
    与`mask_preview`不同，本函数不会把缩略区域内的单个命中扩成满色像素。
    """

    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.bool_:
        raise TypeError("density_thumbnail要求二维bool掩膜")
    target_height, target_width = _thumbnail_shape(mask.shape, max_edge_px)
    if (target_height, target_width) == mask.shape:
        density = mask.astype(np.float32)
    else:
        density = cv2.resize(
            mask.astype(np.float32),
            (target_width, target_height),
            interpolation=cv2.INTER_AREA,
        )
    return np.clip(np.rint(density * 255.0), 0, 255).astype(np.uint8)


def any_hit_thumbnail(mask: np.ndarray, max_edge_px: int) -> np.ndarray:
    """生成“缩略区域内任一点命中”的提示图；该模式会放大稀疏噪声。"""

    if not isinstance(mask, np.ndarray) or mask.ndim != 2 or mask.dtype != np.bool_:
        raise TypeError("any_hit_thumbnail要求二维bool掩膜")
    target_height, target_width = _thumbnail_shape(mask.shape, max_edge_px)
    if (target_height, target_width) == mask.shape:
        return mask.astype(np.uint8) * 255
    # 对0/255图做面积缩放后只判断是否大于0，相当于块内any-hit。
    pooled = cv2.resize(
        mask.astype(np.uint8) * 255,
        (target_width, target_height),
        interpolation=cv2.INTER_AREA,
    )
    return (pooled > 0).astype(np.uint8) * 255


def mask_overlap_statistics(fixed_mask: np.ndarray, local_mask: np.ndarray) -> dict:
    """在全分辨率上计算三个互斥类别和并集守恒统计。"""

    if fixed_mask.dtype != np.bool_ or local_mask.dtype != np.bool_ or fixed_mask.shape != local_mask.shape:
        raise TypeError("固定/局部掩膜必须是同shape二维bool数组")
    fixed_only = fixed_mask & ~local_mask
    local_only = local_mask & ~fixed_mask
    overlap = fixed_mask & local_mask
    union = fixed_mask | local_mask
    total = int(union.size)
    counts = {
        "fixed_only_count": int(np.count_nonzero(fixed_only)),
        "local_only_count": int(np.count_nonzero(local_only)),
        "overlap_count": int(np.count_nonzero(overlap)),
        "union_count": int(np.count_nonzero(union)),
        "total_pixels": total,
    }
    if counts["fixed_only_count"] + counts["local_only_count"] + counts["overlap_count"] != counts["union_count"]:
        raise AssertionError("固定/局部三类互斥统计不守恒")
    counts.update(
        {
            "fixed_only_fraction": counts["fixed_only_count"] / total,
            "local_only_fraction": counts["local_only_count"] / total,
            "overlap_fraction": counts["overlap_count"] / total,
            "union_fraction": counts["union_count"] / total,
        }
    )
    return counts


def density_overlay(
    response_display: np.ndarray,
    fixed_mask: np.ndarray,
    local_mask: np.ndarray,
    max_edge_px: int,
    alpha_max: float = 0.85,
) -> tuple[np.ndarray, dict]:
    """按全分辨率互斥类别下采样后绘制真实密度叠加图。

    红=固定独有、青=局部独有、黄=共同命中；颜色强度与对应缩略块覆盖率相关，
    不先把缩略图二值化。返回RGB图和全分辨率计数守恒统计。
    """

    stats = mask_overlap_statistics(fixed_mask, local_mask)
    fixed_only = fixed_mask & ~local_mask
    local_only = local_mask & ~fixed_mask
    overlap = fixed_mask & local_mask
    red = density_thumbnail(fixed_only, max_edge_px).astype(np.float32) / 255.0
    cyan = density_thumbnail(local_only, max_edge_px).astype(np.float32) / 255.0
    yellow = density_thumbnail(overlap, max_edge_px).astype(np.float32) / 255.0
    base = response_display if response_display.ndim == 2 else cv2.cvtColor(response_display, cv2.COLOR_RGB2GRAY)
    target_height, target_width = red.shape
    if base.shape != (target_height, target_width):
        base = cv2.resize(base, (target_width, target_height), interpolation=cv2.INTER_AREA)
    base_rgb = np.repeat(base[..., None].astype(np.float32), 3, axis=2)
    colors = ((red, np.asarray([255.0, 60.0, 60.0], dtype=np.float32)),
              (cyan, np.asarray([60.0, 220.0, 255.0], dtype=np.float32)),
              (yellow, np.asarray([255.0, 220.0, 40.0], dtype=np.float32)))
    for density, color in colors:
        alpha = np.clip(density * float(alpha_max), 0.0, float(alpha_max))[..., None]
        base_rgb = base_rgb * (1.0 - alpha) + color[None, None, :] * alpha
    return np.clip(np.rint(base_rgb), 0, 255).astype(np.uint8), stats


def save_density_diagnostic(
    path: Path,
    title: str,
    density: np.ndarray,
    any_hit: np.ndarray,
    full_fraction: float,
    thumbnail_mean_fraction: float,
) -> None:
    """保存带覆盖率色标和any-hit警告的诊断图。"""

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0), dpi=160)
    density_image = axes[0].imshow(density, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
    axes[0].set_title(
        f"density_thumbnail\n全图比例={full_fraction * 100:.6f}%\n缩略均值={thumbnail_mean_fraction * 100:.6f}%",
        fontsize=9,
    )
    axes[0].set_xticks([])
    axes[0].set_yticks([])
    colorbar = fig.colorbar(density_image, ax=axes[0], fraction=0.046, pad=0.04)
    colorbar.set_label("候选覆盖率（0–100%）")
    axes[1].imshow(any_hit, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
    axes[1].set_title("any_hit_thumbnail\n仅表示块内任一点命中；会放大稀疏噪声", fontsize=9)
    axes[1].set_xticks([])
    axes[1].set_yticks([])
    fig.suptitle(title, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def save_revision_contact_sheet(
    path: Path,
    sample_id: int,
    frame_id: int,
    entries: list[dict],
    raw_shape: tuple[int, int],
) -> None:
    """保存A0/A1/A2真实密度联系图；每个候选图标题标注全图真实比例。"""

    columns = [
        ("response", "响应DN显示"),
        ("a0_fixed", "A0固定200 density"),
        ("a0_local", "A0局部k5/floor120 density"),
        ("a1_fixed", "A1按尺度固定代表 density"),
        ("a2_local", "A2局部代表 density"),
        ("overlay", "密度叠加：红固定独有/青局部独有/黄重合"),
    ]
    fig, axes = plt.subplots(len(entries), len(columns), figsize=(18, max(4.0, 2.8 * len(entries))), dpi=150, squeeze=False)
    for row_index, entry in enumerate(entries):
        for col_index, (key, label) in enumerate(columns):
            image = entry[key]
            if image.ndim == 2:
                axes[row_index, col_index].imshow(image, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
            else:
                axes[row_index, col_index].imshow(image, interpolation="nearest")
            if key == "response":
                title = f"{entry['scale']}px {label}"
            elif key == "overlay":
                title = f"{entry['scale']}px {label}"
            else:
                title = f"{entry['scale']}px {label}\n全图={entry[key + '_fraction'] * 100:.6f}%"
            axes[row_index, col_index].set_title(title, fontsize=8)
            axes[row_index, col_index].set_xticks([])
            axes[row_index, col_index].set_yticks([])
        if row_index == len(entries) - 1:
            axes[row_index, 0].set_xlabel("响应显示；非定量", fontsize=7)
            axes[row_index, 1].set_xlabel("A0基线", fontsize=7)
            axes[row_index, 2].set_xlabel("A0基线", fontsize=7)
            axes[row_index, 3].set_xlabel("A1仅为代表候选", fontsize=7)
            axes[row_index, 4].set_xlabel("A2仅为代表候选", fontsize=7)
            axes[row_index, 5].set_xlabel("密度下采样，非二值逻辑", fontsize=7)
    fig.suptitle(
        f"Case03-A-R1样品{sample_id}第{frame_id}帧 A0/A1/A2真实密度对照｜原始shape={raw_shape[0]}×{raw_shape[1]}\n"
        "A1/A2尚未确定为正式阈值；候选比例不是真实缺陷召回率",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def threshold_surface_preview(
    threshold_grid: np.ndarray,
    max_edge_px: int,
    target_shape: tuple[int, int] | None = None,
) -> np.ndarray:
    """把小尺寸网格阈值面双线性上采样为显示图，检查分块缝。"""

    values = threshold_grid.astype(np.float32)
    low = float(values.min())
    high = float(values.max())
    if high <= low:
        high = low + 1.0
    display = np.clip((values - low) / (high - low) * 255.0, 0, 255).astype(np.uint8)
    if target_shape is not None:
        target_height, target_width = target_shape
        scale = min(1.0, max_edge_px / max(target_height, target_width))
        target_size = (max(1, round(target_width * scale)), max(1, round(target_height * scale)))
        return cv2.resize(display, target_size, interpolation=cv2.INTER_LINEAR)
    return resize_display(display, max_edge_px)


def response_mask_overlay(response_display: np.ndarray, fixed_mask_display: np.ndarray, local_mask_display: np.ndarray) -> np.ndarray:
    """生成红色固定阈值/青色局部阈值叠加图，仅用于显示。"""

    base = cv2.cvtColor(response_display, cv2.COLOR_GRAY2RGB)
    fixed = fixed_mask_display > 0
    local = local_mask_display > 0
    base[fixed & ~local] = (255, 60, 60)
    base[~fixed & local] = (60, 220, 255)
    base[fixed & local] = (255, 220, 40)
    return base


def _axis(ax, image: np.ndarray, title: str) -> None:
    if image.ndim == 2:
        ax.imshow(image, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
    else:
        ax.imshow(image, interpolation="nearest")
    ax.set_title(title, fontsize=8)
    ax.set_xticks([])
    ax.set_yticks([])


def save_threshold_contact_sheet(
    path: Path,
    sample_id: int,
    frame_id: int,
    entries: list[dict],
    raw_shape: tuple[int, int],
) -> None:
    """保存每尺度响应/固定阈值/局部阈值/叠加联系图。"""

    fig, axes = plt.subplots(len(entries), 4, figsize=(13, max(3.0, 2.35 * len(entries))), dpi=180, squeeze=False)
    for row_index, entry in enumerate(entries):
        _axis(axes[row_index, 0], entry["response_preview"], f"{entry['scale']} px响应\nDN显示上限={entry['response_high_dn']:.1f}")
        _axis(axes[row_index, 1], entry["fixed_preview"], f"固定阈值\nR≥{entry['fixed_threshold_dn']} DN")
        _axis(axes[row_index, 2], entry["local_preview"], f"局部Median/MAD\nk={entry['local_k']} floor={entry['floor_dn']} DN")
        _axis(axes[row_index, 3], entry["overlay_preview"], "红=固定 青=局部 黄=重合")
        if row_index == len(entries) - 1:
            for col in range(4):
                axes[row_index, col].set_xlabel("x=列，y=行；显示缩放不参与定量", fontsize=7)
    fig.suptitle(
        f"Case03-A样品{sample_id}第{frame_id}帧阈值对照｜原始shape={raw_shape[0]}×{raw_shape[1]}\n"
        "仅为全图掩膜诊断；不含连通域、面积过滤或真实疵病判定",
        fontsize=11,
    )
    legend = [
        Patch(facecolor="#ff3c3c", label="固定阈值独有"),
        Patch(facecolor="#3cdcff", label="局部阈值独有"),
        Patch(facecolor="#ffdc28", label="两者重合"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=3, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _add_cross(ax, center_x: int, center_y: int, patch_size: int) -> None:
    half = patch_size / 2
    center = (half, half)
    ax.plot(center[0], center[1], marker="+", markersize=12, markeredgewidth=2, color="red")


def save_point_patch_comparison(
    path: Path,
    title: str,
    raw_patch: np.ndarray,
    fused_patch: np.ndarray,
    fixed_patch: np.ndarray,
    local_patch: np.ndarray,
    winning_patch: np.ndarray,
    patch_size_px: int,
    raw_display_range: tuple[float, float],
    response_display_high_dn: float,
) -> None:
    """保存指定全分辨率坐标的原始/响应/两种掩膜比较图。"""

    raw_low, raw_high = raw_display_range
    raw_display = cv2.convertScaleAbs(raw_patch, alpha=255.0 / max(raw_high - raw_low, 1.0), beta=-raw_low * 255.0 / max(raw_high - raw_low, 1.0))
    fused_display = cv2.convertScaleAbs(fused_patch, alpha=255.0 / max(response_display_high_dn, 1.0), beta=0)
    winning_display = cv2.convertScaleAbs(winning_patch.astype(np.uint8), alpha=255.0 / 5.0, beta=0)
    fixed_display = fixed_patch.astype(np.uint8) * 255
    local_display = local_patch.astype(np.uint8) * 255
    overlay = response_mask_overlay(fused_display, fixed_display, local_display)
    panels = [
        (raw_display, f"原始RAW DN\n显示{raw_low:.1f}–{raw_high:.1f} DN"),
        (fused_display, f"融合Black-Hat\n显示上限{response_display_high_dn:.1f} DN"),
        (winning_display, "胜出尺度图\n1~5对应3/5/9/15/31 px"),
        (fixed_display, "固定阈值\nR≥200 DN"),
        (local_display, "局部Median/MAD\nk=5 floor=120 DN"),
        (overlay, "叠加\n红固定 青局部 黄重合"),
    ]
    fig, axes = plt.subplots(1, len(panels), figsize=(15, 3.0), dpi=200)
    for ax, (image, panel_title) in zip(axes, panels):
        _axis(ax, image, panel_title)
        _add_cross(ax, raw_patch.shape[1] // 2, raw_patch.shape[0] // 2, patch_size_px)
    fig.suptitle(title + "｜中心十字为全分辨率坐标；不是人工真值", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_revision_point_patch_comparison(
    path: Path,
    title: str,
    raw_patch: np.ndarray,
    fused_patch: np.ndarray,
    a0_fixed_patch: np.ndarray,
    a0_local_patch: np.ndarray,
    a1_fixed_patch: np.ndarray,
    a2_local_patch: np.ndarray,
    patch_size_px: int,
    raw_display_range: tuple[float, float],
    response_display_high_dn: float,
    a1_label: str,
    a2_label: str,
) -> None:
    """保存Case03-A-R1原始尺寸patch的A0/A1/A2前后对照。"""

    if any(image.ndim != 2 for image in (raw_patch, fused_patch, a0_fixed_patch, a0_local_patch, a1_fixed_patch, a2_local_patch)):
        raise TypeError("R1 patch面板必须是二维数组")
    if any(image.shape != raw_patch.shape for image in (fused_patch, a0_fixed_patch, a0_local_patch, a1_fixed_patch, a2_local_patch)):
        raise ValueError("R1 patch面板shape必须一致")
    raw_low, raw_high = raw_display_range
    raw_scale = max(raw_high - raw_low, 1.0)
    raw_display = cv2.convertScaleAbs(raw_patch, alpha=255.0 / raw_scale, beta=-raw_low * 255.0 / raw_scale)
    fused_display = cv2.convertScaleAbs(fused_patch, alpha=255.0 / max(response_display_high_dn, 1.0), beta=0)
    a0_fixed_display = a0_fixed_patch.astype(np.uint8) * 255
    a0_local_display = a0_local_patch.astype(np.uint8) * 255
    a1_fixed_display = a1_fixed_patch.astype(np.uint8) * 255
    a2_local_display = a2_local_patch.astype(np.uint8) * 255
    overlay = response_mask_overlay(fused_display, a1_fixed_display, a2_local_display)
    panels = [
        (raw_display, f"原始RAW DN\n{raw_low:.1f}–{raw_high:.1f} DN"),
        (fused_display, f"融合Black-Hat\n上限{response_display_high_dn:.1f} DN"),
        (a0_fixed_display, "A0固定\n200 DN"),
        (a0_local_display, "A0局部\nk=5 floor=120"),
        (a1_fixed_display, f"A1固定代表\n{a1_label}"),
        (a2_local_display, f"A2局部代表\n{a2_label}"),
        (overlay, "A1/A2诊断叠加\n红固定 青局部 黄重合"),
    ]
    fig, axes = plt.subplots(1, len(panels), figsize=(17.5, 3.2), dpi=200)
    for ax, (image, panel_title) in zip(axes, panels):
        _axis(ax, image, panel_title)
        _add_cross(ax, raw_patch.shape[1] // 2, raw_patch.shape[0] // 2, patch_size_px)
    fig.suptitle(title + "｜中心十字为全分辨率坐标；candidate_not_truth", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
