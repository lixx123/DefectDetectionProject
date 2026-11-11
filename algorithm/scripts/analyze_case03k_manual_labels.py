"""Case03-K1: read completed manual classifications and compare noise features.

Does not estimate recall from target-enriched sampled ROIs. Does not fit or
update detector parameters. Treats UNCERTAIN as unresolved and excludes it
from exploratory real-versus-noise features. A separate untouched frame is
required for independent validation before deploying a noise filter.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd,numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg

DEFAULT=cfg.OUTPUT_ROOT/(
    "case03k_light_review/run_20261012_small_candidate_manual_review_v2/manual_review_template.csv")
KEYS=("source_area_px2","source_max_feret_px","target_blackhat_peak_DN",
      "target_relative_dark_contrast","target_dark_z_MAD",
      "target_DoG_median_DN","nearest_medium_large_center_distance_px",
      "window_MAD_RAW_DN","window_STD_RAW_DN")
ALLOWED={"","REAL_MICRO_DEFECT","BACKGROUND_NOISE","UNCERTAIN"}


def analyze(path:Path)->dict:
    df=pd.read_csv(path,encoding="utf-8-sig",keep_default_na=False)
    if "manual_candidate_label" not in df:raise ValueError("missing manual label field")
    if not set(df["manual_candidate_label"]).issubset(ALLOWED):
        bad=set(df["manual_candidate_label"])-ALLOWED
        raise ValueError(f"invalid manual label values: {bad}")
    candidates=df[df.sample_kind=="SMALL_CANDIDATE"].copy()
    background=df[df.sample_kind=="NO_J5_CANDIDATE_ROI"].copy()
    if background.manual_candidate_label.ne("").any():
        raise ValueError("background ROIs do not contain a defined candidate target")
    labeled=candidates[candidates.manual_candidate_label.isin(
        ["REAL_MICRO_DEFECT","BACKGROUND_NOISE"])].copy()
    uncertain=(candidates.manual_candidate_label=="UNCERTAIN").sum()
    completed_review=(df.manual_complete_roi_review.astype(str)
                      .str.upper().isin(["TRUE","YES","1"])).sum()
    report={
        "stage":"K1_LABEL_ANALYSIS",
        "source_table":str(path),
        "sampled_green_objects":len(candidates),
        "manually_decided_green_objects":len(labeled),
        "manual_real":int((labeled.manual_candidate_label=="REAL_MICRO_DEFECT").sum()),
        "manual_noise":int((labeled.manual_candidate_label=="BACKGROUND_NOISE").sum()),
        "unresolved_uncertain":int(uncertain),
        "manually_completely_reviewed_ROIs":int(completed_review),
        "population_precision_NOT_estimated":True,
        "recall_NOT_estimated_from_cropped_candidate_sample":True,
        "algorithm_parameters_changed":False,
        "exploratory_data_only":True
    }
    if report["manual_real"]<5 or report["manual_noise"]<5:
        report["feature_comparison"]="INSUFFICIENT_LABELS: at least 5 verified real and 5 noise examples"
    else:
        stats=[]
        for k in KEYS:
            for category in ("REAL_MICRO_DEFECT","BACKGROUND_NOISE"):
                a=pd.to_numeric(labeled.loc[
                    labeled.manual_candidate_label==category,k],
                    errors="coerce").dropna().astype(float)
                stats.append({
                    "feature":k,"manual_category":category,"sample_count":len(a),
                    "median":float(a.median()) if len(a) else None,
                    "p25":float(a.quantile(.25)) if len(a) else None,
                    "p75":float(a.quantile(.75)) if len(a) else None,
                })
        out=path.with_name("manual_labels_feature_comparison.csv")
        # Never overwrite original manual annotations or prior analysis.
        if out.exists():raise FileExistsError(out)
        pd.DataFrame(stats).to_csv(out,index=False,encoding="utf-8-sig")
        report["feature_comparison"]=str(out)
    outjson=path.with_name("manual_labels_exploratory_report.json")
    if outjson.exists():raise FileExistsError(outjson)
    outjson.write_text(json.dumps(report,ensure_ascii=False,indent=2),
                       encoding="utf-8")
    print("K1_MANUAL_REVIEW_STATUS",json.dumps(report,ensure_ascii=False),flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--reviewed-csv",default=str(DEFAULT))
    opts=p.parse_args()
    analyze(Path(opts.reviewed_csv))
