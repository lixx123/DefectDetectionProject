"""Regenerate Case03-C-R1 review figures using installed CJK fonts and saved exact ROI masks."""
import argparse
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.revise_case03c_evidence import render_roi
from src.detection.feature_discrimination import read_csv_rows


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-dir",required=True)
    args=ap.parse_args()
    folder=Path(args.output_dir)
    if not folder.is_absolute():folder=ROOT/folder
    manifest=read_csv_rows(folder/"reference_geometry_audit.csv")
    src=ROOT/"outputs"/"case03c"/"run_20261008_174000"
    features={r["candidate_id"]:r for r in read_csv_rows(src/"hysteresis_candidate_features.csv")}
    for i,r in enumerate(manifest,1):
        cid=r["candidate_id"]
        feat=features.get(cid)
        with np.load(folder/r["patch"],allow_pickle=False) as n:
            raw=n["raw_dn"];response=n["response_dn"]
            s=n["S230"];h=n["H170_230"];selected=n["selected_candidate"]
            eligible=n["reference_eligible_in_roi"];used=n["reference_sample_used_in_roi"]
        meta={
            "review_id":r["review_id"],"candidate_id":cid or "(background ROI)",
            "eligible_count":int(r["global_eligible_count"]),
            "sample_count":int(r["global_reference_sample_count"]),
            "valid":r["valid_reference"]=="True",
            "invalid_reason":r["invalid_reason"],
            "bg_median_dn":feat["raw_background_median_dn"] if feat else "",
            "raw_delta_dn":feat["raw_delta_dn"] if feat else "",
            "bg_mad_dn":feat["background_noise_mad_dn"] if feat else "",
        }
        render_roi(folder/r["figure"],raw,response,s,h,selected,eligible,used,meta)
        if i%10==0:print("RERENDER_CJK",i,flush=True)
    print("RERENDER_DONE",len(manifest),flush=True)


if __name__=="__main__":
    main()
