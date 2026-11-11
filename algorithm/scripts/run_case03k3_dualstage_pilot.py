"""Case03-K3: prototype BH61-assisted, RAW-based spot contour review on 24
manually reviewed candidates + 6 independent prediction-empty ROI controls.

Frozen J4/J5 untouched; ALL results PROVISIONAL. Labels are included only
for retrospective performance auditing, never as detection inputs.
"""
from __future__ import annotations
import json,sys
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,component_seeded_H,raw_outer_envelope,decision,
    aspect_and_bbox
)
from scripts.run_case03g_joint_noise_refinement import save_png

B=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
OUT=B/"K3_dualstage_contour_pilot_v1"
if OUT.exists():raise FileExistsError(OUT)
(OUT/"figures").mkdir(parents=True)
(OUT/"masks").mkdir(parents=True)
review=pd.read_csv(B/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv",
                   encoding="utf-8-sig",keep_default_na=False)
members=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
parts=members.groupby("global_defect_id")
raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
              shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
fused=np.load(cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
              mmap_mode="r")
c=PilotConfig()
c.validate()
cache={}
def tile_data(name):
    if name not in cache:
        with np.load(J4/"tile_masks"/(name+".npz")) as f:
            cache[name]=(f["grouped_source_only_i32"].copy(),
                         tuple(int(v) for v in f["core_xyxy"]))
    return cache[name]
def fetch_masks(s):
    x0,y0,x1,y1=[int(s[k]) for k in ("x0","y0","x1","y1")]
    original=np.zeros((128,128),bool)
    competitors=np.zeros_like(original)
    wanted=str(s["global_defect_id"])
    partids={name:int(n) for name,n in zip(
       parts.get_group(wanted)["source_tile_id"],
       parts.get_group(wanted)["source_local_object_index"])}
    for iy in range(y0//256,(y1-1)//256+1):
        for ix in range(x0//256,(x1-1)//256+1):
            name=f"T{iy:03d}_{ix:03d}"
            image,rect=tile_data(name)
            ax=max(rect[0],x0);ay=max(rect[1],y0)
            bx=min(rect[2],x1);by=min(rect[3],y1)
            if ax>=bx or ay>=by:continue
            view=image[ay-rect[1]:by-rect[1],ax-rect[0]:bx-rect[0]]
            loc=(slice(ay-y0,by-y0),slice(ax-x0,bx-x0))
            own=view==partids.get(name,-1)
            original[loc]|=own
            competitors[loc]|=(view>0)&~own
    if int(original.sum())!=int(float(s["source_area_px2"])):
        raise AssertionError("J5 source mask mismatch "+str(s["sample_id"]))
    assert not np.any(original&competitors)
    return original,competitors
def grayscale(raw128):
    a,b=np.percentile(raw128,[1,99.5])
    return np.uint8(np.clip((raw128.astype(float)-a)/max(1,b-a)*255,0,255))
def panel(rawgray,heading,sub,masks):
    img=cv2.cvtColor(rawgray,cv2.COLOR_GRAY2BGR)
    for m,color in masks:
        cnt,_=cv2.findContours(np.uint8(m),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img,cnt,-1,color,1)
        if m.any():
            tint=img.copy();tint[m]=color
            img=cv2.addWeighted(img,.86,tint,.14,0)
    big=cv2.resize(img,(260,260),interpolation=cv2.INTER_NEAREST)
    banner=np.full((65,260,3),24,np.uint8)
    cv2.putText(banner,heading,(5,25),cv2.FONT_HERSHEY_SIMPLEX,.47,(240,240,240),1)
    cv2.putText(banner,sub,(5,47),cv2.FONT_HERSHEY_SIMPLEX,.36,(214,214,214),1)
    return np.vstack((banner,big))

rows=[];largecards=[]
for s in review[review.sample_kind=="SMALL_CANDIDATE"].to_dict("records"):
    name=s["sample_id"]
    x0,y0,x1,y1=[int(s[k]) for k in ("x0","y0","x1","y1")]
    wx0=max(0,x0-72);wy0=max(0,y0-72)
    wx1=min(cfg.RAW_WIDTH,x1+72);wy1=min(cfg.RAW_HEIGHT,y1+72)
    r=np.asarray(raw[wy0:wy1,wx0:wx1],np.uint16)
    old=np.asarray(fused[wy0:wy1,wx0:wx1],np.uint16)
    bh61=black_hat_uint16(r,c.bh61_kernel_px,"ellipse")
    combined=np.maximum(old,bh61)
    own,competitors=fetch_masks(s)
    seed=np.zeros(r.shape,bool)
    seed[y0-wy0:y1-wy0,x0-wx0:x1-wx0]=own
    h_old=component_seeded_H(old,seed,c)
    h_new=component_seeded_H(combined,seed,c)
    sl=(slice(y0-wy0,y1-wy0),slice(x0-wx0,x1-wx0))
    core=h_old[sl];extended=h_new[sl]
    rawpatch=r[sl]
    center=(float(s["target_x_global"])-x0,float(s["target_y_global"])-y0)
    rawprop,rawstats=raw_outer_envelope(rawpatch,own,center,c)
    status,reasons=decision(own,core,extended,rawprop,competitors,rawstats,c)
    suggested=(rawprop|own) if status=="PROVISIONAL_OUTER_SUGGESTION" else own.copy()
    e_aspect,e_box=aspect_and_bbox(extended)
    data={
       "sample_id":name,
       "source_J5_ID":s["global_defect_id"],
       "human_label_evaluation_only":s["manual_candidate_label"],
       "original_area_px2":int(own.sum()),
       "H31_anchor_area_px2":int(core.sum()),
       "H61_added_anchor_area_px2":int(extended.sum()),
       "H61_anchor_aspect":round(float(e_aspect),3) if np.isfinite(e_aspect) else None,
       "raw_envelope_area_px2":int(rawprop.sum()),
       "suggested_display_area_px2":int(suggested.sum()),
       "H61_ratio_from_source":round(extended.sum()/max(int(own.sum()),1),3),
       "original_source_retained":bool(np.all(suggested[own])),
       "overlap_with_other_J5_source":int(np.count_nonzero(rawprop&competitors)),
       "decision":status,
       "rejection_reasons":";".join(reasons),
       **rawstats
    }
    rows.append(data)
    np.savez_compressed(OUT/"masks"/(name+".npz"),
       roi_global_xyxy=np.asarray((x0,y0,x1,y1),np.int32),
       original_J5_detected=own.astype(np.uint8),
       competitor_J5_detected=competitors.astype(np.uint8),
       old_H170_230_anchor=core.astype(np.uint8),
       add61_H170_230_anchor=extended.astype(np.uint8),
       proposed_RAW_envelope=rawprop.astype(np.uint8),
       suggested_display=suggested.astype(np.uint8))
    g=grayscale(rawpatch)
    red=(0,0,245);yellow=(10,225,235);cyan=(210,220,45)
    figs=[
      panel(g,name,"RAW original",[]),
      panel(g,"Frozen J5",f"{own.sum()} px2 original",[(own,red)]),
      panel(g,"BlackHat +61",f"{extended.sum()} px2 H170/230",[(own,red),(extended,yellow)]),
      panel(g,"RAW outer",f"{rawprop.sum()} px2 estimated",[(own,red),(rawprop,cyan)]),
      panel(g,"DISPLAY ONLY",status.replace("_"," ")[:30],[(own,red),(suggested,cyan)]),
    ]
    sheet=np.hstack(figs)
    save_png(OUT/"figures"/(name+"_fivepanel.png"),sheet)
    # a compact 1x3 panel for 24-case summary and first visual inspection.
    pic=cv2.resize(np.hstack((figs[1],figs[2],figs[4])),(780,325),
                   interpolation=cv2.INTER_AREA)
    largecards.append(pic)

# Negative controls: adding BH61 alone must not silently propose new
# detections in the final J5 objects; count new seeds to quantify risk.
for s in review[review.sample_kind=="NO_J5_CANDIDATE_ROI"].to_dict("records"):
    x0,y0,x1,y1=[int(s[k]) for k in ("x0","y0","x1","y1")]
    patch=np.asarray(raw[max(0,y0-72):min(cfg.RAW_HEIGHT,y1+72),
                         max(0,x0-72):min(cfg.RAW_WIDTH,x1+72)],np.uint16)
    ax=max(0,x0-72);ay=max(0,y0-72)
    sl=(slice(y0-ay,y1-ay),slice(x0-ax,x1-ax))
    legacy=np.asarray(fused[ay:ay+patch.shape[0],ax:ax+patch.shape[1]],np.uint16)
    new61=black_hat_uint16(patch,61,"ellipse")
    plus=np.maximum(legacy,new61)
    def new_seed_count(v):
        n,lab,_,_=cv2.connectedComponentsWithStats(np.uint8(v>=170),8)
        hit=np.unique(lab[v>=230]);hit=hit[hit>0]
        return len(hit)
    rows.append({
      "sample_id":s["sample_id"],
      "human_label_evaluation_only":"UNREVIEWED_NO_PREDICTION",
      "original_area_px2":0,
      "H31_anchor_area_px2":0,
      "H61_added_anchor_area_px2":0,
      "raw_envelope_area_px2":0,
      "suggested_display_area_px2":0,
      "decision":"NO_SEED_NO_ADDITIONAL_OBJECT",
      "rejection_reasons":"NO_EXISTING_J5_ANCHOR",
      "old_H_high_seed_components_work_patch":new_seed_count(legacy),
      "H61_high_seed_components_work_patch":new_seed_count(plus),
    })

tab=pd.DataFrame(rows)
tab.to_csv(OUT/"all_30_audit.csv",index=False,encoding="utf-8-sig")
# Concise stable numbered contact sheets; source legend per image.
for i in range(0,len(largecards),6):
    cards=largecards[i:i+6]
    while len(cards)<6:cards.append(np.full_like(cards[-1],25))
    grid=np.vstack(cards)
    save_png(OUT/(f"review_candidates_{i+1:02d}_to_{min(i+6,len(largecards)):02d}.png"),grid)
report={
 "stage":"K3_PROTOTYPE_REVIEW_ONLY",
 "source_J5_frame":"26 (1).raw",
 "original_mask_changes":False,
 "new_independent_defects_proposed":False,
 "new_H_scale_px":61,
 "low_high_DN":[170,230],
 "prototype_config":asdict(c),
 "all_human_labels_posthoc_only":True,
 "sampled_small_candidates":24,
 "no_prediction_ROIs":6,
 "provisional_display_suggestions":int((tab.decision=="PROVISIONAL_OUTER_SUGGESTION").sum()),
 "suggestions_by_human_label":tab[tab.decision=="PROVISIONAL_OUTER_SUGGESTION"]["human_label_evaluation_only"].value_counts().to_dict(),
 "no_missing_source_pixels_in_display":bool(tab["original_source_retained"].dropna().all()),
 "raw_envelope_physical_area_validated":False,
 "need_independent_frame_validation":True
}
(OUT/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),
                                 encoding="utf-8")
print("K3_PROTOTYPE_RESULTS")
print(tab[["sample_id","human_label_evaluation_only","original_area_px2",
           "H61_added_anchor_area_px2","raw_envelope_area_px2",
           "decision","rejection_reasons"]].to_string(index=False),flush=True)
print("K3_PILOT_SUMMARY",json.dumps(report,ensure_ascii=False),flush=True)
