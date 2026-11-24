"""Redraw the existing Case03-D AUTO top12 atlas with three panels.

Exactly: 1 RAW; 2 ALL S/H; 3 ALL AUTO in ROI, numbered.
Does not reclassify, re-threshold or touch historical source masks.
Original selected-only and four-panel images are backed up separately.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from src.visualization.case03d_detected_atlas import atlas_three_view

RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
MASKS=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"


def regenerate(output_dir:Path=RUN)->dict:
    folder=output_dir/"figures"
    target=folder/"atlas_detected_top12.png"
    four_backup=folder/"atlas_detected_top12_four_panel_backup.png"
    first_backup=folder/"atlas_detected_top12_legacy_selected_only.png"
    if target.exists() and not (four_backup.is_file() and first_backup.is_file()):
        raise RuntimeError("Both legacy images must be backed up before overwriting")
    df=pd.read_csv(output_dir/"detected_provisional.csv",
                   dtype={"candidate_id":str},low_memory=False)
    if len(df)!=139 or df["candidate_id"].duplicated().any():
        raise AssertionError("source detected candidate identities invalid")
    if not df["triage_status"].eq("detected_provisional").all():
        raise AssertionError("source detection classification mismatch")
    rows=df.sort_values(["peak_response_dn","area_px"],
                        ascending=[False,False],kind="mergesort").head(12).to_dict("records")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    H=load_packed_mask(MASKS/"fused_H_TL170_TH230.npz")
    S=load_packed_mask(MASKS/"fused_S_TL230_TH230.npz")
    with np.load(output_dir/"candidate_status_map_lossless.npz",allow_pickle=False) as z:
        classes=z["class_map"]
    if not (raw.shape==H.shape==S.shape==classes.shape==(9200,11276)):
        raise AssertionError("input shape mismatch")
    if np.any((classes==3)&~H):
        raise AssertionError("class 3 outside H")
    atlas,evidence=atlas_three_view(
        rows,df.to_dict("records"),raw,H,S,classes,size=160,columns=3
    )
    third=[r for r in evidence if r["atlas_card_index"]==3]
    if not {
        "H_sample26_0405250","H_sample26_0406312","H_sample26_0408029"
    }.issubset({r["auto_candidate_id"] for r in third}):
        raise AssertionError("lower detected spot missing from third card")
    if len(evidence)!=16 or len(rows)!=12:
        raise AssertionError("unexpected ROI candidate audit population")
    pd.DataFrame(evidence).to_csv(
        output_dir/"atlas_detected_top12_roi_numbers.csv",
        index=False,encoding="utf-8-sig"
    )
    ok,png=cv2.imencode(".png",atlas,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise IOError("3-panel atlas PNG encode failed")
    tmp=folder/"atlas_detected_top12.temporary.png"
    tmp.write_bytes(png.tobytes())
    tmp.replace(target)
    metadata={
        "current_file":str(target),
        "previous_four_panel_backup":str(four_backup),
        "original_selected_only_backup":str(first_backup),
        "panels":["1 RAW","2 ALL S/H","3 ALL AUTO in ROI"],
        "atlas_card_count":len(rows),
        "roi_numbered_components":len(evidence),
        "third_card_candidate_ids":sorted(r["auto_candidate_id"] for r in third),
        "selected_id_in_third_card":"H_sample26_0406312",
        "source_auto_candidate_count":len(df),
        "all_H_component_labels_local_to_each_ROI":True,
        "no_detection_or_classification_changes":True,
        "auto_is_provisional_not_confirmed_physical_defect":True,
        "shape":[int(x) for x in atlas.shape]
    }
    (output_dir/"atlas_detected_top12_three_panel_validation.json").write_text(
        json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    print("THREE_PANEL_ATLAS",target)
    print("THREE_PANEL_VALIDATION",json.dumps(metadata,ensure_ascii=False))
    return metadata


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",default=str(RUN))
    args=parser.parse_args()
    regenerate(Path(args.output_dir))
