"""K8C prioritized user display with tested K5 RAW contours.

Main: frozen J5 WORK MEDIUM/LARGE only + genuinely enlarged, controlled
K5RAW preliminary medium/large outlines. Small candidates on reference
map; unresolved K5RAW expansions only in review appendix.
No original J5 or B/K8C masks changed; no physical grading accepted.
"""
from pathlib import Path
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03i_size_grade import GRADE_COLORS_BGR
from scripts.run_case03g_joint_noise_refinement import save_png

BASE=cfg.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
K8B=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8C=cfg.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
STRIDE=8

def display_bg(frame):
    raw=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",
                  mode="r",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    sub=np.asarray(raw[::STRIDE,::STRIDE],np.float32)
    low,high=np.percentile(sub,[1,99.5])
    base=np.uint8(np.clip((sub-low)/max(1,high-low)*255,0,255))
    return cv2.cvtColor(base,cv2.COLOR_GRAY2BGR)

def frozen_j5_main(base,objects):
    mediumlarge=objects[(objects.K8A_region_code_by_original_J5_center==2)
                        &objects.grade.isin(["MEDIUM","LARGE"])].copy()
    main=base.copy()
    for s in mediumlarge.itertuples(index=False):
        x0,y0=int(s.display_bbox_x_global)//STRIDE,int(s.display_bbox_y_global)//STRIDE
        x1,y1=int(s.display_bbox_xmax_inclusive)//STRIDE,int(s.display_bbox_ymax_inclusive)//STRIDE
        cv2.rectangle(main,(x0,y0),(max(x0,x1),max(y0,y1)),
                      GRADE_COLORS_BGR[s.grade],1,cv2.LINE_8)
    return main,mediumlarge

def smallmap(base,objects,candidates):
    frame=base.copy()
    group=objects[(objects.K8A_region_code_by_original_J5_center==2)
                  &(objects.grade=="SMALL")]
    for s in group.itertuples(index=False):
        x=int(s.center_x_global)//STRIDE
        y=int(s.center_y_global)//STRIDE
        if 0<=x<frame.shape[1] and 0<=y<frame.shape[0]:
            frame[y,x]=GRADE_COLORS_BGR["SMALL"]
    # Small K8-C promising/subject-to-review are not noise -- see green dot map.
    for item in candidates.itertuples(index=False):
        if item.original_B_size_grade!="SMALL" and item.proposal_size_grade_REVIEW_ONLY!="SMALL":
            continue
        with np.load(pathmask(item),allow_pickle=False) as masks:
            mask=masks["original_B_seed"].astype(bool)
            bounds=masks["full_resolution_roi_global_xyxy"]
        ys,xs=np.where(mask)
        if not len(xs):continue
        x=int((float(xs.mean())+bounds[0])/STRIDE)
        y=int((float(ys.mean())+bounds[1])/STRIDE)
        if 0<=x<frame.shape[1] and 0<=y<frame.shape[0]:
            frame[y,x]=(210,205,45) # cyan B supplemental/uncertain small
    return frame,len(group)

def pathmask(item):
    return BASE/f"frame26_{int(item.frame)}"/f"band{int(item.band_id):02d}"/(
            f"F{int(item.frame)}_B{int(item.band_id)}_C{int(item.candidate_label):05d}_all_masks.npz")

def overlay_proposed(image,records,render_unapproved=False,make_labels=True):
    result=image.copy();log=[]
    for rec in records.itertuples(index=False):
        if not render_unapproved:
            if (rec.K5RAW_noise_k_sigma_selected!=rec.K5RAW_noise_k_sigma_selected
               or not str(rec.status).startswith("PROVISIONAL_RAW")):
                continue
            if rec.proposal_size_grade_REVIEW_ONLY=="SMALL":
                continue
        with np.load(pathmask(rec),allow_pickle=False) as f:
            mask=f["proposed_after_safety_gate"].astype(bool)
            src=f["original_B_seed"].astype(bool)
            bounds=f["full_resolution_roi_global_xyxy"]
            rawtrial=f["raw_k1p5"].astype(bool)
        if render_unapproved:
            mask=rawtrial if rawtrial.sum()>src.sum() else src
        x0,y0=[int(z) for z in bounds[:2]]
        # Draw source-pixel contours AFTER zoom reduction so 1 DISPLAY PIXEL thick.
        # For a mask not in a continuous 8x8 display-grid block avoid fake area:
        mini=cv2.resize(np.uint8(mask),(16,16),interpolation=cv2.INTER_AREA)>0
        yy,xx=np.where(mini)
        if not len(xx):continue
        xoff=x0//STRIDE
        yoff=y0//STRIDE
        xmin=max(0,xoff);ymin=max(0,yoff)
        yend=min(result.shape[0],yoff+16)
        xend=min(result.shape[1],xoff+16)
        if yend<=ymin or xend<=xmin:continue
        # geometric mapping when x0 not integer multiple of stride:
        # project each native contour vertex directly to RAW global/stride
        cnt,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
        pts=[]
        for c in cnt:
            data=c.reshape(-1,2).astype(np.int32)
            data[:,0]=(data[:,0]+x0)//STRIDE
            data[:,1]=(data[:,1]+y0)//STRIDE
            pts.append(data.reshape(-1,1,2))
        color=(250,220,40) if not render_unapproved else (30,145,235)
        cv2.drawContours(result,pts,-1,color,1,cv2.LINE_8)
        if make_labels:
            box=np.concatenate([p.reshape(-1,2) for p in pts],axis=0)
            if len(box):
                x=int(box[:,0].min());y=int(box[:,1].min())
                # Main view numeric size labels may overlap; detailed CSV/6panel
                # contain complete values and mandatory uncertainty note.
                text=f"B{int(rec.band_id)}-{int(rec.candidate_label)} A~{int(rec.proposed_K5RAW_outer_area_um2)}um2"
                cv2.putText(result,text,(max(5,x),max(11,y-3)),
                        cv2.FONT_HERSHEY_SIMPLEX,.36,color,1,cv2.LINE_8)
        log.append({"frame":int(rec.frame),"band_id":int(rec.band_id),
                    "candidate_label":int(rec.candidate_label),
                    "original_B_area_px2":int(rec.original_B_source_area_px2),
                    "new_provisional_K5RAW_area_px2":int(rec.proposed_K5RAW_outer_area_px2),
                    "old_source_grade":rec.original_B_size_grade,
                    "new_trial_grade":rec.proposal_size_grade_REVIEW_ONLY,
                    "review_required":True})
    return result,log

def banner(base,title,details,count):
    top=np.full((99,base.shape[1],3),26,np.uint8)
    cv2.putText(top,title,(12,28),cv2.FONT_HERSHEY_SIMPLEX,.57,(238,238,238),1)
    cv2.putText(top,details[:120],(12,57),cv2.FONT_HERSHEY_SIMPLEX,.40,(220,220,220),1)
    cv2.putText(top,count[:130],(12,84),cv2.FONT_HERSHEY_SIMPLEX,.41,(215,215,215),1)
    return np.vstack([top,base])

def run():
    report={"stage":"CASE03K8C_J5_MEDLARGE_FIRST_WITH_K5RAW_OUTER_TRIAL",
            "original_J5_detection_unchanged":True,
            "supplemental_outer_not_confirmed_physical_size":True,
            "full_overlay_band_count_from_K8A_not_hardcoded":True,
            "frames":{}}
    for frame in (1,2):
        out=BASE/f"frame26_{frame}"
        if (out/"PRIORITY_VIEW_SUMMARY.json").exists():
            raise FileExistsError("Refuse overwrite priority views")
        objects=pd.read_csv(K8B/f"frame26_{frame}/original_J5_object_center_workband_classification.csv",
                            encoding="utf-8-sig")
        trials=pd.read_csv(out/"all_selected_darkspots_K5RAW_outer_comparison.csv")
        base=display_bg(frame)
        main,old_large=frozen_j5_main(base,objects)
        integrated,selected=overlay_proposed(main,trials,
                                             render_unapproved=False,make_labels=True)
        newonly,selected_new=overlay_proposed(base,trials,
                                              render_unapproved=False,make_labels=True)
        small,nsmall=smallmap(base,objects,trials)
        review_candidates=trials[~trials.status.str.startswith(
                                "PROVISIONAL_RAW")].copy()
        other,review_list=overlay_proposed(base,review_candidates,
                             render_unapproved=True,make_labels=False)
        images=[
         ("01_PRIORITY_original_J5_MED_LARGE.png",main,
          "Original J5 MEDIUM/LARGE within WORK core: 1px frames.",
          f"Old medium+large {len(old_large)} | small J5 objects NOT on main"),
         ("02_PRIORITY_J5_MED_LARGE_plus_K5RAW_review_OUTER.png",integrated,
          "Old J5 MED/LARGE + CYAN provisional RAW contours where safety passed.",
          f"J5 med/large {len(old_large)} + K5RAW possible medium/large {len(selected)}; sizes NOT accepted"),
         ("03_K5RAW_expanded_contours_only_MED_LARGE.png",newonly,
          "K8C new spot outer outlines PROVISIONAL; only MED/LARGE proposals.",
          f"Safely enlarged medium/large proposals {len(selected_new)}"),
         ("04_REVIEW_safety_rejected_raw_outer_candidates.png",other,
          "ORANGE RAW proposal fails guard or lacks stable link: NOT accepted.",
          f"Needs independent attention {len(review_list)}; no official mask changes"),
         ("05_SMALL_original_J5_and_K8C_reference.png",small,
          "Original J5 SMALL and original tiny K8C new detections shown separately.",
          f"Old J5 small WORK centers {nsmall}; original candidate masks still available")
        ]
        for name,im,info,nums in images:
            save_png(out/name,banner(im,f"F26({frame}) {name[:-4]}",info,nums))
        stats={
          "frame":frame,
          "work_core_frozen_J5_mediumlarge":len(old_large),
          "work_core_frozen_J5_small":nsmall,
          "K8C_candidate_source_hypotheses_considered":len(trials),
          "safe_contours_mediumlarge_promoted_for_review":len(selected),
          "source_mask_reviewed_small_candidates_separate":True,
          "source_A_fixed_and_J5_unmodified":True,
          "provisional_pixels_not_approved_measured_area":True,
          "images":[row[0] for row in images]
        }
        (out/"PRIORITY_VIEW_SUMMARY.json").write_text(
             json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
        for name,_,_,_ in images:
            im=cv2.imdecode(np.frombuffer((out/name).read_bytes(),np.uint8),
                            cv2.IMREAD_COLOR)
            assert im is not None and im.shape[1]==base.shape[1]
        print("K8C_PRIORITY_FROZEN_PLUS_REVIEW_READY",
              json.dumps(stats,ensure_ascii=False),flush=True)
        report["frames"][str(frame)]=stats
    (BASE/"priority_view_summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":run()
