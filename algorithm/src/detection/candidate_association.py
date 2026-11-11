"""Exact sample-26 S230 to H170/230 component association.

The module rebuilds a disk-backed component label raster from already saved
Case03-B masks.  It never scans the full image once per candidate: each tile
is labelled once, tile-boundary unions are resolved once, and subsequent
feature/association passes read only the sparse non-zero candidate pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
from scipy import ndimage

from src.detection.tiled_components import (
    _UnionFind,
    _join_prior_neighbors,
    _structure,
    _tile_ranges,
)


@dataclass(frozen=True)
class LabelComponent:
    """Stable component geometry in full-image coordinates."""

    component_index: int
    area_px: int
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    centroid_x: float
    centroid_y: float
    peak_response_dn: int
    touches_border: bool


class LabelRaster:
    """Disk-backed provisional labels with stable component-index lookup."""

    def __init__(
        self,
        path: Path,
        labels: np.memmap,
        union_find: _UnionFind,
        root_to_index: dict[int, int],
        components: list[LabelComponent],
        shape: tuple[int, int],
        tile_shape: tuple[int, int],
    ) -> None:
        self.path = path
        self.labels = labels
        self.union_find = union_find
        self.root_to_index = root_to_index
        self.components = components
        self.shape = shape
        self.tile_shape = tile_shape

    def stable_tile(self, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
        """Return a copied tile whose positive values are stable component IDs."""

        provisional = np.array(self.labels[y0:y1, x0:x1], copy=True)
        positive = provisional > 0
        if not np.any(positive):
            return np.zeros(provisional.shape, dtype=np.int32)
        unique, inverse = np.unique(provisional[positive], return_inverse=True)
        stable = np.asarray(
            [self.root_to_index.get(self.union_find.find(int(value)), 0) for value in unique],
            dtype=np.int32,
        )
        output = np.zeros(provisional.shape, dtype=np.int32)
        output[positive] = stable[inverse]
        return output

    def close(self) -> None:
        """Close and remove the temporary disk-backed label raster."""

        self.labels.flush()
        mmap_handle = getattr(self.labels, "_mmap", None)
        del self.labels
        if mmap_handle is not None:
            mmap_handle.close()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "LabelRaster":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def _aggregate_component_features(
    tile_labels: np.ndarray,
    response_tile: np.ndarray,
    y0: int,
    x0: int,
    features: dict[int, dict],
    union_find: _UnionFind,
) -> None:
    positive = tile_labels > 0
    if not np.any(positive):
        return
    labels = tile_labels[positive].astype(np.int64, copy=False)
    responses = response_tile[positive].astype(np.int64, copy=False)
    unique, inverse, counts = np.unique(labels, return_inverse=True, return_counts=True)
    height, width = tile_labels.shape
    flat = np.flatnonzero(positive)
    local_y = flat // width
    local_x = flat % width
    min_y = np.full(unique.size, height, dtype=np.int64)
    min_x = np.full(unique.size, width, dtype=np.int64)
    max_y = np.full(unique.size, -1, dtype=np.int64)
    max_x = np.full(unique.size, -1, dtype=np.int64)
    sum_y = np.zeros(unique.size, dtype=np.int64)
    sum_x = np.zeros(unique.size, dtype=np.int64)
    peak = np.full(unique.size, -1, dtype=np.int64)
    np.minimum.at(min_y, inverse, local_y)
    np.minimum.at(min_x, inverse, local_x)
    np.maximum.at(max_y, inverse, local_y)
    np.maximum.at(max_x, inverse, local_x)
    np.add.at(sum_y, inverse, local_y)
    np.add.at(sum_x, inverse, local_x)
    np.maximum.at(peak, inverse, responses)
    for index, provisional in enumerate(unique.tolist()):
        root = union_find.find(int(provisional))
        area = int(counts[index])
        item = features.setdefault(
            root,
            {
                "area_px": 0,
                "min_x": width + x0,
                "min_y": height + y0,
                "max_x": -1,
                "max_y": -1,
                "sum_x": 0,
                "sum_y": 0,
                "peak_response_dn": -1,
            },
        )
        item["area_px"] += area
        item["min_x"] = min(item["min_x"], int(min_x[index]) + x0)
        item["min_y"] = min(item["min_y"], int(min_y[index]) + y0)
        item["max_x"] = max(item["max_x"], int(max_x[index]) + x0)
        item["max_y"] = max(item["max_y"], int(max_y[index]) + y0)
        item["sum_x"] += int(sum_x[index]) + area * x0
        item["sum_y"] += int(sum_y[index]) + area * y0
        item["peak_response_dn"] = max(item["peak_response_dn"], int(peak[index]))


def build_label_raster(
    mask: np.ndarray,
    response_dn: np.ndarray,
    *,
    connectivity: int,
    tile_shape: tuple[int, int],
    temp_dir: Path,
    name: str,
) -> LabelRaster:
    """Build a stable full-image component raster without a RAM int32 image."""

    if mask.dtype != np.bool_ or mask.ndim != 2:
        raise TypeError("mask must be a 2-D bool array")
    if response_dn.shape != mask.shape:
        raise ValueError("mask and response shape mismatch")
    height, width = mask.shape
    tile_h, tile_w = int(tile_shape[0]), int(tile_shape[1])
    y_ranges = _tile_ranges(height, tile_h)
    x_ranges = _tile_ranges(width, tile_w)
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"{name}_{uuid4().hex}.dat"
    labels = np.memmap(path, dtype=np.int32, mode="w+", shape=(height, width))
    labels[:] = 0
    union_find = _UnionFind()
    structure = _structure(connectivity)
    next_label = 1
    try:
        for y0, y1 in y_ranges:
            for x0, x1 in x_ranges:
                local, local_count = ndimage.label(mask[y0:y1, x0:x1], structure=structure)
                if local_count == 0:
                    continue
                local = local.astype(np.int32, copy=False)
                local[local > 0] += next_label - 1
                _join_prior_neighbors(local, labels, y0, x0, union_find, connectivity)
                labels[y0:y1, x0:x1] = local
                next_label += int(local_count)
        labels.flush()
        features: dict[int, dict] = {}
        for y0, y1 in y_ranges:
            for x0, x1 in x_ranges:
                _aggregate_component_features(
                    np.array(labels[y0:y1, x0:x1], copy=True),
                    response_dn[y0:y1, x0:x1],
                    y0,
                    x0,
                    features,
                    union_find,
                )
        ordered = sorted(features.items(), key=lambda pair: (pair[1]["min_y"], pair[1]["min_x"], -pair[1]["area_px"]))
        components: list[LabelComponent] = []
        root_to_index: dict[int, int] = {}
        for index, (root, item) in enumerate(ordered, start=1):
            root_to_index[root] = index
            min_x, max_x = int(item["min_x"]), int(item["max_x"])
            min_y, max_y = int(item["min_y"]), int(item["max_y"])
            area = int(item["area_px"])
            components.append(
                LabelComponent(
                    component_index=index,
                    area_px=area,
                    bbox_x=min_x,
                    bbox_y=min_y,
                    bbox_w=max_x - min_x + 1,
                    bbox_h=max_y - min_y + 1,
                    centroid_x=float(item["sum_x"] / area),
                    centroid_y=float(item["sum_y"] / area),
                    peak_response_dn=int(item["peak_response_dn"]),
                    touches_border=bool(min_x == 0 or min_y == 0 or max_x == width - 1 or max_y == height - 1),
                )
            )
        return LabelRaster(path, labels, union_find, root_to_index, components, (height, width), (tile_h, tile_w))
    except Exception:
        mmap_handle = getattr(labels, "_mmap", None)
        del labels
        if mmap_handle is not None:
            mmap_handle.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def iter_stable_pixels(label_raster: LabelRaster, mask: np.ndarray):
    """Yield sparse ``(candidate_id, y, x)`` arrays tile by tile."""

    height, width = mask.shape
    tile_h, tile_w = label_raster.tile_shape
    for y0, y1 in _tile_ranges(height, tile_h):
        for x0, x1 in _tile_ranges(width, tile_w):
            stable = label_raster.stable_tile(y0, y1, x0, x1)
            positive = stable > 0
            if not np.any(positive):
                continue
            local_y, local_x = np.nonzero(positive & mask[y0:y1, x0:x1])
            if local_y.size:
                yield stable[local_y, local_x], local_y.astype(np.int64) + y0, local_x.astype(np.int64) + x0


def associate_s_to_h(
    s_raster: LabelRaster,
    h_raster: LabelRaster,
    s_mask: np.ndarray,
    h_mask: np.ndarray,
    *,
    tile_shape: tuple[int, int],
) -> dict:
    """Create a one-S-to-one-H mapping and H core aggregation with checks."""

    if s_mask.shape != h_mask.shape or s_mask.shape != s_raster.shape or s_mask.shape != h_raster.shape:
        raise ValueError("association shapes do not match")
    if np.any(s_mask & ~h_mask):
        raise ValueError("S230 is not a subset of H170/230")
    s_to_h: dict[int, set[int]] = {component.component_index: set() for component in s_raster.components}
    h_core_area = np.zeros(len(h_raster.components) + 1, dtype=np.int64)
    height, width = s_mask.shape
    tile_h, tile_w = tile_shape
    for y0, y1 in _tile_ranges(height, tile_h):
        for x0, x1 in _tile_ranges(width, tile_w):
            s_tile = s_raster.stable_tile(y0, y1, x0, x1)
            if not np.any(s_tile):
                continue
            h_tile = h_raster.stable_tile(y0, y1, x0, x1)
            s_values = s_tile[s_tile > 0]
            h_values = h_tile[s_tile > 0]
            if np.any(h_values <= 0):
                raise ValueError("an S230 pixel has no H170/230 component")
            pairs = np.unique(np.column_stack((s_values, h_values)), axis=0)
            for s_index, h_index in pairs.tolist():
                s_to_h[int(s_index)].add(int(h_index))
            np.add.at(h_core_area, h_values, 1)
    ambiguous = {key: sorted(value) for key, value in s_to_h.items() if len(value) != 1}
    if ambiguous:
        raise ValueError(f"S components without a unique H mapping: {list(ambiguous.items())[:5]}")
    h_core_components: list[set[int]] = [set() for _ in range(len(h_raster.components) + 1)]
    for s_index, h_values in s_to_h.items():
        h_core_components[next(iter(h_values))].add(s_index)
    if int(sum(h_core_area)) != int(np.count_nonzero(s_mask)):
        raise AssertionError("S pixel association area does not conserve")
    if int(sum(len(value) for value in h_core_components)) != len(s_raster.components):
        raise AssertionError("S component association count does not conserve")
    return {
        "s_to_h": {int(key): int(next(iter(value))) for key, value in s_to_h.items()},
        "h_core_area": h_core_area,
        "h_core_components": h_core_components,
        "s_area_px": int(np.count_nonzero(s_mask)),
        "h_area_px": int(np.count_nonzero(h_mask)),
        "s_component_count": len(s_raster.components),
        "h_component_count": len(h_raster.components),
    }
