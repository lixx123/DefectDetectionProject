from pathlib import Path
import sys,cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from config import user_config as c
K=c.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2"
P=c.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2/frame26_2"
A=pd.read_csv(K/"all_K8D_original_vs_outer_review.csv")
B=pd.read_csv(P/"original_J5_object_center_workband_classification.csv")
def load(i):
 p=K/"band02"/f"F2_B2_C{i:05d}_K8D_all_masks.npz"
 with np.load(p,allow_pickle=False) as z:
  box=z["raw_global_roi_xyxy"].astype(int)
  mask=z["K8D_full_outer"].astype(bool)
  source=z["original_B_source"].astype(bool)
 return box,mask,source
for i in (1148,1161,626):
 box,m,s=load(i)
 print("SAMPLE",i,"roi",box,"source",s.sum(),"outer",m.sum())
 print("evidence",A[A.candidate_label==i][["associated_B_labels","partial_B_competitors","status"]].to_dict("records"))
 j=B[(B.center_x_global>=box[0])&(B.center_x_global<box[2])&(B.center_y_global>=box[1])&(B.center_y_global<box[3])]
 hits=[]
 for row in j.itertuples():
  y=int(round(row.center_y_global))-int(box[1]);x=int(round(row.center_x_global))-int(box[0])
  if 0<=x<m.shape[1] and 0<=y<m.shape[0] and m[y,x]:
   hits.append((row.global_id,row.grade))
 print("J5_centers_inside_full_outer",hits[:30],"total",len(hits))
for i,j in [(1148,1161),(1148,626)]:
 aa,ma,sa=load(i);bb,mb,sb=load(j)
 left=max(aa[0],bb[0]);right=min(aa[2],bb[2]);top=max(aa[1],bb[1]);bottom=min(aa[3],bb[3])
 if left<right and top<bottom:
  a=ma[top-aa[1]:bottom-aa[1],left-aa[0]:right-aa[0]]
  b=mb[top-bb[1]:bottom-bb[1],left-bb[0]:right-bb[0]]
  both=int((a&b).sum());print("PAIR",i,j,"AND",both,"IoU",round(both/(ma.sum()+mb.sum()-both),4),
                           "mincover",round(both/min(ma.sum(),mb.sum()),4),
                           "union",int(ma.sum()+mb.sum()-both))
