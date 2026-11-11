"""Frozen production policy: ROI_BH first, direct FULL only on rejection."""
from domain import ExecutionInfo, InspectionResult, QualityControl, ROIInfo
from domain.enums import PipelineMode, ExecutionStatus, QAStatus, FallbackReason
from core.runtime.execution_runner import run_attempt
from core.adapters.roi_mapper import map_roi
from core.runtime.resources import ResourceCollector
from core.adapters.qa_mapper import check


def execute(adapter, image_path, config, run_dir, input_info, algorithm_info, input_checks,
            logger, *, legacy_dir=None):
    requested = config.pipeline_mode
    modes = [PipelineMode.ROI_BH, PipelineMode.FULL] if requested == PipelineMode.AUTO else [requested]
    attempts, result, outputs = [], None, []
    for mode in modes:
        candidate, attempt, output = run_attempt(adapter, image_path, mode, run_dir, config,
            input_info, algorithm_info, input_checks, logger, legacy_dir=legacy_dir)
        attempts.append(attempt)
        outputs.append(output)
        if candidate is not None:
            result = candidate
            break
        if requested == PipelineMode.AUTO and len(attempts) == 1:
            logger.warning("fallback trigger: %s; direct FULL (no ROI_J4)", attempt.reason.value)
    fallback = requested == PipelineMode.AUTO and len(attempts) == 2
    reason = attempts[0].reason if fallback else None
    execution = ExecutionInfo(requested_mode=requested, attempted_mode=attempts[0].mode,
        final_mode=attempts[-1].mode if result is not None else None,
        status=ExecutionStatus.SUCCEEDED if result is not None else ExecutionStatus.FAILED,
        fallback_used=fallback, fallback_reason=reason,
        fallback_message=attempts[0].message if fallback else None,
        qa_status=QAStatus.PASS if result is not None else QAStatus.FAIL,
        qa_checks=list(attempts[-1].qa_checks), attempts=attempts)
    if result is None:
        return InspectionResult(task_id=run_dir.name, input_info=input_info, algorithm_info=algorithm_info,
            calibration_info=config.calibration, execution_info=execution,
            quality_control=QualityControl(status=QAStatus.FAIL,
                checks=[check("no_adoptable_result", False, "All requested attempts rejected", stage="RESULT_QC")]))
    result.execution_info = execution
    if fallback and reason == FallbackReason.BAND_GEOMETRY_INVALID:
        failed_roi, _ = map_roi(outputs[0], ResourceCollector(run_dir), raw_path=image_path,
                                shape=(input_info.height_px, input_info.width_px), trusted=False)
        result.roi_info = failed_roi
        result.intermediate_results.extensions["geometry_scope"] = "FULL artifacts; ROIInfo preserves failed primary geometry"
    return result
