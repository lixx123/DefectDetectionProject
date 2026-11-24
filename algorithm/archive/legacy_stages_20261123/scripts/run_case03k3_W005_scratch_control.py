"""K3 control: impact of BH61 on frozen cross-shaped W005 (DEFECT_07328).

New scale is diagnostic only. W005 scratch remains on original
specialized J2/J5 long-scratch association path. No spot-like contour
growth is attempted for scratches.
"""
from pathlib import Path
import json,sys,cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k3_spot_contour_pilot import PilotConfig,aspect_and_bbox
from scripts.run_case03g_joint_noise_refinement import save_png
b=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
out=b/"K3_dualstage_contour_pilot_v1"
j4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
j5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
w=(2950,1020,3370,1250)
x0,y0,x1,y1=w
raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
bh=np.load(cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",mmap_mode="r")
m=pd.read_csv(j5/"global_object_membership.csv")
m=m[m.global_defect_id=="DEFECT_07328"]
assert len(m)>=2
orig=np.zeros((y1-y0,x1-x0),bool)
other=np.zeros_like(orig)
for iy in range(y0//256,(y1-1)//256+1):
    for ix in range(x0//256,(x1-1)//256+1):
        name=f"T{iy:03d}_{ix:03d}"
        with np.load(j4/"tile_masks"/(name+".npz")) as z:
            lab=z["grouped_source_only_i32"]
            rect=[int(v) for v in z["core_xyxy"]]
        a,b=max(rect[0],x0),max(rect[1],y0)
        c,e=min(rect[2],x1),min(rect[3],y1)
        if a>=c or b>=e:continue
        view=lab[b-rect[1]:e-rect[1],a-rect[0]:c-rect[0]]
        localids=m[m.source_tile_id==name].source_local_object_index.astype(int).tolist()
        own=np.isin(view,localids)
        idx=(slice(b-y0,e-y0),slice(a-x0,c-x0))
        orig[idx]|=own
        other[idx]|=(view>0)&~own
assert int(orig.sum())==7689,(orig.sum())
wraw=np.asarray(raw[y0-72:y1+72,x0-72:x1+72],np.uint16)
full_old=np.asarray(bh[y0-72:y1+72,x0-72:x1+72],np.uint16)
additional=black_hat_uint16(wraw,61,"ellipse")
new=np.maximum(full_old,additional)
sel=(slice(72,72+y1-y0),slice(72,72+x1-x0))
counts=[]
for typ,im in [("original_31",full_old),("plus_61",new)]:
    stage=im[sel]
    lo=stage>=170;hi=stage>=230
    n,labels,_,_=cv2.connectedComponentsWithStats(np.uint8(lo),8)
    seeded=np.unique(labels[hi]);seeded=seeded[seeded>0]
    anch=np.unique(labels[orig]);anch=anch[anch>0]
    valid=np.intersect1d(seeded,anch)
    keep=np.isin(labels,valid)
    counts.append({
        "method":typ,"scratch_original_J5_pixels":int(orig.sum()),
        "raw_H_components_intersecting_scratch_source":len(anch),
        "seeded_H_components_in_scratch_source":len(valid),
        "H_pixels_anchored_to_existing_scratch":int(keep.sum()),
        "H_pixels_overlapping_other_J5_objects":int((keep&other).sum()),
        "object_grade_is_original_large_scratch":True,
        "K3_spot_contour_applied":False,
    })
pd.DataFrame(counts).to_csv(out/"W005_scratch_scale_control.csv",
                            encoding="utf-8-sig",index=False)
original=np.asarray(raw[y0:y1,x0:x1],np.uint16)
lo,hi=np.percentile(original,[1,99.5])
g=np.uint8(np.clip((original.astype(float)-lo)/max(1,hi-lo)*255,0,255))
views=[]
for label,mask in [("Frozen original scratch",orig),("H-scale61 response",new[sel]>=170)]:
    image=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    tint=image.copy();tint[mask]=(15,215,230)
    image=cv2.addWeighted(image,.7,tint,.3,0)
    header=np.full((55,image.shape[1],3),24,np.uint8)
    cv2.putText(header,label,(8,26),cv2.FONT_HERSHEY_SIMPLEX,.48,
                (239,239,239),1,cv2.LINE_AA)
    views.append(np.vstack((header,image)))
save_png(out/"W005_scratch_not_sent_to_spot_refiner.png",np.hstack(views))
print("K3_W005_SCRATCH_QA",pd.DataFrame(counts).to_string(index=False),flush=True)
