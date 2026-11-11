"""K6_190 diagnostic: source seed at center, obvious dark structure to left.

Strict read-only audit. No changes to production J4/J5/K5. Save
actual 128px gray response and J5 labels, BH61 seed vs RAW dark components.
"""
from pathlib import Path
import sys,json
import numpy as np,cv2,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03k6_second_frame_K5 import J5,RAW,RESP,original_id_map
from scripts.run_case03g_joint_noise_refinement import save_png
from src.detection.case03k3_spot_contour_pilot import (
 PilotConfig,raw_outer_envelope,robust_outer_plane,aspect_and_bbox)
SOURCE=cfg.OUTPUT_ROOT/"case03k6_frame2_independent/run_20261012_frame26_2_frozen_K5_v1"
OUT=SOURCE/"K6_190_seed_geometry_diagnostic_v1"
if OUT.exists():raise FileExistsError(OUT)
OUT.mkdir()
s=pd.read_csv(SOURCE/"fixed_selection_and_blank_manual_review.csv",encoding="utf-8-sig")
s=s[s.sample_id=="K6_190"].iloc[0].to_dict()
membership=pd.read_csv(J5/"global_object_membership.csv")
global_by_tile=dict(zip(zip(membership.source_tile_id,membership.source_local_object_index.astype(int)),membership.global_defect_id))
idmap,seed=original_id_map(s,global_by_tile)
x0,y0,x1,y1=(int(s[k]) for k in ("x0","y0","x1","y1"))
rawmem=np.memmap(RAW,mode="r",dtype=">u2",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
raw=np.asarray(rawmem[y0:y1,x0:x1],np.uint16)
response=np.load(RESP,mmap_mode="r")
bh31=np.asarray(response[y0:y1,x0:x1],np.uint16)
from src.detection.blackhat import black_hat_uint16
full=np.asarray(rawmem[y0-72:y1+72,x0-72:x1+72],np.uint16)
bh61=np.maximum(np.asarray(response[y0-72:y1+72,x0-72:x1+72],np.uint16),
                black_hat_uint16(full,61,"ellipse"))[72:200,72:200]
yy,xx=np.mgrid[:128,:128]
xc,yc=float(s["center_x_global"])-x0,float(s["center_y_global"])-y0
rad=np.hypot(xx-xc,yy-yc)
fine=cv2.GaussianBlur(raw.astype(np.float32),(0,0),1.3)
outer=(rad>=38)&(rad<=58)
plane=robust_outer_plane(raw.astype(float).astype(np.float32),xx-xc,yy-yc,outer)
delta=plane-fine
noisescale=1.4826*np.median(abs(delta[outer]-np.median(delta[outer])))
near=rad<=9
active={}
clist=[]
for k in (3,2,1.5,1,.75):
    threshold=max(float(k*noisescale),float(.15*np.percentile(delta[near],99)))
    good=(delta>=threshold)&(rad<=49)
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(good.astype(np.uint8),8)
    hist=np.bincount(labels[seed].ravel(),minlength=n);hist[0]=0
    picked=int(hist.argmax())
    seedcount=int(hist[picked]) if picked>0 else 0
    pickedmask=labels==picked if picked else np.zeros_like(seed)
    component_sizes=[int(stats[i,cv2.CC_STAT_AREA]) for i in range(1,n)]
    active[k]=good
    clist.append({
       "k":k,"effective_threshold_DN":round(threshold,3),
       "overall_foreground_px":int(good.sum()),
       "component_count":n-1,
       "largest_components_px":sorted(component_sizes,reverse=True)[:5],
       "source_seed_active_pixels":int((good&seed).sum()),
       "source_seed_connected_area":int(pickedmask.sum()) if seedcount else 0,
       "source_seed_component_overlap_pixels":seedcount,
       "largest_component_centroid_local":(
           centroids[1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))].round(2).tolist()
           if n>1 else None
       )})
# Other J5 original sources within main dark left side.
idstats=[]
sourceids=[z for z in np.unique(idmap) if z]
J5global=pd.read_csv(J5/"global_defects.csv")
reference=J5global.set_index("global_defect_id")
for gid in sourceids:
    m=idmap==gid
    iy,ix=np.where(m)
    idstats.append({
      "J5_ID":gid,
      "local_source_pixels":int(m.sum()),
      "full_source_area_px2":int(reference.loc[gid,"source_area_px2"]),
      "centroid_local_xy":[round(float(ix.mean()),2),round(float(iy.mean()),2)],
      "nearest_distance_to_current_seed_px":round(float(np.min(np.hypot(ix-xc,iy-yc))),2),
      "mean_RAW_DN":round(float(raw[m].mean()),2),
      "mean_BH31_DN":round(float(bh31[m].mean()),2),
      "mean_BH61_DN":round(float(bh61[m].mean()),2)
    })
# Segmented dark coherent region from original RAW (not source anchored!)
# Compute only descriptive connected components of thresholded dark pixels to
# estimate if the left side forms independently visible region.
dark_candidates=[]
for method,baseline in [
    ("global_p90",float(np.percentile(raw,90))*np.ones_like(fine)),
    ("outer_ring_p75",float(np.percentile(raw[outer],75))*np.ones_like(fine)),
    ("robust_plane",plane)
]:
    contrast=baseline-fine
    # No claim that this is physically calibrated.
    for dn in (35,55,75,95,120):
        inside=(contrast>=dn)
        n,labels,stats,center=cv2.connectedComponentsWithStats(
            inside.astype(np.uint8),8)
        comps=[]
        for k in range(1,n):
            if stats[k,cv2.CC_STAT_AREA]<15:continue
            centerx,centery=center[k]
            comps.append({
                "area":int(stats[k,cv2.CC_STAT_AREA]),
                "centroid_local":[round(float(centerx),2),round(float(centery),2)],
                "bbox_xywh":list(map(int,stats[k,:4])),
                "distance_from_J5_seed":round(float(np.hypot(centerx-xc,centery-yc)),2),
                "core_seed_pixel_overlap":int(np.count_nonzero((labels==k)&seed))
            })
        comps.sort(key=lambda z:-z["area"])
        dark_candidates.append({"model":method,"min_DN":dn,
                                "top_components":comps[:5]})
gray=np.uint8(np.clip((raw.astype(float)-np.percentile(raw,1))/
        max(1,np.percentile(raw,99.5)-np.percentile(raw,1))*255,0,255))
def pane(title,subtitle,base=None,focus_ids=False,points=False):
    im=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    if base is not None and np.any(base):
        colored=im.copy();colored[base]=(35,205,220)
        im=cv2.addWeighted(im,.75,colored,.25,0)
        cont,_=cv2.findContours(np.uint8(base),cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(im,cont,-1,(25,226,238),1)
    if focus_ids:
        for gid in sourceids:
            m=idmap==gid
            if gid==s["source_global_defect_id"]:
                continue
            im[m]=(225,40,185)
    if points:
        p=next((p for p in dark_candidates if p["model"]=="outer_ring_p75" and p["min_DN"]==75))
        if p and p["top_components"]:
            x,y=p["top_components"][0]["centroid_local"]
            cv2.drawMarker(im,(int(round(x)),int(round(y))),(45,238,60),
                           cv2.MARKER_CROSS,10,1)
    im[seed]=(0,0,245)
    img=cv2.resize(im,(350,350),interpolation=cv2.INTER_NEAREST)
    h=np.full((68,350,3),28,np.uint8)
    cv2.putText(h,title,(8,26),cv2.FONT_HERSHEY_SIMPLEX,.51,(237,237,237),1)
    cv2.putText(h,subtitle,(8,49),cv2.FONT_HERSHEY_SIMPLEX,.39,(215,215,215),1)
    return np.vstack((h,img))
pictures=[
 pane("Original RAW","RED=K6_190 J5 seed"),
 pane("All frozen J5 sources","MAGENTA=other J5 ID",focus_ids=True),
 pane("Original BH31/ H170","CYAN=BH31>170",base=bh31>=170),
 pane("Added BH61 / H170","CYAN=BH61>170",base=bh61>=170),
 pane("RAW delta K5 / 3MAD","CYAN=all dark residual",base=active[3]),
 pane("RAW delta K5 / 1.5MAD","CYAN=all dark residual",base=active[1.5]),
 pane("Raw dark px / globalp90","CYAN=contrast>75",
      base=((float(np.percentile(raw,90))-fine)>=75),points=True),
 pane("Other sources + RAW dark","CYAN=dark vs outer p75",
      base=((float(np.percentile(raw[outer],75))-fine)>=75),focus_ids=True)
]
panel=np.vstack((np.hstack(pictures[:4]),np.hstack(pictures[4:])))
save_png(OUT/"K6_190_real_raw_seed_and_dark_regions_8panels.png",panel)
np.savez_compressed(OUT/"original_diagnostic_arrays.npz",
    raw_128_u16=raw,
    source_J5_mask=seed.astype(np.uint8),
    source_J5_label_strings=idmap,
    original_BH31_u16=bh31,
    expanded_BH61_u16=bh61,
    K5_plane_f32=plane,
    K5_dark_residual_f32=delta,
    K5_active3=active[3].astype(np.uint8),
    K5_active1p5=active[1.5].astype(np.uint8),
    roi_global_xyxy=np.asarray([x0,y0,x1,y1],np.int32))
res={
 "source_sample":"K6_190","global_J5_ID":str(s["source_global_defect_id"]),
 "source_bbox_global_xyxy":[x0,y0,x1,y1],
 "source_local_center":[round(xc,4),round(yc,4)],
 "source_mask_px":int(seed.sum()),
 "BH61_pixels_greater170":int((bh61>=170).sum()),
 "K5_background_outer_annulus_p50_dn":float(np.median(raw[outer])),
 "K5_background_noise_sigma_dn":float(noisescale),
 "K5_seed_center_plane_DN":float(plane[round(yc),round(xc)]),
 "K5_seed_center_raw_DN":int(raw[round(yc),round(xc)]),
 "K5_seed_delta_median_dn":float(np.median(delta[seed])),
 "K5_seed_delta_range_dn":[float(np.min(delta[seed])),float(np.max(delta[seed]))],
 "K5_center_dark_peak99_dn":float(np.percentile(delta[near],99)),
 "K5_threshold_trials":clist,
 "other_J5_original_sources":idstats,
 "unseeded_RAW_dark_component_hypotheses":dark_candidates,
 "official_mappings_or_masks_changed":False,
 "all_unseeded_dark_components_are_exploratory_not_accepted_defects":True
}
(OUT/"K6_190_diagnostic.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
print("K6_190_SUMMARY",json.dumps({
 "local_center":res["source_local_center"],
 "seed_delta_median_dn":res["K5_seed_delta_median_dn"],
 "seed_delta_range_dn":res["K5_seed_delta_range_dn"],
 "outer_noise_sigma_dn":res["K5_background_noise_sigma_dn"],
 "threshold_trials":clist,
 "J5_ids_in_roi":idstats,
 "raw_dark_candidates_globalp90_75":next(z for z in dark_candidates if z["model"]=="global_p90" and z["min_DN"]==75),
 "raw_dark_candidates_ringp75_75":next(z for z in dark_candidates if z["model"]=="outer_ring_p75" and z["min_DN"]==75),
},ensure_ascii=False),flush=True)
print("K6_190_DIAGNOSTIC_WRITTEN",OUT,flush=True)
