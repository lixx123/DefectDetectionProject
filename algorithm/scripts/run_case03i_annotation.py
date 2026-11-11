"""Case03-I: automatically annotate selected original RAW ROIs with candidate size grades.

FRAME1: read frozen Case03-H final states, apply to old H-anchored labels.
FRAME2: read frozen Case03-T fixed170/230 + F/G/H displayed final mask.
This stage does not tune thresholds, run independent defect proposals, or
modify previous results. All human clicked points used ONLY for optional
viewpoint cropping AFTER automatic mask grading.
"""
from __future__ import annotations
import argparse,json,sys
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import (
    SizeGradeConfig,extract_regions,render_marked_raw,GRADE_COLORS_BGR
)
from scripts.run_case03g_joint_noise_refinement import save_png,gray,crop_bounds

E2=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"
H=ROOT/"outputs/case03h_texture/run_20261010_10target_texture_dog_guard_v3"
T=ROOT/"outputs/case03t_threshold_pilot/run_20261010_sample26_frame2_three_methods_v1"
TAGS={"SMALL":1,"MEDIUM":2,"LARGE":3}


def input_rois_frame1():
    history=pd.read_csv(H/"candidate_screen_audit.csv",encoding="utf-8-sig")
    for p in sorted((E2/"masks").glob("E2_W*_labels.npz")):
        name=p.name.removesuffix("_labels.npz")
        with np.load(p,allow_pickle=False) as z:
            h=z["H170_230"].astype(bool)
            refined=z["all_object_labels"].astype(np.int32)
            x0,y0=map(int,z["roi_origin_raw_xy"])
        decisions=history.loc[history.window_id==name].set_index("local_H_id")
        n,labels,stats,_=cv2.connectedComponentsWithStats(
            h.astype(np.uint8),8)
        assert len(decisions)==n-1
        kept=[]
        for j in range(1,n):
            local=f"Hlocal_{j:04d}"
            state=str(decisions.at[local,"case03h_state"])
            if state!="hide_suggestion":kept.append(j)
        mask=np.isin(refined,kept)
        assert not np.any(mask & (refined==0))
        yield "26_1",name,(x0,y0,x0+h.shape[1],y0+h.shape[0]),mask


def input_rois_frame2():
    for p in sorted((T/"masks").glob("*_method_masks.npz")):
        name=p.name.removesuffix("_method_masks.npz")
        with np.load(p,allow_pickle=False) as z:
            rect=tuple(int(v) for v in z["roi_global_xyxy"])
            mask=z["fixed170_230_final"].astype(bool)
            assert np.all(mask <= np.ones(mask.shape,dtype=bool))
        yield "26_2",name,rect,mask


def contact_sheet(files:list[Path],path:Path,cols:int=3)->None:
    tiles=[]
    for p in files:
        im=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if im is None:raise OSError("invalid comparison PNG "+str(p))
        target=(448,478)  # original 3*256 with 78 title, resized preview
        tiles.append(cv2.resize(im,target,interpolation=cv2.INTER_AREA))
    if not tiles:raise ValueError("no tiles to show")
    while len(tiles)%cols:
        tiles.append(np.full_like(tiles[-1],(25,25,25),dtype=np.uint8))
    sheet=np.vstack([np.hstack(tiles[i:i+cols]) for i in range(0,len(tiles),cols)])
    save_png(path,sheet)


def frame_overview(frame:str,raw:np.memmap,rows:list[dict],dest:Path,
                   output_edge:int=2048)->None:
    # This image is an ROI LOCATION MAP, not proof of full-frame detection.
    H0,W0=raw.shape
    factor=max(1,int(np.ceil(max(H0,W0)/output_edge)))
    reduced=np.asarray(raw[::factor,::factor],dtype=np.uint16)
    base=gray(reduced)
    scale_x=base.shape[1]/W0
    scale_y=base.shape[0]/H0
    for r in rows:
        x,y,x1,y1=[int(r[z]) for z in ("roi_x0","roi_y0","roi_x1","roi_y1")]
        a=(int(round(x*scale_x)),int(round(y*scale_y)))
        b=(int(round(x1*scale_x)),int(round(y1*scale_y)))
        cv2.rectangle(base,a,b,(210,210,210),1)
        level=r["largest_grade"]
        if level!="NONE":
            cx=int(round(((x+x1)/2)*scale_x))
            cy=int(round(((y+y1)/2)*scale_y))
            cv2.circle(base,(cx,cy),6,GRADE_COLORS_BGR[level],-1,
                       lineType=cv2.LINE_AA)
    banner=98
    out=cv2.copyMakeBorder(base,banner,0,0,0,cv2.BORDER_CONSTANT,
                           value=(25,25,25))
    cv2.putText(out,f"RAW26 FRAME {frame[-1]} | ROI ONLY | UNINSPECTED AREA IS NOT CLEAR",
                (16,30),cv2.FONT_HERSHEY_SIMPLEX,.58,
                (238,238,238),1,cv2.LINE_AA)
    cv2.putText(out,f"{len(rows)} ROIs; max grade per ROI is shown by center color",
                (16,60),cv2.FONT_HERSHEY_SIMPLEX,.57,
                (220,220,220),1,cv2.LINE_AA)
    cv2.putText(out,"GREEN: SMALL    YELLOW: MEDIUM    RED: LARGE    PIXEL UNITS",
                (16,85),cv2.FONT_HERSHEY_SIMPLEX,.5,
                (215,215,215),1,cv2.LINE_AA)
    save_png(dest,out)


def ten_first_frame_focus(raw:np.memmap,grade_labels:dict[str,np.ndarray],
                          source_regions:dict[str,list[dict]],
                          rois:dict[str,tuple[int,int,int,int]],
                          output:Path)->None:
    refs=pd.read_csv(E2/"ten_manual_targets_posthoc_evaluation.csv")
    if len(refs)!=10:raise AssertionError("need all 10 earlier views")
    output.mkdir(exist_ok=True)
    if list(output.glob("*.png")):
        raise FileExistsError("review images already exist; refusing overwrite")
    for ref in refs.itertuples(index=False):
        name=ref.window_id
        origin=rois[name]
        lx0,ly0,lx1,ly1=crop_bounds(
            int(ref.clicked_RAW_x),int(ref.clicked_RAW_y),
            (origin[0],origin[1]),(256,256),size=160)
        r0=np.asarray(raw[origin[1]+ly0:origin[1]+ly1,
                          origin[0]+lx0:origin[0]+lx1],dtype=np.uint16)
        labels=grade_labels[name][ly0:ly1,lx0:lx1]
        bgr=gray(r0)
        overlay=bgr.copy()
        for reg in source_regions[name]:
            locid=int(reg["local_region_id"])
            selected=labels==locid
            if not np.any(selected):continue
            color=GRADE_COLORS_BGR[reg["size_grade"]]
            overlay[selected]=color
        bgr=cv2.addWeighted(overlay,.23,bgr,.77,0)
        for reg in source_regions[name]:
            selected=np.uint8(labels==int(reg["local_region_id"]))
            if not np.any(selected):continue
            color=GRADE_COLORS_BGR[reg["size_grade"]]
            contour,_=cv2.findContours(selected,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(bgr,contour,-1,color,1)
        expanded=cv2.resize(bgr,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)
        expanded=cv2.copyMakeBorder(expanded,55,0,0,0,cv2.BORDER_CONSTANT,
                                    value=(29,29,29))
        cv2.putText(expanded,str(ref.manual_target_id)+" | RAW26 frame1",
                    (12,28),cv2.FONT_HERSHEY_SIMPLEX,.65,
                    (245,245,245),1,cv2.LINE_AA)
        cv2.putText(expanded,"color = provisional size (not physical acceptance)",
                    (12,47),cv2.FONT_HERSHEY_SIMPLEX,.4,
                    (220,220,220),1,cv2.LINE_AA)
        save_png(output/(str(ref.manual_target_id)+"_auto_grades.png"),expanded)


def run(run_id:str,grade:SizeGradeConfig)->Path:
    grade.validate()
    dest=cfg.OUTPUT_ROOT/"case03i_annotation"/run_id
    if dest.exists():raise FileExistsError("refuse overwrite "+str(dest))
    for folder in ("frame26_1_9roi","frame26_2_18roi",
                   "region_masks","focus_first10"):
        (dest/folder).mkdir(parents=True)
    # Input frame ROIs are frozen from previous stages, NOT new selected seeds.
    raw_by_frame={
        "26_1":np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH)),
        "26_2":np.memmap(cfg.DATA_ROOT/"26 (2).raw",mode="r",dtype=">u2",
                shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH)),
    }
    catalogs=[];per_roi=[];roimap={};first_labels={};first_regions={}
    figures={"26_1":[],"26_2":[]}
    for frame,name,rect,mask in list(input_rois_frame1())+list(input_rois_frame2()):
        x0,y0,x1,y1=rect
        if name in roimap and frame=="26_1":raise AssertionError("duplicate frame1 roi")
        if not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_:
            raise ValueError("input mask must be bool")
        raw=np.asarray(raw_by_frame[frame][y0:y1,x0:x1],dtype=np.uint16)
        regions,labels=extract_regions(mask,grade,name,rect)
        counted=sum(v["area_px2"] for v in regions)
        if counted!=int(mask.sum()):raise AssertionError("incomplete grading")
        for r in regions:
            r.update(frame=frame,source_mask="Case03H_v3" if frame=="26_1"
                    else "Case03T_fixed170230_plus_H",
                     is_full_frame_validated=False,
                     cross_window_merged=False,
                     area_px2_is_lower_bound_if_touches_border=r["touches_window_border"])
            catalogs.append(r)
        grade_values=np.zeros_like(labels,dtype=np.uint8)
        for r in regions:
            grade_values[labels==r["local_region_id"]]=TAGS[r["size_grade"]]
        assert int(np.count_nonzero(grade_values))==int(mask.sum())
        area_counts={g:sum(r["size_grade"]==g for r in regions)
                     for g in TAGS}
        biggest=max([("SMALL","MEDIUM","LARGE").index(
                    r["size_grade"]) for r in regions],default=-1)
        highest=("SMALL","MEDIUM","LARGE")[biggest] if biggest>=0 else "NONE"
        per_roi.append({
            "frame":frame,"window_id":name,
            "roi_x0":x0,"roi_y0":y0,"roi_x1":x1,"roi_y1":y1,
            "candidate_regions":len(regions),
            "small_count":area_counts["SMALL"],
            "medium_count":area_counts["MEDIUM"],
            "large_count":area_counts["LARGE"],
            "largest_grade":highest,
            "refined_candidate_mask_pixels":int(mask.sum()),
            "border_truncated_components":sum(r["touches_window_border"] for r in regions),
            "scope_is_roi_only":True,
            "physical_objects_may_span_multiple_regions":True,
        })
        out_folder="frame26_1_9roi" if frame=="26_1" else "frame26_2_18roi"
        shown=render_marked_raw(raw,mask,regions,labels,
               title=f"{frame} / {name} | FIXED170/230 + CASE03H",
               roi_origin_xy=(x0,y0),zoom=3)
        result=dest/out_folder/(f"{name}_RAW_auto_graded.png")
        save_png(result,shown)
        figures[frame].append(result)
        np.savez_compressed(dest/"region_masks"/(frame+"_"+name+"_graded_masks.npz"),
            roi_global_xyxy=np.array(rect,dtype=np.int32),
            exact_final_mask=mask.astype(np.uint8),
            grade_mask_uint8=grade_values,
            local_region_labels_int32=labels)
        if frame=="26_1":
            first_labels[name]=grade_values
            # focus overlay expects local_region_id not grade pixel codes
            first_labels[name]=labels.copy()
            first_regions[name]=regions
            roimap[name]=rect
        print("GRADED",frame,name,"components",len(regions),
              area_counts,flush=True)
    assert len(figures["26_1"])==9 and len(figures["26_2"])==18
    ten_first_frame_focus(raw_by_frame["26_1"],first_labels,first_regions,
                          roimap,dest/"focus_first10")
    assert len(list((dest/"focus_first10").glob("*.png")))==10
    dframe=pd.DataFrame(catalogs)
    droi=pd.DataFrame(per_roi)
    dframe.to_csv(dest/"all_candidate_size_grades.csv",index=False,encoding="utf-8-sig")
    droi.to_csv(dest/"roi_grade_summary.csv",index=False,encoding="utf-8-sig")
    contact_sheet(figures["26_1"],dest/"frame26_1_9roi_contact.png")
    contact_sheet(figures["26_2"],dest/"frame26_2_18roi_contact.png")
    for frame in ("26_1","26_2"):
        frame_overview(frame,raw_by_frame[frame],
                       [r for r in per_roi if r["frame"]==frame],
                       dest/(frame+"_ROI_locations_on_raw_overview.png"))
    summary={
        "grade_type":"PROVISIONAL IMAGE-PIXEL SIZE, NOT ACCEPTANCE",
        "grade_config":asdict(grade),
        "green_small":"area<medium area limit AND length<medium length limit",
        "yellow_medium":"area>=medium or length>=medium; smaller than large limits",
        "red_large":"area>=large area limit OR length>=large length limit",
        "length_definition":"max pairwise Euclidean distance between convex hull pixel CENTERS; minimum 1 px",
        "area_definition":"count of pixels in each 8-connected DISPLAYED refined candidate mask",
        "image_pixel_not_object_plane_micron":True,
        "full_frame_done":False,
        "scope":"9 frame1 windows and 18 frame2 windows (some overlap), not full raw frame",
        "cross_window_deduplication_done":False,
        "human_points_in_detection":False,
        "frame1_sources":"Case03H v3 decision + frozen Case03E2 refined object label",
        "frame2_sources":"Case03T fixed170_230_final computed independently from frame2",
        "rejected_candidates_drawn_in_graded_overlay":False,
        "candidate_not_confirmed_defect":True,
        "per_frame_counts":[{
            "frame":frame,
            "windows":len([r for r in per_roi if r["frame"]==frame]),
            "roi_connected_components":len([r for r in catalogs if r["frame"]==frame]),
            "small":sum(r["size_grade"]=="SMALL" and r["frame"]==frame for r in catalogs),
            "medium":sum(r["size_grade"]=="MEDIUM" and r["frame"]==frame for r in catalogs),
            "large":sum(r["size_grade"]=="LARGE" and r["frame"]==frame for r in catalogs),
        } for frame in ("26_1","26_2")]
    }
    (dest/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
    print("OUTPUT",dest,flush=True)
    return dest


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",default="run_20261010_frame1_frame2_pixel_grade_v1")
    args=p.parse_args()
    run(args.run_id,SizeGradeConfig(
        medium_area_min_px2=cfg.CASE03I_MEDIUM_AREA_MIN_PX2,
        large_area_min_px2=cfg.CASE03I_LARGE_AREA_MIN_PX2,
        medium_length_min_px=cfg.CASE03I_MEDIUM_LENGTH_MIN_PX,
        large_length_min_px=cfg.CASE03I_LARGE_LENGTH_MIN_PX,
        connectivity=cfg.CASE03I_CONNECTIVITY,
        max_per_window=cfg.CASE03I_MAX_COMPONENTS_PER_WINDOW))
