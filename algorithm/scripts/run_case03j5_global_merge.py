"""Case03-J5 whole-frame object reconciliation from frozen Case03-J4.

- No rerun of H170/230, background screens, morphological refinements, or J2.
- Every source detected pixel belongs to precisely one non-overlapping J4
  core. Merging objects never changes these pixels, merely their global ID.
- Direct cross-tile 8-neighbor contact is guaranteed connectivity.
- Noncontact association is an audited *hypothesis*, requiring gap darkness,
  a line direction and absence of ambiguous competing links.
- J4 inferred bridge pixels are display provenance, NEVER measured area.
- Full-frame labels are global unique, pixel sizes are not calibrated microns.
"""
from __future__ import annotations
import argparse, functools,json,math,sys,time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03j4_fullscan import tiles,json_save
from src.detection.case03j5_seam_match import (
    J5Config,UnionFind,neighboring_pairs,approximate_geometry,decide_pair,
    resolve_ambiguous_near_links
)
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import gray,save_png

J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
OUTPUT_ROOT=cfg.OUTPUT_ROOT/"case03j5_global"
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


def load_input_rows(path:Path,config:J5Config):
    state=json.loads((path/"run_status.json").read_text(encoding="utf-8"))
    if (state.get("stage")!="J4_COMPLETE" or
        state.get("completed_tiles")!=state.get("planned_tiles")):
        raise ValueError("J4 not complete: do not create global IDs")
    expected=tiles((cfg.RAW_HEIGHT,cfg.RAW_WIDTH),cfg.CASE03J4_CORE_SIZE_PX)
    schedule=path/'scheduled_tiles.json'
    if schedule.exists():
        planned=json.loads(schedule.read_text(encoding='utf8'))
        if not planned or len({t['tile_id'] for t in planned})!=len(planned) or any(t not in expected for t in planned):
            raise ValueError('invalid J4 schedule/global grid')
        for t in planned:
            status=json.loads((path/'tile_status'/(t['tile_id']+'.json')).read_text(encoding='utf8'))
            if status.get('stage')!='J4_TILE_COMPLETE' or status.get('core_xyxy')!=t['core_xyxy']:
                raise ValueError('J4 scheduled tile missing or geometry changed')
        expected=planned
    if state["planned_tiles"]!=len(expected):
        raise ValueError("tile geometry changed from J4")
    frame=pd.read_csv(path/"j4_unmerged_tile_objects.csv",encoding="utf-8-sig")
    if len(frame)!=int(state["candidate_j4_local_objects"]):
        raise ValueError("J4 input count mismatch")
    if frame["object_id"].duplicated().any():
        raise ValueError("J4 local object IDs are not unique")
    necessary={"object_id","tile_id","local_object_index","source_area_px2",
        "source_max_feret_px","display_bbox_x_global","display_bbox_y_global",
        "display_bbox_xmax_inclusive","display_bbox_ymax_inclusive",
        "source_bbox_x_global","source_bbox_y_global",
        "source_bbox_width_px","source_bbox_height_px",
        "inferred_bridge_pixels","member_count"}
    if necessary-set(frame.columns):raise ValueError("missing J4 columns")
    rows={str(t["object_id"]):t for t in frame.to_dict("records")}
    bytile=defaultdict(dict)
    for uid,row in rows.items():
        bytile[str(row["tile_id"])][int(row["local_object_index"])]=uid
    return expected,rows,bytile


def tile_loader(path:Path):
    @functools.lru_cache(maxsize=128)
    def load(name:str):
        with np.load(path/"tile_masks"/(name+".npz"),allow_pickle=False) as z:
            source=z["grouped_source_only_i32"].copy()
            rect=tuple(int(v) for v in z["core_xyxy"])
        return source,rect
    return load


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
              grades:SizeGradeConfig):
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
    if len(idmapping)!=len(rows):
        raise AssertionError("global reconciliation lost local objects")
    return out,idmapping,{
        "accepted_links":sum(e["accepted"] for e in edges),
        "direct_source_connectivity_links":sum(
            e["accepted"] and e["direct_connected"] for e in edges),
        "separated_gap_hypothesis_links":sum(
            e["accepted"] and not e["direct_connected"] for e in edges),
        "successful_union_operations":success,
        "redundant_links_within_existing_group":already_linked,
    }


def overview(rawmem:np.memmap,objects:list[dict],out:Path,frame_label:str="26_1")->None:
    stride=8
    raw_small=np.asarray(rawmem[::stride,::stride],dtype=np.uint16)
    base=gray(raw_small)
    all_overlay=base.copy()
    clear_overlay=base.copy()
    for o in objects:
        idx=o["global_defect_id"]
        grade=o["grade"]
        x0=int(o["display_bbox_x_global"]//stride)
        y0=int(o["display_bbox_y_global"]//stride)
        x1=int(o["display_bbox_xmax_inclusive"]//stride)
        y1=int(o["display_bbox_ymax_inclusive"]//stride)
        pt=(int(o["center_x_global"]//stride),
            int(o["center_y_global"]//stride))
        color=GRADE_COLORS_BGR[grade]
        if grade=="SMALL":
            cv2.circle(all_overlay,pt,1,color,-1,cv2.LINE_8)
        else:
            cv2.rectangle(all_overlay,(x0,y0),(x1,y1),color,1)
            cv2.rectangle(clear_overlay,(x0,y0),(x1,y1),color,1)
            if grade=="LARGE" and x1-x0>=20:
                cv2.putText(clear_overlay,idx.replace("DEFECT_","D"),
                            (x0,max(10,y0-2)),cv2.FONT_HERSHEY_SIMPLEX,
                            .25,color,1,cv2.LINE_AA)
    for file,im,subtitle in [
        ("full_frame_all_sizes_unreviewed.png",all_overlay,
         "SMALL dot / MEDIUM box / LARGE box | all candidate objects"),
        ("full_frame_medium_large_unreviewed.png",clear_overlay,
         "MEDIUM + LARGE only | absence of markers is NOT a defect-free claim"),
    ]:
        pad=85
        dest=cv2.copyMakeBorder(im,pad,0,0,0,cv2.BORDER_CONSTANT,value=(25,25,25))
        cv2.putText(dest,f"CASE03-J5 GLOBAL OBJECTS | PROVISIONAL | {frame_label.replace('_', ' FRAME')}",
                    (12,26),cv2.FONT_HERSHEY_SIMPLEX,.54,
                    (232,232,232),1,cv2.LINE_AA)
        cv2.putText(dest,subtitle,(12,50),cv2.FONT_HERSHEY_SIMPLEX,.41,
                    (215,215,215),1,cv2.LINE_AA)
        cv2.putText(dest,f"Total {len(objects)} candidate objects, not confirmed defects",
                    (12,74),cv2.FONT_HERSHEY_SIMPLEX,.40,
                    (215,215,215),1,cv2.LINE_AA)
        save_png(out/file,dest)


def review_crops(rawmem:np.memmap,objects:list[dict],
                 membership:dict[str,str],bytile:dict,tileload,out:Path,
                 limit:int=20,j4_input:Path|None=None)->None:
    j4_input=J4 if j4_input is None else Path(j4_input)
    """Object-level montage over full RAW; source region mask and inferred
    J4 bridge provenance are colored independently."""
    folder=out/"review_crops"
    folder.mkdir()
    selections=sorted(objects,key=lambda r:(
        -r["source_area_px2"],-r["source_max_feret_px"]))[:limit]
    # Add an object nearest to historical W005 center to visually inspect the
    # same engineering area; this reference point DOES NOT influence matching.
    w005=[r for r in objects if
          2910<=r["center_x_global"]<=3220 and
          1050<=r["center_y_global"]<=1210 and r["grade"]=="LARGE"]
    if w005:
        extra=max(w005,key=lambda o:o["source_area_px2"])
        if extra not in selections:selections.append(extra)
    for obj in selections:
        x0=max(0,int(obj["display_bbox_x_global"])-24)
        y0=max(0,int(obj["display_bbox_y_global"])-24)
        x1=min(cfg.RAW_WIDTH,int(obj["display_bbox_xmax_inclusive"])+25)
        y1=min(cfg.RAW_HEIGHT,int(obj["display_bbox_ymax_inclusive"])+25)
        if x1<=x0 or y1<=y0:continue
        raw=np.asarray(rawmem[y0:y1,x0:x1],dtype=np.uint16)
        original=np.zeros(raw.shape,np.uint8)
        bridge=np.zeros(raw.shape,np.uint8)
        member_tiles={
            key.split("_C",1)[0] for key,globalid in membership.items()
            if globalid==obj["global_defect_id"]}
        for name in member_tiles:
            with np.load(j4_input/"tile_masks"/(name+".npz"),allow_pickle=False) as z:
                src=z["grouped_source_only_i32"]
                vis=z["inferred_bridge_i32"]
                rect=tuple(int(v) for v in z["core_xyxy"])
            xx0=max(rect[0],x0);xx1=min(rect[2],x1)
            yy0=max(rect[1],y0);yy1=min(rect[3],y1)
            if xx0>=xx1 or yy0>=yy1:continue
            mask_src=np.zeros((yy1-yy0,xx1-xx0),bool)
            mask_br=np.zeros_like(mask_src)
            for loc,gid in membership.items():
                if gid!=obj["global_defect_id"] or not loc.startswith(name+"_C"):
                    continue
                n=int(loc.rsplit("_C",1)[1])
                cut=(slice(yy0-rect[1],yy1-rect[1]),
                     slice(xx0-rect[0],xx1-rect[0]))
                mask_src|=(src[cut]==n)
                mask_br|=(vis[cut]==n)
            clip=(slice(yy0-y0,yy1-y0),slice(xx0-x0,xx1-x0))
            original[clip][mask_src]=1
            bridge[clip][mask_br & ~mask_src]=1
        if int(original.sum())!=int(obj["source_area_px2"]):
            raise AssertionError("review crop source area differs from object table")
        source=gray(raw)
        painted=source.copy()
        painted[original>0]=GRADE_COLORS_BGR[obj["grade"]]
        painted[bridge>0]=(235,220,75)
        overlay=cv2.addWeighted(painted,.32,source,.68,0)
        contou,_=cv2.findContours(np.uint8((original>0)|(bridge>0)),
                                  cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay,contou,-1,GRADE_COLORS_BGR[obj["grade"]],1)
        bx=int(obj["display_bbox_x_global"])-x0;by=int(obj["display_bbox_y_global"])-y0
        ex=int(obj["display_bbox_xmax_inclusive"])-x0
        ey=int(obj["display_bbox_ymax_inclusive"])-y0
        cv2.rectangle(overlay,(bx,by),(ex,ey),
                      GRADE_COLORS_BGR[obj["grade"]],1)
        # Protect from huge atlas file for broad band source.
        reduce=max(1,int(np.ceil(max(raw.shape)/1024)))
        def scaled(im):
            return cv2.resize(im,(max(1,im.shape[1]//reduce),
                                  max(1,im.shape[0]//reduce)),
                              interpolation=cv2.INTER_AREA)
        left=scaled(source);right=scaled(overlay)
        width=min(left.shape[1],right.shape[1])
        content=np.hstack((left[:,:width],right[:,:width]))
        png=cv2.copyMakeBorder(content,66,0,0,0,cv2.BORDER_CONSTANT,value=(27,27,27))
        cv2.putText(png,f'{obj["global_defect_id"]} | {obj["grade"]} | source A={obj["source_area_px2"]}px2',
                    (12,25),cv2.FONT_HERSHEY_SIMPLEX,.50,(240,240,240),1,cv2.LINE_AA)
        cv2.putText(png,"LEFT RAW / RIGHT GLOBAL BOX + CYAN INFERRED PIXELS",
                    (12,49),cv2.FONT_HERSHEY_SIMPLEX,.39,(215,215,215),1,cv2.LINE_AA)
        save_png(folder/(obj["global_defect_id"]+"_review.png"),png)


def run(run_id:str,review_limit:int=20,
        input_J4_run:Path|None=None,input_raw_file:Path|None=None,
        frame_label:str="26_1")->Path:
    input_J4_run=J4 if input_J4_run is None else Path(input_J4_run)
    out=OUTPUT_ROOT/run_id
    if out.exists():raise FileExistsError("Refuse overwrite: "+str(out))
    out.mkdir(parents=True)
    config=J5Config(
        gap_max_px=cfg.CASE03J5_GAP_MAX_PX,
        min_line_length_px=cfg.CASE03J5_MIN_LINE_LENGTH_PX,
        min_piece_area_px=cfg.CASE03J5_MIN_PIECE_AREA_PX,
        min_line_aspect=cfg.CASE03J5_MIN_LINE_ASPECT,
        angle_tolerance_degrees=cfg.CASE03J5_ANGLE_TOL_DEG,
        min_bridge_dog_dn=cfg.CASE03J5_BRIDGE_DOG_MIN_DN,
        min_positive_bridge_fraction=cfg.CASE03J5_BRIDGE_POSITIVE_FRACTION,
        ambiguity_margin_px=cfg.CASE03J5_AMBIGUITY_GAP_PX)
    config.validate()
    expected,rows,bytile=load_input_rows(input_J4_run,config)
    rawpath=cfg.DATA_ROOT/"26 (1).raw" if input_raw_file is None else Path(input_raw_file)
    rawmem=np.memmap(rawpath,mode="r",dtype=">u2",
                     shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    tileload=tile_loader(input_J4_run)
    snapshot={
        "stage":"J5","source_run":str(input_J4_run),
        "raw_frame":str(rawpath),"frame_label":frame_label,
        "source_j4_status":"J4_COMPLETE",
        "total_tiles":len(expected),"local_object_count":len(rows),
        "geometry":asdict(config),"global_dimensions":list(rawmem.shape),
        "source_pixel_preservation":True,
        "associations_are_not_defect_ground_truth":True,
    }
    json_save(out/"config_snapshot.json",snapshot)
    tic=time.perf_counter()
    edges,seams,proposed=candidate_seam_edges(
        expected,rows,bytile,tileload,rawmem,config)
    if edges:
        flat=[{k:v for k,v in e.items() if k not in ("p0","p1")}
              |{"p0_global_xy":str(e["p0"]),"p1_global_xy":str(e["p1"])}
              for e in edges]
        pd.DataFrame(flat).to_csv(
            out/"cross_tile_matching_audit.csv",index=False,encoding="utf-8-sig")
    uf=UnionFind(list(rows))
    for e in edges:
        if e["accepted"]:uf.join(e["a_id"],e["b_id"])
    groups=defaultdict(list)
    for key in rows:groups[uf.find(key)].append(key)
    moments,hulls=moments_and_hulls(expected,tileload,bytile,groups)
    grades=SizeGradeConfig(
        medium_area_min_px2=cfg.CASE03I_MEDIUM_AREA_MIN_PX2,
        large_area_min_px2=cfg.CASE03I_LARGE_AREA_MIN_PX2,
        medium_length_min_px=cfg.CASE03I_MEDIUM_LENGTH_MIN_PX,
        large_length_min_px=cfg.CASE03I_LARGE_LENGTH_MIN_PX)
    objects,mapping,meta=reconcile(rows,edges,moments,hulls,grades)
    pd.DataFrame(objects,columns=None if objects else ['global_defect_id','center_x_global','center_y_global',
        'source_area_px2','source_max_feret_px','source_bbox_x_global','source_bbox_y_global',
        'source_bbox_width_px','source_bbox_height_px','grade']).to_csv(out/"global_defects.csv",index=False,
                                 encoding="utf-8-sig")
    mem=[]
    for loc in sorted(mapping):
        base=rows[loc]
        mem.append({"global_defect_id":mapping[loc],
                    "J4_local_object_id":loc,
                    "source_tile_id":str(base["tile_id"]),
                    "source_local_object_index":int(base["local_object_index"]),
                    "source_area_px2":int(base["source_area_px2"]),
                    "original_region_members":str(base["original_region_members"]),
                    "source_pixels_unchanged":True})
    pd.DataFrame(mem,columns=None if mem else ['global_defect_id','J4_local_object_id','source_tile_id',
        'source_local_object_index','source_area_px2','original_region_members','source_pixels_unchanged']).to_csv(out/"global_object_membership.csv",
                             index=False,encoding="utf-8-sig")
    overview(rawmem,objects,out,frame_label=frame_label)
    if review_limit:
        review_crops(rawmem,objects,mapping,bytile,tileload,out,review_limit,
                     j4_input=input_J4_run)
    total_area=sum(int(x["source_area_px2"]) for x in objects)
    j4_area=sum(int(x["source_area_px2"]) for x in rows.values())
    if total_area!=j4_area:raise AssertionError("global area double count or loss")
    grades_count={grade:sum(x["grade"]==grade for x in objects)
                  for grade in ("SMALL","MEDIUM","LARGE")}
    reported={
        "stage":"J5_COMPLETE",
        "source_J4_tiles":len(expected),
        "original_J4_unmerged_objects":len(rows),
        "global_candidate_objects":len(objects),
        "source_area_before_pixels":j4_area,
        "source_area_after_pixels":total_area,
        "source_area_unchanged":True,
        "pairwise_seams_scanned":seams,
        "candidate_pairs_considered":proposed,
        "grade_counts":grades_count,
        "objects_spanning_multiple_tiles":sum(
            bool(x["cross_tile_merged"]) for x in objects),
        "objects_with_gap_link_review":sum(
            bool(x["J5_gap_link_review"]) for x in objects),
        "edge_accept_stats":meta,
        "full_image_completed":len(expected)==len(tiles(rawmem.shape,cfg.CASE03J4_CORE_SIZE_PX)),
        "scheduled_detection_region_completed":True,
        "physical_ground_truth_evaluated":False,
        "precision_recall_not_available_without_manual_labels":True,
        "pixel_grade_not_acceptance":True,
        "elapsed_seconds":round(time.perf_counter()-tic,2)
    }
    json_save(out/"summary.json",reported)
    print("J5_GLOBAL_COMPLETED",json.dumps(reported,ensure_ascii=False),flush=True)
    return out


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",default="run_20261012_frame26_1_global_j5_v1")
    p.add_argument("--review-limit",type=int,default=20)
    args=p.parse_args()
    run(args.run_id,review_limit=args.review_limit)
