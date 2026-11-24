"""Case03-K7: thin 1px outlines + detector-plane dimension labels on BOTH frames.

K7 is a visualization/measurement export ONLY: fixed J5 grade, geometry,
global IDs, source masks, raw, and K5 hypotheses are NEVER overwritten.
Sizes use 3.2 um/detector-pixel; these are IMAGE-PLANE equivalent quantities,
not object-plane physical size without magnification calibration.

Separate medium+large main, small reference, tentative K5 review, all-object
dimension CSV; top-36 native pixel masks have actual 1px contours and size
labels. No fake source areas for inferred bridges.
"""
from __future__ import annotations
from pathlib import Path
import sys,json,math
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import save_png,gray

SOURCE={
  1:cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1",
  2:cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_2_J5_independent_v1"
}
J4={
  1:cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1",
  2:cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_2_J4_independent_v1"
}
RUN_ROOT=cfg.OUTPUT_ROOT/"case03k7_detector_size_annotations"
RUN_DIR=RUN_ROOT/"run_20261012_dualframe_thin_line_3p2um_v2"
PITCH=float(cfg.PIXEL_SIZE_UM)
STRIDE=4
MAIN_LABEL_LIMIT=150
GALLERY_TOP_N=36

def checked_pitch():
    if not 0<PITCH<50:raise ValueError("invalid detector pitch")
    if abs(PITCH-3.2)>1e-10:raise RuntimeError("pitch changed; use new output run ID")
    return PITCH

def detector_table(df:pd.DataFrame)->pd.DataFrame:
    """Derived fields only. Uses J5 source pixels and source max Feret."""
    out=df.copy()
    assert out.global_defect_id.is_unique
    assert (out.source_area_px2>=1).all()
    assert (out.source_max_feret_px>=1).all()
    out["detector_pitch_um_per_pixel"]=PITCH
    out["detector_equiv_max_feret_length_um"]=(
        out.source_max_feret_px.astype(float)*PITCH).round(3)
    out["detector_equiv_detected_area_um2"]=(
        out.source_area_px2.astype(float)*PITCH**2).round(3)
    out["detector_equiv_bbox_width_um"]=(
        out.source_bbox_width_px.astype(float)*PITCH).round(3)
    out["detector_equiv_bbox_height_um"]=(
        out.source_bbox_height_px.astype(float)*PITCH).round(3)
    out["detector_equiv_circle_diameter_um"]=(
        2*np.sqrt(out.source_area_px2.astype(float)/np.pi)*PITCH).round(3)
    out["dimension_calibration_scope"]="DETECTOR_IMAGE_PLANE_EQUIVALENT_NOT_OBJECT_PLANE"
    out["measurement_source"]="J5_ORIGINAL_SOURCE_PIXELS_NO_INFERRED_BRIDGE"
    out["object_plane_magnification_verified"]=False
    out["size_grade_was_reclassified"]=False
    out["candidate_is_not_confirmed_true_defect"]=True
    assert (out.detector_equiv_detected_area_um2>0).all()
    assert (out.detector_equiv_max_feret_length_um>=PITCH).all()
    return out

def label_text(s,with_id:bool=True):
    # Short ASCII labels render cross-platform via cv2; units are microns.
    idshort=str(s.global_defect_id).split("_")[-1]
    l=float(s.detector_equiv_max_feret_length_um)
    area=float(s.detector_equiv_detected_area_um2)
    return (f"#{idshort} " if with_id else "")+f"L{l:.1f}um A{area:.0f}um2"

def title_bar(img,frame,kind,notice):
    header=np.full((94,img.shape[1],3),27,np.uint8)
    for k,(txt,scale) in enumerate([
        (f"26 FRAME {frame} | K7 | {kind}",.62),
        (f"DETECTOR pitch={PITCH:g} um/px; physical object plane NOT calibrated",.49),
        (notice,.43)]):
        cv2.putText(header,txt,(14,26+k*29),cv2.FONT_HERSHEY_SIMPLEX,
                    scale,(238,238,238),1,cv2.LINE_AA)
    return np.vstack((header,img))

def base_preview(raw):
    # Each frame identical 1:4 coordinates; image contrast normalized
    # independently for display only; RAW DN unchanged.
    img=np.asarray(raw[::STRIDE,::STRIDE],np.uint16)
    preview=gray(img)
    assert preview.dtype==np.uint8
    if preview.ndim==2:preview=cv2.cvtColor(preview,cv2.COLOR_GRAY2BGR)
    return preview

def bbox_preview(s):
    left=int(s.display_bbox_x_global)//STRIDE
    top=int(s.display_bbox_y_global)//STRIDE
    right=int(s.display_bbox_xmax_inclusive)//STRIDE
    bottom=int(s.display_bbox_ymax_inclusive)//STRIDE
    # 1-pixel objects still visible as 1px rect; never artificially dilate source.
    return left,top,max(left,right),max(top,bottom)

def no_overlap(box,occupied,pad=2):
    l,t,r,b=box
    for a,c,x,y in occupied:
        if not (r+pad<a or x+pad<l or b+pad<c or y+pad<t):
            return False
    return True

def labelled_box(img,s,occupied,force=False):
    l,t,r,b=bbox_preview(s)
    h,w=img.shape[:2]
    text=label_text(s)
    font=cv2.FONT_HERSHEY_SIMPLEX
    scale=.35
    tw,th=cv2.getTextSize(text,font,scale,1)[0]
    spots=[
        (l,min(h-5,b+th+8)),
        (l,max(th+5,t-5)),
        (r+6,min(h-5,t+th+4)),
        (max(3,l-tw-8),min(h-5,t+th+4)),
    ]
    for x,y in spots:
        x=int(np.clip(x,2,max(2,w-tw-5)))
        y=int(np.clip(y,th+5,h-4))
        box=(x-2,y-th-3,x+tw+2,y+3)
        if not no_overlap(box,occupied):continue
        # Do not place text over object rectangle even if available.
        if not (box[2]<l-2 or box[0]>r+2 or box[3]<t-2 or box[1]>b+2):
            continue
        occupied.append(box)
        # Dark plaque so label remains legible over noisy RAW
        cv2.rectangle(img,(box[0],box[1]),(box[2],box[3]),(30,30,30),-1)
        cv2.putText(img,text,(x,y),font,scale,
                    GRADE_COLORS_BGR[s.grade],1,cv2.LINE_AA)
        return True
    return False

def draw_main(preview,objects,frame):
    clean=preview.copy()
    labeled=preview.copy()
    groups=objects[objects.grade.isin(("MEDIUM","LARGE"))].copy()
    for s in groups.itertuples(index=False):
        l,t,r,b=bbox_preview(s)
        color=GRADE_COLORS_BGR[s.grade]
        cv2.rectangle(clean,(l,t),(r,b),color,1,cv2.LINE_8)
        cv2.rectangle(labeled,(l,t),(r,b),color,1,cv2.LINE_8)
    groups["sort_grade"]=groups.grade.map({"LARGE":0,"MEDIUM":1})
    sorted_objects=groups.sort_values(
        ["sort_grade","source_area_px2"],ascending=[True,False])
    # No false claim of labels for all 720 objects; audit number placed.
    occupied=[]
    attempted=0;placed=0
    for s in sorted_objects.itertuples(index=False):
        if attempted>=MAIN_LABEL_LIMIT:break
        attempted+=1
        if labelled_box(labeled,s,occupied):placed+=1
    clean=title_bar(clean,frame,"MEDIUM+LARGE | THIN 1px",
        f"Objects={len(groups)}; all outlined, no labels to hide RAW. See size CSV and gallery.")
    labeled=title_bar(labeled,frame,"MEDIUM+LARGE | SIZE LABELS",
        f"Labels {placed} / top {attempted} by grade+area; all {len(groups)} in CSV.")
    return clean,labeled,placed

def draw_small(preview,objects,frame):
    img=preview.copy()
    subset=objects[objects.grade=="SMALL"]
    for s in subset.itertuples(index=False):
        x=int(s.center_x_global)//STRIDE
        y=int(s.center_y_global)//STRIDE
        if 0<=x<img.shape[1] and 0<=y<img.shape[0]:
            img[y,x]=GRADE_COLORS_BGR["SMALL"] # exactly one display pixel
    return title_bar(img,frame,"SMALL / REFERENCE ONLY",
        f"{len(subset)} unverified small candidates; 1px marks / size in CSV.")

def object_source_mask(global_id,box,mapping,j4dir):
    x0,y0,x1,y1=box
    mask=np.zeros((y1-y0,x1-x0),bool)
    member=mapping.get_group(global_id)
    bytile={tile:set(p.source_local_object_index.astype(int))
            for tile,p in member.groupby("source_tile_id")}
    for name,localids in bytile.items():
        with np.load(j4dir/"tile_masks"/(name+".npz"),allow_pickle=False) as f:
            lab=f["grouped_source_only_i32"]
            r=[int(q) for q in f["core_xyxy"]]
        ax=max(x0,r[0]);ay=max(y0,r[1])
        bx=min(x1,r[2]);by=min(y1,r[3])
        if ax>=bx or ay>=by:continue
        chunk=lab[ay-r[1]:by-r[1],ax-r[0]:bx-r[0]]
        mask[ay-y0:by-y0,ax-x0:bx-x0]|=np.isin(chunk,list(localids))
    return mask

def make_gallery(raw,objects,frame,dst,j4dir,j5dir):
    """Native source pixel contour is exactly 1px; optionally zoomed panel."""
    members=pd.read_csv(j5dir/"global_object_membership.csv")
    indexed=members.groupby("global_defect_id")
    order=objects[objects.grade.isin(("MEDIUM","LARGE"))].copy()
    order["priority"]=order.grade.map({"LARGE":0,"MEDIUM":1})
    order=order.sort_values(["priority","source_area_px2"],ascending=[True,False]).head(GALLERY_TOP_N)
    cards=[];audit=[]
    for s in order.itertuples(index=False):
        x0=max(0,int(s.display_bbox_x_global)-20)
        y0=max(0,int(s.display_bbox_y_global)-20)
        x1=min(cfg.RAW_WIDTH,int(s.display_bbox_xmax_inclusive)+21)
        y1=min(cfg.RAW_HEIGHT,int(s.display_bbox_ymax_inclusive)+21)
        # Long unusual source objects are represented with full bbox, not clipped.
        r=np.asarray(raw[y0:y1,x0:x1],np.uint16)
        if r.size==0:raise RuntimeError("empty gallery ROI")
        old=gray(r)
        if old.ndim==2:im=cv2.cvtColor(old,cv2.COLOR_GRAY2BGR)
        else:im=old.copy()
        src=object_source_mask(s.global_defect_id,(x0,y0,x1,y1),indexed,j4dir)
        assert src.sum()==int(s.source_area_px2),(s.global_defect_id,int(src.sum()),s.source_area_px2)
        # Native source pixels define length/area; the 1-pixel outline is
        # drawn AFTER resizing the background so the stroke stays 1 DISPLAY pixel.
        target=320
        height,width=im.shape[:2]
        factor=min(target/max(width,1),target/max(height,1))
        target_w=max(1,round(width*factor));target_h=max(1,round(height*factor))
        scaled=cv2.resize(im,(target_w,target_h),interpolation=(
            cv2.INTER_AREA if factor<1 else cv2.INTER_NEAREST))
        scaled_mask=cv2.resize(src.astype(np.uint8),(target_w,target_h),
                               interpolation=cv2.INTER_NEAREST)
        if src.any() and not scaled_mask.any():
            yi,xi=np.where(src)
            px=min(target_w-1,max(0,round(float(xi.mean())*factor)))
            py=min(target_h-1,max(0,round(float(yi.mean())*factor)))
            scaled_mask[py,px]=1
        outlines,_=cv2.findContours(scaled_mask,cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(scaled,outlines,-1,GRADE_COLORS_BGR[s.grade],1,cv2.LINE_8)
        card=np.full((378,340,3),26,np.uint8)
        x=(340-target_w)//2;y=44+(320-target_h)//2
        card[y:y+target_h,x:x+target_w]=scaled
        cv2.putText(card,
            f"FRAME{frame} {s.global_defect_id} ({s.grade[0]})",
            (7,20),cv2.FONT_HERSHEY_SIMPLEX,.48,(230,230,230),1,cv2.LINE_AA)
        cv2.putText(card,
            f"L {float(s.detector_equiv_max_feret_length_um):.1f}um; A {float(s.detector_equiv_detected_area_um2):.1f}um2",
            (7,371),cv2.FONT_HERSHEY_SIMPLEX,.45,(230,230,230),1,cv2.LINE_AA)
        cards.append(card)
        audit.append({"global_defect_id":s.global_defect_id,"source_pixels_verified":int(src.sum()),
                      "gallery_roi_xyxy":(x0,y0,x1,y1)})
    ncol=4
    paths=[]
    for i in range(0,len(cards),12):
        batch=cards[i:i+12]
        while len(batch)%ncol:batch.append(np.full_like(batch[-1],26))
        sheet=np.vstack([np.hstack(batch[j:j+ncol])
                          for j in range(0,len(batch),ncol)])
        p=dst/f"large_medium_gallery_{i+1:02d}_to_{min(i+12,len(cards)):02d}.png"
        save_png(p,sheet);paths.append(p.name)
    return paths,audit

def k5_trial_table(frame):
    """Trial RAW halo pixels DO NOT enter official J5 metrics."""
    if frame==1:
        p=cfg.OUTPUT_ROOT/"case03k_adaptive_group_trial/run_20261012_K5_adaptive_and_J5_group_review_v2/k5_23_case_adaptive_and_group_audit.csv"
        df=pd.read_csv(p)
        selected=df[["sample_id","frozen_J5_ID","original_J5_source_pixels",
                     "adaptive_outer_area_px2","display_status","group_status",
                     "floor_selected_sigma"]].copy()
        selected=selected.rename(columns={
           "frozen_J5_ID":"global_defect_id",
           "original_J5_source_pixels":"source_area_px2",
           "adaptive_outer_area_px2":"trial_contour_area_px2"
        })
    else:
        p=cfg.OUTPUT_ROOT/"case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1/all_288_frozen_K5_audit.csv"
        df=pd.read_csv(p)
        selected=df[df.K5_adaptive_area_px2>0][[
            "sample_id","frozen_second_frame_J5_ID","original_source_area_px2",
            "K5_adaptive_area_px2","display_status","group_status",
            "noise_multiplier_chosen"]].copy()
        selected=selected.rename(columns={
           "frozen_second_frame_J5_ID":"global_defect_id",
           "original_source_area_px2":"source_area_px2",
           "K5_adaptive_area_px2":"trial_contour_area_px2",
           "noise_multiplier_chosen":"floor_selected_sigma"})
    selected["detector_pitch_um_per_pixel"]=PITCH
    selected["trial_contour_area_detector_um2"]=(
        selected.trial_contour_area_px2.astype(float)*PITCH**2).round(3)
    selected["official_J5_mask_and_area_replaced"]=False
    selected["estimated_contour_not_physical_truth"]=True
    return selected

def run():
    checked_pitch()
    if RUN_DIR.exists():raise FileExistsError("K7 refuses to overwrite existing report")
    RUN_DIR.mkdir(parents=True)
    summary={"stage":"CASE03K7_THIN_DETECTOR_EQUIV_SIZE_ANNOTATIONS",
             "pitch_um_per_detector_pixel":PITCH,
             "pixel_area_um2":PITCH**2,
             "preview_stride":STRIDE,
             "outline_width_preview_px":1,
             "outline_width_native_gallery_px":1,
             "object_plane_scale_calibrated":False,
             "official_J5_source_masks_changed":False,
             "original_K5_areas_changed":False,"frames":{}}
    for frame in (1,2):
        j5=SOURCE[frame];j4=J4[frame]
        fdir=RUN_DIR/f"frame26_{frame}"
        fdir.mkdir()
        df=pd.read_csv(j5/"global_defects.csv")
        state=json.loads((j5/"summary.json").read_text(encoding="utf-8"))
        assert state["stage"]=="J5_COMPLETE" and len(df)==int(state["global_candidate_objects"])
        mm=detector_table(df)
        mm.to_csv(fdir/"all_J5_objects_detector_sizes_um.csv",encoding="utf-8-sig",index=False)
        mm[mm.grade.isin(("MEDIUM","LARGE"))].to_csv(
            fdir/"medium_large_sizes_um.csv",encoding="utf-8-sig",index=False)
        mm[mm.grade=="SMALL"].to_csv(fdir/"small_reference_sizes_um.csv",
            encoding="utf-8-sig",index=False)
        raw=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",mode="r",
            dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
        prev=base_preview(raw)
        clean,annotated,placed=draw_main(prev,mm,frame)
        small=draw_small(prev,mm,frame)
        names=[
            "medium_large_thin_1px.png",
            "medium_large_with_detector_sizes_um.png",
            "small_reference_thin_1px.png"]
        for name,img in zip(names,(clean,annotated,small)):
            save_png(fdir/name,img)
            assert cv2.imdecode(np.frombuffer((fdir/name).read_bytes(),np.uint8),
                               cv2.IMREAD_COLOR) is not None
        galleries,source_audit=make_gallery(raw,mm,frame,fdir,j4,j5)
        trial=k5_trial_table(frame)
        trial.to_csv(fdir/"K5_estimated_contour_sizes_FOR_REVIEW_ONLY.csv",
                     encoding="utf-8-sig",index=False)
        summary["frames"][str(frame)]={
            "J5_source_path":str(j5),
            "all_global_candidates":len(mm),
            "medium":int((mm.grade=="MEDIUM").sum()),
            "large":int((mm.grade=="LARGE").sum()),
            "small":int((mm.grade=="SMALL").sum()),
            "medium_large_top_labels_placed":placed,
            "gallery_N":len(source_audit),
            "gallery_source_pixel_values_verified":True,
            "gallery_images":galleries,
            "K5_trial_rows":len(trial),
            "K5_trial_area_retains_separate_status":True,
            "preview_images":names,
            "measurement_formula_area":"N_source_pixels*(3.2 um/px)^2",
            "measurement_formula_feret":"source_max_feret_px*(3.2 um/px)",
            "not_object_plane_calibrated":True,
            "all_original_J5_objects_and_grades_retained":True
        }
        (fdir/"gallery_pixel_conservation.json").write_text(
            json.dumps(source_audit,ensure_ascii=False,indent=2),encoding="utf-8")
        print("K7_FRAME_COMPLETE",frame,
              len(mm),"gallery",len(source_audit),
              "labels",placed,flush=True)
    (RUN_DIR/"summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K7_TWO_FRAMES_COMPLETE",json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=="__main__":run()
