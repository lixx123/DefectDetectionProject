"""Small independent fake outputs exercise orchestration and adverse QA paths."""
from pathlib import Path
import csv
import json
import math
import threading

import cv2
import numpy as np
import pytest

from core.detector import Detector
from core.adapters.reference_engine_adapter import RawProfile
from core.adapters.qa_mapper import classify_failure
from core.runtime.resources import write_json, sha256
from core.errors import InputValidationError, InspectionCancelled
from domain import InspectionResult, FinalValidationError
from domain.configuration import InspectionConfig
from domain.enums import PipelineMode, FallbackReason, ExecutionStatus, QAStatus, SeverityGrade


def table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def png(path, array):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cv2.imencode(".png", array)[1].tobytes())


def fixture_output(path):
    path.mkdir()
    mask = np.ones((2, 2), np.uint8)
    folder = path / "EXACT_FINAL_BINARY_MASKS"
    folder.mkdir()
    np.savez_compressed(folder / "F1_FINAL_0001.npz", mask=mask,
        global_RAW_bbox_xyxy_exclusive=np.array([2, 3, 4, 5]), source_uids=np.array(["H:F1:C1"]))
    table(path / "FINAL_DEFECTS_AND_MEASUREMENTS.csv", [{"final_ID": "F1_FINAL_0001",
        "final_area_detector_px2": 4, "max_Feret_detector_px": math.sqrt(2),
        "bbox_xyxy_exclusive": "[2,3,4,5]", "grade": "SMALL", "human_confirmed_darkspot": "False",
        "source_uids": "H:F1:C1", "decision_reason": "FIXTURE_EVIDENCE"}])
    table(path / "ALL_SOURCE_DISPOSITIONS.csv", [{"candidate_source_uid": "H:F1:C1", "stage": "H",
        "source_area_px2": 4, "source_bbox_x0": 2, "source_bbox_y0": 3,
        "source_bbox_x1_exclusive": 4, "source_bbox_y1_exclusive": 5,
        "final_ID": "F1_FINAL_0001", "original_source_preserved": "True", "decision_reason": "FIXTURE_EVIDENCE"}])
    binary = np.zeros((12, 12), np.uint8)
    binary[3:5, 2:4] = 255
    png(path / "01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png", binary)
    png(path / "00_FINAL_DEFECTS_ONLY_fullframe_1to4.png", binary)
    png(path / "band_id_fullres.png", np.ones((12, 12), np.uint8))
    png(path / "region_type_fullres.png", np.full((12, 12), 2, np.uint8))
    write_json(path / "band_geometry.json", {"bands": [{"band_id": 1, "validation_flags": []}]})
    write_json(path / "detection_plan.json", {"tiles": [{"tile_id": "T1"}], "full_tiles": 1,
        "skipped_tiles": 0, "legal_source_pixels": 144, "fallback_reasons": []})
    write_json(path / "bridge_qa.json", {"context_rectangles_checked": 1, "sentinel_status": "PASS"})
    write_json(path / "acceptance.json", {"objects": 1, "area": 4, "source_count": 1,
        "actual_fresh_J4_tiles": 1, "RAW_unchanged": True})
    write_json(path / "upstream_J4/fresh/run_status.json", {"stage": "J4_COMPLETE", "completed_tiles": 1})
    write_json(path / "upstream_J5/fresh/summary.json", {"stage": "J5_COMPLETE", "source_area_unchanged": True,
        "source_J4_tiles": 1, "scheduled_detection_region_completed": True})
    return path


class FakeAdapter:
    def __init__(self, root, failures=None):
        self.reference_root = root
        self.outputs = {m: fixture_output(root / ("fixture_" + m.value)) for m in (PipelineMode.ROI_BH, PipelineMode.FULL, PipelineMode.ROI_J4)}
        self.failures, self.calls = failures or {}, []

    def profile(self):
        return RawProfile(12, 12, 12, "big")

    def source_manifest(self):
        return "fixture-source-only-not-a-real-engine", []

    def run(self, image_path, mode, run_dir, logger):
        self.calls.append(mode)
        output = self.outputs[mode]
        reason = self.failures.get(mode)
        if reason == FallbackReason.BAND_GEOMETRY_INVALID:
            plan_path = output / "detection_plan.json"
            plan = json.loads(plan_path.read_text())
            plan["fallback_reasons"] = ["UNTRUSTED_EDGE_FIT"]
            plan_path.write_text(json.dumps(plan), encoding="utf8")
        return output, ({"reason": reason.value, "stage": "FIXTURE_FAILURE", "error": "injected test failure"} if reason else None)


@pytest.fixture
def raw(tmp_path):
    path = tmp_path / "26 (1).raw"
    path.write_bytes(np.arange(144, dtype=">u2").tobytes())
    return path


def detector(tmp_path, failures=None):
    adapter = FakeAdapter(tmp_path, failures)
    return Detector(output_root=tmp_path / "runtime", engine_adapter=adapter), adapter


def test_detector_returns_real_model_and_maps_measurements(tmp_path, raw):
    d, adapter = detector(tmp_path)
    result = d.inspect(raw, InspectionConfig())
    assert isinstance(result, InspectionResult)
    result.validate_final()
    assert adapter.calls == [PipelineMode.ROI_BH]
    assert result.input_info.sha256 == sha256(raw)
    assert result.input_info.width_px == 12 and result.input_info.effective_bits == 12
    assert result.algorithm_info.algorithm_version and result.algorithm_info.config_hash
    assert result.roi_info.band_count == 1 and result.roi_info.band_list[0].mean_gray_dn is not None
    assert result.statistics.total_defects == 1 and result.statistics.total_defect_area_px == 4
    defect = result.defects[0]
    assert defect.geometry.area_px == 4 and defect.geometry.length_px == pytest.approx(math.sqrt(2))
    assert defect.geometry.area_um2 == pytest.approx(4 * result.calibration_info.spatial_scale_um_per_px ** 2)
    assert defect.geometry.length_method == "MAX_FERET_PIXEL_CENTERS"
    assert defect.geometry.area_method == "COUNT_FINAL_MASK_PIXELS_NOT_DISPLAY_BOX"
    assert defect.classification.severity_grade == SeverityGrade.UNKNOWN
    assert result.audit_log.source_candidate_count == 1 and result.audit_log.lineage_complete
    assert result.audit_log.candidates[0].final_defect_id == defect.identity.defect_id
    assert result.quality_control.status == QAStatus.PASS
    assert {c.name for c in result.execution_info.qa_checks} >= {"sentinel", "J4_completed", "J5_completed", "source_lineage"}
    path = d.last_run_dir / "result.json"
    result.save_json(path)
    assert InspectionResult.load_json(path) == result
    assert not Path(defect.geometry.mask_reference.path).is_absolute()
    assert "C:\\" not in result.to_json() and "D:\\" not in result.to_json()


@pytest.mark.parametrize("reason", list(FallbackReason))
def test_auto_rejected_roi_goes_directly_to_full(tmp_path, raw, reason):
    d, adapter = detector(tmp_path, {PipelineMode.ROI_BH: reason})
    result = d.inspect(raw, InspectionConfig())
    assert adapter.calls == [PipelineMode.ROI_BH, PipelineMode.FULL]
    assert result.execution_info.final_mode == PipelineMode.FULL
    assert result.execution_info.fallback_reason == reason
    assert result.execution_info.fallback_used
    assert PipelineMode.ROI_J4 not in adapter.calls
    result.validate_final()


def test_full_failure_returns_draft_not_empty_approved_inspection(tmp_path, raw):
    failures = {PipelineMode.ROI_BH: FallbackReason.SENTINEL_CONSUMED,
                PipelineMode.FULL: FallbackReason.J4_EXECUTION_FAILED}
    d, adapter = detector(tmp_path, failures)
    result = d.inspect(raw, InspectionConfig())
    assert result.execution_info.status == ExecutionStatus.FAILED
    assert result.execution_info.final_mode is None and result.quality_control.status == QAStatus.FAIL
    with pytest.raises(FinalValidationError):
        result.validate_final()


@pytest.mark.parametrize("message,expected", [
    ("Uncomputed BlackHat sentinel consumed by J4", FallbackReason.SENTINEL_CONSUMED),
    ("BAND_LOCATOR_FAILED", FallbackReason.BAND_LOCATOR_FAILED),
    ("UNTRUSTED_EDGE_GEOMETRY", FallbackReason.BAND_GEOMETRY_INVALID),
    ("ROI_PLAN failed", FallbackReason.ROI_PLAN_FAILED),
    ("halo context incomplete", FallbackReason.ROI_CONTEXT_INCOMPLETE),
    ("J4 run_tile failure", FallbackReason.J4_EXECUTION_FAILED),
    ("J5 global_merge failure", FallbackReason.J5_EXECUTION_FAILED),
    ("reverse lineage missing", FallbackReason.SOURCE_LINEAGE_INVALID),
    ("final mask QA failed", FallbackReason.QA_FAILED),
    ("unexpected arbitrary failure", FallbackReason.UNKNOWN_EXCEPTION),
])
def test_failure_classification_uses_stage_evidence(message, expected):
    assert classify_failure(message) == expected


@pytest.mark.parametrize("mode", [PipelineMode.FULL, PipelineMode.ROI_BH, PipelineMode.ROI_J4])
def test_explicit_debug_mode_never_auto_falls_back(tmp_path, raw, mode):
    d, adapter = detector(tmp_path)
    result = d.inspect(raw, InspectionConfig(pipeline_mode=mode, advanced_debug=True))
    assert adapter.calls == [mode]
    assert result.execution_info.final_mode == mode and not result.execution_info.fallback_used


def test_reverse_lineage_missing_rejects_mapping_and_auto_full(tmp_path, raw):
    d, adapter = detector(tmp_path)
    table(adapter.outputs[PipelineMode.ROI_BH] / "ALL_SOURCE_DISPOSITIONS.csv", [
        {"candidate_source_uid": "UNRELATED", "stage": "H", "final_ID": ""}])
    result = d.inspect(raw, InspectionConfig())
    assert result.execution_info.fallback_reason == FallbackReason.SOURCE_LINEAGE_INVALID
    assert result.execution_info.final_mode == PipelineMode.FULL


@pytest.mark.parametrize("file,field,bad", [("acceptance.json", "objects", 999), ("acceptance.json", "area", 999)])
def test_summary_mismatch_is_not_silently_accepted(tmp_path, raw, file, field, bad):
    d, adapter = detector(tmp_path)
    for output in adapter.outputs.values():
        data = json.loads((output / file).read_text())
        data[field] = bad
        (output / file).write_text(json.dumps(data))
    result = d.inspect(raw, InspectionConfig())
    assert result.execution_info.status == ExecutionStatus.FAILED
    assert result.quality_control.status == QAStatus.FAIL


def test_bad_raw_input_fails_before_engine(tmp_path, raw):
    d, adapter = detector(tmp_path)
    raw.write_bytes(b"bad")
    with pytest.raises(InputValidationError):
        d.inspect(raw, InspectionConfig())
    assert adapter.calls == []


def test_raw_effective_bit_depth_is_checked(tmp_path, raw):
    d, adapter = detector(tmp_path)
    raw.write_bytes(np.full((12, 12), 65535, dtype=">u2").tobytes())
    with pytest.raises(InputValidationError):
        d.inspect(raw, InspectionConfig())
    assert adapter.calls == []


def test_config_scale_is_used_without_modifying_pixel_results(tmp_path, raw):
    d, adapter = detector(tmp_path)
    config = InspectionConfig()
    config.calibration = config.calibration.with_user_scale(5)
    result = d.inspect(raw, config)
    config.calibration.spatial_scale_um_per_px = 10
    assert result.calibration_info.spatial_scale_um_per_px == 5
    assert result.defects[0].geometry.area_px == 4
    assert result.defects[0].geometry.area_um2 == 100


def test_missing_final_mask_is_not_an_approved_empty_result(tmp_path, raw):
    d, adapter = detector(tmp_path)
    for output in adapter.outputs.values():
        (output / "01_FINAL_EXACT_FULLRES_BINARY_DEFECT_MASK.png").unlink()
    result = d.inspect(raw, InspectionConfig())
    assert result.quality_control.status == QAStatus.FAIL


def test_each_inspection_has_its_own_run_directory(tmp_path, raw):
    d, adapter = detector(tmp_path)
    first = d.inspect(raw, InspectionConfig())
    directory = d.last_run_dir
    second = d.inspect(raw, InspectionConfig())
    assert d.last_run_dir != directory and first.result_id != second.result_id
    assert directory.is_dir() and (directory / "logs/inspection.log").is_file()


def test_raw_recovery_history_is_linked_to_final_defect(tmp_path, raw):
    d, adapter = detector(tmp_path)
    table(adapter.outputs[PipelineMode.ROI_BH] / "RAW_recovery_gate_audit.csv", [
        {"source_uids": "H:F1:C1", "accepted": "True", "reason": "RAW_EVIDENCE"}])
    result = d.inspect(raw, InspectionConfig())
    assert result.audit_log.events[0]["candidate_ids"] == ["H:F1:C1"]
    assert result.defects[0].detection.merge_history[0]["accepted"] is True


def test_final_membership_mismatch_is_source_lineage_failure(tmp_path, raw):
    d, adapter = detector(tmp_path)
    table(adapter.outputs[PipelineMode.ROI_BH] / "final_group_membership.csv", [
        {"source_uid": "H:F1:C1", "final_ID": "MISSING"}])
    result = d.inspect(raw, InspectionConfig())
    assert result.execution_info.fallback_reason == FallbackReason.SOURCE_LINEAGE_INVALID


def test_cancellation_propagates_and_never_triggers_full(tmp_path, raw, monkeypatch):
    d, adapter = detector(tmp_path)
    def cancelled(*args, **kwargs):
        adapter.calls.append(PipelineMode.ROI_BH)
        raise InspectionCancelled("cancelled for unit test")
    monkeypatch.setattr(adapter, "run", cancelled)
    with pytest.raises(InspectionCancelled):
        d.inspect(raw, InspectionConfig())
    assert adapter.calls == [PipelineMode.ROI_BH]
    assert (d.last_run_dir / "cancelled.json").is_file()
