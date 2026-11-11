from pathlib import Path
import cv2
import numpy as np
from domain import ROIInfo, BandInfo, RegionInfo
from domain.common import BoundingBox
from domain.enums import GeometryStatus
from core.errors import EngineOutputError
from core.runtime.resources import load_json


def read_png(path):
    array = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
    if array is None:
        raise EngineOutputError(f"unreadable image: {Path(path).name}")
    return array


def write_png(path, array):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", array)
    if not ok:
        raise EngineOutputError("PNG encoding failed")
    path.write_bytes(encoded.tobytes())


def bbox_of(mask):
    ys = np.flatnonzero(mask.any(axis=1))
    xs = np.flatnonzero(mask.any(axis=0))
    return None if not len(xs) else BoundingBox(int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1)


def map_roi(engine_dir, resources, *, raw_path=None, shape=None, trusted=True):
    engine_dir = Path(engine_dir)
    geometry_path = engine_dir / "band_geometry.json"
    if not geometry_path.is_file():
        return ROIInfo(geometry_source="NOT_PRESENT_IN_LEGACY_EXPORT"), None
    geometry = load_json(geometry_path)
    geometry_ref = resources.reference(geometry_path)
    types_path, ids_path = engine_dir / "region_type_fullres.png", engine_dir / "band_id_fullres.png"
    types = read_png(types_path) if types_path.is_file() else None
    ids = read_png(ids_path) if ids_path.is_file() else None
    if types is not None and (types.shape != shape or ids is None or ids.shape != shape):
        raise EngineOutputError("ROI raster dimensions differ from RAW")
    bands, regions = [], {}
    raw = np.memmap(raw_path, mode="r", dtype=">u2", shape=shape) if raw_path and shape else None
    if types is not None:
        if trusted and not np.array_equal(ids > 0, types == 2):
            raise EngineOutputError("WORK and Band-ID masks disagree")
        for name, codes in (("work", [2]), ("nonwork", [0, 1]), ("review", [3])):
            mask = np.isin(types, codes)
            destination = resources.run_dir / "artifacts" / "roi" / (engine_dir.name + "_" + name + ".png")
            write_png(destination, np.uint8(mask) * 255)
            regions[name] = RegionInfo(region_id=name.upper(), bbox=bbox_of(mask),
                pixel_count=int(mask.sum()), mask_reference=resources.reference(destination),
                extensions={"reference_region_codes": codes})
    for band in geometry.get("bands", []):
        bid = int(band["band_id"])
        mask = ids == bid if ids is not None else None
        count = int(mask.sum()) if mask is not None else None
        bounds = bbox_of(mask) if mask is not None else None
        stats = (None, None, None)
        if count and raw is not None:
            values = np.asarray(raw)[mask]
            stats = (float(values.mean()), float(values.min()), float(values.max()))
        reference = None
        if mask is not None:
            destination = resources.run_dir / "artifacts" / "roi" / f"{engine_dir.name}_band_{bid}.png"
            write_png(destination, np.uint8(mask) * 255)
            reference = resources.reference(destination)
        bands.append(BandInfo(band_id=str(bid), name=f"Band {bid}", bbox=bounds,
            pixel_count=count, mean_gray_dn=stats[0], min_gray_dn=stats[1], max_gray_dn=stats[2],
            valid=trusted and not band.get("validation_flags"), mask_reference=reference,
            extensions={"reference_geometry": band, "geometry_reference": {
                "path": geometry_ref.path, "sha256": geometry_ref.sha256}}))
    mask_refs = {"geometry": geometry_ref}
    if types_path.is_file():
        mask_refs["region_type_fullres"] = resources.reference(types_path)
        mask_refs["band_id_fullres"] = resources.reference(ids_path)
    return ROIInfo(status=GeometryStatus.VALID if trusted else GeometryStatus.INVALID,
        work_region=regions.get("work"), nonwork_region=regions.get("nonwork"), review_region=regions.get("review"),
        band_count=len(bands), band_list=bands, mask_references=mask_refs,
        geometry_source="REFERENCE_K8A_OUTPUT_NOT_GUI_RECOMPUTATION"), ids
