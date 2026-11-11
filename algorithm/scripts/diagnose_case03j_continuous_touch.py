from pathlib import Path
import cv2,numpy as np,pandas as pd
p=Path(__file__).resolve().parents[1]/"outputs/case03j_continuous/run_20261010_27windows_one_piece_v1"
with np.load(p/"masks/26_1_E2_W005_contour_provenance.npz") as z:
    old=z["grouped_original_only_ids"]
    original=z["original_region_labels"]
    bridge=z["inferred_bridge_ids"]
    rect=z["roi_global_xyxy"]
for j in np.unique(bridge):
    if not j:continue
    near=cv2.dilate(np.uint8(bridge==j),np.ones((3,3),np.uint8))
    where=(near>0)&(old>0)&(old!=j)
    ys,xs=np.nonzero(where)
    print('bridgegroup',j,'touched pixels',list(zip((xs+rect[0]).tolist(),(ys+rect[1]).tolist())),'source labels',original[ys,xs].tolist(),'other groups',old[ys,xs].tolist())
