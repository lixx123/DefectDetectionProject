"""Case03-J1: scratch-fragment association pilot, frozen Case03-I ROI masks.

No full-frame detection, no manual annotations in the decision. Exact original
binary mask untouched; physical object is an auditable grouping hypothesis.
"""
from __future__ import annotations
import argparse,json,sys
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03j_fragment_association import AssociationConfig,associate_fragments
from src.detection.case03i_size_grade import SizeGradeConfig,GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import save_png,gray
I=ROOT/"outputs/case03i_annotation/run_20261010_frame1_frame2_pixel_grade_v1"
OUT=cfg.OUTPUT_ROOT/"case03j_fragment_association"


def make_canvas(raw:np.ndarray,oldlab:np.ndarray,objmap:np.ndarray,
                regions:list[dict],objects:list[dict],window:str)->np.ndarray:
    """RAW, original 8-connected grading, group-aware recoloring (no gap fill)."""
    H,W=raw.shape
    rawpic=gray(raw)
    gradings={int(x["local_region_id"]):x["size_grade"] for x in regions}
    object_gradings={i:o["size_grade"] for i,o in enumerate(objects,1)}
    frames=[rawpic.copy()]
    for regions_mask,gr in ((oldlab,gradings),(objmap,object_gradings)):
        vis=rawpic.copy()
        fill=rawpic.copy()
        for j,grade in gr.items():
            if not np.any(regions_mask==j):continue
            color=GRADE_COLORS_BGR[grade]
            fill[regions_mask==j]=color
        vis=cv2.addWeighted(fill,.26,vis,.74,0)
        for j,grade in gr.items():
            material=np.uint8(regions_mask==j)
            if not material.any():continue
            contours,_=cv2.findContours(material,cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(vis,contours,-1,GRADE_COLORS_BGR[grade],1)
        if regions_mask is objmap:
            # One ID per hypothesized physical object. No connecting line drawn.
            for ix,o in enumerate(objects,1):
                if o["member_count"]<2:continue
                x=int(o["center_x_global"]-regions[0]["_global_x0"])
                y=int(o["center_y_global"]-regions[0]["_global_y0"])
                pt=(max(0,min(W-36,x)),max(12,min(H-3,y-6)))
                cv2.putText(vis,f"{ix:03d}",pt,cv2.FONT_HERSHEY_SIMPLEX,
                            .45,(20,20,20),2,cv2.LINE_AA)
                cv2.putText(vis,f"{ix:03d}",pt,cv2.FONT_HERSHEY_SIMPLEX,
                            .45,GRADE_COLORS_BGR[o["size_grade"]],1,cv2.LINE_AA)
        frames.append(vis)
    panels=[]
    for title,im in zip(("RAW","individual regions","grouped hypothesis"),frames):
        z=cv2.resize(im,None,fx=3,fy=3,interpolation=cv2.INTER_NEAREST)
        z=cv2.copyMakeBorder(z,60,0,0,0,cv2.BORDER_CONSTANT,
                            value=(30,30,30))
        cv2.putText(z,f"{window} / {title}",(12,28),
                    cv2.FONT_HERSHEY_SIMPLEX,.72,(245,245,245),1,cv2.LINE_AA)
        cv2.putText(z,"Exact mask conserved; size grade only",(12,52),
                    cv2.FONT_HERSHEY_SIMPLEX,.48,(220,220,220),1,cv2.LINE_AA)
        panels.append(z)
    return np.hstack(panels)


def run(run_id:str)->Path:
    dest=OUT/run_id
    if dest.exists():raise FileExistsError(dest)
    (dest/"figures_first9").mkdir(parents=True)
    (dest/"figures_second18").mkdir()
    (dest/"exact_masks").mkdir()
    cfgJ=AssociationConfig(
        max_gap_px=cfg.CASE03J_MAX_LINK_GAP_PX,
        min_core_area_px=cfg.CASE03J_MIN_CORE_AREA_PX,
        min_piece_area_px=cfg.CASE03J_MIN_PIECE_AREA_PX,
        min_secondary_length_px=cfg.CASE03J_MIN_PIECE_LENGTH_PX,
        strong_aspect_ratio=cfg.CASE03J_STRONG_ASPECT_RATIO,
        angle_tolerance_deg=cfg.CASE03J_ANGLE_TOLERANCE_DEG,
        min_bridge_dog_median_dn=cfg.CASE03J_MIN_BRIDGE_DOG_MEDIAN_DN,
        min_bridge_dog_positive_fraction=cfg.CASE03J_MIN_BRIDGE_POSITIVE_FRACTION,
        small_bridge_gap_px=cfg.CASE03J_SHORT_CONNECTOR_GAP_PX,
        min_piece_dog_median_dn=cfg.CASE03J_MIN_PIECE_DOG_MEDIAN_DN,
        min_core_length_px=cfg.CASE03J_MIN_CORE_LENGTH_PX,
    )
    grade=SizeGradeConfig(
        medium_area_min_px2=cfg.CASE03I_MEDIUM_AREA_MIN_PX2,
        large_area_min_px2=cfg.CASE03I_LARGE_AREA_MIN_PX2,
        medium_length_min_px=cfg.CASE03I_MEDIUM_LENGTH_MIN_PX,
        large_length_min_px=cfg.CASE03I_LARGE_LENGTH_MIN_PX,
    )
    raw={
        "26_1":np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",
                         shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH),dtype=">u2"),
        "26_2":np.memmap(cfg.DATA_ROOT/"26 (2).raw",mode="r",
                         shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH),dtype=">u2"),
    }
    by_region=pd.read_csv(I/"all_candidate_size_grades.csv",encoding="utf-8-sig")
    objs=[];edges=[];members=[];summary=[]
    for p in sorted((I/"region_masks").glob("*_graded_masks.npz")):
        frame="26_1" if p.name.startswith("26_1_") else "26_2"
        name=p.name[len(frame)+1:].removesuffix("_graded_masks.npz")
        with np.load(p,allow_pickle=False) as z:
            rect=tuple(int(v) for v in z["roi_global_xyxy"])
            mask=z["exact_final_mask"].astype(bool)
            labels=z["local_region_labels_int32"].astype(np.int32)
        rows=by_region.loc[(by_region.frame==frame)&
                           (by_region.window_id==name)].to_dict("records")
        for r in rows:
            r["_global_x0"]=rect[0]
            r["_global_y0"]=rect[1]
        original=np.asarray(raw[frame][rect[1]:rect[3],rect[0]:rect[2]],
                            dtype=np.uint16)
        objects,adj,regions,objectmap=associate_fragments(
            labels,rows,original,cfgJ,grade
        )
        assert np.array_equal(objectmap>0,mask)
        for o in objects:
            o["frame"]=frame
            objs.append(o)
        for a in adj:
            edges.append({"frame":frame,"window_id":name,**a})
        for r in regions:
            members.append({"frame":frame,"window_id":name,**r})
        joined=[o for o in objects if o["member_count"]>1]
        summary.append({
            "frame":frame,"window_id":name,
            "separate_region_count":len(rows),
            "after_association_object_count":len(objects),
            "linked_group_count":len(joined),
            "regions_in_linked_groups":sum(int(o["member_count"]) for o in joined),
            "accepted_links":sum(bool(a["accepted"]) for a in adj),
            "rejected_nearby_pairs":sum(not a["accepted"] for a in adj),
            "original_mask_pixels":int(mask.sum()),
            "grouped_mask_pixels":int(np.count_nonzero(objectmap)),
            "no_new_pixels_created":True,
            "physical_identity_not_yet_confirmed":True
        })
        image=make_canvas(original,labels,objectmap,rows,objects,name)
        folder="figures_first9" if frame=="26_1" else "figures_second18"
        save_png(dest/folder/(name+"_original_vs_grouped.png"),image)
        np.savez_compressed(dest/"exact_masks"/(p.stem+"_groupmap.npz"),
            original_mask=mask.astype(np.uint8),
            source_region_labels=labels,
            grouped_object_labels=objectmap,
            rect_xyxy=np.asarray(rect,dtype=np.int32))
        print("GROUPED",frame,name,
              f"{len(rows)}->{len(objects)}",
              "linked",[(o["member_ids"],o["size_grade"]) for o in joined],
              flush=True)
    pd.DataFrame(objs).to_csv(dest/"object_hypotheses.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(edges).to_csv(dest/"association_link_audit.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(members).to_csv(dest/"source_region_to_object.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(summary).to_csv(dest/"window_before_after_counts.csv",
                                  index=False,encoding="utf-8-sig")
    stats={
        "method":"conservative_direction_gap_dark_DoG_cross_component_grouping",
        "windows":len(summary),
        "frame1_windows":9,"frame2_windows":18,
        "old_region_count":sum(r["separate_region_count"] for r in summary),
        "new_group_hypothesis_count":sum(r["after_association_object_count"] for r in summary),
        "linked_groups":sum(r["linked_group_count"] for r in summary),
        "old_mask_pixels":sum(r["original_mask_pixels"] for r in summary),
        "new_mask_pixels":sum(r["grouped_mask_pixels"] for r in summary),
        "is_window_only_not_full_frame":True,
        "objects_are_hypotheses_not_verified_physical_defects":True,
        "human_points_not_used":True,
        "no_mask_pixels_added_or_removed":True,
        "not_auto_tuned_to_manual_reference":True,
        "config":asdict(cfgJ),
        "W005":[r for r in summary if r["frame"]=="26_1" and r["window_id"]=="E2_W005"]
    }
    (dest/"summary.json").write_text(json.dumps(stats,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("FINAL",json.dumps(stats,ensure_ascii=False),flush=True)
    return dest


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",default="run_20261010_W005_fragment_link_pilot_v1")
    args=p.parse_args()
    run(args.run_id)
