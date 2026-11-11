"""Case03-J2 continuous scratch display, keeping original exact candidate mask.

W005 first, then all existing 27 pilot windows. Each composite contour is
verified to be 8-connected for every inferred grouped object.
"""
from __future__ import annotations
import sys,json,argparse
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03j_continuous_contour import (
    ContinuousConfig,reconstruct_continuous_visual
)
from src.detection.case03j_fragment_association import AssociationConfig
from src.detection.case03i_size_grade import SizeGradeConfig,GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import gray,save_png

I=ROOT/"outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1"
J1=ROOT/"outputs/case03j_fragment_association/run_20261010_W005_fragment_link_guarded_v2"


def draw(raw:np.ndarray,labels:np.ndarray,bridge:np.ndarray,
         objects:list[dict],regions:list[dict],heading:str)->np.ndarray:
    H,W=raw.shape
    shade=gray(raw)
    old=shade.copy()
    old_fill=old.copy()
    for r in regions:
        tag=int(r["local_region_id"])
        old_fill[labels==tag]=GRADE_COLORS_BGR[r["size_grade"]]
    old=cv2.addWeighted(old_fill,.26,old,.74,0)
    for r in regions:
        m=np.uint8(labels==int(r["local_region_id"]))
        cont,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(old,cont,-1,GRADE_COLORS_BGR[r["size_grade"]],1)
    frames=[("RAW",shade),("Old: disconnected",old)]
    # Unified physical-hypothesis contour. BOTH source + inferred path use
    # same displayed grade, with one contour around the visual union.
    combined=np.zeros_like(labels,dtype=np.int32)
    originals=np.zeros_like(labels,dtype=np.int32)
    for idx,o in enumerate(objects,1):
        ids=[int(x) for x in o["members"].split(";")]
        originals[np.isin(labels,ids)]=idx
    combined[:]=originals
    combined[(combined==0)&(bridge>0)]=bridge[(combined==0)&(bridge>0)]
    continuous=shade.copy()
    fill=shade.copy()
    provenance=shade.copy()
    prov_fill=shade.copy()
    for idx,o in enumerate(objects,1):
        c=GRADE_COLORS_BGR[o["size_grade"]]
        fill[combined==idx]=c
        prov_fill[originals==idx]=c
    continuous=cv2.addWeighted(fill,.25,continuous,.75,0)
    provenance=cv2.addWeighted(prov_fill,.25,provenance,.75,0)
    # Mark bridge pixels in BLUE-CYAN, visibly distinct from old detections.
    provenance[bridge>0]=(240,210,65)
    for idx,o in enumerate(objects,1):
        if not np.any(combined==idx):continue
        c=GRADE_COLORS_BGR[o["size_grade"]]
        contour,_=cv2.findContours(np.uint8(combined==idx),
                                  cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(continuous,contour,-1,c,1)
        cv2.drawContours(provenance,contour,-1,c,1)
        if o["member_count"]>1:
            x=int(round(o["center_x_global"]-regions[0]["_global_x0"]))
            y=int(round(o["center_y_global"]-regions[0]["_global_y0"]))
            tx=max(1,min(W-58,x-15));ty=max(16,min(H-4,y-22))
            cv2.putText(continuous,o["object_id"].rsplit("C",1)[-1],
                        (tx,ty),cv2.FONT_HERSHEY_SIMPLEX,.48,
                        (10,10,10),2,cv2.LINE_AA)
            cv2.putText(continuous,o["object_id"].rsplit("C",1)[-1],
                        (tx,ty),cv2.FONT_HERSHEY_SIMPLEX,.48,
                        c,1,cv2.LINE_AA)
    frames.append(("NEW: one continuous contour",continuous))
    frames.append(("Provenance: CYAN = inferred bridge",provenance))
    panels=[]
    for label,im in frames:
        z=cv2.resize(im,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
        z=cv2.copyMakeBorder(z,66,0,0,0,cv2.BORDER_CONSTANT,value=(27,27,27))
        cv2.putText(z,heading+" / "+label,(12,26),
                    cv2.FONT_HERSHEY_SIMPLEX,.62,(244,244,244),1,cv2.LINE_AA)
        cv2.putText(z,"raw mask unchanged | inferred pixels excluded from area",
                    (12,51),cv2.FONT_HERSHEY_SIMPLEX,.42,
                    (222,222,222),1,cv2.LINE_AA)
        panels.append(z)
    return np.hstack(panels)


def run(runid:str,only_w005:bool=True)->Path:
    out=cfg.OUTPUT_ROOT/"case03j_continuous"/runid
    if out.exists():raise FileExistsError(out)
    (out/"figures").mkdir(parents=True)
    (out/"masks").mkdir()
    entries=pd.read_csv(I/"all_candidate_size_grades.csv",encoding="utf-8-sig")
    edges=pd.read_csv(J1/"association_link_audit.csv",encoding="utf-8-sig")
    acfg=AssociationConfig()
    ccfg=ContinuousConfig(
        context_max_gap_px=cfg.CASE03J2_CONTEXT_MAX_GAP_PX,
        main_stroke_min_length_px=cfg.CASE03J2_MAIN_STROKE_MIN_LENGTH_PX,
        main_stroke_min_aspect=cfg.CASE03J2_MAIN_STROKE_MIN_ASPECT,
        piece_min_area_px=cfg.CASE03J2_PIECE_MIN_AREA_PX,
        piece_min_length_px=cfg.CASE03J2_PIECE_MIN_LENGTH_PX,
        max_perpendicular_offset_px=cfg.CASE03J2_MAX_PERPENDICULAR_OFFSET_PX,
        context_angle_tolerance_deg=cfg.CASE03J2_CONTEXT_ANGLE_TOLERANCE_DEG,
        bridge_half_width_px=cfg.CASE03J2_BRIDGE_HALF_WIDTH_PX,
        bridge_min_dog_dn=cfg.CASE03J2_BRIDGE_MIN_DOG_DN,
        max_context_links_per_group=cfg.CASE03J2_MAX_CONTEXT_LINKS_PER_GROUP,
        ambiguous_gap_margin_px=cfg.CASE03J2_AMBIGUOUS_GAP_MARGIN_PX,
    )
    grade=SizeGradeConfig()
    rawmem={frame:np.memmap(cfg.DATA_ROOT/(fn+".raw"),dtype=">u2",
                            mode="r",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
            for frame,fn in [("26_1","26 (1)"),("26_2","26 (2)")]}
    rows_out=[];edges_out=[];bridges=[];window_stats=[]
    files=sorted((I/"region_masks").glob("*_graded_masks.npz"))
    if only_w005:
        files=[p for p in files if p.stem=="26_1_E2_W005_graded_masks"]
    for p in files:
        frame="26_1" if p.name.startswith("26_1_") else "26_2"
        name=p.stem[len(frame)+1:].removesuffix("_graded_masks")
        with np.load(p,allow_pickle=False) as z:
            rect=tuple(int(x) for x in z["roi_global_xyxy"])
            labels=z["local_region_labels_int32"].astype(np.int32)
            original=z["exact_final_mask"].astype(bool)
        raw=np.asarray(rawmem[frame][rect[1]:rect[3],rect[0]:rect[2]],
                       dtype=np.uint16)
        r=entries.loc[(entries.frame==frame)&(entries.window_id==name)].to_dict("records")
        for record in r:
            record["_global_x0"]=rect[0];record["_global_y0"]=rect[1]
        e=edges.loc[(edges.frame==frame)&(edges.window_id==name)].to_dict("records")
        objects,objmap,bridge,combined,new_edges,bridge_log=reconstruct_continuous_visual(
            labels,raw,r,e,grade,acfg,ccfg)
        if not np.array_equal(objmap>0,original):raise AssertionError("source modified")
        if np.any((bridge>0)&original):raise AssertionError("inferred overlap source")
        if not np.array_equal(combined>0,original | (bridge>0)):
            raise AssertionError("composite changed source")
        for o in objects:
            o.update(source_frame=frame)
            rows_out.append(o)
        for a in new_edges:
            edges_out.append({"frame":frame,"window_id":name,**a})
        for a in bridge_log:
            bridges.append({"frame":frame,"window_id":name,**a})
        stats={
            "frame":frame,"window":name,
            "original_regions":len(r),
            "combined_objects":len(objects),
            "linked_objects":sum(o["member_count"]>1 for o in objects),
            "original_pixels":int(original.sum()),
            "inferred_bridge_pixels":int(np.count_nonzero(bridge)),
            "visual_composite_pixels":int(np.count_nonzero(combined)),
            "preserved_original_mask":True,
            "visually_disconnected_linked_objects":sum(
                o["continuous_display_components"]!=1 for o in objects
                if o["member_count"]>1
            )
        }
        window_stats.append(stats)
        im=draw(raw,labels,bridge,objects,r,name)
        save_png(out/"figures"/(frame+"_"+name+"_connected_fourpanel.png"),im)
        np.savez_compressed(out/"masks"/(frame+"_"+name+"_contour_provenance.npz"),
            source_exact_mask=original.astype(np.uint8),
            original_region_labels=labels,
            grouped_original_only_ids=objmap,
            inferred_bridge_ids=bridge,
            one_piece_visual_ids=combined,
            roi_global_xyxy=np.array(rect,np.int32))
        print("WROTE",frame,name,
              "fragments",len(r),"objects",len(objects),
              "inferred px",stats["inferred_bridge_pixels"],
              "groups",[(o["members"],o["size_grade"])
                         for o in objects if o["member_count"]>1],flush=True)
    pd.DataFrame(rows_out).to_csv(out/"object_level_grades.csv",index=False,
                                   encoding="utf-8-sig")
    pd.DataFrame(edges_out).to_csv(out/"all_link_edges_with_context.csv",index=False,
                                    encoding="utf-8-sig")
    pd.DataFrame(bridges).to_csv(out/"inferred_bridge_pixel_audit.csv",index=False,
                                    encoding="utf-8-sig")
    pd.DataFrame(window_stats).to_csv(out/"window_continuity_check.csv",index=False,
                                       encoding="utf-8-sig")
    summary={
        "scope":"W005_FIRST" if only_w005 else "27 ROI trial",
        "source_mask_modified":False,
        "source_area_excludes_inferred_bridge":True,
        "all_linked_display_objects_8_connected":all(
                s["visually_disconnected_linked_objects"]==0
                for s in window_stats),
        "original_regions":sum(x["original_regions"] for x in window_stats),
        "new_continuous_objects":sum(x["combined_objects"] for x in window_stats),
        "total_inferred_bridge_pixels":sum(x["inferred_bridge_pixels"] for x in window_stats),
        "config":asdict(ccfg),
        "original_dataset":str(I),
        "pairwise_link_audit_source":str(J1),
        "evidence":"ROI RAW dark-ridge + context long-axis; no manual labels",
        "not_blind_validated":True
    }
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("COMPLETE",json.dumps(summary,ensure_ascii=False),flush=True)
    return out


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",default="run_20261010_W005_one_piece_v1")
    p.add_argument("--all",action="store_true")
    args=p.parse_args()
    run(args.run_id,only_w005=not args.all)
