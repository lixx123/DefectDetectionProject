"""Case00读取模块的轻量级单元测试。"""

from pathlib import Path

import numpy as np
import pytest

from src.io.raw_reader import RawReadConfig, read_raw, summarize_raw


def test_read_big_endian_small_fixture(tmp_path: Path) -> None:
    config = RawReadConfig(width=3, height=2, effective_bits=12, endian="big")
    values = np.array([[1, 256, 4095], [0, 17, 2048]], dtype=np.uint16)
    path = tmp_path / "fixture.raw"
    values.astype(">u2").tofile(path)
    decoded = read_raw(path, config)
    assert decoded.dtype == np.uint16
    np.testing.assert_array_equal(decoded, values)
    summary = summarize_raw(decoded, config)
    assert summary["within_effective_range"] is True
    assert summary["nonconstant"] is True


def test_read_rejects_wrong_file_size(tmp_path: Path) -> None:
    config = RawReadConfig(width=2, height=2, effective_bits=12, endian="big")
    path = tmp_path / "wrong.raw"
    path.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError, match="文件大小不符"):
        read_raw(path, config)
