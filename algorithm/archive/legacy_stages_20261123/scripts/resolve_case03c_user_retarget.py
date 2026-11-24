"""Link user-selected RAW pixels to exact Case03-B S/H connected components.

Uses original full-resolution losslessly restored binary masks and a bounded-
size BFS to identify the *actual pixel-containing* 8-connected component.
Matches the pixel component to Case03-C feature rows by full bbox+area.
No guessed component IDs for unsegmented clicked pixels. Never modifies inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from src.detection.thresholding import load_packed_mask
from src.detection.feature_discrimination import (
    read_csv_rows,unique_manual_labels,exploratory_auc
)

SOURCE_LABELS=ROOT/"outputs/case03c/run_20261008_174000"
SOURCE_MASKS=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"
ANNOTATION_DEFAULT=Path(r"C:\Users\lixia\Downloads\case03c_sample26_user_retarget.csv")
PREVIOUS_AUDIT=ROOT/"outputs/case03c_label_analysis/run_20261009_manual_review_v1"
EXPECTED_REVIEWS={18,19,21,24,27,31,39,46,56}
EXPECTED_SID={"S230_yellow","H170_only_cyan","no_segmented_pixel"}


def digest(path:Path)->dict:
    st=path.stat()
    if path.stat().st_size<3_000_000:
        return {"name":str(path),"bytes":st.st_size,"mtime_ns":st.st_mtime_ns,
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"name":str(path),"bytes":st.st_size,"mtime_ns":st.st_mtime_ns}


def write_csv(path:Path,rows:list[dict]):
    if not rows:
        path.write_text("",encoding="utf-8")
        return
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)


def lookup_by_geometry(feature_rows:list[dict])->dict[tuple[int,int,int,int,int],list[dict]]:
    ans={}
    for r in feature_rows:
        key=tuple(int(r[k]) for k in ("bbox_x","bbox_y","bbox_w","bbox_h","area_px"))
        ans.setdefault(key,[]).append(r)
    return ans


def flood_8_component(mask:np.ndarray, x:int,y:int, *, maximum_pixels:int=250000)->dict|None:
    """Exact connected pixel set; never crops the image or relabels tile borders."""
    height,width=mask.shape
    if not (0<=x<width and 0<=y<height):
        raise ValueError("point outside mask")
    if not bool(mask[y,x]):
        return None
    queue=deque([(x,y)])
    seen={(x,y)}
    minx=maxx=x
    miny=maxy=y
    while queue:
        px,py=queue.popleft()
        if px<minx:minx=px
        if py<miny:miny=py
        if px>maxx:maxx=px
        if py>maxy:maxy=py
        for dy in (-1,0,1):
            cy=py+dy
            if cy<0 or cy>=height:continue
            for dx in (-1,0,1):
                if dx==0 and dy==0:continue
                cx=px+dx
                if cx<0 or cx>=width:continue
                if bool(mask[cy,cx]) and (cx,cy) not in seen:
                    seen.add((cx,cy))
                    if len(seen)>maximum_pixels:
                        raise MemoryError("candidate unexpectedly exceeds max contiguous size")
                    queue.append((cx,cy))
    return {"bbox_x":minx,"bbox_y":miny,"bbox_w":maxx-minx+1,"bbox_h":maxy-miny+1,
            "area_px":len(seen),"pixels":seen}


def match_component(mask:np.ndarray, feature_idx:dict, x:int,y:int, cache:dict)->tuple[dict|None,dict|None]:
    """match using complete component geometry, with exhaustive pixel connectivity."""
    if not bool(mask[y,x]):
        return None,None
    key=(x,y)
    if key in cache:
        return cache[key]
    geom=flood_8_component(mask,x,y)
    bbox=tuple(geom[k] for k in ("bbox_x","bbox_y","bbox_w","bbox_h","area_px"))
    candidates=feature_idx.get(bbox,[])
    if len(candidates)!=1:
        raise AssertionError(f"pixel at ({x},{y}) has ambiguous/missing global candidate {bbox}: {len(candidates)} matches")
    feature=candidates[0]
    result=feature,{k:v for k,v in geom.items() if k!="pixels"}
    for xy in geom["pixels"]:
        cache[xy]=result
    return result


def nearest_mask_pixel(mask:np.ndarray,x:int,y:int, *, radius:int=24):
    h,w=mask.shape
    xa=max(0,x-radius);xb=min(w,x+radius+1)
    ya=max(0,y-radius);yb=min(h,y+radius+1)
    local=mask[ya:yb,xa:xb]
    yy,xx=np.nonzero(local)
    if xx.size==0:return None
    dx=xx+(xa-x);dy=yy+(ya-y)
    distance_sq=dx*dx+dy*dy
    idx=int(np.argmin(distance_sq))
    return {"x":int(xx[idx]+xa),"y":int(yy[idx]+ya),
            "euclidean_distance_px":round(float(math.sqrt(float(distance_sq[idx]))),3)}


def validate_annotation(row:dict, s:np.ndarray,h:np.ndarray)->dict:
    review=int(row["review_id"].split("_")[-1])
    if review not in EXPECTED_REVIEWS or row["source_sample"]!="26" or row["source_frame"]!="1":
        raise ValueError(f"unexpected annotation source {row['review_id']}")
    if row["mode"] not in ("point","box"):raise ValueError("unexpected annotation mode")
    if row["mode"]=="point":
        x=int(row["raw_global_x"]);y=int(row["raw_global_y"])
        if not(0<=x<s.shape[1] and 0<=y<s.shape[0]):raise ValueError("point out of bounds")
        actual="S230_yellow" if s[y,x] else "H170_only_cyan" if h[y,x] else "no_segmented_pixel"
        if actual!=row["mask_membership_at_point"]:
            raise ValueError(f"browser PNG/CSV mismatch {row.get('annotation_id', 'unknown')} {actual} vs {row['mask_membership_at_point']}")
        return {"membership_verified":actual}
    x0=int(row["raw_global_x0"]);y0=int(row["raw_global_y0"])
    x1=int(row["raw_global_x1"]);y1=int(row["raw_global_y1"])
    if not(0<=x0<x1<=s.shape[1] and 0<=y0<y1<=s.shape[0]):
        raise ValueError("invalid ROI box")
    ns=int(s[y0:y1,x0:x1].sum());nh=int(h[y0:y1,x0:x1].sum())
    if ns!=int(row["box_S230_pixel_count"]) or nh!=int(row["box_H170_pixel_count"]):
        raise AssertionError(f"box count mismatch: {row['annotation_id']}")
    return {"membership_verified":"box_not_pixel_gt","area_box_px":(x1-x0)*(y1-y0),
            "box_S230_pixels":ns,"box_H170_pixels":nh,
            "box_S230_coverage_pct":round(100*ns/((x1-x0)*(y1-y0)),4),
            "box_H170_coverage_pct":round(100*nh/((x1-x0)*(y1-y0)),4)}


def consolidate_labels(positive_ids:set[str], feature_rows:list[dict])->list[dict]:
    original=read_csv_rows(PREVIOUS_AUDIT/"labels_conservative_note_aligned.csv")
    base,counts=unique_manual_labels(original)
    assert len(base)==49 and counts.get("label_confirmed_dark_spot")==10 and counts.get("label_background_artifact")==39
    clashes=positive_ids & {x for x,v in base.items() if v=="background_artifact"}
    if clashes:raise ValueError(f"New human targets clash with existing negatives: {sorted(clashes)}")
    for k in positive_ids:base[k]="confirmed_dark_spot"
    feat_ids={r["candidate_id"] for r in feature_rows}
    if set(base)-feat_ids:raise ValueError("one or more user candidate IDs missing from H feature table")
    return [{"candidate_id":k,"manual_label":v,"review_status":"reviewed",
             "provenance":"new_exact_pixel" if k in positive_ids else "prior_10_positive_39_negative"} for k,v in sorted(base.items())]


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",default=str(ANNOTATION_DEFAULT))
    p.add_argument("--run-id",default=None)
    a=p.parse_args()
    source=Path(a.input)
    if not source.is_file():raise FileNotFoundError(source)
    outroot=ROOT/"outputs/case03c_label_analysis"
    name=a.run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
    dest=outroot/name
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True)
    inputs=[source,SOURCE_MASKS/"fused_S_TL230_TH230.npz",SOURCE_MASKS/"fused_H_TL170_TH230.npz",
            SOURCE_LABELS/"hysteresis_candidate_features.csv",SOURCE_LABELS/"s230_candidate_features.csv"]
    before=[digest(x) for x in inputs]
    anno=read_csv_rows(source)
    h_features=read_csv_rows(inputs[3])
    s_features=read_csv_rows(inputs[4])
    h_idx=lookup_by_geometry(h_features)
    s_idx=lookup_by_geometry(s_features)
    S=load_packed_mask(inputs[1])
    H=load_packed_mask(inputs[2])
    if S.shape!=(9200,11276) or H.shape!=S.shape or np.any(S & ~H):
        raise ValueError("input H/S masks invalid")
    s_cache={};h_cache={}
    outputs=[]
    directly_mapped=set()
    for row in anno:
        meta=validate_annotation(row,S,H)
        item=dict(row)
        item.update(meta)
        if row["mode"]=="point":
            x,y=int(row["raw_global_x"]),int(row["raw_global_y"])
            item["exact_H_candidate_id"]=""
            item["exact_S_candidate_id"]=""
            item["retarget_status"]="NO_SEGMENTED_PIXEL_AT_TARGET"
            item["nearest_H_candidate_id_suggestion"]=""
            item["nearest_S_candidate_id_suggestion"]=""
            if H[y,x]:
                hf,hgeo=match_component(H,h_idx,x,y,h_cache)
                item["exact_H_candidate_id"]=hf["candidate_id"]
                item["H_area_px"]=int(hf["area_px"])
                item["H_peak_response_dn"]=int(hf["peak_response_dn"])
                item["H_growth_ratio_px"]=hf["growth_ratio_px"]
                item["H_core_component_count"]=int(hf["core_component_count"])
                item["H_raw_reference_valid"]=hf["raw_reference_valid"]
                item["H_raw_delta_dn"]=hf["raw_delta_dn"]
                item["retarget_status"]="EXACT_H_CONNECTED_COMPONENT_FROM_PIXEL"
                if row["label"] in {"visual_dark_spot","visual_fine_line"}:
                    directly_mapped.add(hf["candidate_id"])
                if S[y,x]:
                    sf,sgeo=match_component(S,s_idx,x,y,s_cache)
                    item["exact_S_candidate_id"]=sf["candidate_id"]
                    if sf["h_candidate_id"] != hf["candidate_id"]:
                        raise AssertionError(f"S↔H exact pixel candidate link mismatch: {x},{y}")
            else:
                for prefix,mask,idx,cache in (("H",H,h_idx,h_cache),("S",S,s_idx,s_cache)):
                    near=nearest_mask_pixel(mask,x,y,radius=24)
                    if near:
                        item[f"nearest_{prefix}_distance_px"]=near["euclidean_distance_px"]
                        item[f"nearest_{prefix}_pixel_x"]=near["x"]
                        item[f"nearest_{prefix}_pixel_y"]=near["y"]
                        candidate,_=match_component(mask,idx,near["x"],near["y"],cache)
                        item[f"nearest_{prefix}_candidate_id_suggestion"]=candidate["candidate_id"]
                item["retarget_status"]="POINT_NOT_IN_MASK_REVIEW_RING_OR_MISSED"
        else:
            item["retarget_status"]="BOX_REGION_NOT_A_SINGLE_COMPONENT"
            item["exact_H_candidate_id"]=""
            item["exact_S_candidate_id"]=""
            item["box_quality_note"]="Box coverage is a proxy, not pixel-perfect manual segmentation mask"
        outputs.append(item)
        print(item["review_id"],row["mode"],item["retarget_status"],
              item.get("exact_H_candidate_id",""),
              ("near_H="+str(item.get("nearest_H_distance_px",""))),flush=True)
    assert len(outputs)==len(anno)
    if len({r["annotation_id"] for r in outputs}) != len(outputs):
        raise ValueError("duplicate user annotation id")
    write_csv(dest/"pixel_retarget_associations.csv",outputs)
    matchrows=consolidate_labels(directly_mapped,h_features)
    write_csv(dest/"candidate_labels_verified.csv",matchrows)
    auc=exploratory_auc(h_features,{r["candidate_id"]:r["manual_label"] for r in matchrows})
    write_csv(dest/"reconciled_exploratory_feature_auc.csv",auc)
    after=[digest(x) for x in inputs]
    if before!=after:raise AssertionError("one or more input files modified")
    statuses=Counter(r["retarget_status"] for r in outputs)
    reviews=Counter(r["review_id"] for r in outputs)
    summary={
        "user_input_csv":str(source),"source_file_unmodified":True,
        "review_rows":len(outputs),"unique_review_ids":len(reviews),
        "annotated_reviews":dict(reviews),
        "missing_review_056":not any(r["review_id"]=="review_056" for r in outputs),
        "membership_groups":dict(Counter(r["membership_verified"] for r in outputs)),
        "retarget_status_counts":dict(statuses),
        "unique_directly_mapped_positive_H_candidates":len(directly_mapped),
        "direct_positive_candidate_ids":sorted(directly_mapped),
        "AUC_unique_positive_n":sum(r["manual_label"]=="confirmed_dark_spot" for r in matchrows),
        "AUC_unique_negative_n":sum(r["manual_label"]=="background_artifact" for r in matchrows),
        "feature_auc_use":"exploratory, non-random sample26 human-positive/negative; never production accuracy",
        "candidate_id_matching":"8-connect full mask BFS; exact bbox+area matched unique Case03-C feature row; all matches source confirmed",
        "no_guessing_for_unsegmented_clicks":True,
    }
    (dest/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    with (dest/"source_manifest.json").open("w",encoding="utf-8") as f:
        json.dump({"before":before,"after":after,"unchanged":before==after},f,ensure_ascii=False,indent=2)
    print("ANALYSIS_DIR",dest,flush=True)
    print("SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
