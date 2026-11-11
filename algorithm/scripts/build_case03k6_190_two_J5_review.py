"""K6_190 corrected DISPLAY diagnostic - two existing independent J5 objects.

Fix REVIEW VISUALIZATION only: show all J5 objects in 128x128 ROI, with
source intact and labels. Not an automatic merge or resegmentation.
The visually dominant source is an already-detected LARGE object.
"""
from pathlib import Path
import cv2,numpy as np,json,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"outputs/case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1/K6_190_seed_geometry_diagnostic_v1"
DEST=SRC/"K6_190_CORRECTED_TWO_J5_OBJECTS_4panel.png"
J5=ROOT/"outputs/case03j5_global/run_20261012_frame26_2_J5_independent_v1"
if DEST.exists():raise FileExistsError("Refuse overwrite revised review display")
with np.load(SRC/"original_diagnostic_arrays.npz",allow_pickle=False) as z:
    raw=z["raw_128_u16"]
    source=z["source_J5_mask"].astype(bool)
    labels=z["source_J5_label_strings"]
    response=z["original_BH31_u16"]
    resp61=z["expanded_BH61_u16"]
    k3dark=z["K5_active3"].astype(bool)
    xyxy=[int(v) for v in z["roi_global_xyxy"]]
assert tuple(raw.shape)==(128,128) and source.sum()==15
large=labels=="DEFECT_02914"
small=labels=="DEFECT_02917"
assert large.sum()==1646 and np.array_equal(source,small)
catalog=pd.read_csv(J5/"global_defects.csv").set_index("global_defect_id")
assert catalog.loc["DEFECT_02914","grade"]=="LARGE"
assert catalog.loc["DEFECT_02917","grade"]=="SMALL"

low,hi=np.percentile(raw,[1,99.5])
G=np.uint8(np.clip((raw.astype(np.float32)-low)/max(hi-low,1)*255,0,255))
def bounding_box(mask):
    y,x=np.where(mask)
    return [int(x.min()),int(y.min()),int(x.max()),int(y.max())]
lb=bounding_box(large)
sb=bounding_box(small)
gap=max(0,sb[0]-lb[2]-1)
assert gap==15 # local true source bbox separation

def pane(title,desc,which,show_boxes=False):
    im=cv2.cvtColor(G,cv2.COLOR_GRAY2BGR)
    if which in ("both","big"):
        outlines,_=cv2.findContours(np.uint8(large),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        fill=im.copy();fill[large]=(65,202,84)
        im=cv2.addWeighted(im,.68,fill,.32,0)
        cv2.drawContours(im,outlines,-1,(75,230,105),1)
    if which in ("both","small"):
        outlines,_=cv2.findContours(np.uint8(small),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        im[small]=(0,0,255)
        cv2.drawContours(im,outlines,-1,(25,30,255),1)
    if which=="k3":
        outlines,_=cv2.findContours(np.uint8(k3dark),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im,outlines,-1,(10,207,238),1)
        im[small]=(0,0,255)
    if show_boxes:
        cv2.rectangle(im,(lb[0],lb[1]),(lb[2],lb[3]),(60,220,75),1)
        cv2.rectangle(im,(sb[0],sb[1]),(sb[2],sb[3]),(25,30,250),1)
    im=cv2.resize(im,(400,400),interpolation=cv2.INTER_NEAREST)
    hdr=np.full((86,400,3),25,np.uint8)
    cv2.putText(hdr,title,(8,29),cv2.FONT_HERSHEY_SIMPLEX,.57,(242,242,242),1)
    cv2.putText(hdr,desc,(8,52),cv2.FONT_HERSHEY_SIMPLEX,.39,(213,213,213),1)
    return np.vstack((hdr,im))
images=[
    pane("RAW | TWO SPATIAL REGIONS","Frozen second frame; coordinates unchanged","none",True),
    pane("J5 LARGE: DEFECT_02914","GREEN = original 1646 source px", "big"),
    pane("J5 SMALL: DEFECT_02917","RED = original 15 source px", "small"),
    pane("CORRECTED JOINT VIEW","Two original IDs, NO merge", "both",True)
]
combined=np.hstack(images)
success,data=cv2.imencode(".png",combined)
assert success;DEST.write_bytes(data.tobytes())
verified=cv2.imdecode(np.frombuffer(DEST.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
assert verified is not None and verified.shape==combined.shape
name=str(DEST)
report={
  "sample":"K6_190","frame":"26 (2).raw",
  "ROI_global_xyxy":xyxy,
  "original_small_J5":{
    "ID":"DEFECT_02917","source_area_px2":15,"J5_grade":"SMALL",
    "source_bbox_global_xywh":[8250,8067,6,7],
    "center_global_xy":[8252.6667,8069.6667]},
  "visually_dominant_left_J5":{
    "ID":"DEFECT_02914","source_area_px2":1646,"J5_grade":"LARGE",
    "source_bbox_global_xywh":[8195,8033,40,68],
    "center_global_xy":[8213.8165,8068.3378]},
  "horizontal_source_bounding_boxes_separated_pixels":gap,
  "cause":"K6_190 is anchored on small right-side J5 02917; left dark region is already J5 02914, not a missed defect",
  "RAW_K5_source_anchored_k3_area_px2":0,
  "visualization_recommendation":"Display both source masks and IDs in local ROI. Do not auto-merge or change defect areas.",
  "confirmed_actual_physical_identity_of_two_sources":False,
  "source_J5_IDs_and_masks_changed":False,
  "output":name
}
(SRC/"K6_190_two_existing_J5_explanation.json").write_text(
    json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print("K6_190_CORRECTED_VIEW_READY",json.dumps(report,ensure_ascii=False),flush=True)
