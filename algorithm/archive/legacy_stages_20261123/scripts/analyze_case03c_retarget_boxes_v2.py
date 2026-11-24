"""Second exported human CSV: quantify all boxes, preserve explicit review_056 NO_ISSUE.

Human rectangular ROI is not a per-pixel lesion mask or a unique H component.
For each box, enumerate all underlying full-res 8-connected H components
and the exact number of their pixels inside this box. Do not auto-label them.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
import cv2

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config
from src.detection.thresholding import load_packed_mask
from scripts.resolve_case03c_user_retarget import lookup_by_geometry,match_component,read_csv_rows
from src.detection.feature_discrimination import exploratory_auc

RUN=ROOT/"outputs/case03c_label_analysis/run_20261009_exact_pixel_retarget_v2"
CASE03C=ROOT/"outputs/case03c/run_20261008_174000"
CASE03B=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"
CASE02=ROOT/"outputs/case02/run_20260930_153727/samples/sample_26_frame_1/responses/blackhat_fused.npz"
RAWP=user_config.DATA_ROOT/"26 (1).raw"
OUTPUTS=RUN/"box_diagnostics"
OUTPUTS.mkdir(exist_ok=True)


def save(path:Path,rows:list[dict])->None:
    cols=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols)
        w.writeheader();w.writerows(rows)

def generate_figure(box:tuple[int,int,int,int],raw,rsp,s,h, name:str)->None:
    x0,y0,x1,y1=box
    xa=max(0,x0-30);xb=min(s.shape[1],x1+30)
    ya=max(0,y0-30);yb=min(s.shape[0],y1+30)
    raw_window=np.asarray(raw[ya:yb,xa:xb],dtype=np.float32)
    lo,hi=np.percentile(raw_window,[1,99.5])
    if hi<=lo:hi=lo+1
    gray=np.uint8(np.clip((raw_window-lo)/(hi-lo)*255,0,255))
    col=np.stack([gray,gray,gray],axis=2)
    S=s[ya:yb,xa:xb]
    H=h[ya:yb,xa:xb]
    col[S]=np.array([255,220,30],dtype=np.uint8)
    col[H&~S]=np.array([30,232,245],dtype=np.uint8)
    xy0=(x0-xa,y0-ya);xy1=(x1-1-xa,y1-1-ya)
    cv2.rectangle(col,xy0,xy1,(255,25,25),1)
    rawrgb=np.stack([gray,gray,gray],axis=2)
    cv2.rectangle(rawrgb,xy0,xy1,(255,25,25),1)
    v=np.concatenate((rawrgb,col),axis=1)
    ok,png=cv2.imencode(".png",cv2.cvtColor(v,cv2.COLOR_RGB2BGR))
    if not ok:raise IOError("PNG encode failed")
    (OUTPUTS/name).write_bytes(png.tobytes())

def main():
    rows=read_csv_rows(RUN/"pixel_retarget_associations.csv")
    feats=read_csv_rows(CASE03C/"hysteresis_candidate_features.csv")
    idx=lookup_by_geometry(feats)
    fullH=load_packed_mask(CASE03B/"fused_H_TL170_TH230.npz")
    fullS=load_packed_mask(CASE03B/"fused_S_TL230_TH230.npz")
    raw=np.memmap(RAWP,dtype=">u2",mode="r",shape=fullH.shape)
    with np.load(CASE02,allow_pickle=False) as f:
        rsp=np.asarray(f["fused_response_dn"],dtype=np.uint16)
    assert raw.shape==rsp.shape==fullH.shape==fullS.shape==(9200,11276)
    assert not np.any(fullS&~fullH)
    cache={}
    reports=[]
    box_candidate_rows=[]
    for row in rows:
        if row["mode"]!="box":continue
        rid=row["review_id"]
        x0,y0,x1,y1=(int(row[k]) for k in ("raw_global_x0","raw_global_y0","raw_global_x1","raw_global_y1"))
        area=(x1-x0)*(y1-y0)
        r=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
        b=rsp[y0:y1,x0:x1]
        hs=fullH[y0:y1,x0:x1]
        ss=fullS[y0:y1,x0:x1]
        ys,xs=np.nonzero(hs)
        count=Counter()
        hits={}
        for yl,xl in zip(ys.tolist(),xs.tolist()):
            gx=x0+xl;gy=y0+yl
            hit,geom=match_component(fullH,idx,gx,gy,cache)
            cid=hit["candidate_id"]
            count[cid]+=1
            hits[cid]=hit
        candidates=[]
        for cid,n in count.most_common():
            hit=hits[cid]
            candidates.append({
                "review_id":rid,
                "annotation_id":row["annotation_id"],
                "component_id":cid,
                "H_pixels_in_human_rectangle":n,
                "H_component_total_area_px":int(hit["area_px"]),
                "H_component_bbox_x":int(hit["bbox_x"]),
                "H_component_bbox_y":int(hit["bbox_y"]),
                "H_component_bbox_w":int(hit["bbox_w"]),
                "H_component_bbox_h":int(hit["bbox_h"]),
                "fraction_of_component_inside_box":round(n/int(hit["area_px"]),4),
                "H_peak_response_dn":hit["peak_response_dn"],
                "user_confirmed_component_exactly":"NOT_YET__multiple_components_or_box_not_pixel_mask"
            })
        box_candidate_rows.extend(candidates)
        if len(candidates)==1 and int(candidates[0]["H_pixels_in_human_rectangle"])==int(hs.sum()):
            auto_note="one H component intersects box; identity known but user has not approved full H as positive"
        elif len(candidates)>1:
            auto_note=f"{len(candidates)} distinct H components intersect human box; do NOT automatically label all as positive"
        else:
            auto_note="no H component inside selected box; requires visual false-negative review"
        lo=0 if r.size==0 else float(np.percentile(r,5))
        med=float(np.median(r))
        ringX0=max(0,x0-12);ringY0=max(0,y0-12);ringX1=min(11276,x1+12);ringY1=min(9200,y1+12)
        nearRaw=np.asarray(raw[ringY0:ringY1,ringX0:ringX1],dtype=np.uint16)
        outer=np.ones(nearRaw.shape,dtype=bool)
        outer[y0-ringY0:y1-ringY0,x0-ringX0:x1-ringX0]=False
        outer&=~fullH[ringY0:ringY1,ringX0:ringX1]
        valid=(nearRaw[outer] if np.any(outer) else np.empty(0,np.uint16))
        bg_med=float(np.median(valid)) if valid.size else ""
        boxContrast=round(bg_med-med,3) if valid.size else ""
        item={
           "review_id":rid,"annotation_id":row["annotation_id"],
           "label_from_user":row["label"],"box_full_RAW_coords":f"({x0},{y0})..({x1},{y1})",
           "x0":x0,"y0":y0,"x1":x1,"y1":y1,"box_pixels":area,
           "S230_count":int(ss.sum()),"H170_230_count":int(hs.sum()),
           "ratio_S230":round(float(ss.mean()),5),"ratio_H170_230":round(float(hs.mean()),5),
           "blackhat_max_dn":int(b.max()),"blackhat_median_dn":float(np.median(b)),
           "blackhat_p90_dn":round(float(np.percentile(b,90)),3),
           "blackhat_n_above170":int((b>=170).sum()),
           "blackhat_n_above230":int((b>=230).sum()),
           "RAW_box_median_dn":med,"RAW_box_p5_dn":lo,
           "RAW_reference_ring_median_dn":bg_med,
           "RAW_reference_minus_box_median_dn":boxContrast,
           "H_component_count_intersecting_box":len(candidates),
           "most_overlap_component_id":candidates[0]["component_id"] if candidates else "",
           "most_overlap_H_pixels":candidates[0]["H_pixels_in_human_rectangle"] if candidates else 0,
           "most_overlap_fraction_of_H_pixels_in_rectangle":
             round(candidates[0]["H_pixels_in_human_rectangle"]/int(hs.sum()),4) if int(hs.sum()) else 0,
           "identity_mapping_warning":auto_note,
           "original_data_preserved":"True"
        }
        reports.append(item)
        generate_figure((x0,y0,x1,y1),raw,rsp,fullS,fullH,f"{rid}_{row['annotation_id'][-6:]}_box_RAW_vs_segmentation.png")
        print("BOX",rid,"dim",x1-x0,y1-y0,
             "S/H",int(ss.sum()),int(hs.sum()),
             "max",int(b.max()),"Hcomponent",len(candidates),
             "top",count.most_common(4),"contrast",boxContrast,flush=True)
    assert len(reports)==7 and len(box_candidate_rows)>0
    save(RUN/"box_retarget_diagnostics_v2.csv",reports)
    save(RUN/"box_overlapping_H_components_v2.csv",box_candidate_rows)
    status={"new_csv_rows":len(rows),"box_count":len(reports),
            "distinct_user_review_images":len({r["review_id"] for r in rows}),
            "review_056_user_confirmed":"NO_ANOMALY_NEEDS_FOLLOWUP",
            "review_056_as_specific_negative_candidate":False,
            "review_056_in_new_labels":False,
            "box_H_auto_relabeling":False,
            "point_exact_retarget_new_unique_positive_components":
                len({r["exact_H_candidate_id"] for r in rows if r["exact_H_candidate_id"]}),
            "box_count_by_review":dict(Counter(r["review_id"] for r in reports)),
            "box_diagnostics_source":"full-resolution RAW and Case02 fused BlackHat uint16 + Case03B S/H exact masks",
            "box_overlapping_components_rule":"all intersecting full-resolution H components enumerated; no box treated as per-pixel anomaly ground truth"}
    (RUN/"box_analysis_status_v2.json").write_text(json.dumps(status,indent=2,ensure_ascii=False),encoding="utf-8")
    print("FINAL",json.dumps(status,ensure_ascii=False,indent=2),flush=True)
    return 0
if __name__=="__main__":raise SystemExit(main())
