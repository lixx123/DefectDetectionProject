"""Case03-J pilot: auditable association of disjoint dark scratch components.

Physical hypotheses are grouped WITHOUT ever altering candidate masks.
Safety: do not merge based on centroid distance alone; use contour gap,
one clear dominant geometric direction, and positive dark-ridge support
through the actual gap in RAW's band-pass (DoG8 - DoG2).
All parameters are engineering trials, not final material QC thresholds.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import cv2
from scipy.spatial import cKDTree
from src.detection.case03i_size_grade import (
    SizeGradeConfig,grade_size,max_feret_centers_px
)


@dataclass(frozen=True)
class AssociationConfig:
    max_gap_px:float=18.
    min_core_area_px:int=80
    min_piece_area_px:int=8
    min_secondary_length_px:float=5.
    strong_aspect_ratio:float=1.35
    angle_tolerance_deg:float=38.
    min_bridge_dog_median_dn:float=16.
    min_bridge_dog_positive_fraction:float=.7
    small_bridge_gap_px:float=4.
    min_piece_dog_median_dn:float=12.
    min_core_length_px:float=15.
    min_backdrop_samples:int=2

    def validate(self):
        if not (2<=self.max_gap_px<=32 and 0<self.small_bridge_gap_px<=self.max_gap_px):
            raise ValueError("invalid gap")
        if not (0<self.angle_tolerance_deg<=60 and self.strong_aspect_ratio>=1.1):
            raise ValueError("invalid orientation")
        if self.min_piece_area_px<2 or self.min_core_area_px<=self.min_piece_area_px:
            raise ValueError("invalid area")
        if not (0<=self.min_bridge_dog_positive_fraction<=1):
            raise ValueError("invalid dark evidence")


def _angle_alignment(vector:np.ndarray,axis:np.ndarray)->float:
    n=np.linalg.norm(vector)
    if n<1e-9:return 0.
    return float(abs(np.dot(vector/n,axis)))


def _component_geometry(labels:np.ndarray,records:list[dict],dog:np.ndarray,
                        config:AssociationConfig)->dict[int,dict]:
    geometry={}
    for r in records:
        j=int(r["local_region_id"])
        bx=int(r["bbox_x_global"])-int(r["_global_x0"])
        by=int(r["bbox_y_global"])-int(r["_global_y0"])
        w=int(r["bbox_width_px"]);h=int(r["bbox_height_px"])
        mask=labels[by:by+h,bx:bx+w]==j
        yy,xx=np.nonzero(mask)
        pts=np.stack((xx+bx,yy+by),axis=1).astype(np.float32)
        if pts.shape[0]!=int(r["area_px2"]):
            raise AssertionError("changed source area")
        centers=pts.astype(np.float64)
        length=float(r["max_feret_centers_px"])
        bbox_aspect=max(w/h,h/w)
        if len(pts)>=3:
            cov=np.cov(centers.T)
            eigvals,eigvecs=np.linalg.eigh(cov)
            order=np.argsort(eigvals)[::-1]
            large=float(eigvals[order[0]])
            small=float(max(eigvals[order[1]],.001))
            eig_aspect=float(np.sqrt(max(.001,large)/small))
            axis=eigvecs[:,order[0]]
        else:
            eig_aspect=1.
            axis=np.asarray((1.,0.))
        # Reliable axis may come from covariance or a strongly elongated bbox.
        reliable=bool(length>=config.min_core_length_px and
                      max(bbox_aspect,eig_aspect)>=config.strong_aspect_ratio)
        if reliable and eig_aspect<config.strong_aspect_ratio and bbox_aspect>=config.strong_aspect_ratio:
            axis=np.asarray((1.,0.)) if w>=h else np.asarray((0.,1.))
        # Contour positions are enough for nearest bridge distances.
        edge=cv2.findContours(mask.astype(np.uint8),
                              cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)[0]
        if not edge:raise ValueError("component contour missing")
        edges=np.vstack([a.reshape(-1,2) for a in edge]).astype(float)
        edges[:,0]+=bx;edges[:,1]+=by
        geometry[j]={
            "points":pts,"boundary":edges,
            "center":centers.mean(axis=0),
            "axis":np.asarray(axis,dtype=float),
            "axis_reliable":reliable,
            "aspect":round(float(max(eig_aspect,bbox_aspect)),3),
            "area":len(pts),"length":length,
            "dog_median":float(np.median(dog[by+yy,bx+xx])),
            "bbox":(bx,by,bx+w-1,by+h-1),
        }
    return geometry


def _nearest_pair(a:np.ndarray,b:np.ndarray)->tuple[float,np.ndarray,np.ndarray]:
    tree=cKDTree(a)
    distance,idx=tree.query(b,k=1)
    k=int(np.argmin(distance))
    return float(distance[k]),a[int(idx[k])],b[k]


def _bridge_support(dog:np.ndarray,a:np.ndarray,b:np.ndarray,
                    labels:np.ndarray,config:AssociationConfig)->tuple[float,float,int]:
    dist=float(np.linalg.norm(b-a))
    n=max(config.min_backdrop_samples,int(np.ceil(dist*2)))
    # DoG of actual gap samples only, not core pixels.
    positions=np.rint(np.linspace(a,b,n+2)[1:-1]).astype(int)
    x=np.clip(positions[:,0],0,dog.shape[1]-1)
    y=np.clip(positions[:,1],0,dog.shape[0]-1)
    between=(labels[y,x]==0)
    values=dog[y[between],x[between]]
    if len(values)<config.min_backdrop_samples:
        return -float("inf"),0.,int(len(values))
    return float(np.median(values)),float(np.mean(values>0)),int(len(values))


def associate_fragments(labels:np.ndarray,records:list[dict],raw:np.ndarray,
                        config:AssociationConfig=AssociationConfig(),
                        grades:SizeGradeConfig=SizeGradeConfig()
                        )->tuple[list[dict],list[dict],list[dict],np.ndarray]:
    """Return physical-object hypotheses, accepted/rejected link audit, member map,
    and uint32 object-id raster (same nonzero support as source labels).
    """
    config.validate();grades.validate()
    if labels.ndim!=2 or raw.shape!=labels.shape or raw.dtype!=np.uint16:
        raise ValueError("RAW and label raster geometry/dtype mismatch")
    if len(set(int(r["local_region_id"]) for r in records))!=len(records):
        raise ValueError("duplicate region IDs")
    for r in records:
        if not all(k in r for k in ("bbox_x_global","bbox_y_global",
                                    "area_px2","max_feret_centers_px")):
            raise ValueError("missing original region dimensions")
    origin=(
        min([int(r["bbox_x_global"])-int(r.get("_local_bbox_x",0)) for r in records]
            or [0]),
        min([int(r["bbox_y_global"])-int(r.get("_local_bbox_y",0)) for r in records]
            or [0]),
    )
    # Require caller to supply global origin explicitly per candidate. Remove
    # any risk of deriving window global origin from bounding-box min values.
    if records:
        explicit={(int(r["_global_x0"]),int(r["_global_y0"])) for r in records}
        if len(explicit)!=1:raise ValueError("inconsistent ROI origin")
    f=raw.astype(np.float32)
    dog=cv2.GaussianBlur(f,(0,0),8.)-cv2.GaussianBlur(f,(0,0),2.)
    geo=_component_geometry(labels,records,dog,config)
    keys=sorted(geo)
    parent={k:k for k in keys}
    def root(k:int)->int:
        while parent[k]!=k:
            parent[k]=parent[parent[k]]
            k=parent[k]
        return k
    audit=[]
    alignment_min=float(np.cos(np.deg2rad(config.angle_tolerance_deg)))
    for ii,a in enumerate(keys):
        ga=geo[a]
        for b in keys[ii+1:]:
            gb=geo[b]
            xa,ya,x2a,y2a=ga["bbox"]
            xb,yb,x2b,y2b=gb["bbox"]
            dx=max(0,xb-x2a,xa-x2b)
            dy=max(0,yb-y2a,ya-y2b)
            if dx*dx+dy*dy>config.max_gap_px**2:continue
            if min(ga["area"],gb["area"])<config.min_piece_area_px:continue
            if min(ga["length"],gb["length"])<config.min_secondary_length_px:continue
            # No grouping between nearby dots. Require a substantial core or
            # very short local connector in same high-dark-ridge structure.
            strong_core=max(ga["area"],gb["area"])>=config.min_core_area_px
            if not strong_core and max(ga["area"],gb["area"])<20:continue
            if min(ga["dog_median"],gb["dog_median"])<config.min_piece_dog_median_dn:
                continue
            gap,pt_a,pt_b=_nearest_pair(ga["boundary"],gb["boundary"])
            if gap<=1.42 or gap>config.max_gap_px:continue
            vec=pt_b-pt_a
            alignment=max(
                _angle_alignment(vec,ga["axis"]) if ga["axis_reliable"] else 0.,
                _angle_alignment(vec,gb["axis"]) if gb["axis_reliable"] else 0.)
            # Tiny connectors within 4 pixels may lack a reliable axis, but
            # require a strong proximal dark-ridge. No distant blob chaining.
            short_connector=(gap<=config.small_bridge_gap_px and
                             max(ga["area"],gb["area"])>=20 and
                             max(ga["length"],gb["length"])>=12.)
            orientation_ok=alignment>=alignment_min or short_connector
            median,positive,n=_bridge_support(dog,pt_a,pt_b,labels,config)
            dark_ok=(median>=config.min_bridge_dog_median_dn and
                     positive>=config.min_bridge_dog_positive_fraction)
            accepted=bool(orientation_ok and dark_ok)
            record={
                "a":a,"b":b,"gap_px":round(gap,3),
                "axis_alignment":round(alignment,3),
                "orientation_pass":orientation_ok,
                "gap_dog_median_dn":round(median,3) if np.isfinite(median) else None,
                "gap_positive_fraction":round(positive,3),
                "bridge_samples":n,
                "accepted":accepted,
                "reason":"linked_dark_aligned_gap" if accepted else
                         ("direction_incompatible" if not orientation_ok
                          else "gap_has_no_dark_evidence"),
            }
            audit.append(record)
            if accepted:
                ra,rb=root(a),root(b)
                if ra!=rb:parent[max(ra,rb)]=min(ra,rb)
    groups={}
    for k in keys:groups.setdefault(root(k),[]).append(k)
    objects=[];members=[]
    object_map=np.zeros(labels.shape,dtype=np.uint32)
    for ix,(leader,ids) in enumerate(sorted(groups.items()),1):
        member_recs=[next(x for x in records if int(x["local_region_id"])==j)
                     for j in ids]
        total_area=sum(int(x["area_px2"]) for x in member_recs)
        coords=np.vstack([geo[j]["points"] for j in ids])
        length=max_feret_centers_px(coords)
        grade,trigger=grade_size(total_area,length,grades)
        ys=coords[:,1];xs=coords[:,0]
        touches=any(bool(x["touches_window_border"]) for x in member_recs)
        obj={
            "object_id":f'{member_recs[0]["window_id"]}_OBJ{ix:04d}',
            "window_id":member_recs[0]["window_id"],
            "member_ids":";".join(str(j) for j in ids),
            "member_count":len(ids),
            "area_union_original_pixels":total_area,
            "max_feret_centers_px":round(length,4),
            "size_grade":grade,"grade_trigger":trigger,
            "center_x_global":round(float(xs.mean()+member_recs[0]["_global_x0"]),3),
            "center_y_global":round(float(ys.mean()+member_recs[0]["_global_y0"]),3),
            "bbox_x_global":int(xs.min()+member_recs[0]["_global_x0"]),
            "bbox_y_global":int(ys.min()+member_recs[0]["_global_y0"]),
            "bbox_width_px":int(xs.max()-xs.min()+1),
            "bbox_height_px":int(ys.max()-ys.min()+1),
            "touches_window_border":touches,
            "one_physical_defect_unconfirmed":True,
            "association_does_not_fill_gaps":True,
        }
        objects.append(obj)
        for j in ids:
            object_map[labels==j]=ix
            members.append({"region_id":next(x["region_id"] for x in member_recs
                       if x["local_region_id"]==j),
                       "local_region_id":j,
                       "object_id":obj["object_id"],
                       "linked":len(ids)>1})
    if not np.array_equal(labels>0,object_map>0):
        raise AssertionError("association must preserve exact old segmentation")
    if sum(x["area_union_original_pixels"] for x in objects)!=np.count_nonzero(labels):
        raise AssertionError("group area double counted")
    if len(members)!=len(records):raise AssertionError("lost member")
    return objects,audit,members,object_map
