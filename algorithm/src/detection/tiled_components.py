"""Scalable connected components for Case03-B.

The implementation labels each tile independently and joins provisional labels
through the already-written top/left tile boundaries.  The label raster is a
disk-backed int32 memmap, so the full-resolution response and masks are not
duplicated by a full-resolution in-memory label image.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
from scipy import ndimage


@dataclass
class ComponentExtraction:
    """Result of a tiled component extraction."""

    final_mask: np.ndarray
    low_only_mask: np.ndarray
    components: list[dict]
    support_component_count: int
    active_component_count: int
    support_pixel_count: int
    seed_pixel_count: int
    provisional_label_count: int
    tile_count: int


class _UnionFind:
    """Sparse union-find; only labels touching a tile boundary need a parent."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, value: int) -> int:
        parent = self.parent.get(value)
        if parent is None:
            return value
        root = value
        while True:
            next_value = self.parent.get(root)
            if next_value is None or next_value == root:
                break
            root = next_value
        while value != root:
            next_value = self.parent.get(value)
            self.parent[value] = root
            if next_value is None:
                break
            value = next_value
        return root

    def union(self, first: int, second: int) -> None:
        left = self.find(first)
        right = self.find(second)
        if left == right:
            return
        if left < right:
            self.parent[right] = left
        else:
            self.parent[left] = right


def _structure(connectivity: int) -> np.ndarray:
    if connectivity == 8:
        return np.ones((3, 3), dtype=np.uint8)
    if connectivity == 4:
        return np.asarray([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
    raise ValueError("connectivity must be 4 or 8")


def _tile_ranges(length: int, tile_length: int) -> list[tuple[int, int]]:
    if tile_length <= 0:
        raise ValueError("tile dimensions must be positive")
    return [(start, min(length, start + tile_length)) for start in range(0, length, tile_length)]


def _join_prior_neighbors(
    provisional: np.ndarray,
    labels: np.memmap,
    y0: int,
    x0: int,
    union_find: _UnionFind,
    connectivity: int,
) -> None:
    """Join current top/left boundary pixels to previously written neighbors.

    Looking at all eight neighbors is intentional: it handles diagonal links
    through a tile corner, not just straight horizontal/vertical seams.
    """

    height, width = provisional.shape
    boundary = np.argwhere((np.indices((height, width))[0] == 0) | (np.indices((height, width))[1] == 0))
    max_y, max_x = labels.shape
    for local_y, local_x in boundary:
        current = int(provisional[local_y, local_x])
        if current <= 0:
            continue
        global_y = y0 + int(local_y)
        global_x = x0 + int(local_x)
        if connectivity == 4:
            offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
        else:
            offsets = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))
        for dy, dx in offsets:
            neighbor_y = global_y + dy
            neighbor_x = global_x + dx
            if not (0 <= neighbor_y < max_y and 0 <= neighbor_x < max_x):
                continue
            previous = int(labels[neighbor_y, neighbor_x])
            if previous > 0:
                union_find.union(current, previous)


def _aggregate_tile(
    tile_labels: np.ndarray,
    response_tile: np.ndarray,
    seed_tile: np.ndarray,
    y0: int,
    x0: int,
    features: dict[int, dict],
    union_find: _UnionFind,
) -> None:
    positive = tile_labels > 0
    if not np.any(positive):
        return
    positive_labels = tile_labels[positive].astype(np.int64, copy=False)
    response_values = response_tile[positive].astype(np.int64, copy=False)
    seed_values = seed_tile[positive].astype(np.int64, copy=False)
    unique, inverse, counts = np.unique(positive_labels, return_inverse=True, return_counts=True)
    local_height, local_width = tile_labels.shape
    flat_positions = np.flatnonzero(positive)
    local_y = flat_positions // local_width
    local_x = flat_positions % local_width
    min_y = np.full(unique.size, local_height, dtype=np.int64)
    min_x = np.full(unique.size, local_width, dtype=np.int64)
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
    np.maximum.at(peak, inverse, response_values)
    seed_counts = np.bincount(inverse, weights=seed_values, minlength=unique.size).astype(np.int64)

    for index, provisional in enumerate(unique.tolist()):
        root = union_find.find(int(provisional))
        area = int(counts[index])
        record = features.setdefault(
            root,
            {
                "area_px": 0,
                "min_x": local_width + x0,
                "min_y": local_height + y0,
                "max_x": -1,
                "max_y": -1,
                "sum_x": 0,
                "sum_y": 0,
                "peak_response": -1,
                "seed_pixel_count": 0,
            },
        )
        record["area_px"] += area
        record["min_x"] = min(record["min_x"], int(min_x[index]) + x0)
        record["min_y"] = min(record["min_y"], int(min_y[index]) + y0)
        record["max_x"] = max(record["max_x"], int(max_x[index]) + x0)
        record["max_y"] = max(record["max_y"], int(max_y[index]) + y0)
        record["sum_x"] += int(sum_x[index]) + area * x0
        record["sum_y"] += int(sum_y[index]) + area * y0
        record["peak_response"] = max(record["peak_response"], int(peak[index]))
        record["seed_pixel_count"] += int(seed_counts[index])


def extract_tiled_components(
    support_mask: np.ndarray,
    response_dn: np.ndarray,
    seed_mask: np.ndarray | None = None,
    *,
    connectivity: int = 8,
    tile_shape: tuple[int, int] = (512, 1024),
    temp_dir: Path | None = None,
) -> ComponentExtraction:
    """Extract all components from a full-resolution support mask.

    ``seed_mask`` controls the final hysteresis selection.  If omitted, every
    support component is active, which is the single-threshold operation.
    No area, morphology, or Top-N filtering is performed.
    """

    if support_mask.dtype != np.bool_ or support_mask.ndim != 2:
        raise TypeError("support_mask must be a 2-D bool array")
    if response_dn.ndim != 2 or response_dn.shape != support_mask.shape:
        raise ValueError("response_dn and support_mask shapes must match")
    if seed_mask is None:
        seed_mask = support_mask
    if seed_mask.dtype != np.bool_ or seed_mask.shape != support_mask.shape:
        raise TypeError("seed_mask must be a same-shape 2-D bool array")
    if np.any(seed_mask & ~support_mask):
        raise ValueError("seed_mask must be a subset of support_mask")

    height, width = support_mask.shape
    tile_h, tile_w = int(tile_shape[0]), int(tile_shape[1])
    y_ranges = _tile_ranges(height, tile_h)
    x_ranges = _tile_ranges(width, tile_w)
    temp_root = Path(temp_dir or Path.cwd() / ".case03b_tmp")
    temp_root.mkdir(parents=True, exist_ok=True)
    label_path = temp_root / f"labels_{uuid4().hex}.dat"
    labels = np.memmap(label_path, dtype=np.int32, mode="w+", shape=(height, width))
    labels[:] = 0
    union_find = _UnionFind()
    next_label = 1
    structure = _structure(connectivity)
    tile_count = 0

    try:
        for y0, y1 in y_ranges:
            for x0, x1 in x_ranges:
                tile_count += 1
                local_support = support_mask[y0:y1, x0:x1]
                local_labels, local_count = ndimage.label(local_support, structure=structure)
                if local_count:
                    local_labels = local_labels.astype(np.int32, copy=False)
                    local_labels[local_labels > 0] += next_label - 1
                    _join_prior_neighbors(local_labels, labels, y0, x0, union_find, connectivity)
                    labels[y0:y1, x0:x1] = local_labels
                    next_label += int(local_count)
        labels.flush()

        features: dict[int, dict] = {}
        for y0, y1 in y_ranges:
            for x0, x1 in x_ranges:
                _aggregate_tile(
                    np.array(labels[y0:y1, x0:x1], copy=True),
                    response_dn[y0:y1, x0:x1],
                    seed_mask[y0:y1, x0:x1],
                    y0,
                    x0,
                    features,
                    union_find,
                )

        active_roots = {root for root, record in features.items() if int(record["seed_pixel_count"]) > 0}
        final_mask = np.zeros((height, width), dtype=np.bool_)
        for y0, y1 in y_ranges:
            for x0, x1 in x_ranges:
                tile_labels = np.array(labels[y0:y1, x0:x1], copy=True)
                positive = tile_labels > 0
                if not np.any(positive):
                    continue
                positive_labels = tile_labels[positive].astype(np.int64, copy=False)
                unique, inverse = np.unique(positive_labels, return_inverse=True)
                if seed_mask is support_mask:
                    active = np.ones(unique.size, dtype=np.bool_)
                else:
                    active = np.asarray([union_find.find(int(value)) in active_roots for value in unique], dtype=np.bool_)
                tile_output = final_mask[y0:y1, x0:x1]
                tile_output[positive] = active[inverse]

        low_only_mask = support_mask & ~final_mask
        components: list[dict] = []
        for root, record in features.items():
            if root not in active_roots and seed_mask is not support_mask:
                continue
            area = int(record["area_px"])
            min_x, max_x = int(record["min_x"]), int(record["max_x"])
            min_y, max_y = int(record["min_y"]), int(record["max_y"])
            components.append(
                {
                    "area_px": area,
                    "min_x": min_x,
                    "min_y": min_y,
                    "max_x": max_x,
                    "max_y": max_y,
                    "bbox_x": min_x,
                    "bbox_y": min_y,
                    "bbox_w": max_x - min_x + 1,
                    "bbox_h": max_y - min_y + 1,
                    "centroid_x": float(record["sum_x"] / area),
                    "centroid_y": float(record["sum_y"] / area),
                    "peak_response": int(record["peak_response"]),
                    "seed_pixel_count": int(record["seed_pixel_count"]),
                    "touches_border": bool(min_x == 0 or min_y == 0 or max_x == width - 1 or max_y == height - 1),
                }
            )
        components.sort(key=lambda item: (int(item["min_y"]), int(item["min_x"]), -int(item["area_px"])))
        return ComponentExtraction(
            final_mask=final_mask,
            low_only_mask=low_only_mask,
            components=components,
            support_component_count=len(features),
            active_component_count=len(components),
            support_pixel_count=int(np.count_nonzero(support_mask)),
            seed_pixel_count=int(np.count_nonzero(seed_mask)),
            provisional_label_count=next_label - 1,
            tile_count=tile_count,
        )
    finally:
        labels.flush()
        mmap_handle = getattr(labels, "_mmap", None)
        del labels
        if mmap_handle is not None:
            mmap_handle.close()
        try:
            label_path.unlink()
        except FileNotFoundError:
            pass
