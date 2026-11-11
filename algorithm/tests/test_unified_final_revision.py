"""Behavior gates for the reviewed unified backend, not frozen object counts."""
import numpy as np

def test_explicit_input_always_dispatches_fresh_pipeline(monkeypatch,tmp_path):
    from scripts import run_unified_raw_input as fresh
    from scripts.run_unified_final_revision import run
    calls=[]
    monkeypatch.setattr(fresh,'run_raw',lambda path,run_id:calls.append((path,run_id)) or 'fresh')
    assert run('unique',input_path=tmp_path/'input.raw')=='fresh'
    assert calls==[((tmp_path/'input.raw').resolve(),'unique')]

def test_elongated_RAW_target_is_one_object_without_losing_sources():
    from scripts import run_case03_unified_final_detector_26_1_2 as baseline
    import pandas as pd
    rows=pd.read_csv(baseline.I/'frame26_1/end_to_end_candidate_lineage.csv',low_memory=False)
    objects,_=baseline.build_b(1,rows)
    wanted={'B:F1:B02:C0000614','B:F1:B02:C0001028','B:F1:B02:C0001273','B:F1:B02:C0001562'}
    from scripts.run_unified_final_revision import compute
    final=compute(1)[3]
    matched=[v for v in final if v['sources'] & wanted]
    assert len(matched)==1, 'RAW-connected elongated target fragmented by v2 seed fallback'
    assert wanted <= matched[0]['sources']
    assert matched[0]['mask'].sum()>827

def test_final_revision_never_overwrites_existing_release():
    import pytest
    from scripts.run_unified_final_revision import run
    with pytest.raises(FileExistsError):
        run('CASE03_UNIFIED_FINAL_DETECTOR_26_1_26_2_20261019_v2')

def test_negative_masks_veto_recovery_and_preserve_originals():
    import cv2,pandas as pd
    from scripts import run_case03_unified_final_detector_26_1_2 as old
    from scripts.run_unified_final_revision import K8A,read_png
    from src.detection.unified_raw_recovery import recover_objects
    rows=pd.read_csv(old.I/'frame26_1/end_to_end_candidate_lineage.csv',low_memory=False)
    obs,_=old.build_b(1,rows)
    raw=np.memmap(old.C.DATA_ROOT/'26 (1).raw',dtype='>u2',mode='r',shape=(9200,11276))
    ids=read_png(K8A/'frame26_1/band_id_fullres.png')
    negative={'mask':np.ones((300,300),bool),'bbox':(5150,4450,5450,4750)}
    result,audit=recover_objects(obs,raw,ids,[negative])
    assert any(x['reason']=='OTHER_OBJECT_OR_HUMAN_NEGATIVE_CONFLICT' for x in audit)
    assert len([x for x in result if x['band']==2 and not x['user_approved']])==4

def test_final_renderer_has_no_mask_contour_call():
    import ast,inspect
    from src.visualization.unified_final_boxes import render
    tree=ast.parse(inspect.getsource(render))
    names={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not names & {'drawContours','polylines','findContours'}

def test_two_near_dark_spots_without_RAW_connection_are_not_merged():
    import cv2
    from scripts.run_case03_unified_final_detector_26_1_2 import item
    from src.detection.unified_raw_recovery import recover_objects
    raw=np.full((256,256),1000,np.float32)
    cv2.circle(raw,(105,128),7,800,-1);cv2.circle(raw,(135,128),7,800,-1)
    a=item(np.ones((3,3),bool),(104,127,107,130),'B_SOURCE',['a'],1)
    b=item(np.ones((3,3),bool),(134,127,137,130),'B_SOURCE',['b'],1)
    output,audit=recover_objects([a,b],raw,np.ones(raw.shape,np.uint8))
    assert len(output)==2
    assert audit[0]['reason']=='NO_SHARED_RAW_COMPONENT_COVERING_ALL_SEEDS'

def test_approved_mask_cannot_be_expanded_by_RAW_recovery():
    from scripts.run_case03_unified_final_detector_26_1_2 import item
    from src.detection.unified_raw_recovery import recover_objects
    obj=item(np.ones((3,3),bool),(100,100,103,103),'B_APPROVED',['known'],1,approval=True)
    raw=np.full((256,256),1000,np.uint16);raw[90:110,90:110]=500
    result,audit=recover_objects([obj],raw,np.ones(raw.shape,np.uint8))
    assert not audit and np.array_equal(result[0]['mask'],obj['mask'])

def test_display_rectangle_does_not_define_area():
    from src.detection.case03i_size_grade import max_feret_centers_px
    mask=np.eye(20,dtype=bool)
    y,x=np.where(mask)
    assert mask.sum()==20 and mask.size==400
    assert abs(max_feret_centers_px(np.column_stack([x,y]))-np.sqrt(2)*19)<1e-6
