"""Case03-D evidence: two separately AUTO-DETECTED dark spots in one RAW crop.

This corrects misleading impression of atlas_detected_top12: right-hand panel
shows *selected component only*, while another automatically detected
component is nearby. No edits to detection rules, masks, labels or sources.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
import cv2,numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from src.detection.candidate_contour_export import exact_candidate_submask

RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
SRC=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"
A="H_sample26_0406312"
B="H_sample26_0408029"

def check_and_render():
    df=pd.read_csv(RUN/"detected_provisional.csv",low_memory=False).set_index("candidate_id")
    for cid in (A,B):
        if cid not in df.index:raise AssertionError(f"{cid} not automatically detected")
        if df.loc[cid,"triage_status"]!="detected_provisional":
            raise AssertionError("candidate was not detected")
    top=df.loc[A].to_dict();bottom=df.loc[B].to_dict()
    top["candidate_id"]=A;bottom["candidate_id"]=B
    x0,y0,x1,y1=9360,998,9520,1158
    w,h=x1-x0,y1-y0
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(9200,11276))
    patch=np.asarray(raw[y0:y1,x0:x1],dtype=np.float32)
    S=load_packed_mask(SRC/"fused_S_TL230_TH230.npz")[y0:y1,x0:x1]
    H=load_packed_mask(SRC/"fused_H_TL170_TH230.npz")[y0:y1,x0:x1]
    with np.load(RUN/"candidate_status_map_lossless.npz",allow_pickle=False) as dat:
        class_map=dat["class_map"][y0:y1,x0:x1].copy()
    lo,hi=np.percentile(patch,[1,99.5]);hi=max(hi,lo+1)
    gray=np.uint8(np.rint(np.clip((patch-lo)/(hi-lo),0,1)*255))
    orig=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    thresh=orig.copy()
    thresh[S]=(20,232,252)  # BGR yellow = S230 core
    thresh[H&~S]=(245,215,35) # BGR cyan = H170 extension
    both=orig.copy()
    both[class_map==3]=(50,219,55) # Both detected components and any others in crop.
    both[class_map==2]=(20,172,240) # uncertain amber
    selected=orig.copy()
    exact1,(bx,by,bw,bh)=exact_candidate_submask(
        load_packed_mask(SRC/"fused_H_TL170_TH230.npz"),top)
    selected[by-y0:by-y0+bh,bx-x0:bx-x0+bw][exact1.astype(bool)]=(50,219,55)
    # Global bbox identity and validation for both directly selected component masks.
    details=[]
    for i,row in enumerate([top,bottom]):
        mask,(bx,by,bw,bh)=exact_candidate_submask(
            load_packed_mask(SRC/"fused_H_TL170_TH230.npz"),row)
        xx=bx-x0;yy=by-y0
        if not(0<=xx and 0<=yy and xx+bw<=w and yy+bh<=h):
            raise ValueError("full component bbox not inside demonstration crop")
        if not np.all(class_map[yy:yy+bh,xx:xx+bw][mask.astype(bool)]==3):
            raise AssertionError("component is not in AUTO detected pixel class")
        cv2.rectangle(both,(xx,yy),(xx+bw-1,yy+bh-1),(13,26,252),1)
        cv2.putText(both,str(i+1),(max(0,xx-10),max(10,yy-2)),
            cv2.FONT_HERSHEY_SIMPLEX,.38,(15,20,252),1,cv2.LINE_AA)
        details.append({"candidate_id":row["candidate_id"],
                        "center_global_raw_xy":[float(row["centroid_x"]),float(row["centroid_y"])],
                        "exact_area_px":int(mask.sum()),
                        "peak_blackhat_dn":int(row["peak_response_dn"]),
                        "bbox_global_xywh":[bx,by,bw,bh],
                        "classification":"detected_provisional",
                        "pixel_class_3_verified":True})
    separator=np.full((h,10,3),255,dtype=np.uint8)
    image=np.concatenate([orig,separator,thresh,separator,both,separator,selected],axis=1)
    topheight=76
    canvas=np.full((topheight+h,image.shape[1],3),245,dtype=np.uint8)
    canvas[topheight:]=image
    labels=["1 RAW","2 ALL S/H","3 ALL AUTO in ROI","4 SELECTED H_0406312 ONLY"]
    for i,label in enumerate(labels):
        cv2.putText(canvas,label,(i*(w+10)+5,28),cv2.FONT_HERSHEY_SIMPLEX,.49,
                     (25,41,54),1,cv2.LINE_AA)
    cv2.putText(canvas,"Green = all automatically selected H components (view 3); yellow = S230, cyan = H170 addition (view 2)",
               (7,52),cv2.FONT_HERSHEY_SIMPLEX,.42,(54,60,68),1,cv2.LINE_AA)
    cv2.putText(canvas,"Bottom spot H_0408029 is ALSO auto detected; view 4 hides it only because one H component is selected.",
               (7,69),cv2.FONT_HERSHEY_SIMPLEX,.42,(38,58,72),1,cv2.LINE_AA)
    p=RUN/"figures"/"diagnostic_two_automatically_detected_spots_0406312_0408029.png"
    ok,encoded=cv2.imencode(".png",canvas)
    if not ok:raise IOError(p)
    p.write_bytes(encoded.tobytes())
    evidence={"image_path":str(p),"raw_window_xyxy":[x0,y0,x1,y1],
       "classification_source":"detected_provisional.csv + full-resolution candidate_status_map_lossless.npz",
       "two_separate_detected_spots":details,
       "disclaimer":"Image is a 160x160 RAW crop; detected_provisional is not physical defect truth; no detection rules changed.",
       "image_display_note":"3rd panel shows all auto components, 4th panel shows ONLY selected upper component",
       "raw_mask_and_source_unchanged":True}
    result=RUN/"two_spots_verification.json"
    result.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
    print("VERIFIED",json.dumps(evidence,ensure_ascii=False),flush=True)
    return evidence

if __name__=="__main__":
    check_and_render()
