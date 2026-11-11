"""Case03-J2: one continuous displayed scratch contour, auditable inferred bridges.

Inputs are frozen Case03-I region label maps and the Case03-J1 association
audit. Neither original RAW nor original H/refined detector mask changes.

Linking accepts a second, conservative context-based extension: a sizeable
piece along the extrapolated axis of an already linked long scratch, with
a strong RAW-DoG ridge through the exact inter-region gap. This closes W005's
visually obvious right-side scratch extension when local centroids alone
provide no reliable line direction.

Bridge mask is display-only provenance: never count its pixels as detected
defect area. Union contour is a visual hypothesis, not measured segmentation.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import cv2
from .case03j_fragment_association import (
    AssociationConfig,_component_geometry,_nearest_pair,_bridge_support
)
from .case03i_size_grade import (
    SizeGradeConfig,grade_size,max_feret_centers_px
)


@dataclass(frozen=True)
class ContinuousConfig:
    context_max_gap_px:float=18.
    main_stroke_min_length_px:float=60.
    main_stroke_min_aspect:float=3.
    piece_min_area_px:int=40
    piece_min_length_px:float=12.
    max_perpendicular_offset_px:float=20.
    context_angle_tolerance_deg:float=35.
    bridge_half_width_px:int=3
    bridge_min_dog_dn:float=12.
    max_context_links_per_group:int=1
    ambiguous_gap_margin_px:float=2.

    def validate(self):
        if not (2<=self.context_max_gap_px<=32):raise ValueError("bad gap")
        if not (1<=self.bridge_half_width_px<=8):raise ValueError("bad display bridge radius")
        if not (0<=self.context_angle_tolerance_deg<=60):raise ValueError("bad angle")


def _group_by_edges(ids:list[int],edges:list[dict])->dict[int,list[int]]:
    parents={j:j for j in ids}
    def find(j):
        while parents[j]!=j:
            parents[j]=parents[parents[j]]
            j=parents[j]
        return j
    for edge in edges:
        if not edge["accepted"]:continue
        a=int(edge["a"]);b=int(edge["b"])
        if a not in parents or b not in parents:raise ValueError("edge unknown")
        x,y=find(a),find(b)
        if x!=y:parents[max(x,y)]=min(x,y)
    groups={}
    for j in ids:groups.setdefault(find(j),[]).append(j)
    return groups


def extend_context_links(labels:np.ndarray,raw:np.ndarray,
                         rows:list[dict],edges:list[dict],
                         old_cfg:AssociationConfig=AssociationConfig(),
                         cfg:ContinuousConfig=ContinuousConfig()
                         )->tuple[list[dict],np.ndarray,dict]:
    cfg.validate()
    if labels.shape!=raw.shape or raw.dtype!=np.uint16:
        raise ValueError("source geometry mismatch")
    f=raw.astype(np.float32)
    dog=cv2.GaussianBlur(f,(0,0),old_cfg.dog_large_sigma_px) if hasattr(old_cfg,"dog_large_sigma_px") else cv2.GaussianBlur(f,(0,0),8.)
    dog=dog-cv2.GaussianBlur(f,(0,0),2.)
    if not rows:return [],dog,{}
    geo=_component_geometry(labels,rows,dog,old_cfg)
    ids=sorted(geo)
    groups=_group_by_edges(ids,edges)
    alignment_min=float(np.cos(np.deg2rad(cfg.context_angle_tolerance_deg)))
    choices=[]
    for leader,members in sorted(groups.items()):
        if len(members)<2:continue
        anchors=[j for j in members if
             geo[j]["length"]>=cfg.main_stroke_min_length_px
             and geo[j]["aspect"]>=cfg.main_stroke_min_aspect
             and geo[j]["axis_reliable"]]
        if not anchors:continue
        candidate_anchors=sorted(anchors,key=lambda j:geo[j]["length"],reverse=True)
        anchor=geo[candidate_anchors[0]]
        axis=anchor["axis"]/np.linalg.norm(anchor["axis"])
        # Centroid offset from long axis is checked independently of nearest
        # local blob geometry, so a nearly isotropic knot can be bridged.
        p_anchor=anchor["center"]
        for j in ids:
            if j in members:continue
            cand=geo[j]
            if cand["area"]<cfg.piece_min_area_px or cand["length"]<cfg.piece_min_length_px:
                continue
            if cand["dog_median"]<old_cfg.min_piece_dog_median_dn:continue
            delt=cand["center"]-p_anchor
            perp=float(abs(axis[0]*delt[1]-axis[1]*delt[0]))
            if perp>cfg.max_perpendicular_offset_px:continue
            # Candidate must extrapolate beyond the long source stroke, not
            # lie alongside its central body (avoids parallel nearby spots).
            source_proj=np.dot(anchor["points"]-p_anchor,axis)
            cand_proj=float(np.dot(delt,axis))
            if not (cand_proj>float(source_proj.max())+1 or
                    cand_proj<float(source_proj.min())-1):
                continue
            nearby=[]
            for origin in members:
                if origin==j:continue
                old=geo[origin]
                xa,ya,x2a,y2a=old["bbox"]
                xb,yb,x2b,y2b=cand["bbox"]
                dx=max(0,xb-x2a,xa-x2b)
                dy=max(0,yb-y2a,ya-y2b)
                if dx*dx+dy*dy > cfg.context_max_gap_px**2:continue
                gap,p0,p1=_nearest_pair(old["boundary"],cand["boundary"])
                if not 1.42<gap<=cfg.context_max_gap_px:continue
                unit=(p1-p0)/gap
                align=float(abs(np.dot(unit,axis)))
                if align<alignment_min:continue
                med,pos,num=_bridge_support(dog,p0,p1,labels,old_cfg)
                if (num>=2 and med>=old_cfg.min_bridge_dog_median_dn and
                    pos>=old_cfg.min_bridge_dog_positive_fraction):
                    nearby.append((gap,origin,med,pos,align))
            if nearby:
                gap,origin,med,pos,align=min(nearby)
                choices.append({
                    "a":int(origin),"b":int(j),"gap_px":round(gap,3),
                    "axis_alignment":round(align,3),
                    "orientation_pass":True,
                    "gap_dog_median_dn":round(float(med),3),
                    "gap_positive_fraction":round(float(pos),3),
                    "bridge_samples":int(round(gap*2)),
                    "accepted":True,
                    "reason":"context_long_scratch_dark_ridge",
                    "context_anchor":int(candidate_anchors[0]),
                    "perpendicular_offset_px":round(perp,3),
                    "group_leader":int(leader)
                })
    # Never force an ambiguous piece into two competing nearby objects.
    choice_groups={}
    for edge in choices:choice_groups.setdefault(edge["b"],[]).append(edge)
    new=[]
    for j,candidates in sorted(choice_groups.items()):
        candidates.sort(key=lambda e:e["gap_px"])
        if (len(candidates)>1 and
            candidates[1]["gap_px"]-candidates[0]["gap_px"]<
                     cfg.ambiguous_gap_margin_px):
            continue
        new.append(candidates[0])
    selected=[]
    counts={}
    for edge in sorted(new,key=lambda e:e["gap_px"]):
        g=edge["group_leader"]
        if counts.get(g,0)<cfg.max_context_links_per_group:
            selected.append(edge)
            counts[g]=counts.get(g,0)+1
    return selected,dog,geo


def _promote_microfragments_on_dark_bridge(
    labels:np.ndarray,geo:dict[int,dict],groups:dict[int,list[int]],
    evidence_edges:list[dict],config:ContinuousConfig,
)->list[dict]:
    """Promote only strong-dark microfragments lying on validated bridges.

    A microfragment must intersect the expected corridor of an already
    confirmed edge in an elongated group. No human labels influence this.
    """
    ids=set(geo)
    used={v for a in groups.values() if len(a)>1 for v in a}
    assignments=[]
    for leader,members in sorted(groups.items()):
        if len(members)<3:continue
        if not any(geo[k]["length"]>=config.main_stroke_min_length_px
                   for k in members):
            continue
        paths=np.zeros(labels.shape,dtype=np.uint8)
        valid_edges=[e for e in evidence_edges
                     if e["accepted"] and int(e["a"]) in members
                     and int(e["b"]) in members]
        for e in valid_edges:
            gap,a,b=_nearest_pair(
                geo[int(e["a"])]["boundary"],geo[int(e["b"])]["boundary"])
            line=np.zeros(labels.shape,dtype=np.uint8)
            cv2.line(line,tuple(a.astype(int)),tuple(b.astype(int)),1,1)
            paths=cv2.bitwise_or(paths,cv2.dilate(line,
                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9))))
        if not paths.any():continue
        for j in sorted(ids-used):
            candidate=geo[j]
            if not (5<=candidate["area"]<=20):
                continue
            if candidate["dog_median"]<30.:continue
            points=candidate["points"].astype(int)
            overlap=int(np.count_nonzero(paths[points[:,1],points[:,0]]))
            if overlap<max(1,int(np.ceil(candidate["area"]*.2))):
                continue
            # Avoid ambiguous multi-group attachments.
            potential=[]
            for other_leader,other_members in groups.items():
                if other_leader==leader or len(other_members)<=1:continue
                potential.append(any(
                    geo[v]["area"]>=40 and
                    np.linalg.norm(geo[v]["center"]-candidate["center"])<8
                    for v in other_members))
            if any(potential):continue
            closest=min(members,key=lambda k:_nearest_pair(
                geo[k]["boundary"],candidate["boundary"])[0])
            gap,_,_=_nearest_pair(geo[closest]["boundary"],candidate["boundary"])
            assignments.append({
                "a":int(closest),"b":int(j),
                "gap_px":round(float(gap),3),
                "accepted":True,
                "reason":"dark_microfragment_on_validated_bridge",
                "bridge_overlap_pixels":overlap,
                "microfragment_dog_median_dn":round(candidate["dog_median"],3),
            })
            used.add(j)
    return assignments


def reconstruct_continuous_visual(
    labels:np.ndarray,raw:np.ndarray,records:list[dict],
    pair_edges:list[dict],region_grade:SizeGradeConfig=SizeGradeConfig(),
    assoc_cfg:AssociationConfig=AssociationConfig(),
    config:ContinuousConfig=ContinuousConfig()
)->tuple[list[dict],np.ndarray,np.ndarray,np.ndarray,list[dict],list[dict]]:
    """Returns objects, original object label map, inferred bridge ID map,
    visually continuous ID map, all accepted edge audit and bridge pixel audit.
    """
    config.validate()
    if labels.ndim!=2 or labels.shape!=raw.shape:
        raise ValueError("shape mismatch")
    new_edges,dog,geo=extend_context_links(labels,raw,records,
                                            pair_edges,assoc_cfg,config)
    all_edges=[dict(e) for e in pair_edges]+new_edges
    groups=_group_by_edges(sorted(geo),all_edges)
    micro_edges=_promote_microfragments_on_dark_bridge(
        labels,geo,groups,all_edges,config)
    all_edges.extend(micro_edges)
    groups=_group_by_edges(sorted(geo),all_edges)
    by_id={int(r["local_region_id"]):r for r in records}
    objmap=np.zeros_like(labels,dtype=np.int32)
    bridgeids=np.zeros_like(labels,dtype=np.int32)
    objects=[]
    audit=[]
    H,W=labels.shape
    for objnum,(leader,members) in enumerate(sorted(groups.items()),1):
        for mid in members:objmap[labels==mid]=objnum
        pts=np.vstack([geo[j]["points"] for j in members])
        area=sum(geo[j]["area"] for j in members)
        length=max_feret_centers_px(pts)
        grade,reason=grade_size(area,length,region_grade)
        entry={
            "object_id":f'{by_id[members[0]]["window_id"]}_C{objnum:04d}',
            "frame":str(by_id[members[0]].get("frame","unknown")),
            "window_id":by_id[members[0]]["window_id"],
            "members":";".join(str(j) for j in members),
            "member_count":len(members),
            "original_area_px2":int(area),
            "original_max_feret_px":round(float(length),4),
            "size_grade":grade,
            "grade_trigger":reason,
            "center_x_global":float(pts[:,0].mean()+by_id[members[0]]["_global_x0"]),
            "center_y_global":float(pts[:,1].mean()+by_id[members[0]]["_global_y0"]),
            "candidate_not_confirmed":True,
        }
        objects.append(entry)
        if len(members)==1:continue
        for e in all_edges:
            if not e["accepted"] or int(e["a"]) not in members or int(e["b"]) not in members:
                continue
            a=int(e["a"]);b=int(e["b"])
            gap,p0,p1=_nearest_pair(geo[a]["boundary"],geo[b]["boundary"])
            segment=np.zeros(labels.shape,dtype=np.uint8)
            pa=tuple(int(v) for v in p0)
            pb=tuple(int(v) for v in p1)
            cv2.line(segment,pa,pb,1,1,lineType=cv2.LINE_8)
            kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                    (2*config.bridge_half_width_px+1,)*2)
            expanded=cv2.dilate(segment,kernel)
            # Intensity-constrained inferred band. The thin guaranteed core
            # is only allowed after the pair passed the RAW dark-gap test.
            candidate=(segment>0) | (
                (expanded>0) & (dog>=config.bridge_min_dog_dn))
            # No inferred pixel is allowed to overwrite another independent
            # source object or an existing inferred object from another group.
            legal=candidate & (labels==0) & (bridgeids==0)
            bridgeids[legal]=objnum
            audit.append({
                "object_id":entry["object_id"],"a":a,"b":b,
                "gap_px":round(gap,3),
                "is_context_link":e["reason"]=="context_long_scratch_dark_ridge",
                "bridge_proposal_pixels":int(legal.sum()),
                "source_mask_modified":False,
                "bridge_is_inferred_not_detected":True,
                "endpoint_a_xy":str(pa),"endpoint_b_xy":str(pb)
            })
    combined=objmap.copy()
    free=(combined==0)&(bridgeids>0)
    combined[free]=bridgeids[free]
    if not np.array_equal(labels>0,objmap>0):
        raise AssertionError("original object support not preserved")
    if np.any((bridgeids>0)&(labels>0)):
        raise AssertionError("inferred bridges overwrite source")
    if np.any((combined>0)!=( (objmap>0)|(bridgeids>0))):
        raise AssertionError("composite visual object mask mismatch")
    # Strong acceptance: each multi-piece object's display geometry is 8-
    # connected, hence the shared physical contour really looks continuous.
    for i,o in enumerate(objects,1):
        if o["member_count"]<2:continue
        cnt,_=cv2.connectedComponents(np.uint8(combined==i),connectivity=8)
        o["inferred_bridge_pixels"]=int(np.count_nonzero(bridgeids==i))
        o["display_support_pixels"]=int(np.count_nonzero(combined==i))
        o["continuous_display_components"]=int(cnt-1)
        if cnt!=2:
            raise RuntimeError(
                f"{o['object_id']}: still visually disconnected into {cnt-1} pieces")
    for i,o in enumerate(objects,1):
        if "inferred_bridge_pixels" not in o:
            o["inferred_bridge_pixels"]=0
            o["display_support_pixels"]=o["original_area_px2"]
            o["continuous_display_components"]=1
    return objects,objmap,bridgeids,combined,all_edges,audit
