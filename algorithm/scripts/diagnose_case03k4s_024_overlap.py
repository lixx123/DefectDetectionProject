"""Audit why K4S_024 RAW ring conflicts with nearby original J5 objects."""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_case03k4_expanded_pilot import retrieve_source_and_others,J5,J4
from src.detection.case03k3_spot_contour_pilot import PilotConfig,raw_outer_envelope
from scripts.run_case03g_joint_noise_refinement import save_png
src=ROOT/"outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1"
row=pd.read_csv(src/"240_scale_trial_audit.csv")
r=row.loc[row.sample_id=="K4S_024"].iloc[0].to_dict()
membership=pd.read_csv(J5/"global_object_membership.csv")
lookup=dict(zip(zip(membership.source_tile_id,membership.source_local_object_index),
                membership.global_defect_id))
source,competitor=retrieve_source_and_others(r,membership.groupby("global_defect_id"))
x0,y0,x1,y1=[int(r[k]) for k in ("x0","y0","x1","y1")]
raw=np.memmap(ROOT/"../疵病实测数据/260624批次表观（5片）/26 (1).raw",
             mode="r",dtype=">u2",shape=(9200,11276))
im=np.asarray(raw[y0:y1,x0:x1],np.uint16)
center=(float((x0+x1)/2),float((y0+y1)/2))
candidate,stats=raw_outer_envelope(im,source,(center[0]-x0,center[1]-y0),PilotConfig())
counts={}
details={}
pixel_byid=np.empty(source.shape,dtype=object);pixel_byid[:]=None
for iy in range(y0//256,(y1-1)//256+1):
  for ix in range(x0//256,(x1-1)//256+1):
    name=f"T{iy:03d}_{ix:03d}"
    with np.load(J4/"tile_masks"/(name+".npz"),allow_pickle=False) as z:
      label=z["grouped_source_only_i32"].copy()
      rect=[int(k) for k in z["core_xyxy"]]
    ax=max(x0,rect[0]);ay=max(y0,rect[1]);bx=min(x1,rect[2]);by=min(y1,rect[3])
    if bx<=ax or by<=ay:continue
    tile=label[ay-rect[1]:by-rect[1],ax-rect[0]:bx-rect[0]]
    cand=candidate[ay-y0:by-y0,ax-x0:bx-x0]
    for idx in np.unique(tile[cand & (tile>0)]):
      key=lookup.get((name,int(idx)),"unmapped")
      amount=int(np.count_nonzero((tile==idx)&cand))
      counts[key]=counts.get(key,0)+amount
      details[key]=details.get(key,[])+[(name,int(idx),amount)]
df=pd.read_csv(J5/"global_defects.csv")
facts=df[df.global_defect_id.isin(counts.keys())].copy()
facts["overlap_px"]=facts.global_defect_id.map(counts)
facts=facts.sort_values("overlap_px",ascending=False)
print("RAW_candidate_pixels",candidate.sum(),"own_original_J5",source.sum(),
      "overlap_other_J5",int(np.count_nonzero(candidate & competitor)))
print("distinct_J5_objects_intersecting_raw_outer",len(counts))
print(facts[["global_defect_id","grade","source_area_px2","source_max_feret_px",
             "center_x_global","center_y_global","overlap_px"]].to_string(index=False))
print("COMPONENTS",json.dumps(details))
# emit reversible audit figure: background + provisional perimeter + original source and competing J5 pixels.
lo,hi=np.percentile(im,[1,99.5])
g=np.uint8(np.clip((im.astype(float)-lo)/max(hi-lo,1)*255,0,255))
vis=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
outline,_=cv2.findContours(np.uint8(candidate),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
cv2.drawContours(vis,outline,-1,(30,230,235),1)
vis[source]=(10,10,250)
vis[candidate & competitor]=(10,190,255)
vis[competitor & ~candidate]=(235,30,170)
show=cv2.resize(vis,(640,640),interpolation=cv2.INTER_NEAREST)
header=np.full((76,640,3),28,np.uint8)
cv2.putText(header,"K4S_024 | CYAN=raw outer | RED=J5 own | ORANGE=other J5 within outer",
           (8,27),cv2.FONT_HERSHEY_SIMPLEX,.41,(239,239,239),1)
cv2.putText(header,
           f"Raw=725 px2; competing overlaps={int(np.count_nonzero(candidate&competitor))}; J5 IDs={len(counts)}",
           (8,55),cv2.FONT_HERSHEY_SIMPLEX,.45,(225,225,225),1)
dest=src/"K4S_024_intersecting_J5_labels_diagnostic.png"
if dest.exists():raise FileExistsError(dest)
save_png(dest,np.vstack((header,show)))
audit=src/"K4S_024_intersecting_J5_objects.csv"
if audit.exists():raise FileExistsError(audit)
facts.to_csv(audit,index=False,encoding="utf-8-sig")
print("DIAGNOSTIC",dest)
