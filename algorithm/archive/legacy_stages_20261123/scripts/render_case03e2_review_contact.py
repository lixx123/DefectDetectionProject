"""Prepare one easy-to-open contact sheet of all 9 multi-candidate ROIs."""
from __future__ import annotations
import json,sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"outputs/case03e2/run_20261010_multiseed_fusion_v5"

def build(run:Path=RUN):
    entries=json.loads((run/"window_summary.json").read_text(encoding="utf-8"))
    frames=[]
    for item in entries:
        name=item["window_id"]
        path=run/"figures"/f"{name}_5panel_ALL_AUTO.png"
        im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if im is None:raise IOError(path)
        reduced=cv2.resize(im,(1270,387),interpolation=cv2.INTER_AREA)
        frames.append(reduced)
    if len(frames)!=9:
        raise AssertionError("expected all nine evaluated ROI windows")
    big=np.concatenate(frames,axis=0)
    ok,buf=cv2.imencode(".png",big,[cv2.IMWRITE_PNG_COMPRESSION,4])
    if not ok:raise IOError("contact encode")
    out=run/"figures"/"E2_all_9_windows_contact_sheet.png"
    out.write_bytes(buf.tobytes())
    print("CONTACT_READY",out,"shape",big.shape)
    return out

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-dir",type=Path,default=RUN)
    args=parser.parse_args()
    build(args.run_dir)
