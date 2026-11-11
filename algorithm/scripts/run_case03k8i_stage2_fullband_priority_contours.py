"""Case03 K8I stage 2: K8C evidence-led RAW outer trial, provenance and review groups.

FULL-SOURCE POLICY: NO source deletion, no changes to J5/B/K8C or frozen K8D,
K8E or K8F/G/I runs. All remaining lower-evidence/micro objects explicitly
accounted for as untouched source reference, never considered noise truth.

Keep the exact old K8D/K8E user-approved 2 groups F2 B2 G006/G009 frozen:
new proposals may overlap but do NOT auto-merge/correct old reviewed groups.
"""
from pathlib import Path
from dataclasses import asdict,replace
import sys,math,json
from collections import defaultdict,Counter
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as C
from src.detection.case03k3_spot_contour_pilot import PilotConfig,raw_outer_envelope
from src.detection.case03k8d_group_stability import K8DConfig,resolve
from src.detection.case03k8e_group_hypothesis import (
    GroupPolicy,make_groups,global_intersection)
from src.detection.case03k8g_display_boxes import (
    expand_bbox_xyxy,bbox_to_display_px)
from scripts.run_case03k8d_grouped_raw_contours import make6
from scripts.run_case03k8g_1p5_display_boxes import write_lossless
K8I=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_sample26_2frames_fullcandidate_lineage_v1"
K8B=C.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8A=C.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
K8D=C.OUTPUT_ROOT/"case03k8d_grouped_stable_outlines/run_20261014_K8D_full_contour_realtime_v3"
K8E=C.OUTPUT_ROOT/"case03k8e_object_hypothesis_unions/run_20261014_K8E_exact_group_union_v1"
PRIOR=C.OUTPUT_ROOT/"case03k8i_full_frame_lineage/run_20261015_fullframe_novel_medlarge_K8D_original_rules_probe_v1"
OUT=C.OUTPUT_ROOT/"case03k8i_stage2_RAW_review_and_association/run_20261017_twoframes_priority_evidence_v1"
ENABLED_CLASSES={"PROMISING_DARK_REVIEW","UNCERTAIN_REVIEW","BOUNDARY_REVIEW"}
APPROVED={"K8E_F2_B2_G006","K8E_F2_B2_G009"}
RAW_CONF=PilotConfig(); STABLE_CONF=K8DConfig();GROUP_CONF=GroupPolicy()

def pngread(p):
    v=cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if v is None:raise IOError(p)
    return v

def raw_labels_in_128(labels,source_y0,box):
    x0,y0,x1,y1=box
    out=np.zeros((128,128),np.int32)
    left=max(y0,source_y0);right=min(y1,source_y0+labels.shape[0])
    if left<right:
        out[left-y0:right-y0,:]=labels[left-source_y0:right-source_y0,x0:x1]
    return out

def read_prior_mask(frame,band,label):
    paths=[
        (K8D/f"frame26_{frame}"/f"band{band:02d}"/
            f"F{frame}_B{band}_C{label:05d}_K8D_all_masks.npz",
          "K8D_full_outer","raw_global_roi_xyxy"),
        (PRIOR/f"frame26_{frame}"/f"band{band:02d}"/
            f"F{frame}_B{band}_C{label:05d}_NEW_RAW_trial_all_masks.npz",
          "K8I_K8D_review_outer","original_RAW_roi_xyxy")]
    for p,m,b in paths:
        if p.exists():
            with np.load(p,allow_pickle=False) as z:
                mask=z[m].astype(bool)
                box=tuple(map(int,z[b]))
            return {"band_id":band,"label":label,"mask":mask,"box":box,"source_file":str(p)}
    raise FileNotFoundError(f"missing existing RAW candidate {frame}-{band}-{label}")

def run_frame(frame):
    dest=OUT/f"frame26_{frame}";dest.mkdir()
    df=pd.read_csv(K8I/f"frame26_{frame}"/"end_to_end_candidate_lineage.csv",
                   encoding="utf-8-sig",low_memory=False,
                   dtype={"source_local_id":"string"})
    sources=df[df.stage=="K8B"].copy()
    assert len(sources)==(16766 if frame==1 else 3892)
    d=pd.read_csv(K8D/f"frame26_{frame}"/"all_K8D_original_vs_outer_review.csv")
    prior_file=PRIOR/f"frame26_{frame}"/"all_NOT_PREVIOUSLY_PROCESSED_NOVEL_MEDLARGE_K8D_trials.csv"
    old=pd.read_csv(prior_file)
    old_set={(int(x.band_id),int(x.candidate_label)) for x in d.itertuples()}
    pilot_set={(int(x.band_id),int(x.B_label)) for x in old.itertuples()}
    assert not (old_set&pilot_set)
    known=old_set|pilot_set
    raw=np.memmap(C.DATA_ROOT/f"26 ({frame}).raw",mode="r",dtype=">u2",
                  shape=(C.RAW_HEIGHT,C.RAW_WIDTH))
    band_id=pngread(K8A/f"frame26_{frame}"/"band_id_fullres.png")
    assert band_id.shape==raw.shape
    bmeta=json.loads((K8B/f"frame26_{frame}"/"summary.json").read_text(encoding="utf-8"))
    roi_by_band={int(v["band_id"]):v["ROI_global_xyxy"] for v in bmeta["ROI_crops"]}
    new_results=[];new_masks=[];old_masks=[];decisions=[]
    for band in sorted(roi_by_band):
        subset=sources[sources.band_id==band]
        srcmask=pngread(K8B/f"frame26_{frame}"/f"band_{band:02d}_B_hysteresis_mask_cropped.png")
        n,labels,stats,centers=cv2.connectedComponentsWithStats(np.uint8(srcmask>0),8)
        assert len(subset)==n-1
        ybase=int(roi_by_band[band][1])
        for r in subset.itertuples(index=False):
            lid=int(r.source_local_id)
            klass=str(r.K8C_noise_review_classification)
            ident=(band,lid)
            if ident in old_set:
                tier="REUSE_OLD_K8D_UNMODIFIED"
            elif ident in pilot_set:
                tier="REUSE_PREVIOUS_K8I_MEDLARGE_UNMODIFIED"
            elif klass in ENABLED_CLASSES:
                tier="NEW_RAW_EVIDENCE_REVIEW"
            elif klass=="MICRO_REVIEW":
                tier="MICRO_REVIEW_SOURCE_RETAINED_NO_NEW_RAW"
            elif klass=="MICRO_HIDE_SUGGESTION":
                tier="MICRO_SUGGEST_HIDE_SOURCE_RETAINED_NO_NEW_RAW"
            elif klass=="EXISTING_FIXED_H":
                tier="FIXED_H_SOURCE_REFERENCE_NO_NEW_RAW"
            else:
                tier="OTHER_SOURCE_RETAINED_NO_NEW_RAW"
            line={
                "frame":frame,"band_id":band,"B_label":lid,
                "source_UID":str(r.candidate_source_uid),
                "K8C_classification":klass,"K8I_visibility_layer":str(r.primary_visibility_layer),
                "source_area_px2":int(r.source_area_px2),
                "stage2_tier":tier,
                "stage2_review_status":"SOURCE_RETAINED_NO_RAW_TRIAL",
                "candidate_source_preserved":True,
                "human_confirmed_by_this_run":False,
                "production_count_changed":False}
            if ident in known:
                line["stage2_review_status"]="EXISTING_RAW_TRIAL_READ_ONLY"
                old_masks.append(read_prior_mask(frame,band,lid))
            elif tier=="NEW_RAW_EVIDENCE_REVIEW":
                assert int(stats[lid,cv2.CC_STAT_AREA])==int(r.source_area_px2)
                cx=round(float(centers[lid,0]),3)
                cy=round(float(centers[lid,1]+ybase),3)
                x0=max(0,min(C.RAW_WIDTH-128,int(round(cx))-64))
                y0=max(0,min(C.RAW_HEIGHT-128,int(round(cy))-64))
                box=(x0,y0,x0+128,y0+128)
                local=raw_labels_in_128(labels,ybase,box)
                seed=local==lid
                source_area=int(stats[lid,cv2.CC_STAT_AREA])
                reason=None
                if seed.sum()!=source_area:
                    reason="SOURCE_COMPONENT_DOES_NOT_FIT_128PX_ROI"
                else:
                    core=band_id[y0:y0+128,x0:x0+128]==band
                    if np.any(seed&~core):
                        reason="SOURCE_CROSSES_OR_LIES_OUTSIDE_WORK_CORE"
                if reason:
                    line["stage2_review_status"]="SKIPPED_WITH_EXPLICIT_GEOMETRY_REASON"
                    line["reason"]=reason
                    new_results.append({**line,"K8D_trial_outer_area_px2":source_area,
                       "selected_k":None,"new_NPZ":"","source_mask_exact":True})
                else:
                    roi=np.asarray(raw[y0:y0+128,x0:x0+128],np.uint16)
                    trial={};aud={}
                    for k in (3.,2.,1.5):
                        trial[k],aud[k]=raw_outer_envelope(
                            roi,seed,(cx-x0,cy-y0),
                            replace(RAW_CONF,raw_noise_sigma_multiplier=k))
                    outer,decision=resolve(seed,trial,aud,core,local,
                                            stats[:,cv2.CC_STAT_AREA],lid,STABLE_CONF)
                    assert not np.any(seed&~outer)
                    status=str(decision["status"])
                    filepath=dest/f"band{band:02d}"/f"F{frame}_B{band}_C{lid:05d}_full_RAW_trial.npz"
                    filepath.parent.mkdir(exist_ok=True)
                    np.savez_compressed(filepath,
                         original_B_source=np.uint8(seed),
                         raw_k3=np.uint8(trial[3.]),raw_k2=np.uint8(trial[2.]),
                         raw_k1p5=np.uint8(trial[1.5]),
                         new_full_RAW_review_outer=np.uint8(outer),
                         K8A_band_CORE=np.uint8(core),
                         original_B_label_grid=np.int32(local),
                         RAW_roi_global_xyxy=np.int32(box))
                    line["stage2_review_status"]=status
                    line["reason"]=";".join(decision["reasons"])
                    new_results.append({**line,
                        "K8D_trial_outer_area_px2":int(outer.sum()),
                        "k3_area_px2":int(trial[3.].sum()),
                        "k2_area_px2":int(trial[2.].sum()),
                        "k1p5_area_px2":int(trial[1.5].sum()),
                        "selected_k":decision["selected_k"],
                        "associated_sibling_B_labels":";".join(map(str,decision["group"]["eligible_siblings"])),
                        "partial_other_B_competitors":";".join(map(str,decision["group"]["partial_competitors"])),
                        "new_NPZ":str(filepath),"source_mask_exact":True})
                    new_masks.append({"band_id":band,"label":lid,
                        "box":box,"mask":outer,"status":status,
                        "partial_competitors":decision["group"]["partial_competitors"],
                        "embedded_evidence":decision["group"]["member_evidence"]})
            decisions.append(line)
        print("K8I_STAGE2_BAND",frame,band,"new",sum(z["band_id"]==band for z in new_masks),
              "preserved_old",sum(z["band_id"]==band for z in old_masks),flush=True)
    dec=pd.DataFrame(decisions)
    dec.to_csv(dest/"ALL_B_STAGE2_processing_disposition.csv",index=False,encoding="utf-8-sig")
    assert len(dec)==len(sources) and not dec.duplicated(["band_id","B_label"]).any()
    attempts=pd.DataFrame(new_results)
    attempts.to_csv(dest/"new_evidence_RAW_trial_results.csv",index=False,encoding="utf-8-sig")
    # Exact K8E-style pixel OR grouping only for NEW trial masks.
    # Existing K8E (including user's two confirmed groups) remain frozen.
    groups=make_groups(new_masks,GROUP_CONF) if new_masks else []
    review_rows=[]
    for i,g in enumerate(groups,1):
        name=f"K8I2_F{frame}_B{g['band_id']:02d}_G{i:04d}"
        # All old contour intersections are reported, NEVER autounioned with
        # archived K8E, since this could silently change approved 370/348px2.
        nearby=[]
        probe={"box":g["box"],"mask":g["mask"]}
        for oldmask in old_masks:
            if oldmask["band_id"]!=g["band_id"]:continue
            hit=global_intersection(probe,oldmask)
            if hit["intersection_px2"]:
                nearby.append({"old_B_label":oldmask["label"],
                               "intersection_px2":hit["intersection_px2"],
                               "iou":round(hit["iou"],5),
                               "containment":round(hit["min_containment"],5)})
        approval_state="PENDING_MANUAL_REVIEW"
        if nearby:approval_state="PENDING_OLD_OUTER_OVERLAP_REVIEW"
        maskfile=dest/"new_group_exact_masks"/(name+"_pixel_union.npz")
        maskfile.parent.mkdir(exist_ok=True)
        np.savez_compressed(maskfile,RAW_global_bbox=np.int32(g["box"]),
            exact_review_union=np.uint8(g["mask"]),
            raw_outer_source_B_labels=np.int32(g["selected_candidate_labels"]),
            embedded_B_source_labels=np.int32([x["B_label"] for x in g["embedded_B_source_evidence"]]))
        yy,xx=np.where(g["mask"]);box=g["box"]
        bound=(box[0]+int(xx.min()),box[1]+int(yy.min()),
               box[0]+int(xx.max())+1,box[1]+int(yy.max())+1)
        review_rows.append({"new_group_id":name,"frame":frame,"band_id":g["band_id"],
            "new_source_B_labels":";".join(map(str,g["selected_candidate_labels"])),
            "embedded_B_labels_unapproved":";".join(map(str,[x["B_label"] for x in g["embedded_B_source_evidence"]])),
            "old_K8D_B_mask_overlap_json":json.dumps(nearby),
            "new_RAW_source_areas_sum_px2":g["original_K8D_masks_sum_px2"],
            "new_exact_union_area_px2":g["exact_group_union_px2"],
            "new_internal_duplicate_pixels_removed":g["deduplicated_pixels"],
            "new_group_evidence":g["review_status"],
            "approval_status":approval_state,
            "is_user_confirmed":False,"no_old_K8E_group_ID_merged":True,
            "original_sources_unchanged":True,
            "RAW_global_review_bbox_xyxy":json.dumps(bound),
            "npz_file":str(maskfile)})
    pd.DataFrame(review_rows).to_csv(dest/"new_exact_group_union_review.csv",index=False,encoding="utf-8-sig")
    # Overlay is additional review layer; original K8I main untouched.
    imgpath=K8I/f"frame26_{frame}"/"01_MAIN_J5_plus_confirmed_plus_unapproved_MEDLARGE_1to4.png"
    img=pngread(imgpath)
    H,W=img.shape[:2]
    assert H==(C.RAW_HEIGHT+3)//4+88
    for record in review_rows:
        x0,y0,x1,y1=json.loads(record["RAW_global_review_bbox_xyxy"])
        scaled=expand_bbox_xyxy((x0,y0,x1,y1),(C.RAW_WIDTH,C.RAW_HEIGHT),1.5)
        a,b,c,e=bbox_to_display_px(scaled,(C.RAW_WIDTH,C.RAW_HEIGHT),(W,H-88),4)
        # Cyan/orange review border, no filled region, no source reclassification.
        cv2.rectangle(img,(a,b+88),(c,e+88),(18,168,246),1,cv2.LINE_8)
    write_lossless(dest/"01_STAGE2_NEW_RAW_GROUPS_REVIEW_plus_original_K8I_main.png",img)
    # All B sources have explicit treatment; eligible new status is never
    # treated as approved, and 1-2px MICRO_REVIEW remains visible upstream.
    counts=dict(sorted(Counter(dec.stage2_tier).items()))
    statuses=dict(sorted(Counter(dec.stage2_review_status).items()))
    summary={"frame":frame,"source_B_total":len(dec),
        "new_evidence_selected_count":int((dec.stage2_tier=="NEW_RAW_EVIDENCE_REVIEW").sum()),
        "new_exact_RAW_trials":len(new_masks),
        "new_geometry_skips_explicit":int(len(new_results)-len(new_masks)),
        "old_K8D_K8I_reused":len(old_masks),
        "new_group_review_count":len(review_rows),
        "approved_groups_changed":0,"source_objects_omitted":0,
        "user_approval_automatically_assigned":0,
        "tier_counts":counts,"status_counts":statuses,
        "micro_candidate_outside_scope_reason":
        "K8C MICRO_REVIEW and MICRO_HIDE_SUGGESTION kept as original B source references; conservative RAW expansion not approved for tiny low-evidence seeds.",
        "J5_B_crosschannel_physical_merge_performed":False,
        "all_candidate_source_masks_original_unchanged":True}
    (dest/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_STAGE2_FRAME_COMPLETE",json.dumps({k:v for k,v in summary.items()
            if k not in ("tier_counts","status_counts")},ensure_ascii=False),flush=True)
    return summary

def main():
    if OUT.exists():raise FileExistsError("No overwriting existing stage2 run "+str(OUT))
    OUT.mkdir(parents=True)
    frames=[run_frame(f) for f in (1,2)]
    final={"stage":"K8I_STAGE2_PRIORITY_K8C_EVIDENCE_REVIEW",
           "rule_classes":sorted(ENABLED_CLASSES),
           "old_K8D_and_confirmed_K8E_groups_frozen":True,
           "no_all_micro_RAW_outer_claim":True,
           "no_frozen_J5_B_K8C_K8D_K8E_K8I_source_modified":True,
           "parameters":{"RAW":asdict(RAW_CONF),
                         "K8D_STABILITY":asdict(STABLE_CONF),
                         "K8E_GROUP":asdict(GROUP_CONF)},
           "frames":frames}
    (OUT/"summary.json").write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding="utf-8")
    print("K8I_STAGE2_COMPLETE",str(OUT),flush=True)
if __name__=="__main__":main()
