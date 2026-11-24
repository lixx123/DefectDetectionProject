"""Add size-in-pixels comparisons for 10-ROI manual polygons.

These are manual polygon approximations, NOT confirmed physical defect areas.
Do not convert 3.2um sensor pixel to object plane or invent grade cutoffs.
"""
from __future__ import annotations
import json,math,sys
from pathlib import Path
import numpy as np
import pandas as pd
import cv2

ROOT=Path(__file__).resolve().parents[1]
ANALYSIS=ROOT/"outputs/case03d_true_target_analysis/run_20261010_manual_10roi_matching"

def main():
    annotations=pd.read_csv(
        r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv",
        encoding="utf-8-sig",keep_default_na=False
    )
    mapped=pd.read_csv(ANALYSIS/"11_polygon_vs_actual_H_components.csv",
                       keep_default_na=False)
    points=pd.read_csv(ANALYSIS/"11_clicked_points_class_status.csv",
                       keep_default_na=False)
    man=pd.read_csv(
        ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200/"
        "ten_roi_true_target_click_annotation/ten_roi_manifest.csv",
        keep_default_na=False
    )
    all_rows=[]
    for parent,frame in annotations.groupby("source_parent_H_candidate_id",sort=False):
        m=man[man.candidate_id==parent].iloc[0]
        masks=frame[frame.annotation_kind=="poly"].sort_values("target_index_in_roi")
        pins=frame[frame.annotation_kind=="point"].sort_values("target_index_in_roi")
        if len(masks)!=len(pins):
            raise AssertionError(f"number of point centers must equal number polygons for {parent}")
        for i,(poly,pin) in enumerate(zip(masks.to_dict("records"),pins.to_dict("records")),1):
            pos=np.asarray(json.loads(poly["vertices_RAW_global_xy_JSON"]),dtype=np.float64)
            center=np.asarray([int(pin["raw_x"]),int(pin["raw_y"])],dtype=np.float64)
            mn=pos.min(axis=0);mx=pos.max(axis=0)
            if not((mn<=center).all() and (center<=mx).all()):
                raise AssertionError(f"clicked center not in corresponding polygon bbox: {parent}")
            test=cv2.pointPolygonTest(np.int32(pos).reshape(-1,1,2),
                                      (float(center[0]),float(center[1])),False)
            if test<0:
                # Warn, but center-polygon pairing remains an audit hypothesis.
                paired_inside=False
            else:paired_inside=True
            distances=np.sqrt(((pos[:,None,:]-pos[None,:,:])**2).sum(axis=2))
            maximum=float(distances.max())
            raster=mapped[(mapped.source_parent_H_candidate_id==parent)&
                          (mapped.annotation_number==int(poly["target_index_in_roi"]))]
            if len(raster)!=1:
                raise AssertionError(f"matching polygon feature missing {parent}")
            d=raster.iloc[0].to_dict()
            visited=points[(points.source_parent_H_candidate_id==parent)&
                           (points.annotation_number==int(pin["target_index_in_roi"]))]
            if len(visited)!=1:raise AssertionError("missing point status")
            c=visited.iloc[0]
            near_border=bool((pos[:,0]-int(m.roi_x0)<=2).any() or
                             (int(m.roi_x0)+159-pos[:,0]<=2).any() or
                             (pos[:,1]-int(m.roi_y0)<=2).any() or
                             (int(m.roi_y0)+159-pos[:,1]<=2).any())
            verified=False if parent=="H_sample26_0452065" else None
            all_rows.append({
                "review_target_id":f"RAW26_MANUAL_{len(all_rows)+1:03d}",
                "original_ROI_parent_candidate_id":parent,
                "manual_polygon_row_id":int(poly["target_index_in_roi"]),
                "manual_point_row_id":int(pin["target_index_in_roi"]),
                "clicked_raw_x":int(pin["raw_x"]),
                "clicked_raw_y":int(pin["raw_y"]),
                "point_inside_paired_polygon":paired_inside,
                "user_new_note":poly["new_roi_note"],
                "user_note_conflict_no_anomaly":parent=="H_sample26_0452065",
                "manual_polygon_area_shoelace_px2":float(poly["manual_approx_area_px2"]),
                "manual_polygon_raster_area_px":int(d["rasterized_polygon_pixel_area"]),
                "manual_polygon_bbox_width_px":int(mx[0]-mn[0])+1,
                "manual_polygon_bbox_height_px":int(mx[1]-mn[1])+1,
                "manual_polygon_max_vertex_span_px":round(maximum,2),
                "manual_polygon_eq_diameter_px":round(
                    2*math.sqrt(float(poly["manual_approx_area_px2"])/math.pi),2),
                "manual_polygon_near_160px_ROI_boundary":near_border,
                "existing_H_segmentation_area_intersect_polygon_px":int(d["H_overlap_pixel_count"]),
                "existing_H_segmentation_polygon_coverage":float(d["original_H_pixel_coverage_fraction"]),
                "corresponding_H_component_number_in_polygon":int(d["number_H_components_touching_polygon"]),
                "dominant_exact_H_candidate_id":d["top_matching_H_component_ID"],
                "dominant_exact_H_candidate_decision":d["top_matching_H_component_status"],
                "clicked_pixel_H_class":c["clicked_point_H_status"],
                "clicked_pixel_exact_H_candidate_id":c["exact_H_component_ID_at_clicked_pixel"],
                "severe_segmentation_coverage_gap_heuristic":float(
                    d["original_H_pixel_coverage_fraction"])<.40,
                "not_final_physical_defect_truth":True,
                "size_grade":"PENDING_USER_MEASUREMENT_THRESHOLDS",
            })
    df=pd.DataFrame(all_rows)
    if len(df)!=11 or df.review_target_id.duplicated().any():
        raise AssertionError("manual polygon objects count mismatch")
    df.to_csv(ANALYSIS/"11_manual_target_size_and_status_preliminary.csv",
              encoding="utf-8-sig",index=False)
    summary={
        "manual_polygon_proposals":len(df),
        "user_note_conflict_count":int(df.user_note_conflict_no_anomaly.sum()),
        "manual_point_inside_polygon_counts":df.point_inside_paired_polygon.value_counts().to_dict(),
        "polygon_near_ROI_edge_count":int(df.manual_polygon_near_160px_ROI_boundary.sum()),
        "polygons_H_coverage_below_40_percent":int(
            df.severe_segmentation_coverage_gap_heuristic.sum()),
        "polygons_H_coverage_below_40_percent_excluding_user_conflict":int(
            (df.severe_segmentation_coverage_gap_heuristic &
             ~df.user_note_conflict_no_anomaly).sum()),
        "grade_thresholds":None,
        "object_plane_magnification":None,
        "area_not_ground_truth":True,
        "physical_defect_count_not_validated":True
    }
    (ANALYSIS/"size_measurement_preliminary_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("MANUAL_SIZE_OUTPUT",ANALYSIS/"11_manual_target_size_and_status_preliminary.csv")
    print("MANUAL_SIZE_SUMMARY",json.dumps(summary,ensure_ascii=False))
    print(df[["review_target_id","original_ROI_parent_candidate_id",
        "clicked_raw_x","clicked_raw_y","manual_polygon_area_shoelace_px2",
        "manual_polygon_max_vertex_span_px","dominant_exact_H_candidate_decision",
        "existing_H_segmentation_polygon_coverage","user_note_conflict_no_anomaly",
        "manual_polygon_near_160px_ROI_boundary"]].to_string(index=False))

if __name__=="__main__":main()
