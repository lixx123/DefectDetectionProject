"""Immutable Case03-K8D/E priority RAW candidate trials across the full 20-RAW batch.

Old 26_1/26_2 are referenced unchanged. New frames use frozen original K8C
classification, K8D 3/2/1.5 MAD RAW envelope and K8E exact pixel OR grouping.
Not production acceptance, not J5+B physical-object reconciliation.
All original B source candidates have explicit dispositions including micros.
"""
from pathlib import Path
from dataclasses import replace
from collections import Counter
import sys,argparse,json,traceback,time
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from scripts.run_case03frozen_all20_robustness import (
    inputs,OUT as ROBUST,BAND_CFG,B_CFG,region_of_interest)
from scripts.run_case03k8i_stage2_fullband_priority_contours import (
    raw_labels_in_128,ENABLED_CLASSES,RAW_CONF,STABLE_CONF,GROUP_CONF)
from src.detection.case03k8a_band_locator import locate_transmission_bands
from src.detection.case03k3_spot_contour_pilot import raw_outer_envelope
from src.detection.case03k8d_group_stability import resolve
from src.detection.case03k8e_group_hypothesis import make_groups
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03k8g_1p5_display_boxes import write_lossless
HIST=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
OUT=C.OUTPUT_ROOT/"CASE03_FROZEN_K8DE_PRIORITY_ALL20_20261019_v1"
VERSION="FROZEN_K8DE_ALL20_PRIORITY_NO_AUTO_APPROVAL_V1"
def png(path):
    im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if im is None:raise IOError(path)
    return im
def savejson(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
def one(info):
    uid=info["uid"];folder=OUT/uid;status=folder/"status.json"
    if status.exists():
        result=json.loads(status.read_text(encoding="utf-8"))
        if result["status"]=="PASS":return result
        raise RuntimeError("Existing failed/partial result preserved: "+str(folder))
    if folder.exists():raise FileExistsError("Incomplete K8DE frame "+str(folder))
    folder.mkdir(parents=True)
    start=time.perf_counter()
    result={"uid":uid,"sample":info["sample_id"],"frame":info["frame_id"],
       "version":VERSION,"status":"RUNNING",
       "source_B_pixels_modified":False,"original_J5_modified":False,
       "original_K8A_K8B_K8C_modified":False,
       "all_micro_K8D_raw_expansion_done":False,
       "cross_channel_J5_B_dedup_done":False,
       "new_user_confirmation_count":0}
    try:
        if uid in ("26_1","26_2"):
            old=HIST/f"frame26_{info['frame_id']}"
            s=json.loads((old/"summary.json").read_text(encoding="utf-8"))
            result.update({"status":"PASS","scope":"FROZEN_K8I2_REFERENCE_NO_RERUN",
                "B_all_source_count":s["source_B_total"],
                "new_raw_trials":s["new_exact_RAW_trials"],
                "review_group_count":s["new_group_review_count"],
                "source_archive":str(old),"elapsed_sec":0.0})
            savejson(status,result);return result
        src=ROBUST/uid
        original=pd.read_csv(src/"ALL_B_SOURCE_CANDIDATE_LEDGER.csv",
                             low_memory=False,encoding="utf-8-sig")
        metadata=json.loads((src/"status.json").read_text(encoding="utf-8"))
        assert metadata["status"]=="PASS"
        assert len(original)==metadata["B_all_source_object_count"]
        raw=np.memmap(info["path"],mode="r",dtype=">u2",
                      shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
        ids=png(src/"K8A_band_id_fullres.png")
        loc=locate_transmission_bands(raw,BAND_CFG)
        bands=loc["bands"]
        assert len(bands)==metadata["band_count"]
        assert {int(x["band_id"]) for x in bands}==set(np.unique(ids))-{0}
        all_sources=[];trialrows=[];trialmasks=[]
        for band in bands:
            bid=int(band["band_id"])
            sub=original[original.band_id==bid]
            y0,y1=region_of_interest(band,raw.shape,B_CFG)
            original_B=png(src/f"band{bid:02d}/B_adaptive_SOURCE_UNALTERED.png")>0
            assert original_B.shape==(y1-y0,C.RAW_WIDTH)
            assert not np.any(original_B & (ids[y0:y1]!=bid))
            n,lab,stats,centers=cv2.connectedComponentsWithStats(
                np.uint8(original_B),8)
            assert len(sub)==n-1
            for candidate in sub.itertuples(index=False):
                label=int(candidate.band_component_label)
                area=int(candidate.candidate_area_px2)
                assert int(stats[label,cv2.CC_STAT_AREA])==area
                typ=str(candidate.classification)
                selected=typ in ENABLED_CLASSES
                policy=("K8D_PRIORITY_RAW_PENDING" if selected
                      else "MICRO_SUGGEST_HIDE_RETAINED_NOT_NOISE_TRUTH"
                      if typ=="MICRO_HIDE_SUGGESTION"
                      else "MICRO_REVIEW_RETAINED_NOT_NOISE_TRUTH"
                      if typ=="MICRO_REVIEW"
                      else "FIXED_H_A_B_COMMON_SOURCE_RETAINED"
                      if typ=="EXISTING_FIXED_H"
                      else "OTHER_SOURCE_RETAINED_NO_RAW_TRIAL")
                base={"uid":str(candidate.candidate_source_uid),
                   "sample":info["sample_id"],"frame":info["frame_id"],
                   "band_id":bid,"B_source_label":label,
                   "K8C_category":typ,"source_area_px2":area,
                   "processing_tier":policy,
                   "status":"SOURCE_RETAINED_NO_RAW_TRIAL",
                   "source_B_preserved":True,
                   "automatically_user_approved":False}
                if selected:
                    cx=float(centers[label,0]);cy=float(centers[label,1])+y0
                    x0=max(0,min(C.RAW_WIDTH-128,int(round(cx))-64))
                    yy0=max(0,min(C.RAW_HEIGHT-128,int(round(cy))-64))
                    rect=(x0,yy0,x0+128,yy0+128)
                    source128=raw_labels_in_128(lab,y0,rect)
                    seed=(source128==label)
                    reason=""
                    if int(seed.sum())!=area:
                        reason="ORIGINAL_COMPONENT_NOT_FULLY_INSIDE_128PX_ROI"
                    else:
                        work=(ids[yy0:yy0+128,x0:x0+128]==bid)
                        if np.any(seed&~work):
                            reason="SOURCE_CROSSES_WORKCORE_OR_BAND_BORDER"
                    if reason:
                        base["status"]="GEOMETRY_REVIEW_SOURCE_ONLY"
                        base["reason"]=reason
                        trialrows.append({**base,"outer_area_px2":area,
                                          "mask_npz":"","selected_raw_k":None})
                    else:
                        roi=np.asarray(raw[yy0:yy0+128,x0:x0+128],np.uint16)
                        masks={};audits={}
                        for k in (3.,2.,1.5):
                            masks[k],audits[k]=raw_outer_envelope(
                                roi,seed,(cx-x0,cy-yy0),
                                replace(RAW_CONF,raw_noise_sigma_multiplier=k))
                        outer,dec=resolve(seed,masks,audits,work,source128,
                                          stats[:,cv2.CC_STAT_AREA],label,STABLE_CONF)
                        assert np.all(outer[seed])
                        name=f"S{info['sample_id']}_F{info['frame_id']}_B{bid:02d}_C{label:07d}"
                        file=folder/f"band{bid:02d}"/(name+"_RAW_K8D_MASKS.npz")
                        file.parent.mkdir(exist_ok=True)
                        np.savez_compressed(file,
                            original_B_source=np.uint8(seed),
                            original_B_labels=np.int32(source128),
                            k3=np.uint8(masks[3.]),k2=np.uint8(masks[2.]),
                            k1p5=np.uint8(masks[1.5]),
                            outer=np.uint8(outer),
                            workcore=np.uint8(work),
                            raw_roi_global_xyxy=np.int32(rect))
                        base["status"]=str(dec["status"])
                        base["reason"]=";".join(dec["reasons"])
                        trialrows.append({**base,
                            "outer_area_px2":int(outer.sum()),
                            "k3_area_px2":int(masks[3.].sum()),
                            "k2_area_px2":int(masks[2.].sum()),
                            "k1p5_area_px2":int(masks[1.5].sum()),
                            "selected_raw_k":dec["selected_k"],
                            "eligible_sibling_B_labels":";".join(
                                map(str,dec["group"]["eligible_siblings"])),
                            "mask_npz":str(file)})
                        trialmasks.append({"band_id":bid,"label":label,
                            "box":rect,"mask":outer,
                            "status":dec["status"],
                            "partial_competitors":dec["group"]["partial_competitors"],
                            "embedded_evidence":dec["group"]["member_evidence"]})
                all_sources.append(base)
            print("K8DE_BAND",uid,bid,"B",len(sub),"newRAW",
                  sum(x["band_id"]==bid for x in trialrows),flush=True)
        assert len(all_sources)==len(original)
        assert len(set(x["uid"] for x in all_sources))==len(original)
        pd.DataFrame(all_sources).to_csv(
            folder/"ALL_ORIGINAL_B_DISPOSITION.csv",encoding="utf-8-sig",index=False)
        pd.DataFrame(trialrows).to_csv(
            folder/"K8D_PRIORITY_RAW_3_2_1p5MAD_TRIALS.csv",encoding="utf-8-sig",index=False)
        groups=make_groups(trialmasks,GROUP_CONF) if trialmasks else []
        csvrows=[]
        canvas=png(src/"B_ALL_wholeframe_1to8.png")
        assert canvas.ndim==3 and canvas.shape[:2]==(
            C.RAW_HEIGHT//8,(C.RAW_WIDTH+7)//8)
        for i,g in enumerate(groups,1):
            name=f"K8DE_S{info['sample_id']}_F{info['frame_id']}_B{int(g['band_id']):02d}_G{i:05d}"
            path=folder/"K8E_exact_review_unions"/(name+".npz")
            path.parent.mkdir(exist_ok=True)
            np.savez_compressed(path,RAW_global_bbox=np.int32(g["box"]),
                exact_review_union=np.uint8(g["mask"]),
                raw_outer_source_B_labels=np.int32(g["selected_candidate_labels"]),
                embedded_B_source_labels=np.int32(
                    [x["B_label"] for x in g["embedded_B_source_evidence"]]))
            yy,xx=np.nonzero(g["mask"])
            assert len(xx)==int(g["exact_group_union_px2"])
            bbox=(g["box"][0]+int(xx.min()),g["box"][1]+int(yy.min()),
                  g["box"][0]+int(xx.max())+1,g["box"][1]+int(yy.max())+1)
            rect=expand_bbox_xyxy(bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
            a,b,c,e=bbox_to_display_px(rect,(C.RAW_WIDTH,C.RAW_HEIGHT),
                                      (canvas.shape[1],canvas.shape[0]),8)
            cv2.rectangle(canvas,(a,b),(c,e),(20,166,244),1,cv2.LINE_8)
            csvrows.append({"review_group_id":name,"sample":info["sample_id"],
                "frame":info["frame_id"],"band_id":int(g["band_id"]),
                "source_B_labels":";".join(map(str,g["selected_candidate_labels"])),
                "sum_source_outer_areas_px2":int(g["original_K8D_masks_sum_px2"]),
                "exact_union_area_px2":int(g["exact_group_union_px2"]),
                "duplicate_pixels_removed":int(g["deduplicated_pixels"]),
                "review_status":str(g["review_status"]),
                "review_bbox_global_xyxy":json.dumps(bbox),
                "mask_npz":str(path),"user_confirmed":False,
                "production_defect_count_not_approved":True})
        pd.DataFrame(csvrows,columns=[
           "review_group_id","sample","frame","band_id","source_B_labels",
           "sum_source_outer_areas_px2","exact_union_area_px2",
           "duplicate_pixels_removed","review_status",
           "review_bbox_global_xyxy","mask_npz","user_confirmed",
           "production_defect_count_not_approved"]).to_csv(
           folder/"K8E_EXACT_OR_GROUPS_PENDING.csv",index=False,encoding="utf-8-sig")
        cv2.putText(canvas,
           f"{uid} / RAW K8DE Review ONLY / ORIGINAL B SOURCE SAVED",
           (10,48),cv2.FONT_HERSHEY_SIMPLEX,.5,(237,239,245),1,cv2.LINE_8)
        write_lossless(folder/"K8DE_ALL_PRIORITY_REVIEW_1to8.png",canvas)
        result.update({"status":"PASS",
            "scope":"K8C_STRONG_UNCERTAIN_BOUNDARY_NEW_RAW_K8D_K8E",
            "B_all_source_count":len(all_sources),
            "new_raw_trials":len(trialrows),
            "new_exact_outer_masks":len(trialmasks),
            "review_group_count":len(csvrows),
            "source_records_lost":0,
            "selected_K8C_categories":sorted(ENABLED_CLASSES),
            "nonselected_B_records_preserved":len(all_sources)-len(trialrows),
            "RAW_trial_status_counts":dict(Counter(x["status"] for x in trialrows)),
            "elapsed_sec":round(time.perf_counter()-start,2)})
        savejson(status,result)
        print("K8DE_FRAME_PASS",uid,"B",len(all_sources),
              "RAW",len(trialrows),"GROUPS",len(csvrows),flush=True)
        return result
    except Exception as err:
        result.update({"status":"FAIL","error":str(err),
            "traceback":traceback.format_exc(),
            "elapsed_sec":round(time.perf_counter()-start,2)})
        savejson(status,result)
        print("K8DE_FRAME_FAIL",uid,type(err).__name__,str(err),flush=True)
        return result

def summarize():
    reports=[];allraw=inputs()
    for info in allraw:
        p=OUT/info["uid"]/"status.json"
        reports.append(json.loads(p.read_text(encoding="utf-8"))
                       if p.is_file() else {"uid":info["uid"],"status":"NOT_RUN"})
    summary={"stage":"K8DE_K8C_EVIDENCE_PRIORITY_RAW_AND_PIXEL_OR_20_RAW",
        "frames_pass":sum(x["status"]=="PASS" for x in reports),
        "frames_fail":sum(x["status"]=="FAIL" for x in reports),
        "frames_not_run":sum(x["status"]=="NOT_RUN" for x in reports),
        "all_B_source_dispositions_present_where_processed":True,
        "micro_unexpanded_and_retained":True,
        "J5_B_crosschannel_dedup_not_done":True,
        "user_approval_never_guessed":True,"frames":reports}
    savejson(OUT/"summary.json",summary)
    pd.DataFrame([{"uid":x["uid"],"status":x["status"],
       "B_source_count":x.get("B_all_source_count"),
       "RAW_trial_count":x.get("new_raw_trials"),
       "K8E_review_groups":x.get("review_group_count"),
       "failure":x.get("error","")} for x in reports]).to_csv(
       OUT/"ALL20_K8DE_STAGE_LEDGER.csv",index=False,encoding="utf-8-sig")
    print("K8DE_ROBUST20_STATUS",summary["frames_pass"],"PASS",
        summary["frames_fail"],"FAIL",
        summary["frames_not_run"],"NOT_RUN",flush=True)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--only",nargs="*",default=[])
    args=parser.parse_args()
    allraw=inputs()
    if args.only and set(args.only)-{x["uid"] for x in allraw}:
        raise ValueError("Unknown IDs "+str(args.only))
    OUT.mkdir(parents=True,exist_ok=True)
    for info in allraw:
        if args.only and info["uid"] not in args.only:continue
        one(info)
        summarize()
    summarize()
if __name__=="__main__":main()
