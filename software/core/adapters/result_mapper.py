"""A common result mapper for real fresh outputs and explicit legacy replay."""
from pathlib import Path
import numpy as np
from domain import (InspectionResult, AlgorithmInfo, QualityControl, IntermediateResults)
from domain.enums import QAStatus, IntermediateLevel, PipelineMode
from core.errors import ResultQCError, MappingError
from core.runtime.resources import ResourceCollector, load_json, portable_reference
from .tabular import read_rows
from .defect_mapper import map_defects
from .audit_mapper import map_audit
from .roi_mapper import map_roi, read_png
from .statistics_mapper import aggregate
from .qa_mapper import check


def map_result(engine_dir, run_dir, config, input_info, algorithm_info, execution,
               *, reference_root=None, raw_path=None):
    engine_dir, run_dir = Path(engine_dir), Path(run_dir)
    resources = ResourceCollector(run_dir)
    table = engine_dir / "FINAL_DEFECTS_AND_MEASUREMENTS.csv"
    rows = read_rows(table)
    shape = (input_info.height_px, input_info.width_px)
    defects, ownership, rebuilt_mask = map_defects(rows, engine_dir, resources,
        config.calibration, shape, algorithm_info.algorithm_version)
    audit = map_audit(engine_dir, ownership, resources, reference_root=reference_root)
    for defect in defects:
        defect.detection.merge_history = [event for event in audit.events
            if defect.identity.defect_id in event.get("final_defect_ids", [])]
    if {v.final_defect_id for v in audit.candidates if v.final_defect_id} != {d.identity.defect_id for d in defects}:
        raise MappingError("Defect -> Candidate reverse lineage incomplete")
    roi, ids = map_roi(engine_dir, resources, raw_path=raw_path, shape=shape)
    if ids is not None:
        for defect in defects:
            x, y = int(defect.location.image_x), int(defect.location.image_y)
            if 0 <= y < shape[0] and 0 <= x < shape[1] and ids[y, x] > 0:
                defect.location.band_id = str(int(ids[y, x]))
                defect.location.roi_id = "WORK"
    statistics = aggregate(defects)
    acceptance_path = engine_dir / "acceptance.json"
    if not acceptance_path.is_file():
        raise ResultQCError("reference acceptance summary missing")
    acceptance = load_json(acceptance_path)
    expected_count = acceptance.get("objects")
    expected_area = acceptance.get("area", acceptance.get("area_px2"))
    if expected_count != len(defects) or expected_area != statistics.total_defect_area_px:
        raise ResultQCError("Defect statistics differ from reference acceptance summary")
    if "source_count" in acceptance and audit.extensions["fresh_source_count"] != acceptance["source_count"]:
        raise MappingError("reference source_count differs from fresh audit ledger")
    masks = sorted(engine_dir.glob("01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK*.png"))
    if len(masks) != 1:
        raise ResultQCError("missing/ambiguous final full-frame mask")
    binary = read_png(masks[0])
    if not np.array_equal(binary, rebuilt_mask):
        raise ResultQCError("full-frame mask differs from union of disjoint final NPZ masks")
    annotated = engine_dir / "00_FINAL_DEFECTS_ONLY_fullframe_1to4.png"
    annotated_array = read_png(annotated)
    if not annotated_array.size:
        raise ResultQCError("annotated image empty")
    intermediates = IntermediateResults(level=config.intermediate_level,
        final_mask=resources.reference(masks[0]), annotated_image=resources.reference(annotated))
    for field, region in (("work_mask", roi.work_region), ("nonwork_mask", roi.nonwork_region),
                          ("review_mask", roi.review_region)):
        if region:
            setattr(intermediates, field, region.mask_reference)
    intermediates.band_masks = {b.band_id: b.mask_reference for b in roi.band_list if b.mask_reference}
    # Keep measurement/audit resources even when optional image retention is NONE.
    checks = [check("FINAL_DEFECTS_readable", True, stage="RESULT_TABLE"),
        check("mask_foreground_area_Feret", True, stage="RESULT_MASK"),
        check("final_mask_disjoint_union", True, stage="RESULT_MASK"),
        check("defect_statistics_vs_summary", True, stage="STATISTICS"),
        check("Defect_ID_unique", True, stage="RESULT_TABLE"),
        check("bidirectional_source_lineage", True, stage="LINEAGE"),
        check("mask_references_exist_and_SHA256", True, stage="RESOURCES"),
        check("annotated_image_readable", True, stage="RESOURCES")]
    execution.qa_checks += [check("source_lineage", True, stage="SOURCE_LINEAGE"),
                            check("final_selection", True, stage="FINAL_SELECTION")]
    execution.attempts[-1].qa_checks += [check("source_lineage", True, stage="SOURCE_LINEAGE"),
                                        check("final_selection", True, stage="FINAL_SELECTION")]
    result = InspectionResult(task_id=run_dir.name, input_info=input_info, algorithm_info=algorithm_info,
        calibration_info=config.calibration, execution_info=execution, roi_info=roi,
        defects=defects, statistics=statistics, audit_log=audit, intermediate_results=intermediates,
        quality_control=QualityControl(status=QAStatus.PASS, checks=checks),
        extensions={"reference_final_table": portable_reference(resources.reference(table)),
                    "reference_acceptance": portable_reference(resources.reference(acceptance_path)),
                    "real_input_run": execution.final_mode != PipelineMode.LEGACY_REPLAY})
    return result
