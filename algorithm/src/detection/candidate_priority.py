"""Case03-D: non-destructive, unsupervised candidate review priority.

The score is a *review ordering*, not probability of physical filter defects.
No human labels are inputs to the score. Tiers are capacity-based top fractions,
never deletion or high/medium/low scientific confidence.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd


def rank_percentile_ties(values: pd.Series) -> np.ndarray:
    """Return average-tie empirical ranking in (0,1], without label training."""
    numeric=pd.to_numeric(values,errors="coerce")
    if numeric.isna().any() or not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("unavailable/nonfinite candidate feature, refuse silent imputation")
    if (numeric.to_numpy(dtype=float)<0).any():
        raise ValueError("negative physical feature forbidden")
    # scipy rankdata average-ties yields stable and fair percentile for one-pixel ties.
    return numeric.rank(method="average",pct=True).to_numpy(dtype=float)


def build_priority(
    frame: pd.DataFrame,
    *,
    area_weight: float=0.5,
    peak_weight: float=0.5,
    first_tier_fraction: float=0.01,
    second_tier_cumulative_fraction: float=0.10,
) -> pd.DataFrame:
    """Return complete scores/ranks/tier for all H components (no dropped rows).

    Primary predeclared score: weighted mean of *all-image percentile ranks*
    for area and peak Black-Hat DN. Baselines are each individual percentile
    rank. User ground truth must NEVER be passed to score construction.
    """
    required={"candidate_id","area_px","peak_response_dn"}
    if required-set(frame.columns):
        raise ValueError(f"missing required fields: {sorted(required-set(frame.columns))}")
    n=len(frame)
    if n==0 or frame["candidate_id"].isna().any() or frame["candidate_id"].duplicated().any():
        raise ValueError("candidates must have unique nonmissing IDs")
    if not math.isclose(area_weight+peak_weight,1.,abs_tol=1.e-12) or min(area_weight,peak_weight)<=0:
        raise ValueError("positive weights must sum to one")
    if not (0<first_tier_fraction<second_tier_cumulative_fraction<1):
        raise ValueError("invalid review-budget tier fractions")
    out=pd.DataFrame(index=frame.index)
    out["candidate_id"]=frame["candidate_id"].astype(str)
    area=pd.to_numeric(frame["area_px"],errors="raise")
    peak=pd.to_numeric(frame["peak_response_dn"],errors="raise")
    if (area<1).any() or (peak<0).any():
        raise ValueError("invalid feature values")
    out["area_percentile"]=rank_percentile_ties(area)
    out["peak_percentile"]=rank_percentile_ties(peak)
    out["review_score"]=area_weight*out["area_percentile"]+peak_weight*out["peak_percentile"]
    # deterministic descending review order. ID used only as tie-breaker.
    primary=out.assign(_area=area,_peak=peak).sort_values(
        ["review_score","_peak","_area","candidate_id"],
        ascending=[False,False,False,True],kind="mergesort"
    )
    if primary["candidate_id"].duplicated().any() or len(primary)!=n:
        raise AssertionError("score changed candidate population")
    primary["priority_rank"]=np.arange(1,n+1,dtype=np.int64)
    a=int(math.ceil(n*first_tier_fraction))
    b=int(math.ceil(n*second_tier_cumulative_fraction))
    primary["review_tier"]=np.where(primary["priority_rank"]<=a,"A_first_review",
                              np.where(primary["priority_rank"]<=b,"B_second_review","C_later_review"))
    # baselines for comparison; both independent of labels, save deterministic rank.
    area_baseline=primary.sort_values(
        ["_area","_peak","candidate_id"],ascending=[False,False,True],kind="mergesort"
    )
    peak_baseline=primary.sort_values(
        ["_peak","_area","candidate_id"],ascending=[False,False,True],kind="mergesort"
    )
    area_rank=pd.Series(np.arange(1,n+1,dtype=np.int64),index=area_baseline["candidate_id"].to_numpy())
    peak_rank=pd.Series(np.arange(1,n+1,dtype=np.int64),index=peak_baseline["candidate_id"].to_numpy())
    primary["baseline_area_only_rank"]=primary["candidate_id"].map(area_rank).astype(np.int64)
    primary["baseline_peak_only_rank"]=primary["candidate_id"].map(peak_rank).astype(np.int64)
    output=primary.drop(columns=["_area","_peak"]).set_index("candidate_id").loc[frame["candidate_id"]].reset_index()
    if len(output)!=n or output["candidate_id"].duplicated().any():
        raise AssertionError("ranking lost candidates")
    return output


def evaluate_review_budget(
    scores: pd.DataFrame,
    labels: Mapping[str,str],
    *,
    budgets: tuple[int,...]=(100,500,1000,5000),
    manual_truth_provenance: str="human-selected same-image, NOT independent GT",
) -> tuple[list[dict],list[dict]]:
    """Compute review coverage among *labeled* H objects only, not image recall.

    Positive/negative labels have to be independently assigned to candidate IDs.
    AUC/ROC cannot be interpreted as full-image detection sensitivity.
    """
    n=len(scores)
    by_id=scores.set_index("candidate_id")
    if not by_id.index.is_unique:
        raise ValueError("duplicate score candidate IDs")
    unknown=set(labels)-set(by_id.index)
    if unknown:raise ValueError(f"labeled candidate missing: {list(sorted(unknown))[:8]}")
    pos={k for k,v in labels.items() if v=="confirmed_dark_spot"}
    neg={k for k,v in labels.items() if v=="background_artifact"}
    if len(pos)+len(neg)!=len(labels):
        raise ValueError("only reviewed dark-spot and background-artifact labels accepted")
    rank_columns={
        "combined_area_peak":"priority_rank",
        "area_only":"baseline_area_only_rank",
        "peak_only":"baseline_peak_only_rank"
    }
    detailed=[]
    for cid,label in sorted(labels.items()):
        data=by_id.loc[cid]
        detailed.append({
            "candidate_id":cid,"manual_label":label,
            "review_score":round(float(data["review_score"]),9),
            "review_tier":data["review_tier"],
            "primary_rank":int(data["priority_rank"]),
            "area_only_rank":int(data["baseline_area_only_rank"]),
            "peak_only_rank":int(data["baseline_peak_only_rank"]),
            "relative_review_percentile_rank":round(100*int(data["priority_rank"])/n,4),
            "label_origin":manual_truth_provenance
        })
    budgets_sorted=tuple(sorted({min(n,int(k)) for k in budgets if int(k)>0}
                                |{int(math.ceil(.01*n)),int(math.ceil(.1*n)),n}))
    results=[]
    for method,field in rank_columns.items():
        for budget in budgets_sorted:
            p=sum(int(by_id.loc[k,field])<=budget for k in pos)
            z=sum(int(by_id.loc[k,field])<=budget for k in neg)
            results.append({
                "method":method,"budget_rank_top_n":budget,
                "candidate_fraction_all":round(budget/n,7),
                "label_positive_in_top_n":p,"positive_total_labeled":len(pos),
                "label_positive_coverage":round(p/len(pos),6) if pos else "",
                "label_negative_in_top_n":z,"negative_total_labeled":len(neg),
                "label_negative_coverage":round(z/len(neg),6) if neg else "",
                "validity":"EXPLORATORY_SAME_SAMPLE_NONRANDOM_LABELS",
                "warning":"Coverage of labeled objects only; cannot measure full-image recall, precision, or defect probability."
            })
    return detailed,results
