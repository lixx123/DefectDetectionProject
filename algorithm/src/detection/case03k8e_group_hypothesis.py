"""K8E reversible grouping of existing K8D RAW outer *proposals*.

Does NOT fuse original J5 defect IDs or modify source B masks. Groups are
new display hypotheses; group area uses exact pixel union in global coordinates.
"""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class GroupPolicy:
    pair_min_containment:float=.65
    pair_min_iou:float=.50
    mutual_contour_iou_strong:float=.90
    full_B_member_coverage:float=.80
    max_group_members:int=10

def _check(box,mask):
    box=[int(v) for v in box]
    if len(box)!=4 or box[2]<=box[0] or box[3]<=box[1]:raise ValueError("invalid ROI")
    mask=np.asarray(mask,bool)
    if mask.shape!=(box[3]-box[1],box[2]-box[0]):raise ValueError("mask/ROI mismatch")
    return box,mask

def global_intersection(left,right):
    a,mask_a=_check(left["box"],left["mask"])
    b,mask_b=_check(right["box"],right["mask"])
    ix0=max(a[0],b[0]);iy0=max(a[1],b[1])
    ix1=min(a[2],b[2]);iy1=min(a[3],b[3])
    if ix0>=ix1 or iy0>=iy1:
        return {"intersection_px2":0,"union_px2":int(mask_a.sum()+mask_b.sum()),
                "iou":0.,"min_containment":0.,
                "coverage_left":0.,"coverage_right":0.}
    x=mask_a[iy0-a[1]:iy1-a[1],ix0-a[0]:ix1-a[0]]
    y=mask_b[iy0-b[1]:iy1-b[1],ix0-b[0]:ix1-b[0]]
    inter=int((x&y).sum())
    ma=int(mask_a.sum());mb=int(mask_b.sum())
    union=ma+mb-inter
    return {"intersection_px2":inter,"union_px2":union,
            "iou":inter/max(union,1),
            "min_containment":inter/max(min(ma,mb),1),
            "coverage_left":inter/max(ma,1),"coverage_right":inter/max(mb,1)}

def union_global(items):
    if not items:raise ValueError("no items")
    bounds=[_check(x["box"],x["mask"])[0] for x in items]
    x0=min(x[0] for x in bounds);y0=min(x[1] for x in bounds)
    x1=max(x[2] for x in bounds);y1=max(x[3] for x in bounds)
    union=np.zeros((y1-y0,x1-x0),bool)
    for x in items:
        box,mask=_check(x["box"],x["mask"])
        union[box[1]-y0:box[3]-y0,box[0]-x0:box[2]-x0]|=mask
    return (x0,y0,x1,y1),union

def make_groups(items,policy=GroupPolicy()):
    """Same-band graph of contour containment; GROUP, not original-ID merge.

    Any selected singleton can have embedded source-B labels that are not
    among chosen K8D objects. Store them separately as hypotheses.
    """
    for i,obj in enumerate(items):
        if not obj["mask"].any():raise ValueError("empty source not groupable")
        _check(obj["box"],obj["mask"])
    parent=list(range(len(items)))
    def find(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]];v=parent[v]
        return v
    links=[]
    for i in range(len(items)):
        for j in range(i+1,len(items)):
            if items[i]["band_id"]!=items[j]["band_id"]:continue
            metric=global_intersection(items[i],items[j])
            if (metric["min_containment"]>=policy.pair_min_containment
                and metric["iou"]>=policy.pair_min_iou):
                links.append({"indices":[i,j],"candidate_labels":[
                    int(items[i]["label"]),int(items[j]["label"])],
                    **metric})
                a=find(i);b=find(j)
                if a!=b:parent[b]=a
    families={}
    for i in range(len(items)):
        families.setdefault(find(i),[]).append(i)
    output=[]
    for root,members in families.items():
        members.sort()
        curr=[items[i] for i in members]
        if len({v["band_id"] for v in curr})!=1:raise AssertionError("crossband grouping")
        box,full=union_global(curr)
        ids=[int(t["label"]) for t in curr]
        selected_ids=set(ids)
        embedded={}
        for obj in curr:
            for e in obj.get("embedded_evidence",[]):
                eid=int(e["B_label"])
                if eid in selected_ids:continue
                coverage=float(e["whole_overlap_fraction"])
                if coverage>=policy.full_B_member_coverage and bool(e["eligible_same_spot_review"]):
                    old=embedded.get(eid)
                    if old is None or coverage>old["coverage"]:
                        embedded[eid]={
                            "B_label":eid,
                            "coverage":coverage,
                            "source_full_px":int(e["source_full_px"]),
                            "member_is_display_hypothesis":True}
        group_pairs=[x for x in links if set(x["indices"]).issubset(set(members))]
        cross=(len(members)>policy.max_group_members or
               len(group_pairs)!=len(members)*(len(members)-1)//2 or any(
                 x["min_containment"]<policy.pair_min_containment or
                 x["iou"]<policy.pair_min_iou for x in group_pairs))
        conflict=any(obj.get("partial_competitors") for obj in curr)
        stable=all(str(obj["status"]).startswith("STABLE_") for obj in curr)
        if not stable: review="RAW_SAFETY_UNRESOLVED"
        elif cross or conflict:review="GROUP_CONFLICT_REVIEW"
        elif len(curr)>1:
            min_iou=min(x["iou"] for x in group_pairs)
            review="MUTUAL_CONTOUR_NEAR_IDENTICAL_REVIEW" if min_iou>=policy.mutual_contour_iou_strong else "MULTI_PROPOSAL_ASSOCIATION_REVIEW"
        elif embedded:review="EMBEDDED_B_SOURCE_REVIEW"
        else:review="SINGLE_STABLE_REVIEW"
        assert int(full.sum())<=sum(int(t["mask"].sum()) for t in curr)
        for x in curr:
            b=x["box"]
            clip=full[b[1]-box[1]:b[3]-box[1],b[0]-box[0]:b[2]-box[0]]
            assert np.all(clip[x["mask"]]),"union lost original pixels"
        output.append({
            "band_id":int(curr[0]["band_id"]),
            "selected_candidate_labels":ids,
            "embedded_B_source_evidence":sorted(embedded.values(),key=lambda a:a["B_label"]),
            "review_status":review,
            "original_K8D_masks_sum_px2":int(sum(x["mask"].sum() for x in curr)),
            "exact_group_union_px2":int(full.sum()),
            "deduplicated_pixels":int(sum(x["mask"].sum() for x in curr)-full.sum()),
            "box":box,"mask":full,"pair_links":group_pairs,
            "original_B_J5_ids_merged":False,
            "real_defect_confirmation":False})
    return sorted(output,key=lambda o:(o["band_id"],min(o["selected_candidate_labels"])))
