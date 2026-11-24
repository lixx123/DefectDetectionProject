"""K3 experiment part A: added 61px BlackHat, fixed 170/230, J5 anchors only.
All images/CSVs from frozen RAW and J5. No segmentation config changes.
"""
from pathlib import Path
import json,sys
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from scripts.run_case03g_joint_noise_refinement import save_png
B=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
O=B/"K3_scale61_seeded_pilot_v1"
if O.exists():raise FileExistsError(O)
O.mkdir()
LABEL=B/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv"
D=pd.read_csv(LABEL,encoding="utf-8-sig",keep_default_na=False)
D=D[D.sample_kind=="SMALL_CANDIDATE"]
mem=pd.read_csv(cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1/global_object_membership.csv")
mm=mem.groupby("global_defect_id")
J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
bh=np.load(cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",mmap_mode="r")
def objmask(r):
    x0,y0,x1,y1=[int(r[k]) for k in ("x0","y0","x1","y1")]
    dst=np.zeros((128,128),bool)
    for m in mm.get_group(r["global_defect_id"]).itertuples():
        with np.load(J4/"tile_masks"/(m.source_tile_id+".npz")) as z:
            labels=z["grouped_source_only_i32"]
            rect=[int(t) for t in z["core_xyxy"]]
        ax=max(x0,rect[0]);ay=max(y0,rect[1]);ex=min(x1,rect[2]);ey=min(y1,rect[3])
        if ax>=ex or ay>=ey:continue
        dst[ay-y0:ey-y0,ax-x0:ex-x0]|=(labels[
          ay-rect[1]:ey-rect[1],ax-rect[0]:ex-rect[0]]==m.source_local_object_index)
    if dst.sum()!=int(float(r["source_area_px2"])):
        raise AssertionError("source area wrong "+str(r["sample_id"]))
    return dst
def seeded(label,seed,high=230,low=170):
    n,lb,_,_=cv2.connectedComponentsWithStats(np.uint8(label>=low),8)
    ids=np.unique(lb[seed]);ids=ids[ids>0]
    if len(ids)==0:return np.zeros(seed.shape,bool)
    overlaps=np.bincount(lb[seed].ravel(),minlength=n);overlaps[0]=0
    best=int(np.argmax(overlaps))
    if best==0 or not np.any((lb==best)&(label>=high)):return np.zeros(seed.shape,bool)
    return lb==best
rows=[]
for record in D.to_dict("records"):
    x0,y0,x1,y1=(int(record[k]) for k in ("x0","y0","x1","y1"))
    ax=max(0,x0-72);ay=max(0,y0-72);ex=min(cfg.RAW_WIDTH,x1+72);ey=min(cfg.RAW_HEIGHT,y1+72)
    window=np.asarray(raw[ay:ey,ax:ex],dtype=np.uint16)
    orig=np.asarray(bh[ay:ey,ax:ex],dtype=np.uint16)
    extra=black_hat_uint16(window,61,"ellipse")
    combined=np.maximum(orig,extra)
    seed_roi=objmask(record)
    seed=np.zeros(window.shape,bool);seed[y0-ay:y1-ay,x0-ax:x1-ax]=seed_roi
    cand0=seeded(orig,seed)
    cand61=seeded(combined,seed)
    if not np.all(cand0[seed]): # J5 refined may have extra pixels beyond H; don't assert equality.
        pass
    cut=(slice(y0-ay,y1-ay),slice(x0-ax,x1-ax))
    core=cand0[cut];enh=cand61[cut]
    yy,xx=np.nonzero(enh)
    touches=bool((yy==0).any() or (yy==127).any() or
                 (xx==0).any() or (xx==127).any())
    rows.append({
       "sample_id":record["sample_id"],
       "user_label_POSTHOC_ONLY":record["manual_candidate_label"],
       "original_J5_area":int(seed_roi.sum()),
       "original_H_anchor_area":int(core.sum()),
       "added61_H_anchor_area":int(enh.sum()),
       "added61_growth_ratio_from_H":round(float(enh.sum()/max(core.sum(),1)),3),
       "added61_target_high_peak_dn":int(combined[seed].max()),
       "added61_H_source_overlap":int((enh&seed_roi).sum()),
       "added61_H_bbox_width":int(np.ptp(xx)+1) if len(xx) else 0,
       "added61_H_bbox_height":int(np.ptp(yy)+1) if len(yy) else 0,
       "added61_roi_edge_touched":touches,
       "frozen_original_masks_changed":False
    })
table=pd.DataFrame(rows)
table.to_csv(O/"24_targets_scale61_vs_original_H.csv",index=False,encoding="utf-8-sig")
print("K3_PART_A_RESULTS")
print(table[["sample_id","user_label_POSTHOC_ONLY","original_J5_area","original_H_anchor_area","added61_H_anchor_area","added61_growth_ratio_from_H","added61_H_source_overlap"]].to_string(index=False))
print("K3_PART_A_GROUPS")
print(table.groupby("user_label_POSTHOC_ONLY").agg(n=("sample_id","size"),base=("original_H_anchor_area","median"),enhanced=("added61_H_anchor_area","median"),ratio=("added61_growth_ratio_from_H","median")).to_string())
print("K3_PART_A_OUTPUT",O)
