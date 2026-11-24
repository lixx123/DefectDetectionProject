"""Case03-K5 run: two targeted corrections with frozen original J5.

Inputs K4S' 22 fixed BH61-eligible original J5 objects plus developer
reference 074. User labels never drive thresholds/group decisions.
Documents 024, 057, 086 and 079 with complete RAW/hypothesis/review images.
Produces separate proposed groups, NEVER overwrites J4/J5 or IDs.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
from functools import lru_cache
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,component_seeded_H,decision,aspect_and_bbox
)
from src.detection.case03k5_adaptive_grouping import (
    AdaptiveConfig,choose_adaptive_envelope,audit_object_membership,
    render_status
)
from src.detection.blackhat import black_hat_uint16
from scripts.run_case03g_joint_noise_refinement import save_png
from scripts.run_case03k4_expanded_pilot import retrieve_source_and_others

BASE=cfg.OUTPUT_ROOT/"case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1"
K0=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
OUT=cfg.OUTPUT_ROOT/"case03k_adaptive_group_trial/run_20261012_K5_adaptive_and_J5_group_review_v2"
PILOT=PilotConfig()
SETTINGS=AdaptiveConfig()

@lru_cache(maxsize=256)
def source_labels(name):
    with np.load(J4/"tile_masks"/(name+".npz"),allow_pickle=False) as a:
        return a["grouped_source_only_i32"].copy(),tuple(int(e) for e in a["core_xyxy"])

def member_id_grid(region:dict,local_map:dict)->np.ndarray:
    """Map J4 tile-local object IDs to frozen GLOBAL J5 IDs at source pixels.

    Never uses an image center proximity shortcut. IDs are exact original
    source labels; across tile membership can be traced without merge.
    """
    x0,y0,x1,y1=[int(region[k]) for k in ("x0","y0","x1","y1")]
    ids=np.full((y1-y0,x1-x0),"",dtype="<U32")
    for iy in range(y0//256,(y1-1)//256+1):
        for ix in range(x0//256,(x1-1)//256+1):
            tid=f"T{iy:03d}_{ix:03d}"
            label,rect=source_labels(tid)
            ax=max(x0,rect[0]);ay=max(y0,rect[1])
            bx=min(x1,rect[2]);by=min(y1,rect[3])
            if ax>=bx or ay>=by:continue
            segment=label[ay-rect[1]:by-rect[1],
                          ax-rect[0]:bx-rect[0]]
            sub=ids[ay-y0:by-y0,ax-x0:bx-x0]
            for lid in np.unique(segment):
                if lid<=0:continue
                global_id=local_map.get((tid,int(lid)))
                if not global_id:raise RuntimeError(f"unmapped J4 {tid} {lid}")
                sub[segment==lid]=global_id
    return ids


def roi_image(raw128:np.ndarray,src:np.ndarray,h61:np.ndarray,
              old:np.ndarray,adaptive:np.ndarray,shown:np.ndarray,
              overlap:np.ndarray,status:str,metric:dict)->np.ndarray:
    dark=raw128.astype(float)
    lo,hi=np.percentile(dark,[1,99.5])
    g=np.uint8(np.clip((dark-lo)/max(1.,hi-lo)*255,0,255))
    images=[]
    cols=[
        ("RAW",None,"Input 128x128 RAW"),
        ("J5 / RED CORE",src,f"{int(src.sum())} detected px2"),
        ("BH +61",h61,f"{int(h61.sum())} proposed px2"),
        ("RAW k=3",old,f"{int(old.sum())} trial px2"),
        ("ADAPTIVE RAW",adaptive,
         f"k={metric['floor_selected_sigma']:g}, {int(adaptive.sum())}px2"),
        ("DISPLAY / REVIEW",shown,status[:32])
    ]
    for i,(title,mask,desc) in enumerate(cols):
        im=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
        if mask is not None and np.any(mask):
            overlay=im.copy()
            overlay[mask]=(30,220,220) if i==4 else (32,196,235)
            im=cv2.addWeighted(im,.75,overlay,.25,0)
            cnt,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            # cyan = provisional single; amber = review only/group/confl
            color=(30,220,230) if (i==5 and status=="PROVISIONAL_OUTER_SINGLE") else (10,185,255)
            cv2.drawContours(im,cnt,-1,color,1)
        # competitor pixels inside outer = orange; outside = purple in the last panel.
        if i==5:
            im[overlap & adaptive]=(20,130,255)
        cnt,_=cv2.findContours(np.uint8(src),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im,cnt,-1,(0,0,245),1)
        im=cv2.resize(im,(280,280),interpolation=cv2.INTER_NEAREST)
        header=np.full((63,280,3),26,np.uint8)
        cv2.putText(header,title,(7,23),cv2.FONT_HERSHEY_SIMPLEX,.49,(238,238,238),1,cv2.LINE_AA)
        cv2.putText(header,desc,(7,45),cv2.FONT_HERSHEY_SIMPLEX,.37,(212,212,212),1,cv2.LINE_AA)
        images.append(np.vstack((header,im)))
    return np.hstack(images)


def run():
    if OUT.exists():raise FileExistsError("refuse overwrite historical run "+str(OUT))
    (OUT/"review_figures").mkdir(parents=True)
    (OUT/"reversible_masks").mkdir()
    eligible=pd.read_csv(BASE/"240_scale_trial_audit.csv",encoding="utf-8-sig",
                         keep_default_na=False)
    eligible=eligible.loc[eligible.shape_size_precheck_pass.astype(str).str.lower()=="true"].copy()
    frozen_selection=pd.read_csv(BASE/"fixed_unlabeled_selection.csv",encoding="utf-8-sig")
    eligible=eligible.merge(frozen_selection[["global_defect_id","center_x_global","center_y_global"]],on="global_defect_id",validate="one_to_one")
    assert len(eligible)==22
    # For A/B diagnosis, keep prior dev reference 074 in the same routine.
    sample=pd.read_csv(K0/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv",
                       encoding="utf-8-sig",keep_default_na=False)
    seventyfour=sample[sample.sample_id=="K0_SMALL_074"].iloc[0].to_dict()
    seventyfour["sample_id"]="K0_SMALL_074"
    seventyfour["global_defect_id"]=str(seventyfour["global_defect_id"])
    seventyfour["center_x_global"]=float(seventyfour["target_x_global"])
    seventyfour["center_y_global"]=float(seventyfour["target_y_global"])
    seventyfour["source_area_px2"]=int(float(seventyfour["source_area_px2"]))
    samples=eligible.to_dict("records")+[seventyfour]
    membership=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
    objects=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    allarea=dict(zip(objects.global_defect_id,
                     objects.source_area_px2.astype(int)))
    local_id_map=dict(zip(
        zip(membership.source_tile_id,membership.source_local_object_index.astype(int)),
        membership.global_defect_id))
    bygid=membership.groupby("global_defect_id")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",dtype=">u2",mode="r",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    frozen=np.load(cfg.OUTPUT_ROOT/
      "case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
      mmap_mode="r")
    audits=[];group_audits=[]
    review_pictures=[]
    for case in samples:
        sample_id=case["sample_id"]
        x0,y0,x1,y1=[int(case[k]) for k in ("x0","y0","x1","y1")]
        assert x1-x0==y1-y0==128
        source,comp=retrieve_source_and_others(case,bygid)
        ids=member_id_grid(case,local_id_map)
        assert np.array_equal(ids==case["global_defect_id"],source)
        assert np.array_equal((ids!="") & ~source,comp)
        wx0=max(0,x0-72);wy0=max(0,y0-72)
        wx1=min(cfg.RAW_WIDTH,x1+72);wy1=min(cfg.RAW_HEIGHT,y1+72)
        rawwin=np.asarray(raw[wy0:wy1,wx0:wx1],np.uint16)
        old=np.asarray(frozen[wy0:wy1,wx0:wx1],np.uint16)
        extra=black_hat_uint16(rawwin,61,"ellipse")
        seed=np.zeros(rawwin.shape,bool)
        seed[y0-wy0:y1-wy0,x0-wx0:x1-wx0]=source
        reg=(slice(y0-wy0,y1-wy0),slice(x0-wx0,x1-wx0))
        h31=component_seeded_H(old,seed,PILOT)[reg]
        h61=component_seeded_H(np.maximum(old,extra),seed,PILOT)[reg]
        source_area=int(source.sum())
        aspect,_=aspect_and_bbox(h61)
        if (h61.sum()<PILOT.min_h61_area_px or
            h61.sum()/max(source_area,1)<PILOT.min_h61_growth_ratio or
            aspect>PILOT.max_h61_axis_aspect or
            h61.sum()>PILOT.h61_max_fraction_of_roi*source.size):
            raise AssertionError(f"K5 expected frozen scale precheck for {sample_id}")
        raw128=np.asarray(raw[y0:y1,x0:x1],np.uint16)
        center=(float(case["center_x_global"])-x0,
                float(case["center_y_global"])-y0)
        adaptive,audit,decisioninfo=choose_adaptive_envelope(
            raw128,source,center,int(h61.sum()),PILOT,SETTINGS)
        from src.detection.case03k3_spot_contour_pilot import raw_outer_envelope
        initial,initial_meta=raw_outer_envelope(raw128,source,center,PILOT)
        assert int(initial.sum())==decisioninfo["floor_3_area_px2"]
        proposed_group=audit_object_membership(
            adaptive,str(case["global_defect_id"]),ids,allarea,audit,SETTINGS)
        # All OTHER K3 physical shape/edge gates must still pass.
        # Let the new group logic, not old zero-competing guard, handle overlaps.
        verdict,reasons=decision(source,h31,h61,adaptive,
                np.zeros_like(comp),audit,PILOT)
        # Preserve cross-label risk separately, never treat as accepted group
        # without a reasoned object-coverage audit.
        if proposed_group["group_status"]=="REJECTED_SEED_ABSENT":
            reasons.append("GROUP_PRIMARY_SEED_MISSING")
        if (comp & adaptive).any() and proposed_group[
            "group_status"]=="NO_SIBLING_CONFLICT":
            reasons.append("UNMAPPED_FOREIGN_SOURCE_CONFLICT")
        status,display=render_status(source,adaptive,audit,proposed_group,reasons)
        assert np.all(display[source])
        info={
           "sample_id":sample_id,
           "frozen_J5_ID":str(case["global_defect_id"]),
           "original_J5_source_pixels":source_area,
           "h31_source_anchor_pixels":int(h31.sum()),
           "h61_source_anchor_pixels":int(h61.sum()),
           **decisioninfo,
           "adaptive_outer_area_px2":int(adaptive.sum()),
           "adaptive_raw_seed_coverage_fraction":audit[
               "raw_proposal_seed_overlap_fraction"],
           "old_noncompetition_guards_ok":not bool(reasons),
           "other_guard_vetoes":";".join(reasons),
           "raw_conflicting_J5_pixels":int(np.count_nonzero(adaptive&comp)),
           "competing_J5_IDs":";".join(proposed_group["competing_J5_ids"]),
           "proposed_group_member_IDs":";".join(proposed_group["proposed_review_group_ids"]),
           "group_count":len(proposed_group["proposed_review_group_ids"]),
           "group_status":proposed_group["group_status"],
           "group_vetoes":";".join(proposed_group["group_reject_reasons"]),
           "display_status":status,
           "raw_outer_is_not_real_physical_measurement":True,
           "official_J5_unchanged":True,
           "human_label_used_by_algorithm":False
        }
        audits.append(info)
        group_audits.append({
            "sample_id":sample_id,"frozen_J5_ID":str(case["global_defect_id"]),
            **proposed_group
        })
        np.savez_compressed(OUT/"reversible_masks"/(sample_id+".npz"),
            global_roi_xyxy=np.array([x0,y0,x1,y1],dtype=np.int32),
            original_J5_source=source.astype(np.uint8),
            original_competing_J5=comp.astype(np.uint8),
            original_H31=h31.astype(np.uint8),
            expanded_blackhat_H61=h61.astype(np.uint8),
            raw_initial_k3=initial.astype(np.uint8),
            raw_adaptive=adaptive.astype(np.uint8),
            displayed_review_mask=display.astype(np.uint8))
        viz=roi_image(raw128,source,h61,initial,adaptive,display,comp,status,decisioninfo)
        save_png(OUT/"review_figures"/(sample_id+"_6panel.png"),viz)
        if sample_id in ("K4S_024","K4S_057","K4S_086","K4S_079","K0_SMALL_074",
                         "K4S_055"):
            review_pictures.append((sample_id,cv2.resize(viz,(1260,257),interpolation=cv2.INTER_AREA)))
        print("K5_ITEM",sample_id,status,
              "old",decisioninfo["floor_3_area_px2"],
              "ad",int(adaptive.sum()),"group",proposed_group["competing_J5_ids"],flush=True)
    pd.DataFrame(audits).to_csv(OUT/"k5_23_case_adaptive_and_group_audit.csv",
                               encoding="utf-8-sig",index=False)
    (OUT/"provisional_group_membership_review.json").write_text(
        json.dumps(group_audits,ensure_ascii=False,indent=2),encoding="utf-8")
    if review_pictures:
        for key,pic in review_pictures:
            p=OUT/(key+"_review_focus.png")
            save_png(p,pic)
        tiles=[pic for key,pic in review_pictures]
        head=np.full((58,tiles[0].shape[1],3),28,np.uint8)
        cv2.putText(head,"K5 six-stage diagnostic: RED original / CYAN trial / AMBER pending review",
            (10,25),cv2.FONT_HERSHEY_SIMPLEX,.47,(225,225,225),1)
        save_png(OUT/"K5_focus_024_057_086_079_074.png",
                 np.vstack([head]+tiles))
    stat=pd.DataFrame(audits)
    summ={
       "stage":"CASE03K5_ADAPTIVE_RAW_PLUS_GROUP_REVIEW_ONLY",
       "existing_source_J5_candidates":len(audits),
       "included_K0_development_reference":"K0_SMALL_074",
       "source_image":"26 (1).raw",
       "adaptive_relaxation_candidates":int((stat.floor_selected_sigma==1.5).sum()),
       "provisional_group_reviews":int((stat.group_status=="COHERENT_GROUP_REVIEW").sum()),
       "unresolved_group_conflicts":int((stat.group_status=="CONFLICT_UNRESOLVED_REVIEW").sum()),
       "original_J4_J5_masks_and_global_IDs_unchanged":True,
       "raw_area_trial_not_physical_truth":True,
       "human_confirmation_of_new_groups":False,
       "not_an_independent_frame_validation":True,
       "adaptive_config":asdict(SETTINGS),
       "frozen_K3_config":asdict(PILOT)
    }
    (OUT/"summary.json").write_text(json.dumps(summ,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("K5_SUMMARY",json.dumps(summ,ensure_ascii=False),flush=True)
    return summ
if __name__=="__main__":run()
