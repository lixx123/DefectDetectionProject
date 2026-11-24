"""K8I priority RAW contour trial for ALL not-yet-processed NOVEL MED/LARGE B.

No new thresholds, no J5/other source changes. Explicit four F1
candidates are discovered dynamically from complete K8I ledger, NOT from
a hand-coded B label list. All results remain pending manual assessment.
"""
from pathlib import Path
from dataclasses import replace
import sys,json,math
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k3_spot_contour_pilot import PilotConfig,raw_outer_envelope
from src.detection.case03k8d_group_stability import K8DConfig,resolve
from src.detection.case03i_size_grade import SizeGradeConfig,grade_size,max_feret_centers_px
from src.detection.case03k8g_display_boxes import expand_bbox_xyxy,bbox_to_display_px
from scripts.run_case03k8d_grouped_raw_contours import make6
from scripts.run_case03k8g_1p5_display_boxes import write_lossless
BASE=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
A=C.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
OUT=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_fullframe_novel_medlarge_K8D_original_rules_probe_v1"
KCFG=K8DConfig();GCFG=SizeGradeConfig()
def readpng(p):
    v=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if v is None:raise ValueError(p)
    return v

def evaluate(frame,rows):
    folder=OUT/f"frame26_{frame}"
    folder.mkdir()
    prior=BASE/f"frame26_{frame}"
    bmeta=json.loads((B/f"frame26_{frame}/summary.json").read_text(encoding="utf-8"))
    spec_by_id={int(z["band_id"]):z for z in bmeta["ROI_crops"]}
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",mode="r",
                  dtype=">u2",shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    workid=readpng(A/f"frame26_{frame}/band_id_fullres.png")
    assert workid.shape==raw.shape
    img=readpng(prior/"01_MAIN_J5_plus_confirmed_plus_unapproved_MEDLARGE_1to4.png")
    orig=img.copy()
    assert img.shape==(C.RAW_HEIGHT//4+88,math.ceil(C.RAW_WIDTH/4),3)
    newresults=[];selected=[]
    for band in sorted(set(rows.band_id)):
        spec=spec_by_id[int(band)]
        roi=spec["ROI_global_xyxy"]
        ybase=int(roi[1])
        mask=readpng(B/f"frame26_{frame}"/f"band_{int(band):02d}_B_hysteresis_mask_cropped.png")>0
        n,labels,stats,centers=cv2.connectedComponentsWithStats(np.uint8(mask),8)
        assert labels.shape[1]==C.RAW_WIDTH
        for row in rows[rows.band_id==band].itertuples(index=False):
            lid=int(row.source_local_id)
            assert int(stats[lid,cv2.CC_STAT_AREA])==int(row.source_area_px2)
            xcenter=round(float(centers[lid,0]),3)
            ycenter=round(float(centers[lid,1]+ybase),3)
            x0=max(0,min(C.RAW_WIDTH-128,int(round(xcenter))-64))
            y0=max(0,min(C.RAW_HEIGHT-128,int(round(ycenter))-64))
            x1,y1=x0+128,y0+128
            lb=np.zeros((128,128),np.int32)
            ymin=max(y0,ybase);ymax=min(y1,ybase+labels.shape[0])
            if ymin<ymax:
                lb[ymin-y0:ymax-y0,:]=labels[ymin-ybase:ymax-ybase,x0:x1]
            seed=lb==lid
            if int(seed.sum())!=row.source_area_px2:
                # Do not crop / silently lose the source component.
                newresults.append({"frame":frame,"band_id":band,"B_label":lid,
                    "original_B_source_area_px2":int(row.source_area_px2),
                    "K8D_trial_outer_area_px2":int(row.source_area_px2),
                    "selected_k":None,"status":"NO_RAW_ROI_SOURCE_FULL_COVERAGE",
                    "reason":"Original B connected component extends beyond 128px review ROI",
                    "fully_manual_review_required":True,"source_modified":False})
                continue
            trial={};audit={}
            patch=np.asarray(raw[y0:y1,x0:x1],np.uint16)
            relative=(xcenter-x0,ycenter-y0)
            for k in (3.,2.,1.5):
                m,info=raw_outer_envelope(patch,seed,relative,
                    replace(PilotConfig(),raw_noise_sigma_multiplier=k))
                trial[k]=m;audit[k]=info
            core=workid[y0:y1,x0:x1]==int(band)
            proposed,decision=resolve(seed,trial,audit,core,lb,
                             stats[:,cv2.CC_STAT_AREA],lid,KCFG)
            if not np.all(proposed[seed]):raise AssertionError("source seed removed")
            dest=folder/f"band{int(band):02d}"
            dest.mkdir(exist_ok=True)
            name=f"F{frame}_B{int(band)}_C{lid:05d}"
            write_lossless(dest/(name+"_NEW_RAW_trial_6panel.png"),
                           make6(patch,seed,trial,proposed,decision,frame,int(band),lid))
            np.savez_compressed(dest/(name+"_NEW_RAW_trial_all_masks.npz"),
                original_B_source=np.uint8(seed),raw_k3=np.uint8(trial[3.]),
                raw_k2=np.uint8(trial[2.]),raw_k1p5=np.uint8(trial[1.5]),
                K8I_K8D_review_outer=np.uint8(proposed),
                original_B_labels=np.int32(lb),K8A_work_core=np.uint8(core),
                original_RAW_roi_xyxy=np.array((x0,y0,x1,y1),np.int32))
            yy,xx=np.where(proposed)
            bbox=(x0+int(xx.min()),y0+int(yy.min()),
                  x0+int(xx.max())+1,y0+int(yy.max())+1)
            enlarged=expand_bbox_xyxy(bbox,(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
            bx0,by0,bx1,by1=bbox_to_display_px(
                enlarged,(C.RAW_WIDTH,C.RAW_HEIGHT),
                (img.shape[1],img.shape[0]-88),4)
            # Strict display-only overlay; do not turn any trial into a
            # confirmed defect. Colors orange even when K8D safety is stable.
            cv2.rectangle(img,(bx0,by0+88),(bx1,by1+88),(28,157,243),1)
            cv2.putText(img,f"K8I C{lid} RAW-review",
                (max(bx0,2),max(103,by0+78)),cv2.FONT_HERSHEY_SIMPLEX,
                .35,(28,157,243),1)
            coords=np.column_stack((xx,yy))
            fl=max_feret_centers_px(coords)
            grade,_=grade_size(len(xx),fl,GCFG)
            rec={"frame":frame,"band_id":int(band),"B_label":lid,
                 "source_candidate_uid":str(row.candidate_source_uid),
                 "source_K8C_classification":str(row.K8C_noise_review_classification),
                 "original_B_source_area_px2":int(seed.sum()),
                 "RAW_3MAD_px2":int(trial[3.].sum()),
                 "RAW_2MAD_px2":int(trial[2.].sum()),
                 "RAW_1p5MAD_px2":int(trial[1.5].sum()),
                 "K8D_trial_outer_area_px2":int(proposed.sum()),
                 "trial_length_detector_image_um":round(fl*float(C.PIXEL_SIZE_UM),3),
                 "trial_size_grade":grade,"selected_k":decision["selected_k"],
                 "status":decision["status"],
                 "reason":";".join(decision["reasons"]),
                 "association_proposed_B_labels":";".join(map(str,
                    decision["group"]["eligible_siblings"])),
                 "no_official_ID_merge":True,
                 "fully_manual_review_required":True,
                 "source_modified":False,
                 "roi_original_RAW_xyxy":json.dumps([x0,y0,x1,y1]),
                 "NPZ":str(dest/(name+"_NEW_RAW_trial_all_masks.npz"))}
            newresults.append(rec)
            selected.append(rec)
            print("K8I_PRIORITY_OUTER_PROBE",frame,band,lid,
                  rec["original_B_source_area_px2"],rec["K8D_trial_outer_area_px2"],
                  rec["status"],flush=True)
    pdf=pd.DataFrame(newresults,columns=['frame','band_id','B_label','source_candidate_uid','source_K8C_classification','original_B_source_area_px2','RAW_3MAD_px2','RAW_2MAD_px2','RAW_1p5MAD_px2','K8D_trial_outer_area_px2','trial_length_detector_image_um','trial_size_grade','selected_k','status','reason','association_proposed_B_labels','no_official_ID_merge','fully_manual_review_required','source_modified','roi_original_RAW_xyxy','NPZ'])
    pdf.to_csv(folder/"all_NOT_PREVIOUSLY_PROCESSED_NOVEL_MEDLARGE_K8D_trials.csv",
               encoding="utf-8-sig",index=False)
    # Original K8I main rendering remains frozen. Overlay separately with
    # transparent traceability; new snapshots are not a replacement.
    write_lossless(folder/"08_NEW_MEDLARGE_RAW_trial_overlay_NOT_APPROVED.png",img)
    difference=np.any(img!=orig,axis=2)
    assert difference.sum()>0 if len(rows) else not difference.any()
    summary={"frame":frame,"novel_MEDLARGE_without_previous_K8D":len(rows),
        "new_K8D_RAW_trials_executed":len(selected),
        "pending_remaining_source_fullcoverage":len(rows)-len(selected),
        "newly_production_approved_count":0,
        "any_original_J5_B_or_existing_K8D_data_changed":False,
        "all_new_proposed_masks_review_only":True}
    (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

def main():
    if OUT.exists():raise FileExistsError("Refuse overwrite "+str(OUT))
    OUT.mkdir(parents=True)
    results=[]
    for frame in (1,2):
        p=BASE/f"frame26_{frame}"/"end_to_end_candidate_lineage.csv"
        tab=pd.read_csv(p,encoding="utf-8-sig",low_memory=False,
            dtype={"source_local_id":"string"})
        targets=tab[tab.primary_visibility_layer=="B_NOVEL_MEDLARGE"]
        # This is an audit stage, not an implicit all-B K8D deployment.
        results.append(evaluate(frame,targets))
    (OUT/"summary.json").write_text(json.dumps({
      "stage":"K8I_ORIGINAL_K8D_RULES_ON_UNPROCESSED_NOVEL_MEDLARGE",
      "frames":results,"source_lineage_run":str(BASE),
      "complete_unprocessed_MEDLARGE_priority_coverage":True,
      "all_B_micro_full_RAW_contours_computed":False,
      "no_detection_parameter_changes":True,
      "all_new_outlines_pending_review":True,
      "automatic_production_acceptance":False},ensure_ascii=False,indent=2),
      encoding="utf-8")
    print("K8I_MEDLARGE_K8D_PROBE_COMPLETE",flush=True)
if __name__=="__main__":main()
