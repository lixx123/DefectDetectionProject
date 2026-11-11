import numpy as np
import pytest
from src.detection.two_level_roi import build_plan, halo_requirements, compute_fused, require_computed_response
from scripts.run_case03j4_fullscan import tiles, halo_rect


def geometry(shape=(1024,1024)):
    return {'status':'AUTOMATIC_CANDIDATE_REVIEW_REQUIRED','bands':[{
        'band_id':1,'validation_flags':[], 'top_line_y_at_x0':400,
        'bottom_line_y_at_x0':500,'top_line_slope_y_per_x':0.,
        'bottom_line_slope_y_per_x':0.,
        'top_edge_quality':{'linear_model_used':True,'edge_samples':30,
                            'edge_median_residual_px':1.,'edge_p90_residual_px':2.},
        'bottom_edge_quality':{'linear_model_used':True,'edge_samples':30,
                               'edge_median_residual_px':1.,'edge_p90_residual_px':2.}}]}


def test_normal_plan_expands_core_and_skips_tiles():
    p=build_plan((1024,1024),geometry())
    assert p['roi_mode']=='K8A_WORK_ROI'
    assert 0<len(p['tiles'])<16
    assert p['algorithm_halo_px']>=93
    assert p['detection_rectangles'][0][1]<400-p['algorithm_halo_px']


@pytest.mark.parametrize('failure',['empty','fit','flags','reverse','outside','count','nan','nan_quality'])
def test_untrusted_geometry_automatically_falls_back(failure):
    loc=geometry();b=loc['bands'][0]
    if failure=='empty':loc['bands']=[]
    if failure=='fit':b['top_edge_quality']['linear_model_used']=False
    if failure=='flags':b['validation_flags']=['INSUFFICIENT_COLUMN_GEOMETRY_SAMPLES']
    if failure=='reverse':b['bottom_line_y_at_x0']=300
    if failure=='outside':b['bottom_line_y_at_x0']=2000
    if failure=='count':loc['bands']=loc['bands']*20
    if failure=='nan':b['top_line_y_at_x0']=float('nan')
    if failure=='nan_quality':b['top_edge_quality']['edge_p90_residual_px']=float('nan')
    p=build_plan((1024,1024),loc)
    assert p['roi_mode']=='FULL_FRAME_FALLBACK' and p['fallback_reasons']
    assert len(p['tiles'])==16


def test_original_grid_and_complete_partial_tile_context():
    p=build_plan((1024,1024),geometry());grid=tiles((1024,1024))
    for t in p['tiles']:
        assert t in grid
        assert halo_rect(t['core_xyxy'],(1024,1024),64) in p['response_rectangles']
    assert sum((t['core_xyxy'][2]-t['core_xyxy'][0])*(t['core_xyxy'][3]-t['core_xyxy'][1]) for t in p['tiles'])==p['legal_source_pixels']


def test_roi_blackhat_exact_at_all_consumed_pixels(tmp_path):
    rng=np.random.default_rng(91);raw=rng.integers(0,4096,(2048,1024),dtype=np.uint16)
    p=build_plan(raw.shape,geometry())
    full,fm=compute_fused(raw,tmp_path/'full.npy')
    roi,rm=compute_fused(raw,tmp_path/'roi.npy',p['response_rectangles'])
    from config import user_config as C
    from src.detection.blackhat import black_hat_uint16
    direct=np.maximum.reduce([black_hat_uint16(raw,k,'ellipse') for k in C.BLACKHAT_KERNEL_SIZES_PX])
    assert np.array_equal(direct,full)
    for x0,y0,x1,y1 in p['response_rectangles']:
        assert np.array_equal(full[y0:y1,x0:x1],roi[y0:y1,x0:x1])
    assert rm['blackhat_input_pixels_with_repeats']<fm['blackhat_input_pixels_with_repeats']


def test_halo_accounts_for_composed_filter_support():
    r=halo_requirements()
    assert r['BH_close_two_operations']>=30
    assert r['Gaussian22_median_and_smoothing']>=93
    assert r['Closing61_median_and_smoothing']>=65
    assert r['K8D_raw_context']>=64


def test_no_band_input_really_runs_full_detection_not_empty_work_filter(tmp_path,monkeypatch):
    import json
    from config import user_config as C
    from scripts.run_two_level_unified import run_raw
    monkeypatch.setattr(C,'RAW_HEIGHT',1024);monkeypatch.setattr(C,'RAW_WIDTH',1024)
    monkeypatch.setattr(C,'OUTPUT_ROOT',tmp_path);monkeypatch.setattr(C,'DATA_ROOT',tmp_path)
    path=tmp_path/'synthetic.raw';path.write_bytes(np.full((1024,1024),1000,dtype='>u2').tobytes())
    out=run_raw(path,'fallback','roi-bh')
    a=json.loads((out/'acceptance.json').read_text(encoding='utf8'))
    assert a['roi_mode']=='FULL_FRAME_FALLBACK'
    assert a['actual_fresh_J4_tiles']==a['full_tiles']==16
    assert not a['K8B_executed']
    assert a['status']=='FULL_FRAME_FALLBACK_MANUAL_GEOMETRY_REVIEW_REQUIRED'
    assert (out/'upstream_J4/fresh/tile_masks/T000_000.npz').exists()


def test_sparse_J5_rejects_changed_global_grid(tmp_path):
    import json
    from scripts.run_case03j5_global_merge import load_input_rows
    from src.detection.case03j5_seam_match import J5Config
    (tmp_path/'run_status.json').write_text(json.dumps({'stage':'J4_COMPLETE','planned_tiles':1,'completed_tiles':1}))
    (tmp_path/'scheduled_tiles.json').write_text(json.dumps([{'tile_id':'T000_000','ix':0,'iy':0,'core_xyxy':[1,0,256,256]}]))
    with pytest.raises(ValueError,match='schedule/global grid'):load_input_rows(tmp_path,J5Config())


def test_uncomputed_blackhat_sentinel_fails_closed():
    require_computed_response(np.array([[0,4095]],dtype=np.uint16),'unit-test-valid')
    with pytest.raises(RuntimeError,match='Uncomputed BlackHat sentinel'):
        require_computed_response(np.array([[0,65535]],dtype=np.uint16),'unit-test-invalid')


def test_j4_rejects_uncomputed_blackhat_before_detection(tmp_path):
    from scripts.run_case03j4_fullscan import run_tile
    raw=np.zeros((256,256),dtype=np.uint16)
    fused=np.full((256,256),65535,dtype=np.uint16)
    tile={'tile_id':'T000_000','ix':0,'iy':0,'core_xyxy':[0,0,256,256]}
    with pytest.raises(RuntimeError,match='J4 work window'):
        run_tile(tile,raw,fused,None,None,None,None,64,tmp_path,image_enabled=False)
