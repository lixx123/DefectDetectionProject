"""Case03-K4: FROZEN K3 guarded contour algorithm on NEW unlabelled J5 targets.

Predefined deterministic area/spatial stratification; 12 MEDIUM, 12 LARGE
compact candidates, 24 SMALL not used in K3 development, and 12 no-detection
ROIs. Never select with human truth or modify segmentation outputs.
Physical outer boundary accuracy remains unknown pending annotation.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
from collections import defaultdict
from functools import lru_cache
import json,sys
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

J5=cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1"
J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
K0=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
O=cfg.OUTPUT_ROOT/"case03k_expanded_validation/run_20261012_new_J5_objects_K3_frozen_v1"
RNG=np.random.default_rng(20261012+43)
W,H=cfg.RAW_WIDTH,cfg.RAW_HEIGHT
CFG=PilotConfig()
CFG.validate()

def pick_spread(df:pd.DataFrame,n:int,blocked:list[tuple[float,float]],minimum_sep:int=144)->pd.DataFrame:
    """Spatially diverse seeded selection from candidate pool, no labels."""
    if len(df)<n:raise ValueError(f"Pool {len(df)} insufficient for {n}")
    d=df.copy()
    d["cell_x"]=np.minimum(5,(d.center_x_global*6/W).astype(int))
    d["cell_y"]=np.minimum(3,(d.center_y_global*4/H).astype(int))
    cell_dict={}
    for cell,part in d.groupby(["cell_y","cell_x"]):
        inds=part.index.to_numpy(copy=True)
        RNG.shuffle(inds)
        cell_dict[cell]=inds.tolist()
    cell_count=defaultdict(int)
    selected=[]
    for _ in range(n):
        candidates=[]
        for cell in sorted(cell_dict):
            while cell_dict[cell]:
                idx=cell_dict[cell][-1]
                row=d.loc[idx]
                px,py=float(row.center_x_global),float(row.center_y_global)
                if any(abs(px-x)<minimum_sep and abs(py-y)<minimum_sep for x,y in blocked):
                    cell_dict[cell].pop()
                else:
                    candidates.append((cell,idx,px,py));break
        if not candidates:raise RuntimeError("Insufficient spatially separated J5 candidates")
        # prefer sparsely selected geographical bins, seeded tie break
        minima=min(cell_count[cell] for cell,_,_,_ in candidates)
        options=[x for x in candidates if cell_count[x[0]]==minima]
        cell,idx,px,py=options[int(RNG.integers(len(options)))]
        cell_dict[cell].pop()
        cell_count[cell]+=1
        blocked.append((px,py))
        selected.append(idx)
    return d.loc[selected].copy()


def selection():
    allrows=pd.read_csv(J5/"global_defects.csv",encoding="utf-8-sig")
    green=pd.read_csv(K0/"manual_review_template.csv",encoding="utf-8-sig",
                      keep_default_na=False)
    first=pd.read_csv(K0/"first_pass_review_30.csv",encoding="utf-8-sig",
                      keep_default_na=False)
    previously_reviewed=set(first.loc[
        first.sample_kind=="SMALL_CANDIDATE","global_defect_id"])
    blocked=[]
    groups=[]
    for grade in ("MEDIUM","LARGE"):
        pool=allrows.loc[
          allrows.grade.eq(grade)&
          allrows.source_bbox_width_px.between(3,48)&
          allrows.source_bbox_height_px.between(3,48)&
          allrows.source_area_px2.between(30,900)&
          allrows.center_x_global.between(150,W-150)&
          allrows.center_y_global.between(150,H-150)&
          ~allrows.touches_full_image_border].copy()
        sub=pick_spread(pool,12,blocked)
        for row in sub.to_dict("records"):
            groups.append((grade,row,None))
    small=green[green.sample_kind=="SMALL_CANDIDATE"].copy()
    small=small.loc[~small.global_defect_id.isin(previously_reviewed)]
    for band in ("A_1px2","B_2to3px2","C_4to7px2","D_8pluspx2"):
        gid=small[small.area_group==band].global_defect_id.tolist()
        pool=allrows[allrows.global_defect_id.isin(gid)].copy()
        sub=pick_spread(pool,6,blocked,minimum_sep=128)
        for row in sub.to_dict("records"):
            groups.append(("UNREVIEWED_SMALL_"+band,row,None))
    assert len(groups)==48
    neg=green[green.sample_kind=="NO_J5_CANDIDATE_ROI"].tail(12)
    assert len(neg)==12
    for r in neg.to_dict("records"):
        groups.append(("NO_PREDICTION_CONTROL",None,r))
    selection_df=[]
    for ix,(group,row,negrow) in enumerate(groups,1):
        if row is not None:
            px=int(round(float(row["center_x_global"])))
            py=int(round(float(row["center_y_global"])))
            x0=int(np.clip(px-64,0,W-128));y0=int(np.clip(py-64,0,H-128))
            box=[x0,y0,x0+128,y0+128]
            # Source bounding box must fit the region; do not silently crop.
            assert (x0<=row["source_bbox_x_global"] and
                    y0<=row["source_bbox_y_global"] and
                    x0+128>=row["source_bbox_x_global"]+row["source_bbox_width_px"] and
                    y0+128>=row["source_bbox_y_global"]+row["source_bbox_height_px"])
            sid=f"K4_{ix:03d}_{row['global_defect_id']}"
            selection_df.append({
              "sample_id":sid,"sample_group":group,
              "global_defect_id":row["global_defect_id"],
              "source_J5_grade":row["grade"],
              "source_area_px2":int(row["source_area_px2"]),
              "center_x_global":float(row["center_x_global"]),
              "center_y_global":float(row["center_y_global"]),
              "x0":box[0],"y0":box[1],"x1":box[2],"y1":box[3],
              "human_manual_label":"","manual_complete_roi_review":"",
              "review_outer_contour_quality":"",
              "review_is_true_defect":"",
              "review_comments":""
            })
        else:
            sid=f"K4_{ix:03d}_NOPRED"
            selection_df.append({
              "sample_id":sid,"sample_group":group,"global_defect_id":"",
              "source_J5_grade":"","source_area_px2":0,
              "center_x_global":np.nan,"center_y_global":np.nan,
              "x0":int(negrow["x0"]),"y0":int(negrow["y0"]),
              "x1":int(negrow["x1"]),"y1":int(negrow["y1"]),
              "human_manual_label":"","manual_complete_roi_review":"",
              "review_outer_contour_quality":"",
              "review_is_true_defect":"",
              "review_comments":""
            })
    df=pd.DataFrame(selection_df)
    assert df.sample_id.is_unique and len(df)==60
    assert not set(df.global_defect_id)&previously_reviewed
    return df,allrows


@lru_cache(maxsize=128)
def tile_info(name):
    with np.load(J4/"tile_masks"/(name+".npz"),allow_pickle=False) as z:
        return z["grouped_source_only_i32"].copy(),tuple(int(v) for v in z["core_xyxy"])

def retrieve_source_and_others(row,bygid):
    x0,y0,x1,y1=(int(row[k]) for k in ("x0","y0","x1","y1"))
    orig=np.zeros((128,128),bool)
    other=np.zeros_like(orig)
    if row["global_defect_id"]:
        m=bygid.get_group(row["global_defect_id"])
        owned={name:set(int(t) for t in part["source_local_object_index"])
               for name,part in m.groupby("source_tile_id")}
    else:
        owned={}
    for iy in range(y0//256,(y1-1)//256+1):
        for ix in range(x0//256,(x1-1)//256+1):
            tid=f"T{iy:03d}_{ix:03d}"
            label,rect=tile_info(tid)
            px=max(rect[0],x0);py=max(rect[1],y0)
            qx=min(rect[2],x1);qy=min(rect[3],y1)
            if px>=qx or py>=qy:continue
            region=label[py-rect[1]:qy-rect[1],px-rect[0]:qx-rect[0]]
            sl=(slice(py-y0,qy-y0),slice(px-x0,qx-x0))
            wanted=np.isin(region,list(owned.get(tid,())))
            orig[sl]|=wanted
            other[sl]|=(region>0)&~wanted
    assert not np.any(orig&other)
    if row["global_defect_id"]:
        assert orig.sum()==int(row["source_area_px2"]),(row["sample_id"],int(orig.sum()),row["source_area_px2"])
    else:
        assert not orig.any() and not other.any(),"No-prediction control contains J5 object"
    return orig,other


def viz(raw,source,h61,outer,display,group,name):
    a,b=np.percentile(raw,[1,99.5])
    g=np.uint8(np.clip((raw.astype(float)-a)/max(1,b-a)*255,0,255))
    imgs=[]
    for i,(name_part,mask) in enumerate([
        ("RAW",np.zeros_like(source)),("FROZEN J5",source),
        ("BH61 H170/230",h61),("RAW OUTER",outer),
        ("DISPLAY ONLY",display)
    ]):
        im=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
        if mask.any():
            tint=im.copy();tint[mask]=(36,207,228)
            im=cv2.addWeighted(im,.77,tint,.23,0)
            cn,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(im,cn,-1,(20,223,240),1)
        red,_=cv2.findContours(np.uint8(source),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im,red,-1,(0,0,235),1)
        im=cv2.resize(im,(260,260),interpolation=cv2.INTER_NEAREST)
        band=np.full((53,260,3),27,np.uint8)
        cv2.putText(band,name_part,(5,20),cv2.FONT_HERSHEY_SIMPLEX,.43,(232,232,232),1)
        cv2.putText(band,f"{int(mask.sum())} px2",(5,42),cv2.FONT_HERSHEY_SIMPLEX,.39,(210,210,210),1)
        imgs.append(np.vstack((band,im)))
    return np.hstack(imgs)


def run():
    if O.exists():raise FileExistsError(O)
    (O/"figures").mkdir(parents=True)
    (O/"masks").mkdir()
    sample,allrows=selection()
    sample.to_csv(O/"manual_review_template.csv",index=False,encoding="utf-8-sig")
    memberships=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
    bygid=memberships.groupby("global_defect_id")
    raw=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",shape=(H,W))
    fused=np.load(cfg.OUTPUT_ROOT/
       "case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
       mmap_mode="r")
    rows=[]
    contact=[]
    for i,s in enumerate(sample.to_dict("records"),1):
        x0,y0,x1,y1=[int(s[k]) for k in ("x0","y0","x1","y1")]
        source,competitor=retrieve_source_and_others(s,bygid)
        patch=np.asarray(raw[y0:y1,x0:x1],np.uint16)
        if s["global_defect_id"]:
            wx0=max(0,x0-72);wy0=max(0,y0-72)
            wx1=min(W,x1+72);wy1=min(H,y1+72)
            win=np.asarray(raw[wy0:wy1,wx0:wx1],np.uint16)
            orig=np.asarray(fused[wy0:wy1,wx0:wx1],np.uint16)
            enlarged=np.maximum(orig,black_hat_uint16(win,61,"ellipse"))
            sourcewin=np.zeros(win.shape,bool)
            sourcewin[y0-wy0:y1-wy0,x0-wx0:x1-wx0]=source
            reg=(slice(y0-wy0,y1-wy0),slice(x0-wx0,x1-wx0))
            old=component_seeded_H(orig,sourcewin,CFG)[reg]
            h61=component_seeded_H(enlarged,sourcewin,CFG)[reg]
            center=(float(s["center_x_global"])-x0,float(s["center_y_global"])-y0)
            rawprop,stats=raw_outer_envelope(patch,source,center,CFG)
            status,reasons=decision(source,old,h61,rawprop,competitor,stats,CFG)
            visible=source|rawprop if status=="PROVISIONAL_OUTER_SUGGESTION" else source.copy()
            row={"sample_id":s["sample_id"],"sample_group":s["sample_group"],
                 "source_global_defect_id":s["global_defect_id"],
                 "source_area_px2":int(source.sum()),
                 "old_H_anchor_px2":int(old.sum()),
                 "new_H61_anchor_px2":int(h61.sum()),
                 "raw_outer_px2":int(rawprop.sum()),
                 "display_provisional_px2":int(visible.sum()),
                 "intersects_competitor_px":int(np.count_nonzero(rawprop&competitor)),
                 "suggestion":status,
                 "review_reason":";".join(reasons),
                 "seed_core_fully_preserved":bool(np.all(visible[source])),
                 "trained_or_tuned_on_sample":False,**stats}
            np.savez_compressed(O/"masks"/(s["sample_id"]+".npz"),
                original_source=source.astype(np.uint8),
                other_detected=competitor.astype(np.uint8),
                original_H=old.astype(np.uint8),
                augmented_H61=h61.astype(np.uint8),
                provisional_raw_outer=rawprop.astype(np.uint8),
                suggested_display=visible.astype(np.uint8),
                global_xyxy=np.array([x0,y0,x1,y1],dtype=np.int32))
        else:
            h61=np.zeros_like(source);rawprop=np.zeros_like(source);visible=source.copy()
            row={"sample_id":s["sample_id"],"sample_group":s["sample_group"],
                 "source_global_defect_id":"",
                 "source_area_px2":0,"old_H_anchor_px2":0,
                 "new_H61_anchor_px2":0,"raw_outer_px2":0,
                 "display_provisional_px2":0,"intersects_competitor_px":0,
                 "suggestion":"NO_J5_OBJECT_NO_NEW_PROPOSAL",
                 "review_reason":"ROI_UNREVIEWED_POTENTIAL_FALSE_NEGATIVE",
                 "seed_core_fully_preserved":True,
                 "trained_or_tuned_on_sample":False}
        rows.append(row)
        panels=viz(patch,source,h61,rawprop,visible,s["sample_group"],s["sample_id"])
        save_png(O/"figures"/(s["sample_id"]+"_5panel.png"),panels)
        contact.append(cv2.resize(panels,(780,188),interpolation=cv2.INTER_AREA))
        if i%12==0:
            print("K4_PROGRESS",i,"/",len(sample),flush=True)
    result=pd.DataFrame(rows)
    result.to_csv(O/"all_60_audit.csv",encoding="utf-8-sig",index=False)
    for i in range(0,len(contact),12):
        pick=contact[i:i+12]
        grid=np.vstack([np.hstack(pick[j:j+3]) for j in range(0,12,3)])
        save_png(O/(f"contact_{i+1:02d}_to_{i+12:02d}.png"),grid)
    summary={
     "stage":"K4_EXTENDED_PILOT_FROZEN_K3",
     "data":"26 (1).raw","all_J4_J5_frozen":True,
     "target_selection_uses_human_labels":False,
     "number_of_new_compact_medium_large_J5_candidates":24,
     "number_of_new_unreviewed_small_J5_candidates":24,
     "number_of_new_no_prediction_regions":12,
     "all_samples":len(sample),
     "algorithm_config":asdict(CFG),
     "new_human_ground_truth_labels":0,
     "new_candidate_sources_created":0,
     "provisional_contour_suggestions":int((result.suggestion=="PROVISIONAL_OUTER_SUGGESTION").sum()),
     "suggestions_by_predeclared_group":result[result.suggestion=="PROVISIONAL_OUTER_SUGGESTION"].sample_group.value_counts().to_dict(),
     "source_pixel_integrity_unchanged":bool(result.seed_core_fully_preserved.all()),
     "independent_frame_validated":False,
     "no_precision_recall_claim":True
    }
    (O/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K4_EXTENDED_SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
    print("OUTPUT",O,flush=True)
    return summary

if __name__=="__main__":run()
