"""Scratchpad: DoG feature stats on H candidates, strictly descriptive."""
from pathlib import Path
import sys
import numpy as np,cv2,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
source=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"
screen=pd.read_csv(ROOT/"outputs/case03f_localcontrast/run_20261010_small_raw_contrast_v1/candidate_trial_decisions.csv")
stage=pd.read_csv(ROOT/"outputs/case03g_joint/run_20261010_10target_noise_refinement_v1/joint_candidate_audit.csv")
raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
              shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
for win in ("E2_W001","E2_W002"):
    with np.load(source/"masks"/(win+"_labels.npz")) as z:
        H=z["H170_230"].astype(bool)
        x0,y0=(int(a) for a in z["roi_origin_raw_xy"])
    tile=np.asarray(raw[y0:y0+256,x0:x0+256],np.float32)
    dog=cv2.GaussianBlur(tile,(0,0),8)-cv2.GaussianBlur(tile,(0,0),2)
    n,labels,stats,_=cv2.connectedComponentsWithStats(H.astype(np.uint8),8)
    rows=[]
    for j in range(1,n):
        v=dog[labels==j]
        rows.append({
            "local_H_id":"Hlocal_%04d"%j,
            "dog_mean":float(v.mean()),"dog_peak":float(v.max()),
            "dog_median":float(np.median(v))})
    df=pd.DataFrame(rows)
    c=screen[screen.window_id==win].merge(stage[stage.window_id==win],on=["window_id","local_H_id"]).merge(df,on="local_H_id")
    print("\n",win)
    print("MEDIUM [6..30] DoG distribution for currently kept:")
    print(c[c.area_px.between(6,30)].groupby(pd.cut(c[c.area_px.between(6,30)].dog_median,[-999,0,5,10,15,20,30,50,1000]),observed=True).size())
    print("Main H:",c[c.local_H_id.isin(["Hlocal_0088","Hlocal_0197","Hlocal_0066","Hlocal_0071","Hlocal_0077"])][["local_H_id","area_px","dog_mean","dog_median","dog_peak"]].to_string(index=False))
    print("Medium DoG median quantiles",c[c.area_px.between(6,30)].dog_median.quantile([0,.1,.25,.5,.75,.9,1]).to_dict())
