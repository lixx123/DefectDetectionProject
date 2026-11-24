"""Frozen Case03 20-RAW robustness runner: K8A/B/C full source-preserving branch.

Every input RAW gets independently located WORK bands, unchanged 3/5/9/15/31
elliptical multiscale BlackHat (unmasked before morphology), existing fixed
A H170/230 and robust-z per-band B, plus K8C local RAW/MAD/DoG triage.
Outputs are NOT complete J4/J5 or automated K8D/E; the workflow stage ledger
must say so. All source B pixels, including micro/hide suggestions, saved.
Existing J4/J5 is computationally heavy and is a separate mandatory stage
for production-equivalence; no manual labels enter this robustness screening.

Supports restart/resume without overwriting completed data. Per-frame failure
is recorded as FAIL and does not magically disappear from summary.
"""
from pathlib import Path
from dataclasses import asdict
import sys,json,math,time,traceback,argparse,hashlib
from collections import Counter
import numpy as np,pandas as pd,cv2
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k8a_band_locator import (
    BandLocatorConfig,locate_transmission_bands,rasterize_region_masks)
from src.detection.case03k8b_perband_trial import (
    PerBandTrial,stats_median_mad,threshold_params,hysteresis_on_work)
from src.detection.case03k8c_noise_review import K8CConfig,evaluate_binary_band
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size
from scripts.run_case03k8b_bandwise_thresholds import (
    region_of_interest,recompute_unmasked_band_raw)
from scripts.run_case03g_joint_noise_refinement import save_png
from scripts.run_case03k8a_variable_band_masks import render as render_workbands

OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_ROBUSTNESS_20RAW_20261019_v3"
RAW_EXPECT=C.RAW_HEIGHT*C.RAW_WIDTH*2
BAND_CFG=BandLocatorConfig()
B_CFG=PerBandTrial()
C_CFG=K8CConfig()
GRADE_CFG=SizeGradeConfig()
SCREEN_VERSION="K8A_K8B_K8C_full_source_retention_v3_GLOBAL_SAMPLE_ALIGNMENT"
ORIG_A=C.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
ORIG_B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
ORIG_C=C.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
def write_json(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
def image(path):
    b=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if b is None:raise IOError(path)
    return b
def inputs():
    raws=sorted(C.DATA_ROOT.glob("*.raw"))
    out=[]
    for sample in C.SAMPLE_IDS:
        for frame in C.FRAME_IDS:
            name=f"26 ({frame}).raw" if sample==26 else f"{sample}-{frame}_000.raw"
            p=C.DATA_ROOT/name
            if not p.is_file():raise FileNotFoundError("missing 20-input RAW "+str(p))
            if p.stat().st_size!=RAW_EXPECT:
                raise AssertionError("wrong bytes "+str(p))
            out.append({"sample_id":sample,"frame_id":frame,
                        "path":str(p),"size_bytes":p.stat().st_size,
                        "uid":f"{sample}_{frame}","file":name})
    assert len(out)==20
    assert {r["file"] for r in out}=={x.name for x in raws},(
       "unaccounted/raw file extension changes",len(raws))
    return out
def metadata_for_preview(metadata):
    # The source locator profile is np.ndarray, not JSON-compatible.
    m={k:v for k,v in metadata.items() if k!="profile"}
    return m
def build_preview_canvas(raw):
    sub=np.asarray(raw[::8,::8],np.float32)
    lo,hi=np.percentile(sub,[1,99.5])
    g=np.uint8(np.clip((sub-lo)/max(1.,hi-lo)*255,0,255))
    return cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
def preview_layers(base,labels_y0,band,bmask,amask,classes,overlay):
    H,W=base.shape[:2]
    n,lab,stats,_=cv2.connectedComponentsWithStats(np.uint8(bmask),8)
    assert len(classes)==n-1
    states=np.zeros(n,np.uint8)
    for x in classes:
        cid=int(x["band_component_label"])
        typ=str(x["classification"])
        states[cid]=(
            3 if typ=="MICRO_HIDE_SUGGESTION" else
            1 if typ=="PROMISING_DARK_REVIEW" else 2)
    assert np.array_equal(bmask,states[lab]>0)
    y0=labels_y0
    # Monotonic downsample: cv2 INTER_AREA preserves tiny source support
    # as a visible subpixel occupancy. This does not measure defect area.
    for key,code,color in [
        ("B_ALL",0,(35,207,246)),
        ("B_STRONG",1,(39,219,110)),
        ("B_REVIEW",2,(25,179,246)),
        ("B_MICRO",3,(132,153,228))]:
        mask=bmask if code==0 else (states[lab]==code)
        if not np.any(mask):continue
        nimg=overlay[key]
        # Align ROI to global 1:8 grid in integer RAW coordinates.
        # Use nearest anchored SOURCE pixel when rendering, not contour scale.
        ys,xs=np.nonzero(mask)
        yy=(ys+y0)//8;xx=xs//8
        valid=(yy<H)&(xx<W)
        nimg[yy[valid],xx[valid]]=color

def run_one(info):
    uid=info["uid"];dest=OUT/uid
    complete=dest/"status.json"
    if complete.is_file():
        s=json.loads(complete.read_text(encoding="utf-8"))
        if s.get("status")=="PASS" and s.get("version")==SCREEN_VERSION:
            print("ROBUST20_ALREADY_PASS",uid,flush=True)
            return s
        raise RuntimeError(f"Partial/FAIL result already exists {dest}, preserve evidence; retry needs explicit new run ID")
    if dest.exists():raise FileExistsError("Partial frame exists; fail safe "+str(dest))
    dest.mkdir(parents=True)
    start=time.perf_counter()
    base={"uid":uid,"sample":info["sample_id"],"frame":info["frame_id"],
          "source_file":info["path"],"input_bytes":RAW_EXPECT,
          "version":SCREEN_VERSION,"parameters":{
              "band_locator":asdict(BAND_CFG),
              "per_band_trial":asdict(B_CFG),
              "noise_triage":asdict(C_CFG),
              "frozen_J5_hysteresis_branch_used_as_reference_only":True},
          "J4_J5_full_frame_executed_for_this_sample":False,
          "G_H_Gaussian_morphology_full_J5_stage_replayed":False,
          "K8D_all_source_RAW_outer_executed":False,
          "K8E_cross_B_and_J5_physical_dedup_executed":False,
          "new_user_confirmed_defect_count":0,
          "all_B_sources_preserved":True}
    try:
        raw=np.memmap(info["path"],dtype=">u2",mode="r",
                      shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
        loc=locate_transmission_bands(raw,BAND_CFG)
        if not loc["bands"]:raise RuntimeError("AUTO_K8A_NO_INTERIOR_BANDS")
        types,ids=rasterize_region_masks(raw.shape,loc["bands"],loc["exterior"],BAND_CFG)
        if ids.shape!=raw.shape or not np.array_equal(ids>0,types==2):
            raise AssertionError("WORK-band original fullres mask mismatch")
        render_workbands(raw,loc,types,ids,info["file"],dest)
        save_png(dest/"K8A_band_id_fullres.png",ids)
        save_png(dest/"K8A_region_type_fullres.png",types)
        baseline_original_equal=None
        if info["sample_id"]==26 and info["frame_id"] in (1,2):
            source=ORIG_A/f"frame26_{info['frame_id']}"
            baseline_original_equal=(
                np.array_equal(ids,image(source/"band_id_fullres.png")) and
                np.array_equal(types,image(source/"region_type_fullres.png")))
            if not baseline_original_equal:
                raise AssertionError("K8A geometry changed in frozen replay of 26_1/26_2")
        steps=int(B_CFG.robust_sample_stride_px)
        batch=[]
        stats={}
        workbands=[]
        for band in loc["bands"]:
            bid=int(band["band_id"])
            y0,y1=region_of_interest(band,raw.shape,B_CFG)
            core=(ids[y0:y1]==bid)
            if not np.count_nonzero(core):raise ValueError("empty core "+str(bid))
            t=time.perf_counter()
            bh=recompute_unmasked_band_raw(raw,y0,y1)
            assert bh.shape==core.shape and bh.dtype==np.uint16
            grid_start=(-y0)%steps  # historical K8B samples fused RAW on GLOBAL [::8] grid
            bg_sample=bh[grid_start::steps,::steps][core[grid_start::steps,::steps]]
            cal=stats_median_mad(bg_sample,B_CFG.min_sigma_dn)
            local_raw=np.asarray(raw[y0+grid_start:y1:steps,::steps],np.uint16)
            rawmed=float(np.median(local_raw[core[grid_start::steps,::steps]]))
            cal.update({"workband_raw_median_dn":round(rawmed,4),
                        "band_id":bid})
            stats[bid]=cal
            np.save(dest/f"B{bid:02d}_exact_unmasked_5kernel_blackhat_rawDN.npy",bh)
            batch.append({"band_id":bid,"y0":y0,"y1":y1,
                          "core_source_px":int(core.sum())})
            print("ROBUST20_BH",uid,"band",bid,"core",int(core.sum()),
                  "secs",round(time.perf_counter()-t,2),flush=True)
        ref=max(stats,key=lambda z:stats[z]["workband_raw_median_dn"])
        transfer=threshold_params(stats,B_CFG,ref)
        if info["sample_id"]==26 and info["frame_id"] in (1,2):
            tab=pd.read_csv(ORIG_B/f"frame26_{info['frame_id']}"/
                            "perband_comparison_and_thresholds.csv")
            for b in batch:
                bid=b["band_id"]
                line=tab[tab.band_id==bid].iloc[0]
                assert np.isclose(transfer[bid]["band_trial_low_dn"],
                                  line.band_trial_low_dn,rtol=0,atol=.025),(
                   "Original K8B low change",uid,bid)
                assert np.isclose(transfer[bid]["band_trial_high_dn"],
                                  line.band_trial_high_dn,rtol=0,atol=.025),(
                   "Original K8B high change",uid,bid)
        all_rows=[]
        zone_stats=[]
        bg=build_preview_canvas(raw)
        overlay={k:bg.copy() for k in ("B_ALL","B_STRONG","B_REVIEW","B_MICRO")}
        for item in batch:
            bid=item["band_id"];y0=item["y0"];y1=item["y1"]
            banddir=dest/f"band{bid:02d}";banddir.mkdir()
            bhpath=dest/f"B{bid:02d}_exact_unmasked_5kernel_blackhat_rawDN.npy"
            bh=np.load(bhpath,mmap_mode="r")
            core=(ids[y0:y1]==bid)
            a,meta_a=hysteresis_on_work(bh,core,
                       B_CFG.original_low_dn,B_CFG.original_high_dn)
            b,meta_b=hysteresis_on_work(bh,core,
                       transfer[bid]["band_trial_low_dn"],
                       transfer[bid]["band_trial_high_dn"])
            a_outside_b=int(np.count_nonzero(a&~b))
            if not np.any(b):raise ValueError("B has no source pixels in workband")
            save_png(banddir/"A_fixed170_230_source_pixels.png",np.uint8(a)*255)
            save_png(banddir/"B_adaptive_SOURCE_UNALTERED.png",np.uint8(b)*255)
            if info["sample_id"]==26 and info["frame_id"] in (1,2):
                p=ORIG_B/f"frame26_{info['frame_id']}"/f"band_{bid:02d}_B_hysteresis_mask_cropped.png"
                if not np.array_equal(b,image(p)>0):
                    raise AssertionError("Exact K8B B mask not reproduced "+uid+str(bid))
            cropped=np.asarray(raw[y0:y1],np.uint16)
            t=time.perf_counter()
            rows,prom,review,micro=evaluate_binary_band(cropped,b,a&b,core,C_CFG)
            # Exactly conserve ALL adaptive B source pixel masks and counts.
            if int(b.sum())!=sum(int(z["candidate_area_px2"]) for z in rows):
                raise AssertionError("Source B pixels lost")
            if not np.array_equal((prom|review|micro),b):
                raise AssertionError("Noise review lost B source pixels")
            for row in rows:
                row["sample_id"]=info["sample_id"]
                row["frame_id"]=info["frame_id"]
                row["band_id"]=bid
                row["global_center_x"]=row["candidate_center_local_x"]
                row["global_center_y"]=round(row["candidate_center_local_y"]+y0,3)
                row["global_bbox_x"]=row["bbox_local_x"]
                row["global_bbox_y"]=row["bbox_local_y"]+y0
                row["candidate_source_uid"]=(
                    f"S{info['sample_id']}_F{info['frame_id']}_B{bid:02d}_C{int(row['band_component_label']):07d}")
                row["visibility_layer"]=(
                    "MICRO_HIDE_REVIEW_ONLY_NOT_DELETED"
                    if row["classification"]=="MICRO_HIDE_SUGGESTION"
                    else "K8C_PROMISING_PENDING" if row["classification"]=="PROMISING_DARK_REVIEW"
                    else "K8C_OTHER_SOURCE_PENDING_REVIEW")
                row["K8D_raw_outer_status"]="UNPROCESSED_OUT_OF_ROBUSTNESS_K8A_B_C_SCOPE"
                row["J5_crosschannel_state"]="PENDING_J5_FULL_PIPELINE"
            save_png(banddir/"K8C_STRONG_RAW_DARK_PENDING.png",np.uint8(prom)*255)
            save_png(banddir/"K8C_REVIEW_OTHER_SOURCES.png",np.uint8(review)*255)
            save_png(banddir/"K8C_MICRO_SUGGEST_HIDE_NOT_DELETED.png",np.uint8(micro)*255)
            preview_layers(bg,y0,bid,b,a,rows,overlay)
            counts=dict(sorted(Counter(z["classification"] for z in rows).items()))
            if info["sample_id"]==26 and info["frame_id"] in (1,2):
                historical=pd.read_csv(ORIG_C/f"frame26_{info['frame_id']}"/
                    "all_K8B_candidate_objects_complete_K8C_audit.csv")
                old=historical[historical.band_id==bid]
                if len(old)!=len(rows):raise AssertionError("K8C count regression "+uid)
                if dict(Counter(old.classification))!=counts:
                    raise AssertionError("K8C categories changed "+uid+str(bid))
            zone_stats.append({
                "sample_id":info["sample_id"],"frame_id":info["frame_id"],
                "band_id":bid,"core_source_px":item["core_source_px"],
                "BH_five_multiscale_unmasked_before_workband":True,
                "historical_robust_ref":ref,
                "A_fixed_low_high":[170,230],
                "B_adaptive_low_high":[transfer[bid]["band_trial_low_dn"],
                                       transfer[bid]["band_trial_high_dn"]],
                "A_mask_px":int(a.sum()),"B_mask_px":int(b.sum()),
                "A_fixed_pixels_not_selected_by_B_adaptive":a_outside_b,
                "B_source_components":len(rows),
                "K8C_class_counts":counts,
                "strong_raw_supported_pending":counts.get("PROMISING_DARK_REVIEW",0),
                "micro_suggest_hide_but_NOT_deleted":counts.get("MICRO_HIDE_SUGGESTION",0),
                "all_B_source_pixel_conserved":True})
            all_rows.extend(rows)
            # Do not need BH temporary for later stages: source B mask remains.
            del bh
            bhpath.unlink()
            print("ROBUST20_K8C",uid,"band",bid,
                  "objects",len(rows),"states",counts,
                  "seconds",round(time.perf_counter()-t,2),flush=True)
        pd.DataFrame(all_rows).to_csv(dest/"ALL_B_SOURCE_CANDIDATE_LEDGER.csv",
                                      index=False,encoding="utf-8-sig")
        pd.DataFrame(zone_stats).to_csv(dest/"BANDWISE_SCREENING_SUMMARY.csv",
                                        index=False,encoding="utf-8-sig")
        for kind,img in overlay.items():
            # Crop full-resolution 8x preview, only source occupancy.
            cv2.putText(img,uid+" | "+kind+" | ORIGINAL RAW SOURCE PIXELS, NOT PHYSICAL TRUTH",
                        (10,25),cv2.FONT_HERSHEY_SIMPLEX,.48,(230,230,230),1)
            save_png(dest/(kind+"_wholeframe_1to8.png"),img)
        count=Counter(x["classification"] for x in all_rows)
        base.update({"status":"PASS",
                     "band_count":len(batch),"band_ids":sorted(stats),
                     "band_count_hardcoded":False,
                     "strongest_RAW_band_used_as_reference":ref,
                     "B_all_source_object_count":len(all_rows),
                     "all_B_source_pixel_count":sum(z["B_mask_px"] for z in zone_stats),
                     "class_counts":dict(sorted(count.items())),
                     "A_170_230_source_component_candidates":
                            sum(z["A_mask_px"] for z in zone_stats),
                     "all_bands_processed":True,
                     "K8A_baseline_26_1_2_bitexact":baseline_original_equal,
                     "K8B_original_26_1_2_bitexact":(
                       True if info["sample_id"]==26 and info["frame_id"] in (1,2) else None),
                     "K8C_original_26_1_2_count_and_class_exact":(
                       True if info["sample_id"]==26 and info["frame_id"] in (1,2) else None),
                     "J4_J5_full_frame_executed_for_this_sample":(
                       True if info["sample_id"]==26 and info["frame_id"] in (1,2) else False),
                     "G_H_Gaussian_morphology_full_J5_stage_replayed":False,
                     "K8D_all_source_RAW_outer_executed":False,
                     "K8E_cross_B_and_J5_physical_dedup_executed":False,
                     "elapsed_sec":round(time.perf_counter()-start,2)})
        write_json(complete,base)
        print("ROBUST20_FRAME_PASS",uid,"bands",len(batch),"B",len(all_rows),
              "secs",base["elapsed_sec"],flush=True)
        return base
    except Exception as exc:
        base.update({"status":"FAIL","failure_type":type(exc).__name__,
                     "failure_message":str(exc),"traceback":traceback.format_exc(),
                     "elapsed_sec":round(time.perf_counter()-start,2)})
        write_json(complete,base)
        print("ROBUST20_FRAME_FAIL",uid,type(exc).__name__,str(exc),flush=True)
        return base

def summarize(inputs_list,run_selected):
    reports=[]
    for info in inputs_list:
        p=OUT/info["uid"]/"status.json"
        if p.is_file():reports.append(json.loads(p.read_text(encoding="utf-8")))
        else:reports.append({"uid":info["uid"],"source_file":info["path"],"status":"NOT_RUN"})
    fieldnames=[
        "uid","sample","frame","status","band_count","band_ids",
        "B_all_source_object_count","all_B_source_pixel_count",
        "class_counts","K8A_baseline_26_1_2_bitexact",
        "K8B_original_26_1_2_bitexact",
        "K8C_original_26_1_2_count_and_class_exact",
        "J4_J5_full_frame_executed_for_this_sample",
        "G_H_Gaussian_morphology_full_J5_stage_replayed",
        "K8D_all_source_RAW_outer_executed",
        "K8E_cross_B_and_J5_physical_dedup_executed",
        "failure_message","elapsed_sec"]
    data=[{key:r.get(key) for key in fieldnames} for r in reports]
    pd.DataFrame(data).to_csv(OUT/"ALL_20_INPUTS_STAGE_STATUS.csv",
                               index=False,encoding="utf-8-sig")
    summ={"stage":"ALL_20_RAW_K8A_K8B_K8C_ROBUSTNESS_ACTUAL_EXECUTION",
        "20_expected_inputs":len(inputs_list),
        "frames_pass":sum(r["status"]=="PASS" for r in reports),
        "frames_fail":sum(r["status"]=="FAIL" for r in reports),
        "frames_not_yet_run":sum(r["status"]=="NOT_RUN" for r in reports),
        "all_20_screening_passed":all(r["status"]=="PASS" for r in reports),
        "full_J4_J5_all20_pipeline_completed":False,
        "frozen_full_algorithm_not_equivalent_for_18_new_frames":True,
        "Do_not_report_precision_recall_without_groundtruth":True,
        "no_human_annots_used_to_tune_thresholds":True,
        "all_saved_original_26_1_2_masks_bands_and_K8C_check_retained":True,
        "frames":reports}
    write_json(OUT/"summary.json",summ)
    print("ROBUST20_SUMMARY",summ["frames_pass"],"PASS",
          summ["frames_fail"],"FAIL",summ["frames_not_yet_run"],"NOT_RUN",flush=True)
    return summ

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--only",nargs="*",default=[],
                         help="sample-frame ids such as 26_1, 27_3")
    args=parser.parse_args()
    allinput=inputs()
    if not OUT.exists():OUT.mkdir(parents=True)
    chosen=set(args.only)
    if chosen-set(x["uid"] for x in allinput):
        raise ValueError("Unknown --only "+str(chosen))
    for inf in allinput:
        if chosen and inf["uid"] not in chosen:continue
        run_one(inf)
        summarize(allinput,chosen)
    summarize(allinput,chosen)
if __name__=="__main__":main()
