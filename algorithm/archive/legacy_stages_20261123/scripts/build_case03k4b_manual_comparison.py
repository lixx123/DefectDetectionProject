"""Make readable fixed-coordinate 4-panel K4S_079 RAW boundary review.
All masks source from K4b sensitivity NPZ. Each panel reuses one RAW
gray scale; no image resizing or coordinate transform differences.
"""
from pathlib import Path
import cv2,numpy as np,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1/K4b_079_outer_boundary_sensitivity_v1"
path=OUT/"K4S079_compare_179_272_314_for_manual_review.png"
if path.exists():raise FileExistsError(path)
with np.load(OUT/"all_outlines.npz",allow_pickle=False) as z:
    source=z["original_mask"]>0
    masks=[z["base_179"]>0,z["alpha15_noise2p0"]>0,z["alpha15_noise1p5"]>0]
    roi=z["roi_xyxy"].tolist()
assert len(masks)==3 and [int(m.sum()) for m in masks]==[179,272,314]
rawmem=np.memmap(ROOT/"../疵病实测数据/260624批次表观（5片）/26 (1).raw",
                 mode="r",dtype=">u2",shape=(9200,11276))
x0,y0,x1,y1=map(int,roi)
raw=np.asarray(rawmem[y0:y1,x0:x1],np.uint16)
a,b=np.percentile(raw,[1,99.5])
gray=np.uint8(np.clip((raw.astype(float)-a)/max(1,b-a)*255,0,255))
def card(title,subtitle,mask,show):
    im=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    if show and mask.any():
        tint=im.copy();tint[mask]=(35,220,230)
        im=cv2.addWeighted(im,.75,tint,.25,0)
        outline,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im,outline,-1,(0,225,245),1)
    original,_=cv2.findContours(np.uint8(source),cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(im,original,-1,(0,0,250),1)
    im=cv2.resize(im,(400,400),interpolation=cv2.INTER_NEAREST)
    header=np.full((86,400,3),26,np.uint8)
    cv2.putText(header,title,(12,34),cv2.FONT_HERSHEY_SIMPLEX,.55,
                (235,235,235),1,cv2.LINE_AA)
    cv2.putText(header,subtitle,(12,63),cv2.FONT_HERSHEY_SIMPLEX,.38,
                (213,213,213),1,cv2.LINE_AA)
    return np.vstack((header,im))
items=[
    card("RAW | 7px J5 core","Red core / native 128x128 ROI",source,False),
    card("K3 original | 179 px2","15% peak + 3 MAD sigma",masks[0],True),
    card("Trial A | 272 px2","15% peak + 2 MAD sigma",masks[1],True),
    card("Trial B | 314 px2","15% peak + 1.5 MAD sigma",masks[2],True),
]
img=np.hstack(items)
success,buf=cv2.imencode(".png",img)
assert success
path.write_bytes(buf.tobytes())
decoded=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
assert decoded is not None and decoded.shape==img.shape
print("K4S079_FOUR_PANEL_READY",path,decoded.shape)
