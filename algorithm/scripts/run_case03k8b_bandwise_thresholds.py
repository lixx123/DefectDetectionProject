"""Case03-K8-B: per-band BlackHat and threshold experiments on 26 two frames.

APPROVED K8A geometries, original RAW and exact full-frame fused BlackHat.
No masking before BlackHat. Two transparent H-threshold *trial branches*:
 A fixed 170/230 within band CORE
 B robust z transfer from strongest workband to other workbands
These binary candidates are NOT full J5-G/H detection; no physical true-defect
statistic may be inferred without blinded pixel annotations.
"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import sys,json,cv2
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.blackhat import black_hat_uint16
from src.detection.case03k8b_perband_trial import (
    PerBandTrial,stats_median_mad,threshold_params,hysteresis_on_work)
from scripts.run_case03g_joint_noise_refinement import save_png

K8A=cfg.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
OUT=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
PARAMS=PerBandTrial()
KERNELS=(3,5,9,15,31)
FUSED={
 1:cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
 2:cfg.OUTPUT_ROOT/"case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy"
}
J5={
 1:cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_1_global_j5_v1",
 2:cfg.OUTPUT_ROOT/"case03j5_global/run_20261012_frame26_2_J5_independent_v1"
}
PALETTE=[(60,216,110),(230,160,65),(55,185,235),(185,115,225),
         (170,210,65),(210,170,190)]


def load_gray_png(path):
    v=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if v is None or v.ndim!=2:raise ValueError("Invalid original segmentation mask "+str(path))
    return v


def sample_band_stats(frame,rawmem,fused,ids,region,meta,config):
    step=config.robust_sample_stride_px
    sampled_ids=ids[::step,::step]
    response=np.asarray(fused[::step,::step],np.uint16)
    raw=np.asarray(rawmem[::step,::step],np.float32)
    stats={}
    for obj in meta["bands"]:
        bid=int(obj["band_id"])
        mask=sampled_ids==bid
        assert np.count_nonzero(mask)>3000
        out=stats_median_mad(response[mask],config.min_sigma_dn)
        out["workband_raw_median_dn"]=round(float(np.median(raw[mask])),4)
        out["band_id"]=bid
        out["frame"]=frame
        out["band_source_core_validated"]=True
        stats[bid]=out
    # Reference is brightest workband, selected WITHOUT labels and independent of
    # which band numbering 4 or 5. Do not silently use nonwork bright plateaus.
    reference=max(stats,key=lambda k:stats[k]["workband_raw_median_dn"])
    thresholds=threshold_params(stats,config,reference)
    return thresholds,reference


def region_of_interest(band,shape,cfg):
    height,width=shape
    ys=[
        band["top_line_y_at_x0"],
        band["top_line_y_at_x0"]+band["top_line_slope_y_per_x"]*(width-1),
        band["bottom_line_y_at_x0"],
        band["bottom_line_y_at_x0"]+band["bottom_line_slope_y_per_x"]*(width-1)
    ]
    y0=max(0,int(np.floor(min(ys)))-10)
    y1=min(height,int(np.ceil(max(ys)))+11)
    assert y1-y0>200
    return y0,y1


def recompute_unmasked_band_raw(rawmem,y0,y1):
    """Recompute exact original BlackHat with sufficient halo in RAW space."""
    h,w=rawmem.shape
    halo=PARAMS.blackhat_halo_px
    start=max(0,y0-halo);end=min(h,y1+halo)
    local=np.asarray(rawmem[start:end,:],np.uint16)
    merged=np.zeros(local.shape,np.uint16)
    for k in KERNELS:
        temp=black_hat_uint16(local,k,"ellipse")
        np.maximum(merged,temp,out=merged)
    return merged[y0-start:y1-start,:]


def view_background(raw,limit_width=1420):
    grid=np.asarray(raw[::8,::8],np.float32)
    lo,hi=np.percentile(grid,[1,99.5])
    norm=np.uint8(np.clip((grid-lo)/max(1.,hi-lo)*255.,0,255))
    return cv2.cvtColor(norm,cv2.COLOR_GRAY2BGR)


def downsample_occupancy(mask,shape):
    """Max in approximate preview cell instead of skipping tiny candidates."""
    b=np.uint8(mask)*255
    reduced=cv2.resize(b,(shape[1],shape[0]),interpolation=cv2.INTER_AREA)
    return reduced>0


def make_overview(raw,work_id_map,frame,baseline,adaptive,out:Path,rows):
    bg=view_background(raw)
    mask=work_id_map[::8,::8]
    # User sees same coordinates in all three maps; whole image downsample 1:8.
    def visualize(which):
        im=bg.copy()
        allowed=mask>0
        dark=im.copy();dark[~allowed]=(25,25,25)
        im=cv2.addWeighted(im,.75,dark,.25,0)
        reduced=downsample_occupancy(which,im.shape)
        im[reduced & allowed]=(25,220,235)
        for b in rows:
            bid=int(b["band_id"])
            y=int(round(float(b["band_peak_row_y"])/8.))
            cv2.putText(im,f"B{bid}",(8,y),
                        cv2.FONT_HERSHEY_SIMPLEX,.55,PALETTE[(bid-1)%len(PALETTE)],1)
        return im
    a=visualize(baseline);b=visualize(adaptive)
    c=visualize(adaptive & ~baseline)
    header=np.full((86,bg.shape[1],3),28,np.uint8)
    def titled(img,name,subtitle):
        top=header.copy()
        cv2.putText(top,name,(12,30),cv2.FONT_HERSHEY_SIMPLEX,.65,(245,245,245),1)
        cv2.putText(top,subtitle,(12,55),cv2.FONT_HERSHEY_SIMPLEX,.42,(222,222,222),1)
        cv2.putText(top,"Rendered occupancy NOT measured defect size",(12,77),
                    cv2.FONT_HERSHEY_SIMPLEX,.38,(215,215,215),1)
        return np.vstack((top,img))
    save_png(out/"A_fixed_170_230_workband_overview.png",
             titled(a,f"FRAME{frame} A: FIXED 170/230","WORK bands only; unchanged fused BlackHat"))
    save_png(out/"B_robustZ_perband_workband_overview.png",
             titled(b,f"FRAME{frame} B: PER-BAND ROBUST Z","Experimental thresholds; NOT J5/confirmed defects"))
    save_png(out/"B_new_vs_A_fixed_overview.png",
             titled(c,f"FRAME{frame} B minus A: NEW pixel proposals","More proposals can be noise. Examine RAW strips!"))


def band_side_by_side(rawmem,bh,core,base,adapt,bandnum,thresholds,outfile):
    yraw=np.asarray(rawmem,np.uint16)
    w,h=yraw.shape[1],yraw.shape[0]
    minv,maxv=np.percentile(yraw[::3,::8],[1,99.5])
    norm=np.uint8(np.clip((yraw.astype(np.float32)-minv)/max(1.,maxv-minv)*255.,0,255))
    shape=(w//6,h//6)
    if shape[0]<1 or shape[1]<1:raise ValueError("invalid thumbnail")
    raw=cv2.cvtColor(cv2.resize(norm,shape,interpolation=cv2.INTER_AREA),cv2.COLOR_GRAY2BGR)
    bh8=np.uint8(np.clip(bh.astype(np.float32)/max(1.,np.percentile(bh[core][::50],99.5))*255,0,255))
    norm_bh=cv2.cvtColor(cv2.resize(bh8,shape,interpolation=cv2.INTER_AREA),cv2.COLOR_GRAY2BGR)
    over=[]
    for title,im,which in [
        ("RAW",raw,None),("BlackHat DN",norm_bh,None),
        ("A FIXED",raw,base),("B ADAPTIVE",raw,adapt)]:
        p=im.copy()
        if which is not None:
            overlay=downsample_occupancy(which,p.shape)
            p[overlay]=(40,230,245)
        bar=np.full((74,p.shape[1],3),27,np.uint8)
        cv2.putText(bar,title,(8,22),cv2.FONT_HERSHEY_SIMPLEX,.54,(238,238,238),1)
        cv2.putText(bar,("fixed 170/230 DN" if title=="A FIXED" else
                         f"trial L/H {thresholds[0]:.1f}/{thresholds[1]:.1f} DN" if title=="B ADAPTIVE" else
                         f"BAND {bandnum}  original RAW/BH"),
                    (8,50),cv2.FONT_HERSHEY_SIMPLEX,.4,(220,220,220),1)
        over.append(np.vstack((bar,p)))
    save_png(outfile,np.hstack(over))


def object_membership(j5dir,ids,regions,dest:Path):
    objs=pd.read_csv(j5dir/"global_defects.csv",encoding="utf-8-sig")
    Y=np.clip(objs.center_y_global.round().astype(int),0,ids.shape[0]-1)
    X=np.clip(objs.center_x_global.round().astype(int),0,ids.shape[1]-1)
    objs["K8A_region_code_by_original_J5_center"]=regions[Y,X]
    objs["K8A_workband_id_by_original_J5_center"]=ids[Y,X]
    objs["K8A_assignment_method"]="J5_center_lookup_NOT_object_source_overlap"
    objs["K8A_band_assignment_is_not_confirmed_truth"]=True
    objs.to_csv(dest/"original_J5_object_center_workband_classification.csv",
                encoding="utf-8-sig",index=False)
    counts=[]
    for key,group in objs.groupby(["K8A_region_code_by_original_J5_center",
                                   "K8A_workband_id_by_original_J5_center",
                                   "grade"],sort=True):
        counts.append({"region_code":int(key[0]),"band_id":int(key[1]),
                       "original_J5_grade":key[2],
                       "original_J5_object_count":len(group)})
    pd.DataFrame(counts).to_csv(dest/"frozen_J5_distribution_by_functional_region.csv",
                                 encoding="utf-8-sig",index=False)
    return objs


def run_frame(frame):
    output=OUT/f"frame26_{frame}"
    if output.exists():raise FileExistsError("Refuse overwrite "+str(output))
    output.mkdir(parents=True)
    meta=json.loads((K8A/f"frame26_{frame}/audit.json").read_text(encoding="utf-8"))
    if not meta.get("band_count_hardcoded") is False:raise AssertionError("fixed band mask")
    raw=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    fused=np.load(FUSED[frame],mmap_mode="r",allow_pickle=False)
    ids=load_gray_png(K8A/f"frame26_{frame}/band_id_fullres.png")
    regions=load_gray_png(K8A/f"frame26_{frame}/region_type_fullres.png")
    assert ids.shape==regions.shape==raw.shape==fused.shape
    assert np.array_equal(ids>0,regions==2)
    thresholds,anchor=sample_band_stats(frame,raw,fused,ids,regions,meta,PARAMS)
    objects=object_membership(J5[frame],ids,regions,output)
    global_A=np.zeros(raw.shape,bool)
    global_B=np.zeros(raw.shape,bool)
    records=[]
    roi_manifest=[]
    for band in meta["bands"]:
        bid=int(band["band_id"])
        y0,y1=region_of_interest(band,raw.shape,PARAMS)
        local_core=(ids[y0:y1]==bid)
        img=np.asarray(fused[y0:y1],np.uint16)
        local_recomputed=recompute_unmasked_band_raw(raw,y0,y1)
        assert local_recomputed.shape==img.shape
        ncompare=int(np.count_nonzero(local_core))
        if ncompare==0:raise RuntimeError("No core in candidate band")
        delta=np.abs(local_recomputed[local_core].astype(np.int32)-img[local_core].astype(np.int32))
        maxdiff=int(delta.max())
        assert maxdiff==0,("per-band unmasked BH differs from global BH",frame,bid,maxdiff)
        lo,hi=PARAMS.original_low_dn,PARAMS.original_high_dn
        altlo,althi=thresholds[bid]["band_trial_low_dn"],thresholds[bid]["band_trial_high_dn"]
        a,ma=hysteresis_on_work(img,local_core,lo,hi)
        b,mb=hysteresis_on_work(img,local_core,altlo,althi)
        assert np.all(a<=local_core) and np.all(b<=local_core)
        assert np.array_equal((b&a),a) if (altlo<=lo and althi<=hi) else True
        global_A[y0:y1,:]|=a
        global_B[y0:y1,:]|=b
        # Bitexact 8-bit source mask in ROI crop; full-res global XY offsets stored separately.
        save_png(output/f"band_{bid:02d}_A_hysteresis_mask_cropped.png",a.astype(np.uint8)*255)
        save_png(output/f"band_{bid:02d}_B_hysteresis_mask_cropped.png",b.astype(np.uint8)*255)
        nA=int(a.sum());nB=int(b.sum())
        nAdd=int(np.count_nonzero(b&~a))
        nLost=int(np.count_nonzero(a&~b))
        rec={
          "frame":frame,"band_id":bid,"band_peak_row_y":band["peak_position_y"],
          "band_original_dn_median":thresholds[bid]["workband_raw_median_dn"],
          "original_blackhat_low_high_DN":"170/230",
          **thresholds[bid],
          "band_source_core_pixels":ncompare,
          "same_original_blackhat_max_diff_dn":maxdiff,
          "band_crop_y0_inclusive":y0,
          "band_crop_y1_exclusive":y1,
          "original_J5_small_centers_in_band":int(((objects.K8A_workband_id_by_original_J5_center==bid)&(objects.grade=="SMALL")).sum()),
          "original_J5_medium_centers_in_band":int(((objects.K8A_workband_id_by_original_J5_center==bid)&(objects.grade=="MEDIUM")).sum()),
          "original_J5_large_centers_in_band":int(((objects.K8A_workband_id_by_original_J5_center==bid)&(objects.grade=="LARGE")).sum()),
          "A_fixed_hysteresis_candidate_pixels":nA,
          "A_fixed_hysteresis_candidate_components":ma["hysteresis_candidate_components"],
          "A_fixed_components_ge3":ma["hysteresis_candidate_ge3"],
          "B_adaptive_hysteresis_candidate_pixels":nB,
          "B_adaptive_hysteresis_candidate_components":mb["hysteresis_candidate_components"],
          "B_adaptive_components_ge3":mb["hysteresis_candidate_ge3"],
          "B_added_vs_A_candidate_pixels":nAdd,
          "B_lost_vs_A_candidate_pixels":nLost,
          "A_total_low_threshold_pixels":ma["low_threshold_px"],
          "B_total_low_threshold_pixels":mb["low_threshold_px"],
          "A_total_high_seed_pixels":ma["high_seed_pixels"],
          "B_total_high_seed_pixels":mb["high_seed_pixels"],
          "full_J5_classification_was_rerun":False,
          "change_in_candidate_count_is_not_measurement_of_true_defect_performance":True
        }
        records.append(rec)
        roi_manifest.append({"band_id":bid,"ROI_global_xyxy":[0,y0,raw.shape[1],y1],
                     "masks_file_names":[f"band_{bid:02d}_A_hysteresis_mask_cropped.png",
                                         f"band_{bid:02d}_B_hysteresis_mask_cropped.png"],
                     "mask_value_255":"candidate detected (not validated real defect)",
                     "mask_value_0":"not selected in this trial"})
        band_side_by_side(raw[y0:y1],img,local_core,a,b,bid,
              (altlo,althi),output/f"band_{bid:02d}_4panel_RAW_BH_A_B.png")
        print("K8B_BAND_RESULT",frame,bid,"REF",anchor,
              "A pixels/objects",nA,ma["hysteresis_candidate_components"],
              "B pixels/objects",nB,mb["hysteresis_candidate_components"],
              "adaptive thresholds",altlo,althi,flush=True)
    stats=pd.DataFrame(records)
    stats.to_csv(output/"perband_comparison_and_thresholds.csv",
                 encoding="utf-8-sig",index=False)
    make_overview(raw,ids,frame,global_A,global_B,output,records)
    allcounts={
       "0_NONWORK_center_J5":int((objects.K8A_region_code_by_original_J5_center==0).sum()),
       "1_SHIELD_center_J5":int((objects.K8A_region_code_by_original_J5_center==1).sum()),
       "2_WORK_CORE_center_J5":int((objects.K8A_region_code_by_original_J5_center==2).sum()),
       "3_EDGE_REVIEW_center_J5":int((objects.K8A_region_code_by_original_J5_center==3).sum())
    }
    assert sum(allcounts.values())==len(objects)
    assert not np.any(global_A&~(ids>0)) and not np.any(global_B&~(ids>0))
    result={
      "stage":"CASE03K8B_READ_ONLY_BAND_THRESHOLD_COMPARISON",
      "source_frame":f"26 ({frame}).raw",
      "bands_detected_from_K8A":len(meta["bands"]),
      "bands_count_assumed_fixed":False,
      "anchor_band_id":anchor,
      "anchor_selection":"max detector RAW median inside confirmed work bands, no labels",
      "recomputed_original_BlackHat_maxdiff_DN":int(stats.same_original_blackhat_max_diff_dn.max()),
      "A_fixed_hysteresis_candidate_pixels":int(stats.A_fixed_hysteresis_candidate_pixels.sum()),
      "A_fixed_hysteresis_components":int(stats.A_fixed_hysteresis_candidate_components.sum()),
      "B_bandwise_adaptive_candidate_pixels":int(stats.B_adaptive_hysteresis_candidate_pixels.sum()),
      "B_bandwise_adaptive_candidate_components":int(stats.B_adaptive_hysteresis_candidate_components.sum()),
      "new_B_minus_A_candidate_pixels":int(stats.B_added_vs_A_candidate_pixels.sum()),
      "original_J5_candidates_all_regions":len(objects),
      "original_J5_center_based_region_counts":allcounts,
      "parameters":asdict(PARAMS),
      "ROI_crops":roi_manifest,
      "both_mask_series_same_workband_regions":True,
      "masks_before_BlackHat_processing_applied":False,
      "original_J5_H170_230_K5_and_grades_modified":False,
      "provisional_thresholds_unvalidated_by_annotated_truth":True,
      "H170_230_trial_cannot_replace_full_J5_GH_association":True
    }
    (output/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8B_FRAME_FINISHED",json.dumps(result,ensure_ascii=False),flush=True)
    return result


def run():
    if OUT.exists():raise FileExistsError("refuse overwrite")
    OUT.mkdir(parents=True)
    result=[]
    for f in (1,2):result.append(run_frame(f))
    summ={
      "stage":"K8B_TWO_FRAME_EXPERIMENT_FINISHED_REVIEW_REQUIRED",
      "frames":[1,2],
      "geometry_approved_by_user_in_conversation":True,
      "perband_production_thresholds_not_approved":True,
      "source_J5_not_modified":True,
      "no_true_defect_precision_or_recall_measurable":True,
      "results":result
    }
    (OUT/"summary.json").write_text(json.dumps(summ,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8B_DONE",flush=True)

if __name__=="__main__":run()
