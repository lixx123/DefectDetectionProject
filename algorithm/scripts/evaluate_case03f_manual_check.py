"""Case03-F独立后验复核：9窗口RAW人工多边形仅评估候选隐藏风险，不给检测器当种子。"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from config import user_config as cfg

SOURCE=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"
TRIAL=cfg.OUTPUT_ROOT/"case03f_localcontrast/run_20261010_small_raw_contrast_v1"
ANNOTATIONS=Path(r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv")


def run()->None:
    manual=pd.read_csv(ANNOTATIONS, encoding="utf-8-sig").fillna("")
    truth=pd.read_csv(SOURCE/"ten_manual_targets_posthoc_evaluation.csv")
    trial=pd.read_csv(TRIAL/"candidate_trial_decisions.csv")
    summary=[]
    for row in truth.itertuples(index=False):
        win=row.window_id
        x, y=int(row.clicked_RAW_x),int(row.clicked_RAW_y)
        polygons=manual.loc[manual.annotation_kind.eq("poly")].copy()
        # 仅用点击位置来给人工多边形选最近配对，不能用于筛选候选/阈值。
        polygons["_distance"]=((pd.to_numeric(polygons.raw_x)-x)**2+
                                (pd.to_numeric(polygons.raw_y)-y)**2)
        poly=polygons.sort_values("_distance").iloc[0]
        if float(poly["_distance"])>400:
            raise AssertionError(f"No matching human polygon for {row.manual_target_id}")
        with np.load(SOURCE/"masks"/f"{win}_labels.npz") as z:
            h=z["H170_230"].astype(bool)
            ox,oy=(int(v) for v in z["roi_origin_raw_xy"])
        coords=np.asarray(json.loads(poly.vertices_RAW_global_xy_JSON),dtype=np.int32)
        pos=coords-np.array([ox,oy],dtype=np.int32)
        manual_mask=np.zeros_like(h,dtype=np.uint8)
        cv2.fillPoly(manual_mask,[pos.reshape(-1,1,2)],1)
        poly_bool=manual_mask.astype(bool)
        n,lab,st,_=cv2.connectedComponentsWithStats(h.astype(np.uint8),8)
        hide=trial.loc[(trial.window_id==win)&(trial.trial_status=="suggest_hide"),
                       "local_H_id"]
        hide_indices=[int(v.rsplit("_",1)[1]) for v in hide]
        hidden=np.isin(lab,hide_indices)&h
        intersection=h&poly_bool
        before=int(intersection.sum())
        dropped=int((intersection&hidden).sum())
        after=before-dropped
        area=int(poly_bool.sum())
        summary.append({
            "manual_target_id":row.manual_target_id,
            "window_id":win,"manual_note":poly.new_roi_note,
            "preexisting_h_overlap_pixels":before,
            "suggested_hidden_H_overlap_pixels":dropped,
            "retained_H_overlap_pixels":after,
            "manual_approx_polygon_area_pixels":area,
            "H_overlap_retention_fraction":round(after/max(before,1),4),
            "manual_polygon_is_approximation":True,
            "trial_not_physical_truth":True,
        })
    dest=TRIAL/"manual_polygon_retention_posthoc.csv"
    pd.DataFrame(summary).to_csv(dest,index=False,encoding="utf-8-sig")
    print(pd.DataFrame(summary)[["manual_target_id","window_id",
                                 "preexisting_h_overlap_pixels",
                                 "suggested_hidden_H_overlap_pixels",
                                 "H_overlap_retention_fraction"]].to_string(index=False))
    print("saved",dest)


if __name__=="__main__":
    run()
