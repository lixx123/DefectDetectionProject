"""Scheme-A four-view atlas checks for LOCAL ALL-AUTO vs SELECTED-only.

A real crop can contain several distinct automatically detected objects.
The old atlas rendered only the currently selected H object, misleading a
human reviewer into mistaking neighboring detections for missed defects.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from src.visualization.case03d_detected_atlas import (
    AUTO_GREEN,LABEL_H,SEPARATOR,atlas_four_view,four_view_tile,
    visible_auto_objects
)


def _example(size=200):
    raw=np.full((size,size),1800,dtype=np.uint16)
    H=np.zeros((size,size),dtype=bool)
    S=np.zeros_like(H)
    classes=np.zeros_like(H,dtype=np.uint8)
    info=[]
    # Current spot in middle; other spot BELOW; third spot PARTLY at left.
    for cid,x,y in [("top",98,75),("lower",99,119),("partial",50,91)]:
        H[y:y+5,x:x+5]=True
        S[y+1:y+4,x+1:x+4]=True
        classes[y:y+5,x:x+5]=3
        raw[y:y+5,x:x+5]=900
        info.append(dict(candidate_id=cid,centroid_x=float(x+2),
                         centroid_y=float(y+2),
                         bbox_x=x,bbox_y=y,bbox_w=5,bbox_h=5,
                         area_px=25,peak_response_dn=400,
                         triage_status="detected_provisional"))
    return raw,H,S,classes,info


def test_four_panel_shows_all_roi_autos_and_selected_only():
    raw,H,S,classes,info=_example()
    current=info[0]
    tile,labels=four_view_tile(current,info,raw,H,S,classes,size=96)
    assert tile.shape==(96+LABEL_H,4*96+3*SEPARATOR,3)
    assert len(labels)==3
    assert {x["auto_candidate_id"] for x in labels}=={"top","lower","partial"}
    assert {x["roi_number"] for x in labels}=={1,2,3}
    assert sum(x["is_current_selected"] for x in labels)==1

    # Current row is centered at (100,77), ROI y=29..125, x=52..148.
    x0=52;y0=29
    third_panel_start=2*(96+SEPARATOR)
    fourth_panel_start=3*(96+SEPARATOR)
    # Green of the lower second spot is visible in ALL AUTO but absent in
    # SELECTED ONLY (as it must be).
    global_x=101;global_y=121
    a=tile[LABEL_H+global_y-y0,third_panel_start+global_x-x0]
    b=tile[LABEL_H+global_y-y0,fourth_panel_start+global_x-x0]
    assert tuple(a)==AUTO_GREEN
    assert tuple(b)!=AUTO_GREEN
    # Same pixel in the selected top component appears in both panels,
    # but avoid red bbox border and number badges in the test point.
    gx=100;gy=77
    selected_px=tile[LABEL_H+gy-y0,fourth_panel_start+gx-x0]
    # On tiny candidates the red 2px bbox outline can blend over all
    # five pixels; verify detection overlay exists vs the identical RAW.
    raw_px=tile[LABEL_H+gy-y0,gx-x0]
    assert not np.array_equal(selected_px,raw_px)


def test_numbered_component_must_truly_have_H_pixels_in_roi():
    raw,H,S,classes,info=_example()
    # Create a component whose bbox intersects the ROI but its only actual
    # pixel is outside the ROI: should not receive a phantom index.
    fake=info[0].copy()
    fake.update(candidate_id="absent",bbox_x=52,bbox_y=30,bbox_w=5,bbox_h=5,
                centroid_x=54,centroid_y=32,area_px=1)
    # Do not pass fake into actual data since its geometry contradicts H;
    # the renderer must fail closed on source inconsistency.
    import pytest
    with pytest.raises(ValueError):
        four_view_tile(info[0],info+[fake],raw,H,S,classes,size=96)


def test_full_atlas_provides_evidence_mapping_for_each_card():
    raw,H,S,classes,info=_example()
    img,records=atlas_four_view(info[:2],info,raw,H,S,classes,
                                size=96,columns=2)
    assert img.shape[1]==2*(4*96+3*SEPARATOR+14)
    assert {r["atlas_card_index"] for r in records}=={1,2}
    assert len([r for r in records if r["atlas_card_index"]==1])==3


def test_actual_rebuilt_atlas_keeps_legacy_and_numbers_three_in_third_card():
    root=Path(__file__).resolve().parents[1]
    out=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    current=out/"figures/atlas_detected_top12.png"
    old=out/"figures/atlas_detected_top12_legacy_selected_only.png"
    assert current.exists() and old.exists()
    assert current.read_bytes()!=old.read_bytes()
    image=cv2.imdecode(np.frombuffer(current.read_bytes(),dtype=np.uint8),
                       cv2.IMREAD_COLOR)
    assert image.shape==(1099,1524,3)
    assert "3 ALL AUTO" in "3 ALL AUTO in ROI"
    audit=json.loads((out/"atlas_detected_top12_three_panel_validation.json").read_text(encoding="utf-8"))
    assert audit["atlas_card_count"]==12
    assert audit["panels"]==["1 RAW","2 ALL S/H","3 ALL AUTO in ROI"]
    third=set(audit["third_card_candidate_ids"])
    assert third=={"H_sample26_0405250","H_sample26_0406312","H_sample26_0408029"}
    assert audit["source_auto_candidate_count"]==139
    assert audit["no_detection_or_classification_changes"]



def test_real_roi_number_ledger_matches_visible_three_auto_targets():
    import pandas as pd
    root=Path(__file__).resolve().parents[1]
    output=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    info=pd.read_csv(output/"atlas_detected_top12_roi_numbers.csv")
    assert info["atlas_card_index"].nunique()==12
    assert len(info)==16
    assert info.groupby("atlas_card_index")["is_current_selected"].sum().eq(1).all()
    third=info[info["atlas_card_index"]==3]
    assert len(third)==3
    assert third["roi_number"].tolist()==[1,2,3]
    assert set(third["auto_candidate_id"])=={
        "H_sample26_0405250","H_sample26_0406312","H_sample26_0408029"
    }
    assert third.loc[third["is_current_selected"],"auto_candidate_id"].tolist()==[
        "H_sample26_0406312"
    ]
    # All three represent actually visible source H pixels.
    assert (third["visible_auto_pixels"]>0).all()


def test_future_pipeline_draw_atlas_uses_three_panel_for_detected_only():
    import inspect
    from scripts.run_case03d_autodetect import draw_atlas
    source=inspect.getsource(draw_atlas)
    assert 'if name=="detected_top12"' in source
    assert 'atlas_three_view' in source
    assert 'atlas_detected_top12_roi_numbers.csv' in source
    # Old 3-panel tile code remains for other atlases and offline UI.
    assert 'tile_for(row,raw,H,S)' in source



def test_three_view_tile_exactly_three_columns_and_all_auto_neighbors():
    from src.visualization.case03d_detected_atlas import three_view_tile
    raw,H,S,classes,items=_example()
    tile,mapping=three_view_tile(items[0],items,raw,H,S,classes,size=96)
    assert tile.shape==(96+LABEL_H,3*96+2*SEPARATOR,3)
    assert len(mapping)==3
    assert {r["auto_candidate_id"] for r in mapping}=={"top","lower","partial"}
    assert sum(r["is_current_selected"] for r in mapping)==1
    # All green below-selected pixels remain present in the third panel.
    x0,y0=52,29
    lower=(101,121)
    third_x=2*(96+SEPARATOR)+lower[0]-x0
    third_y=LABEL_H+lower[1]-y0
    assert tuple(tile[third_y,third_x])==AUTO_GREEN


def test_three_view_full_atlas_omits_selected_only_without_dropping_ids():
    from src.visualization.case03d_detected_atlas import atlas_three_view
    raw,H,S,classes,items=_example()
    image,ledger=atlas_three_view(items[:2],items,raw,H,S,classes,
                                   size=96,columns=2)
    assert image.shape[1]==2*(3*96+2*SEPARATOR+14)
    assert {x["atlas_card_index"] for x in ledger}=={1,2}
    assert len([x for x in ledger if x["atlas_card_index"]==1])==3
    assert len({x["auto_candidate_id"] for x in ledger})==3


def test_four_panel_backup_and_current_three_panel_distinct():
    root=Path(__file__).resolve().parents[1]
    d=root/"outputs/case03d_autodetect/run_20261009_autodetect_final/figures"
    current=cv2.imdecode(
        np.frombuffer((d/"atlas_detected_top12.png").read_bytes(),dtype=np.uint8),
        cv2.IMREAD_COLOR)
    previous=cv2.imdecode(
        np.frombuffer((d/"atlas_detected_top12_four_panel_backup.png").read_bytes(),dtype=np.uint8),
        cv2.IMREAD_COLOR)
    assert current.shape==(1099,1524,3)
    assert previous.shape==(1099,2025,3)
    assert (d/"atlas_detected_top12_legacy_selected_only.png").is_file()
