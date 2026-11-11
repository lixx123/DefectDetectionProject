"""Case03-D-R2 triage and exact pixel contour regression."""
from __future__ import annotations
import base64
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.detection.candidate_autodecision import classify_candidates,inspect_reviewed_against_triage
from src.detection.candidate_contour_export import describe_exact_contour


def make_features():
    return pd.DataFrame([
        # credible interior compact spot: auto detection
        dict(candidate_id="spot",area_px=120,peak_response_dn=350,bbox_w=14,bbox_h=15,
             bbox_aspect_ratio=14/15,bbox_fill_ratio=.57,linearity_proxy=.12,
             near_band_transition=False,raw_reference_valid=True,raw_delta_dn=110,
             touches_border=False,seed_area_px=60,core_component_count=2),
        # high peak vertical stripe at black band transition: artifact-like
        dict(candidate_id="stripe",area_px=1200,peak_response_dn=800,bbox_w=12,bbox_h=200,
             bbox_aspect_ratio=.06,bbox_fill_ratio=.5,linearity_proxy=.99,
             near_band_transition=True,raw_reference_valid=False,raw_delta_dn=np.nan,
             touches_border=False,seed_area_px=600,core_component_count=1),
        # weak short actual-style spot, uncertain
        dict(candidate_id="weak",area_px=16,peak_response_dn=250,bbox_w=5,bbox_h=7,
             bbox_aspect_ratio=5/7,bbox_fill_ratio=.46,linearity_proxy=.5,
             near_band_transition=True,raw_reference_valid=False,raw_delta_dn=np.nan,
             touches_border=False,seed_area_px=3,core_component_count=1),
        # one-pixel low response: noise-like but still retained
        dict(candidate_id="tiny",area_px=1,peak_response_dn=231,bbox_w=1,bbox_h=1,
             bbox_aspect_ratio=1,bbox_fill_ratio=1,linearity_proxy=np.nan,
             near_band_transition=False,raw_reference_valid=True,raw_delta_dn=5,
             touches_border=False,seed_area_px=1,core_component_count=1),
        # strong line inside the frame: auto detection
        dict(candidate_id="line",area_px=150,peak_response_dn=320,bbox_w=90,bbox_h=8,
             bbox_aspect_ratio=90/8,bbox_fill_ratio=.21,linearity_proxy=.97,
             near_band_transition=False,raw_reference_valid=True,raw_delta_dn=45,
             touches_border=False,seed_area_px=60,core_component_count=2),
        # strong spot but RAW delta negative: must abstain
        dict(candidate_id="raw_fail",area_px=130,peak_response_dn=360,bbox_w=13,bbox_h=15,
             bbox_aspect_ratio=13/15,bbox_fill_ratio=.67,linearity_proxy=.11,
             near_band_transition=False,raw_reference_valid=True,raw_delta_dn=-12,
             touches_border=False,seed_area_px=50,core_component_count=1),
        # one-pixel high peak should remain reviewable
        dict(candidate_id="tiny_high",area_px=1,peak_response_dn=330,bbox_w=1,bbox_h=1,
             bbox_aspect_ratio=1,bbox_fill_ratio=1,linearity_proxy=np.nan,
             near_band_transition=False,raw_reference_valid=False,raw_delta_dn=np.nan,
             touches_border=False,seed_area_px=1,core_component_count=1),
    ])


def test_tristate_deterministic_retains_every_H_candidate():
    inp=make_features()
    d=classify_candidates(inp)
    assert len(d)==len(inp)
    assert (d["candidate_id"].to_numpy()==inp["candidate_id"].to_numpy()).all()
    states=dict(zip(d["candidate_id"],d["triage_status"]))
    assert states=={
        "spot":"detected_provisional","stripe":"noise_like_retained",
        "weak":"uncertain_review","tiny":"noise_like_retained",
        "line":"detected_provisional","raw_fail":"uncertain_review",
        "tiny_high":"uncertain_review"
    }
    assert d["candidate_retained"].all()
    assert d.set_index("candidate_id").loc["stripe","band_edge_artifact_signature"]


def test_no_label_leakage_from_existing_CSV_label_and_order():
    original=make_features()
    a=classify_candidates(original)
    original["manual_label"]=["confirmed_dark_spot"]*len(original)
    original["priority_rank"]=np.arange(len(original))
    b=classify_candidates(original)
    pd.testing.assert_frame_equal(a,b)


def test_invalid_reference_cannot_be_used_for_auto():
    f=make_features()
    f.loc[f["candidate_id"]=="spot","raw_reference_valid"]=False
    f.loc[f["candidate_id"]=="spot","raw_delta_dn"]=np.nan
    r=classify_candidates(f)
    assert r.set_index("candidate_id").loc["spot","triage_status"]=="uncertain_review"
    f.loc[f["candidate_id"]=="spot","raw_reference_valid"]=True
    with pytest.raises(ValueError,match="valid RAW"):
        classify_candidates(f)


def test_bad_candidate_ID_and_nonphysical_geometry_rejected():
    f=make_features()
    f.loc[1,"candidate_id"]="spot"
    with pytest.raises(ValueError,match="unique"):
        classify_candidates(f)
    f=make_features()
    f.loc[0,"bbox_fill_ratio"]=1.5
    with pytest.raises(ValueError,match="nonphysical"):
        classify_candidates(f)


def test_exact_contour_matches_only_target_component_not_other_mask_pixels():
    H=np.zeros((35,45),dtype=bool)
    H[3:7,5:9]=True           # target 4x4=16px
    H[4,7]=False               # target 15px
    H[9:11,10:12]=True        # second nearby but separate
    row=dict(candidate_id="H_test_1",bbox_x=5,bbox_y=3,bbox_w=4,bbox_h=4,
             area_px=15,centroid_x=6.5,centroid_y=4.5,peak_response_dn=341,
             triage_status="detected_provisional",morphology_hint="spot_like")
    record,mask,(x,y,w,h)=describe_exact_contour(H,row)
    assert record["candidate_id"]==row["candidate_id"]
    assert int(mask.sum())==15
    packed=np.frombuffer(base64.b64decode(record["bbox_binary_mask_base64"]),dtype=np.uint8)
    restored=np.unpackbits(packed,bitorder="little")[:w*h].reshape(h,w)
    np.testing.assert_array_equal(restored,mask)
    assert all(x<=pt[0]<=x+w-1 and y<=pt[1]<=y+h-1
               for p in record["boundary_contours"] for pt in p["xy"])


def test_single_pixel_has_exact_pixel_mask_not_fake_polygon():
    H=np.zeros((7,7),bool)
    H[4,2]=True
    row=dict(candidate_id="one",bbox_x=2,bbox_y=4,bbox_w=1,bbox_h=1,
             area_px=1,centroid_x=2.,centroid_y=4.,peak_response_dn=270,
             triage_status="uncertain_review",morphology_hint="unclassified")
    d,mask,box=describe_exact_contour(H,row)
    assert box==(2,4,1,1)
    assert d["nonpolygon_1px_or_line_mask"]
    assert d["exact_pixel_area"]==1


def test_reviewed_diagnostic_group_counts_not_full_image_rates():
    states=classify_candidates(make_features())
    d=inspect_reviewed_against_triage(states,{
        "spot":"confirmed_dark_spot","weak":"confirmed_dark_spot",
        "tiny":"background_artifact","stripe":"background_artifact"
    })
    assert sum(x["count"] for x in d)==4
    assert all("not image recall" in x["interpretation"] for x in d)


def test_integrated_case03d_auto_output_preserves_all_candidacy():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    assert run.is_dir()
    summary=json.loads((run/"summary.json").read_text(encoding="utf-8"))
    assert summary["source_candidate_count"]==88043
    assert summary["source_H_mask_pixels"]==311790
    assert summary["candidate_counts"]=={
        "detected_provisional":139,"uncertain_review":6685,"noise_like_retained":81219}
    assert summary["class_pixel_counts"]=={
        "detected_provisional":36719,"uncertain_review":74285,"noise_like_retained":200786}
    assert summary["exact_contoured_regions"]==6824
    assert summary["no_candidate_deleted"]
    assert not summary["independent_holdout_available"]
    full=pd.read_csv(run/"candidate_decisions_full.csv",
                     usecols=["candidate_id","triage_status","area_px"],low_memory=False)
    assert full["candidate_id"].is_unique
    assert len(full)==88043
    assert int(full["area_px"].sum())==311790
    assert len(pd.read_csv(run/"detected_provisional.csv"))==139
    assert len(pd.read_csv(run/"uncertain_review_top500.csv"))==500
    assert len(pd.read_csv(run/"uncertain_review_full.csv"))==6685


def test_exact_class_status_map_fully_covers_original_case03b_H_binary_pixels():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    source=root/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_H_TL170_TH230.npz"
    from src.detection.thresholding import load_packed_mask
    H=load_packed_mask(source)
    with np.load(run/"candidate_status_map_lossless.npz") as z:
        status=z["class_map"]
    assert status.shape==H.shape==(9200,11276)
    assert np.array_equal(status>0,H)
    assert int((status==3).sum())==36719
    assert int((status==2).sum())==74285
    assert int((status==1).sum())==200786


def test_development_reference_corrections_stay_separate_from_auto_decisions():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    comp=pd.read_csv(run/"in_sample_human_comparison.csv")
    counts={(r.manual_label,r.triage_status):r["count"]
            for _,r in comp.iterrows()}
    assert counts[("confirmed_dark_spot","detected_provisional")]==10
    assert counts[("confirmed_dark_spot","uncertain_review")]==3
    assert counts[("confirmed_dark_spot","noise_like_retained")]==0
    assert counts[("background_artifact","detected_provisional")]==0
    assert counts[("background_artifact","uncertain_review")]==12
    assert counts[("background_artifact","noise_like_retained")]==30
    triage=pd.read_csv(run/"candidate_decisions_full.csv")
    index=triage.set_index("candidate_id")
    for cid in ("H_sample26_0428940","H_sample26_0425919"):
        assert index.loc[cid,"triage_status"]=="noise_like_retained"
        assert bool(index.loc[cid,"band_edge_artifact_signature"])
    assert index.loc["H_sample26_0379819","triage_status"]=="noise_like_retained"


def test_exact_export_jsonl_contains_all_6824_and_real_bitpacked_masks():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    count=0
    sampled={}
    with (run/"component_contours_exact.jsonl").open("r",encoding="utf-8") as f:
        for line in f:
            record=json.loads(line)
            count+=1
            if count in (1,3,150,2000,6824):
                sampled[record["candidate_id"]]=record
    assert count==6824
    assert len(sampled)==5
    for record in sampled.values():
        x,y,w,h=record["bbox_global_xywh"]
        decoded=np.frombuffer(base64.b64decode(record["bbox_binary_mask_base64"]),dtype=np.uint8)
        restored=np.unpackbits(decoded,bitorder="little")[:w*h]
        assert int(restored.sum())==record["exact_pixel_area"]
        assert record["triage_status"] in {"detected_provisional","uncertain_review"}
        assert not record["physical_defect_truth"]


def test_auto_preview_gallery_and_fullview_overlay_exists():
    root=Path(__file__).resolve().parents[1]
    run=root/"outputs/case03d_autodetect/run_20261009_autodetect_final"
    imgs=run/"figures"
    for basename in (
        "atlas_detected_top12.png","atlas_uncertain_top12.png",
        "atlas_band_edge_artifacts.png","atlas_human_positive_13.png",
        "atlas_human_negative_top12.png",
        "automatic_detection_centroid_locator.png",
        "auto_detected_only_full_view.png",
        "auto_detected_and_uncertain_full_view.png",
    ):
        assert (imgs/basename).is_file(),basename
    acceptance=json.loads((run/"acceptance.json").read_text(encoding="utf-8"))
    assert acceptance["engineering_status"]=="PASS"
    assert not acceptance["physical_defect_accuracy_validated"]
    snapshot=json.loads((run/"config_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["CASE03D_AUTO_MIN_AREA_PX"]==20
    assert snapshot["CASE03D_AUTO_MIN_PEAK_DN"]==270


def test_uncertain_human_review_ui_100_cases_all_new_unlabeled():
    root=Path(__file__).resolve().parents[1]
    out=root/"outputs/case03d_autodetect/run_20261009_autodetect_final/uncertain_manual_review_batch01"
    assert (out/"index.html").is_file()
    manifest=pd.read_csv(out/"review_batch_100_manifest.csv")
    assert len(manifest)==100
    assert manifest["candidate_id"].is_unique
    assert manifest["review_group"].value_counts().to_dict()=={
        "micro_high_response":20,"interior_spotlike":20,
        "elongated_line_like":20,"band_transition_context":20,
        "other_uncertain":20
    }
    already=pd.read_csv(root/"outputs/case03d/run_20261009_190000/manual_label_revision_after_review045/strict_corrected_labels.csv")
    assert not set(manifest["candidate_id"])&set(already["candidate_id"])
    for basename in manifest["image_rel"]:
        p=out/basename
        assert p.is_file() and p.stat().st_size>1000
    html=(out/"index.html").read_text(encoding="utf-8")
    assert '导出人工复核CSV' in html
    assert 'confirmed_fine_line' in html
    assert 'background_artifact' in html
    assert 'confirmed_dark_spot' in html
    assert 'fetch(' not in html and 'http://' not in html and 'https://' not in html


def test_full_res_true_contour_preview_distinct_from_centroid_locator():
    root=Path(__file__).resolve().parents[1]
    d=root/"outputs/case03d_autodetect/run_20261009_autodetect_final/figures"
    auto=d/"auto_detected_only_full_view.png"
    loc=d/"automatic_detection_centroid_locator.png"
    assert auto.is_file() and loc.is_file()
    assert auto.read_bytes()!=loc.read_bytes()
