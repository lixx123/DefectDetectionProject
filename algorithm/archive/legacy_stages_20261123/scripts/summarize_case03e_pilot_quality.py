"""Case03-E pilot QA: reject provisional-size confidence where region is unstable.

No hand-drawn polygon is used to set the segmentation status or choose
thresholds; this is fixed heuristic QA of the six algorithmic outputs.
IoU against user-drawn polygons is retained for diagnosis only.
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"outputs/case03e/run_20261010_10roi_boundary_pilot_v1"
TABLE=RUN/"all_60_pilot_experiments.csv"

def judge_pilot(data:pd.DataFrame,*,area_ratio_warn:float=3)->pd.DataFrame:
    groups=[]
    for uid,group in data.groupby("user_target_id",sort=True):
        amin=int(group.predicted_area_px.min())
        amax=int(group.predicted_area_px.max())
        ratio=(amax/max(amin,1))
        boundary=bool(group.touches_crop_edge.any())
        if boundary:
            status="UNRESOLVED_CONNECTED_TO_CROP_BOUNDARY"
            reason="Segmentation reaches 256px window edge; connected background/stripe risk"
        elif ratio>=area_ratio_warn:
            status="UNRESOLVED_METHOD_INSTABILITY"
            reason="Candidate area varies by >=3x across predeclared local methods"
        else:
            status="NEEDS_INDEPENDENT_CONTOUR_REVIEW"
            reason="Methods stable by basic area/border checks; not proven accurate"
        # one chosen reference variant for consistent inspection, not a
        # validated automatic model. It must be flagged if other methods fail.
        a=group[(group.method=="gaussian22")&(group.threshold_level=="liberal")]
        if len(a)!=1:raise AssertionError(f"missing fixed comparator {uid}")
        sel=a.iloc[0]
        groups.append({
            "user_target_id":uid,
            "engineering_quality_gate":status,
            "gate_reason":reason,
            "any_method_crop_edge":boundary,
            "min_area_across_six_px":amin,
            "max_area_across_six_px":amax,
            "area_ratio_max_min":round(ratio,2),
            "reference_variant":"gaussian22_liberal",
            "reference_variant_area_px":int(sel.predicted_area_px),
            "reference_max_span_px":round(float(sel.max_hull_vertex_span_px),2),
            "reference_equivalent_diameter_px":round(float(sel.equivalent_diameter_px),2),
            "reference_manual_polygon_iou_DIAGNOSTIC_ONLY":
                float(sel.iou_against_manual_approximation),
            "reference_manual_polygon_coverage_DIAGNOSTIC_ONLY":
                float(sel.coverage_of_manual_polygon),
            "user_annotations_used_to_change_gate":False,
            "physical_size_grade":"UNDEFINED"
        })
    result=pd.DataFrame(groups)
    if len(result)!=10:raise AssertionError("ten target risk statuses required")
    return result


def preview_table(q:pd.DataFrame)->None:
    tiles=[]
    # The pre-generated atlas is 4x2 of 256px panels, 59px headers,
    # separated by 10px with 58px global header.
    sz=256;tileh=315;header=58;stride_x=266;stride_y=325
    for r in q.itertuples(index=False):
        name=r.user_target_id
        path=RUN/"figures"/f"{name}_local_8panel.png"
        original=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),
                              cv2.IMREAD_COLOR)
        if original is None:raise IOError(path)
        choices=[
           (0,0,"RAW + handwritten polygon"),
           (0,1,"Historic H170/230"),
           (1,2,"Gaussian22 liberal"),
           (0,3,"Closing61 conservative")
        ]
        sections=[]
        for row,col,label in choices:
            x=col*stride_x;y=header+row*stride_y
            extract=original[y:y+tileh,x:x+sz].copy()
            # More legible across big overview, resize to 180px.
            extract=cv2.resize(extract,(180,222),interpolation=cv2.INTER_AREA)
            sections.append(extract)
        assembled=np.concatenate(sections,axis=1)
        top=np.full((48,720,3),246,np.uint8)
        label=f"{name}  | {r.engineering_quality_gate} | area ratio {r.area_ratio_max_min:.2f}"
        cv2.putText(top,label[:95],(7,23),
                    cv2.FONT_HERSHEY_SIMPLEX,.46,(38,47,62),1,cv2.LINE_AA)
        cv2.putText(top,"RAW (manual yellow)      H source      Gaussian22 liberal      Closing61 conservative",
                    (7,41),cv2.FONT_HERSHEY_SIMPLEX,.35,(55,63,73),1,cv2.LINE_AA)
        tiles.append(np.concatenate([top,assembled],axis=0))
    contact=np.concatenate(tiles,axis=0)
    ok,encoded=cv2.imencode(".png",contact,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise IOError("overview encoding error")
    (RUN/"figures"/"CASE03E_all_10_boundary_comparison.png").write_bytes(encoded.tobytes())


def main():
    data=pd.read_csv(TABLE)
    if len(data)!=60:raise ValueError("unexpected experiment count")
    qa=judge_pilot(data)
    qa.to_csv(RUN/"per_target_engineering_QA.csv",encoding="utf-8-sig",index=False)
    preview_table(qa)
    counts=qa.engineering_quality_gate.value_counts().to_dict()
    summary={
        "all_targets":len(qa),
        "unresolved_due_to_roi_edge_and_background_bridge":
            int(counts.get("UNRESOLVED_CONNECTED_TO_CROP_BOUNDARY",0)),
        "unresolved_due_to_method_instability":
            int(counts.get("UNRESOLVED_METHOD_INSTABILITY",0)),
        "stable_enough_for_manual_boundary_review_not_proven_valid":
            int(counts.get("NEEDS_INDEPENDENT_CONTOUR_REVIEW",0)),
        "quality_rules_fixed_without_manual_polygon_ground_truth":True,
        "crop_edge_threshold":"any variant touches 256px crop boundary",
        "method_area_ratio_threshold":3.,
        "reference_variant_for_visual_comparison":"gaussian22_liberal",
        "reference_variant_not_validated":True,
        "do_not_use_unresolved_masks_for_final_size_grades":True,
    }
    assert sum(counts.values())==10
    (RUN/"engineering_qa_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),
        encoding="utf-8"
    )
    print("CASE03E_QA",json.dumps(summary,ensure_ascii=False))
    print("CASE03E_QA_PER_TARGET\n"+qa.to_string(index=False))
    print("CASE03E_CONTACT",RUN/"figures"/"CASE03E_all_10_boundary_comparison.png")


if __name__=="__main__":
    main()
