"""Case03-K2 diagnostic: why the obvious K0_SMALL_074 black spot has 24px mask.

Only read frozen J4/J5 & original RAW/fused BlackHat. NO algorithm changes.
Produces stage provenance, radial RAW dark-core profile, and multiple
hypothetical *display* extents for user review. Not calibrated real contour.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03j4_fullscan import halo_rect
from scripts.run_case03t_threeway_comparison import policies,process_one
from scripts.run_case03g_joint_noise_refinement import save_png

SRC=cfg.OUTPUT_ROOT/"case03k_light_review/run_20261012_small_candidate_manual_review_v2"
OUT=SRC/"K2_obvious_spot_074_extent_diagnostic_v1"
if OUT.exists():raise FileExistsError("refuse overwrite historical analysis")
OUT.mkdir()
A=pd.read_csv(SRC/"revision_074_obvious_dark_spot_20261012/first_pass_review_30_labels_corrected.csv",
              encoding="utf-8-sig")
item=A[A.sample_id=="K0_SMALL_074"].iloc[0]
x0,y0,x1,y1=map(int,(item.x0,item.y0,item.x1,item.y1))
gx,gy=int(item.target_x_global),int(item.target_y_global)
assert (x0,y0,x1,y1)==(5635,5606,5763,5734)
rawmem=np.memmap(cfg.DATA_ROOT/"26 (1).raw",mode="r",dtype=">u2",
                 shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
resp=np.load(cfg.OUTPUT_ROOT/
    "case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
    mmap_mode="r")
raw=np.asarray(rawmem[y0:y1,x0:x1],dtype=np.uint16)
blackhat=np.asarray(resp[y0:y1,x0:x1],dtype=np.uint16)
tile="T022_022";J4=cfg.OUTPUT_ROOT/"case03j4_fullframe/run_20261012_frame26_1_full_j4_v1"
with np.load(J4/"tile_masks"/(tile+".npz")) as z:
    rect=np.asarray(z["core_xyxy"],int)
    group=z["grouped_source_only_i32"]
    labels=z["source_region_label_i32"]
    comp=z["continuous_display_i32"]
    bridge=z["inferred_bridge_i32"]
assert tuple(rect)==(5632,5632,5888,5888)
local_id=1
sourceglobal=group==local_id
source=np.zeros(raw.shape,bool)
continuous=np.zeros(raw.shape,bool)
xa,ya=max(x0,rect[0]),max(y0,rect[1])
xb,yb=min(x1,rect[2]),min(y1,rect[3])
source[ya-y0:yb-y0,xa-x0:xb-x0]=sourceglobal[ya-rect[1]:yb-rect[1],xa-rect[0]:xb-rect[0]]
continuous[ya-y0:yb-y0,xa-x0:xb-x0]=comp[ya-rect[1]:yb-rect[1],xa-rect[0]:xb-rect[0]]==local_id
assert int(source.sum())==24 and np.array_equal(source,continuous)
# Re-run identical J4 256+64 halo only to recover stage maps, not alter source.
wx0,wy0,wx1,wy1=halo_rect(rect.tolist(),(cfg.RAW_HEIGHT,cfg.RAW_WIDTH),64)
work=np.asarray(rawmem[wy0:wy1,wx0:wx1],dtype=np.uint16)
response=np.asarray(resp[wy0:wy1,wx0:wx1],dtype=np.uint16)
maps=process_one(work,response,170.,230.,*policies())["maps"]
def crop_work(arr):
    return np.asarray(arr[y0-wy0:y1-wy0,x0-wx0:x1-wx0],bool)
original_H=crop_work(maps["h_original"])
kept_H=crop_work(maps["h_kept_display"])
final=crop_work(maps["fused_joint_display"])
assert np.array_equal(final,source),f"unexpected stage mismatch {final.sum()} {source.sum()}"
# Find the original H component belonging to this real candidate, not all
# unrelated noise peaks within the same 128px crop.
n,lab,stats,_=cv2.connectedComponentsWithStats(np.uint8(original_H),connectivity=8)
intersections=np.bincount(lab[source].ravel(),minlength=n)
intersections[0]=0
id0=int(intersections.argmax())
original_component=lab==id0
# Classifier possibly held original H or H bounded-refinement component.
yy,xx=np.mgrid[:raw.shape[0],:raw.shape[1]]
rad=np.hypot(xx-(gx-x0),yy-(gy-y0))
smooth=cv2.GaussianBlur(raw.astype(np.float32),(0,0),1.3)
background=cv2.GaussianBlur(raw.astype(np.float32),(0,0),20.0)
residual=background-smooth
ann=(rad>=30)&(rad<=48)
median_ann=float(np.median(residual[ann]))
sigma=1.4826*float(np.median(np.abs(residual[ann]-median_ann)))
# RAW annulus estimates are background descriptive, not certified truth.
peak=float(np.percentile(residual[rad<=9],99))
# select one contiguous support region overlapping original 24px source, no
# free-standing proposals. Center threshold tests are independent.
candidates={}
for alpha in (.15,.25,.35,.50):
    thr=max(3*sigma,alpha*peak)
    response_mask=(residual>=thr)&(rad<=34)
    n2,connect,st,_=cv2.connectedComponentsWithStats(
        response_mask.astype(np.uint8),connectivity=8)
    overlap=np.bincount(connect[source].ravel(),minlength=n2)
    overlap[0]=0
    idx=int(overlap.argmax())
    mask=connect==idx if idx>0 and overlap[idx]>0 else np.zeros_like(source)
    candidates[alpha]=(mask,thr)
# Build measured radial means and reference background distribution.
profiles=[]
for j in range(0,51,2):
    selector=(rad>=j)&(rad<j+2)
    profiles.append({"r_inner_px":j,"r_outer_px":j+2,
                     "n":int(selector.sum()),
                     "raw_median_dn":round(float(np.median(raw[selector])),3),
                     "dog20_minus_smoothed_median_dn":round(float(np.median(residual[selector])),3)})
pd.DataFrame(profiles).to_csv(OUT/"radial_profile.csv",index=False,encoding="utf-8-sig")
def bounds(m):
    yy0,xx0=np.where(m)
    if len(xx0)==0:return None
    return {"left_global":int(xx0.min()+x0),"top_global":int(yy0.min()+y0),
            "width_px":int(xx0.max()-xx0.min()+1),
            "height_px":int(yy0.max()-yy0.min()+1),
            "area_px2":int(m.sum()),
            "touches_review_border":bool(
                np.any(xx0==0)|np.any(yy0==0)|
                np.any(xx0==raw.shape[1]-1)|np.any(yy0==raw.shape[0]-1))}
details={
 "sample_id":"K0_SMALL_074",
 "global_defect_id":"DEFECT_10725",
 "raw_review_xyxy":[x0,y0,x1,y1],
 "original_j4_tile":tile,
 "original_j5_area_px2":int(source.sum()),
 "original_j4_H_pixels_in_crop_all":int(original_H.sum()),
 "original_H_same_component_pixels":int(original_component.sum()),
 "original_H_covered_by_J5":int((original_component&source).sum()),
 "original_final_pixels_in_crop_all":int(final.sum()),
 "h_kept_pixels_in_crop_all":int(kept_H.sum()),
 "j5_object_bbox":bounds(source),
 "radial_background_noise_sigma_DN":round(sigma,4),
 "radial_background_residual_median_DN":round(median_ann,4),
 "peak_background_subtracted_dark_DN":round(peak,4),
 "candidate_boundaries_are_hypotheses_not_truth":True,
 "no_config_or_original_mask_changed":True,
 "candidate_masks":{}
}
for alpha,(mask,thr) in candidates.items():
    details["candidate_masks"][str(alpha)]={
       "threshold_DN":round(thr,3),
       "mask_bbox":bounds(mask),
       "J5_source_pixels_inside":int((mask&source).sum()),
       "new_hypothetical_pixels":int((mask&~source).sum()),
       "not_measured_actual_defect_area":True}
def background8():
    a,b=np.percentile(raw.astype(float),[1,99.5])
    return np.uint8(np.clip((raw.astype(float)-a)/(max(a+1,b)-a)*255,0,255))
g=background8()
def pane(title,mask=None,color=(15,225,230),bbox=True):
    image=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    if mask is not None and mask.any():
        fill=image.copy()
        fill[mask]=color
        image=cv2.addWeighted(image,.72,fill,.28,0)
        contour,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(image,contour,-1,color,1)
    cv2.drawMarker(image,(gx-x0,gy-y0),(230,190,32),
                   cv2.MARKER_CROSS,6,1)
    scaled=cv2.resize(image,(384,384),interpolation=cv2.INTER_NEAREST)
    bar=np.full((55,384,3),28,np.uint8)
    cv2.putText(bar,title,(10,24),cv2.FONT_HERSHEY_SIMPLEX,
                .60,(245,245,245),1,cv2.LINE_AA)
    return np.vstack((bar,scaled))
panels=[
 pane("RAW original"),
 pane(f"Original H component ({original_component.sum()} px)",original_component,(180,100,245)),
 pane(f"J5 detected object ({source.sum()} px)",source,(5,5,240)),
 pane(f"RAW residual >= 15% peak ({candidates[.15][0].sum()})",candidates[.15][0],(50,220,220)),
 pane(f"RAW residual >= 25% peak ({candidates[.25][0].sum()})",candidates[.25][0],(10,180,230)),
 pane(f"RAW residual >= 35% peak ({candidates[.35][0].sum()})",candidates[.35][0],(60,170,70)),
 pane(f"RAW residual >= 50% peak ({candidates[.50][0].sum()})",candidates[.50][0],(210,170,15)),
 pane("Original RAW (same pixels)")]
combined=np.vstack((np.hstack(panels[:4]),np.hstack(panels[4:])))
save_png(OUT/"074_original_H_J5_vs_local_extent_8panels.png",combined)
np.savez_compressed(OUT/"074_exact_trial_masks.npz",
                   raw_128_u16=raw,source_J5_mask_uint8=source.astype(np.uint8),
                   original_H_component_u8=original_component.astype(np.uint8),
                   original_H_all_u8=original_H.astype(np.uint8),
                   final_all_u8=final.astype(np.uint8),
                   candidate_alpha15=candidates[.15][0].astype(np.uint8),
                   candidate_alpha25=candidates[.25][0].astype(np.uint8),
                   candidate_alpha35=candidates[.35][0].astype(np.uint8),
                   candidate_alpha50=candidates[.50][0].astype(np.uint8),
                   roi_global_xyxy=np.asarray((x0,y0,x1,y1),dtype=np.int32))
(OUT/"diagnostic_summary.json").write_text(
    json.dumps(details,ensure_ascii=False,indent=2),encoding="utf-8")
print("K2_074_DIAGNOSTIC",json.dumps(details,ensure_ascii=False),flush=True)
print("OUTPUT",OUT,flush=True)
