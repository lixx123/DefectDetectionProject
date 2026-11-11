"""Actual existing Phase 3 revision AUTO results, never invokes a detector."""
from pathlib import Path
import json
import pytest
from domain import InspectionResult
from infrastructure.repositories import JsonResultRepository


@pytest.mark.parametrize('frame',[1,2])
def test_real_auto_repository_preserves_full_domain(frame):
    root=Path(__file__).resolve().parents[1]
    report_path=root/'docs/phase_4/phase_4_acceptance.json'
    if not report_path.exists(): pytest.skip('run scripts.validate_phase4_repository with existing evidence first')
    report=json.loads(report_path.read_text(encoding='utf-8'))
    case=next(c for c in report['cases'] if c['frame']==frame)
    original=InspectionResult.load_json(root/f'output/phase3_revision/remapped_results/26_{frame}_auto/result.json')
    repository=JsonResultRepository(root/'output/phase4_validation/repository')
    restored=repository.load(case['result_id'])
    assert restored==original
    assert restored.schema_version=='1.0'
    assert restored.execution_info.final_mode.value=='roi-bh'
    assert [a.mode.value for a in restored.execution_info.attempts]==['roi-bh']
    assert case['verify']['status']=='PASS' and case['inspection_result_exact_equal']
    assert case['result_json_values_equal']
    assert report['algorithm_executions']==0 and not report['phase5_started']
