"""Case03-K8-A: per-frame dynamic spectral work-band masks (26 frame1/2).

STRICT SCOPE:
- No BlackHat, H170/230, J5, K5 detection or grade modifications.
- No fixed 4/5 band assumption.
- Only geometry proposals, pixel-code segmentation and checkable overlays.
- Work/SHIELD/NONWORK masks are provisional pending human acceptance.
"""
from pathlib import Path
from dataclasses import asdict
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03k8a_band_locator import (
    BandLocatorConfig,locate_transmission_bands,rasterize_region_masks,
    polygon_for_band
)
from scripts.run_case03g_joint_noise_refinement import save_png
OUTPUT=cfg.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
SETTINGS=BandLocatorConfig()
STRIDE=8
COLORS=((30,215,125),(235,165,40),(90,140,250),(190,80,215),
        (50,220,220),(200,120,75),(105,235,235))

def write_png(p:Path,image:np.ndarray):
    ok,encoded=cv2.imencode(".png",image)
    if not ok:raise RuntimeError("PNG compression failed")
    p.write_bytes(encoded.tobytes())

def preview(raw,shape):
    sub=np.asarray(raw[::STRIDE,::STRIDE],np.float32)
    lo,hi=np.percentile(sub,[1,99.5])
    g=np.uint8(np.clip((sub-lo)/max(1.,hi-lo)*255.,0,255))
    return cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)

def render(raw,metadata,regions,labels,frame,fdir:Path):
    b=metadata["bands"];p=preview(raw,regions.shape)
    assert labels.shape==regions.shape
    scaling_w=p.shape[1]/raw.shape[1]
    scaling_h=p.shape[0]/raw.shape[0]
    colored=p.copy()
    labels_small=labels[::STRIDE,::STRIDE]
    reg_small=regions[::STRIDE,::STRIDE]
    darken=colored.copy()
    darken[reg_small==0]=(0,0,0)
    darken[reg_small==1]=(25,25,25)
    colored=cv2.addWeighted(colored,.76,darken,.24,0.)
    for item in b:
        i=int(item["band_id"])
        x=COLORS[(i-1)%len(COLORS)]
        mask=labels_small==i
        if mask.any():
            tinted=colored.copy()
            tinted[mask]=x
            colored=cv2.addWeighted(colored,.77,tinted,.23,0.)
        outer=polygon_for_band(item,raw.shape[1],SETTINGS,core=False)
        inner=polygon_for_band(item,raw.shape[1],SETTINGS,core=True)
        outer=(outer*np.array([scaling_w,scaling_h])).astype(np.int32)
        inner=(inner*np.array([scaling_w,scaling_h])).astype(np.int32)
        cv2.polylines(colored,[outer],True,(5,190,255),1,cv2.LINE_8)
        cv2.polylines(colored,[inner],True,x,1,cv2.LINE_8)
        yc=int(round(item["peak_position_y"]*scaling_h))
        cv2.putText(colored,f"B{i}: {int(item['peak_dn'])}DN",
                    (25,max(18,min(p.shape[0]-8,yc))),
                    cv2.FONT_HERSHEY_SIMPLEX,.58,x,2,cv2.LINE_AA)
    y_top=int(metadata["exterior"]["top_nonwork_end"]*scaling_h)
    y_bottom=int(metadata["exterior"]["bottom_nonwork_start"]*scaling_h)
    cv2.line(colored,(0,y_top),(p.shape[1]-1,y_top),(230,80,230),1)
    cv2.line(colored,(0,y_bottom),(p.shape[1]-1,y_bottom),(230,80,230),1)
    h,w=p.shape[:2]
    header=np.full((100,w,3),26,np.uint8)
    cv2.putText(header,
      f"CASE03-K8-A | FRAME 26({frame}) | AUTO BANDS={len(b)} (NOT FIXED)",
      (14,30),cv2.FONT_HERSHEY_SIMPLEX,.58,(240,240,240),1)
    cv2.putText(header,
      "COLORED inner = WORK; YELLOW outlines = 12px EDGE REVIEW; DARK = SHIELD/NONWORK",
      (14,59),cv2.FONT_HERSHEY_SIMPLEX,.45,(230,230,230),1)
    cv2.putText(header,
      "Masks for geometry review only: BlackHat/J5/K5 UNCHANGED. All band borders unverified.",
      (14,84),cv2.FONT_HERSHEY_SIMPLEX,.42,(224,224,224),1)
    save_png(fdir/"work_band_overlay_on_RAW.png",np.vstack((header,colored)))
    # This image is only a visualization of categorical mask, 8x reduced.
    typecolor=np.zeros((h,w,3),np.uint8)
    typecolor[reg_small==0]=(52,52,52)
    typecolor[reg_small==1]=(8,8,8)
    typecolor[reg_small==3]=(22,165,235)
    for item in b:
        typecolor[labels_small==int(item["band_id"])]=COLORS[(int(item["band_id"])-1)%len(COLORS)]
    save_png(fdir/"region_codes_preview.png",np.vstack((header,typecolor)))
    profile=metadata["profile"]
    curve=profile["row_profile_smooth_dn"]
    plot=np.full((465,w,3),26,np.uint8)
    lower=0.
    upper=max(1.0,float(np.max(curve))*1.05)
    pts=np.asarray([[int(j/max(len(curve)-1,1)*(w-1)),int(430-(float(v)-lower)/(upper-lower)*400)]
                    for j,v in enumerate(curve)],np.int32)
    cv2.polylines(plot,[pts],False,(220,220,220),2,cv2.LINE_AA)
    for item in b:
        xp=int(round(item["peak_position_y"]/raw.shape[0]*(w-1)))
        top=int(round(item["profile_top_y"]/raw.shape[0]*(w-1)))
        bottom=int(round(item["profile_bottom_y"]/raw.shape[0]*(w-1)))
        cv2.line(plot,(top,38),(top,450),(50,170,225),1)
        cv2.line(plot,(bottom,38),(bottom,450),(50,170,225),1)
        cv2.putText(plot,f"B{item['band_id']}",(max(5,xp-15),27),
                    cv2.FONT_HERSHEY_SIMPLEX,.5,COLORS[(item["band_id"]-1)%len(COLORS)],1)
    cv2.putText(plot,
       "Horizontal axis = original RAW row y | vertical = robust center-strip DN",
       (15,458),cv2.FONT_HERSHEY_SIMPLEX,.43,(215,215,215),1)
    save_png(fdir/"row_band_profile.png",plot)

def evaluate_mask(raw,loc,region,band_ids):
    bands=loc["bands"]
    h,w=raw.shape
    assert len(bands)==len(np.unique(band_ids[band_ids>0]))
    assert np.array_equal(region==2,band_ids>0)
    all_stats=[]
    for item in bands:
        i=int(item["band_id"])
        yidx,xidx=np.where(band_ids[::16,::32]==i)
        assert len(yidx)>100
        grayvalues=np.asarray(raw[yidx*16,xidx*32],np.float32)
        all_stats.append({
          "band_id":i,
          "region_x_min":item["core_x_min"],
          "region_x_max_exclusive":item["core_x_max_exclusive"],
          "raw_peak_row_y":item["peak_position_y"],
          "boundary_top_at_x0":item["top_line_y_at_x0"],
          "boundary_bottom_at_x0":item["bottom_line_y_at_x0"],
          "line_top_slope":item["top_line_slope_y_per_x"],
          "line_bottom_slope":item["bottom_line_slope_y_per_x"],
          "average_band_height_original_px":round((
           item["bottom_line_y_at_x0"]-item["top_line_y_at_x0"]+
           (item["bottom_line_slope_y_per_x"]-item["top_line_slope_y_per_x"])*w/2),1),
          "core_pixels_exact":int(np.count_nonzero(band_ids==i)),
          "RAW_median_DN_inside_work":round(float(np.median(grayvalues)),1),
          "RAW_p10_DN_inside_work":round(float(np.percentile(grayvalues,10)),1),
          "RAW_p90_DN_inside_work":round(float(np.percentile(grayvalues,90)),1),
          "RAW_deviation_mad_sigma_DN":round(1.4826*float(np.median(
                    np.abs(grayvalues-np.median(grayvalues)))),2),
          "geometry_column_samples":item["x_sample_count"],
          "edge_quality_status":"NEEDS_REVIEW" if item["validation_flags"] else "PROPOSED_CHECK_VISUALLY",
          "human_approved":"",
          "human_comments":"",
          "candidate_not_physical_wavelength_calibrated":True
        })
    return all_stats

def run_one(frame:int):
    fdir=OUTPUT/f"frame26_{frame}"
    if fdir.exists():raise FileExistsError(fdir)
    fdir.mkdir(parents=True)
    source=cfg.DATA_ROOT/f"26 ({frame}).raw"
    assert source.stat().st_size==cfg.RAW_HEIGHT*cfg.RAW_WIDTH*2
    raw=np.memmap(source,mode="r",dtype=">u2",
                 shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    metadata=locate_transmission_bands(raw,SETTINGS)
    if not metadata["bands"]:raise RuntimeError(f"No bands for frame{frame}: do not produce fake masks")
    region,ids=rasterize_region_masks(raw.shape,metadata["bands"],
                                     metadata["exterior"],SETTINGS)
    # Explicitly save original resolution uint8 categorical masks, lossless.
    write_png(fdir/"region_type_fullres.png",region)
    write_png(fdir/"band_id_fullres.png",ids)
    for band in metadata["bands"]:
        i=int(band["band_id"])
        write_png(fdir/f"band_{i:02d}_core_fullres.png",np.uint8(ids==i)*255)
    records=evaluate_mask(raw,metadata,region,ids)
    pd.DataFrame(records).to_csv(fdir/"band_geometry_and_DN_statistics.csv",
                                 index=False,encoding="utf-8-sig")
    render(raw,metadata,region,ids,frame,fdir)
    profile=metadata.pop("profile")
    np.savez_compressed(fdir/"row_gray_projection_data.npz",
       sampled_row_median_dn=profile["row_median_dn"],
       smoothed_row_profile_dn=profile["row_profile_smooth_dn"],
       sampled_row_p10_dn=profile["row_p10_dn"],
       sampled_row_p90_dn=profile["row_p90_dn"],
       y_stride_px=np.int16(profile["profile_stride_px"]))
    state={
      "stage":"CASE03K8A_DYNAMIC_WORKBAND_LOCATION",
      "frame":frame,
      "source_raw":str(source),
      "raw_source_read_only":True,
      "image_size_h_w":[cfg.RAW_HEIGHT,cfg.RAW_WIDTH],
      "bands_detected_automatic":len(metadata["bands"]),
      "band_count_hardcoded":False,
      "band_count_manual_expected":None,
      "band_count_human_approved":False,
      "bands":metadata["bands"],
      "rejected_peaks_not_treated_as_bands":metadata["rejected_candidates"],
      "outer_non_work":metadata["exterior"],
      "mask_codes":{"0":"NON_WORK","1":"SHIELD","2":"WORK_CORE",
                    "3":"BOUNDARY_REVIEW"},
      "mask_scope":"Frame-specific original resolution",
      "disposition":"GEOMETRY_ONLY_MANUAL_CONFIRMATION_REQUIRED",
      "all_J5_K5_blackhat_thresholds_unchanged":True,
      "segmentation_purpose":"FOR_K8_B_AND_LATER_PENDING_APPROVAL",
      "frame_specific_mask_not_copied_from_other_frame":True,
      "parameters":asdict(SETTINGS),
      "source_statistics":records
    }
    (fdir/"audit.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),
                                   encoding="utf-8")
    # Verify actual written mask decodes with no alteration:
    for name,original in [("region_type_fullres.png",region),("band_id_fullres.png",ids)]:
        p=fdir/name
        decoded=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
        assert decoded is not None and decoded.shape==original.shape
        assert np.array_equal(decoded,original)
    print("K8A_FRAME_SUCCESS",json.dumps({
       "frame":frame,"bands":len(metadata["bands"]),
       "band_peaks_y":[b["peak_position_y"] for b in metadata["bands"]],
       "band_core_rows_est":[[b["profile_top_y"],b["profile_bottom_y"]] for b in metadata["bands"]],
       "source_medians_DN":[r["RAW_median_DN_inside_work"] for r in records],
       "outer_nonwork_y":[state["outer_non_work"]["top_nonwork_end"],
                          state["outer_non_work"]["bottom_nonwork_start"]],
       "region_class_counts":{str(int(k)):int(v) for k,v in zip(*np.unique(region,return_counts=True))},
       "no_J5_mutation":True
    },ensure_ascii=False),flush=True)
    return state

def run():
    if OUTPUT.exists():raise FileExistsError("K8A output exists; do not overwrite")
    OUTPUT.mkdir(parents=True)
    reports=[]
    for frame in (1,2):
        reports.append(run_one(frame))
    summary={
      "stage":"CASE03_K8A_COMPLETE_PENDING_HUMAN_VISUAL_INSPECTION",
      "frames":[v["frame"] for v in reports],
      "band_counts":[v["bands_detected_automatic"] for v in reports],
      "band_count_not_fixed":True,
      "first_frame_mask_not_reused":True,
      "all_raw_files_read_only":True,
      "no_existing_detection_config_or_data_modified":True,
      "output_ROOT":str(OUTPUT)
    }
    (OUTPUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                                       encoding="utf-8")
    return summary
if __name__=="__main__":run()
