from pathlib import Path
from domain import QACheck
from domain.enums import QAStatus, FallbackReason, GeometryStatus
from core.runtime.resources import load_json


def classify_failure(message, *, stage=""):
    text = (message + " " + stage).lower()
    for words, reason in (
        (("sentinel", "uncomputed blackhat"), FallbackReason.SENTINEL_CONSUMED),
        (("locator_exception", "band_locator_failed", "no transmission bands"), FallbackReason.BAND_LOCATOR_FAILED),
        (("geometry", "untrusted_edge", "overlapping_bands", "work_area_abnormal", "untrusted_work", "untrusted_band", "malformed"), FallbackReason.BAND_GEOMETRY_INVALID),
        (("context", "halo", "coverage"), FallbackReason.ROI_CONTEXT_INCOMPLETE),
        (("roi_plan", "empty_roi", "build_plan"), FallbackReason.ROI_PLAN_FAILED),
        (("lineage", "membership", "source uid", "source_uid", "reverse", "source_count", "source_dispositions"), FallbackReason.SOURCE_LINEAGE_INVALID),
        (("j5", "global_merge"), FallbackReason.J5_EXECUTION_FAILED),
        (("j4", "run_tile", "tile_status"), FallbackReason.J4_EXECUTION_FAILED),
        (("qa", "mask", "measurement", "feret", "statistics", "summary", "final"), FallbackReason.QA_FAILED),
    ):
        if any(word in text for word in words):
            return reason
    return FallbackReason.UNKNOWN_EXCEPTION


def check(name, passed, message="", *, stage="ENGINE", mandatory=True):
    return QACheck(name=name, status=QAStatus.PASS if passed else QAStatus.FAIL,
                   stage=stage, message=message, mandatory=mandatory)


def execution_checks(engine_dir, input_checks, *, legacy=False):
    engine_dir = Path(engine_dir)
    if legacy:
        qa_file = engine_dir / "INDEPENDENT_QA" / "acceptance.json"
        if not qa_file.is_file():
            qa_file = engine_dir.parent / "INDEPENDENT_QA" / "acceptance.json"
        state = load_json(qa_file) if qa_file.is_file() else {}
        passed = state.get("status") == "PASS"
        return [*input_checks, check("legacy_frozen_pixel_QA", passed,
                    "Historical artifact validation; not a fresh RAW execution", stage="LEGACY_REPLAY")]
    bridge = load_json(engine_dir / "bridge_qa.json")
    acceptance = load_json(engine_dir / "acceptance.json")
    j4 = load_json(engine_dir / "upstream_J4/fresh/run_status.json")
    j5 = load_json(engine_dir / "upstream_J5/fresh/summary.json")
    plan = load_json(engine_dir / "detection_plan.json")
    planned = len(plan["tiles"])
    return [*input_checks,
        check("Band_locator", bool(load_json(engine_dir / "band_geometry.json").get("bands")), stage="K8A"),
        check("Band_geometry", not plan["fallback_reasons"], stage="K8A"),
        check("ROI_plan", planned + plan["skipped_tiles"] == plan["full_tiles"], stage="ROI_PLAN"),
        check("ROI_context", bridge.get("context_rectangles_checked") == planned, stage="ROI_CONTEXT"),
        check("sentinel", bridge.get("sentinel_status") == "PASS", stage="SENTINEL"),
        check("J4_completed", j4.get("stage") == "J4_COMPLETE" and j4["completed_tiles"] == planned
              == acceptance["actual_fresh_J4_tiles"], stage="J4"),
        check("J5_completed", j5.get("stage") == "J5_COMPLETE" and j5.get("source_area_unchanged") is True
              and j5.get("source_J4_tiles") == planned
              and (j5.get("scheduled_detection_region_completed") is True or j5.get("full_image_completed") is True), stage="J5"),
        check("RAW_unchanged", acceptance.get("RAW_unchanged") is True, stage="INPUT")]


def geometry_plan(engine_dir):
    from domain import DetectionPlanInfo
    path = Path(engine_dir) / "detection_plan.json"
    if not path.is_file():
        return DetectionPlanInfo()
    plan = load_json(path)
    reason = " ".join(plan.get("fallback_reasons", []))
    valid = not plan.get("fallback_reasons")
    return DetectionPlanInfo(roi_geometry_status=GeometryStatus.VALID if valid else GeometryStatus.INVALID,
        band_geometry_status=GeometryStatus.VALID if valid else GeometryStatus.INVALID,
        planned_tiles=len(plan["tiles"]), full_tiles=plan["full_tiles"], skipped_tiles=plan["skipped_tiles"],
        legal_source_pixels=plan["legal_source_pixels"])
