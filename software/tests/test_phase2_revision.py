"""Finalization boundary tests; data only, never runs the reference detector."""
from copy import deepcopy
from dataclasses import fields
import json

import pytest

from domain import (InspectionResult, FinalValidationError, ExecutionInfo,
                    DetectionPlanInfo, ExecutionAttempt, Defect, DefectIdentity,
                    QACheck, QualityControl)
from domain.enums import PipelineMode, ExecutionStatus, QAStatus, GeometryStatus, FallbackReason
from domain.serialization import from_dict, to_dict
from examples.phase2_roundtrip import example_result


REMOVED_PLAN_FIELDS = {
    "roi_geometry_status", "band_geometry_status", "planned_tiles",
    "full_tiles", "skipped_tiles", "legal_source_pixels",
}


def test_execution_has_no_copied_plan_fields():
    execution = example_result().execution_info
    assert not isinstance(execution, DetectionPlanInfo)
    assert not REMOVED_PLAN_FIELDS.intersection(f.name for f in fields(ExecutionInfo))
    assert not REMOVED_PLAN_FIELDS.intersection(to_dict(execution))
    assert all(not hasattr(execution, name) for name in REMOVED_PLAN_FIELDS)


@pytest.mark.parametrize("fallback", [False, True])
def test_final_plan_is_actual_attempt_plan_not_a_copy(fallback):
    execution = example_result(fallback=fallback).execution_info
    assert execution.final_attempt is execution.attempts[-1]
    assert execution.final_plan is execution.attempts[-1].plan
    execution.final_plan.legal_source_pixels = 123
    assert execution.attempts[-1].plan.legal_source_pixels == 123
    assert "final_plan" not in to_dict(execution)
    assert "final_attempt" not in to_dict(execution)
    with pytest.raises(AttributeError):
        execution.final_plan = DetectionPlanInfo()


def test_without_adopted_mode_final_plan_is_none():
    execution = ExecutionInfo(attempted_mode=PipelineMode.ROI_BH,
        attempts=[ExecutionAttempt(mode=PipelineMode.ROI_BH, status=ExecutionStatus.FAILED)])
    assert execution.final_attempt is None and execution.final_plan is None


def test_final_attempt_does_not_select_earlier_matching_success():
    execution = example_result(fallback=True).execution_info
    execution.attempts[0].status = ExecutionStatus.SUCCEEDED
    execution.attempts[0].qa_status = QAStatus.PASS
    execution.final_mode = PipelineMode.ROI_BH
    # The last successful mode is FULL, so the earlier ROI cannot be adopted.
    assert execution.final_attempt is None and execution.final_plan is None


@pytest.mark.parametrize("fallback", [False, True])
def test_valid_examples_pass_final_gate_and_roundtrip(tmp_path, fallback):
    result = example_result(fallback=fallback)
    before = deepcopy(result)
    assert result.validate_final() is None
    assert result == before
    path = tmp_path / "正式示例.json"
    result.save_json(path)
    loaded = InspectionResult.load_json(path)
    loaded.validate_final()
    assert loaded == result
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert not REMOVED_PLAN_FIELDS.intersection(payload["execution_info"])


def test_fallback_preserves_failed_geometry_for_audit():
    result = example_result(fallback=True)
    first = result.execution_info.attempts[0]
    assert first.plan.roi_geometry_status == GeometryStatus.VALID
    assert first.plan.band_geometry_status == GeometryStatus.INVALID
    assert result.roi_info.status == GeometryStatus.INVALID
    assert result.roi_info.band_count == 1
    assert result.roi_info.band_list and not result.roi_info.band_list[0].valid
    assert first.reason == result.execution_info.fallback_reason
    assert result.execution_info.status == ExecutionStatus.SUCCEEDED
    result.validate_final()


def test_invalid_band_fallback_cannot_claim_all_preserved_bands_are_valid():
    result = example_result(fallback=True)
    result.roi_info.band_list[0].valid = True
    with pytest.raises(FinalValidationError, match="identify invalid Bands"):
        result.validate_final()


def test_band_geometry_reason_cannot_coexist_with_valid_plan():
    result = example_result(fallback=True)
    result.execution_info.attempts[0].plan.band_geometry_status = GeometryStatus.VALID
    with pytest.raises(FinalValidationError, match="Band geometry"):
        result.validate_final()


def test_count_mismatch_is_a_serializable_draft_but_not_final():
    result = example_result()
    result.statistics.total_defects = 2
    assert InspectionResult.from_json(result.to_json()) == result
    with pytest.raises(FinalValidationError, match="total_defects"):
        result.validate_final()


def test_mutated_duplicate_defect_id_rechecked():
    result = example_result()
    result.defects.append(deepcopy(result.defects[0]))
    result.statistics.total_defects = 2
    with pytest.raises(FinalValidationError, match="unique"):
        result.validate_final()


@pytest.mark.parametrize("field", ["roi_geometry_status", "band_geometry_status"])
def test_auto_roi_success_requires_valid_plan_geometry(field):
    result = example_result()
    setattr(result.execution_info.final_plan, field, GeometryStatus.INVALID)
    with pytest.raises(FinalValidationError, match="VALID ROI and Band"):
        result.validate_final()


def test_adopted_roi_requires_valid_roi_info():
    result = example_result()
    result.roi_info.status = GeometryStatus.INVALID
    with pytest.raises(FinalValidationError, match="VALID ROIInfo"):
        result.validate_final()


def test_adopted_roi_cannot_have_invalid_production_band():
    result = example_result()
    result.roi_info.band_list[0].valid = False
    with pytest.raises(FinalValidationError, match="production Bands"):
        result.validate_final()


def test_adopted_roi_needs_nonempty_production_bands():
    result = example_result()
    result.roi_info.band_list.clear()
    result.roi_info.band_count = 0
    with pytest.raises(FinalValidationError, match="requires production Bands"):
        result.validate_final()


def test_auto_full_cannot_hide_fallback():
    result = example_result(fallback=True)
    result.execution_info.fallback_used = False
    with pytest.raises(FinalValidationError):
        result.validate_final()


@pytest.mark.parametrize("reason", [None, FallbackReason.QA_FAILED])
def test_full_first_attempt_reason_must_match_fallback(reason):
    result = example_result(fallback=True)
    result.execution_info.attempts[0].reason = reason
    with pytest.raises(FinalValidationError, match="first attempt reason"):
        result.validate_final()


def test_full_cannot_follow_successful_passing_roi():
    result = example_result(fallback=True)
    first = result.execution_info.attempts[0]
    first.status = ExecutionStatus.SUCCEEDED
    first.qa_status = QAStatus.PASS
    first.qa_checks = []
    with pytest.raises(FinalValidationError, match="must not trigger fallback"):
        result.validate_final()


@pytest.mark.parametrize("field,value", [("status", ExecutionStatus.FAILED), ("qa_status", QAStatus.FAIL)])
def test_full_final_attempt_requires_success_and_pass(field, value):
    result = example_result(fallback=True)
    setattr(result.execution_info.attempts[-1], field, value)
    with pytest.raises(FinalValidationError):
        result.validate_final()


def test_success_cannot_have_empty_attempts():
    result = example_result()
    result.execution_info.attempts.clear()
    with pytest.raises(FinalValidationError, match="final attempt"):
        result.validate_final()


def test_full_attempt_cannot_be_hidden_behind_roi_final():
    result = example_result(fallback=True)
    result.execution_info.final_mode = PipelineMode.ROI_BH
    with pytest.raises(FinalValidationError):
        result.validate_final()


def test_fallback_must_keep_strict_attempt_order():
    result = example_result(fallback=True)
    result.execution_info.attempts.reverse()
    with pytest.raises(FinalValidationError):
        result.validate_final()


def test_incomplete_lineage_is_not_final():
    result = example_result()
    result.audit_log.lineage_complete = False
    with pytest.raises(FinalValidationError, match="complete source lineage"):
        result.validate_final()


def test_lineage_count_and_destination_rechecked_after_mutation():
    for change in ("count", "destination"):
        result = example_result()
        if change == "count":
            result.audit_log.source_candidate_count = 999
        else:
            result.audit_log.candidates[0].final_defect_id = "DOES_NOT_EXIST"
        with pytest.raises(FinalValidationError):
            result.validate_final()


@pytest.mark.parametrize("total", ["total_defect_area_px", "total_defect_area_um2"])
def test_area_sum_mismatch_rejected(total):
    result = example_result()
    setattr(result.statistics, total, 1000)
    with pytest.raises(FinalValidationError, match=total):
        result.validate_final()


def test_area_tolerance_is_small_and_explicit():
    result = example_result()
    result.statistics.total_defect_area_px += 0.0000001
    result.validate_final()
    result.statistics.total_defect_area_px += 0.001
    with pytest.raises(FinalValidationError, match="total_defect_area_px"):
        result.validate_final()


def test_no_missing_measurements_are_filled_with_zero():
    result = example_result()
    result.defects[0].geometry.area_um2 = None
    result.defects[0].geometry.width_um = None
    result.statistics.total_defect_area_um2 = None
    before = deepcopy(result)
    result.validate_final()
    assert result == before
    loaded = InspectionResult.from_json(result.to_json())
    assert loaded.defects[0].geometry.area_um2 is None
    assert loaded.statistics.total_defect_area_um2 is None


def test_legitimate_zero_defect_final_result():
    result = example_result()
    result.defects.clear()
    result.statistics.total_defects = 0
    result.statistics.total_defect_area_px = 0
    result.statistics.total_defect_area_um2 = 0
    result.audit_log.candidates.clear()
    result.audit_log.source_candidate_count = 0
    result.validate_final()


def test_execution_qa_and_result_qc_are_independent():
    result = example_result()
    result.quality_control = QualityControl(status=QAStatus.FAIL)
    assert result.execution_info.qa_status == QAStatus.PASS
    with pytest.raises(FinalValidationError, match="Result QC PASS"):
        result.validate_final()
    result = example_result()
    result.execution_info.qa_status = QAStatus.FAIL
    assert result.quality_control.status == QAStatus.PASS
    with pytest.raises(FinalValidationError):
        result.validate_final()


def test_mandatory_result_qc_mutation_cannot_bypass_gate():
    result = example_result()
    result.quality_control.checks.append(QACheck(name="结果资源", status=QAStatus.FAIL))
    with pytest.raises(FinalValidationError):
        result.validate_final()


def test_failed_job_is_draft_only():
    result = InspectionResult(task_id="FAILED_JOB")
    assert InspectionResult.from_json(result.to_json()) == result
    with pytest.raises(FinalValidationError, match="SUCCEEDED"):
        result.validate_final()


def test_unknown_extensions_survive_gate_and_roundtrip():
    data = example_result().to_dict()
    data["extensions"]["未来指标"] = {"单位": "%", "值": None}
    data["execution_info"]["future_execution_field"] = [1, None, "中文"]
    loaded = InspectionResult.from_dict(data)
    before = deepcopy(loaded)
    loaded.validate_final()
    assert loaded == before
    assert loaded.to_dict() == data


@pytest.mark.parametrize("name", sorted(REMOVED_PLAN_FIELDS))
def test_removed_plan_fields_cannot_return_as_unknown_fields(name):
    data = example_result().to_dict()
    data["execution_info"][name] = None
    with pytest.raises(ValueError, match="removed pre-freeze plan fields"):
        InspectionResult.from_dict(data)
