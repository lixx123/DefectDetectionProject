"""Read-only, memory-mapped RAW access and bounded display thumbnails."""
from pathlib import Path
import numpy as np
from PySide6.QtGui import QImage


class RawImageProvider:
    def __init__(self, path, width=11276, height=9200):
        self.path = Path(path)
        self.width, self.height = width, height
        if self.path.stat().st_size != width * height * 2:
            raise ValueError(f"RAW 大小不正确，应为 {width * height * 2:,} 字节")
        self._raw = np.memmap(self.path, dtype='>u2', mode='r', shape=(height, width))

    def dn(self, x, y):
        if self._raw is not None and 0 <= x < self.width and 0 <= y < self.height:
            return int(self._raw[y, x])
        return None

    def thumbnail(self, limit=2800):
        step = max(1, int(np.ceil(max(self.width, self.height) / limit)))
        sample = self._raw[::step, ::step]
        # Display LUT only: no write to the mmap or algorithm input.
        gray = np.clip(sample.astype(np.float32) * (255.0 / 4095), 0, 255).astype(np.uint8)
        return QImage(gray.data, gray.shape[1], gray.shape[0], gray.strides[0],
                      QImage.Format.Format_Grayscale8).copy()

    def crop(self, x0, y0, x1, y1):
        sample = self._raw[y0:y1, x0:x1]
        gray = np.clip(sample.astype(np.float32) * (255.0 / 4095), 0, 255).astype(np.uint8)
        return QImage(gray.data, gray.shape[1], gray.shape[0], gray.strides[0],
                      QImage.Format.Format_Grayscale8).copy()

    def clear(self):
        if self._raw is not None:
            self._raw._mmap.close()
            self._raw = None
