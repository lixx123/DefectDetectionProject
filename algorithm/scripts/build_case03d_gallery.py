"""Case03-D read-only visual atlas: real RAW, true S/H masks, candidate bbox.

Tile shows candidate context, not full connected-component segmentation alone:
other neighbors can share the patch. The rectangle marks chosen H bbox.
Review rank is a queue position, not a defect confidence score.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

from config import user_config as cfg
from src.detection.thresholding import load_packed_mask

ROOT=Path(__file__).resolve().parents[1]
CASE03B=ROOT/"outputs/case03b/run_20261008_153500/masks/sample_26_frame_1"


def save_png(path:Path,array:np.ndarray):
    ok,encoded=cv2.imencode(".png",array)
    if not ok:raise OSError(f"encode failed {path}")
    path.write_bytes(encoded.tobytes())


def _pick_evenly(df:pd.DataFrame,k:int)->list[dict]:
    if len(df)==0:return []
    if len(df)<=k:return df.to_dict("records")
    indices=np.unique(np.rint(np.linspace(0,len(df)-1,k)).astype(int))
    return df.iloc[indices].to_dict("records")


def sample_gallery_groups(frame:pd.DataFrame, strict_ids:set, provisional_ids:set,k:int):
    """Visualization groups may read labels after ranking; never alter score."""
    sorted_frame=frame.sort_values("priority_rank",kind="mergesort")
    negatives=sorted_frame[sorted_frame["manual_label_strict"].eq("background_artifact")]
    positive=sorted_frame[sorted_frame["manual_label_strict"].eq("confirmed_dark_spot")]
    high=sorted_frame[sorted_frame["review_tier"].eq("A_first_review")]
    mid=sorted_frame[sorted_frame["review_tier"].eq("B_second_review")]
    low=sorted_frame[sorted_frame["review_tier"].eq("C_later_review")]
    provisional=sorted_frame[sorted_frame["candidate_id"].isin(provisional_ids)]
    edge=sorted_frame[sorted_frame["near_band_transition"].astype(str).str.lower().eq("true")]
    groups=OrderedDict((
        ("A_top_ranked",high.head(k).to_dict("records")),
        ("B_spread_review",_pick_evenly(mid,k)),
        ("C_spread_unfiltered",_pick_evenly(low,k)),
        ("known_positive_low_priority",positive.tail(k).sort_values("priority_rank",ascending=False).to_dict("records")),
        ("known_negative_high_priority",negatives.head(k).to_dict("records")),
        ("provisional_box_matches",provisional.head(k).to_dict("records")),
        ("transition_sensitive_early",edge.head(k).to_dict("records")),
    ))
    return groups


def render_tile(item:dict,raw:np.ndarray,S:np.ndarray,H:np.ndarray,patch_size:int)->np.ndarray:
    x=int(round(float(item["centroid_x"])));y=int(round(float(item["centroid_y"])))
    h,w=raw.shape
    half=patch_size//2
    x0=min(max(0,x-half),w-patch_size)
    y0=min(max(0,y-half),h-patch_size)
    x1=x0+patch_size;y1=y0+patch_size
    raw_patch=np.asarray(raw[y0:y1,x0:x1],dtype=np.uint16)
    s=S[y0:y1,x0:x1]
    h_mask=H[y0:y1,x0:x1]
    lo,hi=np.percentile(raw_patch,[1,99.5])
    hi=max(float(hi),float(lo)+1)
    gray=np.uint8(np.rint(np.clip((raw_patch-lo)/(hi-lo),0,1)*255))
    raw_view=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    overlay=raw_view.copy()
    # BGR: yellow core, cyan weak support. Human-defined selected component is red outline.
    overlay[s]=(25,220,255)
    overlay[h_mask&~s]=(245,220,30)
    cx=x-x0;cy=y-y0
    cv2.drawMarker(raw_view,(cx,cy),(10,10,250),cv2.MARKER_CROSS,10,1)
    cv2.drawMarker(overlay,(cx,cy),(10,10,250),cv2.MARKER_CROSS,10,1)
    bx=int(item["bbox_x"])-x0;by=int(item["bbox_y"])-y0
    bxe=bx+int(item["bbox_w"])-1;bye=by+int(item["bbox_h"])-1
    cv2.rectangle(overlay,(bx,by),(bxe,bye),(18,36,255),1)
    header=51
    gap=5
    tile=np.full((patch_size+header,patch_size*2+gap,3),245,np.uint8)
    tile[header:header+patch_size,:patch_size]=raw_view
    tile[header:header+patch_size,patch_size+gap:]=overlay
    text_id=str(item["candidate_id"]).replace("H_sample26_","H_")
    line=f"{text_id} | #{int(item['priority_rank'])} | {item['review_tier'][0]}"
    cv2.putText(tile,line,(7,17),cv2.FONT_HERSHEY_SIMPLEX,.43,(38,44,54),1,cv2.LINE_AA)
    status=str(item.get("manual_evidence_status","UNLABELED"))
    if status=="HUMAN_REVIEWED":
        status=str(item.get("manual_label_strict","manual_reviewed"))
    elif status.startswith("PROVISIONAL"):status="PROVISIONAL BOX (not exact GT)"
    else:status="Unlabeled: NOT confirmed noise"
    cv2.putText(tile,status,(7,31),cv2.FONT_HERSHEY_SIMPLEX,.38,(62,70,78),1,cv2.LINE_AA)
    summary=f"area={int(item['area_px'])}px peak={int(item['peak_response_dn'])}DN"
    cv2.putText(tile,summary,(7,45),cv2.FONT_HERSHEY_SIMPLEX,.4,(55,63,67),1,cv2.LINE_AA)
    return tile


def _map_centroids(out:Path,frame:pd.DataFrame,raw:np.ndarray):
    # A pin-map is only a locator. Pin proximity/size does not prove true
    # connected mask coverage. Use original RAW subsampled merely as display.
    stride=6
    gray=np.asarray(raw[::stride,::stride],dtype=np.uint16)
    lo,hi=np.percentile(gray,[1,99.5])
    hi=max(float(hi),float(lo)+1)
    base=np.uint8(np.rint(np.clip((gray.astype(np.float32)-lo)/(hi-lo),0,1)*210+17))
    img=cv2.cvtColor(base,cv2.COLOR_GRAY2BGR)
    for name,allowed in [("A_only",("A_first_review",)),
                         ("A_and_B",("B_second_review","A_first_review"))]:
        canvas=img.copy()
        sub=frame[frame["review_tier"].isin(allowed)]
        for r in sub.itertuples(index=False):
            x=int(round(float(r.centroid_x)/stride))
            y=int(round(float(r.centroid_y)/stride))
            if r.review_tier=="A_first_review":
                color=(40,80,245) # red A
            else:
                color=(245,185,15) # orange B
            if 0<=x<canvas.shape[1] and 0<=y<canvas.shape[0]:
                cv2.circle(canvas,(x,y),2 if r.review_tier=="A_first_review" else 1,color,-1)
        # White/black strips belong to RAW background. Draw legend in top-left.
        cv2.rectangle(canvas,(8,8),(840,60),(255,255,255),-1)
        cv2.putText(canvas,f"Sample26 ranking {name}: A=red B=orange candidate centroids ONLY",
                    (17,31),cv2.FONT_HERSHEY_SIMPLEX,.62,(30,30,30),1,cv2.LINE_AA)
        cv2.putText(canvas,"This is a review locator, not a segmented defect map or physical truth",
                    (17,51),cv2.FONT_HERSHEY_SIMPLEX,.46,(70,70,70),1,cv2.LINE_AA)
        save_png(out/f"priority_map_{name}.png",canvas)


def build_gallery(out:Path,frame:pd.DataFrame,strict_ids:set,provisional_ids:set):
    images=out/"figures";images.mkdir(exist_ok=True)
    size=int(cfg.CASE03D_ATLAS_PATCH_SIZE_PX)
    k=int(cfg.CASE03D_ATLAS_CANDIDATES_PER_GROUP)
    if size<96 or size%2 or k<=0:raise ValueError("invalid gallery configuration")
    raw_file=cfg.DATA_ROOT/"26 (1).raw"
    raw=np.memmap(raw_file,dtype=">u2",mode="r",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    S=load_packed_mask(CASE03B/"fused_S_TL230_TH230.npz")
    H=load_packed_mask(CASE03B/"fused_H_TL170_TH230.npz")
    if not (S.shape==H.shape==raw.shape):
        raise ValueError("mismatched input shapes")
    _map_centroids(images,frame,raw)
    groups=sample_gallery_groups(frame,strict_ids,provisional_ids,k)
    manifest=[]
    for name,rows in groups.items():
        if not rows:continue
        perrow=3
        tile_h=size+51
        tile_w=size*2+5
        margins=12
        pitch_x=tile_w+12
        pitch_y=tile_h+12
        count=len(rows)
        canvas=np.full((math_ceil(count,perrow)*pitch_y+50,perrow*pitch_x,3),245,np.uint8)
        cv2.putText(canvas,name+" | RAW left, exact S/H overlay right | all candidates retained",
                    (14,32),cv2.FONT_HERSHEY_SIMPLEX,.63,(24,37,45),1,cv2.LINE_AA)
        for i,item in enumerate(rows):
            tile=render_tile(item,raw,S,H,size)
            x=(i%perrow)*pitch_x
            y=(i//perrow)*pitch_y+50
            canvas[y:y+tile_h,x:x+tile_w]=tile
            manifest.append({
                "group":name,"candidate_id":item["candidate_id"],
                "priority_rank":int(item["priority_rank"]),
                "review_tier":item["review_tier"],"area_px":int(item["area_px"]),
                "peak_response_dn":int(item["peak_response_dn"]),
                "manual_label":item.get("manual_label_strict",""),
                "manual_evidence_status":item.get("manual_evidence_status","UNLABELED"),
                "figure_name":f"atlas_{name}.png"
            })
        save_png(images/f"atlas_{name}.png",canvas)
    pd.DataFrame(manifest).to_csv(out/"atlas_selection.csv",index=False,encoding="utf-8-sig")
    print("CASE03D_ATLAS_IMAGES",len(list(images.glob("*.png"))),flush=True)


def math_ceil(n:int,d:int)->int:
    return (n+d-1)//d
