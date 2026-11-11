"""Case03-D-R2 detected atlas: four aligned views without hidden neighbors.

1 RAW  2 all S230/H170-230 responses  3 ALL detected_provisional components
in the same 160x160 ROI, individually numbered  4 current selected component.

"Detected" here always means algorithm-proposed, not confirmed filter damage.
This module is visualization-only: it must not change the source masks or
classification of any candidate. Every auto region is based on the exact
full-resolution per-pixel class map, with local numbers linked to true H IDs.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from src.detection.candidate_contour_export import exact_candidate_submask


# OpenCV images use BGR.
S_YELLOW=(22,227,255)
H_CYAN=(247,216,25)
AUTO_GREEN=(42,225,56)
CURRENT_RED=(24,35,247)
OTHER_RED=(65,72,215)
HEADER_INK=(39,49,59)
SEPARATOR=7
LABEL_H=80


def roi_from_current(row:dict,shape:tuple[int,int],size:int)->tuple[int,int,int,int]:
    height,width=shape
    if size<96 or size>min(height,width):
        raise ValueError("invalid patch size")
    x=int(round(float(row["centroid_x"])))
    y=int(round(float(row["centroid_y"])))
    x0=min(max(0,x-size//2),width-size)
    y0=min(max(0,y-size//2),height-size)
    return x0,y0,x0+size,y0+size


def visible_auto_objects(
    current:dict,
    all_detected:list[dict],
    full_H:np.ndarray,
    roi:tuple[int,int,int,int]
)->list[dict]:
    """Return the real H components with >=1 exact pixel inside this crop.

    Bounding-box intersection alone is insufficient and can falsely claim that
    a neighboring defect appears in the crop. We verify each component's exact
    pixel mask, including near-border / overlapping bounding-box cases.
    """
    x0,y0,x1,y1=roi
    overlaps=[]
    for row in all_detected:
        bx=int(row["bbox_x"]);by=int(row["bbox_y"])
        bw=int(row["bbox_w"]);bh=int(row["bbox_h"])
        xa=max(x0,bx);ya=max(y0,by)
        xb=min(x1,bx+bw);yb=min(y1,by+bh)
        if xa>=xb or ya>=yb:
            continue
        mask,(xx,yy,ww,hh)=exact_candidate_submask(full_H,row)
        visible=mask[ya-yy:yb-yy,xa-xx:xb-xx]
        if not np.any(visible):
            continue
        ys,xs=np.nonzero(visible)
        rec=dict(row)
        rec["_visible_count"]=int(len(xs))
        rec["_visible_center_x"]=int(xa+round(float(np.median(xs))))
        rec["_visible_center_y"]=int(ya+round(float(np.median(ys))))
        overlaps.append(rec)
    overlaps.sort(key=lambda r:(r["_visible_center_y"],r["_visible_center_x"],str(r["candidate_id"])))
    for index,row in enumerate(overlaps,1):
        row["_roi_number"]=index
        row["_is_selected"]=str(row["candidate_id"])==str(current["candidate_id"])
    if not sum(row["_is_selected"] for row in overlaps)==1:
        raise AssertionError("selected candidate not among visible AUTO components")
    return overlaps


def _badge(img:np.ndarray,label:str,x:int,y:int,*,selected:bool):
    """Draw a high-contrast numbered badge located near the visible component."""
    font=cv2.FONT_HERSHEY_SIMPLEX
    scale=.49;thickness=1
    (tw,th),_baseline=cv2.getTextSize(label,font,scale,thickness)
    h,w=img.shape[:2]
    xx=int(np.clip(x-3,0,max(0,w-tw-11)))
    yy=int(np.clip(y-th-7,0,max(0,h-th-11)))
    fill=CURRENT_RED if selected else (62,70,76)
    cv2.rectangle(img,(xx,yy),(xx+tw+10,yy+th+9),fill,-1)
    cv2.putText(img,label,(xx+5,yy+th+5),font,scale,(255,255,255),thickness,cv2.LINE_AA)


def _draw_boxes_and_numbers(
    all_img:np.ndarray,objects:list[dict],roi:tuple[int,int,int,int],
)->None:
    """Number every actually visible auto candidate; red emphasizes selected."""
    x0,y0,x1,y1=roi
    h,w=all_img.shape[:2]
    for r in objects:
        x=int(r["bbox_x"])-x0;y=int(r["bbox_y"])-y0
        xmax=x+int(r["bbox_w"])-1
        ymax=y+int(r["bbox_h"])-1
        xa=max(0,x);ya=max(0,y)
        xb=min(w-1,xmax);yb=min(h-1,ymax)
        if xa>xb or ya>yb:
            continue
        sel=r["_is_selected"]
        # Draw rectangles around the *actual* proposal bbox, not the display
        # crop; these are guidance rectangles, NOT segmentation outlines.
        cv2.rectangle(all_img,(xa,ya),(xb,yb),
                      CURRENT_RED if sel else OTHER_RED,2 if sel else 1,cv2.LINE_AA)
        vx=int(r["_visible_center_x"])-x0
        vy=int(r["_visible_center_y"])-y0
        _badge(all_img,str(r["_roi_number"]),vx+7,vy-8,selected=sel)


def four_view_tile(
    current:dict,
    all_detected:list[dict],
    raw:np.ndarray,
    H:np.ndarray,
    S:np.ndarray,
    class_map:np.ndarray,
    *,
    size:int=160
)->tuple[np.ndarray,list[dict]]:
    """Render a four-column panel and explicit number->candidate-ID evidence."""
    if not (raw.shape==H.shape==S.shape==class_map.shape):
        raise ValueError("raw, H, S, auto class map dimensions differ")
    roi=roi_from_current(current,raw.shape,size)
    x0,y0,x1,y1=roi
    b_raw=np.asarray(raw[y0:y1,x0:x1],dtype=np.float32)
    lo,hi=np.percentile(b_raw,[1,99.5])
    hi=max(float(hi),float(lo)+1)
    grayscale=np.uint8(np.rint(np.clip((b_raw-lo)/(hi-lo),0,1)*255))
    raw_img=cv2.cvtColor(grayscale,cv2.COLOR_GRAY2BGR)
    s=S[y0:y1,x0:x1]
    h=H[y0:y1,x0:x1]
    cmap=class_map[y0:y1,x0:x1]
    if np.any((cmap==3)&(~h)):
        raise AssertionError("auto class pixels are outside the original H mask")
    response=raw_img.copy()
    response[s]=S_YELLOW
    response[h&~s]=H_CYAN

    # Panel 3 MUST include all auto detected neighbors, not selected only.
    all_auto=raw_img.copy()
    all_auto[cmap==3]=AUTO_GREEN
    neighbors=visible_auto_objects(current,all_detected,H,roi)
    # Pixelwise proof: all individually verified objects must exactly explain
    # the auto-status mask in the chosen ROI, not just center-point matches.
    proven=np.zeros_like(cmap,dtype=bool)
    for r in neighbors:
        mask,(bx,by,bw,bh)=exact_candidate_submask(H,r)
        xa=max(x0,bx);ya=max(y0,by)
        xb=min(x1,bx+bw);yb=min(y1,by+bh)
        local=mask[ya-by:yb-by,xa-bx:xb-bx].astype(bool)
        dest=proven[ya-y0:yb-y0,xa-x0:xb-x0]
        if np.any(dest&local):
            raise AssertionError("separate AUTO components overlap in ROI")
        dest|=local
    if not np.array_equal(proven,cmap==3):
        raise AssertionError("numbered auto objects fail to cover exact ROI auto pixels")
    _draw_boxes_and_numbers(all_auto,neighbors,roi)

    # Panel 4 contains exactly one green connected component (current H ID).
    selected=raw_img.copy()
    mask,(bx,by,bw,bh)=exact_candidate_submask(H,current)
    xa=max(x0,bx);ya=max(y0,by)
    xb=min(x1,bx+bw);yb=min(y1,by+bh)
    if xb<=xa or yb<=ya:
        raise AssertionError("current exact H component not visible")
    cropped=mask[ya-by:yb-by,xa-bx:xb-bx].astype(bool)
    target=selected[ya-y0:yb-y0,xa-x0:xb-x0]
    target[cropped]=AUTO_GREEN
    cv2.rectangle(selected,
                  (max(0,bx-x0),max(0,by-y0)),
                  (min(size-1,bx+bw-1-x0),min(size-1,by+bh-1-y0)),
                  CURRENT_RED,2,cv2.LINE_AA)

    images=[raw_img,response,all_auto,selected]
    line=np.full((size,SEPARATOR,3),247,dtype=np.uint8)
    panels=[images[0]]
    for other in images[1:]:
        panels.extend([line,other])
    picture=np.concatenate(panels,axis=1)
    canvas=np.full((size+LABEL_H,picture.shape[1],3),247,dtype=np.uint8)
    canvas[LABEL_H:]=picture
    candidate=str(current["candidate_id"]).replace("H_sample26_","H_")
    item_no=next(r["_roi_number"] for r in neighbors if r["_is_selected"])
    cv2.putText(canvas,f"{candidate} / auto provisional",(5,15),
                cv2.FONT_HERSHEY_SIMPLEX,.47,HEADER_INK,1,cv2.LINE_AA)
    cv2.putText(canvas,
                f"Area {int(current['area_px'])} px | Peak {int(current['peak_response_dn'])} DN"
                f" | ROI auto={len(neighbors)} | CURRENT #{item_no}",
                (5,34),cv2.FONT_HERSHEY_SIMPLEX,.45,HEADER_INK,1,cv2.LINE_AA)
    titles=("1 RAW","2 ALL S/H","3 ALL AUTO ROI","4 SELECTED ONLY")
    for i,title in enumerate(titles):
        ox=i*(size+SEPARATOR)
        cv2.putText(canvas,title,(ox+2,66),cv2.FONT_HERSHEY_SIMPLEX,
                    .39,HEADER_INK,1,cv2.LINE_AA)
    evidence=[{
        "atlas_selected_candidate_id":str(current["candidate_id"]),
        "roi_number":int(r["_roi_number"]),
        "auto_candidate_id":str(r["candidate_id"]),
        "is_current_selected":bool(r["_is_selected"]),
        "visible_auto_pixels":int(r["_visible_count"]),
        "roi_x0":int(x0),"roi_y0":int(y0),
        "roi_width":int(size),"roi_height":int(size),
        "centroid_x":float(r["centroid_x"]),
        "centroid_y":float(r["centroid_y"]),
        "component_area_px":int(r["area_px"]),
        "classification":"detected_provisional"
    } for r in neighbors]
    return canvas,evidence


def atlas_four_view(
    rows:list[dict],
    all_detected:list[dict],
    raw:np.ndarray,H:np.ndarray,S:np.ndarray,class_map:np.ndarray,
    *,
    size:int=160,columns:int=3
)->tuple[np.ndarray,list[dict]]:
    """Render all top-12 tiles with local numbers, plus an audit manifest."""
    if not rows or columns<=0:
        raise ValueError("atlas requires rows and positive columns")
    tile_w=4*size+3*SEPARATOR
    tile_h=size+LABEL_H
    spacing=14
    header_h=83
    nr=(len(rows)+columns-1)//columns
    output=np.full((header_h+nr*(tile_h+spacing),columns*(tile_w+spacing),3),
                   250,dtype=np.uint8)
    cv2.putText(output,
        "Case03-D AUTO candidates | 1 RAW / 2 S230+H170 / 3 ALL AUTO in ROI / 4 CURRENT ONLY",
        (14,26),cv2.FONT_HERSHEY_SIMPLEX,.68,HEADER_INK,1,cv2.LINE_AA)
    cv2.putText(output,
        "GREEN=automatically proposed H; RED BOX=selected; ROI numbers identify ALL detected neighbors.",
        (14,52),cv2.FONT_HERSHEY_SIMPLEX,.54,HEADER_INK,1,cv2.LINE_AA)
    cv2.putText(output,
        "AUTO = provisional classification, NOT confirmed physical filter defects.",
        (14,73),cv2.FONT_HERSHEY_SIMPLEX,.46,(68,74,80),1,cv2.LINE_AA)
    evidence=[]
    for i,row in enumerate(rows):
        tile,detail=four_view_tile(row,all_detected,raw,H,S,class_map,size=size)
        px=(i%columns)*(tile_w+spacing)
        py=header_h+(i//columns)*(tile_h+spacing)
        output[py:py+tile_h,px:px+tile_w]=tile
        for item in detail:
            item["atlas_card_index"]=i+1
        evidence.extend(detail)
    return output,evidence


def three_view_tile(
    current:dict,
    all_detected:list[dict],
    raw:np.ndarray,
    H:np.ndarray,
    S:np.ndarray,
    class_map:np.ndarray,
    *,
    size:int=160
)->tuple[np.ndarray,list[dict]]:
    """Three-view review tile: RAW, ALL S/H, ALL AUTO in ROI.

    Reuse the pixelwise-validated ALL-AUTO renderer. The selected-only view
    is intentionally absent: current ID remains highlighted with a red
    rectangle and numbered red badge in the ALL-AUTO panel.
    """
    original,evidence=four_view_tile(
        current,all_detected,raw,H,S,class_map,size=size
    )
    new_width=3*size+2*SEPARATOR
    return original[:,:new_width].copy(),evidence


def atlas_three_view(
    rows:list[dict],
    all_detected:list[dict],
    raw:np.ndarray,
    H:np.ndarray,
    S:np.ndarray,
    class_map:np.ndarray,
    *,
    size:int=160,
    columns:int=3
)->tuple[np.ndarray,list[dict]]:
    """Default Case03-D AUTO atlas: exactly 3 useful panels per card."""
    if not rows or columns<=0:
        raise ValueError("atlas requires rows and positive columns")
    tile_w=3*size+2*SEPARATOR
    tile_h=size+LABEL_H
    spacing=14
    header_h=83
    nr=(len(rows)+columns-1)//columns
    output=np.full(
        (header_h+nr*(tile_h+spacing),columns*(tile_w+spacing),3),
        250,dtype=np.uint8
    )
    cv2.putText(
        output,"Case03-D AUTO candidates | 1 RAW / 2 S230+H170 / 3 ALL AUTO in ROI",
        (14,26),cv2.FONT_HERSHEY_SIMPLEX,.68,HEADER_INK,1,cv2.LINE_AA
    )
    cv2.putText(
        output,"GREEN=all provisional detections; RED BOX/RED NUMBER=current candidate;",
        (14,52),cv2.FONT_HERSHEY_SIMPLEX,.54,HEADER_INK,1,cv2.LINE_AA
    )
    cv2.putText(
        output,"numbers identify neighboring H objects, not confirmed filter defects.",
        (14,73),cv2.FONT_HERSHEY_SIMPLEX,.50,(68,74,80),1,cv2.LINE_AA
    )
    evidence=[]
    for i,row in enumerate(rows):
        tile,detail=three_view_tile(
            row,all_detected,raw,H,S,class_map,size=size
        )
        px=(i%columns)*(tile_w+spacing)
        py=header_h+(i//columns)*(tile_h+spacing)
        output[py:py+tile_h,px:px+tile_w]=tile
        for item in detail:
            item["atlas_card_index"]=i+1
        evidence.extend(detail)
    return output,evidence
