"""K3/K4 scale-sensitive discovery from unseen candidate objects (no human labels).

Deterministic upfront sample 240 J5 SMALL: 24 area1,24 area2-3,
72 area4-7,120 area8-39. Excludes all K0 previously presented small IDs
and K4 already assessed IDs. Examine BH61 source-anchor potential BEFORE
optional RAW stage. No new object creation, no writeback.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
import json,sys
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k3_spot_contour_pilot import (
 PilotConfig,component_seeded_H,raw_outer_envelope,decision,aspect_and_bbox)
from scripts.run_case03k4_expanded_pilot import (
 retrieve_source_and_others,viz,J5,J4,K0)
from scripts.run_case03g_joint_noise_refinement import save_png
D=cfg.OUTPUT_ROOT/"case03k_expanded_validation/run_20261012_new_J5_objects_K3_frozen_v1"
O=cfg.OUTPUT_ROOT/"case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1"
CFG=PilotConfig()
if O.exists():raise FileExistsError(O)
O.mkdir()
m=pd.read_csv(J5/"global_object_membership.csv")
bygid=m.groupby("global_defect_id")
j=pd.read_csv(J5/"global_defects.csv")
j=j[(j.grade=="SMALL")&
    (j.center_x_global.between(170,cfg.RAW_WIDTH-170))&
    (j.center_y_global.between(170,cfg.RAW_HEIGHT-170))&
    (j.source_bbox_width_px<=48)&(j.source_bbox_height_px<=48)]
old=pd.read_csv(K0/"manual_review_template.csv",keep_default_na=False)
k4=pd.read_csv(D/"manual_review_template.csv",keep_default_na=False)
blocked=set(old.loc[old.sample_kind=="SMALL_CANDIDATE","global_defect_id"])|set(k4.global_defect_id)
j=j[~j.global_defect_id.isin(blocked)].copy()
j["stratum"]=pd.cut(j.source_area_px2,bins=(0,1,3,7,39),labels=("A1","B2to3","C4to7","D8plus"),include_lowest=True)
target={"A1":24,"B2to3":24,"C4to7":72,"D8plus":120}
rng=np.random.default_rng(20261012+45)
chosen=[]
for group,n in target.items():
    part=j[j.stratum==group].copy()
    if len(part)<n:raise ValueError(f"Not enough unexposed samples {group} {len(part)}")
    # Equalized coarse 6x4 cell sampling with deterministic random order.
    part["cell"]=((part.center_y_global*4//cfg.RAW_HEIGHT).astype(int)*6+
                   (part.center_x_global*6//cfg.RAW_WIDTH).astype(int))
    cells={}
    for key,section in part.groupby("cell"):
        ids=section.index.to_numpy(copy=True)
        rng.shuffle(ids);cells[int(key)]=ids.tolist()
    cnt={k:0 for k in cells}
    selected=[]
    for _ in range(n):
        opts=[k for k in cells if cells[k]]
        min_count=min(cnt[k] for k in opts)
        possible=[k for k in opts if cnt[k]==min_count]
        k=possible[int(rng.integers(len(possible)))]
        selected.append(cells[k].pop());cnt[k]+=1
    chosen.extend(selected)
selected=j.loc[chosen].copy()
assert len(selected)==sum(target.values()) and selected.global_defect_id.is_unique
selected.to_csv(O/"fixed_unlabeled_selection.csv",index=False,encoding="utf-8-sig")

RAW=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
BH=np.load(cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",mmap_mode="r")
table=[]
vis=[]
for i,s in enumerate(selected.to_dict("records"),1):
    xc=int(round(s["center_x_global"]));yc=int(round(s["center_y_global"]))
    x0=xc-64;y0=yc-64;x1=x0+128;y1=y0+128
    if not (x0<=s["source_bbox_x_global"] and y0<=s["source_bbox_y_global"] and
            x1>=s["source_bbox_x_global"]+s["source_bbox_width_px"] and
            y1>=s["source_bbox_y_global"]+s["source_bbox_height_px"]):
        raise ValueError("source candidate escaped ROI, do not silently clip")
    case={"sample_id":f"K4S_{i:03d}","sample_group":str(s["stratum"]),
          "global_defect_id":s["global_defect_id"],
          "source_area_px2":int(s["source_area_px2"]),
          "x0":x0,"y0":y0,"x1":x1,"y1":y1}
    source,competitors=retrieve_source_and_others(case,bygid)
    ax=x0-72;ay=y0-72;bx=x1+72;by=y1+72
    win=np.asarray(RAW[ay:by,ax:bx],np.uint16)
    frozen=np.asarray(BH[ay:by,ax:bx],np.uint16)
    combined=np.maximum(frozen,black_hat_uint16(win,61,"ellipse"))
    global_seed=np.zeros(win.shape,bool)
    global_seed[72:200,72:200]=source
    cut=(slice(72,200),slice(72,200))
    h61=component_seeded_H(combined,global_seed,CFG)[cut]
    h_old=component_seeded_H(frozen,global_seed,CFG)[cut]
    aspect,_=aspect_and_bbox(h61)
    try_raw=(int(h61.sum())>=CFG.min_h61_area_px and
             h61.sum()>=CFG.min_h61_growth_ratio*int(source.sum()) and
             aspect<=CFG.max_h61_axis_aspect and
             h61.sum()<=CFG.h61_max_fraction_of_roi*source.size)
    prop=np.zeros_like(source)
    audit={}
    verdict="PRECHECK_FAIL_NOT_RUN_RAW";reasons=[]
    if try_raw:
        prop,audit=raw_outer_envelope(np.asarray(RAW[y0:y1,x0:x1],np.uint16),
                                     source,(s["center_x_global"]-x0,
                                             s["center_y_global"]-y0),CFG)
        verdict,reasons=decision(source,h_old,h61,prop,competitors,audit,CFG)
    entry={
       **case,
       "H31_anchor_area":int(h_old.sum()),
       "H61_anchor_area":int(h61.sum()),
       "H61_growth_ratio_from_J5":round(h61.sum()/max(source.sum(),1),3),
       "H61_axis_aspect":round(float(aspect),3) if np.isfinite(aspect) else None,
       "shape_size_precheck_pass":bool(try_raw),
       "RAW_envelope_trial_area":int(prop.sum()),
       "accepted_provisional":verdict=="PROVISIONAL_OUTER_SUGGESTION",
       "decision":verdict,"veto":";".join(reasons),
       "other_J5_mask_intersected":int(np.count_nonzero(prop&competitors)),
       "human_label_provided":False,"J5_source_untouched":True
    }
    table.append(entry)
    if try_raw:vis.append((entry,source,h61,prop,np.asarray(RAW[y0:y1,x0:x1],np.uint16)))
    if i%40==0:print("SCALE_DISCOVERY_PROGRESS",i,240,
                    "eligible",len(vis),flush=True)

df=pd.DataFrame(table)
df.to_csv(O/"240_scale_trial_audit.csv",encoding="utf-8-sig",index=False)
displayed=sorted(vis,key=lambda z:(
    z[0]["accepted_provisional"],
    z[0]["RAW_envelope_trial_area"],z[0]["H61_growth_ratio_from_J5"]),reverse=True)[:18]
(O/"review_figures").mkdir()
thumbs=[]
for item,source,h61,prop,im in displayed:
    suggested=source|prop if item["accepted_provisional"] else source
    five=viz(im,source,h61,prop,suggested,item["sample_group"],item["sample_id"])
    dst=O/"review_figures"/(item["sample_id"]+"_unlabeled_5panel.png")
    save_png(dst,five)
    thumbs.append(cv2.resize(five,(780,188),interpolation=cv2.INTER_AREA))
for i in range(0,len(thumbs),9):
    arr=thumbs[i:i+9]
    while len(arr)<9:arr.append(np.full_like(thumbs[0],26))
    img=np.vstack([np.hstack(arr[z:z+3]) for z in range(0,9,3)])
    save_png(O/(f"top_unlabeled_{i+1:02d}_to_{i+9:02d}.png"),img)
summary={
 "stage":"UNLABELED_SCALE_SENSITIVE_DISCOVERY",
 "fixed_sample_count":len(df),
 "sample_size_strata":target,
 "excluded_all_K0_96_previous_samples":True,
 "excluded_K4_60_previous_samples":True,
 "user_labels_used_to_select":False,
 "BH61_scale_eligible":int(df.shape_size_precheck_pass.sum()),
 "all_guard_conditions_provisional_suggestions":int(df.accepted_provisional.sum()),
 "eligible_unlabeled_review_images":len(displayed),
 "original_H_and_J5_data_changed":False,
 "not_an_independent_frame":True,
 "no_real_defect_or_quality_claims":True,
 "config":asdict(CFG),
}
(O/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print("K4S_DISCOVERY_RESULT",json.dumps(summary,ensure_ascii=False),flush=True)
print("K4S_ELIGIBLE_ROWS",df[df.shape_size_precheck_pass][["sample_id","source_area_px2","H61_anchor_area","RAW_envelope_trial_area","decision","veto"]].to_string(index=False))
