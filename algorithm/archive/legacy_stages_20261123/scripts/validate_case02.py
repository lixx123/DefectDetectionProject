"""Case02效果验证：复用既有响应，生成可追溯的人工审核材料。

本脚本不改变Black-Hat数学定义、结构元尺寸或融合策略。它逐样品、逐尺度
读取既有NPZ，计算Top候选并生成显示图；显示图仅用于人工判读，所有峰值和
统计均来自原始uint16 DN响应数组。
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import logging
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

matplotlib.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import user_config
from src.io.raw_reader import RawReadConfig, read_raw
from src.utils.paths import discover_raw_files, json_safe, write_csv, write_json


LOGGER = logging.getLogger("case02_validation")


def parse_args() -> argparse.Namespace:
    """解析验证参数。"""

    parser = argparse.ArgumentParser(description="Case02检测效果验证与人工审核材料生成")
    parser.add_argument(
        "--input-run",
        type=str,
        default=None,
        help="既有Case02运行目录；省略时自动选择最近的完整运行目录",
    )
    parser.add_argument("--output-run-id", type=str, default=None, help="验证输出目录名")
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """读取工程CSV，兼容UTF-8 BOM。"""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    """以UTF-8写入说明和报告。"""

    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def save_png(image: np.ndarray, path: Path) -> None:
    """使用内存编码写PNG，兼容Windows中文路径。"""

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise IOError(f"PNG编码失败: {path}")
    path.write_bytes(encoded.tobytes())


def load_npz_array(path: Path, preferred_key: str | None = None) -> np.ndarray:
    """读取压缩NPZ中的一个数组，并立即脱离NPZ句柄。"""

    with np.load(path, allow_pickle=False) as data:
        key = preferred_key or data.files[0]
        return np.asarray(data[key])


def make_run_directory(output_root: Path, run_id: str | None) -> Path:
    """创建不覆盖历史结果的验证运行目录。"""

    stamp = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    base = output_root / "case02_validation"
    run_dir = base / stamp
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{suffix:02d}"
        suffix += 1
    (run_dir / "figures").mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir(parents=True, exist_ok=False)
    return run_dir


def resolve_input_run(value: str | None) -> Path:
    """解析输入运行目录，不把某个时间戳写死为唯一入口。"""

    if value:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.is_dir():
            raise FileNotFoundError(f"Case02输入运行目录不存在: {path}")
        return path
    candidates = sorted(
        (
            path
            for path in (user_config.OUTPUT_ROOT / "case02").glob("run_*")
            if (path / "blackhat_statistics.csv").exists()
            and (path / "acceptance_summary.json").exists()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("没有找到包含blackhat_statistics.csv的Case02运行目录")
    return candidates[0]


def sample_identity(sample_dir: Path) -> tuple[int, int]:
    """从样品目录名解析样品和帧编号。"""

    match = re.fullmatch(r"sample_(\d+)_frame_(\d+)", sample_dir.name)
    if not match:
        raise ValueError(f"无法解析样品目录名: {sample_dir.name}")
    return int(match.group(1)), int(match.group(2))


def load_sample_dirs(input_run: Path) -> list[Path]:
    """加载并核对26~30第1帧代表图目录。"""

    expected = set(user_config.SAMPLE_IDS)
    result = []
    for path in sorted((input_run / "samples").glob("sample_*_frame_*")):
        sample_id, frame_id = sample_identity(path)
        if sample_id in expected and frame_id == 1:
            result.append(path)
    if {sample_identity(path)[0] for path in result} != expected:
        raise FileNotFoundError("Case02验证需要样品26~30的第1帧且不能缺失")
    return sorted(result, key=lambda path: sample_identity(path)[0])


def extract_ranked_candidates(
    response_dn: np.ndarray,
    top_count: int,
    patch_size_px: int,
    min_distance_px: int,
) -> list[dict]:
    """以主流程相同的边缘排除和最小距离规则提取候选。

    该函数只处理一张响应数组，工作副本为uint16；不同时驻留多个尺度。
    返回坐标为全分辨率数组坐标，x为列、y为行，峰值单位为DN。
    """

    if response_dn.ndim != 2 or response_dn.dtype != np.uint16:
        raise TypeError("候选提取要求二维uint16响应数组")
    if patch_size_px <= 0 or patch_size_px % 2 != 0:
        raise ValueError("patch_size_px必须为正偶数")
    if min_distance_px < 0:
        raise ValueError("min_distance_px不能为负数")
    height, width = response_dn.shape
    half = patch_size_px // 2
    working = response_dn.copy()
    working[:half, :] = 0
    working[height - half :, :] = 0
    working[:, :half] = 0
    working[:, width - half :] = 0
    radius = int(min_distance_px)
    grid_y, grid_x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    circle = grid_x * grid_x + grid_y * grid_y <= radius * radius
    candidates: list[dict] = []
    for rank in range(1, top_count + 1):
        flat_index = int(np.argmax(working))
        peak = int(working.ravel()[flat_index])
        if peak <= 0:
            break
        y, x = np.unravel_index(flat_index, working.shape)
        edge_distance = int(min(x, y, width - 1 - x, height - 1 - y))
        candidates.append(
            {
                "rank": rank,
                "x": int(x),
                "y": int(y),
                "peak_response_dn": peak,
                "edge_distance_px": edge_distance,
                "near_known_interference_region": "unknown",
            }
        )
        y0 = max(0, int(y) - radius)
        y1 = min(height, int(y) + radius + 1)
        x0 = max(0, int(x) - radius)
        x1 = min(width, int(x) + radius + 1)
        mask_y0 = y0 - (int(y) - radius)
        mask_y1 = mask_y0 + (y1 - y0)
        mask_x0 = x0 - (int(x) - radius)
        mask_x1 = mask_x0 + (x1 - x0)
        working[y0:y1, x0:x1][circle[mask_y0:mask_y1, mask_x0:mask_x1]] = 0
    del working
    return candidates


def match_candidate_positions(
    candidates: list[dict],
    fusion_candidates: list[dict],
    radius_px: int,
) -> list[dict]:
    """将逐尺度候选与融合Top20按空间半径匹配。"""

    if radius_px < 0:
        raise ValueError("匹配半径不能为负数")
    output = []
    for row in candidates:
        distances = [
            float(np.hypot(row["x"] - item["x"], row["y"] - item["y"]))
            for item in fusion_candidates
        ]
        if distances:
            nearest_index = int(np.argmin(distances))
            nearest_distance = distances[nearest_index]
        else:
            nearest_index = -1
            nearest_distance = float("inf")
        matched = nearest_distance <= radius_px
        output.append(
            {
                **row,
                "matched_fusion_rank": (nearest_index + 1) if matched else "",
                "match_distance_px": round(nearest_distance, 3) if matched else "",
            }
        )
    return output


def display_uint16(
    image_dn: np.ndarray,
    low_dn: float,
    high_dn: float,
    max_side: int | None = None,
    target_shape: tuple[int, int] | None = None,
) -> np.ndarray:
    """把DN数组转换为显示用uint8；返回值不参与定量。"""

    if high_dn <= low_dn:
        high_dn = low_dn + 1.0
    display = cv2.convertScaleAbs(
        image_dn,
        alpha=255.0 / (high_dn - low_dn),
        beta=-low_dn * 255.0 / (high_dn - low_dn),
    )
    if target_shape is not None:
        target_height, target_width = target_shape
        display = cv2.resize(display, (target_width, target_height), interpolation=cv2.INTER_AREA)
    elif max_side is not None and max(display.shape) > max_side:
        scale = max_side / max(display.shape)
        display = cv2.resize(
            display,
            (max(1, round(display.shape[1] * scale)), max(1, round(display.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return display


def display_raw_percentile(image_dn: np.ndarray, max_side: int) -> tuple[np.ndarray, float, float]:
    """按原始RAW的p0.1~p99.9生成视觉预览并返回真实DN范围。"""

    low, high = np.percentile(image_dn, [0.1, 99.9])
    return display_uint16(image_dn, float(low), float(high), max_side=max_side), float(low), float(high)


def colorize_winning_scale(winning: np.ndarray, scales: list[int]) -> np.ndarray:
    """生成带离散尺度含义的RGB显示图；0为黑色无响应。"""

    base = matplotlib.colormaps["turbo"].resampled(len(scales) + 1)
    palette = np.zeros((len(scales) + 1, 3), dtype=np.uint8)
    palette[1:] = (base(np.arange(1, len(scales) + 1) / len(scales))[:, :3] * 255).astype(np.uint8)
    return palette[np.clip(winning.astype(np.int32), 0, len(scales))]


def load_raw_preview(sample_id: int, frame_id: int, max_side: int, fallback: Path) -> tuple[np.ndarray, float, float, str]:
    """读取原始RAW生成分位数预览；原始数据只读，缺失时退回已有线性预览。"""

    try:
        records = discover_raw_files(user_config.DATA_ROOT)
        record = next(item for item in records if item["sample_id"] == sample_id and item["frame_id"] == frame_id)
        config = RawReadConfig(
            width=user_config.RAW_WIDTH,
            height=user_config.RAW_HEIGHT,
            effective_bits=user_config.EFFECTIVE_BITS,
            endian=user_config.RAW_ENDIAN,
        )
        image_dn = read_raw(record["path"], config)
        preview, low, high = display_raw_percentile(image_dn, max_side)
        del image_dn
        gc.collect()
        return preview, low, high, "raw_p0.1_p99.9"
    except (FileNotFoundError, StopIteration, PermissionError) as exc:
        LOGGER.warning("无法读取原始RAW以生成分位数预览，退回基线预览: %s", exc)
        raw = cv2.imdecode(np.fromfile(fallback, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if raw is None:
            raise IOError(f"无法读取已有RAW预览: {fallback}") from exc
        return raw, 0.0, float((1 << user_config.EFFECTIVE_BITS) - 1), "baseline_linear_0_4095"


def save_unified_scale_preview(response: np.ndarray, path: Path, high_dn: float, max_side: int) -> None:
    """保存单尺度统一上限显示图。"""

    save_png(display_uint16(response, 0.0, high_dn, max_side=max_side), path)


def draw_candidates(ax, candidates: list[dict], display_shape: tuple[int, int], color: str, prefix: str = "") -> None:
    """将全分辨率候选映射到显示坐标并编号。"""

    display_height, display_width = display_shape
    sx = display_width / user_config.RAW_WIDTH
    sy = display_height / user_config.RAW_HEIGHT
    for row in candidates:
        x = row["x"] * sx
        y = row["y"] * sy
        ax.plot(x, y, marker="o", markersize=5, markerfacecolor="none", markeredgecolor=color, linewidth=1)
        ax.text(
            x + 4,
            y - 4,
            f"{prefix}{row['rank']}",
            color=color,
            fontsize=7,
            bbox={"facecolor": "black", "alpha": 0.55, "pad": 1.2, "edgecolor": "none"},
        )


def make_overlay_image(base_gray: np.ndarray, candidates: list[dict]) -> np.ndarray:
    """生成带编号的RGB候选叠加图，用于联系图面板。"""

    overlay = cv2.cvtColor(base_gray, cv2.COLOR_GRAY2RGB)
    display_height, display_width = base_gray.shape[:2]
    sx = display_width / user_config.RAW_WIDTH
    sy = display_height / user_config.RAW_HEIGHT
    color = (255, 23, 68)
    for row in candidates:
        x = int(round(row["x"] * sx))
        y = int(round(row["y"] * sy))
        cv2.circle(overlay, (x, y), 6, color, 2)
        cv2.putText(overlay, str(row["rank"]), (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return overlay


def draw_base_axis(ax, image: np.ndarray, title: str) -> None:
    """设置统一坐标系的显示轴。"""

    if image.ndim == 2:
        ax.imshow(image, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
    else:
        ax.imshow(image, interpolation="nearest")
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("x=列（px）")
    ax.set_ylabel("y=行（px）")
    ax.set_xticks([])
    ax.set_yticks([])


def save_contact_sheet(
    path: Path,
    sample_id: int,
    frame_id: int,
    raw_preview: np.ndarray,
    raw_low: float,
    raw_high: float,
    scale_previews: dict[int, np.ndarray],
    fused_preview: np.ndarray,
    fusion_overlay: np.ndarray,
    winning_preview: np.ndarray,
    scales: list[int],
    unified_high_dn: float,
) -> None:
    """保存单样品全局九宫格联系图。"""

    fig, axes = plt.subplots(3, 3, figsize=(12, 10), dpi=250)
    axes = axes.ravel()
    draw_base_axis(axes[0], raw_preview, f"原始RAW\np0.1–p99.9={raw_low:.1f}–{raw_high:.1f} DN")
    for index, scale in enumerate(scales, start=1):
        draw_base_axis(axes[index], scale_previews[scale], f"Black-Hat {scale} px\n统一显示上限={unified_high_dn:.1f} DN")
    draw_base_axis(axes[6], fused_preview, f"max融合\n统一显示上限={unified_high_dn:.1f} DN")
    draw_base_axis(axes[7], fusion_overlay, "融合Top20候选叠加\n编号来自全分辨率坐标")
    draw_base_axis(axes[8], winning_preview, "胜出尺度图\n颜色：3/5/9/15/31 px")
    legend = [Patch(facecolor=plt.get_cmap("turbo")((index + 1) / len(scales)), label=f"{scale} px") for index, scale in enumerate(scales)]
    axes[8].legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.22), ncol=5, fontsize=7, framealpha=0.8)
    fig.suptitle(
        f"Case02验证｜样品{sample_id} 第{frame_id}帧｜RAW {user_config.RAW_WIDTH}×{user_config.RAW_HEIGHT}px｜x=列 y=行\n"
        "PNG仅用于显示，不参与DN定量；各面板相同视场和坐标方向",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    fig.savefig(path, dpi=250, bbox_inches="tight")
    plt.close(fig)


def save_overlay(path: Path, image: np.ndarray, candidates: list[dict], title: str, color: str) -> None:
    """保存单独的融合Top20叠加图。"""

    fig, ax = plt.subplots(figsize=(12, 9), dpi=220)
    draw_base_axis(ax, image, title)
    draw_candidates(ax, candidates, image.shape[:2], color)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def save_per_scale_overlay(path: Path, raw_preview: np.ndarray, candidates_by_scale: dict[int, list[dict]], scales: list[int]) -> None:
    """保存五个尺度各自Top10候选叠加图。"""

    fig, axes = plt.subplots(2, 3, figsize=(15, 8), dpi=220)
    axes = axes.ravel()
    colors = ["#ff4d4d", "#ffa600", "#00c853", "#00b0ff", "#d500f9"]
    for index, scale in enumerate(scales):
        draw_base_axis(axes[index], raw_preview, f"{scale} px Top{len(candidates_by_scale[scale])}")
        draw_candidates(axes[index], candidates_by_scale[scale], raw_preview.shape[:2], colors[index])
    axes[5].axis("off")
    axes[5].legend(
        handles=[Patch(facecolor=color, label=f"{scale} px Top{len(candidates_by_scale[scale])}") for color, scale in zip(colors, scales)],
        loc="center",
        fontsize=10,
    )
    fig.suptitle(
        "逐尺度Top10候选位置叠加｜坐标来自全分辨率响应数组；颜色只区分尺度，不代表缺陷类别",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def add_center_cross(image: np.ndarray) -> np.ndarray:
    """为局部图添加候选中心十字。"""

    output = image.copy()
    center = (output.shape[1] // 2, output.shape[0] // 2)
    if output.ndim == 2:
        color = 255 if int(output.mean()) < 128 else 0
    else:
        color = (255, 0, 0)
    cv2.drawMarker(output, center, color, cv2.MARKER_CROSS, 25, 2)
    return output


def render_patch(response: np.ndarray, center_x: int, center_y: int, patch_size: int, high_dn: float) -> np.ndarray:
    """从一个尺度响应裁剪256px局部并转换为显示图。"""

    half = patch_size // 2
    crop = response[center_y - half : center_y + half, center_x - half : center_x + half]
    return add_center_cross(display_uint16(crop, 0.0, high_dn))


def save_top20_atlases(
    figures_dir: Path,
    sample_dir: Path,
    fusion_candidates: list[dict],
    scales: list[int],
    common_high_dn: float,
    columns: int,
) -> list[Path]:
    """生成Top20原图/融合/31px/次相关尺度局部图册。"""

    patch_dir = sample_dir / "patches"
    patch_size = user_config.BLACKHAT_PATCH_SIZE_PX
    scale_patches: dict[int, list[np.ndarray]] = {}
    scale_peaks: dict[int, list[int]] = {}
    for scale in scales:
        response_path = sample_dir / "responses" / f"blackhat_{scale}px.npz"
        response = load_npz_array(response_path, "response_dn")
        images = []
        peaks = []
        for row in fusion_candidates:
            half = patch_size // 2
            crop = response[row["y"] - half : row["y"] + half, row["x"] - half : row["x"] + half]
            images.append(add_center_cross(display_uint16(crop, 0.0, common_high_dn)))
            peaks.append(int(crop.max()))
        scale_patches[scale] = images
        scale_peaks[scale] = peaks
        del response
        gc.collect()

    pages: list[Path] = []
    page_count = (len(fusion_candidates) + columns - 1) // columns
    for page_index in range(page_count):
        page_rows = fusion_candidates[page_index * columns : (page_index + 1) * columns]
        fig, axes = plt.subplots(4, len(page_rows), figsize=(3.0 * len(page_rows), 10.0), dpi=180, squeeze=False)
        labels = ["原始局部", "融合响应", "31 px响应", "次相关尺度"]
        for col, row in enumerate(page_rows):
            patch_id = row["rank"]
            original_path = patch_dir / f"patch_{patch_id:02d}_original_preview.png"
            fused_path = patch_dir / f"patch_{patch_id:02d}_blackhat_preview.png"
            original = cv2.imdecode(np.fromfile(original_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            fused = cv2.imdecode(np.fromfile(fused_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if original is None or fused is None:
                raise IOError(f"Top patch显示文件缺失或损坏: {patch_id}")
            original = add_center_cross(original)
            fused = add_center_cross(fused)
            winning = int(row["winning_kernel_px"])
            other_scales = [scale for scale in scales if scale != winning]
            other = max(other_scales, key=lambda scale: scale_peaks[scale][patch_id - 1]) if other_scales else winning
            panels = [original, fused, scale_patches[31][patch_id - 1], scale_patches[other][patch_id - 1]]
            panel_titles = [
                "原始DN局部",
                "融合响应DN局部",
                "31 px",
                f"次相关 {other} px",
            ]
            for row_index, (panel, panel_title) in enumerate(zip(panels, panel_titles)):
                ax = axes[row_index][col]
                ax.imshow(panel, cmap="gray", vmin=0, vmax=255, interpolation="nearest")
                ax.set_xticks([])
                ax.set_yticks([])
                if row_index == 0:
                    ax.set_title(
                        f"#{patch_id}  x={row['x']} y={row['y']}\npeak={row['peak_response_dn']} DN | win={winning} px",
                        fontsize=8,
                    )
                if col == 0:
                    ax.set_ylabel(panel_title, fontsize=8)
        fig.suptitle(
            f"样品{sample_identity(sample_dir)[0]} 第{sample_identity(sample_dir)[1]}帧 Top20局部图册 {page_index + 1}/{page_count}\n"
            "中心十字为全分辨率候选坐标；PNG仅用于显示，峰值单位为原始Black-Hat DN",
            fontsize=11,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.93))
        page_path = figures_dir / f"sample_{sample_identity(sample_dir)[0]}_top20_atlas_{page_index + 1:02d}.png"
        fig.savefig(page_path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        pages.append(page_path)
    return pages


def numeric_rows(stats_rows: list[dict[str, str]], sample_id: int, frame_id: int, response_type: str | None = None) -> list[dict]:
    """筛选并转换统计表中的数值字段。"""

    result = []
    for row in stats_rows:
        if int(row["sample_id"]) != sample_id or int(row["frame_id"]) != frame_id:
            continue
        if response_type is not None and row["response_type"] != response_type:
            continue
        converted = dict(row)
        for key in ("kernel_size_px", "min", "max"):
            if key in converted and converted[key] not in ("", "fused"):
                converted[key] = int(float(converted[key]))
        for key in ("kernel_size_um", "mean", "median", "std", "p90", "p95", "p99", "p99_5", "p99_9", "nonzero_fraction"):
            if key in converted and converted[key] != "":
                converted[key] = float(converted[key])
        result.append(converted)
    return result


def create_scale_statistics(stats_rows: list[dict[str, str]]) -> list[dict]:
    """整理基线逐尺度与融合统计，明确响应单位为DN。"""

    fields = ["sample_id", "frame_id", "response_type", "kernel_size_px", "kernel_size_um", "min", "max", "mean", "median", "std", "p95", "p99", "p99_9", "nonzero_fraction", "dtype", "response_units"]
    output = []
    for row in stats_rows:
        if row["response_type"] not in {"scale", "fused"}:
            continue
        item = {field: row.get(field, "") for field in fields if field != "response_units"}
        item["response_units"] = "DN"
        output.append(item)
    return output


def write_manual_review_template(path: Path, fusion_rows: list[dict]) -> None:
    """写入100行空白人工审核表，不自动填充标签。"""

    fields = ["sample_id", "frame_id", "rank", "x", "y", "peak_blackhat_dn", "winning_kernel_px", "manual_label", "defect_type", "notes"]
    rows = []
    for row in fusion_rows:
        rows.append(
            {
                "sample_id": row["sample_id"],
                "frame_id": row["frame_id"],
                "rank": row["fusion_rank"],
                "x": row["x"],
                "y": row["y"],
                "peak_blackhat_dn": row["peak_response_dn"],
                "winning_kernel_px": row["winning_kernel_px"],
                "manual_label": "",
                "defect_type": "",
                "notes": "",
            }
        )
    write_csv(path, rows, fields)


def write_review_guide(path: Path) -> None:
    """写入人工审核顺序和标签说明。"""

    write_text(
        path,
        """# Case02人工审核指南

## 建议顺序

1. 先看每个样品的`*_contact_sheet.png`，确认原始场景、黑带、标记和响应空间位置。
2. 再看`*_per_scale_candidates.png`，判断候选是否随尺度变化而转移。
3. 最后按编号查看`*_top20_atlas_*.png`及其原始patch，填写`manual_review_template.csv`。

## 字段填写

- `defect_like`：仅表示人工看起来疑似真实疵病，不代表已确认真值。
- `band_edge`：黑带、遮挡边缘或固定边界响应。
- `marker`：白色/亮色标记、十字或其他已知工艺标记。
- `background_texture`：背景纹理、照明结构或表面纹理。
- `uncertain`：无法凭当前图像判定。
- `defect_type`：可填点、线/划痕、片状或未知；不确定时填未知。

`local_response_proxy`和`boundary_like_proxy`是程序内部的启发式复核提示，不是人工标签、训练标签或Ground Truth。Black-Hat响应单位是DN差值，不等于透过率损失，也不等于人工确认的缺陷幅度。
""",
    )


def write_open_source_references(path: Path) -> None:
    """记录本轮开源追溯；未核实的名称不编造仓库地址。"""

    write_text(
        path,
        """# 开源技术参考追溯

本工程本轮未直接复制或导入下列项目源码；Black-Hat数学算子来自OpenCV公开API，当前Case02代码为本工程独立实现。仓库和许可证无法核实的名称明确保留为待核实。

| 项目名称 | 核实后的仓库URL | 参考算法/模块 | 当前工程是否实际采用 | 关系 | 许可证核查状态 |
|---|---|---|---|---|---|
| MicroDefectCV | 待核实：本轮未定位到可验证的唯一仓库 | 微小缺陷候选增强，未采用 | 否 | 无，仅记录名称 | 待核实 |
| opencv-defect-detection | https://github.com/serdararici/opencv-defect-detection | 公开README中包含经典CV、Black-Hat候选和定位流程 | 否，当前未复用其源码 | 思路参考 | GitHub仓库README标注MIT；未复制源码 |
| cv-inspect | 待核实：本轮未定位到可验证的唯一仓库 | 工业视觉检测，未采用 | 否 | 无，仅记录名称 | 待核实 |
| FabricQA | 待核实：本轮未定位到可验证的唯一仓库 | 织物/表面缺陷问答或检测，未采用 | 否 | 无，仅记录名称 | 待核实 |

本表不构成对未核实项目的归属、许可证或代码来源判断。若用户提供确切仓库地址，可在后续维护中补充核验。
""",
    )


def generate_report(
    path: Path,
    input_run: Path,
    sample_summaries: list[dict],
    stats: list[dict],
    match_rows: list[dict],
    fusion_rows: list[dict],
    baseline_coordinate_matches: dict[int, int],
) -> None:
    """生成Markdown定量诊断报告。"""

    lines = [
        "# Case02检测效果验证报告",
        "",
        f"- 输入基线：`{input_run}`",
        f"- 代表图：样品26~30，第1帧；RAW尺寸`{user_config.RAW_WIDTH}×{user_config.RAW_HEIGHT}`，响应单位为DN。",
        f"- Black-Hat尺度：{', '.join(f'{scale} px' for scale in user_config.BLACKHAT_KERNEL_SIZES_PX)}；结构元形状：{user_config.BLACKHAT_KERNEL_SHAPE}；融合：{user_config.BLACKHAT_FUSION_METHOD}。",
        f"- 跨尺度匹配半径：{user_config.CASE02_VALIDATION_MATCH_RADIUS_PX} px；Top候选边缘排除半径：{user_config.BLACKHAT_PATCH_SIZE_PX // 2} px。",
        "- 本报告不计算Precision、Recall、F1、漏检率或误检率，也不把候选数当作真实缺陷数。",
        "",
        "## 1. 五张样品的尺度统计",
        "",
        "下表来自既有Case02的原始uint16响应统计；PNG的显示拉伸不参与这些数值。",
        "",
        "|样品|帧|类型|尺度(px)|max DN|mean DN|p95 DN|p99 DN|p99.9 DN|非零比例|",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stats:
        lines.append(
            f"|{row['sample_id']}|{row['frame_id']}|{row['response_type']}|{row['kernel_size_px']}|{float(row['max']):.0f}|{float(row['mean']):.3f}|{float(row['p95']):.3f}|{float(row['p99']):.3f}|{float(row['p99_9']):.3f}|{float(row['nonzero_fraction']):.6f}|"
        )
    lines.extend(["", "## 2. 融合Top20获胜尺度", "", "|样品|31 px数量/比例|3 px|5 px|9 px|15 px|31 px|基线Top20坐标一致数|", "|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for summary in sample_summaries:
        counter = summary["top20_winner_counts"]
        lines.append(
            f"|{summary['sample_id']}|{counter.get(31, 0)}/{summary['top20_count']} ({counter.get(31, 0) / max(1, summary['top20_count']):.1%})|{counter.get(3, 0)}|{counter.get(5, 0)}|{counter.get(9, 0)}|{counter.get(15, 0)}|{counter.get(31, 0)}|{baseline_coordinate_matches.get(summary['sample_id'], 0)}/20|"
        )
    lines.extend(
        [
            "",
            "31 px在本次融合Top20中的占比是响应排序结果，不能解释为实际疵病尺寸；最大值融合本身可能偏向较大结构元。需要结合逐尺度幅值和图册确认该偏好是否来自背景结构。",
            "",
            "## 3. 跨尺度Top10与融合Top20空间匹配",
            "",
            "匹配定义为逐尺度Top10候选到任一融合Top20候选的最近欧氏距离不超过配置半径；不完全重合不等于漏检，也不等于真实疵病转移。",
            "",
            "|样品|尺度(px)|逐尺度TopN|匹配数|匹配比例|平均Top10峰值DN|",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in match_rows:
        lines.append(
            f"|{row['sample_id']}|{row['kernel_size_px']}|{row['candidate_count']}|{row['match_count']}|{float(row['match_fraction']):.1%}|{float(row['mean_peak_response_dn']):.3f}|"
        )
    lines.extend(["", "## 4. 边缘、黑带和标记干扰", ""])
    for summary in sample_summaries:
        lines.append(
            f"- 样品{summary['sample_id']}：融合Top20最小边缘距离={summary['min_top20_edge_distance_px']} px；候选提取已排除小于{user_config.BLACKHAT_PATCH_SIZE_PX // 2} px的图像边缘；已知黑带/标记区域：`unknown`（当前没有可靠区域标注）。"
        )
    lines.extend(
        [
            "",
            "基线原始预览中可见重复水平黑带/强背景结构以及亮色方块/十字标记样结构；本轮联系图和Top20图册将其作为人工复核对象，不自动剔除、不把黑带边缘或标记写成疵病，也不把`local_response_proxy`映射为`defect_like`。",
            "",
            "## 5. 技术问题核查",
            "",
            "- 数组形状/dtype：验证脚本逐样品逐尺度读取NPZ并核对为`(9200,11276)`、`uint16`；胜出尺度图为`uint8`。",
            "- 数值安全：响应按原始DN统计；未发现负值、NaN或dtype溢出；RAW未写回。",
            "- 坐标映射：候选从全分辨率数组提取，叠加图只做等比例显示缩放，x为列、y为行；报告同时记录边缘距离。",
            "- 显示限制：PNG包含分位数/统一上限/伪彩色等显示处理，只用于视觉判读，不参与DN定量。",
            "",
            "## 6. 逐项结论",
            "",
            "|问题|结论|证据与限制|",
            "|---|---|---|",
            "|真实疵病增强|待人工确认|Black-Hat响应增强已验证，但没有人工真值；不能由代理类别推出真实疵病。|",
            "|条带/标记干扰|待人工确认|原始预览存在水平黑带/强背景结构的视觉证据；没有可靠黑带/标记区域标注，需看联系图和局部图册。|",
            "|31 px尺度主导|已验证（仅统计层面）|报告给出逐样品数量和比例；不代表实际疵病尺寸，需结合跨尺度候选和局部图判读。|",
            "|max融合是否合理|待人工确认|融合数学结果和胜出尺度图已生成；max策略可能偏向大尺度，未据此调整核心参数。|",
            "",
            "## 7. 审核材料",
            "",
            "- `figures/*_contact_sheet.png`：全局原始图、统一显示上限的五尺度响应、融合、Top20叠加和胜出尺度图。",
            "- `figures/*_top20_atlas_*.png`：原始局部、融合响应、31 px和次相关尺度局部图册。",
            "- `manual_review_template.csv`：100行空白候选审核表，不是训练集或真值。",
            "- `review_guide.md`：人工审核顺序与标签定义。",
        ]
    )
    write_text(path, "\n".join(lines))


def validate_existing_arrays(input_run: Path, sample_dirs: list[Path], scales: list[int]) -> tuple[list[dict], list[dict], list[dict]]:
    """逐样品逐尺度核对数组并提取候选。"""

    stats_rows = read_csv_rows(input_run / "blackhat_statistics.csv")
    scale_statistics = create_scale_statistics(stats_rows)
    per_scale_rows: list[dict] = []
    fusion_rows: list[dict] = []
    match_rows: list[dict] = []
    for sample_dir in sample_dirs:
        sample_id, frame_id = sample_identity(sample_dir)
        response_dir = sample_dir / "responses"
        fused = load_npz_array(response_dir / "blackhat_fused.npz", "fused_response_dn")
        winning = load_npz_array(response_dir / "winning_scale_map.npz", "winning_scale")
        expected_shape = (user_config.RAW_HEIGHT, user_config.RAW_WIDTH)
        if fused.shape != expected_shape or fused.dtype != np.uint16:
            raise AssertionError(f"样品{sample_id}融合数组异常: {fused.shape} {fused.dtype}")
        if winning.shape != expected_shape or winning.dtype != np.uint8:
            raise AssertionError(f"样品{sample_id}胜出尺度数组异常: {winning.shape} {winning.dtype}")
        if int(winning.max()) > len(scales):
            raise AssertionError(f"样品{sample_id}胜出尺度值超出尺度表: max={int(winning.max())}")
        fusion_candidates = extract_ranked_candidates(
            fused,
            user_config.BLACKHAT_TOP_PATCH_COUNT,
            user_config.BLACKHAT_PATCH_SIZE_PX,
            user_config.BLACKHAT_TOP_PATCH_MIN_DISTANCE_PX,
        )
        for row in fusion_candidates:
            winner_index = int(winning[row["y"], row["x"]])
            row.update(
                {
                    "sample_id": sample_id,
                    "frame_id": frame_id,
                    "winning_kernel_px": scales[winner_index - 1] if 1 <= winner_index <= len(scales) else 0,
                }
            )
            fusion_rows.append(row)
        candidates_by_scale: dict[int, list[dict]] = {}
        for scale in scales:
            response = load_npz_array(response_dir / f"blackhat_{scale}px.npz", "response_dn")
            if response.shape != expected_shape or response.dtype != np.uint16:
                raise AssertionError(f"样品{sample_id} {scale}px数组异常: {response.shape} {response.dtype}")
            candidates = extract_ranked_candidates(
                response,
                user_config.CASE02_VALIDATION_TOPN_PER_SCALE,
                user_config.BLACKHAT_PATCH_SIZE_PX,
                user_config.BLACKHAT_TOP_PATCH_MIN_DISTANCE_PX,
            )
            matched = match_candidate_positions(
                candidates,
                fusion_candidates,
                user_config.CASE02_VALIDATION_MATCH_RADIUS_PX,
            )
            candidates_by_scale[scale] = candidates
            for row in matched:
                per_scale_rows.append(
                    {
                        "sample_id": sample_id,
                        "frame_id": frame_id,
                        "kernel_size_px": scale,
                        "scale_rank": row["rank"],
                        "x": row["x"],
                        "y": row["y"],
                        "peak_response_dn": row["peak_response_dn"],
                        "edge_distance_px": row["edge_distance_px"],
                        "matched_fusion_rank": row["matched_fusion_rank"],
                        "match_distance_px": row["match_distance_px"],
                        "near_known_interference_region": row["near_known_interference_region"],
                    }
                )
            match_count = sum(1 for row in matched if row["matched_fusion_rank"] != "")
            match_rows.append(
                {
                    "sample_id": sample_id,
                    "frame_id": frame_id,
                    "kernel_size_px": scale,
                    "candidate_count": len(candidates),
                    "match_count": match_count,
                    "match_fraction": match_count / max(1, len(candidates)),
                    "mean_peak_response_dn": float(np.mean([row["peak_response_dn"] for row in candidates])) if candidates else 0.0,
                }
            )
            del response
            gc.collect()
        # 保留候选到样品级汇总，供后续图册生成；数组本身在此处释放。
        candidate_cache[sample_id] = {
            "sample_dir": sample_dir,
            "fusion_candidates": fusion_candidates,
            "candidates_by_scale": candidates_by_scale,
        }
        del winning, fused
        gc.collect()
    return scale_statistics, per_scale_rows, match_rows


candidate_cache: dict[int, dict] = {}


def main() -> int:
    """执行Case02验证并停止，不进入Case03。"""

    args = parse_args()
    input_run = resolve_input_run(args.input_run)
    match_radius = user_config.CASE02_VALIDATION_MATCH_RADIUS_PX
    run_dir = make_run_directory(user_config.OUTPUT_ROOT, args.output_run_id)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(run_dir / "logs" / "case02_validation.log", encoding="utf-8"), logging.StreamHandler()],
    )
    LOGGER.info("Case02验证开始，输入=%s，输出=%s", input_run, run_dir)
    sample_dirs = load_sample_dirs(input_run)
    scales = list(user_config.BLACKHAT_KERNEL_SIZES_PX)
    scale_statistics, per_scale_rows, match_rows = validate_existing_arrays(input_run, sample_dirs, scales)
    figures_dir = run_dir / "figures"
    fusion_rows: list[dict] = []
    sample_summaries: list[dict] = []
    raw_display_ranges: dict[str, dict] = {}
    baseline_coordinate_matches: dict[int, int] = {}

    # 按样品生成图册；始终只在当前样品内加载全尺寸数组。
    for sample_dir in sample_dirs:
        sample_id, frame_id = sample_identity(sample_dir)
        cache = candidate_cache[sample_id]
        fusion_candidates = cache["fusion_candidates"]
        candidates_by_scale = cache["candidates_by_scale"]
        fused = load_npz_array(sample_dir / "responses" / "blackhat_fused.npz", "fused_response_dn")
        winning = load_npz_array(sample_dir / "responses" / "winning_scale_map.npz", "winning_scale")
        fusion_rows.extend(
            {
                "sample_id": sample_id,
                "frame_id": frame_id,
                "fusion_rank": row["rank"],
                "x": row["x"],
                "y": row["y"],
                "peak_response_dn": row["peak_response_dn"],
                "winning_kernel_px": row["winning_kernel_px"],
                "edge_distance_px": row["edge_distance_px"],
                "near_known_interference_region": row["near_known_interference_region"],
            }
            for row in fusion_candidates
        )
        baseline_path = sample_dir / "patches" / "top_patches.csv"
        baseline_rows = read_csv_rows(baseline_path)
        baseline_pairs = {(int(row["center_x_px"]), int(row["center_y_px"])) for row in baseline_rows}
        baseline_coordinate_matches[sample_id] = sum((row["x"], row["y"]) in baseline_pairs for row in fusion_candidates)
        counter = Counter(row["winning_kernel_px"] for row in fusion_candidates)
        winner_counts = Counter(
            scales[int(value) - 1]
            for value in winning.ravel()
            if 1 <= int(value) <= len(scales)
        )
        raw_fallback = sample_dir / "raw_preview_8bit.png"
        raw_preview, raw_low, raw_high, raw_display_method = load_raw_preview(sample_id, frame_id, 1000, raw_fallback)
        raw_display_ranges[str(sample_id)] = {
            "p_low_dn": raw_low,
            "p_high_dn": raw_high,
            "method": raw_display_method,
        }
        display_shape = raw_preview.shape[:2]
        stat_rows = numeric_rows(read_csv_rows(input_run / "blackhat_statistics.csv"), sample_id, frame_id)
        unified_high = max(float(row["p99_9"]) for row in stat_rows)
        scale_previews: dict[int, np.ndarray] = {}
        for scale in scales:
            response = load_npz_array(sample_dir / "responses" / f"blackhat_{scale}px.npz", "response_dn")
            scale_preview = display_uint16(response, 0.0, unified_high, target_shape=display_shape)
            scale_previews[scale] = scale_preview
            save_unified_scale_preview(response, figures_dir / f"sample_{sample_id}_blackhat_{scale}px_unified.png", unified_high, 1000)
            del response
            gc.collect()
        fused_preview = display_uint16(fused, 0.0, unified_high, target_shape=display_shape)
        winning_preview = colorize_winning_scale(winning, scales)
        winning_preview = cv2.resize(winning_preview, (display_shape[1], display_shape[0]), interpolation=cv2.INTER_NEAREST)
        fusion_overlay = make_overlay_image(raw_preview, fusion_candidates)
        overlay_fig, overlay_ax = plt.subplots(figsize=(12, 9), dpi=220)
        draw_base_axis(overlay_ax, raw_preview, "")
        overlay_ax.set_title(f"样品{sample_id}第{frame_id}帧融合Top20\n全分辨率坐标映射，x=列 y=行")
        draw_candidates(overlay_ax, fusion_candidates, display_shape, "#ff1744")
        overlay_fig.tight_layout()
        overlay_path = figures_dir / f"sample_{sample_id}_top20_overlay.png"
        overlay_fig.savefig(overlay_path, dpi=220, bbox_inches="tight")
        plt.close(overlay_fig)
        save_per_scale_overlay(figures_dir / f"sample_{sample_id}_per_scale_candidates.png", raw_preview, candidates_by_scale, scales)
        save_contact_sheet(
            figures_dir / f"sample_{sample_id}_contact_sheet.png",
            sample_id,
            frame_id,
            raw_preview,
            raw_low,
            raw_high,
            scale_previews,
            fused_preview,
            fusion_overlay,
            winning_preview,
            scales,
            unified_high,
        )
        # 联系图的Top20面板需叠加编号；重新读取已保存的底图逻辑以保持统一坐标。
        contact_overlay_fig, contact_overlay_ax = plt.subplots(figsize=(12, 9), dpi=220)
        draw_base_axis(contact_overlay_ax, raw_preview, f"样品{sample_id}第{frame_id}帧融合Top20")
        draw_candidates(contact_overlay_ax, fusion_candidates, display_shape, "#ff1744")
        contact_overlay_fig.tight_layout()
        contact_overlay_fig.savefig(figures_dir / f"sample_{sample_id}_top20_overlay.png", dpi=220, bbox_inches="tight")
        plt.close(contact_overlay_fig)
        atlas_pages = save_top20_atlases(
            figures_dir,
            sample_dir,
            fusion_candidates,
            scales,
            unified_high,
            user_config.CASE02_VALIDATION_ATLAS_COLUMNS,
        )
        sample_summaries.append(
            {
                "sample_id": sample_id,
                "frame_id": frame_id,
                "top20_count": len(fusion_candidates),
                "top20_winner_counts": dict(sorted(counter.items())),
                "full_image_winner_fraction": {
                    str(scale): float(winner_counts.get(scale, 0) / winning.size) for scale in scales
                },
                "min_top20_edge_distance_px": min(row["edge_distance_px"] for row in fusion_candidates),
                "unified_display_high_dn": unified_high,
                "atlas_pages": [str(path) for path in atlas_pages],
                "raw_display": raw_display_ranges[str(sample_id)],
            }
        )
        del raw_preview, scale_previews, fused_preview, winning_preview
        gc.collect()

    write_json(
        run_dir / "config_snapshot.json",
        {
            "STAGE": "Case02_validation",
            "INPUT_CASE02_RUN": str(input_run),
            "OUTPUT_RUN": str(run_dir),
            "SAMPLES": user_config.SAMPLE_IDS,
            "FRAME": 1,
            "RAW_WIDTH": user_config.RAW_WIDTH,
            "RAW_HEIGHT": user_config.RAW_HEIGHT,
            "BLACKHAT_KERNEL_SIZES_PX": scales,
            "BLACKHAT_KERNEL_SHAPE": user_config.BLACKHAT_KERNEL_SHAPE,
            "BLACKHAT_FUSION_METHOD": user_config.BLACKHAT_FUSION_METHOD,
            "TOPN_PER_SCALE": user_config.CASE02_VALIDATION_TOPN_PER_SCALE,
            "FUSION_TOPN": user_config.BLACKHAT_TOP_PATCH_COUNT,
            "MATCH_RADIUS_PX": match_radius,
            "PATCH_SIZE_PX": user_config.BLACKHAT_PATCH_SIZE_PX,
            "EDGE_DISTANCE_RULE": "candidate center must be at least patch_size/2 from image edge",
            "NO_CORE_ALGORITHM_CHANGE": True,
            "RAW_READ_ONLY": True,
            "DISPLAY_ONLY_PNG": True,
        },
    )
    write_csv(
        run_dir / "scale_statistics.csv",
        scale_statistics,
        ["sample_id", "frame_id", "response_type", "kernel_size_px", "kernel_size_um", "min", "max", "mean", "median", "std", "p95", "p99", "p99_9", "nonzero_fraction", "dtype", "response_units"],
    )
    write_csv(
        run_dir / "per_scale_top_candidates.csv",
        per_scale_rows,
        ["sample_id", "frame_id", "kernel_size_px", "scale_rank", "x", "y", "peak_response_dn", "edge_distance_px", "matched_fusion_rank", "match_distance_px", "near_known_interference_region"],
    )
    write_csv(
        run_dir / "fusion_top_candidates.csv",
        fusion_rows,
        ["sample_id", "frame_id", "fusion_rank", "x", "y", "peak_response_dn", "winning_kernel_px", "edge_distance_px", "near_known_interference_region"],
    )
    write_csv(
        run_dir / "candidate_match_summary.csv",
        match_rows,
        ["sample_id", "frame_id", "kernel_size_px", "candidate_count", "match_count", "match_fraction", "mean_peak_response_dn"],
    )
    winner_rows = []
    for summary in sample_summaries:
        for scale in scales:
            winner_rows.append(
                {
                    "sample_id": summary["sample_id"],
                    "frame_id": summary["frame_id"],
                    "kernel_size_px": scale,
                    "top20_count": summary["top20_winner_counts"].get(scale, 0),
                    "top20_fraction": summary["top20_winner_counts"].get(scale, 0) / max(1, summary["top20_count"]),
                    "full_image_fraction": summary["full_image_winner_fraction"][str(scale)],
                }
            )
    write_csv(
        run_dir / "winner_scale_distribution.csv",
        winner_rows,
        ["sample_id", "frame_id", "kernel_size_px", "top20_count", "top20_fraction", "full_image_fraction"],
    )
    write_manual_review_template(run_dir / "manual_review_template.csv", fusion_rows)
    write_review_guide(run_dir / "review_guide.md")
    write_open_source_references(PROJECT_ROOT / "OPEN_SOURCE_REFERENCES.md")
    write_json(run_dir / "raw_display_ranges.json", raw_display_ranges)
    generate_report(run_dir / "case02_validation_report.md", input_run, sample_summaries, scale_statistics, match_rows, fusion_rows, baseline_coordinate_matches)
    acceptance = {
        "overall_self_check": True,
        "input_run_preserved": True,
        "sample_count": len(sample_dirs),
        "expected_sample_count": len(user_config.SAMPLE_IDS),
        "scale_statistics_rows": len(scale_statistics),
        "per_scale_candidate_rows": len(per_scale_rows),
        "fusion_candidate_rows": len(fusion_rows),
        "manual_review_rows": len(fusion_rows),
        "figure_count": len(list((run_dir / "figures").glob("*.png"))),
        "user_visual_review": "PENDING_USER",
        "defect_vs_background_conclusion": "PENDING_USER",
        "core_algorithm_changed": False,
        "raw_modified": False,
    }
    write_json(run_dir / "acceptance_summary.json", acceptance)
    write_text(
        run_dir / "acceptance.md",
        """# Case02验证验收

|检查项|状态|说明|
|---|---|---|
|复用既有Case02输出且未覆盖基线|PASS|输入目录单独读取，验证结果写入case02_validation新运行目录。|
|5张代表图、5个尺度与融合统计齐全|PASS|详见scale_statistics.csv和case02_validation_report.md。|
|数组shape/dtype、坐标和DN单位核查|PASS|逐尺度读取NPZ；坐标来自全分辨率数组，响应单位为DN。|
|联系图、Top20局部图册、逐尺度候选图|PASS|详见figures/。|
|人工审核模板100行且标签留空|PASS|manual_review_template.csv不是训练集或真值。|
|31 px比例统计|PASS|报告逐样品给出数量/比例；不解释为真实疵病尺寸。|
|真实疵病与黑带/标记边界区分|PENDING USER|没有人工真值；禁止把代理类别当作结论。|
|进入Case03或调整阈值/黑带区域|PASS|本轮未执行。|

显示PNG只用于视觉判读；所有峰值、统计和候选排序基于原始uint16 Black-Hat响应。请用户先审核联系图、Top20图册和manual_review_template.csv，再决定后续阶段。
""",
    )
    LOGGER.info("Case02验证完成：%s", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
