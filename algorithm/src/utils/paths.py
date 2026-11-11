"""工程路径、输入文件发现和运行目录管理。"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable


def parse_raw_identity(path: Path) -> tuple[int, int]:
    """从 260624 文件名解析 `(sample_id, frame_id)`。

    文件名约定为 `26 (1).raw` 或 `27-1_000.raw`。仅使用前两个数字组，
    避免把 `_000` 误识别为帧号。解析失败时抛出 ValueError，不猜测映射。
    """

    groups = re.findall(r"\d+", path.stem)
    if len(groups) < 2:
        raise ValueError(f"无法从文件名解析样品和帧编号: {path.name}")
    return int(groups[0]), int(groups[1])


def discover_raw_files(data_root: Path) -> list[dict]:
    """扫描 RAW 文件并返回排序后的输入清单，不读取或修改原始内容。"""

    records: list[dict] = []
    for path in sorted(data_root.glob("*.raw")):
        sample_id, frame_id = parse_raw_identity(path)
        records.append(
            {
                "path": path,
                "sample_id": sample_id,
                "frame_id": frame_id,
                "filename": path.name,
                "file_bytes": path.stat().st_size,
            }
        )
    return sorted(records, key=lambda item: (item["sample_id"], item["frame_id"], item["filename"]))


def create_run_directory(output_root: Path, case_name: str, run_id: str | None = None) -> Path:
    """创建不覆盖历史结果的运行目录。"""

    stamp = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    base = output_root / case_name / stamp
    run_dir = base
    suffix = 1
    while run_dir.exists():
        run_dir = output_root / case_name / f"{stamp}_{suffix:02d}"
        suffix += 1
    for subdir in (run_dir, run_dir / "previews", run_dir / "profiles", run_dir / "logs"):
        subdir.mkdir(parents=True, exist_ok=False)
    return run_dir


def json_safe(value):
    """递归转换 Path、tuple 等对象，供参数快照和JSON结果使用。"""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def write_json(path: Path, payload: dict) -> None:
    """以UTF-8写入格式化JSON结果。"""

    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    """以UTF-8写入字典记录CSV。"""

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
