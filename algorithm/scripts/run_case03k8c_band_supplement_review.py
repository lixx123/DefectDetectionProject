"""Case03-K8-C: workband B-supplement reversible RAW contrast / DoG triage.

This is a study protocol, not a new accepted detector. Frozen J5/H/G/MAD and
K8B masks unchanged. Three outputs: A=fixed H branch, B=untouched band B
proposals, C=K8C triage status (promising/review/micro hide suggestion).
Never delete pixels; preserve every original candidate connected label.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
import argparse,json,sys
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from src.detection.case03k8c_noise_review import K8CConfig,evaluate_binary_band
from scripts.run_case03g_joint_noise_refinement import save_png

K8B=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
K8A=cfg.OUTPUT_ROOT/"case03k8a_auto_workband_masks/run_20261013_26twoframes_variableband_v2"
OUT_PARENT=cfg.OUTPUT_ROOT/"case03k8c_band_supplement_review"
CONF=K8CConfig()
PREVIEW_STEP=8

def raw_uint16(frame:int):
    return np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",
                     dtype=">u2",mode="r",shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))

def img8(roi):
    sub=np.asarray(roi[::8,::8],np.float32)
    p1,p995=np.percentile(sub,[1,99.5])
    return cv2.cvtColor(np.uint8(np.clip((sub-p1)/max(1.,p995-p1)*255,0,255)),
                        cv2.COLOR_GRAY2BGR)

def pngmask(path):
    m=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    if m is None or m.ndim!=2:raise ValueError(path)
    return m>0

def make_panels(raw,band_id,metadata,results,outdir,frame):
    """Side-by-side three perspectives of SAME RAW pixels, no misalignment."""
    y0,y1=[int(z) for z in metadata["ROI_global_xyxy"][1::2]]
    gray=img8(raw[y0:y1])
    h,w=gray.shape[:2]
    def paint(binary,color):
        base=gray.copy()
        coarse=cv2.resize(np.uint8(binary),(w,h),interpolation=cv2.INTER_AREA)>0
        base[coarse]=color
        return base
    A,B,promising,review,micro=results
    comps=[
      ("A: FIXED 170/230",paint(A,(30,200,230)),
       "Existing fixed-H, not exactly frozen J5"),
      ("B: PER-BAND THRESHOLD",paint(B,(20,185,240)),
       "All experimental B workband candidate px"),
      ("K8-C: PROMISING DARK",paint(promising,(50,220,110)),
       "RAW annulus / MAD / DoG corroborated"),
      ("K8-C: MANUAL REVIEW",paint(review,(25,185,225)),
       "Edges, uncertain or fixed-H supported"),
      ("K8-C: MICRO HIDE SUGGEST",paint(micro,(120,135,160)),
       "Area 1-2px; not deleted from input B")
    ]
    paths=[]
    for i,(headline,pic,sub) in enumerate(comps,1):
        title=np.full((84,w,3),28,np.uint8)
        cv2.putText(title,f"K8C F{frame} B{band_id}: {headline}",
                    (10,25),cv2.FONT_HERSHEY_SIMPLEX,.52,(235,235,235),1)
        cv2.putText(title,sub,(10,51),cv2.FONT_HERSHEY_SIMPLEX,.38,(216,216,216),1)
        cv2.putText(title,"ROI SAME RAW y origin; display occupancy not a defect-size metric",
                    (10,75),cv2.FONT_HERSHEY_SIMPLEX,.35,(214,214,214),1)
        name=f"0{i}_{headline.replace(' ','_').replace(':','').replace('/','_')}.png"
        save_png(outdir/name,np.vstack((title,pic)))
        paths.append(name)
    # One 5-column wide image for on-screen side-by-side if feasible.
    if w*3<4500:
        comparison=np.hstack([
            np.vstack((np.full((24,w,3),28,np.uint8),pic))
            for _,pic,_ in comps[:3]])
        for i,(title,_,_) in enumerate(comps[:3]):
            cv2.putText(comparison,title[:35],(i*w+9,18),
                        cv2.FONT_HERSHEY_SIMPLEX,.45,(236,236,236),1)
        save_png(outdir/"A_B_K8C_three_column_comparison.png",comparison)
    return paths

def annotate_focus(img,label,area,contrast,z,dog,status,band,frame):
    title=np.full((80,img.shape[1],3),27,np.uint8)
    cv2.putText(title,f"F{frame} B{band} | candidate {label} | area={area}px2",
                (7,26),cv2.FONT_HERSHEY_SIMPLEX,.45,(235,235,235),1)
    cv2.putText(title,f"RAW contrast={contrast}; z={z}; DoG P90={dog}",
                (7,48),cv2.FONT_HERSHEY_SIMPLEX,.40,(215,215,215),1)
    cv2.putText(title,status[:48],(7,69),cv2.FONT_HERSHEY_SIMPLEX,.38,(200,200,200),1)
    return np.vstack((title,img))

def focus_atlas(frame,band,raw,metadata,bmask,a_mask,records,banddir):
    """A mix of largest proposed B+ and strongest RAW candidates plus micro controls.

    Images are presented on equal RAW crops with fixed source coords. Does
    not rank using user labels, or touch detector candidate masks.
    """
    y0=int(metadata["ROI_global_xyxy"][1])
    n,lab,stats,centers=cv2.connectedComponentsWithStats(np.uint8(bmask),8)
    df=pd.DataFrame(records)
    novel=df[df.is_independent_of_fixed_H].copy()
    if not len(novel):return
    strongest=novel[(novel.classification=="PROMISING_DARK_REVIEW")].sort_values(
             ["candidate_area_px2","raw_MAD_significance_z"],ascending=False).head(12)
    biggest=novel.sort_values("candidate_area_px2",ascending=False).head(12)
    rng=np.random.default_rng(314159+frame*10+band)
    micro=novel[novel.classification=="MICRO_HIDE_SUGGESTION"]
    if len(micro)>12:
        micro=micro.iloc[rng.choice(len(micro),12,replace=False)]
    images=[]
    for label,list_ in [("large12",biggest),("strong_dark12",strongest),
                        ("micro12",micro)]:
        cards=[]
        for row in list_.itertuples(index=False):
            idx=int(row.band_component_label)
            cx,cy=map(int,np.rint(centers[idx]))
            x0=max(0,cx-64);x1=min(bmask.shape[1],cx+64)
            yb0=max(0,cy-64);yb1=min(bmask.shape[0],cy+64)
            roi=np.asarray(raw[y0+yb0:y0+yb1,x0:x1],np.uint16)
            if roi.size==0:raise ValueError("bad frame crop")
            low,high=np.percentile(roi,[1,99.5])
            g=np.uint8(np.clip((roi.astype(np.float32)-low)/max(1,high-low)*255,0,255))
            plain=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
            overlay=plain.copy()
            mask=lab[yb0:yb1,x0:x1]==idx
            cnt,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(overlay,cnt,-1,(25,200,235),1)
            shape=(192,192)
            pair=np.hstack([cv2.resize(im,shape,interpolation=cv2.INTER_NEAREST)
                            for im in [plain,overlay]])
            cards.append(annotate_focus(
                pair,idx,int(row.candidate_area_px2),
                row.raw_contrast_fraction,row.raw_MAD_significance_z,
                row.dog_dark_core_p90_dn,row.classification,band,frame))
        if not cards:continue
        # 3 columns by 4 rows, each cell approx 384x272.
        w=cards[0].shape[1];h=cards[0].shape[0]
        empty=np.full((h,w,3),26,np.uint8)
        while len(cards)%3:cards.append(empty.copy())
        plate=np.vstack([np.hstack(cards[k:k+3]) for k in range(0,len(cards),3)])
        name=f"review_{label}_RAW_vs_K8C_outline.png"
        save_png(banddir/name,plate)
        images.append(name)
    return images

def run_frame(frame:int,bands:set[int]|None,run:Path):
    root=K8B/f"frame26_{frame}"
    meta=json.loads((root/"summary.json").read_text(encoding="utf-8"))
    frame_raw=raw_uint16(frame)
    k8a_meta=json.loads((K8A/f"frame26_{frame}/audit.json").read_text(encoding="utf-8"))
    # Not modifying or rewriting source IMG or labels.
    region=cv2.imdecode(np.frombuffer(
        (K8A/f"frame26_{frame}/region_type_fullres.png").read_bytes(),np.uint8),
        cv2.IMREAD_UNCHANGED)
    band_ids=cv2.imdecode(np.frombuffer(
        (K8A/f"frame26_{frame}/band_id_fullres.png").read_bytes(),np.uint8),
        cv2.IMREAD_UNCHANGED)
    assert np.array_equal(band_ids>0,region==2)
    stats=pd.read_csv(root/"perband_comparison_and_thresholds.csv")
    target=run/f"frame26_{frame}"
    target.mkdir()
    allrows=[];bandstats=[]
    for spec in meta["ROI_crops"]:
        bid=int(spec["band_id"])
        if bands is not None and bid not in bands:continue
        banddir=target/f"band{bid:02d}"
        banddir.mkdir()
        y0,y1=int(spec["ROI_global_xyxy"][1]),int(spec["ROI_global_xyxy"][3])
        A=pngmask(root/f"band_{bid:02d}_A_hysteresis_mask_cropped.png")
        B=pngmask(root/f"band_{bid:02d}_B_hysteresis_mask_cropped.png")
        core=band_ids[y0:y1]==bid
        assert A.shape==B.shape==core.shape
        assert np.all(A<=B) and np.all(B<=core)
        cropped=np.asarray(frame_raw[y0:y1],np.uint16)
        print("K8C_START_BAND",frame,bid,"B-candidate-pixels",int(B.sum()),flush=True)
        records,promising,review,micro=evaluate_binary_band(cropped,B,A,core,CONF)
        for row in records:
            row["frame"]=frame
            row["band_id"]=bid
            row["candidate_global_center_x"]=row["candidate_center_local_x"]
            row["candidate_global_center_y"]=round(row["candidate_center_local_y"]+y0,3)
            row["candidate_global_y0"]=y0+row["bbox_local_y"]
            row["candidate_global_y1_exclusive"]=y0+row["bbox_local_y"]+row["bbox_height_px"]
            row["candidate_group_uid"]=f"F{frame}_B{bid}_C{row['band_component_label']:06d}"
        allrows.extend(records)
        assert sum(row["candidate_area_px2"] for row in records)==int(B.sum())
        # Save 255/0 mask as full band ROI, plus local signed code map. RGB
        # visualization never changes 1px binary original mask semantics.
        save_png(banddir/"K8C_promising_raw_supported_mask.png",
                 promising.astype(np.uint8)*255)
        save_png(banddir/"K8C_uncertain_or_fixedH_review_mask.png",
                 review.astype(np.uint8)*255)
        save_png(banddir/"K8C_micro_suggest_hide_mask.png",
                 micro.astype(np.uint8)*255)
        roi_note={
          "source_frozen_B_mask":str(root/f"band_{bid:02d}_B_hysteresis_mask_cropped.png"),
          "source_frozen_A_mask":str(root/f"band_{bid:02d}_A_hysteresis_mask_cropped.png"),
          "source_mask_unchanged":True,
          "x0":0,"x1":cfg.RAW_WIDTH,"y0":y0,"y1":y1,
          "candidate_counts":{
           status:sum(row["classification"]==status for row in records)
           for status in sorted({row["classification"] for row in records})},
          "candidate_area_conservation":int(promising.sum()+review.sum()+micro.sum())==int(B.sum()),
          "masked_nonwork_pixels_in_candidates":0
        }
        (banddir/"status_and_geometry.json").write_text(
            json.dumps(roi_note,ensure_ascii=False,indent=2),encoding="utf-8")
        grp={k:sum(t["classification"]==k for t in records)
              for k in sorted(roi_note["candidate_counts"])}
        bandstats.append({"frame":frame,"band_id":bid,
                          "original_A_candidates":int(stats.loc[stats.band_id==bid,
                                                             "A_fixed_hysteresis_candidate_components"].iloc[0]),
                          "K8B_B_candidate_objects":len(records),
                          "novel_B_unshared_with_A":int(sum(z["is_independent_of_fixed_H"] for z in records)),
                          "strong_dark_review_candidates":grp.get("PROMISING_DARK_REVIEW",0),
                          "fixed_A_overlap_candidates":grp.get("EXISTING_FIXED_H",0),
                          "boundary_review_candidates":grp.get("BOUNDARY_REVIEW",0),
                          "small_3to7_review_candidates":grp.get("MICRO_REVIEW",0),
                          "uncertain_review_candidates":grp.get("UNCERTAIN_REVIEW",0),
                          "micro_hide_suggestion_candidates":grp.get("MICRO_HIDE_SUGGESTION",0),
                          "source_B_pixel_count":int(B.sum()),
                          "promising_candidate_pixels":int(promising.sum()),
                          "review_candidate_pixels":int(review.sum()),
                          "micro_hide_suggestion_pixels":int(micro.sum()),
                          "no_official_J5_changes":True})
        make_panels(frame_raw, bid,spec,(A,B,promising,review,micro),
                    banddir,frame)
        focus_atlas(frame,bid,frame_raw,spec,B,A,records,banddir)
        print("K8C_BAND_FINISHED",frame,bid,grp,flush=True)
    objects=pd.DataFrame(allrows)
    objects.to_csv(target/"all_K8B_candidate_objects_complete_K8C_audit.csv",
                   index=False,encoding="utf-8-sig")
    bandtable=pd.DataFrame(bandstats)
    bandtable.to_csv(target/"K8C_per_band_review_summary.csv",
                     index=False,encoding="utf-8-sig")
    # The 12 previously user-reviewed K8B top-area examples are **posthoc**:
    # "belongs to dark spot" should not tune the decision in K8C.
    dev_ref=root/"band02_candidate_review_atlas/band2_candidate_raw_contrast_manual_review.csv"
    if frame==2 and 2 in bandtable.band_id.tolist() and dev_ref.exists():
        confirmed=pd.read_csv(dev_ref,encoding="utf-8-sig")
        top=confirmed[confirmed.group=="top12_by_area"].copy()
        assert len(top)==12
        allB=objects[objects.band_id==2].copy()
        review=top[["candidate_label","pixel_area"]].merge(
            allB,left_on="candidate_label",right_on="band_component_label",
            validate="one_to_one")
        assert len(review)==12
        assert (review.pixel_area==review.candidate_area_px2).all()
        review["user_assessment_from_previous_turn"]="VISIBLE_DARK_SPOT_CANDIDATE"
        review["review_is_development_set_not_blind_validation"]=True
        review["requires_confirming_pixel_outer_contour"]=True
        review.to_csv(target/"band02_user_reviewed_12_POSTHOC_only.csv",
                      index=False,encoding="utf-8-sig")
        print("K8C_POSTHOC_12_USER_REVIEW",frame,
              review.classification.value_counts().to_dict(),flush=True)
    summary={
       "frame":frame,"input_K8B":str(root),"source_RAW":f"26 ({frame}).raw",
       "per_band_count_processed":len(bandstats),
       "band_ids_processed":bandtable.band_id.tolist(),
       "original_J5_and_K5_unchanged":True,
       "no_candidate_source_mask_pixels_ever_deleted":True,
       "proposed_suggest_hide_not_auto_removed_from_source":True,
       "all_mask_regions_inside_original_K8A_work_core":True,
       "human_labels_not_used_in_candidate_gate":True,
       "human_12_dark_spot_references_posthoc_only":True,
       "not_a_true_defect_classifier":True,
       "candidate_summary":bandstats
    }
    (target/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

def run(runid:str,frames:list[int],bands:set[int]|None):
    dest=OUT_PARENT/runid
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True)
    res=[]
    for frame in frames:res.append(run_frame(frame,bands,dest))
    main={"stage":"CASE03K8C_REVERSIBLE_PROPOSAL_TRIAGE",
          "frames":frames,"bands":sorted(bands) if bands else "all_K8A_bands",
          "parameters":asdict(CONF),
          "results":res,
          "source_J5_K5_not_edited":True,
          "manual_dark_spot_reference_separate_from_scoring":True}
    (dest/"summary.json").write_text(json.dumps(main,ensure_ascii=False,indent=2),
                                    encoding="utf-8")
    print("K8C_TRIAL_COMPLETE",json.dumps({
       "output":str(dest),"frames":frames,
       "band_summaries":[item["candidate_summary"] for item in res]
    },ensure_ascii=False),flush=True)
    return dest

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--frames",nargs="+",type=int,choices=[1,2],default=[1,2])
    parser.add_argument("--bands",nargs="*",type=int)
    opts=parser.parse_args()
    run(opts.run_id,opts.frames,set(opts.bands) if opts.bands else None)
