"""Frozen-wire audit semantics and the six existing real revision snapshots."""
import csv
import json
from pathlib import Path
import pytest

from core.adapters.audit_reason_mapper import map_filter_reason, map_candidate_decision
from core.adapters.audit_mapper import map_audit
from core.runtime.resources import ResourceCollector
from domain.enums import CandidateDisposition as D, FilterReason as F
from domain import InspectionResult

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('reason,expected', [
    ('J5_J5_OUTSIDE_WORK', F.OUTSIDE_WORK_REGION), ('NONWORK', F.OUTSIDE_WORK_REGION),
    ('OUTSIDE_ROI', F.OUTSIDE_WORK_REGION), ('BACKGROUND', F.BACKGROUND_NOISE),
    ('NOISE_REJECT', F.BACKGROUND_NOISE), ('LOCAL_NOISE', F.BACKGROUND_NOISE),
    ('LOW_LOCAL_CONTRAST', F.BACKGROUND_NOISE), ('RAW_GATE_REJECT', F.SAFETY_GATE_REJECTED),
    ('RAW_CONTRAST_FAIL', F.SAFETY_GATE_REJECTED), ('STABILITY_FAIL', F.SAFETY_GATE_REJECTED),
    ('SAFETY_REJECT', F.SAFETY_GATE_REJECTED), ('LOW_EVIDENCE', F.LOW_EVIDENCE),
    ('INSUFFICIENT_EVIDENCE', F.LOW_EVIDENCE), ('WEAK_RESPONSE', F.LOW_EVIDENCE),
    ('UNFAMILIAR_DECISION', F.OTHER), ('NOT_PROVEN_NOISE', F.OTHER),
    ('J5_J5_WORK_SMALL', F.OTHER), ('USER_REJECTED', F.OTHER),
])
def test_reason_categories(reason, expected):
    assert map_filter_reason({'decision_reason': reason}) == expected


@pytest.mark.parametrize('reason', ['AREA_TOO_SMALL', 'SIZE_FILTER', 'MIN_AREA', 'GEOMETRY_REJECT'])
def test_authorized_size_extension_without_enum_change(reason):
    decision = map_candidate_decision({'decision_reason': reason})
    assert decision.disposition == D.FILTERED
    assert decision.filter_reason == F.OTHER
    assert decision.extensions['reference_reason_category'] == 'SIZE_OR_GEOMETRY_FILTER'
    assert decision.extensions['reference_fields']['decision_reason'] == reason
    assert 'SIZE_OR_GEOMETRY_FILTER' not in F._value2member_map_


@pytest.mark.parametrize('reason', [
    'K8C_MICRO_HIDE_SUGGESTION_AREA_1_OR_2PX_PROVISIONAL_NO_DELETE',
    'K8C_MICRO_REVIEW_AREA_3_TO_7PX_NOT_PROVEN_NOISE',
    'K8C_UNCERTAIN_REVIEW_DARK_SPOT_EVIDENCE_NOT_SUFFICIENT',
    'J5_J5_WORK_SMALL', 'UNRECOGNIZED_VALUE', 'STABLE_SINGLE_OUTER_REVIEW'])
def test_unselected_does_not_imply_filtered(reason):
    decision = map_candidate_decision({'decision_reason': reason})
    assert decision.disposition == D.REVIEW and decision.filter_reason is None


def test_priority_is_deterministic_and_visibility_used():
    row = {'decision_reason': 'RAW_GATE_REJECT_NOISE', 'primary_visibility_layer': 'J5_OUTSIDE_WORK'}
    assert map_filter_reason(row) == F.OUTSIDE_WORK_REGION
    assert map_filter_reason({'decision_reason': 'RAW_GATE_REJECT_NOISE'}) == F.SAFETY_GATE_REJECTED


def test_human_state_requires_explicit_evidence():
    auto = map_candidate_decision({'decision_reason': 'USER_REJECTED'})
    assert auto.filter_reason != F.USER_REJECTED
    manual = map_candidate_decision({'decision_reason': 'NOISE', 'review_source': 'HUMAN', 'review_status': 'FALSE_POSITIVE'})
    assert manual.disposition == D.FILTERED and manual.filter_reason == F.USER_REJECTED


@pytest.mark.parametrize('target,count,expected', [('F1', 1, D.RETAINED), ('F1', 2, D.MERGED)])
def test_membership_overrides_review_and_noise(target, count, expected):
    decision = map_candidate_decision({'decision_reason': 'MICRO_REVIEW_NOT_PROVEN_NOISE'}, target=target, contributor_count=count)
    assert decision.disposition == expected
    assert decision.filter_reason is None
    assert decision.merged_into == ('F1' if count > 1 else None)


def test_duplicate_requires_verified_merge_target():
    row = {'decision_reason': 'DUPLICATE', 'merged_into': 'F1'}
    unresolved = map_candidate_decision(row)
    assert unresolved.disposition == D.REVIEW and unresolved.merged_into is None
    resolved = map_candidate_decision(row, known_final_ids={'F1'})
    assert resolved.disposition == D.MERGED and resolved.merged_into == 'F1'
    assert resolved.filter_reason is None


@pytest.mark.parametrize('target', [None, 'F1'])
def test_historical_semantics_are_preserved(target):
    decision = map_candidate_decision({'decision_reason': 'NOISE_REJECT'}, target=target, historical_only=True)
    assert decision.disposition == (D.RETAINED if target else D.REVIEW)
    assert decision.filter_reason is None


def test_full_raw_reason_and_fields_survive_mapper(tmp_path):
    engine = tmp_path/'engine'; engine.mkdir()
    row = {'candidate_source_uid': 'J5:F1:DEFECT_00001', 'stage': 'J5',
           'decision_reason': 'J5_J5_OUTSIDE_WORK', 'primary_visibility_layer': 'J5_OUTSIDE_WORK',
           'classification': 'ORIGINAL_CLASS', 'execution_disposition': 'FRESH_EXACT_HISTORICAL_MEMBERS'}
    with (engine/'ALL_SOURCE_DISPOSITIONS.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
    result = map_audit(engine, {}, ResourceCollector(tmp_path/'out')).candidates[0]
    assert result.filter_reason == F.OUTSIDE_WORK_REGION and result.disposition == D.FILTERED
    assert result.filter_message == row['decision_reason'] == result.extensions['reference_decision']
    for key in ('stage', 'decision_reason', 'primary_visibility_layer', 'classification', 'execution_disposition'):
        assert result.extensions['reference_fields'][key] == row[key]


def test_focus_candidate_from_real_full_ledger():
    manifest = ROOT/'docs/phase_3/final_acceptance_runs.json'
    if not manifest.exists(): pytest.skip('local real evidence unavailable')
    run = next(r for r in json.loads(manifest.read_text(encoding='utf-8')) if r['frame'] == 1 and r['requested_mode'] == 'full')
    path = Path(run['run_directory'])/'engine/full/ALL_SOURCE_DISPOSITIONS.csv'
    if not path.exists(): pytest.skip('local real evidence unavailable')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        row = next(r for r in csv.DictReader(stream) if r['candidate_source_uid'] == 'J5:F1:DEFECT_00001')
    decision = map_candidate_decision(row)
    assert row['decision_reason'] == 'J5_J5_OUTSIDE_WORK'
    assert decision.disposition == D.FILTERED and decision.filter_reason == F.OUTSIDE_WORK_REGION


@pytest.mark.parametrize('frame,mode', [(f, m) for f in (1, 2) for m in ('full', 'roi-bh', 'auto')])
def test_real_remapped_snapshots(frame, mode):
    path = ROOT/f'output/phase3_revision/remapped_results/26_{frame}_{mode}/result.json'
    if not path.exists(): pytest.skip('run read-only six-case revision validation first')
    result = InspectionResult.load_json(path); result.validate_final()
    assert result.schema_version == '1.0'
    assert result.extensions['algorithm_recomputed_in_this_mapping_step'] is False
    assert result.extensions['fresh_engine_execution'] is True
    if mode == 'auto':
        assert [a.mode.value for a in result.execution_info.attempts] == ['roi-bh']
        assert result.execution_info.final_mode.value == 'roi-bh'
    assert len(result.defects) == (36 if frame == 1 else 35)
    assert result.statistics.total_defect_area_px == (20356 if frame == 1 else 17709)


def test_remap_tool_has_no_engine_entrypoint():
    import scripts.remap_phase3_results as module
    assert not hasattr(module, 'Detector')
    assert not hasattr(module, 'subprocess')


def test_config_connected_and_auto_policy_preserved():
    from configs.loader import load_config
    config = load_config(ROOT/'configs/production_v1.yaml')
    assert config.status == 'REFERENCE_ENGINE_CONNECTED'
    assert config.pipeline_mode.value == 'auto'
    assert config.auto_policy.primary.value == 'roi-bh'
    assert config.auto_policy.fallback.value == 'full'
