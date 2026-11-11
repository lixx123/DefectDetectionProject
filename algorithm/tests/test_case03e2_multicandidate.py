"""Multiseed automatic candidate engine: synthetic and real audit acceptance.

Synthetic fixtures are independent of sample26 annotations. Real ten human
polygons are used only after running a no-click detection, NEVER training or
fitting thresholds.
"""
from __future__ import annotations
import inspect
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
import pytest

from src.detection.case03e2_multicandidate import (
    FusionConfig,detect_window,
    extract_h_proposals,extract_local_proposals,
)
from src.detection.case03e2_window_stitch import (
    serialize_bbox_binary,read_bbox_binary,exact_overlap_global,
    deduplicate_cross_window
)
from scripts.run_case03e2_multicandidate_fusion import fixed_grid_window

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03e2/run_20261010_multiseed_fusion_v5"


def sample_two_spots():
    base=np.full((256,256),2200,dtype=np.uint16)
    cv2.circle(base,(68,73),9,1860,-1)
    cv2.circle(base,(136,171),12,1910,-1)
    fused=np.maximum(2200-base.astype(np.int32),0).astype(np.uint16)
    S=fused>=230
    H=fused>=170
    return base,H,S,fused


def test_two_distinct_synthetic_spots_both_automatically_discovered():
    raw,H,S,fused=sample_two_spots()
    x=detect_window(raw,H,S,fused)
    assert x["num_source_proposals"]>=6
    objects=[o for o in x["objects"] if o.status=="provisional_fused"]
    assert len(objects)==2
    assert objects[0].mask[73,68] ^ objects[0].mask[171,136]
    assert objects[1].mask[73,68] ^ objects[1].mask[171,136]
    assert all(o.area_px>120 for o in objects)
    assert all(o.source_count==3 for o in objects)
    assert all("H170_230" in o.sources for o in objects)
    assert all(not o.flags for o in objects)


def test_H_only_strong_microspot_survives_even_without_Gaussian_support():
    raw=np.full((256,256),2200,dtype=np.uint16)
    H=np.zeros_like(raw,dtype=bool)
    H[110:112,90:93]=True
    S=H.copy()
    fused=np.zeros_like(raw)
    fused[H]=340
    found=detect_window(raw,H,S,fused)
    assert len(found["H_audit"])==1
    assert found["H_audit"][0]["promoted_to_fusion_pool"]
    honly=[o for o in found["objects"] if o.H_only and o.area_px>0]
    assert len(honly)==1
    assert honly[0].area_px==6
    assert honly[0].status=="needs_review_H_only"
    assert (honly[0].mask[110:112,90:93]).all()


def test_H_high_peak_single_pixel_retained_separately_from_local_method_noise():
    raw=np.full((256,256),2200,dtype=np.uint16)
    H=np.zeros_like(raw,dtype=bool);H[77,88]=True;H[100,100]=True
    fused=np.zeros_like(raw);fused[77,88]=350;fused[100,100]=232
    S=np.zeros_like(H);S[77,88]=True;S[100,100]=True
    result=detect_window(raw,H,S,fused)
    assert len(result["H_audit"])==2
    assert result["H_low_area_audit_only_count"]==1
    assert result["H_source_proposal_count"]==1
    assert any(o.area_px==1 and o.H_only and o.status=="needs_review_H_only" for o in result["objects"])
    # Weak 1px H source was NOT silently deleted: audit and frozen H mask persist.
    assert any(not a["promoted_to_fusion_pool"] and
               a["area_px"]==1 for a in result["H_audit"])


def test_local_Gaussian_and_closing_discover_new_spot_even_if_H_empty():
    raw=np.full((256,256),2200,dtype=np.uint16)
    cv2.circle(raw,(118,103),14,1840,-1)
    H=np.zeros_like(raw,dtype=bool);S=H.copy();fused=np.zeros_like(raw)
    found=detect_window(raw,H,S,fused)
    assert found["H_source_proposal_count"]==0
    assert any("gaussian22" in o.sources and
               o.mask[103,118] for o in found["objects"])
    assert any("closing61" in o.sources and
               o.mask[103,118] for o in found["objects"])
    assert any(o.area_px>100 and not o.H_only for o in found["objects"])


def test_dark_background_bridge_is_flagged_not_silently_joined():
    raw=np.full((256,256),2200,dtype=np.uint16)
    cv2.rectangle(raw,(0,170),(255,245),1480,-1)
    cv2.circle(raw,(67,52),10,1850,-1)
    cv2.circle(raw,(166,95),10,1800,-1)
    fused=np.maximum(2200-raw.astype(np.int32),0).astype(np.uint16)
    H=fused>=170;S=fused>=230
    out=detect_window(raw,H,S,fused)
    assert any(o.status.startswith("needs_review")
               for o in out["objects"])
    top=[o for o in out["objects"] if o.mask[52,67]]
    mid=[o for o in out["objects"] if o.mask[95,166]]
    assert top and mid
    assert top[0].object_id!=mid[0].object_id
    assert not top[0].mask[95,166]
    assert not mid[0].mask[52,67]


def test_H_threshold_seed_must_not_be_outside_H():
    raw,H,S,fused=sample_two_spots()
    S=np.zeros_like(H)
    S[100,100]=True
    with pytest.raises(ValueError):
        detect_window(raw,H,S,fused)


def test_exact_bbox_pack_and_unpack_in_raw_integer_pixels():
    region=np.zeros((256,256),bool)
    region[80:100,110:130]=True
    region[85:91,115:123]=False
    packed=serialize_bbox_binary(region,(800,1200))
    assert packed["bbox_global_xywh"]==[910,1280,20,20]
    assert packed["exact_area_px"]==352
    assert np.array_equal(read_bbox_binary(packed),region[80:100,110:130])


def _global_record(name,window,mask,origin,center):
    return {
        "window_id":window,
        "local_object_id":name,
        "center_raw_x":center[0],
        "center_raw_y":center[1],
        "sources":["H170_230"],
        "fusion_status":"provisional_H_only",
        **serialize_bbox_binary(mask,origin)
    }


def test_cross_window_duplicate_uses_exact_overlap_and_keeps_nearby_independent():
    a=np.zeros((256,256),bool);b=np.zeros((256,256),bool);c=np.zeros((256,256),bool)
    a[80:90,100:110]=True             # global x=300..309, y=380..389
    b[80:90,50:60]=True               # global x=300..309 if 250 origin
    c[80:90,77:87]=True               # distinct nearby x=327..336
    rows=[
       _global_record("A","W1",a,(200,300),(304.5,384.5)),
       _global_record("B","W2",b,(250,300),(304.5,384.5)),
       _global_record("C","W2",c,(250,300),(331.5,384.5))
    ]
    dup,edges=deduplicate_cross_window(rows)
    assert len(dup)==2
    assert len(edges)==1
    assert {tuple(d["bbox_global_xywh"]) for d in dup}=={
        (300,380,10,10),(327,380,10,10)}
    assert sorted(x["exact_area_px"] for x in dup)==[100,100]
    assert sorted(len(x["member_window_object_ids"]) for x in dup)==[1,2]


def test_cross_window_not_duplicate_by_bbox_only_or_centroid_proximity():
    x=np.zeros((256,256),bool);y=x.copy()
    x[40:45,60:65]=True
    y[45:50,60:65]=True
    rec=[
        _global_record("A","W1",x,(0,0),(62.,42.)),
        _global_record("B","W2",y,(0,0),(62.,47.))
    ]
    assert exact_overlap_global(rec[0],rec[1])==0
    joined,edges=deduplicate_cross_window(rec)
    assert len(joined)==2 and not edges


def test_fixed_grid_has_shared_region_for_manual007_008():
    shape=(9200,11276)
    first=fixed_grid_window(11174,60,shape)
    second=fixed_grid_window(11189,126,shape)
    assert first==second==(11020,0,11276,256)
    third=fixed_grid_window(8848,8742,shape)
    assert third[0]<=8848<third[2]
    assert third[1]<=8742<third[3]


def test_engine_has_no_manually_clicked_seed_or_polygon_argument():
    params=inspect.signature(detect_window).parameters
    assert set(params)=={"raw","H","S","fused","cfg"}
    source=inspect.getsource(detect_window)
    assert "manual_polygon" not in source
    assert "clicked_xy" not in source
    script=inspect.getsource(
        __import__("scripts.run_case03e2_multicandidate_fusion",
                   fromlist=["run"]).run
    )
    segment=script[script.index("detected=detect_window("):
                   script.index("        props=detected")]
    assert "annotations[" not in segment
    assert "polygon" not in segment


def test_real_v3_007_008_are_distinct_inside_one_auto_window():
    expected=pd.read_csv(OUT/"ten_manual_targets_posthoc_evaluation.csv")
    assert len(expected)==10
    a=expected[expected.manual_target_id.isin(
        ["RAW26_MANUAL_007","RAW26_MANUAL_008"])]
    assert len(a)==2 and a.window_id.nunique()==1
    assert a.top_fused_object_id.nunique()==2
    assert a.top_fused_object_status.eq("provisional_fused").all()
    assert (a.top_fused_mask_coverage>.80).all()


def test_real_v3_bad_cases_remain_explicitly_unresolved_not_measured_truth():
    q=pd.read_csv(OUT/"ten_manual_targets_posthoc_evaluation.csv")
    assert q.loc[q.manual_target_id=="RAW26_MANUAL_003",
                 "top_fused_object_status"].iloc[0].startswith("needs_review")
    assert q.loc[q.manual_target_id=="RAW26_MANUAL_010",
                 "top_fused_object_status"].iloc[0].startswith("needs_review")
    assert q.loc[q.manual_target_id=="RAW26_MANUAL_004",
                 "top_fused_object_status"].iloc[0].startswith("needs_review")
    q9=q[q.manual_target_id=="RAW26_MANUAL_009"].iloc[0]
    assert q9["top_fused_mask_coverage"]<.20
    assert q9["historical_H_coverage"]>=q9["provisional_safe_union_coverage"]
    assert q["manual_polygon_used_to_choose_any_candidate"].eq(False).all()
    assert q["manual_click_used_as_any_detector_seed"].eq(False).all()
    assert q["coverage_is_not_physical_accuracy"].eq(True).all()


def test_real_v3_all_raw_H_provenance_and_labels_roundtrip():
    root=OUT
    with (root/"all_window_objects_exact.jsonl").open(encoding="utf-8") as f:
        objects=[json.loads(v) for v in f]
    source_H=pd.read_csv(root/"all_original_H_components_in_windows.csv")
    windows=pd.read_csv(root/"window_summary.csv")
    assert len(windows)==9
    assert len(source_H)==1569
    assert int((~source_H.promoted_to_fusion_pool).sum())==979
    assert len(objects)>=400
    for row in [objects[0],objects[67],objects[-1]]:
        assert row["exact_area_px"]==read_bbox_binary(row).sum()
        assert not row["physical_defect_truth"]
        assert row["object_plane_um_per_px"] is None
    assert len(list((root/"masks").glob("*_labels.npz")))==9
    assert len(list((root/"figures").glob("*_5panel_ALL_AUTO.png")))==9
    manifest=json.loads((root/"source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["all_sources_unchanged"]
    assert manifest["inputs_before"]==manifest["inputs_after"]



def test_v5_acceptance_has_no_fabricated_all_pass():
    p=OUT/"acceptance.json"
    assert p.is_file()
    value=json.loads(p.read_text(encoding="utf-8"))
    assert value["counts"]=={"PASS":8,"FAIL":2,"DEFERRED":4}
    assert value["candidate_total"]==591
    assert value["review_candidates"]==583
    assert value["status"]!="ALL_ENGINEERING_GATES_PASS"
    fail={g["gate"] for g in value["gates"] if g["status"]=="FAIL"}
    assert fail=={
        "G09_009_safe_only_nonregression_vs_historic",
        "G10_004_safe_contour_improves_vs_original_H"
    }
    assert (OUT/"uncertain_candidates_top80_for_human.csv").is_file()
    assert len(pd.read_csv(OUT/"uncertain_candidates_top80_for_human.csv"))==80


def test_v5_full_visual_and_main_entry_and_config_snapshot():
    from config import user_config as cfg
    from main import main,parse_args
    import inspect
    assert cfg.CASE03E2_WINDOW_SIZE_PX==256
    assert cfg.CASE03E2_GRID_STRIDE_PX==128
    source=inspect.getsource(main)
    assert 'args.case.lower() in {"3e2","3e-2"}' in source
    assert "scripts.run_case03e2_multicandidate_fusion" in source
    assert (OUT/"figures/E2_all_9_windows_contact_sheet.png").is_file()
    assert (OUT/"CASE03E2_TECHNICAL_REPORT.md").is_file()
    snapshot=json.loads((OUT/"config_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["fusion"]["background_high_floor_dn"]==65.
    assert snapshot["fusion"]["background_low_floor_dn"]==24.
    assert snapshot["physical_grade_thresholds"] is None
    assert snapshot["object_plane_um_per_pixel"] is None
