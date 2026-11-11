"""Case03-K4b | K4S_079: diagnose remaining visible dark halo under frozen
K3 rule. NEVER changes original H/J5 masks, thresholds, IDs or grades.

Compare robust-plane RAW envelope for a controlled 3x3 grid of:
fraction-of-peak (15%,10%,5%) versus noise-floor (3,2,1.5)*MAD-sigma.
Retain existing J5 seed and explicitly audit proximity to other J5 objects.
All contours are exploratory / NOT user-labeled true defect outlines.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import replace
import json,sys
import pandas as pd,numpy as np,cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03k4_expanded_pilot import retrieve_source_and_others,J5
from src.detection.case03k3_spot_contour_pilot import PilotConfig,raw_outer_envelope,decision
from scripts.run_case03g_joint_noise_refinement import save_png
BASE=cfg.OUTPUT_ROOT/"case03k_expanded_validation/run_20261012_240_green_scale_sensitivity_v1"
OUT=BASE/"K4b_079_outer_boundary_sensitivity_v1"
if OUT.exists():raise FileExistsError(OUT)
OUT.mkdir()
AUDIT=pd.read_csv(BASE/"240_scale_trial_audit.csv",encoding="utf-8-sig")
s=AUDIT.loc[AUDIT.sample_id=="K4S_079"].iloc[0].to_dict()
allm=pd.read_csv(J5/"global_object_membership.csv",encoding="utf-8-sig")
source,other=retrieve_source_and_others(s,allm.groupby("global_defect_id"))
assert source.sum()==7
x0,y0,x1,y1=[int(s[k]) for k in ("x0","y0","x1","y1")]
rawfull=np.memmap(cfg.DATA_ROOT/"26 (1).raw",dtype=">u2",mode="r",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
raw=np.asarray(rawfull[y0:y1,x0:x1],np.uint16)
center=(1399.2857-x0,2944.1429-y0)
cfg0=PilotConfig()
cfg0.validate()
base,met=raw_outer_envelope(raw,source,center,cfg0)
assert base.sum()==179,(base.sum(),met)
a,b=np.percentile(raw.astype(float),[1,99.5])
G=np.uint8(np.clip((raw.astype(float)-a)/max(1.,b-a)*255,0,255))
yy,xx=np.indices(raw.shape)
r=np.hypot(xx-center[0],yy-center[1])
def plate(title,mask,text):
    img=cv2.cvtColor(G,cv2.COLOR_GRAY2BGR)
    if mask.any():
        tinted=img.copy();tinted[mask]=(48,207,238)
        img=cv2.addWeighted(img,.73,tinted,.27,0)
        cs,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,
                              cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img,cs,-1,(10,230,240),1)
    c,_=cv2.findContours(np.uint8(source),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(img,c,-1,(0,0,250),1)
    im=cv2.resize(img,(360,360),interpolation=cv2.INTER_NEAREST)
    h=np.full((60,360,3),25,np.uint8)
    cv2.putText(h,title,(7,24),cv2.FONT_HERSHEY_SIMPLEX,.51,(238,238,238),1)
    cv2.putText(h,text,(7,46),cv2.FONT_HERSHEY_SIMPLEX,.37,(205,205,205),1)
    return np.vstack((h,im))
records=[];plates=[
    plate("Original J5 mask: 7px",source,"Red = detector core"),
    plate("Frozen RAW outer: 179px",base,"alpha15%, floor 3sigma")
]
trials={}
for alpha in (.15,.10,.05):
    for k in (3.,2.,1.5):
        cc=replace(cfg0,raw_alpha_peak=alpha,raw_noise_sigma_multiplier=k)
        proposed,metrics=raw_outer_envelope(raw,source,center,cc)
        physical=np.count_nonzero(proposed&other)
        mag=int(proposed.sum())
        if proposed.any():
            sy,sx=np.nonzero(proposed)
            globalbbox=[int(x0+sx.min()),int(y0+sy.min()),
                        int(sx.max()-sx.min()+1),int(sy.max()-sy.min()+1)]
            maxr=float(r[proposed].max())
        else:globalbbox=None;maxr=0.
        row={
            "alpha":alpha,"noise_floor_sigma_multiplier":k,
            "threshold_DN":metrics["raw_boundary_threshold_DN"],
            "sigma_DN":metrics["raw_bg_ring_mad_sigma_DN"],
            "peak_DN":metrics["raw_local_peak_DN"],
            "area_px2":mag,
            "ratio_vs_initial179":round(mag/179.,4),
            "j5_source_overlap":int(np.count_nonzero(proposed&source)),
            "other_J5_source_intersections":int(physical),
            "touches_cap":bool(metrics["raw_proposal_touches_radius_cap"]),
            "touches_crop":bool(metrics["raw_proposal_touches_roi_border"]),
            "global_bbox_xywh":globalbbox,
            "max_radius_px":round(maxr,3),
            "valid_physical_boundary_ground_truth":False
        }
        records.append(row)
        trials[f"alpha{int(alpha*100)}_noise{str(k).replace('.','p')}"]=proposed.astype(np.uint8)
        plates.append(plate(f"alpha{alpha*100:g}% | floor{k:g}σ | {mag}px",
             proposed,f"thr {row['threshold_DN']:.1f}DN; intersects {physical}"))
# Make contact grid (3 cols x4 rows), original+baseline+9 configs=11
while len(plates)%3:plates.append(np.full_like(plates[-1],25))
grid=np.vstack([np.hstack(plates[i:i+3]) for i in range(0,len(plates),3)])
save_png(OUT/"K4S079_11boundary_sensitivity.png",grid)
np.savez_compressed(OUT/"all_outlines.npz",
    **trials,
    original_mask=source.astype(np.uint8),
    base_179=base.astype(np.uint8),
    competitor_mask=other.astype(np.uint8),
    roi_xyxy=np.asarray((x0,y0,x1,y1),np.int32))
pd.DataFrame(records).to_csv(OUT/"sensitivity_audit.csv",index=False,encoding="utf-8-sig")
summary={
 "sample":"K4S_079","source_global_defect_id":s["global_defect_id"],
 "source_mask_area_px2":int(source.sum()),
 "frozen_RAW_contour_area_px2":int(base.sum()),
 "manual_coverage_verbal_estimate":"approximately 70% visual",
 "manual_physical_ground_truth_mask_available":False,
 "tested_thresholds_independent_of_manual_image_contour":True,
 "all_scenarios_exploratory":True,
 "source_J5_and_K3_configs_unchanged":True,
 "settings_tested":records,
 "recommendation":"Compare visible background extension and J5 neighbor overlap; no automatic grade/area update"
}
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                 encoding="utf-8")
check=cv2.imdecode(np.frombuffer((OUT/"K4S079_11boundary_sensitivity.png").read_bytes(),np.uint8),1)
assert check is not None and check.shape==grid.shape
print("K4S079_SENSITIVITY_AUDIT")
print(pd.DataFrame(records)[["alpha","noise_floor_sigma_multiplier","threshold_DN","area_px2","other_J5_source_intersections","touches_cap"]].to_string(index=False),flush=True)
print("K4S079_COMPLETED",str(OUT),flush=True)
