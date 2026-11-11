"""Attempt control with explicit QA/mapping failures; no algorithm definitions."""
from datetime import datetime, timezone, timedelta
import logging
import time
from pathlib import Path
from domain import ExecutionAttempt, ExecutionInfo
from domain.enums import PipelineMode, QAStatus, ExecutionStatus, FallbackReason
from core.errors import InspectionCancelled, InspectionError
from core.adapters.qa_mapper import execution_checks, geometry_plan, classify_failure, check
from core.adapters.result_mapper import map_result


def timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def run_attempt(adapter, image_path, mode, run_dir, config, input_info, algorithm_info,
                input_checks, logger, *, legacy_dir=None):
    started, start = timestamp(), time.perf_counter()
    output = Path(legacy_dir) if legacy_dir else run_dir / "engine" / mode.value
    try:
        if legacy_dir:
            error = None
        else:
            output, error = adapter.run(image_path, mode, run_dir, logger)
        if error:
            reason = FallbackReason(error["reason"])
            logger.error("engine failure stage=%s reason=%s details=%s", error.get("stage"), reason, error.get("error"))
            attempt = ExecutionAttempt(mode=mode, status=ExecutionStatus.FAILED,
                plan=geometry_plan(output), qa_status=QAStatus.FAIL,
                qa_checks=[*input_checks, check("engine_execution", False, reason.value, stage=error.get("stage", "ENGINE"))],
                reason=reason, message=f"Engine failed at {error.get('stage', 'ENGINE')}; see engine log",
                started_at=started, finished_at=timestamp(), execution_time_seconds=time.perf_counter()-start)
            return None, attempt, output
        checks = execution_checks(output, input_checks, legacy=mode == PipelineMode.LEGACY_REPLAY)
        failed = next((c for c in checks if c.mandatory and c.status != QAStatus.PASS), None)
        if failed:
            from core.errors import ExecutionQAError
            raise ExecutionQAError(f"{failed.name} {failed.stage} QA failed")
        attempt = ExecutionAttempt(mode=mode, status=ExecutionStatus.SUCCEEDED,
            plan=geometry_plan(output), qa_status=QAStatus.PASS, qa_checks=list(checks),
            started_at=started, finished_at=timestamp(), execution_time_seconds=time.perf_counter()-start)
        execution = ExecutionInfo(requested_mode=mode, attempted_mode=mode, final_mode=mode,
            status=ExecutionStatus.SUCCEEDED, qa_status=QAStatus.PASS, qa_checks=list(checks), attempts=[attempt])
        logger.info("Execution QA PASS; mapping start %s", mode.value)
        result = map_result(output, run_dir, config, input_info, algorithm_info, execution,
                            reference_root=adapter.reference_root, raw_path=image_path)
        result.validate_final()
        logger.info("mapping end; Result QC PASS count=%d area=%s", len(result.defects), result.statistics.total_defect_area_px)
        return result, attempt, output
    except InspectionCancelled:
        raise
    except Exception as exc:
        logger.exception("attempt rejected %s", mode.value)
        reason = classify_failure(str(exc), stage=type(exc).__name__)
        # A failure to parse/verify output is not an approved empty inspection.
        attempt = ExecutionAttempt(mode=mode, status=ExecutionStatus.FAILED,
            plan=geometry_plan(output) if (output / "detection_plan.json").is_file() else geometry_plan(run_dir / "missing"),
            qa_status=QAStatus.FAIL,
            qa_checks=[*input_checks, check("attempt_adoption", False, reason.value, stage=type(exc).__name__)],
            reason=reason, message=f"{type(exc).__name__}: attempt rejected; see run log",
            started_at=started, finished_at=timestamp(), execution_time_seconds=time.perf_counter()-start)
        return None, attempt, output
