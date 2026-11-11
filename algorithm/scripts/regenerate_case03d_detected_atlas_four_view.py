"""Standalone safe regenerating only atlas_detected_top12 with four aligned views.

Reads frozen Case03-D output. The previous PNG must have been backed up as
atlas_detected_top12_legacy_selected_only.png before this is invoked.
Never runs detection/classification, writes masks, or changes candidate IDs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from config import user_config as cfg
from src.detection.thresholding import load_packed_mask
from src.visualization.case03d_detected_atlas import atlas_four_view

RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"
HNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_H_TL170_TH230.npz"
SNPZ=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1/fused_S_TL230_TH230.npz"


def regenerate(output_dir:Path=RUN, *, overwrite_existing:bool=True)->dict:
    figure_dir=output_dir/"figures"
    oldpath=figure_dir/"atlas_detected_top12.png"
    backup=figure_dir/"atlas_detected_top12_legacy_selected_only.png"
    if overwrite_existing and oldpath.exists() and not backup.is_file():
        raise RuntimeError("Must preserve the old PNG before overwriting historical figure")
    all_detected=pd.read_csv(output_dir/"detected_provisional.csv",
                             dtype={"candidate_id":str},low_memory=False)
    if len(all_detected)!=139 or all_detected["candidate_id"].duplicated().any():
        raise ValueError("Unexpected source AUTO candidate population")
    if not all_detected["triage_status"].eq("detected_provisional").all():
        raise ValueError("AUTO candidate status mismatch")
    rows=all_detected.sort_values(
        ["peak_response_dn","area_px"],ascending=[False,False],kind="mergesort"
    ).head(12).to_dict("records")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",dtype=">u2",
                  mode="r",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    H=load_packed_mask(HNPZ)
    S=load_packed_mask(SNPZ)
    with np.load(output_dir/"candidate_status_map_lossless.npz",allow_pickle=False) as npz:
        classes=npz["class_map"]
    if not (raw.shape==H.shape==S.shape==classes.shape==(9200,11276)):
        raise AssertionError("Source shape mismatch")
    if np.any((classes==3)&~H):
        raise AssertionError("Detected class pixels not in original H")
    image,details=atlas_four_view(rows,all_detected.to_dict("records"),
                                  raw,H,S,classes,size=160,columns=3)
    if len(rows)!=12:
        raise AssertionError("No longer have 12 selected auto candidates")
    # The first-row third card contains two independent detected dark spots.
    third={x["auto_candidate_id"] for x in details if x["atlas_card_index"]==3}
    expected={"H_sample26_0406312","H_sample26_0408029"}
    if not expected.issubset(third):
        raise AssertionError(f"Evidence failed: atlas first row third card only shows {third}")
    df=pd.DataFrame(details)
    df.to_csv(output_dir/"atlas_detected_top12_roi_numbers.csv",
              index=False,encoding="utf-8-sig")
    # Historical original saved by previous code; use atomic image replacement.
    ok,buf=cv2.imencode(".png",image,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise IOError("unable to encode four-panel atlas")
    destination=oldpath if overwrite_existing else figure_dir/"atlas_detected_top12_four_panel_v2.png"
    temp=figure_dir/(destination.stem+".tmp.png")
    temp.write_bytes(buf.tobytes())
    temp.replace(destination)
    metadata={
        "figure":str(destination),
        "legacy_backup":str(backup),
        "source_auto_detection_count":len(all_detected),
        "atlas_card_count":len(rows),
        "roi_objects_numbered_total":len(details),
        "third_card_detected_ids":sorted(third),
        "expected_two_spots_both_present":expected.issubset(third),
        "four_columns":["1 RAW","2 ALL S/H","3 ALL AUTO in ROI",
                        "4 SELECTED current candidate only"],
        "green_is_auto_provisional_not_physically_confirmed":True,
        "all_labels_local_to_each_ROI":True,
        "no_classification_or_mask_modified":True,
        "image_shape":[int(v) for v in image.shape]
    }
    (output_dir/"atlas_detected_top12_four_view_validation.json").write_text(
        json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    print("FOUR_PANEL_ATLAS",destination)
    print("FOUR_PANEL_CHECK",json.dumps(metadata,ensure_ascii=False))
    return metadata


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",default=str(RUN))
    parser.add_argument("--no-overwrite",action="store_true")
    args=parser.parse_args()
    regenerate(Path(args.output_dir),overwrite_existing=not args.no_overwrite)
