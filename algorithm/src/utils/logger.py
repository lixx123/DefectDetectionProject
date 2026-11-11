"""统一日志配置。"""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_path: Path) -> logging.Logger:
    """配置同时写入文件和控制台的工程日志。"""

    logger = logging.getLogger("filter_defect_detection")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger
