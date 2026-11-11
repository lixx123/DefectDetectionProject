"""Case03-D-R2 presentation: true contours for automatic proposed detections.

The displayed image is downsampled, so outlines are projected for visualization.
Canonical pixel-exact outlines stay in component_contours_exact.jsonl and the
lossless status map; image markers must not be used to measure lesion area.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg

OUTPUT=ROOT/"outputs/case03d_autodetect/run_20261009_automated_triage_r2"


def make_preview(out:Path=OUTPUT,stride:int=6):
    raw_file=cfg.DATA_ROOT/"26 (1).raw"
    raw=np.memmap(raw_file,mode="r",dtype=">u2",shape=(9200,11276))
    sampled=np.asarray(raw[::stride,::stride],dtype=np.float32)
    lo,hi=np.percentile(sampled,[1,99.5])
    hi=max(lo+1,hi)
    gray=np.uint8(np.rint(np.clip((sampled-lo)/(hi-lo),0,1)*185+42))
    base=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    detected=base.copy()
    with_uncertain=base.copy()
    count=0
    with (out/"component_contours_exact.jsonl").open("r",encoding="utf-8") as f:
        for line in f:
            record=json.loads(line)
            if record["triage_status"]!="detected_provisional":
                continue
            count+=1
            bbox=record["bbox_global_xywh"]
            # Correct source contour, projected with the known image sampling ratio.
            for contour in record["boundary_contours"]:
                if contour["is_inner_hole"] or not contour["xy"]:
                    continue
                coords=np.asarray(contour["xy"],dtype=np.float32)
                points=np.rint(coords/stride).astype(np.int32).reshape((-1,1,2))
                if len(points)>=2:
                    cv2.polylines(detected,[points],True,(40,230,40),1,cv2.LINE_8)
                    cv2.polylines(with_uncertain,[points],True,(40,230,40),1,cv2.LINE_8)
            cx=int(round(record["centroid_global_xy"][0]/stride))
            cy=int(round(record["centroid_global_xy"][1]/stride))
            if 0<=cx<detected.shape[1] and 0<=cy<detected.shape[0]:
                cv2.circle(detected,(cx,cy),2,(30,223,30),-1)
                cv2.circle(with_uncertain,(cx,cy),2,(30,223,30),-1)
    uncertain=pd.read_csv(out/"uncertain_review_full.csv",
                          usecols=["centroid_x","centroid_y"],low_memory=False)
    for row in uncertain.itertuples(index=False):
        cx=int(round(row.centroid_x/stride))
        cy=int(round(row.centroid_y/stride))
        if 0<=cx<with_uncertain.shape[1] and 0<=cy<with_uncertain.shape[0]:
            cv2.circle(with_uncertain,(cx,cy),1,(20,178,247),-1)
    for image,kind in [(detected,"detected_only"),
                       (with_uncertain,"detected_and_uncertain")]:
        cv2.rectangle(image,(8,8),(1110,75),(250,250,250),-1)
        label=("Provisional auto DETECTION: green outlines, N="+str(count)
               if kind=="detected_only" else
               "Provisional detections: green; uncertain centers: amber")
        cv2.putText(image,label,(17,32),cv2.FONT_HERSHEY_SIMPLEX,.65,
                    (28,35,44),1,cv2.LINE_AA)
        cv2.putText(image,"DOWN-SAMPLED DISPLAY; measure shape via exact JSONL/NPZ, not this PNG",
                    (17,56),cv2.FONT_HERSHEY_SIMPLEX,.48,
                    (41,41,41),1,cv2.LINE_AA)
        filename=(out/"figures"/("auto_"+kind+"_full_view.png"))
        ok,buf=cv2.imencode(".png",image)
        if not ok:raise IOError(filename)
        filename.write_bytes(buf.tobytes())
        print("OUTPUT",filename.name,"size",filename.stat().st_size)
    print("AUTOMATIC_CONTOURED_OBJECTS",count)
    return count


if __name__=="__main__":
    make_preview()
