"""Case03-K2b - extend obvious 074 dark spot envelope beyond previous 15%.

Pure diagnostic, NOT new defect segmentation ground truth.
Investigates: (A) sigma20 local-background halo self-contamination;
(B) old 3*MADσ minimum that overrides nominal 15% peak;
(C) anisotropic low-contrast tail which radial averages miss.

Try sigma20, sigma40 and robust outer-annulus planar background under
k=3,2,1.5 local MADσ. Candidate must touch original J5 24px mask.
All png and csv are new and all past masks/parameters unchanged.
"""
from __future__ import annotations
from pathlib import Path
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_case03g_joint_noise_refinement import save_png
BASE=ROOT/"outputs/case03k_light_review/run_20261012_small_candidate_manual_review_v2"
SRC=BASE/"K2_obvious_spot_074_extent_diagnostic_v1/074_exact_trial_masks.npz"
OUT=BASE/"K2b_074_outer_dark_halo_models_v1"
if OUT.exists():raise FileExistsError(OUT)
OUT.mkdir()
with np.load(SRC) as f:
    raw=f["raw_128_u16"].copy()
    source=f["source_J5_mask_uint8"].astype(bool)
    rect=tuple(int(v) for v in f["roi_global_xyxy"])
    old15=f["candidate_alpha15"].astype(bool)
assert raw.shape==(128,128) and int(source.sum())==24
cx,cy=5699-rect[0],5670-rect[1]
yy,xx=np.mgrid[:128,:128]
dx=xx-cx;dy=yy-cy
r=np.hypot(dx,dy)
F=raw.astype(np.float32)
fine=cv2.GaussianBlur(F,(0,0),1.3)
# Outside candidate envelope but sufficiently far from target center:
outer=(r>=38)&(r<=58)
# Median background includes all directions, 1st order plane robust fit.
coords=np.column_stack((np.ones(int(outer.sum())),
                         dx[outer].astype(float),dy[outer].astype(float)))
targets=F[outer].astype(float)
beta=np.linalg.lstsq(coords,targets,rcond=None)[0]
for _ in range(6):
    err=targets-coords@beta
    sigma=1.4826*np.median(abs(err-np.median(err)))
    cutoff=max(3.,1.5*sigma)
    w=np.minimum(1.,cutoff/np.maximum(abs(err),1.e-6))
    Aw=coords*w[:,None]
    beta=np.linalg.lstsq(coords.T@Aw,coords.T@(w*targets),rcond=None)[0]
plane=(beta[0]+beta[1]*dx+beta[2]*dy).astype(np.float32)
methods={
    "G20":cv2.GaussianBlur(F,(0,0),20)-fine,
    "G40":cv2.GaussianBlur(F,(0,0),40)-fine,
    "OUTER_PLANE":plane-fine,
}
def bw_stats(m):
    y,x=np.nonzero(m)
    if not len(x):return {
        "area_px2":0,"bbox_xywh":None,"touch_crop_edge":False,
        "max_radius_px":None, "new_pixels":0}
    return {
      "area_px2":int(m.sum()),
      "bbox_xywh":[int(x.min()+rect[0]),int(y.min()+rect[1]),
                   int(x.max()-x.min()+1),int(y.max()-y.min()+1)],
      "touch_crop_edge":bool((x==0).any() or (x==127).any()
                    or (y==0).any() or (y==127).any()),
      "max_radius_px":round(float(r[m].max()),3),
      "new_pixels":int((m&~source).sum()),
      "origin_pixels_retained":int((m&source).sum())}
def select_seed(m):
    n,lab,_,_=cv2.connectedComponentsWithStats(
         m.astype(np.uint8),8)
    overlap=np.bincount(lab[source],minlength=n)
    overlap[0]=0
    k=int(overlap.argmax())
    if k==0 or not overlap[k]:return np.zeros_like(source)
    return lab==k
base8=np.uint8(np.clip((F-np.percentile(F,1))/max(1,np.percentile(F,99.5)-np.percentile(F,1))*255,0,255))
def panel(name,mask,footer):
    image=cv2.cvtColor(base8,cv2.COLOR_GRAY2BGR)
    if mask.any():
        tint=image.copy()
        tint[mask]=(30,210,205)
        image=cv2.addWeighted(image,.75,tint,.25,0)
        contour,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image,contour,-1,(20,225,230),1)
    c,_=cv2.findContours(np.uint8(source),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(image,c,-1,(0,0,250),1)
    cv2.drawMarker(image,(cx,cy),(220,180,40),cv2.MARKER_CROSS,5,1)
    dst=cv2.resize(image,(400,400),interpolation=cv2.INTER_NEAREST)
    bar=np.full((58,400,3),26,dtype=np.uint8)
    cv2.putText(bar,name,(7,25),cv2.FONT_HERSHEY_SIMPLEX,.60,(244,244,244),1)
    cv2.putText(bar,footer,(7,46),cv2.FONT_HERSHEY_SIMPLEX,.40,(208,208,208),1)
    return np.vstack((bar,dst))
results=[]
sheets=[panel("Original RAW",np.zeros_like(source),"Red core = 24px; no estimated contour"),
        panel("Old 15pct / G20 3sigma",old15,"Old candidate = 638px2")]
storage={"raw":raw,"source_original":source.astype(np.uint8),
         "old15":old15.astype(np.uint8)}
for method,residual in methods.items():
    ring=residual[outer]
    med=float(np.median(ring))
    sigma=1.4826*float(np.median(abs(ring-med)))
    peak=float(np.percentile(residual[r<=9],99))
    for k in (3.,2.5,2.,1.5):
        threshold=max(k*sigma,.15*peak)
        full=(residual>=threshold)&(r<=49)
        candidate=select_seed(full)
        stats=bw_stats(candidate)
        actual={"model":method,"k_noise_sigma":k,
                "noise_sigma_dn":round(sigma,3),
                "peak_dn":round(peak,3),
                "threshold_dn":round(threshold,3),
                "15pct_peak_dn":round(.15*peak,3),
                "outer_annulus_residual_median_dn":round(med,3),
                **stats}
        results.append(actual)
        key=f"{method}_k{k:g}".replace(".","p")
        storage[key]=candidate.astype(np.uint8)
        title=f"{method} {k:g}sigma / {stats['area_px2']}px2"
        footer=f"cut {threshold:.1f}DN | maxr {stats['max_radius_px']} px"
        sheets.append(panel(title,candidate,footer))
while len(sheets)%4:sheets.append(np.full_like(sheets[-1],26))
big=np.vstack([np.hstack(sheets[i:i+4]) for i in range(0,len(sheets),4)])
out=OUT/"074_boundary_model_and_noise_floor_16panel.png"
save_png(out,big)
pd.DataFrame(results).to_csv(OUT/"074_12_boundary_hypotheses.csv",index=False,encoding="utf-8-sig")
np.savez_compressed(OUT/"074_comparison_masks.npz",**storage)
report={
  "title":"K2b multi-model outer halo exploration for obvious 074 spot",
  "source_mask_pixels":24,"previous_alpha15_pixels":638,
  "reference": "Frozen J5 H170/230 source area=24 pixels",
  "models":list(methods),
  "robust_plane_coefficients":beta.tolist(),
  "outer_background_roi_radial_pixels":[38,58],
  "tested_sigmas":[3,2.5,2,1.5],
  "source_masks_modified":False,
  "derived_proposed_masks_are_not_physical_truth":True,
  "edge_not_certified":True
}
(OUT/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
png=cv2.imdecode(np.frombuffer(out.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
assert png is not None and png.shape==big.shape
print("K2b_074_RESULT_TABLE",pd.DataFrame(results).to_string(index=False),flush=True)
print("K2b_074_COMPLETE",str(out),flush=True)
