"""One-off diagnostic of W002 weak-spot loss. No detector receives user ROI."""
import json
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"
f=pd.read_csv(ROOT/"outputs/case03f_localcontrast/run_20261010_small_raw_contrast_v1/candidate_trial_decisions.csv")
g=pd.read_csv(ROOT/"outputs/case03g_joint/run_20261010_10target_noise_refinement_v1/joint_candidate_audit.csv")
h=pd.read_csv(ROOT/"outputs/case03h_texture/run_20261010_10target_texture_conservative_v1/candidate_screen_audit.csv")
a=pd.read_csv(Path(r"C:\Users\lixia\Downloads\case03d_true_target_10roi_locations.csv")).fillna("")
with np.load(source/"masks/E2_W002_labels.npz") as z:
    H=z["H170_230"].astype(bool)
    origin=z["roi_origin_raw_xy"].astype(int)
n,labels,stats,_=cv2.connectedComponentsWithStats(H.astype(np.uint8),8)
poly=a[(a.annotation_kind=="poly")&(a.raw_x==11243)].iloc[0]
vertices=np.asarray(json.loads(poly.vertices_RAW_global_xy_JSON),np.int32)
pts=vertices-origin
mask=np.zeros_like(H,dtype=np.uint8)
cv2.fillPoly(mask,[pts.reshape(-1,1,2)],1)
area_count={}
for lab in np.unique(labels[mask>0]):
    if lab==0:continue
    area_count["Hlocal_%04d"%lab]=int(np.count_nonzero((labels==lab)&(mask>0)))
rows=pd.DataFrame([{"local_H_id":k,"manual_overlap":v} for k,v in area_count.items()])
merge=rows.merge(f[f.window_id=="E2_W002"],on="local_H_id").merge(
    g[g.window_id=="E2_W002"][["local_H_id","joint_gate_state","existing_refinement_sources"]],on="local_H_id").merge(
    h[h.window_id=="E2_W002"][["local_H_id","case03h_state","case03h_reason"]],on="local_H_id")
print(merge[["local_H_id","area_px","manual_overlap","fused_blackhat_peak_dn",
              "relative_contrast","significance_z","existing_refinement_sources",
              "joint_gate_state","case03h_state","case03h_reason"]].to_string(index=False))
print("Total overlap",sum(area_count.values()))
