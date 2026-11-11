"""滤光片疵病检测工程主入口。

当前主流程支持Case00 RAW体检和Case02单张图多尺度Black-Hat；Case02验证
诊断由`scripts/validate_case02.py`独立执行，避免把诊断逻辑堆入主入口。
"""

from __future__ import annotations

import argparse
import gc
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import user_config
from src.detection.blackhat import estimate_memory_bytes, response_statistics
from src.detection.multiscale import iter_scale_responses
from src.io.image_writer import save_preview
from src.io.raw_reader import RawReadConfig, read_raw, summarize_raw
from src.qc.image_statistics import compute_histogram
from src.qc.profile_analysis import compute_profiles, save_profiles
from src.utils.logger import configure_logging
from src.utils.paths import (
    create_run_directory,
    discover_raw_files,
    json_safe,
    write_csv,
    write_json,
)
from src.visualization.defect_response import (
    extract_top_patches,
    save_response_preview,
    save_winning_scale_preview,
)


def parse_args() -> argparse.Namespace:
    """解析主入口参数。"""

    parser = argparse.ArgumentParser(description="滤光片疵病检测工程入口")
    parser.add_argument("--case", type=str, required=True, help="阶段编号：0=RAW体检，1=已回滚，2=Black-Hat，3c=特征分析，3d=复核排序，3d-auto=自动疑似疵病/噪声倾向判别，3e=10处局部轮廓精修对照，3e2=多候选自动发现和互补融合")
    parser.add_argument("--sample", type=int, default=None, help="可选样品编号，例如26")
    parser.add_argument("--frame", type=int, default=None, help="可选帧编号，例如1")
    parser.add_argument("--run-id", type=str, default=None, help="可选输出运行目录名")
    parser.add_argument("--input", type=Path, default=None, help="统一检测输入RAW路径；尺寸/字节序按config/user_config.py")
    parser.add_argument("--fresh", action="store_true", help="从输入RAW重新计算BlackHat、J4/J5、K8和最终检测")
    parser.add_argument('--roi-mode', choices=['full','roi-j4','roi-bh'], default=None,
                        help='两级流程：full对照、roi-j4仅减少扫描、roi-bh同时减少BH；只验证26双帧')
    return parser.parse_args()


def snapshot_config() -> dict:
    """读取用户配置并返回可JSON序列化快照。"""

    return json_safe(user_config.as_dict())


def filter_records(records: list[dict], sample_id: int | None, frame_id: int | None) -> list[dict]:
    """按CLI可选条件筛选输入文件。"""

    return [
        record
        for record in records
        if (sample_id is None or record["sample_id"] == sample_id)
        and (frame_id is None or record["frame_id"] == frame_id)
    ]


def write_acceptance(
    path: Path,
    records: list[dict],
    stats: list[dict],
    run_dir: Path,
    config: RawReadConfig,
) -> dict:
    """基于可检查证据生成Case00一级验收记录。"""

    expected_bytes_ok = all(item["file_bytes"] == config.expected_bytes for item in records)
    expected_count = len(records) == len(user_config.SAMPLE_IDS) * len(user_config.FRAME_IDS)
    stats_ok = len(stats) == len(records) and all(
        item["finite"] and item["within_effective_range"] and item["nonconstant"] for item in stats
    )
    preview_paths = list((run_dir / "previews").glob("*.png"))
    profile_csv_paths = list((run_dir / "profiles").glob("*_profiles.csv"))
    profile_png_paths = list((run_dir / "profiles").glob("*_profiles.png"))
    output_files_ok = (
        len(preview_paths) == len(records)
        and len(profile_csv_paths) == len(records)
        and len(profile_png_paths) == len(records)
        and (run_dir / "histograms.csv").exists()
        and (run_dir / "frame_statistics.csv").exists()
        and (run_dir / "config_snapshot.json").exists()
    )
    all_pass = expected_count and expected_bytes_ok and stats_ok and output_files_ok

    def mark(value: bool) -> str:
        return "PASS" if value else "FAIL"

    lines = [
        "# Case00 验收记录",
        "",
        "## 本阶段目标",
        "",
        "完成260624批次20帧RAW读取、统计、直方图、行/列平均曲线和8 bit显示预览，并保留原始12 bit DN与显示数据的边界。",
        "",
        "## 一级验收（Codex自验）",
        "",
        "| 验收项 | 结果 | 证据 | 说明 |",
        "|---|---|---|---|",
        f"| 20帧输入文件全部发现 | {mark(expected_count)} | `input_manifest.csv` | 实际记录数={len(records)}，预期={len(user_config.SAMPLE_IDS) * len(user_config.FRAME_IDS)} |",
        f"| 文件大小等于11276×9200×2 | {mark(expected_bytes_ok)} | `input_manifest.csv` | 期望字节数={config.expected_bytes} |",
        f"| 大端解码并可reshape | {mark(stats_ok)} | `frame_statistics.csv` | 每帧均完成读取、统计和有效范围检查 |",
        f"| DN主要落在0~4095且无空/全常量帧 | {mark(stats_ok)} | `frame_statistics.csv` | `within_effective_range`、`nonconstant`、`finite`逐帧检查 |",
        f"| 每帧输出预览、行/列曲线、直方图 | {mark(output_files_ok)} | `previews/`, `profiles/`, `histograms.csv` | 输出数量与输入帧数逐项核对 |",
        "| 原始DN与8 bit显示严格分开 | PASS | `src/io/raw_reader.py`, `src/io/image_writer.py` | 统计使用原始数组，预览单独写PNG |",
        "| 预览空间结构人工视觉复核 | PENDING USER | `previews/` | 本项需用户结合现场预期确认，不据此擅自进入下一阶段 |",
        "",
        "## 当前结论",
        "",
        f"- Codex一级自验总体：**{'PASS' if all_pass else 'FAIL'}**。",
        "- 本记录不代表用户验收通过；必须等待用户明确回复后才能进入下一阶段。",
        "- 当前仅实施 Case00，未执行旧Case01配准、背景建模、Black-Hat、阈值或缺陷判型。",
        "",
        "## 遗留问题",
        "",
        "- 需要用户确认预览图的空间结构是否符合设备现场预期，以及是否接受当前大端解码结果。",
        "- 44所数据和厂家平面玻璃结果尚未纳入主流程。",
        "",
        "## 是否允许进入下一阶段",
        "",
        "否。即使一级自验通过，也必须等待用户明确回复 `继续Case02`。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "overall_pass": all_pass,
        "expected_count": expected_count,
        "expected_bytes_ok": expected_bytes_ok,
        "stats_ok": stats_ok,
        "output_files_ok": output_files_ok,
        "preview_visual_review": "PENDING_USER",
    }


def run_case00(args: argparse.Namespace) -> Path:
    """执行Case00并返回本次运行目录。"""

    records = filter_records(
        discover_raw_files(user_config.DATA_ROOT), args.sample, args.frame
    )
    run_dir = create_run_directory(user_config.OUTPUT_ROOT, "case00", args.run_id)
    logger = configure_logging(run_dir / "logs" / "case00.log")
    write_json(run_dir / "config_snapshot.json", snapshot_config())
    logger.info("Case00启动，输入记录数=%d，运行目录=%s", len(records), run_dir)

    read_config = RawReadConfig(
        width=user_config.RAW_WIDTH,
        height=user_config.RAW_HEIGHT,
        effective_bits=user_config.EFFECTIVE_BITS,
        endian=user_config.RAW_ENDIAN,
    )
    manifest_rows = []
    stats_rows = []
    histogram_path = run_dir / "histograms.csv"
    for record in records:
        sample_id = record["sample_id"]
        frame_id = record["frame_id"]
        frame_key = f"sample_{sample_id}_frame_{frame_id}"
        logger.info("读取 %s", record["filename"])
        image = read_raw(record["path"], read_config)
        stats = summarize_raw(image, read_config)
        histogram, overflow = compute_histogram(image, read_config.effective_bits)
        preview_path = run_dir / "previews" / f"{frame_key}.png"
        preview_info = save_preview(
            image, preview_path, read_config.effective_bits, user_config.PREVIEW_MAX_SIZE
        )
        row_mean, col_mean = compute_profiles(image)
        profile_csv = run_dir / "profiles" / f"{frame_key}_profiles.csv"
        profile_png = run_dir / "profiles" / f"{frame_key}_profiles.png"
        save_profiles(
            row_mean,
            col_mean,
            profile_csv,
            profile_png,
            frame_key,
            user_config.PROFILE_PLOT_DPI,
        )
        stats.update(
            {
                "sample_id": sample_id,
                "frame_id": frame_id,
                "filename": record["filename"],
                "preview_width": preview_info["width"],
                "preview_height": preview_info["height"],
                "display_std": preview_info["std_display"],
                "histogram_overflow_count": overflow,
                "row_mean_min_dn": float(row_mean.min()),
                "row_mean_max_dn": float(row_mean.max()),
                "col_mean_min_dn": float(col_mean.min()),
                "col_mean_max_dn": float(col_mean.max()),
            }
        )
        stats_rows.append(stats)
        manifest_rows.append(
            {
                "sample_id": sample_id,
                "frame_id": frame_id,
                "filename": record["filename"],
                "path": str(record["path"]),
                "file_bytes": record["file_bytes"],
                "expected_bytes": read_config.expected_bytes,
                "file_size_ok": record["file_bytes"] == read_config.expected_bytes,
                "decoded_shape": f"{image.shape[1]}x{image.shape[0]}",
                "raw_dtype": str(image.dtype),
                "preview_path": str(preview_path),
                "profile_csv": str(profile_csv),
                "profile_png": str(profile_png),
            }
        )
        logger.info(
            "%s 完成: min=%d max=%d mean=%.3f std=%.3f overflow=%d",
            frame_key,
            stats["min_dn"],
            stats["max_dn"],
            stats["mean_dn"],
            stats["std_dn"],
            stats["overflow_gt_4095_count"],
        )

        # 直方图使用追加方式写出，保持每个DN的原始计数，不生成增强图。
        with histogram_path.open("a", encoding="utf-8-sig", newline="") as handle:
            if histogram_path.stat().st_size == 0:
                handle.write("frame_key,dn,count\n")
            for dn, count in enumerate(histogram):
                handle.write(f"{frame_key},{dn},{int(count)}\n")
            handle.write(f"{frame_key},OVERFLOW_GT_EFFECTIVE_MAX,{overflow}\n")

    manifest_fields = [
        "sample_id", "frame_id", "filename", "path", "file_bytes", "expected_bytes",
        "file_size_ok", "decoded_shape", "raw_dtype", "preview_path", "profile_csv", "profile_png",
    ]
    stats_fields = list(stats_rows[0].keys()) if stats_rows else []
    write_csv(run_dir / "input_manifest.csv", manifest_rows, manifest_fields)
    write_csv(run_dir / "frame_statistics.csv", stats_rows, stats_fields)
    acceptance = write_acceptance(run_dir / "acceptance.md", records, stats_rows, run_dir, read_config)
    write_json(run_dir / "acceptance_summary.json", acceptance)
    logger.info("Case00一级自验结果: %s", acceptance)
    return run_dir


def _save_numeric_array(path: Path, name: str, array: np.ndarray) -> None:
    """压缩保存定量响应数组；PNG只作为人工显示文件。"""

    np.savez_compressed(path, **{name: array})


def write_case02_acceptance(
    path: Path,
    records: list[dict],
    sample_results: list[dict],
    run_dir: Path,
) -> dict:
    """生成Case02一级验收记录。"""

    expected_count = len(records) == len(user_config.SAMPLE_IDS)
    output_ok = expected_count and all(item["output_ok"] for item in sample_results)
    numeric_ok = expected_count and all(item["numeric_ok"] for item in sample_results)
    scale_ok = expected_count and all(item["scale_ok"] for item in sample_results)
    dtype_ok = expected_count and all(item["dtype_ok"] for item in sample_results)
    top_patch_ok = expected_count and all(item["top_patch_ok"] for item in sample_results)
    all_pass = expected_count and output_ok and numeric_ok and scale_ok and dtype_ok and top_patch_ok
    boundary_proxy_count = sum(item["boundary_like_proxy_count"] for item in sample_results)
    local_proxy_count = sum(item["local_response_proxy_count"] for item in sample_results)
    manual_review_count = sum(item["manual_review_count"] for item in sample_results)

    def mark(value: bool) -> str:
        return "PASS" if value else "FAIL"

    lines = [
        "# Case02 验收记录",
        "",
        "## 本阶段目标",
        "",
        "对5个样品各自的第1帧执行单张原始12 bit RAW多尺度Black-Hat暗异常增强；不使用配准、帧间差分、多帧平均、阈值分类或其他增强算法。",
        "",
        "## 回滚验收",
        "",
        "- 活动代码已恢复到Case00功能集合；旧Case01不再由主入口执行，历史`outputs/case01/`仅作追溯。",
        "- Case00运行与Case00测试在本阶段开始前已核对通过；本阶段没有读取或修改历史Case01结果作为输入。",
        "",
        "## 一级验收（Codex自验）",
        "",
        "| 验收项 | 结果 | 证据 | 说明 |",
        "|---|---|---|---|",
        f"| 5张代表图全部完成 | {mark(expected_count)} | `samples/` | 实际={len(records)}，预期={len(user_config.SAMPLE_IDS)} |",
        f"| Black-Hat模块化且逐尺度输出 | {mark(output_ok)} | `src/detection/`, `samples/*/responses/` | 5个尺度、融合图和尺度图均存在 |",
        f"| 原始12 bit DN输入、响应非负且无dtype溢出 | {mark(numeric_ok and dtype_ok)} | `blackhat_statistics.csv`, `*.npz` | 数值统计来自uint16响应数组 |",
        f"| 3/5/9/15/31 px全部运行且尺度有差异 | {mark(scale_ok)} | `blackhat_statistics.csv` | 每张图逐尺度记录统计 |",
        f"| Top-N patch带坐标、峰值和胜出尺度 | {mark(top_patch_ok)} | `samples/*/patches/top_patches.csv` | 仅用于人工观察，不等于最终判定 |",
        "| 黑带/强边界是否主导响应 | PENDING USER | `top_patches.csv`, `blackhat_fused_preview.png` | 当前只提供代理分类和人工复核材料，不宣称检测效果良好 |",
        "",
        "## Top-N响应代理汇总（非Ground Truth）",
        "",
        f"- boundary_like_proxy：{boundary_proxy_count}",
        f"- local_response_proxy：{local_proxy_count}",
        f"- manual_review_required：{manual_review_count}",
        "- 以上分类仅根据patch内部响应形状作工程复核提示，不能替代人工确认或最终缺陷标签。",
        "",
        "## 当前结论",
        "",
        f"- Codex一级自验总体：**{'PASS' if all_pass else 'FAIL'}**。",
        "- Black-Hat基础实现不等于最终疵病检测结论；若Top-N主要来自黑带/强边界，应将其记录为背景干扰问题。",
        "- 本阶段没有进入阈值、形态学清理、连通域或缺陷分类。",
        "",
        "## 遗留问题",
        "",
        "- 需要用户查看5张代表图的多尺度响应和Top-N patch，确认强边界、白色标记与局部暗点/暗线的相对占比。",
        "- 如需进入下一阶段，必须由用户明确回复`通过/继续Case03`；本次执行到此停止。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "overall_pass": all_pass,
        "representative_count": len(records),
        "expected_count": len(user_config.SAMPLE_IDS),
        "output_ok": output_ok,
        "numeric_ok": numeric_ok,
        "scale_ok": scale_ok,
        "dtype_ok": dtype_ok,
        "top_patch_ok": top_patch_ok,
        "boundary_like_proxy_count": boundary_proxy_count,
        "local_response_proxy_count": local_proxy_count,
        "manual_review_count": manual_review_count,
        "user_visual_review": "PENDING_USER",
    }


def run_case02(args: argparse.Namespace) -> Path:
    """执行单张图多尺度Black-Hat阶段。"""

    records = [
        record
        for record in discover_raw_files(user_config.DATA_ROOT)
        if record["frame_id"] == (args.frame if args.frame is not None else 1)
        and (args.sample is None or record["sample_id"] == args.sample)
    ]
    if args.sample is None and args.frame is None:
        expected_samples = set(user_config.SAMPLE_IDS)
        if {record["sample_id"] for record in records} != expected_samples:
            raise FileNotFoundError("Case02代表图必须包含样品26~30的第1帧")
    run_dir = create_run_directory(user_config.OUTPUT_ROOT, "case02", args.run_id)
    logger = configure_logging(run_dir / "logs" / "case02.log")
    snapshot = snapshot_config()
    snapshot.update(
        {
            "STAGE": "Case02",
            "REPRESENTATIVE_FRAME_ID": args.frame if args.frame is not None else 1,
            "NO_REGISTRATION": True,
            "NO_FRAME_DIFFERENCE": True,
        }
    )
    write_json(run_dir / "config_snapshot.json", snapshot)
    memory_estimate = estimate_memory_bytes(user_config.RAW_WIDTH, user_config.RAW_HEIGHT)
    write_json(run_dir / "memory_estimate.json", memory_estimate)
    logger.info("Case02启动，代表图数=%d，内存估算=%s", len(records), memory_estimate)

    raw_config = RawReadConfig(
        width=user_config.RAW_WIDTH,
        height=user_config.RAW_HEIGHT,
        effective_bits=user_config.EFFECTIVE_BITS,
        endian=user_config.RAW_ENDIAN,
    )
    statistics_rows: list[dict] = []
    sample_results: list[dict] = []
    for record in sorted(records, key=lambda item: item["sample_id"]):
        sample_id = record["sample_id"]
        frame_id = record["frame_id"]
        sample_key = f"sample_{sample_id}_frame_{frame_id}"
        sample_dir = run_dir / "samples" / sample_key
        response_dir = sample_dir / "responses"
        patch_dir = sample_dir / "patches"
        response_dir.mkdir(parents=True, exist_ok=False)
        patch_dir.mkdir(parents=True, exist_ok=False)
        logger.info("读取单张代表图 %s", record["filename"])
        image_dn = read_raw(record["path"], raw_config)
        save_preview(
            image_dn,
            sample_dir / "raw_preview_8bit.png",
            user_config.EFFECTIVE_BITS,
            user_config.PREVIEW_MAX_SIZE,
        )
        fused = np.zeros(image_dn.shape, dtype=np.uint16)
        winning = np.zeros(image_dn.shape, dtype=np.uint8)
        scale_max_values: list[int] = []
        scale_rows: list[dict] = []
        for scale_index, (kernel_size_px, response, stats) in enumerate(
            iter_scale_responses(
                image_dn,
                user_config.BLACKHAT_KERNEL_SIZES_PX,
                user_config.BLACKHAT_KERNEL_SHAPE,
            ),
            start=1,
        ):
            scale_max_values.append(stats["max"])
            response_stem = f"blackhat_{kernel_size_px}px"
            _save_numeric_array(response_dir / f"{response_stem}.npz", "response_dn", response)
            preview_info = save_response_preview(
                response,
                response_dir / f"{response_stem}_preview.png",
                user_config.BLACKHAT_PREVIEW_PERCENTILE_LOW,
                user_config.BLACKHAT_PREVIEW_PERCENTILE_HIGH,
            )
            update = response > fused
            fused[update] = response[update]
            winning[update] = scale_index
            scale_rows.append(
                {
                    "sample_id": sample_id,
                    "frame_id": frame_id,
                    "response_type": "scale",
                    "kernel_size_px": kernel_size_px,
                    "kernel_size_um": kernel_size_px * user_config.PIXEL_SIZE_UM,
                    **stats,
                    "preview_low_dn": preview_info["display_low_dn"],
                    "preview_high_dn": preview_info["display_high_dn"],
                    "response_npz": str(response_dir / f"{response_stem}.npz"),
                    "response_preview": str(response_dir / f"{response_stem}_preview.png"),
                }
            )
            logger.info(
                "%s %spx: max=%d p99.9=%.3f nonzero=%.6f",
                sample_key,
                kernel_size_px,
                stats["max"],
                stats["p99_9"],
                stats["nonzero_fraction"],
            )
            del response
            gc.collect()

        fused_stats = response_statistics(fused)
        _save_numeric_array(response_dir / "blackhat_fused.npz", "fused_response_dn", fused)
        fused_preview_info = save_response_preview(
            fused,
            response_dir / "blackhat_fused_preview.png",
            user_config.BLACKHAT_PREVIEW_PERCENTILE_LOW,
            user_config.BLACKHAT_PREVIEW_PERCENTILE_HIGH,
        )
        _save_numeric_array(response_dir / "winning_scale_map.npz", "winning_scale", winning)
        save_winning_scale_preview(
            winning,
            response_dir / "winning_scale_map_preview.png",
            len(user_config.BLACKHAT_KERNEL_SIZES_PX),
        )
        scale_rows.append(
            {
                "sample_id": sample_id,
                "frame_id": frame_id,
                "response_type": "fused",
                "kernel_size_px": "fused",
                "kernel_size_um": 0.0,
                **fused_stats,
                "preview_low_dn": fused_preview_info["display_low_dn"],
                "preview_high_dn": fused_preview_info["display_high_dn"],
                "response_npz": str(response_dir / "blackhat_fused.npz"),
                "response_preview": str(response_dir / "blackhat_fused_preview.png"),
            }
        )
        patch_rows = extract_top_patches(
            image_dn,
            fused,
            winning,
            list(user_config.BLACKHAT_KERNEL_SIZES_PX),
            patch_dir,
            user_config.BLACKHAT_TOP_PATCH_COUNT,
            user_config.BLACKHAT_PATCH_SIZE_PX,
            user_config.BLACKHAT_TOP_PATCH_MIN_DISTANCE_PX,
            user_config.EFFECTIVE_BITS,
            user_config.BLACKHAT_PREVIEW_PERCENTILE_LOW,
            user_config.BLACKHAT_PREVIEW_PERCENTILE_HIGH,
        )
        review_counts = {
            "boundary_like_proxy_count": sum(row.get("review_category_proxy") == "boundary_like_proxy" for row in patch_rows),
            "local_response_proxy_count": sum(row.get("review_category_proxy") == "local_response_proxy" for row in patch_rows),
            "manual_review_count": sum(row.get("review_category_proxy") == "manual_review_required" for row in patch_rows),
        }
        write_json(sample_dir / "top_patch_review_summary.json", review_counts)
        write_json(sample_dir / "sample_summary.json", {"sample_id": sample_id, "frame_id": frame_id, "scale_max_values": scale_max_values, **review_counts})
        statistics_rows.extend(scale_rows)
        sample_results.append(
            {
                "sample_id": sample_id,
                "output_ok": all(
                    (response_dir / f"blackhat_{size}px.npz").exists()
                    and (response_dir / f"blackhat_{size}px_preview.png").exists()
                    for size in user_config.BLACKHAT_KERNEL_SIZES_PX
                ) and (response_dir / "blackhat_fused.npz").exists()
                and (response_dir / "winning_scale_map.npz").exists()
                and (sample_dir / "raw_preview_8bit.png").exists(),
                "numeric_ok": all(row["nonnegative"] and row["finite"] for row in scale_rows),
                "dtype_ok": all(row["dtype"] == "uint16" for row in scale_rows),
                "scale_ok": len(set(scale_max_values)) > 1 and len(scale_max_values) == len(user_config.BLACKHAT_KERNEL_SIZES_PX),
                "top_patch_ok": len(patch_rows) > 0 and (patch_dir / "top_patches.csv").exists(),
                **review_counts,
            }
        )
        del image_dn, fused, winning
        gc.collect()

    stats_fields = [
        "sample_id", "frame_id", "response_type", "kernel_size_px", "kernel_size_um",
        "min", "max", "mean", "median", "std", "p90", "p95", "p99", "p99_5", "p99_9",
        "nonzero_fraction", "finite", "nonnegative", "dtype", "preview_low_dn", "preview_high_dn",
        "response_npz", "response_preview",
    ]
    write_csv(run_dir / "blackhat_statistics.csv", statistics_rows, stats_fields)
    acceptance = write_case02_acceptance(run_dir / "acceptance.md", records, sample_results, run_dir)
    write_json(run_dir / "acceptance_summary.json", acceptance)
    logger.info("Case02一级自验结果: %s", acceptance)
    return run_dir


def main() -> int:
    """主函数：Case01旧配准已回滚，当前支持Case00和Case02。"""

    args = parse_args()
    if args.case == "0":
        run_dir = run_case00(args)
        print(f"Case00完成，输出目录: {run_dir}")
    elif args.case == "1":
        raise SystemExit("旧Case01配准已回滚；当前不会执行配准。")
    elif args.case == "2":
        run_dir = run_case02(args)
        print(f"Case02完成，输出目录: {run_dir}")
    elif args.case.lower() == "3c":
        from scripts.run_case03c import run_from_main

        return run_from_main(args.run_id)
    elif args.case.lower() == "3d":
        from scripts.run_case03d import run_from_main

        return run_from_main(args.run_id)
    elif args.case.lower() in {"3d-auto","3d_auto"}:
        from scripts.run_case03d_autodetect import run

        run(args.run_id)
        return 0
    elif args.case.lower() == "3e":
        from scripts.run_case03e_local_boundary_pilot import run

        run(args.run_id)
        return 0
    elif args.case.lower() in {"3e2","3e-2"}:
        from scripts.run_case03e2_multicandidate_fusion import run

        run(args.run_id,hseeded=True)
        return 0
    elif args.case.lower() in {"3e2-legacy","3e2-legacy-multi"}:
        from scripts.run_case03e2_multicandidate_fusion import run

        run(args.run_id,hseeded=False)
        return 0
    elif args.case.lower() in {"3g", "3g-joint"}:
        from scripts.run_case03g_joint_noise_refinement import run
        from src.detection.case03g_joint_gate import JointGateConfig

        run(args.run_id or "run_20261010_10target_noise_refinement_v1",
            JointGateConfig(
                protect_support_area_min_px=user_config.CASE03G_PROTECT_STRUCTURE_MIN_AREA_PX,
                protect_support_radius_px=user_config.CASE03G_PROTECT_STRUCTURE_RADIUS_PX,
                protect_any_existing_refinement=user_config.CASE03G_PROTECT_EXISTING_REFINEMENT,
            ))
        return 0
    elif args.case.lower() in {"3h", "3h-texture"}:
        from scripts.run_case03h_texture_trial import run
        from src.detection.case03h_background_texture import TextureTrialConfig

        run(args.run_id or "run_20261010_10target_texture_dog_guard_v3",
            TextureTrialConfig(
                medium_min_area_px=user_config.CASE03H_MEDIUM_MIN_AREA_PX,
                medium_max_area_px=user_config.CASE03H_MEDIUM_MAX_AREA_PX,
                min_relative_contrast=user_config.CASE03H_MIN_RELATIVE_CONTRAST,
                min_significance_z=user_config.CASE03H_MIN_SIGNIFICANCE_Z,
                protect_peak_dn=user_config.CASE03H_PROTECT_BLACKHAT_PEAK_DN,
                protect_dog_median_dn=user_config.CASE03H_PROTECT_DOG_MEDIAN_DN,
                dog_small_sigma_px=user_config.CASE03H_DOG_SMALL_SIGMA_PX,
                dog_large_sigma_px=user_config.CASE03H_DOG_LARGE_SIGMA_PX,
                protect_big_area_px=user_config.CASE03H_PROTECT_BIG_AREA_PX,
                protect_big_radius_px=user_config.CASE03H_PROTECT_BIG_RADIUS_PX,
                protect_stroke_min_length_px=user_config.CASE03H_PROTECT_STROKE_MIN_LENGTH_PX,
                protect_stroke_aspect=user_config.CASE03H_PROTECT_STROKE_ASPECT,
            ))
        return 0
    elif args.case.lower() in {"3i","3i-grade","3i-annotation"}:
        from scripts.run_case03i_annotation import run
        from src.detection.case03i_size_grade import SizeGradeConfig

        run(args.run_id or "run_20261010_frame1_frame2_pixel_grade_v2",
            SizeGradeConfig(
                medium_area_min_px2=user_config.CASE03I_MEDIUM_AREA_MIN_PX2,
                large_area_min_px2=user_config.CASE03I_LARGE_AREA_MIN_PX2,
                medium_length_min_px=user_config.CASE03I_MEDIUM_LENGTH_MIN_PX,
                large_length_min_px=user_config.CASE03I_LARGE_LENGTH_MIN_PX,
                connectivity=user_config.CASE03I_CONNECTIVITY,
                max_per_window=user_config.CASE03I_MAX_COMPONENTS_PER_WINDOW,
            ))
        return 0
    elif args.case.lower() in {"3j","3j-pilot","3j-association"}:
        from scripts.run_case03j_fragment_pilot import run

        run(args.run_id or "run_20261010_W005_fragment_link_guarded_main_v1")
        return 0
    elif args.case.lower() in {"3j2","3j-continuous","3j2-contour"}:
        from scripts.run_case03j_continuous_contour import run

        run(args.run_id or "run_20261010_27windows_one_piece_main_v1",
            only_w005=False)
        return 0
    elif args.case.lower() in {"3j4","3j-fullscan"}:
        from scripts.run_case03j4_fullscan import run

        run(args.run_id or "run_20261012_frame26_1_full_j4_main_v1",
            max_tiles=0,halo=user_config.CASE03J4_HALO_PX)
        return 0
    elif args.case.lower() in {"3j5","3j-global-merge"}:
        from scripts.run_case03j5_global_merge import run

        run(args.run_id or "run_20261012_frame26_1_global_j5_main_v1",
            review_limit=20)
        return 0
    elif args.case.lower() in {"unified-final", "3-final", "3u"}:
        if args.sample not in (None, 26) or args.frame not in (None, 1, 2):
            raise SystemExit("当前统一终检已验证26号第1、2帧。其他样本请勿套用本帧人工审核记录。")
        from scripts.run_unified_final_revision import run as run_unified_final
        if args.roi_mode is not None:
            if args.input is None:raise SystemExit('--roi-mode requires --input RAW_PATH')
            from scripts.run_two_level_unified import run_raw
            run_raw(args.input,args.run_id,args.roi_mode)
        elif args.fresh:
            if args.input is None:raise SystemExit('--fresh requires --input RAW_PATH')
            from scripts.run_unified_raw_input import run_raw
            run_raw(args.input,args.run_id)
        else:
            run_unified_final(args.run_id,frames=(args.frame,) if args.frame else (1,2),input_path=args.input)
        return 0
    else:
        raise SystemExit("支持Case00、Case02、Case03历史阶段以及--case unified-final；Case01已回滚。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
