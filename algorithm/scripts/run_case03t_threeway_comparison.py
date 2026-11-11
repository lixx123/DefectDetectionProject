"""Case03-T1: fixed/global/local adaptive H on 26 (2).raw, same E2-H5/F/G/H postprocessor.

Scope: 9 previously selected 256px windows + 9 deterministic spatial
control windows. The coordinates are fixed before inspecting frame2 and
are NOT independent frame2 defect annotations. Report candidate counts
and coverage, not recall/FPR without frame2 ground truth.
"""
from __future__ import annotations
import argparse,json,sys,time
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03t_adaptive_hysteresis import (
    AdaptiveConfig,global_thresholds,local_grids,local_window_thresholds,
    hysteresis_window
)
# Experimental adapter is separate; the production Case03E2 API stays frozen.
from src.detection.case03t_hseeded_variable import (
    detect_window_H_seeded,HSeedConfig
)
from src.detection.case03e2_multicandidate import FusionConfig
from src.detection.candidate_local_noise import (
    NoiseTrialConfig,local_raw_statistics,classify_candidate
)
from src.detection.case03g_joint_gate import JointGateConfig,decide_gate,build_joint_maps
from src.detection.case03h_background_texture import TextureTrialConfig,extend_gate
from scripts.run_case03g_joint_noise_refinement import (
    gray,panel,save_png,crop_bounds,TARGETS
)

RESPONSE_RUN=ROOT/"outputs/case03t_threshold_pilot/run_20261010_sample26_frame2_response_v1"
E2=ROOT/"outputs/case03e2/run_20261010_H_seeded_bounded_consensus_v5"
STRATEGIES=("fixed170_230","global_mad","local_mad")


def policies():
    refine=FusionConfig(
        source_min_region_area_px=cfg.CASE03E2_MIN_LOCAL_COMPONENT_AREA_PX,
        background_high_floor_dn=cfg.CASE03E2_GAUSSIAN_MORPH_HIGH_FLOOR_DN,
        background_low_floor_dn=cfg.CASE03E2_GAUSSIAN_MORPH_LOW_FLOOR_DN,
        high_noise_k=cfg.CASE03E2_GAUSSIAN_MORPH_HIGH_K_MAD,
        low_noise_k=cfg.CASE03E2_GAUSSIAN_MORPH_LOW_K_MAD,
        max_mask_area_fraction=cfg.CASE03E2_MAX_LOCAL_REGION_AREA_FRACTION,
        keep_H_if_area_at_least_px=cfg.CASE03E2_KEEP_H_REGION_MIN_AREA_PX,
        keep_H_if_peak_at_least_dn=cfg.CASE03E2_KEEP_H_REGION_STRONG_PEAK_DN,
        H_only_provisional_min_area_px=cfg.CASE03E2_H_ONLY_PROVISIONAL_AREA_MIN_PX,
        H_only_provisional_peak_DN=cfg.CASE03E2_H_ONLY_PROVISIONAL_PEAK_DN,
    )
    seed=HSeedConfig(
        max_extension_radius_px=cfg.CASE03E2_HSEED_MAX_EXTENSION_RADIUS_PX,
        min_h_pixels_for_refinement=cfg.CASE03E2_HSEED_MIN_H_PIXELS_FOR_REFINEMENT,
        max_extended_to_H_area_ratio=cfg.CASE03E2_HSEED_MAX_AREA_RATIO,
        max_source_component_window_fraction=cfg.CASE03E2_HSEED_MAX_RAW_COMPONENT_FRACTION,
        enable_bounded_extension_fallback=cfg.CASE03E2_HSEED_BOUNDED_FALLBACK_ENABLED,
        bounded_fallback_radius_px=cfg.CASE03E2_HSEED_BOUNDED_RADIUS_PX,
        bounded_fallback_max_area_ratio=cfg.CASE03E2_HSEED_BOUNDED_MAX_AREA_RATIO,
    )
    f=NoiseTrialConfig(
        small_area_max_px=cfg.CASE03F_SMALL_AREA_MAX_PX,
        min_relative_contrast=cfg.CASE03F_MIN_RELATIVE_CONTRAST,
        min_significance_z=cfg.CASE03F_MIN_SIGNIFICANCE_Z,
        ring_outer_radius_px=cfg.CASE03F_RING_OUTER_RADIUS_PX,
        ring_inner_guard_px=cfg.CASE03F_RING_INNER_GUARD_PX,
        ring_min_count=cfg.CASE03F_RING_MIN_COUNT,
        sigma_floor_dn=cfg.CASE03F_SIGMA_FLOOR_DN,
        protect_large_nearby_radius_px=cfg.CASE03F_PROTECT_LARGE_NEARBY_RADIUS_PX,
        protect_large_area_px=cfg.CASE03F_PROTECT_LARGE_AREA_PX,
    )
    g=JointGateConfig(
        protect_support_area_min_px=cfg.CASE03G_PROTECT_STRUCTURE_MIN_AREA_PX,
        protect_support_radius_px=cfg.CASE03G_PROTECT_STRUCTURE_RADIUS_PX,
        protect_any_existing_refinement=cfg.CASE03G_PROTECT_EXISTING_REFINEMENT,
    )
    h=TextureTrialConfig(
        medium_min_area_px=cfg.CASE03H_MEDIUM_MIN_AREA_PX,
        medium_max_area_px=cfg.CASE03H_MEDIUM_MAX_AREA_PX,
        min_relative_contrast=cfg.CASE03H_MIN_RELATIVE_CONTRAST,
        min_significance_z=cfg.CASE03H_MIN_SIGNIFICANCE_Z,
        protect_peak_dn=cfg.CASE03H_PROTECT_BLACKHAT_PEAK_DN,
        protect_dog_median_dn=cfg.CASE03H_PROTECT_DOG_MEDIAN_DN,
        dog_small_sigma_px=cfg.CASE03H_DOG_SMALL_SIGMA_PX,
        dog_large_sigma_px=cfg.CASE03H_DOG_LARGE_SIGMA_PX,
        protect_big_area_px=cfg.CASE03H_PROTECT_BIG_AREA_PX,
        protect_big_radius_px=cfg.CASE03H_PROTECT_BIG_RADIUS_PX,
        protect_stroke_min_length_px=cfg.CASE03H_PROTECT_STROKE_MIN_LENGTH_PX,
        protect_stroke_aspect=cfg.CASE03H_PROTECT_STROKE_ASPECT,
    )
    return refine,seed,f,g,h


def windows(full_shape:tuple[int,int])->tuple[list[dict],list[dict]]:
    historical=pd.read_csv(E2/"window_summary.csv")
    rows=[]
    for r in historical.itertuples(index=False):
        rect=json.loads(r.roi_xyxy)
        rows.append({"name":r.window_id,"scope":"frame1_historical_9_windows",
                     "rect":rect,"source":"pre-existing frozen frame1 ROI"})
    H,W=full_shape
    controls=[]
    # Deterministic 3x3 regular grid unrelated to annotations.
    for iy,fy in enumerate((.17,.5,.83),1):
        for ix,fx in enumerate((.17,.5,.83),1):
            x=int(round((W-256)*fx))
            y=int(round((H-256)*fy))
            controls.append({"name":f"CTRL_{iy}{ix}",
                "scope":"frame2_spatial_grid_controls",
                "rect":[x,y,x+256,y+256],
                "source":"fixed fractional grid no annotation"})
    if len(rows)!=9 or len(controls)!=9:raise AssertionError("wrong window count")
    return rows,controls


def process_one(raw:np.ndarray,response:np.ndarray,
                low:np.ndarray|float,high:np.ndarray|float,
                refine:FusionConfig,seed:HSeedConfig,
                f:NoiseTrialConfig,g:JointGateConfig,h:TextureTrialConfig
                )->dict:
    H,S,original_seeds=hysteresis_window(response,low,high)
    n,labels,stats,_=cv2.connectedComponentsWithStats(H.astype(np.uint8),8)
    if n-1>seed.max_output_regions_per_window:
        raise RuntimeError("candidate overflow; do not truncate")
    # Historical Case03-E2 bounded Gaussian22/Closing61 refinement is reused
    # here and recomputed on the current core+halo RAW window from its own H seeds.
    kw={"cfg":refine,"policy":seed}
    if isinstance(low,np.ndarray):
        kw.update(h_low_threshold_map=low,h_high_threshold_map=high)
    else:
        kw.update(h_low_threshold_dn=float(low),h_high_threshold_dn=float(high))
    detected=detect_window_H_seeded(raw,H,S,response,**kw)
    objects=detected["objects"]
    if len(objects)!=n-1:
        raise AssertionError("missing H object under shared refinement")
    fused_labels=np.zeros_like(labels,dtype=np.int32)
    for j,obj in enumerate(objects,1):
        if np.any(fused_labels[obj.mask]!=0):
            raise AssertionError("refined regions overlap")
        fused_labels[obj.mask]=j
    if np.any(H&(labels!=fused_labels)):
        raise AssertionError("refined mask lost H pixel ownership")
    large_ids=np.flatnonzero(stats[:,cv2.CC_STAT_AREA]>=f.protect_large_area_px)
    large_ids=large_ids[large_ids>0]
    rr=f.protect_large_nearby_radius_px
    near=cv2.dilate(np.isin(labels,large_ids).astype(np.uint8),
                    np.ones((2*rr+1,2*rr+1),np.uint8)).astype(bool)
    old_status=[];features=[]
    # First-stage local RAW median and MAD decisions are recomputed from the
    # current core+halo RAW window; no frame-specific manual label enters them.
    for j in range(1,n):
        x,y,bw,bh,area=(int(v) for v in stats[j,:5])
        hmask=labels==j
        fm=local_raw_statistics(raw,H,hmask,(x,y,bw,bh),f)
        protected=bool(np.any(near[hmask]))
        status,_=classify_candidate(area,bw,bh,fm,protected,f)
        fm.update(area_px=area,
                  fused_blackhat_peak_dn=detected["H_audit"][j-1]["fused_blackhat_peak_dn"])
        old_status.append(status);features.append(fm)
    sources=[tuple(o.sources) for o in objects]
    gstatus,greasons=decide_gate(labels,stats,old_status,sources,g)
    afloat=raw.astype(np.float32)
    dog=(cv2.GaussianBlur(afloat,(0,0),h.dog_large_sigma_px)-
         cv2.GaussianBlur(afloat,(0,0),h.dog_small_sigma_px))
    for j in range(1,n):
        features[j-1]["dog_median_dn"]=float(np.median(dog[labels==j]))
    hstatus,hreasons=extend_gate(labels,stats,gstatus,greasons,features,h)
    maps=build_joint_maps(labels,fused_labels,hstatus)
    if not np.array_equal(maps["h_original"],H):
        raise AssertionError("H original incorrectly altered")
    # n=1 means no candidate (valid result).
    return {
        "candidate_count":int(n-1),
        "H_pixel_count":int(H.sum()),
        "seed_count":int(original_seeds),
        "suggest_hidden":hstatus.count("hide_suggestion"),
        "protected_review":hstatus.count("protected_review"),
        "display_H_pixels":int(maps["h_kept_display"].sum()),
        "display_refined_pixels":int(maps["fused_joint_display"].sum()),
        "refined_objects":sum(not o.H_only for o in objects),
        "maps":maps,
    }


def make_panel(raw:np.ndarray,maps:dict[str,np.ndarray],
               heading:str,step:int=1)->tuple[np.ndarray,np.ndarray]:
    candidate=panel(raw,[(maps["h_original"],(70,215,45))],
                    heading+" / H",zoom=step)
    final=panel(raw,[(maps["fused_joint_display"],(70,215,45)),
                     (maps["h_hidden_suggestion"],(30,130,235))],
                heading+" / H+G+C+gate",zoom=step)
    return candidate,final


def run(run_id:str)->Path:
    cfgT=AdaptiveConfig(
        grid_size_px=cfg.CASE03T_GRID_SIZE_PX,
        sample_stride_px=cfg.CASE03T_GRID_SAMPLE_STRIDE_PX,
        global_sample_stride_px=cfg.CASE03T_GLOBAL_SAMPLE_STRIDE_PX,
        background_trim_percentile=cfg.CASE03T_BACKGROUND_TRIM_PERCENTILE,
        k_low=cfg.CASE03T_LOW_K_MAD,
        k_high=cfg.CASE03T_HIGH_K_MAD,
        noise_sigma_floor_dn=cfg.CASE03T_NOISE_FLOOR_DN,
        low_floor_dn=cfg.CASE03T_LOW_FLOOR_DN,
        high_floor_dn=cfg.CASE03T_HIGH_FLOOR_DN,
        min_hysteresis_gap_dn=cfg.CASE03T_MIN_HYSTERESIS_GAP_DN
    )
    dest=cfg.OUTPUT_ROOT/"case03t_threshold_pilot"/run_id
    if dest.exists():raise FileExistsError("refusing to overwrite: "+str(dest))
    for s in ("figures_historical9","figures_controls9","figures_10_frame1_replay","masks"):
        (dest/s).mkdir(parents=True,exist_ok=False)
    resp=np.load(RESPONSE_RUN/"fused_blackhat_26_frame2_uint16.npy",mmap_mode="r")
    if resp.shape!=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH) or resp.dtype!=np.uint16:
        raise ValueError("wrong fused response geometry")
    rawmem=np.memmap(cfg.DATA_ROOT/"26 (2).raw",mode="r",dtype=">u2",
                     shape=resp.shape)
    global_stat=global_thresholds(resp,cfgT)
    med,sig,cap,audit=local_grids(resp,cfgT)
    pd.DataFrame(audit).to_csv(dest/"local_grid_statistics.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame([global_stat]).to_csv(dest/"global_statistics.csv",index=False,encoding="utf-8-sig")
    named,ncontrols=windows(resp.shape)
    refine,seed,f,g,h=policies()
    entries=[];measure=[];overview=[]
    tic=time.perf_counter()
    for meta in named+ncontrols:
        x0,y0,x1,y1=rect=meta["rect"]
        R=np.asarray(resp[y0:y1,x0:x1],dtype=np.uint16)
        raw=np.asarray(rawmem[y0:y1,x0:x1],dtype=np.uint16)
        LL,HH=local_window_thresholds(med,sig,rect,resp.shape,cfgT)
        threshold_data={
            "fixed170_230":(170.,230.),
            "global_mad":(global_stat["low_dn"],global_stat["high_dn"]),
            "local_mad":(LL,HH)
        }
        maps_by_method={}; output_panels=[]
        for method in STRATEGIES:
            L,Hi=threshold_data[method]
            t1=time.perf_counter()
            obj=process_one(raw,R,L,Hi,refine,seed,f,g,h)
            maps_by_method[method]=obj["maps"]
            low_a=np.asarray(L);hi_a=np.asarray(Hi)
            measure.append({
                "name":meta["name"],"scope":meta["scope"],"method":method,
                "candidate_count":obj["candidate_count"],
                "H_pixel_count":obj["H_pixel_count"],
                "high_seed_count":obj["seed_count"],
                "post_gate_hidden_count":obj["suggest_hidden"],
                "post_gate_protected_count":obj["protected_review"],
                "post_gate_H_pixels":obj["display_H_pixels"],
                "post_gate_refined_pixels":obj["display_refined_pixels"],
                "G_C_bounded_refined_objects":obj["refined_objects"],
                "threshold_low_min_dn":float(low_a.min()),
                "threshold_low_median_dn":float(np.median(low_a)),
                "threshold_low_max_dn":float(low_a.max()),
                "threshold_high_min_dn":float(hi_a.min()),
                "threshold_high_median_dn":float(np.median(hi_a)),
                "threshold_high_max_dn":float(hi_a.max()),
                "elapsed_seconds":round(time.perf_counter()-t1,4),
                "frame2_truth_available":False
            })
            A,B=make_panel(raw,obj["maps"],method)
            output_panels.append((A,B))
        left=panel(raw,[],meta["name"]+" / RAW")
        all_panels=[left]+[p for pair in output_panels for p in pair]
        filename=meta["name"]+"_7panels.png"
        folder="figures_historical9" if meta["scope"]=="frame1_historical_9_windows" else "figures_controls9"
        save_png(dest/folder/filename,np.hstack(all_panels))
        np.savez_compressed(dest/"masks"/(meta["name"]+"_method_masks.npz"),
            roi_global_xyxy=np.array(rect,np.int32),
            **{method+"_H":np.uint8(maps_by_method[method]["h_original"])
               for method in STRATEGIES},
            **{method+"_final":np.uint8(maps_by_method[method]["fused_joint_display"])
               for method in STRATEGIES})
        entries.append(meta)
        print("WINDOW_DONE",meta["name"],
              [(k,m["candidate_count"],m["post_gate_H_pixels"])
               for k,m in [(v["method"],v) for v in measure[-3:]]],flush=True)
    # Historical ten center positions are NOT manual frame2 truth. Only for
    # visual replay at SAME absolute coordinates and geometry.
    refs=pd.read_csv(E2/"ten_manual_targets_posthoc_evaluation.csv")
    for ref in refs.itertuples(index=False):
        p=dest/"figures_historical9"/(ref.window_id+"_7panels.png")
        b=p.read_bytes()
        atlas=cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_COLOR)
        if atlas is None:raise OSError("failed to reopen historic window comparison")
        ix=int(ref.clicked_RAW_x);iy=int(ref.clicked_RAW_y)
        geom=next(a for a in named if a["name"]==ref.window_id)
        cx=ix-geom["rect"][0];cy=iy-geom["rect"][1]
        size=112
        sx=max(0,min(256-size,cx-size//2))
        sy=max(0,min(256-size,cy-size//2))
        sections=[atlas[30+sy:30+sy+size,
                        k*256+sx:k*256+sx+size] for k in range(7)]
        crop=np.hstack([cv2.resize(v,(224,224),interpolation=cv2.INTER_NEAREST)
                        for v in sections])
        save_png(dest/"figures_10_frame1_replay"/
                 (ref.manual_target_id+"_same_coordinates_only.png"),crop)
    if len(list((dest/"figures_historical9").glob("*.png")))!=9 or len(list((dest/"figures_controls9").glob("*.png")))!=9 or len(list((dest/"figures_10_frame1_replay").glob("*.png")))!=10:
        raise AssertionError("missing 9+9+10 comparison figures")
    table=pd.DataFrame(measure)
    table.to_csv(dest/"18windows_3methods_metrics.csv",index=False,encoding="utf-8-sig")
    group=table.groupby(["scope","method"])[[
        "candidate_count","H_pixel_count","high_seed_count",
        "post_gate_hidden_count","post_gate_H_pixels",
        "post_gate_refined_pixels"
    ]].agg(["sum","mean"]).round(3)
    group.to_csv(dest/"method_comparison_summary.csv",encoding="utf-8-sig")
    floor_low=np.mean([v["low_floor_dominates"] for v in audit])
    floor_high=np.mean([v["high_floor_dominates"] for v in audit])
    report={
        "frame":"26 (2).raw","baseline":"fixed 170/230 fused BlackHat DN",
        "global_stats":global_stat,
        "local_grid_count":len(audit),
        "local_low_floor_dominated_grid_fraction":round(float(floor_low),4),
        "local_high_floor_dominated_grid_fraction":round(float(floor_high),4),
        "grid_median_percentiles_DN":np.percentile(med,[5,50,95]).tolist(),
        "grid_sigma_percentiles_DN":np.percentile(sig,[5,50,95]).tolist(),
        "hist_9":9,"control_9":9,"historical_center_replay_images":10,
        "original_frame2_H_generated_independently":True,
        "thresholds_fixed_before_frame2_truth_review":True,
        "not_recall_or_false_positive_rate":True,
        "identical_postprocessing":"Case03E2 bounded Gaussian22/Closing61 + F/G/H gate recomputed",
        "runtime_seconds":round(time.perf_counter()-tic,2),
        "method_metrics":table.groupby(["scope","method"])[
            ["candidate_count","post_gate_H_pixels","post_gate_refined_pixels"]
        ].sum().to_dict(orient="index"),
    }
    # group dictionary contains tuple keys - serialize manually
    report["method_metrics"]=[
        {"scope":key[0],"method":key[1],**{
            c:int(v) for c,v in row.to_dict().items()
        }} for key,row in table.groupby(["scope","method"])[[
            "candidate_count","post_gate_H_pixels","post_gate_refined_pixels"
        ]].sum().iterrows()]
    (dest/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (dest/"config_snapshot.json").write_text(json.dumps({
        "adaptive":asdict(cfgT),"refine":asdict(refine),"H_seed":asdict(seed),
        "noise_small_F":asdict(f),"noise_structure_G":asdict(g),
        "noise_texture_H":asdict(h),
        "source_response":str(RESPONSE_RUN),
        "frame1_windows_replayed_only_for_relative_spatial_comparison":True,
        "manually_annotated_frame2_defects":0
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("RESULT",json.dumps(report,ensure_ascii=False),flush=True)
    print("OUTPUT",dest,flush=True)
    return dest

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--run-id",default="run_20261010_sample26_frame2_three_methods_v1")
    args=a.parse_args()
    run(args.run_id)
