"""Pure-Python protocol example. Does not run the detector or import Qt/OpenCV."""
from pathlib import Path
import sys

from domain import (InspectionResult, Defect, DefectIdentity, DefectGeometry,
                    CalibrationInfo, ROIInfo, BandInfo, ExecutionInfo,
                    ExecutionAttempt, DetectionPlanInfo, QACheck, QualityControl,
                    InspectionStatistics, CandidateAuditRecord, AuditInfo)
from domain.common import ArtifactReference, BoundingBox
from domain.enums import (PipelineMode, FallbackReason, QAStatus, ExecutionStatus,
                          CandidateDisposition, GeometryStatus)


def example_result(*, fallback=False):
    calibration = CalibrationInfo()
    qa = QACheck(name="源候选完整性", status=QAStatus.PASS)
    plan = DetectionPlanInfo(planned_tiles=12, full_tiles=20, skipped_tiles=8,
                             legal_source_pixels=50000,
                             roi_geometry_status=GeometryStatus.VALID,
                             band_geometry_status=GeometryStatus.VALID)
    first = ExecutionAttempt(mode=PipelineMode.ROI_BH, plan=plan,
                             status=ExecutionStatus.SUCCEEDED, qa_status=QAStatus.PASS,
                             qa_checks=[qa])
    attempts = [first]
    if fallback:
        first.status = ExecutionStatus.FAILED
        first.qa_status = QAStatus.FAIL
        first.qa_checks = [QACheck(name="Band几何", status=QAStatus.FAIL)]
        first.reason = FallbackReason.BAND_GEOMETRY_INVALID
        first.plan.band_geometry_status = GeometryStatus.INVALID
        attempts.append(ExecutionAttempt(mode=PipelineMode.FULL,
                         status=ExecutionStatus.SUCCEEDED, qa_status=QAStatus.PASS,
                         qa_checks=[qa], plan=DetectionPlanInfo(planned_tiles=20,
                         full_tiles=20, skipped_tiles=0, legal_source_pixels=100000)))
    result = InspectionResult(task_id="演示任务-仅数据协议",
        calibration_info=calibration,
        execution_info=ExecutionInfo(requested_mode=PipelineMode.AUTO,
            attempted_mode=PipelineMode.ROI_BH,
            final_mode=PipelineMode.FULL if fallback else PipelineMode.ROI_BH,
            status=ExecutionStatus.SUCCEEDED, fallback_used=fallback,
            fallback_reason=FallbackReason.BAND_GEOMETRY_INVALID if fallback else None,
            fallback_message="Band几何无效，full已完成" if fallback else None,
            attempts=attempts, qa_status=QAStatus.PASS, qa_checks=[qa]),
        roi_info=ROIInfo(status=GeometryStatus.INVALID if fallback else GeometryStatus.VALID, band_count=1,
            band_list=[BandInfo(band_id="B01", name="工作波段一",
                bbox=BoundingBox(0, 0, 100, 100), valid=not fallback,
                extensions={"failure_reason": "BAND_GEOMETRY_INVALID"} if fallback else {},
                mask_reference=ArtifactReference(path="masks/B01.png"))],
            geometry_source="EXAMPLE_ONLY"),
        defects=[Defect(identity=DefectIdentity(defect_id="D001"),
            geometry=DefectGeometry(bbox=BoundingBox(10, 20, 15, 25),
                area_px=9, length_px=5, width_px=2,
                mask_reference=ArtifactReference(path="masks/D001.npz")).with_calibration(calibration),
            extensions={"响应下降率": None, "未来指标": {"单位": "%", "值": 1.5}})],
        statistics=InspectionStatistics(total_defects=1, total_defect_area_px=9,
                                         total_defect_area_um2=calibration.area_um2(9)),
        audit_log=AuditInfo(source_candidate_count=2, lineage_complete=True, candidates=[
            CandidateAuditRecord(candidate_id="C001", source="示例通道",
                disposition=CandidateDisposition.RETAINED, final_defect_id="D001"),
            CandidateAuditRecord(candidate_id="C002", source="示例通道",
                disposition=CandidateDisposition.REVIEW, current_stage="人工待审")]),
        quality_control=QualityControl(status=QAStatus.PASS, checks=[
            QACheck(name="结果字段与统计审计自洽（纯数据示例）", status=QAStatus.PASS)]))
    return result


def main(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    for fallback in (False, True):
        result = example_result(fallback=fallback)
        result.validate_final()
        dest = output / ("fallback_result.json" if fallback else "roi_success_result.json")
        result.save_json(dest)
        loaded = InspectionResult.load_json(dest)
        loaded.validate_final()
        assert loaded == result
    print("PASS: ROI成功与直接FULL回退，两份中文JSON均round-trip一致")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
