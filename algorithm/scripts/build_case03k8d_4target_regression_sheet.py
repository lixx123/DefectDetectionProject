"""K8D before-vs-after from exact SAME frame-2 RAW and candidate masks."""
from pathlib import Path
import sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03g_joint_noise_refinement import save_png
NEW=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3/frame26_2"
OLD=C.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1/frame26_2"
R=np.memmap(C.DATA_ROOT/"26 (2).raw",mode="r",dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
LABELS=(1148,1161,626,1483)
W=310;H=310
crops=[]
for label in LABELS:
    name=f"F2_B2_C{label:05d}"
    with np.load(OLD/"band02"/(name+"_all_masks.npz"),allow_pickle=False) as z:
        b=z["original_B_seed"].astype(bool)
        old=z["proposed_after_safety_gate"].astype(bool)
        xyxy=z["full_resolution_roi_global_xyxy"]
    with np.load(NEW/"band02"/(name+"_K8D_all_masks.npz"),allow_pickle=False) as z:
        new=z["K8D_full_outer"].astype(bool)
        assert np.array_equal(z["original_B_source"].astype(bool),b)
    x0,y0,x1,y1=[int(v) for v in xyxy]
    raw=np.asarray(R[y0:y1,x0:x1],np.uint16)
    lo,hi=np.percentile(raw,[1,99.5])
    gray=np.uint8(np.clip((raw.astype(float)-lo)/max(hi-lo,1)*255,0,255))
    background=cv2.cvtColor(cv2.resize(gray,(W,H),interpolation=cv2.INTER_NEAREST),
                             cv2.COLOR_GRAY2BGR)
    overlays=[np.zeros_like(b,bool),b,old,new]
    head=[f"RAW: B2-{label}",f"OLD B SEED  {int(b.sum())} px2",
          f"OLD FINAL  {int(old.sum())} px2",f"NEW K8D  {int(new.sum())} px2"]
    cards=[]
    for i,(mask,title) in enumerate(zip(overlays,head)):
        pic=background.copy()
        if mask.any():
            bm=cv2.resize(mask.astype(np.uint8),(W,H),interpolation=cv2.INTER_NEAREST)
            cnt,_=cv2.findContours(bm,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            color=(40,225,245) if i in (1,2) else (235,215,40)
            cv2.drawContours(pic,cnt,-1,color,1,cv2.LINE_8)
        hdr=np.full((82,W,3),24,np.uint8)
        cv2.putText(hdr,title,(8,27),cv2.FONT_HERSHEY_SIMPLEX,.46,(239,239,239),1)
        subtitle=("source not changed" if i==1 else
                  "old overconservative fallback" if i==2 else
                  "NEW review only, not certified" if i==3 else
                  "same RAW, same 128px coordinates")
        cv2.putText(hdr,subtitle,(8,55),cv2.FONT_HERSHEY_SIMPLEX,.36,(215,215,215),1)
        cards.append(np.vstack([hdr,pic]))
    crops.append(np.hstack(cards))
preview=np.vstack(crops)
path=NEW/"K8D_REGRESSION_4TARGET_OLD_VS_NEW.png"
save_png(path,preview)
back=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
assert back is not None and back.shape==preview.shape
print("K8D_4_REGRESSION_COMPARISON_READY",path,back.shape,flush=True)
