"""Case03-J5 whole-frame object reconciliation from frozen Case03-J4.

- No rerun of the per-band H3 hysteresis, background screens, morphological
  refinements, or J2.
- Every source detected pixel belongs to precisely one non-overlapping J4
  core. Merging objects never changes these pixels, merely their global ID.
- Direct cross-tile 8-neighbor contact is guaranteed connectivity.
- Noncontact association is an audited *hypothesis*, requiring gap darkness,
  a line direction and absence of ambiguous competing links.
- J4 inferred bridge pixels are display provenance, NEVER measured area.
- Full-frame labels are global unique, pixel sizes are not calibrated microns.
"""
from __future__ import annotations
import functools,math,sys
from collections import defaultdict
from pathlib import Path
import numpy as np,cv2
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03j5_seam_match import (
    J5Config,UnionFind,neighboring_pairs,approximate_geometry,decide_pair,
    resolve_ambiguous_near_links
)
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,GRADE_COLORS_BGR

KNOWN_NEIGHBOR_OFFSETS=(
    (0,1,"vertical","left","right"),
    (1,0,"horizontal","top","bottom"),
    (1,1,"diagonal","bottom-right","top-left"),
    (1,-1,"diagonal","bottom-left","top-right"),
)


def full_diameter(pts:np.ndarray)->float:
    """Exact max Euclidean distance among planar pixel-center convex hulls.

    Rotating calipers on the convex hull, O(h log h) for the hull + O(h)
    for the diameter; avoids O(h^2) for long scratches.
    """
    a=np.asarray(pts,dtype=np.float64).reshape(-1,2)
    if len(a)<2:return 1.
    hull=cv2.convexHull(a.astype(np.float32).reshape(-1,1,2))
    poly=hull.reshape(-1,2).astype(np.float64)
    n=len(poly)
    if n<2:return 1.
    if n==2:return max(1.,float(np.linalg.norm(poly[0]-poly[1])))
    def area(i:int,j:int,k:int)->float:
        e=poly[j]-poly[i];f=poly[k]-poly[i]
        return abs(float(e[0]*f[1]-e[1]*f[0]))
    def sqdist(i:int,j:int)->float:
        d=poly[i]-poly[j]
        return float(d@d)
    j=1
    maximum=1.
    for i in range(n):
        ni=(i+1)%n
        while area(i,ni,(j+1)%n)>area(i,ni,j)+1.e-8:
            j=(j+1)%n
        maximum=max(maximum,sqdist(i,j),sqdist(ni,j))
    return float(np.sqrt(maximum))






def candidate_seam_edges(expected:list[dict],rows:dict[str,dict],
                         bytile:dict,tileload,rawmem,config:J5Config):
    lookup={(int(t["iy"]),int(t["ix"])):t for t in expected}
    examined=0;potential=0;links=[]
    for t in expected:
        for dy,dx,orientation,sideA,sideB in KNOWN_NEIGHBOR_OFFSETS:
            other=lookup.get((t["iy"]+dy,t["ix"]+dx))
            if other is None:continue
            first=t["tile_id"];second=other["tile_id"]
            A,ra=tileload(first);B,rb=tileload(second)
            gap=(math.sqrt(2)+1.e-3 if orientation=="diagonal" else config.gap_max_px)
            proposals=neighboring_pairs(A,B,ra,rb,orientation,sideA,sideB,gap)
            if len(proposals)>config.max_linked_components_per_seam:
                raise RuntimeError("seam candidate overflow, no silent truncation: "+first+" "+second)
            examined+=1;potential+=len(proposals)
            if not proposals:continue
            aidset={int(p["a_local"]) for p in proposals}
            bidset={int(p["b_local"]) for p in proposals}
            def clouds(tilemask,rect,ids,localmap):
                data={}
                for lid in ids:
                    if lid not in localmap:
                        raise AssertionError("seam label missing from J4 object CSV")
                    yy,xx=np.where(tilemask==lid)
                    data[localmap[lid]]=np.column_stack(
                        (xx+rect[0],yy+rect[1])).astype(np.float32)
                return data
            ids_a=bytile[first];ids_b=bytile[second]
            ga=approximate_geometry(rows,clouds(A,ra,aidset,ids_a),config)
            gb=approximate_geometry(rows,clouds(B,rb,bidset,ids_b),config)
            for p in proposals:
                aa=ids_a[p["a_local"]];bb=ids_b[p["b_local"]]
                decided=decide_pair(p,ga[aa],gb[bb],rawmem,config)
                decided.update(
                    a_id=aa,b_id=bb,a_tile=first,b_tile=second,
                    seam_orientation=orientation,
                    a_area_px=int(ga[aa]["area"]),
                    b_area_px=int(gb[bb]["area"]),
                    a_feret_px=round(ga[aa]["feret"],4),
                    b_feret_px=round(gb[bb]["feret"],4)
                )
                links.append(decided)
        if t["ix"]==0 and (t["iy"]==0 or t["iy"]%4==0):
            print("J5_SEAM_PROGRESS",t["iy"],"rows",len(lookup),
                  "seams",examined,"proposals",potential,flush=True)
    resolve_ambiguous_near_links(links,config)
    return links,examined,potential


def moments_and_hulls(
    expected:list[dict],tileload,bytile:dict,
    groups:dict[str,list[str]])->tuple[dict[str,tuple],dict[str,np.ndarray]]:
    """Single pass over 1620 original masks for all centroids and area checks.

    Convex hull points are only retained for objects that need intertile
    diameter recomputation; no full raw image labels are loaded in RAM.
    """
    multis={uid for members in groups.values() if len(members)>1 for uid in members}
    summary={}
    hulls={}
    for it,t in enumerate(expected):
        tile=t["tile_id"]
        mask,rect=tileload(tile)
        ids=bytile.get(tile,{})
        yy,xx=np.nonzero(mask)
        labels=mask[yy,xx]
        n=int(mask.max())+1
        area=np.bincount(labels,minlength=n)
        weighted_x=np.bincount(labels,weights=xx,minlength=n)
        weighted_y=np.bincount(labels,weights=yy,minlength=n)
        for local_id,uid in ids.items():
            if local_id>=n or area[local_id]==0:
                raise AssertionError("J4 row references missing source pixels")
            summary[uid]=(
                int(area[local_id]),
                float(weighted_x[local_id]+rect[0]*area[local_id]),
                float(weighted_y[local_id]+rect[1]*area[local_id])
            )
            if uid in multis:
                py,px=np.where(mask==local_id)
                point=np.column_stack((px+rect[0],py+rect[1]))
                convex=cv2.convexHull(point.astype(np.float32).reshape(-1,1,2))
                hulls[uid]=convex.reshape(-1,2).astype(np.float32)
        if it and it%320==0:
            print("J5_GEOMETRY_PROGRESS",it,"/",len(expected),flush=True)
    if len(summary)!=sum(map(len,bytile.values())):
        raise AssertionError("centroid moment coverage mismatch")
    return summary,hulls


def reconcile(rows:dict[str,dict],edges:list[dict],
              moments:dict[str,tuple],hulls:dict[str,np.ndarray],
              grades:SizeGradeConfig,output_policy="LEGACY_FULL"):
    uf=UnionFind(list(rows))
    success=0;already_linked=0
    for e in sorted((x for x in edges if x["accepted"]),
                    key=lambda x:(0 if x["direct_connected"] else 1,
                                  x["gap_px"],x["a_id"],x["b_id"])):
        if uf.join(e["a_id"],e["b_id"]):
            e["union_performed"]=True;success+=1
        else:
            e["union_performed"]=False;already_linked+=1
    for e in edges:
        if not e["accepted"]:e["union_performed"]=False
    groups=defaultdict(list)
    for uid in rows:
        groups[uf.find(uid)].append(uid)
    out=[]
    for leader,members in groups.items():
        records=[rows[m] for m in members]
        area=sum(int(rows[m]["source_area_px2"]) for m in members)
        actual=sum(moments[m][0] for m in members)
        if area!=actual:raise AssertionError("source pixel area mismatch for "+leader)
        sx=sum(moments[m][1] for m in members)
        sy=sum(moments[m][2] for m in members)
        if len(members)>1:
            diameter=full_diameter(np.vstack([hulls[m] for m in members]))
        else:
            diameter=float(records[0]["source_max_feret_px"])
        grade,reason=grade_size(area,diameter,grades)
        if output_policy=="MEDIUM_LARGE_ONLY" and grade=="SMALL":continue
        xmin=min(int(r["display_bbox_x_global"]) for r in records)
        ymin=min(int(r["display_bbox_y_global"]) for r in records)
        xmax=max(int(r["display_bbox_xmax_inclusive"]) for r in records)
        ymax=max(int(r["display_bbox_ymax_inclusive"]) for r in records)
        sxmin=min(int(r["source_bbox_x_global"]) for r in records)
        symin=min(int(r["source_bbox_y_global"]) for r in records)
        sxmax=max(int(r["source_bbox_x_global"])+int(r["source_bbox_width_px"])-1
                  for r in records)
        symax=max(int(r["source_bbox_y_global"])+int(r["source_bbox_height_px"])-1
                  for r in records)
        if not(xmin<=sxmin<=sxmax<=xmax and ymin<=symin<=symax<=ymax):
            raise AssertionError("global display bbox excluded source")
        if not (0<=xmin<=xmax<cfg.RAW_WIDTH and
                0<=ymin<=ymax<cfg.RAW_HEIGHT):
            raise AssertionError("global bbox exceeded image")
        tileset=sorted(set(str(r["tile_id"]) for r in records))
        touches_frame=bool(xmin==0 or ymin==0 or xmax==cfg.RAW_WIDTH-1
                            or ymax==cfg.RAW_HEIGHT-1)
        obj={
            "_leader":leader,
            "_member_local_ids":sorted(members),
            "center_x_global":round(sx/area,4),
            "center_y_global":round(sy/area,4),
            "display_bbox_x_global":xmin,
            "display_bbox_y_global":ymin,
            "display_bbox_width_px":xmax-xmin+1,
            "display_bbox_height_px":ymax-ymin+1,
            "display_bbox_xmax_inclusive":xmax,
            "display_bbox_ymax_inclusive":ymax,
            "source_bbox_x_global":sxmin,
            "source_bbox_y_global":symin,
            "source_bbox_width_px":sxmax-sxmin+1,
            "source_bbox_height_px":symax-symin+1,
            "source_area_px2":area,
            "source_max_feret_px":round(diameter,4),
            "inferred_bridge_pixels_within_tiles":sum(
                int(r["inferred_bridge_pixels"]) for r in records),
            "grade":grade,
            "grade_reason":reason,
            "local_object_count":len(members),
            "source_region_count":sum(int(r["member_count"]) for r in records),
            "tile_count":len(tileset),
            "cross_tile_merged":len(tileset)>1,
            "touches_full_image_border":touches_frame,
            "unresolved_border_in_full_image":touches_frame,
            "object_is_candidate_not_verified_defect":True,
            "grade_is_provisional_pixel_only":True,
            "area_excludes_inferred_bridge":True,
            "J5_gap_link_review":False
        }
        out.append(obj)
    # Every separated-gap inferred merge gets an explicit review flag.
    gap_roots={
        uf.find(e["a_id"]) for e in edges
        if e["accepted"] and not e["direct_connected"]
    }
    for o in out:
        o["J5_gap_link_review"]=o["_leader"] in gap_roots
    out.sort(key=lambda x:(x["center_y_global"],x["center_x_global"],x["_leader"]))
    idmapping={}
    for i,o in enumerate(out,1):
        label=f"DEFECT_{i:05d}"
        o["global_defect_id"]=label
        for local in o["_member_local_ids"]:
            idmapping[local]=label
        del o["_leader"]
        del o["_member_local_ids"]
    if output_policy=="LEGACY_FULL" and len(idmapping)!=len(rows):
        raise AssertionError("global reconciliation lost local objects")
    return out,idmapping,{
        "small_final_gate_rejected":len(groups)-len(out),
        "accepted_links":sum(e["accepted"] for e in edges),
        "direct_source_connectivity_links":sum(
            e["accepted"] and e["direct_connected"] for e in edges),
        "separated_gap_hypothesis_links":sum(
            e["accepted"] and not e["direct_connected"] for e in edges),
        "successful_union_operations":success,
        "redundant_links_within_existing_group":already_linked,
    }
