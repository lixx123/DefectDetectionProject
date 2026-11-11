"""Regression: manual click/poly RAW-coordinate audit is non-mutating and exact."""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching"
PREV=ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200"


def inputs():
    return pd.read_csv(
        r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv",
        keep_default_na=False,encoding="utf-8-sig"),json.loads(
        Path(r"C:\Users\lixia\Downloads\case03d_true_target_10roi_backup.json")
        .read_text(encoding="utf-8-sig")
    )


def test_complete_22_export_rows_are_11_point_polygon_pairs():
    csv,backup=inputs()
    sizes=pd.read_csv(OUT/"11_manual_target_size_and_status_preliminary.csv")
    assert len(csv)==22
    assert csv.annotation_kind.value_counts().to_dict()=={"point":11,"poly":11}
    assert len(backup["annotations"])==10
    assert sum(len(v["targets"]) for v in backup["annotations"].values())==22
    assert len(sizes)==11
    assert sizes["review_target_id"].is_unique
    assert sizes["point_inside_paired_polygon"].all()


def test_each_point_from_json_matches_exact_raw_original_pixel_in_csv():
    csv,backup=inputs()
    manifest=pd.read_csv(PREV/"ten_roi_true_target_click_annotation/ten_roi_manifest.csv")
    refs=manifest.set_index("candidate_id")
    for row in csv.to_dict("records"):
        src=row["source_parent_H_candidate_id"]
        entry=backup["annotations"][src]["targets"][row["target_index_in_roi"]-1]
        raw_coords=[[refs.loc[src,"roi_x0"]+p[0],
                     refs.loc[src,"roi_y0"]+p[1]]
                    for p in entry["points"]]
        assert row["annotation_kind"]==entry["kind"]
        assert raw_coords==json.loads(row["vertices_RAW_global_xy_JSON"])


def test_exact_centerpoint_H_intersections_are_not_guessed_by_bbox():
    table=pd.read_csv(OUT/"11_clicked_points_class_status.csv",keep_default_na=False)
    assert len(table)==11
    assert table["clicked_point_H_status"].value_counts().to_dict()=={
        "uncertain_review":5,"detected_provisional":3,
        "no_H_threshold_candidate":3
    }
    assert (table.loc[table.clicked_point_H_status=="no_H_threshold_candidate",
                       "exact_H_component_ID_at_clicked_pixel"]=="").all()
    assert (table.loc[table.clicked_point_H_status!="no_H_threshold_candidate",
                       "exact_H_component_ID_at_clicked_pixel"]!="").all()
    assert table["clicked_point_H_status"].ne("noise_like_retained").all()


def test_polygon_status_maps_and_component_conservation():
    polygons=pd.read_csv(OUT/"11_polygon_vs_actual_H_components.csv")
    assert len(polygons)==11
    assert polygons["top_matching_H_component_status"].value_counts().to_dict()=={
        "uncertain_review":8,"detected_provisional":3
    }
    assert polygons["H_overlap_pixel_count"].gt(0).all()
    assert polygons["number_H_components_touching_polygon"].ge(1).all()
    assert np.all(
        polygons["H_overlap_pixel_count"].to_numpy()==(
            polygons["polygon_detected_pixel_count"]+
            polygons["polygon_uncertain_pixel_count"]+
            polygons["polygon_noise_like_pixel_count"]
        ).to_numpy()
    )
    for r in polygons.to_dict("records"):
        components=json.loads(r["all_H_component_matches_JSON"])
        assert sum(k["polygon_intersect_H_pixels"] for k in components)==r["H_overlap_pixel_count"]
        assert components[0]["candidate_id"]==r["top_matching_H_component_ID"]


def test_user_no_anomaly_note_blocks_claiming_known_positive():
    p=pd.read_csv(OUT/"11_manual_target_size_and_status_preliminary.csv")
    row=p[p.original_ROI_parent_candidate_id=="H_sample26_0452065"]
    assert len(row)==1
    assert bool(row.iloc[0]["user_note_conflict_no_anomaly"])
    assert row.iloc[0]["user_new_note"]=="无异常"
    assert p["user_note_conflict_no_anomaly"].sum()==1
    summary=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    assert summary["physical_truth_reliable_target_count"]=="NOT_YET_ESTABLISHED"
    assert summary["size_grade_thresholds"]=="NOT_DEFINED"


def test_area_and_span_are_not_object_plane_um_without_calibration():
    p=pd.read_csv(OUT/"11_manual_target_size_and_status_preliminary.csv")
    assert p["manual_polygon_max_vertex_span_px"].between(18,112).all()
    assert p["manual_polygon_area_shoelace_px2"].between(190,2400).all()
    assert p["manual_polygon_near_160px_ROI_boundary"].sum()==4
    assert p["severe_segmentation_coverage_gap_heuristic"].sum()==4
    assert (p["size_grade"]=="PENDING_USER_MEASUREMENT_THRESHOLDS").all()
    summary=json.loads((OUT/"summary.json").read_text(encoding="utf-8"))
    assert summary["object_plane_pixel_size_um"]=="NOT_CALIBRATED"


def test_source_hashes_before_and_after_are_identical():
    s=json.loads((OUT/"source_manifest.json").read_text(encoding="utf-8"))
    assert s["source_files_unchanged"]
    assert s["inputs_before"]==s["inputs_after"]
    assert (OUT/"10roi_manual_polygons_vs_H_segmentation.png").is_file()
    assert (OUT/"CASE03D_TRUE_TARGET_ANALYSIS_REPORT.md").is_file()
