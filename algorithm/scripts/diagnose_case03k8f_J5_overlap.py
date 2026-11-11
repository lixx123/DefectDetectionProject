from pathlib import Path
import numpy as np,pandas as pd,sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from config import user_config as C
E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1/frame26_2"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2/frame26_2"
g=pd.read_csv(E/"K8E_unique_group_union_measurements.csv")
j=pd.read_csv(B/"original_J5_object_center_workband_classification.csv")
for gid in ["K8E_F2_B2_G006","K8E_F2_B2_G009"]:
 t=g[g.group_id==gid].iloc[0]
 with np.load(E/"group_detail"/(gid+"_EXACT_GROUP_MASK.npz"),allow_pickle=False) as z:
  rect=z["roi_xyxy"];mask=z["review_outer"].astype(bool)
 x0,y0,x1,y1=map(int,rect)
 nearby=j[(j.display_bbox_x_global<=x1)&
          (j.display_bbox_xmax_inclusive>=x0)&
          (j.display_bbox_y_global<=y1)&
          (j.display_bbox_ymax_inclusive>=y0)]
 print(gid,"full_bbox_intersect",len(nearby),"J5 rows",nearby[["global_defect_id","source_area_px2","grade"]].to_dict("records"))
 print("K8E",t.unique_outer_union_px2,t.trial_size_grade,t.union_length_detector_um_PROVISIONAL,t.union_area_detector_um2_PROVISIONAL)
