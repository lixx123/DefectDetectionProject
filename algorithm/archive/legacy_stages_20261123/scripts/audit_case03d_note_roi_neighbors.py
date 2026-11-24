"""Inspect H candidate classifications around ten user-noted off-target RAW areas.

No retargeting is inferred from a vague direction (upper/lower/right). All
candidate IDs remain provisional; output is for subsequent human clicks only.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
import cv2,numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.visualization.case03d_detected_atlas import roi_from_current
OUT=ROOT/"outputs/case03d_manual_review_analysis/run_20261010_092200"
RUN=ROOT/"outputs/case03d_autodetect/run_20261009_autodetect_final"

def main():
    joined=pd.read_csv(OUT/"human_review_joined_100.csv",low_memory=False)
    issues=joined[joined["note"].notna()].copy()
    if len(issues)!=10:
        raise AssertionError("expected exactly 10 notes")
    full=pd.read_csv(RUN/"candidate_decisions_full.csv",low_memory=False)
    full["right"]=full["bbox_x"]+full["bbox_w"]
    full["bottom"]=full["bbox_y"]+full["bbox_h"]
    with np.load(RUN/"candidate_status_map_lossless.npz",allow_pickle=False) as z:
        cmap=z["class_map"]
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(9200,11276))
    tiles=[]
    stats=[]
    for record in issues.to_dict("records"):
        cx=float(record["centroid_x"]);cy=float(record["centroid_y"])
        roi=roi_from_current(record,raw.shape,160)
        x0,y0,x1,y1=roi
        local=np.asarray(raw[y0:y1,x0:x1],dtype=np.float32)
        v=cmap[y0:y1,x0:x1]
        lo,hi=np.percentile(local,[1,99.5])
        hi=max(lo+1,hi)
        gray=np.uint8(np.rint(np.clip((local-lo)/(hi-lo),0,1)*255))
        base=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
        selected=base.copy()
        x=int(record["bbox_x"])-x0
        y=int(record["bbox_y"])-y0
        cv2.rectangle(selected,(x,y),
            (x+int(record["bbox_w"])-1,y+int(record["bbox_h"])-1),(12,20,250),2)
        cv2.drawMarker(selected,(int(round(cx))-x0,int(round(cy))-y0),
                       (15,20,255),cv2.MARKER_CROSS,10,1)
        status=base.copy()
        # Status legend: green auto, yellow uncertain, magenta weak/noise-like.
        status[v==3]=(40,220,55)
        status[v==2]=(0,190,245)
        status[v==1]=(165,55,150)
        cv2.rectangle(status,(x,y),
            (x+int(record["bbox_w"])-1,y+int(record["bbox_h"])-1),
            (20,25,250),1)
        overlap=(full["bbox_x"]<x1)&(full["right"]>x0)&(
            full["bbox_y"]<y1)&(full["bottom"]>y0)
        neighbors=full.loc[overlap]
        filtered=neighbors[neighbors["candidate_id"]!=record["candidate_id"]]
        significant=filtered[(filtered["triage_status"]!="noise_like_retained") &
                             (filtered["area_px"]>=12)]
        auto=filtered[filtered["triage_status"]=="detected_provisional"]
        important=significant.sort_values(
            ["area_px","peak_response_dn"],ascending=[False,False]
        ).head(8)
        nearby=[
            {"candidate_id":r["candidate_id"],"triage_status":r["triage_status"],
             "area_px":int(r["area_px"]),"peak_response_dn":int(r["peak_response_dn"]),
             "centroid_raw_xy":[float(r["centroid_x"]),float(r["centroid_y"])]}
            for r in important.to_dict("records")
        ]
        stats.append({
            "candidate_id":record["candidate_id"],
            "manual_label":record["manual_label"],
            "human_note":record["note"],
            "audit_scope_status":record["scope_audit_status"],
            "center_xy":[cx,cy],
            "roi_xyxy":[x0,y0,x1,y1],
            "other_auto_H_bbox_intersecting_roi":len(auto),
            "other_uncertain_H_at_least_12px_bbox_intersecting_roi":
                int(((significant["triage_status"]=="uncertain_review")).sum()),
            "other_significant_nearby_candidates_json":json.dumps(
                nearby,ensure_ascii=False),
            "ROI_class3_auto_pixels":int(np.count_nonzero(v==3)),
            "ROI_class2_uncertain_pixels":int(np.count_nonzero(v==2)),
            "ROI_class1_noise_like_pixels":int(np.count_nonzero(v==1)),
            "no_automatic_retarget":True,
        })
        card=np.full((232,3*160+20,3),250,np.uint8)
        for i,(img,label) in enumerate([
            (base,"1 RAW"),(selected,"2 SELECTED H"),
            (status,"3 ALL H STATUS")]):
            xx=i*170
            cv2.putText(card,label,(xx+3,16),cv2.FONT_HERSHEY_SIMPLEX,.43,
                        (20,41,62),1,cv2.LINE_AA)
            card[52:212,xx:xx+160]=img
        cv2.putText(card,
            str(record["candidate_id"])+" | "+str(record["manual_label"]),
            (4,37),cv2.FONT_HERSHEY_SIMPLEX,.46,(35,42,60),1,cv2.LINE_AA)
        tiles.append(card)
    if len(tiles)!=10:raise AssertionError("scope note visualization incomplete")
    assembled=np.full((5*240+35,2*520,3),246,np.uint8)
    for i,img in enumerate(tiles):
        x=i%2*520
        y=i//2*240+35
        assembled[y:y+img.shape[0],x:x+img.shape[1]]=img
    cv2.putText(assembled,
        "ROI candidate statuses: green=provisional AUTO, yellow=UNCERTAIN, violet=noise-like",
        (10,23),cv2.FONT_HERSHEY_SIMPLEX,.51,(40,60,70),1,cv2.LINE_AA)
    ok,buf=cv2.imencode(".jpg",assembled,[cv2.IMWRITE_JPEG_QUALITY,90])
    if not ok:raise IOError("cannot encode notes ROI status montage")
    (OUT/"10_notes_neighborhood_all_status.jpg").write_bytes(buf.tobytes())
    pd.DataFrame(stats).to_csv(OUT/"10_notes_roi_neighbors.csv",
                               index=False,encoding="utf-8-sig")
    overview=[{"candidate_id":r["candidate_id"],
               "label":r["manual_label"],
               "other_auto_H_bbox":r["other_auto_H_bbox_intersecting_roi"],
               "other_uncertain_12px":r["other_uncertain_H_at_least_12px_bbox_intersecting_roi"],
               "area_pixels_auto_in_crop":r["ROI_class3_auto_pixels"]}
              for r in stats]
    (OUT/"10_notes_roi_neighbors_summary.json").write_text(
        json.dumps(overview,ensure_ascii=False,indent=2),encoding="utf-8"
    )
    print("NOTES_NEIGHBORHOOD",json.dumps(overview,ensure_ascii=True))


if __name__=="__main__":
    main()
