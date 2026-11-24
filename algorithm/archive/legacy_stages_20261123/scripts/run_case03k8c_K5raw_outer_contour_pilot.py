"""Case03-K8C outline repair PILOT (unaccepted): reuse RAW K3/K5 contour method.

Inputs: K8-B original B band masks, K8-C "promising" objects, and in
second-frame B2 also all 12 visually identified development candidates.
Do NOT apply K5's fixed 170/230 or its BH61 seed logic to these lower DN
K8B candidates. Instead reuse the exact previously verified K3
raw_outer_envelope with its 3/2/1.5 MAD floor sweep, conservative
stability/geometry/edge limits.

NO MUTATION: old B/J5/K5 masks or labels; output is review-only contour
proposals, not official defect physical boundaries.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict,replace
import cv2,json,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03k3_spot_contour_pilot import (
    PilotConfig,raw_outer_envelope,aspect_and_bbox)
from src.detection.case03i_size_grade import (
    SizeGradeConfig,max_feret_centers_px,grade_size)
from scripts.run_case03g_joint_noise_refinement import save_png

K8B=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8C=cfg.OUTPUT_ROOT/"case03k8c_band_supplement_review/run_20261013_f1_f2_allbands_reversible_v2"
K8A=cfg.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
OUT=cfg.OUTPUT_ROOT/"case03k8c_outlines_prioritized/run_20261013_K5RAW_contour_expansion_pilot_v1"
PARAM=PilotConfig()
GRADE=SizeGradeConfig()
SIGMAS=(3.,2.,1.5)
PITCH=3.2
# Revision currently modifies NO accepted object ID, grade or source area.
CONTOUR_BORDER_PX=3
MIN_SEED_OVERLAP=.45
MAX_PROPOSAL_TO_B=5.0
MAX_RELAX_STEP_AREA_RATIO=1.55
MAX_BOUNDARY_OVERLAP=0
MAX_OTHER_B_COMPONENT_OVERLAP=2

def decode(path):
    im=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),
                    cv2.IMREAD_UNCHANGED)
    if im is None:raise IOError(path)
    return im

def shape_stats(source:np.ndarray)->dict:
    ys,xs=np.where(source)
    if len(xs)==0:return {"area":0,"feret_px":0,"area_um2":0,"length_um":0,"grade":"NONE"}
    feret=max_feret_centers_px(np.column_stack([xs,ys]))
    grade,_=grade_size(int(len(xs)),feret,GRADE)
    return {"area":int(len(xs)),"feret_px":round(feret,3),
            "area_um2":round(len(xs)*PITCH**2,2),
            "length_um":round(feret*PITCH,2),"grade":grade}

def roi128(raw,labels,source_label,cx,cy,full_band_y0,core_global):
    """128px source around candidate centroid using full RAW coordinates."""
    H,W=raw.shape
    left=max(0,min(W-128,int(round(cx))-64))
    top=max(0,min(H-128,int(round(cy))-64))
    right=left+128;bottom=top+128
    part=np.asarray(raw[top:bottom,left:right],np.uint16)
    seed=np.zeros((128,128),bool)
    other=np.zeros_like(seed)
    yy0=max(top,full_band_y0)
    yy1=min(bottom,full_band_y0+labels.shape[0])
    if yy0<yy1:
        lab=labels[yy0-full_band_y0:yy1-full_band_y0,left:right]
        seed[yy0-top:yy1-top]=(lab==source_label)
        other[yy0-top:yy1-top]=(lab>0)&(lab!=source_label)
    core=core_global[top:bottom,left:right]
    assert part.shape==seed.shape==other.shape==core.shape==(128,128)
    return part,seed,other,core,(left,top,right,bottom)

def select_contour(raw,seed,other,core,center):
    """Compare 3/2/1.5 MAD RAW proposals; only safe expansions provisional."""
    trials={}
    seed_metrics=shape_stats(seed)
    valid={}
    reasons={}
    for k in SIGMAS:
        config=replace(PARAM,raw_noise_sigma_multiplier=k)
        mask,audit=raw_outer_envelope(raw,seed,center,config)
        trials[k]=(mask,audit)
        errs=[]
        area=int(mask.sum())
        if not area:errs.append("NO_CONNECTED_RAW_CONTOUR")
        if area and area<seed_metrics["area"]*.8:errs.append("RAW_SMALLER_THAN_B_SEED")
        if area and area>MAX_PROPOSAL_TO_B*max(1,seed_metrics["area"]):
            errs.append("EXCESSIVE_PROPOSAL_TO_SEED_GROWTH")
        if area>PARAM.raw_max_area_px:errs.append("HARD_MAX_AREA_EXCEEDED")
        if audit["raw_proposal_touches_roi_border"]:
            errs.append("TOUCHES_128ROI_BORDER")
        if audit["raw_proposal_touches_radius_cap"]:
            errs.append("RADIAL_CAP_REACHED")
        if audit["raw_proposal_seed_overlap_fraction"]<MIN_SEED_OVERLAP:
            errs.append("INSUFFICIENT_SEED_OVERLAP")
        if np.any(mask&~core):errs.append("CROSSES_K8A_WORK_CORE")
        if np.count_nonzero(mask&other)>MAX_OTHER_B_COMPONENT_OVERLAP:
            errs.append("INTERSECTS_DIFFERENT_B_HYPOTHESIS")
        ratio,_=aspect_and_bbox(mask)
        if np.isfinite(ratio) and ratio>2.7:
            errs.append("VERY_ELONGATED_CONTOUR")
        valid[k]=not errs
        reasons[str(k)]=errs
    # K5 conservative stable contour floor sweep: no jumping directly from
    # a failed stronger threshold to a relaxed raw proposal. Compare changes
    # in nonempty connected area to previous stronger result.
    selected_mask=seed.copy()
    selected_k=None
    selected_status="SOURCE_ONLY_NO_SAFE_EXPANSION"
    previous_area=0
    for k in SIGMAS:
        mask,_=trials[k]
        area=int(mask.sum())
        if not valid[k]:continue
        if area<=seed_metrics["area"]*1.12:continue
        if k!=3.:
            prev_k=3. if k==2. else 2.
            prev=trials[prev_k][0]
            prev_area=int(prev.sum())
            if not valid[prev_k] or prev_area==0 or (
                area>prev_area*MAX_RELAX_STEP_AREA_RATIO):
                continue
        selected_mask=mask.copy()
        selected_k=k
        selected_status=f"PROVISIONAL_RAW_{k:g}MAD_REVIEW_ONLY"
    # A conservative safeguard: it may be physically valid for RAW source
    # mask to include different pixels; keep original B union, no deletion.
    combined=selected_mask|seed
    if selected_k is not None:
        if np.any(combined&~core):
            selected_mask=seed.copy()
            selected_k=None
            selected_status="SOURCE_ONLY_UNSAFE_OUT_OF_CORE_UNION"
            combined=seed.copy()
    if selected_k is None:combined=seed.copy()
    assert (combined|seed).sum()==combined.sum()
    return trials,combined,selected_k,selected_status,reasons

def png_gray(raw):
    lo,hi=np.percentile(raw,[1,99.5])
    scaled=np.uint8(np.clip((raw.astype(np.float32)-lo)/max(1.,hi-lo)*255,0,255))
    return cv2.cvtColor(scaled,cv2.COLOR_GRAY2BGR)

def panel(source_img,mask,label,line):
    g=png_gray(source_img)
    if mask.any():
        projected=cv2.resize(mask.astype(np.uint8),(256,256),interpolation=cv2.INTER_NEAREST)
        g=cv2.resize(g,(256,256),interpolation=cv2.INTER_NEAREST)
        contour,_=cv2.findContours(projected,cv2.RETR_EXTERNAL,
                                  cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(g,contour,-1,(20,215,250),1,cv2.LINE_8)
    else:g=cv2.resize(g,(256,256),interpolation=cv2.INTER_NEAREST)
    bar=np.full((65,256,3),26,np.uint8)
    cv2.putText(bar,label,(8,24),cv2.FONT_HERSHEY_SIMPLEX,.55,(233,233,233),1)
    cv2.putText(bar,line[:40],(8,49),cv2.FONT_HERSHEY_SIMPLEX,.40,(220,220,220),1)
    return np.vstack((bar,g))

def make_artifact(frame,bid,candidate_id,raw,source,trials,outer,selected,
                  status,out,details):
    metrics_orig=shape_stats(source)
    metrics_new=shape_stats(outer)
    cards=[panel(raw,np.zeros_like(source),f"F{frame} B{bid} C{candidate_id}","Raw original"),
           panel(raw,source,"ORIGINAL B SEED",
                 f"A={metrics_orig['area_um2']:.0f}um2 L={metrics_orig['length_um']:.1f}um")]
    for k in SIGMAS:
        mk,audit=trials[k]
        cards.append(panel(raw,mk,f"K5 RAW {k:g}MAD",
                           f"{int(mk.sum())}px2 | overlap{audit['raw_proposal_seed_overlap_fraction']:.2f}"))
    cards.append(panel(raw,outer,"SAFETY-GATED RESULT",
                       f"A~{metrics_new['area_um2']:.0f}um2 {status[:14]}"))
    fig=np.hstack(cards)
    filename=f"F{frame}_B{bid}_C{candidate_id:05d}_six_panel.png"
    save_png(out/filename,fig)
    return filename

def run_one(frame:int):
    target=OUT/f"frame26_{frame}"
    if target.exists():raise FileExistsError(target)
    target.mkdir(parents=True)
    raw=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",mode="r",dtype=">u2",
                  shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    full_band=decode(K8A/f"frame26_{frame}/band_id_fullres.png")
    allobj=pd.read_csv(K8C/f"frame26_{frame}/all_K8B_candidate_objects_complete_K8C_audit.csv",
                       encoding="utf-8-sig")
    chosen=allobj[allobj.classification=="PROMISING_DARK_REVIEW"].copy()
    if frame==2:
        reference=pd.read_csv(K8C/f"frame26_{frame}/band02_user_reviewed_12_POSTHOC_only.csv",
                              encoding="utf-8-sig")
        extra=allobj[(allobj.band_id==2)&(
             allobj.band_component_label.isin(reference.candidate_label))]
        chosen=pd.concat([chosen,extra],ignore_index=True).drop_duplicates(
            subset=["band_id","band_component_label"])
    assert len(chosen)>=13
    results=[];previewfiles=[]
    cache={}
    for band in chosen.band_id.unique():
        frame_root=K8B/f"frame26_{frame}"
        meta=json.loads((frame_root/"summary.json").read_text(encoding="utf-8"))
        info=next(x for x in meta["ROI_crops"] if x["band_id"]==int(band))
        cropped=decode(frame_root/f"band_{int(band):02d}_B_hysteresis_mask_cropped.png")
        n,labels,stats,cents=cv2.connectedComponentsWithStats((cropped>0).astype(np.uint8),8)
        cache[int(band)]=(labels,info,n)
    for o in chosen.sort_values(["band_id","candidate_area_px2"],ascending=[True,False]).itertuples(index=False):
        bid=int(o.band_id);label=int(o.band_component_label)
        labels,meta,n=cache[bid]
        assert label in range(1,n)
        source_global_center=(float(o.candidate_global_center_x),float(o.candidate_global_center_y))
        raw128,seed,others,core,xyxy=roi128(
            raw,labels,label,*source_global_center,
            int(meta["ROI_global_xyxy"][1]),full_band==bid)
        assert int(seed.sum())==int(o.candidate_area_px2)
        localcenter=(source_global_center[0]-xyxy[0],source_global_center[1]-xyxy[1])
        base=shape_stats(seed)
        trials,revised,k,status,reasons=select_contour(
            raw128,seed,others,core,localcenter)
        changed=shape_stats(revised)
        if changed["area"]<base["area"]:raise AssertionError("Lost B pixels")
        dest=target/f"band{bid:02d}"
        dest.mkdir(exist_ok=True)
        file=make_artifact(frame,bid,label,raw128,seed,trials,revised,k,
                           status,dest,None)
        np.savez_compressed(dest/(f"F{frame}_B{bid}_C{label:05d}_all_masks.npz"),
             original_B_seed=seed.astype(np.uint8),
             raw_k3=trials[3.][0].astype(np.uint8),
             raw_k2=trials[2.][0].astype(np.uint8),
             raw_k1p5=trials[1.5][0].astype(np.uint8),
             proposed_after_safety_gate=revised.astype(np.uint8),
             adjacent_other_B=others.astype(np.uint8),
             core_K8A_work=core.astype(np.uint8),
             full_resolution_roi_global_xyxy=np.asarray(xyxy,np.int32),
             parameter_noise_multipliers=np.asarray(SIGMAS,np.float32))
        review_reason=("PREVIOUS_USER_REVIEW_SECOND_FRAME_B2_TOP12" if frame==2
                and bid==2 and label in set(reference.candidate_label)
                else "K8C_STRONG_DARK_AUTO_PROPOSAL")
        results.append({
            "frame":frame,"band_id":bid,"candidate_label":label,
            "candidate_group_uid":o.candidate_group_uid,
            "source_K8C_classification":o.classification,
            "selected_for_review_reason":review_reason,
            "original_B_source_area_px2":base["area"],
            "original_B_length_um":base["length_um"],
            "original_B_area_um2":base["area_um2"],
            "proposed_K5RAW_outer_area_px2":changed["area"],
            "proposed_K5RAW_outer_length_um":changed["length_um"],
            "proposed_K5RAW_outer_area_um2":changed["area_um2"],
            "original_B_size_grade":base["grade"],
            "proposal_size_grade_REVIEW_ONLY":changed["grade"],
            "K5RAW_noise_k_sigma_selected":k,
            "status":status,
            "chosen_from_existing_K8B_seed":True,
            "raw_k3_area_px2":int(trials[3.][0].sum()),
            "raw_k2_area_px2":int(trials[2.][0].sum()),
            "raw_k1p5_area_px2":int(trials[1.5][0].sum()),
            "raw_k_safety_rejections":json.dumps(reasons,ensure_ascii=False),
            "manual_confirm_K5RAW_outer_complete":"",
            "J5_original_source_unchanged":True,
            "mask_nonwork_extension_authorized":False,
            "existing_B_source_pixels_preserved":True,
            "physical_object_plane_size_calibrated":False,
            "six_panel":str(dest/file)
        })
        previewfiles.append(dest/file)
        print("K8C_K5RAW_PILOT",frame,bid,label,base["area"],changed["area"],
              status,flush=True)
    report=pd.DataFrame(results)
    report.to_csv(target/"all_selected_darkspots_K5RAW_outer_comparison.csv",
                  index=False,encoding="utf-8-sig")
    # A few key objects user already recognized are serialized as a small
    # index, but not used for contour threshold selection.
    report[(report.band_id==2)].to_csv(
       target/"band02_target_review_index.csv",index=False,encoding="utf-8-sig")
    psummary={
      "frame":frame,"selected_hypotheses":len(results),
      "prior_K8C_promising_and_frame2_B2_top12":True,
      "selected_K5_raw_provisional_increased_area":int((report.proposed_K5RAW_outer_area_px2
                        >report.original_B_source_area_px2).sum()),
      "source_B_masks_or_J5_K5_modified":False,
      "pixel_pitch_um":PITCH,"object_plane_calibration_validated":False,
      "all_trial_contours_reversible_npz":True,
      "new_physical_defect_count_confirmed":None,
      "control_stability_rule":"3/2/1.5 MAD floors with seed overlap, size, radius, band core, other-candidate conflicts",
      "files":[str(v) for v in previewfiles]
    }
    (target/"summary.json").write_text(json.dumps(psummary,ensure_ascii=False,indent=2),
                                       encoding="utf-8")
    return psummary

def main():
    if OUT.exists():raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    allres=[run_one(f) for f in (1,2)]
    (OUT/"summary.json").write_text(json.dumps({"frames":allres},ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("K8C_K5RAW_PILOT_COMPLETED",json.dumps(allres,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
