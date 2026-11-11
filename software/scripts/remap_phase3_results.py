"""Remap existing Phase 3 evidence; never invokes a detector or engine process."""
import argparse
import copy
from pathlib import Path

from domain import InspectionResult
from domain.configuration import InspectionConfig
from domain.enums import PipelineMode
from core.adapters.result_mapper import map_result


def remap_result(engine_dir, original_result, output_dir, *, reference_root=None, raw_path=None):
    engine_dir, original_result, output_dir = map(Path, (engine_dir, original_result, output_dir))
    original = InspectionResult.load_json(original_result)
    original.validate_final()
    if not engine_dir.is_dir():
        raise ValueError("existing engine directory required")
    if output_dir.resolve().is_relative_to(engine_dir.resolve()):
        raise ValueError("revision output must be outside engine evidence")
    output_dir.mkdir(parents=True, exist_ok=False)
    config = InspectionConfig(pipeline_mode=original.execution_info.requested_mode,
        advanced_debug=original.execution_info.requested_mode != PipelineMode.AUTO,
        calibration=copy.deepcopy(original.calibration_info),
        intermediate_level=original.intermediate_results.level)
    result = map_result(engine_dir, output_dir, config, copy.deepcopy(original.input_info),
        copy.deepcopy(original.algorithm_info), copy.deepcopy(original.execution_info),
        reference_root=reference_root, raw_path=raw_path)
    # map_result adds lineage checks to the supplied execution; keep one exact copy.
    for holder in [result.execution_info, *result.execution_info.attempts]:
        unique = {}
        for check in holder.qa_checks:
            key = (check.name, check.stage)
            if key in unique and unique[key] != check:
                raise ValueError("conflicting duplicate QA checks")
            unique[key] = check
        holder.qa_checks = list(unique.values())
    for field in ("input_info", "algorithm_info", "calibration_info", "execution_info",
                  "defects", "roi_info", "statistics", "quality_control", "intermediate_results"):
        if getattr(original, field) != getattr(result, field):
            raise ValueError(f"remap changed protected result field: {field}")
    if result.audit_log.source_candidate_count != original.audit_log.source_candidate_count:
        raise ValueError("remap changed source count")
    before = {r.candidate_id: r for r in original.audit_log.candidates}
    after = {r.candidate_id: r for r in result.audit_log.candidates}
    if before.keys() != after.keys():
        raise ValueError("remap changed source membership")
    for uid, candidate in after.items():
        old = before[uid]
        for field in ("candidate_id", "source", "initial_geometry", "current_stage", "final_defect_id"):
            if getattr(candidate, field) != getattr(old, field):
                raise ValueError(f"remap changed protected candidate field: {uid}:{field}")
        if candidate.extensions["historical_only_not_recomputed"] != old.extensions["historical_only_not_recomputed"]:
            raise ValueError("remap changed archive identity")
    if original.audit_log.events != result.audit_log.events:
        raise ValueError("remap changed RAW recovery history")
    result.task_id = original.task_id
    result.extensions = copy.deepcopy(original.extensions)
    provenance = {"fresh_engine_execution": bool(original.extensions.get("real_input_run")),
        "remapped_after_audit_reason_revision": True,
        "algorithm_recomputed_in_this_mapping_step": False,
        "original_result_id": original.result_id}
    result.extensions.update(provenance)
    result.extensions["mapping_provenance"] = provenance
    result.validate_final()
    result.save_json(output_dir / "result.json")
    restored = InspectionResult.load_json(output_dir / "result.json")
    restored.validate_final()
    if restored != result:
        raise ValueError("revision JSON roundtrip differs")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", required=True)
    parser.add_argument("--original-result", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reference-root")
    parser.add_argument("--raw-path", help="existing RAW read only, for unchanged band statistics")
    args = parser.parse_args()
    result = remap_result(args.engine_dir, args.original_result, args.output_dir,
        reference_root=args.reference_root, raw_path=args.raw_path)
    print(f"PASS {result.result_id}: {len(result.defects)} defects; algorithm not executed")


if __name__ == "__main__":
    main()
