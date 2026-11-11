"""Lossless bbox-local mask storage and cautious overlap dedup across windows.

Only merge evidence if exact pixels overlap substantially. A pair merely
sharing a bbox or nearby center is not sufficient. Two nearby independent
dark spots must retain separate global IDs.
"""
from __future__ import annotations
import base64
from collections import defaultdict
import numpy as np


def serialize_bbox_binary(mask:np.ndarray,global_origin_xy:tuple[int,int])->dict:
    if mask.ndim!=2 or not mask.any():
        raise ValueError("cannot serialize empty or non-image mask")
    ys,xs=np.nonzero(mask)
    x=int(xs.min());y=int(ys.min())
    width=int(xs.max()-x+1);height=int(ys.max()-y+1)
    inside=np.ascontiguousarray(mask[y:y+height,x:x+width].astype(np.uint8))
    bits=np.packbits(inside.reshape(-1),bitorder="little")
    return {
      "bbox_global_xywh":[int(global_origin_xy[0]+x),
                          int(global_origin_xy[1]+y),width,height],
      "exact_area_px":int(inside.sum()),
      "encoding":"base64_np_packbits_rowmajor_little",
      "binary_bbox_mask_base64":base64.b64encode(bits.tobytes()).decode("ascii")
    }


def read_bbox_binary(record:dict)->np.ndarray:
    if record["encoding"]!="base64_np_packbits_rowmajor_little":
        raise ValueError("unknown binary mask encoding")
    _,_,w,h=(int(v) for v in record["bbox_global_xywh"])
    binary=base64.b64decode(record["binary_bbox_mask_base64"],validate=True)
    bits=np.unpackbits(np.frombuffer(binary,dtype=np.uint8),
                       bitorder="little",count=w*h)
    crop=bits.reshape(h,w).astype(bool)
    if int(crop.sum())!=int(record["exact_area_px"]):
        raise AssertionError("serialized area not preserved")
    return crop


def exact_overlap_global(a:dict,b:dict)->int:
    ax,ay,aw,ah=(int(v) for v in a["bbox_global_xywh"])
    bx,by,bw,bh=(int(v) for v in b["bbox_global_xywh"])
    x0=max(ax,bx);y0=max(ay,by)
    x1=min(ax+aw,bx+bw);y1=min(ay+ah,by+bh)
    if x0>=x1 or y0>=y1:return 0
    A=read_bbox_binary(a)[y0-ay:y1-ay,x0-ax:x1-ax]
    B=read_bbox_binary(b)[y0-by:y1-by,x0-bx:x1-bx]
    return int((A&B).sum())


def merge_mask_exact(records:list[dict],ids:list[int])->dict:
    x0=min(int(records[i]["bbox_global_xywh"][0]) for i in ids)
    y0=min(int(records[i]["bbox_global_xywh"][1]) for i in ids)
    x1=max(int(records[i]["bbox_global_xywh"][0]+records[i]["bbox_global_xywh"][2])
           for i in ids)
    y1=max(int(records[i]["bbox_global_xywh"][1]+records[i]["bbox_global_xywh"][3])
           for i in ids)
    if (x1-x0)*(y1-y0)>256*256*5:
        raise ValueError("global duplicate merge spans excessively large region")
    union=np.zeros((y1-y0,x1-x0),bool)
    for i in ids:
        rec=records[i]
        x,y,w,h=(int(v) for v in rec["bbox_global_xywh"])
        union[y-y0:y-y0+h,x-x0:x-x0+w]|=read_bbox_binary(rec)
    return serialize_bbox_binary(union,(x0,y0))


def deduplicate_cross_window(records:list[dict],
                             *,
                             min_overlap_fraction:float=.55,
                             max_center_distance_px:float=28.
                             )->tuple[list[dict],list[dict]]:
    """Exactly overlapping cross-window objects only.

    In the special case of the same physical spot on overlapping windows,
    output one union mask and preserve all contributing ROI IDs. Objects
    with zero exact common H/refinement pixels cannot be merged merely by
    proximity. No within-window merges occur in this function.
    """
    count=len(records)
    parent=list(range(count))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    def unite(i,j):
        ii,jj=find(i),find(j)
        if ii!=jj:parent[max(ii,jj)]=min(ii,jj)
    audited=[]
    for i,a in enumerate(records):
        ax,ay,aw,ah=a["bbox_global_xywh"]
        for j in range(i+1,count):
            b=records[j]
            if a["window_id"]==b["window_id"]:continue
            bx,by,bw,bh=b["bbox_global_xywh"]
            if max(ax,bx)>=min(ax+aw,bx+bw) or max(ay,by)>=min(ay+ah,by+bh):
                continue
            dist=np.hypot(a["center_raw_x"]-b["center_raw_x"],
                          a["center_raw_y"]-b["center_raw_y"])
            if dist>max_center_distance_px:continue
            shared=exact_overlap_global(a,b)
            f=shared/max(1,min(a["exact_area_px"],b["exact_area_px"]))
            if shared>=2 and f>=min_overlap_fraction:
                unite(i,j)
                audited.append({
                  "left_object":a["local_object_id"],
                  "right_object":b["local_object_id"],
                  "shared_exact_pixels":shared,
                  "smaller_mask_coverage":round(f,4),
                  "action":"cross_window_duplicate"
                })
    clusters=defaultdict(list)
    for i in range(count):
        clusters[find(i)].append(i)
    merged=[]
    for idx,ids in enumerate(clusters.values(),1):
        masks=merge_mask_exact(records,ids)
        sources=sorted(set(v for i in ids for v in records[i]["sources"]))
        statuses=[records[i]["fusion_status"] for i in ids]
        unsafe=any("needs_review" in s for s in statuses)
        out={
            "global_object_id":f"E2_G{idx:05d}",
            "member_window_object_ids":[records[i]["local_object_id"] for i in ids],
            "member_window_ids":sorted(set(records[i]["window_id"] for i in ids)),
            "duplicate_window_count":len(set(records[i]["window_id"] for i in ids)),
            "sources":sources,
            "fusion_status":"needs_review_if_any_member_unsafe" if unsafe else
                ("provisional_fused" if len(sources)>=2 else
                 ("provisional_H_only" if sources==["H170_230"]
                  else "needs_review_single_method")),
            "measurement_validated":False,
            "size_grade":"PENDING_MEASUREMENT_THRESHOLDS",
            "physical_defect_truth":False,
            **masks
        }
        merged.append(out)
    if len(set(g["global_object_id"] for g in merged))!=len(merged):
        raise AssertionError("global IDs not unique")
    return merged,audited
