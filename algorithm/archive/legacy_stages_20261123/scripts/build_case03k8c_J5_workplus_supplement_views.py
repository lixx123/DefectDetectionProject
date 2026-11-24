"""K8-C dual-frame user views: frozen J5 WORK + K8-C supplementary dark hypotheses.

No object regrading/merging. Original J5 bbox/stats are NOT K8-B H masks.
Suggested new dark contours are K8C proposals, not confirmed real defects.
Uncertain/edge/3-to7 px and micro suggestions have their own images.
All images share same RAW pixel center coordinates at exactly stride=8.
"""
from pathlib import Path
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import save_png
OUT=cfg.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
K8B=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
SIZE=8

def bg(frame):
    raw=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",mode="r",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    img=np.asarray(raw[::SIZE,::SIZE],np.float32)
    lo,hi=np.percentile(img,[1,99.5])
    p=np.uint8(np.clip((img-lo)/max(1.,hi-lo)*255,0,255))
    return cv2.cvtColor(p,cv2.COLOR_GRAY2BGR)

def old_j5_overlay(image,objects):
    result=image.copy()
    old=objects[objects.K8A_region_code_by_original_J5_center==2]
    for s in old.itertuples():
        color=GRADE_COLORS_BGR[s.grade]
        x=int(s.center_x_global)//SIZE
        y=int(s.center_y_global)//SIZE
        if s.grade=="SMALL":
            if 0<=x<result.shape[1] and 0<=y<result.shape[0]:
                result[y,x]=color
        else:
            x0=max(0,int(s.display_bbox_x_global)//SIZE)
            y0=max(0,int(s.display_bbox_y_global)//SIZE)
            x1=min(result.shape[1]-1,int(s.display_bbox_xmax_inclusive)//SIZE)
            y1=min(result.shape[0]-1,int(s.display_bbox_ymax_inclusive)//SIZE)
            cv2.rectangle(result,(x0,y0),(max(x0,x1),max(y0,y1)),
                          color,1,cv2.LINE_8)
    return result,len(old)

def supplement_draw(image,candidates,color,show_id=False):
    result=image.copy()
    for row in candidates.itertuples(index=False):
        a=int(row.bbox_local_x)//SIZE
        b=int(row.candidate_global_y0)//SIZE
        c=int(row.bbox_local_x+row.bbox_width_px-1)//SIZE
        d=int(row.candidate_global_y1_exclusive-1)//SIZE
        a=max(0,min(result.shape[1]-1,a))
        b=max(0,min(result.shape[0]-1,b))
        c=max(a,min(result.shape[1]-1,c))
        d=max(b,min(result.shape[0]-1,d))
        if show_id or (c-a>=2 or d-b>=2):
            cv2.rectangle(result,(a,b),(c,d),color,1,cv2.LINE_8)
        else: result[(b+d)//2,(a+c)//2]=color
        if show_id:
            cv2.putText(result,f"B{row.band_id}-{row.band_component_label}",
              (max(0,a),max(10,b-3)),cv2.FONT_HERSHEY_SIMPLEX,.33,
              color,1,cv2.LINE_8)
    return result

def announce(image,frame,label,note,countstr):
    w=image.shape[1]
    h=np.full((98,w,3),26,np.uint8)
    cv2.putText(h,f"K8-C  | FRAME 26({frame}) | {label}",
       (10,28),cv2.FONT_HERSHEY_SIMPLEX,.59,(239,239,239),1)
    cv2.putText(h,note[:125],(10,53),cv2.FONT_HERSHEY_SIMPLEX,.39,(220,220,220),1)
    cv2.putText(h,countstr[:125],(10,80),cv2.FONT_HERSHEY_SIMPLEX,.42,(210,210,210),1)
    return np.vstack((h,image))

def run():
    for frame in (1,2):
        folder=OUT/f"frame26_{frame}"
        if (folder/"K8C_J5_work_and_supplement_dashboard.json").exists():
            raise FileExistsError("Dashboard already generated")
        old=pd.read_csv(K8B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv",
                        encoding="utf-8-sig")
        data=pd.read_csv(folder/"all_K8B_candidate_objects_complete_K8C_audit.csv",
                         encoding="utf-8-sig")
        base=bg(frame)
        oldimage,nwork=old_j5_overlay(base,old)
        keep=data[data.classification=="PROMISING_DARK_REVIEW"]
        needs=data[data.classification.isin(
            ["UNCERTAIN_REVIEW","BOUNDARY_REVIEW","MICRO_REVIEW"])]
        suspect=data[data.classification=="MICRO_HIDE_SUGGESTION"]
        # Layer order: source J5 remains colored by OLD grade; cyan highlights
        # only new complementary proposal. Does NOT regrade old source objects.
        preview_proposals=supplement_draw(base,keep,(235,225,35),show_id=True)
        both=supplement_draw(oldimage,keep,(235,225,35),show_id=True)
        uncertain=supplement_draw(base,needs,(30,155,240),show_id=False)
        micro=supplement_draw(base,suspect,(90,110,140),show_id=False)
        states=[
          ("01_frozen_J5_WORK_only.png",oldimage,
           "Old J5 original WORK centers: RED big / YELLOW medium / GREEN small.",
           f"Existing WORK-candidate centers {nwork} (not human confirmed)"),
          ("02_K8C_promising_supplement_ONLY.png",preview_proposals,
           "CYAN = experimental RAW/MAD/DoG supported dark candidates, not verified truth.",
           f"Promising supplemental regions {len(keep)}"),
          ("03_J5_WORK_plus_K8C_provisional_supplements.png",both,
           "Original J5 same color, CYAN marks K8C supplemental candidate, 1px boxes.",
           f"Existing J5 WORK {nwork} | K8C promising {len(keep)} (DO NOT SUM AS TRUTH)"),
          ("04_uncertain_boundary_and_micro_review.png",uncertain,
           "ORANGE = pending geometry/noise review, not hidden from archived B.",
           f"Other pending review regions {len(needs)}"),
          ("05_micro_1to2px_HIDE_SUGGESTION_only.png",micro,
           "Grey = suggestion to hide 1-2px micro points on main overview only.",
           f"Uncertain micro suggestions {len(suspect)}; raw B pixels preserved")]
        for name,im,note,count in states:
            save_png(folder/name,announce(im,frame,name[3:-4],note,count))
        details={
           "frame":frame,
           "original_J5_work_center_objects":nwork,
           "original_J5_frozen_all_regions":len(old),
           "K8C_promising_supplemental_review_proposals":len(keep),
           "other_new_uncertain_or_boundary_review_candidates":len(needs),
           "micro_suggest_hide_display_candidates":len(suspect),
           "existing_J5_K8B_H_non_equivalence_disclosed":True,
           "original_J5_grade_area_masks_unchanged":True,
           "K8C_proposals_do_not_count_as_verified_true_defects":True,
           "views_all_on_identical_original_RAW_frame_coordinates":True,
           "preview_scale":SIZE,
           "pixel_pitch_for_existing_J5_um":cfg.PIXEL_SIZE_UM,
           "human_confirmation_still_required_for_K8C_candidates":True,
           "files":[s[0] for s in states]
        }
        (folder/"K8C_J5_work_and_supplement_dashboard.json").write_text(
            json.dumps(details,ensure_ascii=False,indent=2),encoding="utf-8")
        for name,_,_,_ in states:
            file=folder/name
            decoded=cv2.imdecode(np.frombuffer(file.read_bytes(),np.uint8),
                                 cv2.IMREAD_COLOR)
            assert decoded is not None and decoded.shape[1]==base.shape[1]
        print("K8C_WORK_VIEW_READY",json.dumps(details,ensure_ascii=False),flush=True)

if __name__=="__main__":run()
