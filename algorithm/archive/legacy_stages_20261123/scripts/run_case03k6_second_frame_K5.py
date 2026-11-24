"""Case03-K6 frozen K5 independent FRAME2 application (NO training or labels).

Samples predeclared stratified J5 targets from 26 (2).raw. Recomputes
BH61 anchor / local adaptive MAD / tentative J5 sibling membership using
the *second frame's own J4/J5 sources*. Does NOT align frame1 coordinates,
does NOT overwrite any source masks, global IDs or production grades, and
does NOT claim accuracy without human-labeled second-frame ground truth.
"""
from __future__ import annotations
from dataclasses import asdict
from collections import Counter,defaultdict
from functools import lru_cache
from pathlib import Path
import json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k3_spot_contour_pilot import (
 PilotConfig,component_seeded_H,decision,aspect_and_bbox,raw_outer_envelope)
from src.detection.case03k5_adaptive_grouping import (
 AdaptiveConfig,choose_adaptive_envelope,audit_object_membership,render_status)
from scripts.run_case03g_joint_noise_refinement import save_png,gray
from scripts.run_case03k5_adaptive_group_pilot import roi_image

J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_2_J4_independent_v1"
J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_2_J5_independent_v1"
RESP=cfg.OUTPUT_ROOT/"case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy"
RAW=cfg.DATA_ROOT/"26 (2).raw"
OUT=cfg.OUTPUT_ROOT/"case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1"
PILOT=PilotConfig()
ADAPT=AdaptiveConfig()
SEED=20261012+2602
W,H=cfg.RAW_WIDTH,cfg.RAW_HEIGHT

def out_of_bounds(area):
    return (area["center_x_global"]<165 or area["center_x_global"]>W-165 or
            area["center_y_global"]<165 or area["center_y_global"]>H-165)

def choose_pool(allrows,grade:str,size:str,count:int,rng):
    df=allrows[allrows.grade==grade]
    df=df.loc[
      (df.source_bbox_width_px<=48)&(df.source_bbox_height_px<=48)&
      (df.center_x_global.between(165,W-165))&
      (df.center_y_global.between(165,H-165))].copy()
    if grade=="SMALL":
        lo,hi={"A1":(1,1),"B2to3":(2,3),
               "C4to7":(4,7),"D8plus":(8,39)}[size]
        df=df[df.source_area_px2.between(lo,hi)]
    else:
        df=df[df.source_area_px2.between(20,900)]
    if len(df)<count:raise RuntimeError(f"not enough {grade} {size}: {len(df)}")
    df["sector"]=np.minimum(3,(df.center_y_global*4/H).astype(int))*6+np.minimum(
        5,(df.center_x_global*6/W).astype(int))
    by={}
    for k,chunk in df.groupby("sector"):
        idx=chunk.index.to_numpy(copy=True)
        rng.shuffle(idx);by[int(k)]=list(idx)
    used=defaultdict(int)
    chosen=[]
    for _ in range(count):
        keys=[k for k in by if by[k]]
        m=min(used[k] for k in keys)
        options=[k for k in keys if used[k]==m]
        picked=options[int(rng.integers(len(options)))]
        chosen.append(by[picked].pop());used[picked]+=1
    return df.loc[chosen]


def negative_rois(allrows,rng,n=24):
    # Any J5 source/display bounding box intersecting 128ROI disqualifies
    # this as a "no prediction" control. It is NOT human-confirmed negative.
    step=16
    grid=np.zeros((int(np.ceil(H/step)),int(np.ceil(W/step))),bool)
    for v in allrows.itertuples():
        ax=int(v.display_bbox_x_global)//step
        ay=int(v.display_bbox_y_global)//step
        bx=int(v.display_bbox_xmax_inclusive)//step+1
        by=int(v.display_bbox_ymax_inclusive)//step+1
        grid[ay:by,ax:bx]=True
    chosen=[]
    for sector_y in range(4):
        for sector_x in range(6):
            xl=int(sector_x*W/6);xr=int((sector_x+1)*W/6)-128
            yl=int(sector_y*H/4);yr=int((sector_y+1)*H/4)-128
            found=False
            for _ in range(1000):
                x=int(rng.integers(xl,xr+1));y=int(rng.integers(yl,yr+1))
                if grid[max(0,y//step-1):min(grid.shape[0],(y+127)//step+2),
                        max(0,x//step-1):min(grid.shape[1],(x+127)//step+2)].any():
                    continue
                chosen.append({
                 "sample_id":f"K6_BG_{len(chosen)+1:03d}",
                 "sample_group":"NO_J5_PREDICTION_ROI",
                 "source_global_defect_id":"",
                 "source_grade":"",
                 "source_area_px2":0,
                 "center_x_global":None,"center_y_global":None,
                 "x0":x,"y0":y,"x1":x+128,"y1":y+128,
                 "human_true_defect_review":"",
                 "human_missed_defects_in_ROI":"",
                 "manual_outer_quality":"",
                 "human_remarks":""})
                found=True;break
            if not found:raise RuntimeError("no empty J5 box-free control for sector")
    assert len(chosen)==n
    return chosen

def make_fixed_selection(allrows):
    rng=np.random.default_rng(SEED)
    groups=[
       ("SMALL","A1",24),("SMALL","B2to3",24),
       ("SMALL","C4to7",72),("SMALL","D8plus",120),
       ("MEDIUM","M",12),("LARGE","L",12)]
    selection=[]
    for grade,size,count in groups:
        df=choose_pool(allrows,grade,size,count,rng)
        for row in df.to_dict("records"):
            xc=int(round(float(row["center_x_global"])))
            yc=int(round(float(row["center_y_global"])))
            x0=xc-64;y0=yc-64
            if (x0>row["source_bbox_x_global"] or
                x0+128<row["source_bbox_x_global"]+row["source_bbox_width_px"] or
                y0>row["source_bbox_y_global"] or
                y0+128<row["source_bbox_y_global"]+row["source_bbox_height_px"]):
                raise ValueError("J5 candidate not completely inside 128 ROI")
            selection.append({
               "sample_id":f"K6_{len(selection)+1:03d}",
               "sample_group":grade+"_"+size,
               "source_global_defect_id":row["global_defect_id"],
               "source_grade":grade,
               "source_area_px2":int(row["source_area_px2"]),
               "center_x_global":float(row["center_x_global"]),
               "center_y_global":float(row["center_y_global"]),
               "x0":x0,"y0":y0,"x1":x0+128,"y1":y0+128,
               "human_true_defect_review":"",
               "human_missed_defects_in_ROI":"",
               "manual_outer_quality":"",
               "human_remarks":""})
    selection+=negative_rois(allrows,rng)
    assert len(selection)==288
    assert len({v["source_global_defect_id"] for v in selection[:-24]})==264
    return pd.DataFrame(selection)

@lru_cache(maxsize=128)
def tile_labels(tid):
    with np.load(J4/"tile_masks"/(tid+".npz"),allow_pickle=False) as z:
        return z["grouped_source_only_i32"].copy(),tuple(int(k) for k in z["core_xyxy"])

def original_id_map(info,local_to_global):
    x0,y0,x1,y1=[int(info[k]) for k in ("x0","y0","x1","y1")]
    idmap=np.full((128,128),"",dtype="<U32")
    for iy in range(y0//256,(y1-1)//256+1):
        for ix in range(x0//256,(x1-1)//256+1):
            tid=f"T{iy:03d}_{ix:03d}"
            labels,rect=tile_labels(tid)
            ax=max(x0,rect[0]);ay=max(y0,rect[1])
            bx=min(x1,rect[2]);by=min(y1,rect[3])
            if ax>=bx or ay>=by:continue
            portion=labels[ay-rect[1]:by-rect[1],
                           ax-rect[0]:bx-rect[0]]
            region=idmap[ay-y0:by-y0,ax-x0:bx-x0]
            for lid in np.unique(portion):
                if lid<=0:continue
                global_id=local_to_global.get((tid,int(lid)))
                if not global_id:raise AssertionError((tid,lid))
                region[portion==lid]=global_id
    source=idmap==info["source_global_defect_id"]
    if info["source_global_defect_id"]:
        if int(source.sum())!=int(info["source_area_px2"]):
            raise AssertionError("source mask/J5 summary mismatch "+info["sample_id"])
    else:
        assert not np.any(idmap!=""),"Empty J5 roi contains original source pixels"
    return idmap,source

def colored_view(raw128,source,outside,review_status):
    a,b=np.percentile(raw128,[1,99.5])
    g=np.uint8(np.clip((raw128.astype(float)-a)/max(1.,b-a)*255,0,255))
    im=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    if outside.any():
        shade=im.copy();shade[outside]=(30,185,230)
        im=cv2.addWeighted(im,.70,shade,.30,0)
        contours,_=cv2.findContours(np.uint8(outside),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im,contours,-1,(15,210,235),1)
    cnt,_=cv2.findContours(np.uint8(source),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(im,cnt,-1,(0,0,240),1)
    band=np.full((55,384,3),26,np.uint8)
    cv2.putText(band,review_status[:42],(7,21),cv2.FONT_HERSHEY_SIMPLEX,.41,(243,243,243),1)
    cv2.putText(band,f"J5 source {int(source.sum())} px; proposed {int(outside.sum())} px",
                (7,43),cv2.FONT_HERSHEY_SIMPLEX,.37,(220,220,220),1)
    return np.vstack((band,cv2.resize(im,(384,384),interpolation=cv2.INTER_NEAREST)))

def run():
    if OUT.exists():raise FileExistsError(OUT)
    if not (J5/"summary.json").is_file():raise FileNotFoundError("independent second frame J5 not finished")
    state=json.loads((J5/"summary.json").read_text(encoding="utf-8"))
    assert state["stage"]=="J5_COMPLETE"
    assert RAW.stat().st_size==W*H*2
    assert RESP.is_file()
    (OUT/"review_images").mkdir(parents=True)
    source=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    member=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
    local_to_global=dict(zip(zip(member.source_tile_id,member.source_local_object_index.astype(int)),member.global_defect_id))
    allarea=dict(zip(source.global_defect_id,source.source_area_px2.astype(int)))
    selected=make_fixed_selection(source)
    selected.to_csv(OUT/"fixed_selection_and_blank_manual_review.csv",index=False,encoding="utf-8-sig")
    rawmem=np.memmap(RAW,mode="r",dtype=">u2",shape=(H,W))
    fused=np.load(RESP,allow_pickle=False,mmap_mode="r")
    tracks=[];suggestions=[];stored=[]
    for case in selected.to_dict("records"):
        sid=case["sample_id"];x0,y0,x1,y1=[int(case[k]) for k in ("x0","y0","x1","y1")]
        idmap,original=original_id_map(case,local_to_global)
        crop=np.asarray(rawmem[y0:y1,x0:x1],np.uint16)
        status="NO_J5_PREDICTION_ROI";review=original.copy()
        h31=np.zeros_like(original);h61=h31.copy()
        old=np.zeros_like(original);outer=old.copy()
        meta={"floor_selected_sigma":3}
        group=None
        if case["source_global_defect_id"]:
            wx0=x0-72;wy0=y0-72;wx1=x1+72;wy1=y1+72
            work=np.asarray(rawmem[wy0:wy1,wx0:wx1],np.uint16)
            originalBH=np.asarray(fused[wy0:wy1,wx0:wx1],np.uint16)
            scaledBH=np.maximum(originalBH,black_hat_uint16(work,61,"ellipse"))
            seed=np.zeros(work.shape,bool);seed[72:200,72:200]=original
            h31=component_seeded_H(originalBH,seed,PILOT)[72:200,72:200]
            h61=component_seeded_H(scaledBH,seed,PILOT)[72:200,72:200]
            shape,_=aspect_and_bbox(h61)
            passed=(h61.sum()>=PILOT.min_h61_area_px and
                h61.sum()>=PILOT.min_h61_growth_ratio*original.sum() and
                np.isfinite(shape) and shape<=PILOT.max_h61_axis_aspect and
                h61.sum()<=PILOT.h61_max_fraction_of_roi*original.size)
            status="NO_SPOT_SCALE_PRECHECK"
            if passed:
                center=(float(case["center_x_global"])-x0,float(case["center_y_global"])-y0)
                outer,audit,meta=choose_adaptive_envelope(
                    crop,original,center,int(h61.sum()),PILOT,ADAPT)
                old,oldmeta=raw_outer_envelope(crop,original,center,PILOT)
                assert int(old.sum())==meta["floor_3_area_px2"]
                group=audit_object_membership(
                    outer,case["source_global_defect_id"],idmap,allarea,audit,ADAPT)
                stage,reasons=decision(original,h31,h61,outer,np.zeros_like(original),audit,PILOT)
                if group["group_status"]=="REJECTED_SEED_ABSENT":
                    reasons.append("GROUP_PRIMARY_SEED_MISSING")
                status,review=render_status(original,outer,audit,group,reasons)
                if group["group_status"]=="COHERENT_GROUP_REVIEW":
                    suggestions.append({
                       "sample_id":sid,
                       "primary_J5_ID":case["source_global_defect_id"],
                       "proposed_member_J5_IDs":group["proposed_review_group_ids"],
                       "candidate_outer_area_px2":int(outer.sum()),
                       "human_same_physical_defect":"",
                       "new_official_ID_created":False})
                stored.append((sid,case,original,h31,h61,old,outer,review,idmap,status,meta))
        tracks.append({
            "sample_id":sid,
            "sample_group":case["sample_group"],
            "frozen_second_frame_J5_ID":case["source_global_defect_id"],
            "original_source_area_px2":int(original.sum()),
            "H31_area_px2":int(h31.sum()),"H61_area_px2":int(h61.sum()),
            "raw_k3_area_px2":int(old.sum()),
            "K5_adaptive_area_px2":int(outer.sum()),
            "noise_multiplier_chosen":meta.get("floor_selected_sigma",3),
            "display_review_area_px2":int(review.sum()),
            "display_status":status,
            "group_review_candidate_IDs":";".join(group["proposed_review_group_ids"]) if group else "",
            "group_status":group["group_status"] if group else "NOT_RUN",
            "other_IDs_touched":";".join(group["competing_J5_ids"]) if group else "",
            "no_official_ID_or_grade_changed":True,
            "unlabeled_second_frame":True
        })
        if len(tracks)%40==0:
            print("K6_FROZEN_K5_PROGRESS",len(tracks),288,"proposed",(sum(t["K5_adaptive_area_px2"]>0 for t in tracks)),flush=True)
    audit=pd.DataFrame(tracks)
    audit.to_csv(OUT/"all_288_frozen_K5_audit.csv",encoding="utf-8-sig",index=False)
    (OUT/"group_review_proposals.json").write_text(
        json.dumps(suggestions,ensure_ascii=False,indent=2),encoding="utf-8")
    ranked=sorted(stored,key=lambda r:(
       0 if r[9]=="GROUP_OUTER_PENDING_HUMAN_REVIEW" else 1,
       0 if r[9]=="PROVISIONAL_OUTER_SINGLE" else 1,
       -int(r[6].sum()) ),reverse=False)
    cards=[]
    # 30 K5 stage-visible images plus 12 no prediction controls for user.
    chosen=ranked[:30]
    for sid,case,original,h31,h61,old,outer,review,idmap,status,meta in chosen:
        roi=np.asarray(rawmem[int(case["y0"]):int(case["y1"]),
                         int(case["x0"]):int(case["x1"])],np.uint16)
        image=roi_image(roi,original,h61,old,outer,review,
                        (idmap!="") & ~(idmap==case["source_global_defect_id"]),
                        status,meta)
        save_png(OUT/"review_images"/(sid+"_6panel.png"),image)
        cards.append(cv2.resize(image,(1260,257),interpolation=cv2.INTER_AREA))
    if cards:
        # One slide per 5 candidates, each slide includes pixel-bound annotations.
        for i in range(0,len(cards),5):
            c=cards[i:i+5]
            save_png(OUT/(f"selected_6panel_{i+1:02d}_to_{i+len(c):02d}.png"),
                     np.vstack(c))
    for case in selected.tail(12).to_dict("records"):
        crop=np.asarray(rawmem[case["y0"]:case["y1"],case["x0"]:case["x1"]],np.uint16)
        save_png(OUT/"review_images"/(case["sample_id"]+"_no_prediction.png"),
                 colored_view(crop,np.zeros((128,128),bool),
                             np.zeros((128,128),bool),"NO J5 PREDICTION / CHECK MISSES"))
    summary={
      "stage":"K6_SECOND_FRAME_FROZEN_K5_COMPLETE",
      "frame":"26 (2).raw",
      "frozen_J5_source":str(J5),
      "input_global_defects":len(source),
      "input_J5_grade_counts":{k:int(v) for k,v in source.grade.value_counts().to_dict().items()},
      "sampled_J5_objects":264,
      "sampled_J5_empty_ROIs":24,
      "frozen_K5_new_spot_shape_prechecks":int((audit.H61_area_px2>=PILOT.min_h61_area_px).sum()),
      "K5_RAW_envelope_candidates":int((audit.K5_adaptive_area_px2>0).sum()),
      "K5_confident_single_contour_review":int((audit.display_status=="PROVISIONAL_OUTER_SINGLE").sum()),
      "K5_coherent_group_review":int((audit.display_status=="GROUP_OUTER_PENDING_HUMAN_REVIEW").sum()),
      "K5_unresolved_group_review":int((audit.display_status=="CONFLICT_OUTER_PENDING_HUMAN_REVIEW").sum()),
      "K5_review_only_rejected_halo":int((audit.display_status=="REJECTED_HALO_DISPLAY_REVIEW_ONLY").sum()),
      "K5_noise_floor_1p5_selected":int((audit.noise_multiplier_chosen==1.5).sum()),
      "frozen_J5_source_pixels_preserved_in_display":True,
      "K5_frozen_parameters":asdict(PILOT),
      "K5_adaptive_parameters":asdict(ADAPT),
      "selection_seed":SEED,
      "labels_from_first_frame_copied":False,
      "source_J5_updated":False,
      "artificial_new_defect_proposals":False,
      "frame2_reference_truth_unavailable":True,
      "frame2_precision_recall_not_measured":True
    }
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K6_SECOND_FRAME_K5_RESULT",json.dumps(summary,ensure_ascii=False),flush=True)
    return summary

if __name__=="__main__":run()
