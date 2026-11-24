"""Exploratory Case03-C feature analysis; no truth labels are manufactured.

AUC is calculated only from independent human-reviewed candidate IDs. Duplicate
ROI views are collapsed by candidate ID, and conflicting labels are rejected.
Without at least five positives and five negatives, separability is PENDING.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import csv
import numpy as np
from scipy.stats import rankdata

FEATURES = (
    "area_px", "seed_area_px", "growth_ratio_px", "core_component_count",
    "peak_response_dn", "mean_response_dn", "bbox_aspect_ratio",
    "bbox_fill_ratio", "linearity_proxy", "raw_delta_dn",
    "background_noise_mad_dn", "contrast_to_noise_proxy",
)
POSITIVE={"confirmed_dark_spot","confirmed_fine_line"}
NEGATIVE={"background_artifact","instrument_marker"}
ALLOWED=POSITIVE|NEGATIVE|{"uncertain"}


def read_csv_rows(path: Path) -> list[dict]:
    with path.open("r",encoding="utf-8-sig",newline="") as file:
        return list(csv.DictReader(file))


def numeric(value) -> float | None:
    if value is None or value=="":
        return None
    try:
        x=float(value)
    except (TypeError,ValueError):
        return None
    return x if np.isfinite(x) else None


def unique_manual_labels(rows: list[dict]) -> tuple[dict[str,str], dict]:
    """Require coherent reviewer status and deduplicate by candidate_id."""
    labels={}
    status=Counter()
    for row in rows:
        candidate=row.get("candidate_id","").strip()
        label=row.get("manual_label","").strip()
        review_status=row.get("review_status","").strip()
        if not label:
            status["unlabeled"]+=1
            continue
        if label not in ALLOWED:
            raise ValueError(f"invalid manual_label: {label!r}")
        if review_status.lower() not in {"reviewed","done","confirmed"}:
            raise ValueError(f"{candidate}: label supplied but review_status is not reviewed")
        if not candidate:
            raise ValueError("reviewed entry is missing candidate_id")
        if candidate in labels and labels[candidate]!=label:
            raise ValueError(f"conflicting reviewer labels for candidate {candidate}")
        labels[candidate]=label
        status["reviewed_rows"]+=1
    status["unique_reviewed_candidates"]=len(labels)
    status.update({f"label_{key}":value for key,value in Counter(labels.values()).items()})
    return labels,dict(status)


def auc_positive_higher(positive: np.ndarray, negative: np.ndarray) -> float:
    """Mann-Whitney rank AUC with averaged ties, no direction flipping."""
    x=np.asarray(positive,dtype=np.float64)
    y=np.asarray(negative,dtype=np.float64)
    if x.size==0 or y.size==0:
        raise ValueError("two groups are required")
    ranks=rankdata(np.concatenate([x,y]),method="average")
    return float((ranks[:x.size].sum()-x.size*(x.size+1)/2)/(x.size*y.size))


def exploratory_auc(rows:list[dict], labels:dict[str,str], *, minimum_per_group:int=5,
                    bootstrap_iterations:int=300, seed:int=20261009) -> list[dict]:
    """AUC per feature only if sufficient human labels exist. No fitted models."""
    row_index={r["candidate_id"]:r for r in rows}
    if set(labels)-set(row_index):
        raise ValueError(f"review IDs not in feature table: {sorted(set(labels)-set(row_index))[:5]}")
    results=[]
    for feature in FEATURES:
        pos=np.array([v for cid,lab in labels.items() if lab in POSITIVE
                      if (v:=numeric(row_index[cid].get(feature))) is not None],dtype=float)
        neg=np.array([v for cid,lab in labels.items() if lab in NEGATIVE
                      if (v:=numeric(row_index[cid].get(feature))) is not None],dtype=float)
        record={"feature":feature,"positive_n":len(pos),"negative_n":len(neg),
                "status":"PENDING_LABELS","auc_positive_higher":"","ci95_low":"","ci95_high":"",
                "positive_median":"","negative_median":"","limitations":"reviewed case26 candidates only; selected sample; no external test set"}
        if len(pos)>=minimum_per_group and len(neg)>=minimum_per_group:
            rng=np.random.default_rng(seed)
            auc=auc_positive_higher(pos,neg)
            boots=np.asarray([auc_positive_higher(rng.choice(pos,len(pos),replace=True),
                                                   rng.choice(neg,len(neg),replace=True))
                              for _ in range(bootstrap_iterations)])
            record.update(status="EXPLORATORY_ONLY",auc_positive_higher=round(auc,6),
                          ci95_low=round(float(np.percentile(boots,2.5)),6),
                          ci95_high=round(float(np.percentile(boots,97.5)),6),
                          positive_median=float(np.median(pos)),
                          negative_median=float(np.median(neg)))
        results.append(record)
    return results


def unlabeled_distributions(rows:list[dict]) -> list[dict]:
    """Area/edge proxy strata have NO noise or defect labels."""
    sets={
        "all_unlabeled":rows,
        "area_1px_proxy":[r for r in rows if int(r["area_px"])==1],
        "area_2to19px_proxy":[r for r in rows if 2<=int(r["area_px"])<=19],
        "area_ge20px_proxy":[r for r in rows if int(r["area_px"])>=20],
        "near_transition_proxy":[r for r in rows if r["near_band_transition"]=="True"],
        "not_near_transition_proxy":[r for r in rows if r["near_band_transition"]=="False"],
    }
    summary=[]
    for name,subset in sets.items():
        for feature in FEATURES:
            arr=np.array([v for row in subset if (v:=numeric(row.get(feature))) is not None],dtype=float)
            item={"stratum":name,"feature":feature,"candidate_rows":len(subset),
                  "numeric_count":len(arr),"median":"","p25":"","p75":"","p90":""}
            if len(arr):
                item.update(median=float(np.median(arr)),
                            p25=float(np.percentile(arr,25)),
                            p75=float(np.percentile(arr,75)),
                            p90=float(np.percentile(arr,90)))
            summary.append(item)
    return summary
