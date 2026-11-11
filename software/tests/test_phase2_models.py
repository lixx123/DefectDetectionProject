from dataclasses import FrozenInstanceError
import copy
import json
from pathlib import Path

import pytest

from domain import *
from domain.common import ArtifactReference, BoundingBox
from domain.enums import *
from domain.defect import Classification, DetectionInfo
from domain.configuration import AutoPolicy, InspectionConfig
from domain.serialization import from_dict, to_dict
from domain.migrations import MigrationRegistry, SchemaVersionError
from configs.loader import load_config, save_config
from examples.phase2_roundtrip import example_result


def test_minimal_defect_and_result():
    defect = Defect(identity=DefectIdentity(defect_id="D1"))
    assert defect.morphology.circularity is None
    result = InspectionResult(task_id="T1", defects=[defect])
    assert result.schema_version == "1.0"
    assert InspectionResult.from_json(result.to_json()) == result


def test_default_scale():
    c = CalibrationInfo()
    assert c.spatial_scale_um_per_px == 3.2
    assert c.scale_source == ScaleSource.DEFAULT
    assert not c.metrologically_calibrated


def test_pixel_to_um_and_squared_area():
    g = DefectGeometry(area_px=10, length_px=5, width_px=2,
                       equivalent_diameter_px=3).with_calibration(CalibrationInfo())
    assert g.length_um == pytest.approx(16)
    assert g.width_um == pytest.approx(6.4)
    assert g.area_um2 == pytest.approx(102.4)
    assert g.equivalent_diameter_um == pytest.approx(9.6)
    assert g.area_px == 10 and g.length_px == 5


def test_invalid_scale_keeps_pixel_values():
    c = CalibrationInfo(spatial_scale_um_per_px=None, valid=False, scale_source=ScaleSource.UNKNOWN)
    g = DefectGeometry(area_px=3, length_px=2).with_calibration(c)
    assert g.area_px == 3 and g.length_px == 2
    assert g.area_um2 is None and g.length_um is None


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_bad_scales_rejected(value):
    with pytest.raises(ValueError):
        CalibrationInfo(spatial_scale_um_per_px=value)


def test_manual_scale_provenance():
    c = CalibrationInfo().with_user_scale(4)
    assert c.scale_source == ScaleSource.USER_CONFIG and c.linear_um(3) == 12
    assert CalibrationInfo(spatial_scale_um_per_px=4).scale_source == ScaleSource.USER_CONFIG


@pytest.mark.parametrize("fallback", [False, True])
def test_success_and_fallback_roundtrip(tmp_path, fallback):
    r = example_result(fallback=fallback)
    path = tmp_path / "中文结果.json"
    r.save_json(path)
    assert InspectionResult.load_json(path) == r
    assert "工作波段一" in path.read_text(encoding="utf8")
    assert json.loads(path.read_text(encoding="utf8"))["execution_info"]["final_mode"] == ("full" if fallback else "roi-bh")


def test_fallback_is_successful_not_fault():
    r = example_result(fallback=True)
    assert r.execution_info.status == ExecutionStatus.SUCCEEDED
    assert r.execution_info.attempts[0].status == ExecutionStatus.FAILED
    assert r.execution_info.fallback_reason == FallbackReason.BAND_GEOMETRY_INVALID
    assert [a.mode for a in r.execution_info.attempts] == [PipelineMode.ROI_BH, PipelineMode.FULL]


def test_full_fallback_may_fail_without_adopting_result():
    e = ExecutionInfo(requested_mode=PipelineMode.AUTO, attempted_mode=PipelineMode.ROI_BH,
        fallback_used=True, fallback_reason=FallbackReason.QA_FAILED,
        status=ExecutionStatus.FAILED, final_mode=None, qa_status=QAStatus.FAIL,
        attempts=[ExecutionAttempt(mode=PipelineMode.ROI_BH, status=ExecutionStatus.FAILED),
                  ExecutionAttempt(mode=PipelineMode.FULL, status=ExecutionStatus.FAILED)])
    assert from_dict(ExecutionInfo, to_dict(e)) == e


@pytest.mark.parametrize("reason", list(FallbackReason))
def test_all_fallback_reasons_have_stable_wire_values(reason):
    e = ExecutionInfo(attempted_mode=PipelineMode.ROI_BH, fallback_used=True, fallback_reason=reason)
    assert from_dict(ExecutionInfo, to_dict(e)).fallback_reason is reason


def test_roi_j4_not_in_auto_chain():
    with pytest.raises(ValueError):
        ExecutionInfo(attempted_mode=PipelineMode.ROI_J4)
    with pytest.raises(ValueError):
        AutoPolicy(fallback=PipelineMode.ROI_J4)
    with pytest.raises(ValueError):
        ExecutionInfo(attempted_mode=PipelineMode.ROI_BH,
            attempts=[ExecutionAttempt(mode=PipelineMode.ROI_BH), ExecutionAttempt(mode=PipelineMode.ROI_J4)])


def test_passing_qa_required_for_adopted_result():
    with pytest.raises(ValueError):
        ExecutionInfo(attempted_mode=PipelineMode.ROI_BH, final_mode=PipelineMode.ROI_BH,
                      status=ExecutionStatus.SUCCEEDED)
    with pytest.raises(ValueError):
        QualityControl(status=QAStatus.PASS, checks=[QACheck(name="lineage", status=QAStatus.FAIL)])


def test_plan_tile_accounting():
    assert DetectionPlanInfo(planned_tiles=10, full_tiles=15, skipped_tiles=5)
    with pytest.raises(ValueError):
        DetectionPlanInfo(planned_tiles=10, full_tiles=15, skipped_tiles=4)


def test_roi_band_references_roundtrip():
    roi = example_result().roi_info
    assert from_dict(ROIInfo, to_dict(roi)) == roi
    assert roi.band_list[0].bbox == BoundingBox(0, 0, 100, 100)
    with pytest.raises(ValueError):
        ROIInfo(band_count=2, band_list=roi.band_list)


def test_missing_optional_fields():
    r = InspectionResult.from_dict({"schema_version": "1.0", "task_id": "T", "result_id": "R"})
    assert r.roi_info.band_count == 0 and r.defects == []
    assert r.calibration_info.spatial_scale_um_per_px == 3.2


def test_extensions_preserved_at_every_level():
    r = example_result()
    r.extensions = {"中文": [None, True, {"值": 1.25}]}
    r.roi_info.extensions = {"新波段": "未来"}
    r.defects[0].geometry.extensions = {"AI": {"模型": "v3"}}
    assert InspectionResult.from_json(r.to_json()) == r


def test_unknown_additive_fields_resaved_in_place():
    data = example_result().to_dict()
    data["future_root"] = {"中文": None}
    data["defects"][0]["geometry"]["future_width"] = [1, 2]
    data["defects"][0]["review"]["future_review"] = "新信息"
    r = InspectionResult.from_dict(data)
    assert r.to_dict() == data
    assert InspectionResult.from_json(r.to_json()) == r


def test_review_does_not_overwrite_algorithm_decision():
    original = ReviewInfo(algorithm_decision="DEFECT")
    reviewed = original.reviewed(status=ReviewStatus.FALSE_POSITIVE, decision="噪声", reviewer="工程师")
    twice = reviewed.reviewed(status=ReviewStatus.UNCERTAIN, decision="再检查")
    assert twice.algorithm_decision == original.algorithm_decision == "DEFECT"
    assert original.review_status == ReviewStatus.UNREVIEWED
    assert len(twice.history) == 2
    with pytest.raises(FrozenInstanceError):
        twice.algorithm_decision = "NOISE"
    assert from_dict(ReviewInfo, to_dict(twice)) == twice


def test_migration_interface_without_mutating_input():
    registry = MigrationRegistry()
    def upgrade(data):
        data["schema_version"] = "1.0"
        return data
    registry.register("0.9", "1.0", upgrade)
    payload = {"schema_version": "0.9", "task_id": "T", "result_id": "R", "extensions": {"旧": 1}}
    loaded = InspectionResult.from_dict(payload, migrations=registry)
    assert loaded.schema_version == "1.0" and loaded.extensions == {"旧": 1}
    assert payload["schema_version"] == "0.9"


@pytest.mark.parametrize("version", [None, "2.0", "0.9"])
def test_unsupported_schema_explicit_error(version):
    with pytest.raises(SchemaVersionError):
        InspectionResult.from_dict({"schema_version": version, "task_id": "T"})


def test_preserve_old_results_by_default(tmp_path):
    r = example_result()
    path = tmp_path / "result.json"
    r.save_json(path)
    old = path.read_bytes()
    with pytest.raises(FileExistsError):
        r.save_json(path)
    assert path.read_bytes() == old


@pytest.mark.parametrize("path", ["C:/data/mask.png", "D:relative.png", "../mask.png", "/mask.png", "\\\\host\\mask.png", "https://host/mask.png"])
def test_artifact_paths_cannot_depend_on_machine_absolute_paths(path):
    with pytest.raises(ValueError):
        ArtifactReference(path=path)


def test_relative_path_normalization():
    assert ArtifactReference(path=Path("masks") / "a.png").path == "masks/a.png"


def test_nonfinite_and_wrong_types_rejected():
    data = example_result().to_dict()
    data["calibration_info"]["valid"] = "false"
    with pytest.raises((ValueError, TypeError)):
        InspectionResult.from_dict(data)
    r = example_result()
    r.extensions["bad"] = float("nan")
    with pytest.raises((ValueError, TypeError)):
        r.to_json()
    with pytest.raises(ValueError):
        InspectionResult.from_json('{"task_id":"T","task_id":"R"}')


def test_filtered_and_merged_candidates_have_disposition_evidence():
    with pytest.raises(ValueError):
        CandidateAuditRecord(candidate_id="C1", source="H", disposition=CandidateDisposition.FILTERED)
    with pytest.raises(ValueError):
        CandidateAuditRecord(candidate_id="C1", source="H", disposition=CandidateDisposition.MERGED)


def test_lineage_complete_cannot_drop_candidate_records():
    with pytest.raises(ValueError):
        InspectionResult(task_id="T", audit_log=AuditInfo(lineage_complete=True, source_candidate_count=1))
    with pytest.raises(ValueError):
        InspectionResult(task_id="T", audit_log=AuditInfo(lineage_complete=True, source_candidate_count=1,
            candidates=[CandidateAuditRecord(candidate_id="C", source="H", final_defect_id="missing")]))


def test_size_and_severity_are_independent():
    c = Classification(size_grade=SizeGrade.LARGE, severity_grade=SeverityGrade.UNKNOWN)
    assert c.size_grade == SizeGrade.LARGE and c.severity_grade == SeverityGrade.UNKNOWN


@pytest.mark.parametrize("name", ["production_v1", "high_sensitivity", "debug"])
def test_yaml_config_models(tmp_path, name):
    c = load_config(Path(__file__).parents[1] / "configs" / (name + ".yaml"))
    assert c.calibration.spatial_scale_um_per_px == 3.2
    assert c.auto_policy.fallback == PipelineMode.FULL
    assert c.algorithm_parameters == {}
    path = tmp_path / "配置.yaml"
    save_config(c, path)
    assert load_config(path) == c


def test_production_debug_separation_and_hash():
    with pytest.raises(ValueError):
        InspectionConfig(pipeline_mode=PipelineMode.ROI_J4)
    c = InspectionConfig()
    assert len(c.config_hash()) == 64
    changed = copy.deepcopy(c)
    changed.calibration = changed.calibration.with_user_scale(4)
    assert c.config_hash() != changed.config_hash()
    assert InspectionConfig(pipeline_mode=PipelineMode.LEGACY_REPLAY, advanced_debug=True)


def test_no_success_without_attempt_evidence():
    with pytest.raises(ValueError):
        ExecutionInfo(final_mode=PipelineMode.ROI_BH, status=ExecutionStatus.SUCCEEDED,
                      qa_status=QAStatus.PASS)
    with pytest.raises(ValueError):
        ExecutionInfo(requested_mode=PipelineMode.FULL, attempted_mode=PipelineMode.ROI_BH)


def test_domain_updates_keep_future_fields():
    r = example_result().to_dict()
    r["calibration_info"]["future_calibration"] = 1
    r["defects"][0]["geometry"]["future_width"] = 2
    r["defects"][0]["review"]["future_review"] = 3
    loaded = InspectionResult.from_dict(r)
    loaded.calibration_info = loaded.calibration_info.with_user_scale(4)
    loaded.defects[0].geometry = loaded.defects[0].geometry.with_calibration(loaded.calibration_info)
    loaded.defects[0].review = loaded.defects[0].review.reviewed(status=ReviewStatus.CONFIRMED)
    encoded = loaded.to_dict()
    assert encoded["calibration_info"]["future_calibration"] == 1
    assert encoded["defects"][0]["geometry"]["future_width"] == 2
    assert encoded["defects"][0]["review"]["future_review"] == 3


def test_statistics_reject_invalid_counts():
    with pytest.raises(ValueError):
        InspectionStatistics(count_by_band={"B01": -1})


def test_json_nan_unknown_enum_and_missing_required_identity():
    for text in ['{"schema_version":"1.0","task_id":"T","extensions":{"bad":NaN}}',
                 '{"schema_version":"1.0","task_id":"T","execution_info":{"requested_mode":"future-mode"}}',
                 '{"schema_version":"1.0","task_id":"T","defects":[{}]}']:
        with pytest.raises((ValueError, TypeError)):
            InspectionResult.from_json(text)
