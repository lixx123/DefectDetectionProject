"""Level 2: parse protected real baselines only. Never run production detection."""
from pathlib import Path
import json
import subprocess
import sys
import pytest
from domain import ImageInfo, AlgorithmInfo, ExecutionInfo, ExecutionAttempt
from domain.configuration import InspectionConfig
from domain.enums import PipelineMode, ExecutionStatus, QAStatus
from core.adapters.reference_engine_adapter import ReferenceEngineAdapter
from core.adapters.result_mapper import map_result
from core.adapters.qa_mapper import execution_checks, classify_failure
from core.runtime.resources import load_json, sha256
from domain.enums import FallbackReason


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=[1, 2])
def parsed_baseline(request, tmp_path_factory):
    frame = request.param
    adapter = ReferenceEngineAdapter()
    profile = adapter.profile()
    engine = ROOT / "baseline/results/unified_26" / f"26_{frame}"
    input_row = load_json(ROOT / "baseline/baseline_manifest.json")["raw_inputs"][frame - 1]
    checks = execution_checks(engine, [], legacy=True)
    assert all(c.status == QAStatus.PASS for c in checks)
    execution = ExecutionInfo(requested_mode=PipelineMode.LEGACY_REPLAY,
        attempted_mode=PipelineMode.LEGACY_REPLAY, final_mode=PipelineMode.LEGACY_REPLAY,
        status=ExecutionStatus.SUCCEEDED, qa_status=QAStatus.PASS, qa_checks=checks,
        attempts=[ExecutionAttempt(mode=PipelineMode.LEGACY_REPLAY, status=ExecutionStatus.SUCCEEDED,
                    qa_status=QAStatus.PASS, qa_checks=list(checks))])
    info = ImageInfo(file_name=f"26 ({frame}).raw", sha256=input_row["sha256"], width_px=profile.width,
        height_px=profile.height, container_bits=16, effective_bits=profile.effective_bits,
        byte_order=profile.byte_order, input_format="RAW", sample_id="26")
    result = map_result(engine, tmp_path_factory.mktemp(f"baseline_{frame}"),
        InspectionConfig(pipeline_mode=PipelineMode.LEGACY_REPLAY, advanced_debug=True), info,
        AlgorithmInfo(algorithm_version="legacy-manifest:" + sha256(ROOT / "baseline/source_manifest.json")),
        execution, reference_root=adapter.reference_root)
    result.validate_final()
    return frame, result


def test_real_frozen_counts_areas_and_approved_spots(parsed_baseline):
    frame, result = parsed_baseline
    count, area, approved = (36, 20356, [297, 398]) if frame == 1 else (35, 17709, [348, 370])
    assert len(result.defects) == count
    assert result.statistics.total_defect_area_px == area
    assert sorted(d.geometry.area_px for d in result.defects if d.extensions["human_confirmed_darkspot"]) == approved
    assert result.statistics.total_defect_area_um2 == pytest.approx(area * result.calibration_info.spatial_scale_um_per_px ** 2)
    assert result.extensions["real_input_run"] is False


def test_real_frozen_lineage_bidirectional_and_recovery(parsed_baseline):
    frame, result = parsed_baseline
    assert result.audit_log.source_candidate_count == (32370 if frame == 1 else 8332)
    destinations = {row.final_defect_id for row in result.audit_log.candidates if row.final_defect_id}
    assert destinations == {d.identity.defect_id for d in result.defects}
    assert any(event["event"] == "RAW_RECOVERY" for event in result.audit_log.events)
    assert all(d.detection.candidate_ids for d in result.defects)


def test_real_frozen_resources_are_portable(parsed_baseline):
    frame, result = parsed_baseline
    for defect in result.defects:
        ref = defect.geometry.mask_reference
        assert not Path(ref.path).is_absolute() and ref.sha256
    assert result.quality_control.status == QAStatus.PASS


def test_original_sentinel_guard_really_rejects_uncomputed_values():
    adapter = ReferenceEngineAdapter()
    code = """import numpy as np
from src.detection.two_level_roi import require_computed_response
try:
    require_computed_response(np.array([[65535]], dtype=np.uint16), 'Phase3 synthetic safety probe')
except RuntimeError as exc:
    print(str(exc))
else:
    raise SystemExit('guard failed to reject sentinel')
"""
    import os
    probe = subprocess.run([str(adapter.python_executable), "-c", code], cwd=adapter.reference_root,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"))
    assert probe.returncode == 0, probe.stderr
    assert classify_failure(probe.stdout) == FallbackReason.SENTINEL_CONSUMED


def test_worker_pins_reference_namespace_despite_software_scripts_package(tmp_path):
    import os
    adapter = ReferenceEngineAdapter()
    raw = tmp_path / "bad.raw"
    raw.write_bytes(b"not a full RAW")
    output = tmp_path / "worker_probe"
    command = [str(adapter.python_executable), str(ROOT / "core/runtime/engine_worker.py"),
        "--reference-root", str(adapter.reference_root), "--input", str(raw),
        "--output", str(output), "--mode", "roi-bh"]
    probe = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf8", timeout=30,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"))
    assert probe.returncode == 2
    error = load_json(output / "bridge_error.json")
    # Intentionally short RAW fails after successful real-engine imports.
    assert error["stage"] != "IMPORT"
    assert "cannot import name" not in error["error"]
