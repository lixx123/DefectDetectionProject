"""Measured mask/CSV -> Defect, retaining Feret and foreground-count semantics."""
import json
import math
import re
from pathlib import Path
import cv2
import numpy as np
from domain import Defect, DefectIdentity, DefectGeometry, ReviewInfo
from domain.common import BoundingBox, Point
from domain.defect import DetectionInfo, Classification, DefectLocation
from domain.enums import SizeGrade, ReviewStatus
from core.errors import MappingError, ResultQCError
from .tabular import first, sources, truth


def feret(mask):
    y, x = np.nonzero(mask)
    if len(x) == 0:
        raise ResultQCError("empty final defect mask")
    hull = cv2.convexHull(np.column_stack((x, y)).astype(np.float32)).reshape(-1, 2).astype(float)
    best = 0.0
    for start in range(0, len(hull), 128):
        delta = hull[start:start + 128, None, :] - hull[None, :, :]
        best = max(best, float(np.square(delta).sum(axis=2).max()))
    return max(1.0, math.sqrt(best))


def map_defects(rows, engine_dir, resources, calibration, shape, algorithm_version):
    defects, ownership = [], {}
    full_mask = np.zeros(shape, np.uint8)
    for row in rows:
        defect_id = row.get("final_ID", "")
        if not defect_id or any(d.identity.defect_id == defect_id for d in defects):
            raise ResultQCError("missing/duplicate final Defect ID")
        # Prefer this run's NPZ; historical CSV absolute paths are never trusted as references.
        mask_path = Path(engine_dir) / "EXACT_FINAL_BINARY_MASKS" / (defect_id + ".npz")
        with np.load(mask_path, allow_pickle=False) as data:
            mask = data["mask"] > 0
            bbox = tuple(int(v) for v in data["global_RAW_bbox_xyxy_exclusive"])
            npz_sources = set(map(str, data["source_uids"])) if "source_uids" in data else None
        declared = tuple(json.loads(row["bbox_xyxy_exclusive"]))
        x0, y0, x1, y1 = bbox
        if bbox != declared or not (0 <= x0 < x1 <= shape[1] and 0 <= y0 < y1 <= shape[0]):
            raise ResultQCError("final bbox differs from NPZ or exceeds image")
        if mask.shape != (y1 - y0, x1 - x0):
            raise ResultQCError("final mask shape differs from bbox")
        area, length = int(mask.sum()), float(row["max_Feret_detector_px"])
        if area != int(row["final_area_detector_px2"]) or abs(feret(mask) - length) > 0.000051:
            raise ResultQCError("mask foreground/Feret differs from final table")
        source_ids = sources(first(row, "source_uids", "J5_B_or_K8E_sources"))
        if not source_ids or (npz_sources is not None and source_ids != npz_sources):
            raise MappingError("final Defect has no sources or CSV/NPZ source mismatch")
        for uid in source_ids:
            if uid in ownership:
                raise MappingError("one candidate source belongs to multiple final defects")
            ownership[uid] = defect_id
        crop = full_mask[y0:y1, x0:x1]
        if np.any(crop[mask]):
            raise ResultQCError("final masks overlap; area must not be double-counted")
        crop[mask] = 255
        center = Point((x0 + x1) / 2, (y0 + y1) / 2)
        band = first(row, "band_id")
        if not band:
            found = {int(m.group(1)) for s in source_ids if (m := re.search(r":B(\d+):", s))}
            band = str(next(iter(found))) if len(found) == 1 else None
        band = str(int(float(band))) if band and float(band) > 0 else None
        geometry = DefectGeometry(bbox=BoundingBox(*bbox), center=center, area_px=area,
            length_px=length, mask_reference=resources.reference(mask_path, group="masks"),
            area_method="COUNT_FINAL_MASK_PIXELS_NOT_DISPLAY_BOX",
            length_method="MAX_FERET_PIXEL_CENTERS").with_calibration(calibration)
        approved = truth(row.get("human_confirmed_darkspot"))
        defects.append(Defect(identity=DefectIdentity(defect_id=defect_id), geometry=geometry,
            classification=Classification(size_grade=SizeGrade(row["grade"]),
                classification_method="REFERENCE_ENGINE_GEOMETRIC_SIZE_GRADE"),
            location=DefectLocation(image_x=center.x, image_y=center.y, band_id=band,
                roi_id="WORK" if band else None, extensions={"position_method": "FINAL_BBOX_CENTER_NOT_CENTROID"}),
            detection=DetectionInfo(candidate_ids=sorted(source_ids),
                source_channels=sorted({s.split(":", 1)[0] for s in source_ids}),
                detection_stage="REFERENCE_FINAL_SELECTION", algorithm_version=algorithm_version),
            review=ReviewInfo(algorithm_decision="AUTO_SELECTED",
                review_status=ReviewStatus.CONFIRMED if approved else ReviewStatus.UNREVIEWED,
                reviewer_decision="CONFIRMED" if approved else None,
                comment="原算法按RAW内容绑定的历史人工批准" if approved else None),
            extensions={"reference_decision_reason": first(row, "decision_reason", "acceptance_reason"),
                        "human_confirmed_darkspot": approved}))
    return defects, ownership, full_mask
