"""Case03-J5: evidence-gated matching of source candidate pixels across J4 cores.

J4 core tiles are NONOVERLAPPING and exactly cover the RAW. Direct 8-neighbor
contact across a seam is definitive pixel connectivity, whereas separated
fragments are associated only if orientation + RAW DoG ridge agree. All proposed
edges, accept/reject reasons and original pixels remain auditable.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
import math
import cv2,numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class J5Config:
    gap_max_px:float=18.
    min_line_length_px:float=12.
    min_piece_area_px:int=5
    min_line_aspect:float=1.5
    angle_tolerance_degrees:float=30.
    min_bridge_dog_dn:float=16.
    min_positive_bridge_fraction:float=.70
    ambiguity_margin_px:float=2.
    max_linked_components_per_seam:int=5000

    def validate(self):
        if not 1.5<=self.gap_max_px<=32:raise ValueError("bad seam gap")
        if not 0<self.angle_tolerance_degrees<=60:raise ValueError("bad seam angle")
        if not 0<=self.min_positive_bridge_fraction<=1:raise ValueError("bad support")
        if self.min_line_length_px<2 or self.min_piece_area_px<1:
            raise ValueError("bad min geometry")


class UnionFind:
    def __init__(self, ids:list[str]):
        self.parent={v:v for v in ids}
        self.size={v:1 for v in ids}
    def find(self,x:str)->str:
        while self.parent[x]!=x:
            self.parent[x]=self.parent[self.parent[x]]
            x=self.parent[x]
        return x
    def join(self,a:str,b:str)->bool:
        pa,pb=self.find(a),self.find(b)
        if pa==pb:return False
        # Deterministic union by size, lexicographic tie.
        if (self.size[pa],-len(pa),pa)<(self.size[pb],-len(pb),pb):
            pa,pb=pb,pa
        self.parent[pb]=pa
        self.size[pa]+=self.size[pb]
        return True


def axes_from_source(pixels:np.ndarray)->tuple[np.ndarray,bool,float]:
    """Principal axis of original mask; nearly isotropic blobs have no axis."""
    pts=np.asarray(pixels,dtype=np.float64).reshape(-1,2)
    if len(pts)<3:return np.array((1.,0.)),False,1.
    cov=np.cov(pts.T)
    eigen,vec=np.linalg.eigh(cov)
    order=np.argsort(eigen)[::-1]
    aspect=float(np.sqrt(max(eigen[order[0]],.001)/
                         max(eigen[order[1]],.001)))
    major=vec[:,order[0]]
    return major, bool(aspect>=1.5),aspect


def approximate_geometry(rows:dict[str,dict],pixel_clouds:dict[str,np.ndarray],
                         cfg:J5Config)->dict[str,dict]:
    geom={}
    for name,pts in pixel_clouds.items():
        axis,reliable,aspect=axes_from_source(pts)
        entry=rows[name]
        reliable=(reliable and aspect>=cfg.min_line_aspect
                  and float(entry["source_max_feret_px"])>=cfg.min_line_length_px)
        geom[name]={"axis":axis,"reliable":reliable,"aspect":aspect,
                    "area":int(entry["source_area_px2"]),
                    "feret":float(entry["source_max_feret_px"])}
    return geom


def _mask_near_seam(mask:np.ndarray,rect:tuple[int,int,int,int],
                    orientation:str,side:str,margin:int)->tuple[np.ndarray,np.ndarray]:
    """Original global (x,y) pixel-center coordinates and exact local IDs."""
    H,W=mask.shape
    if orientation=="vertical":
        band=mask[:,max(0,W-margin):] if side=="left" else mask[:,:min(margin,W)]
        ys,xs=np.nonzero(band)
        if side=="left":xs=xs+max(0,W-margin)
    elif orientation=="horizontal":
        band=mask[max(0,H-margin):,:] if side=="top" else mask[:min(margin,H),:]
        ys,xs=np.nonzero(band)
        if side=="top":ys=ys+max(0,H-margin)
    elif orientation=="diagonal":
        # General corner points filtered based on which sides face the neighbor.
        vx,hx=side.split("-")
        ystart=max(0,H-margin) if vx=="bottom" else 0
        xstart=max(0,W-margin) if hx=="right" else 0
        band=mask[ystart:ystart+min(H,margin),xstart:xstart+min(W,margin)]
        ys,xs=np.nonzero(band)
        ys+=ystart;xs+=xstart
    else:raise ValueError("unknown orientation")
    if len(xs)==0:
        return np.empty((0,2),dtype=np.float32),np.empty(0,np.int32)
    labels=mask[ys,xs].astype(np.int32)
    pts=np.column_stack((xs+rect[0],ys+rect[1])).astype(np.float32)
    return pts,labels


def neighboring_pairs(
    A:np.ndarray,B:np.ndarray,
    rect_a:tuple[int,int,int,int],rect_b:tuple[int,int,int,int],
    orientation:str,side_a:str,side_b:str,
    max_gap:float,
)->list[dict]:
    """Return a candidate for each pair of distinct original source IDs."""
    k=int(np.ceil(max_gap))+2
    pa,la=_mask_near_seam(A,rect_a,orientation,side_a,k)
    pb,lb=_mask_near_seam(B,rect_b,orientation,side_b,k)
    if len(pa)==0 or len(pb)==0:return []
    tree=cKDTree(pa)
    neighbors=tree.query_ball_point(pb,max_gap)
    closest={}
    for ib,js in enumerate(neighbors):
        for ia in js:
            aid=int(la[ia]);bid=int(lb[ib])
            if not (aid>0 and bid>0):continue
            dist=float(np.linalg.norm(pa[ia]-pb[ib]))
            key=(aid,bid)
            prior=closest.get(key)
            if prior is None or dist<prior[0]:
                closest[key]=(dist,pa[ia].copy(),pb[ib].copy())
    return [
        {"a_local":a,"b_local":b,"gap_px":float(v[0]),
         "p0":tuple(int(q) for q in v[1]),
         "p1":tuple(int(q) for q in v[2])}
        for (a,b),v in sorted(closest.items())
    ]


def sampled_bridge_evidence(raw:np.ndarray,p0:tuple[int,int],
                            p1:tuple[int,int])->tuple[float,float,int]:
    """RAW original DN, DoG sigma 8 minus sigma 2 at gap sample points.

    An explicit 28px context on every side avoids endpoint clamping/filter
    discontinuity at tile boundaries. Uses NO defect annotations.
    """
    x0,y0=p0;x1,y1=p1
    xmin=max(0,min(x0,x1)-28);ymin=max(0,min(y0,y1)-28)
    xmax=min(raw.shape[1],max(x0,x1)+29)
    ymax=min(raw.shape[0],max(y0,y1)+29)
    tile=np.asarray(raw[ymin:ymax,xmin:xmax],dtype=np.float32)
    dog=(cv2.GaussianBlur(tile,(0,0),8)-
         cv2.GaussianBlur(tile,(0,0),2))
    dist=float(np.hypot(x1-x0,y1-y0))
    n=max(2,int(math.ceil(dist*2)))
    sampled=np.rint(np.linspace((x0,y0),(x1,y1),n+2)[1:-1]).astype(int)
    cx=np.clip(sampled[:,0]-xmin,0,dog.shape[1]-1)
    cy=np.clip(sampled[:,1]-ymin,0,dog.shape[0]-1)
    v=dog[cy,cx]
    return float(np.median(v)),float(np.mean(v>0)),int(len(v))


def decide_pair(candidate:dict,geom_a:dict,geom_b:dict,raw:np.ndarray,
                cfg:J5Config)->dict:
    """No global union; classify one proposed seam link."""
    cfg.validate()
    gap=float(candidate["gap_px"])
    accepted=False
    direct=gap<=math.sqrt(2)+1.e-3
    align=0.
    med=None;pos=None;count=0
    if direct:
        accepted=True
        reason="exact_8_neighbor_source_continuity"
    else:
        a_len=geom_a["feret"];b_len=geom_b["feret"]
        if min(geom_a["area"],geom_b["area"])<cfg.min_piece_area_px:
            reason="too_small_for_gap_association"
        elif max(a_len,b_len)<cfg.min_line_length_px:
            reason="no_long_segment_anchor"
        else:
            vector=np.asarray(candidate["p1"],float)-np.asarray(candidate["p0"],float)
            vnorm=float(np.linalg.norm(vector))
            if vnorm<=0:raise AssertionError("gap invalid")
            direction=vector/vnorm
            align=max(
                abs(float(np.dot(direction,geom_a["axis"])))
                   if geom_a["reliable"] else 0.,
                abs(float(np.dot(direction,geom_b["axis"])))
                   if geom_b["reliable"] else 0.
            )
            if align<math.cos(math.radians(cfg.angle_tolerance_degrees)):
                reason="incompatible_scratch_direction"
            else:
                med,pos,count=sampled_bridge_evidence(
                    raw,candidate["p0"],candidate["p1"])
                accepted=bool(med>=cfg.min_bridge_dog_dn and
                              pos>=cfg.min_positive_bridge_fraction)
                reason=("strong_aligned_dark_gap" if accepted else
                        "RAW_dark_gap_evidence_insufficient")
    return {**candidate,
            "direct_connected":bool(direct),
            "axis_alignment":round(align,4),
            "bridge_dog_median_dn":round(med,4) if med is not None else None,
            "bridge_positive_fraction":round(pos,4) if pos is not None else None,
            "bridge_sample_count":count,
            "accepted_initial":bool(accepted),
            "accepted":bool(accepted),
            "reason":reason}


def resolve_ambiguous_near_links(edges:list[dict],cfg:J5Config)->list[dict]:
    """Do not join a weak gap candidate with equally plausible alternatives.

    Direct 8-neighbor links are exact source continuity and excluded from this
    conservative ambiguity veto. Only separated-gap inferred links are vetoed.
    """
    bynode=defaultdict(list)
    for i,e in enumerate(edges):
        if e["accepted"] and not e["direct_connected"]:
            bynode[e["a_id"]].append((float(e["gap_px"]),i))
            bynode[e["b_id"]].append((float(e["gap_px"]),i))
    ambiguous=set()
    for node,values in bynode.items():
        values.sort()
        if len(values)<2:continue
        if values[1][0]-values[0][0]<cfg.ambiguity_margin_px:
            for _,index in values:ambiguous.add(index)
    for i in ambiguous:
        edges[i]["accepted"]=False
        edges[i]["reason"]="ambiguous_multiple_nearby_gap_candidates"
    return edges
