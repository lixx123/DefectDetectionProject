"""Real 26_1/26_2 regression gate for the completed two-level benchmark.

This test intentionally consumes fresh benchmark artifacts. In a source-only
checkout without those artifacts it skips rather than fabricating evidence.
"""
from pathlib import Path
import json
import pandas as pd
import pytest
from config import user_config as C

BENCH=C.OUTPUT_ROOT/'K8A_TWO_LEVEL_20261020_v1'
PROGRESS=BENCH/'benchmark_progress.json'
ROWS=BENCH/'completed_benchmarks.json'
if not PROGRESS.is_file() or not ROWS.is_file():
    pytest.skip('fresh six-run two-level benchmark artifacts unavailable',allow_module_level=True)

progress=json.loads(PROGRESS.read_text(encoding='utf8'))
if progress.get('phase')!='ALL_SIX_FRESH_RUNS_AND_QA_COMPLETE':
    pytest.skip('fresh six-run two-level benchmark incomplete',allow_module_level=True)

records=json.loads(ROWS.read_text(encoding='utf8'))
lookup={(int(r['frame']),str(r['mode'])):r for r in records}


def qa(frame,mode):
    out=Path(lookup[(frame,mode)]['output'])
    return json.loads((out/'independent_QA/QA.json').read_text(encoding='utf8'))


def test_all_six_fresh_modes_have_independent_QA_pass():
    assert set(lookup)=={(f,m) for f in (1,2) for m in ('full','roi-j4','roi-bh')}
    for frame,mode in sorted(lookup):
        q=qa(frame,mode)
        assert q['status']=='PASS'
        assert q['errors']==[]
        assert q['BH_work_window_diff_pixels_with_repeats']==0
        assert q['J4_grouped_source_diff_pixels']==0
        assert q['final_binary_diff_pixels']==0
        assert q['negative_conflict_pixels']==0
        assert q['actual_scheduled_complete']


@pytest.mark.parametrize('frame,areas,objects,total_area',[
    (1,[297,398],36,20356),
    (2,[348,370],35,17709),
])
def test_roi_modes_preserve_final_result_while_reducing_work(frame,areas,objects,total_area):
    full=lookup[(frame,'full')]
    assert full['actual_fresh_J4_tiles']==full['full_tiles']==1620
    assert full['objects']==objects and full['area']==total_area
    assert sorted(full['confirmed_areas'])==areas
    for mode in ('roi-j4','roi-bh'):
        r=lookup[(frame,mode)]
        assert r['roi_mode']=='K8A_WORK_ROI'
        assert r['actual_fresh_J4_tiles']<full['actual_fresh_J4_tiles']
        assert r['skipped_tiles']>0
        assert r['objects']==objects and r['area']==total_area
        assert sorted(r['confirmed_areas'])==areas
    assert lookup[(frame,'roi-bh')]['blackhat_input_pixels_with_repeats'] < full['blackhat_input_pixels_with_repeats']


def test_all_historical_sources_remain_auditable_even_when_nonwork_is_not_rescanned():
    q1=qa(1,'roi-bh');q2=qa(2,'roi-bh')
    assert q1['historical_source_rows']==32370
    assert q2['historical_source_rows']==8332
    assert q1['historical_source_rows']+q2['historical_source_rows']==40702
    assert q1['historical_not_recomputed_rows']>0
    assert q2['historical_not_recomputed_rows']>0


def test_repaired_frame1_target_does_not_regress():
    out=Path(lookup[(1,'roi-bh')]['output'])
    table=pd.read_csv(out/'FINAL_DEFECTS_AND_MEASUREMENTS.csv').set_index('final_ID')
    row=table.loc['F1_FINAL_0029']
    assert int(row.final_area_detector_px2)==3469
    assert abs(float(row.max_Feret_detector_px)-189.973682184455)<1e-6


def test_W005_is_only_a_nonwork_regression_diagnostic():
    q=json.loads((BENCH/'W005_NONWORK_DIAGNOSTIC/QA.json').read_text(encoding='utf8'))
    assert q['status']=='PASS'
    assert q['scope']=='SEPARATE_NONWORK_DIAGNOSTIC_NOT_PRODUCTION_ROI'
    assert q['member_set_exact']
    assert q['all_J4_array_different_pixels']==0


@pytest.mark.parametrize('frame',[1,2])
def test_finalguard_roi_bh_is_current_code_and_independent_QA_pass(frame):
    import hashlib
    out=C.OUTPUT_ROOT/f'K8A_TWO_LEVEL_FINALGUARD_26_{frame}_ROI_BH_20261020_v2'
    if not out.is_dir():
        pytest.skip('post-guard fresh ROI-BH artifact unavailable')
    q=json.loads((out/'independent_QA/QA.json').read_text(encoding='utf8'))
    assert q['status']=='PASS' and q['errors']==[]
    assert q['BH_work_window_diff_pixels_with_repeats']==0
    assert q['J4_grouped_source_diff_pixels']==0
    assert q['final_binary_diff_pixels']==0
    manifest=json.loads((out/'source_SHA256_at_start.json').read_text(encoding='utf8'))
    by_name={Path(r['path']).name:str(r['sha256']).lower() for r in manifest}
    for file in [
        C.PROJECT_ROOT/'src/detection/two_level_roi.py',
        C.PROJECT_ROOT/'scripts/run_case03j4_fullscan.py',
        C.PROJECT_ROOT/'scripts/run_unified_raw_input.py',
    ]:
        current=hashlib.sha256(file.read_bytes()).hexdigest().lower()
        assert by_name[file.name]==current
