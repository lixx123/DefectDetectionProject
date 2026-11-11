"""Case03-K2c: controlled response floor experiments for the 074 halo.

Original 24px mask remains untouched. Visual extent candidates are NOT
physical truth. Stage explicitly tests alpha=15%,10%,5% and k=3,2,1.5
under robust planar external-ring baseline. Includes unconstrained area
of other components for awareness of noise-merging risk.
"""
from pathlib import Path
import sys,json
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_case03g_joint_noise_refinement import save_png
B=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
S=B/"K2_obvious_spot_074_extent_diagnostic_v1/074_exact_trial_masks.npz"
O=B/"K2c_074_lower_floor_guarded_experiment_v2"
if O.exists():raise FileExistsError(O)
O.mkdir()
with np.load(S) as z:
    raw=z["raw_128_u16"].astype(np.float32)
    src=z["source_J5_mask_uint8"]>0
    previous=z["candidate_alpha15"]>0
    rect=z["roi_global_xyxy"]
cx,cy=5699-int(rect[0]),5670-int(rect[1])
yy,xx=np.mgrid[:128,:128]
dx=xx-cx;dy=yy-cy
rad=np.hypot(dx,dy)
ring=(rad>=38)&(rad<=58)
A=np.stack((np.ones_like(dx)[ring],dx[ring],dy[ring]),axis=1)
b=raw[ring]
beta=np.linalg.lstsq(A,b,rcond=None)[0]
for _ in range(5):
    residual=b-A@beta
    s=1.4826*np.median(np.abs(residual-np.median(residual)))
    cut=max(3,1.5*s)
    weights=np.minimum(1.,cut/np.maximum(abs(residual),1.e-6))
    beta=np.linalg.lstsq(A.T@(A*weights[:,None]),A.T@(b*weights),rcond=None)[0]
model=(beta[0]+beta[1]*dx+beta[2]*dy).astype(np.float32)
fine=cv2.GaussianBlur(raw,(0,0),1.3)
delta=model-fine
s=1.4826*np.median(abs(delta[ring]-np.median(delta[ring])))
peak=float(np.percentile(delta[rad<=9],99))
baseline=raw
lo,hi=np.percentile(raw,[1,99.5])
display=np.uint8(np.clip((raw-lo)/max(1,hi-lo)*255,0,255))
def connected_region(t):
    mask=(delta>=t)&(rad<=49)
    n,ids,stats,_=cv2.connectedComponentsWithStats(np.uint8(mask),8)
    counts=np.bincount(ids[src],minlength=n);counts[0]=0
    idx=int(counts.argmax())
    if idx==0 or counts[idx]==0:return np.zeros_like(src),n,0
    return ids==idx,n,n-2  # other foreground components
def render(title,mask,subtitle):
    bg=cv2.cvtColor(display,cv2.COLOR_GRAY2BGR)
    if mask.any():
        tinted=bg.copy();tinted[mask]=(25,198,230)
        bg=cv2.addWeighted(bg,.68,tinted,.32,0)
        outlines,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(bg,outlines,-1,(0,220,220),1)
    oldout,_=cv2.findContours(np.uint8(src),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(bg,oldout,-1,(0,0,250),1)
    image=cv2.resize(bg,(380,380),interpolation=cv2.INTER_NEAREST)
    header=np.full((55,380,3),27,np.uint8)
    cv2.putText(header,title,(8,25),cv2.FONT_HERSHEY_SIMPLEX,.57,(239,239,239),1)
    cv2.putText(header,subtitle,(8,46),cv2.FONT_HERSHEY_SIMPLEX,.37,(213,213,213),1)
    return np.vstack((header,image))
records=[]
views=[render("RAW / real J5 core 24px",src,"RED=original H/J5 source mask"),
       render("Old G20 15% / 638px2",previous,"Old 3sigma floor, r30-48"),
      ]
configs=[(.15,3.),(.10,3.),(.10,2.),(.075,2.),(.05,2.),(.05,1.5)]
for a,k in configs:
    t=max(k*s,a*peak)
    m,total,other=connected_region(t)
    ys,xs=np.nonzero(m)
    params={
        "relative_peak_fraction":a,
        "noise_multiple":k,
        "peak_DN":round(peak,3),
        "noise_MAD_sigma_DN":round(s,3),
        "actual_threshold_DN":round(t,3),
        "candidate_area_px2":int(m.sum()),
        "original_detected_pixels_inside":int((m&src).sum()),
        "new_pixels":int((m&~src).sum()),
        "component_area_fraction_of_128px_crop":round(float(m.mean()),5),
        "max_radius_px":round(float(rad[m].max()),2) if len(xs) else None,
        "bounding_box_global_xywh":[int(xs.min()+rect[0]),int(ys.min()+rect[1]),
           int(np.ptp(xs)+1),int(np.ptp(ys)+1)] if len(xs) else None,
        "touches_crop_or_radius_cap":bool((xs==0).any() or (xs==127).any() or
                                       (ys==0).any() or (ys==127).any() or
                                       (rad[m]>=48).any()) if len(xs) else False,
        "other_foreground_components":int(other),
        "physically_confirmed_outer_boundary":False
    }
    records.append(params)
    views.append(render(f"PLANE {a*100:g}% + {k:g}sig / {m.sum()}px2",
            m,f"thr {t:.1f} DN ; max radius {params['max_radius_px']} px"))
while len(views)%4:views.append(np.full_like(views[-1],27))
img=np.vstack([np.hstack(views[i:i+4]) for i in range(0,len(views),4)])
save_png(O/"074_stricter_vs_broader_boundary_8panel.png",img)
pd.DataFrame(records).to_csv(O/"candidate_threshold_sensitivity.csv",index=False,encoding="utf-8-sig")
summary={"J5_original_pixels":int(src.sum()),"old_15percent_pixels":int(previous.sum()),
         "baseline_model":"robust 1st order fit on outer annulus radius 38-58px",
         "original_masks_untouched":True,
         "all_proposed_boundaries_unverified":True,
         "note":"Lowering percentage alone cannot bypass a higher k*MAD floor",
         "configs":records}
(O/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=float),encoding="utf-8")
print(pd.DataFrame(records)[["relative_peak_fraction","noise_multiple","actual_threshold_DN","candidate_area_px2","max_radius_px","touches_crop_or_radius_cap","other_foreground_components"]].to_string(index=False),flush=True)
print("K2c_DONE",O,flush=True)
