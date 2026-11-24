"""K8-B band2 review atlas: high-rank vs tiny candidates (not trained).

Uses second and first original RAW, existing B-threshold *trial* masks,
and detector BH. Sample selection by candidate area (no labels).
One raw and one contour-overlay panel per candidate; 12 large & 12 tiny
per frame. Annular RAW DN contrast is for audit, not selection/gating.
"""
from pathlib import Path
from collections import defaultdict
import sys,json
import cv2,numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import user_config as cfg
from scripts.run_case03g_joint_noise_refinement import save_png
OUT=cfg.OUTPUT_ROOT/"case03k8b_bandwise_threshold_trial/run_20261013_frame26_1_2_anchoredrobustZ_v2"
FUSED={
    1:cfg.OUTPUT_ROOT/"case03j4_global_cache/sample26_frame1_fused_blackhat_from_case02.npy",
    2:cfg.OUTPUT_ROOT/"case03k6_frame2_fused_blackhat/run_20261012_frame26_2_frozen_kernels_v1/frame26_2_fused_blackhat_exact.npy"
}
PREVIEW=176
SEED=20261013


def maskload(path):
    m=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_UNCHANGED)
    assert m is not None and m.ndim==2
    return m>0


def normalize_raw(raw):
    a,b=np.percentile(raw,[1,99.5])
    v=np.uint8(np.clip((raw.astype(float)-a)/max(1.,b-a)*255,0,255))
    return cv2.cvtColor(v,cv2.COLOR_GRAY2BGR)


def candidate_stats(raw,core,center,compmask,allmask):
    yy,xx=np.ogrid[:raw.shape[0],:raw.shape[1]]
    cx,cy=center
    dist=np.sqrt((xx-cx)**2+(yy-cy)**2)
    ring=(dist>=13)&(dist<=31)&~allmask
    if np.count_nonzero(ring)<70:
        return {"raw_reference_valid":False,
                "relative_dark_contrast":None,"raw_MAD_z":None,
                "raw_contrast_dn":None}
    sourceval=float(np.median(raw[compmask]))
    reference=float(np.median(raw[ring]))
    noise=max(3.,1.4826*float(np.median(abs(raw[ring].astype(float)-reference))))
    diff=reference-sourceval
    return {"raw_reference_valid":True,
            "relative_dark_contrast":round(diff/max(1.,reference),5),
            "raw_MAD_z":round(diff/noise,4),
            "raw_contrast_dn":round(diff,2)}


def card(source_raw,source_bh,source_mask,centroid,info):
    y,x=centroid[1],centroid[0]
    sy0=max(0,y-64);sy1=min(source_raw.shape[0],y+64)
    sx0=max(0,x-64);sx1=min(source_raw.shape[1],x+64)
    raw=np.asarray(source_raw[sy0:sy1,sx0:sx1],np.uint16)
    bh=np.asarray(source_bh[sy0:sy1,sx0:sx1],np.uint16)
    mask=source_mask[sy0:sy1,sx0:sx1]
    if mask.size==0:raise ValueError("empty crop")
    norm=normalize_raw(raw)
    outline=norm.copy()
    cnt,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,
                            cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(outline,cnt,-1,(30,225,244),1)
    # Center J5 seed? red marker at chosen component only, not physical label.
    cv2.drawMarker(outline,(x-sx0,y-sy0),(0,0,230),
                   cv2.MARKER_CROSS,5,1)
    row=[]
    for image in [norm,outline]:
        row.append(cv2.resize(image,(PREVIEW,PREVIEW),
                              interpolation=cv2.INTER_NEAREST))
    plot=np.hstack(row)
    header=np.full((59,plot.shape[1],3),27,np.uint8)
    a=f"Frame {info['frame']}, B2 trial #{info['rank']:02d} | {info['pixel_area']} px2"
    cv2.putText(header,a,(6,23),cv2.FONT_HERSHEY_SIMPLEX,.46,(230,230,230),1)
    b=f"RAW delta={info['raw_contrast_dn']}DN; z={info['raw_MAD_z']}"
    cv2.putText(header,b,(6,47),cv2.FONT_HERSHEY_SIMPLEX,.45,(210,210,210),1)
    return np.vstack((header,plot))


def run_one(frame):
    src=OUT/f"frame26_{frame}"
    fdir=src/"band02_candidate_review_atlas"
    if fdir.exists():raise FileExistsError(fdir)
    fdir.mkdir()
    summary=json.loads((src/"summary.json").read_text(encoding="utf-8"))
    r=next(r for r in summary["ROI_crops"] if r["band_id"]==2)
    y0,y1=r["ROI_global_xyxy"][1],r["ROI_global_xyxy"][3]
    allmask=maskload(src/"band_02_B_hysteresis_mask_cropped.png")
    fixed=maskload(src/"band_02_A_hysteresis_mask_cropped.png")
    assert not np.any(fixed)
    n,labels,stat,center=cv2.connectedComponentsWithStats(
        allmask.astype(np.uint8),8)
    assert n-1>0
    candidates=sorted(range(1,n),key=lambda k:(-stat[k,cv2.CC_STAT_AREA],k))
    biggest=candidates[:12]
    # Tiny small >=? 1/2px, pick across x for representative candidates.
    small=[k for k in candidates if stat[k,cv2.CC_STAT_AREA]<=2]
    rng=np.random.default_rng(SEED+frame)
    selected_small=sorted(rng.choice(small,min(12,len(small)),
                                     replace=False).tolist())
    rawmem=np.memmap(cfg.DATA_ROOT/f"26 ({frame}).raw",dtype=">u2",mode="r",
                     shape=(cfg.RAW_HEIGHT,cfg.RAW_WIDTH))
    BH=np.load(FUSED[frame],mmap_mode="r",allow_pickle=False)
    gray=np.asarray(rawmem[y0:y1,:],np.uint16)
    bh=np.asarray(BH[y0:y1,:],np.uint16)
    rows=[]
    for group,ids in [("top12_by_area",biggest),("tiny12_deterministic",selected_small)]:
        cards=[]
        for rank,i in enumerate(ids,1):
            cx,cy=np.round(center[i]).astype(int)
            sy0=max(0,cy-64);sy1=min(gray.shape[0],cy+64)
            sx0=max(0,cx-64);sx1=min(gray.shape[1],cx+64)
            selected=(labels[sy0:sy1,sx0:sx1]==i)
            fullmask=allmask[sy0:sy1,sx0:sx1]
            localraw=gray[sy0:sy1,sx0:sx1]
            metrics=candidate_stats(localraw,selected,(cx-sx0,cy-sy0),
                                    selected,fullmask)
            rec={
               "frame":frame,"band_id":2,"group":group,"rank":rank,
               "candidate_label":i,"center_global_x":cx,
               "center_global_y":cy+y0,
               "pixel_area":int(stat[i,cv2.CC_STAT_AREA]),
               "original_fixed_170_230_mask_contains_this":False,
               **metrics,
               "manual_confirm_defect":"",
               "manual_defect_contour_valid":"",
               "review_notes":"",
               "new_candidate_does_not_imply_true_defect":True
            }
            cards.append(card(gray,bh,allmask,(cx,cy),rec))
            rows.append(rec)
        # 3 cards per row, four rows (12), cyan outlines / raw local contrast
        sheet=np.vstack([np.hstack(cards[k:k+3])
                         for k in range(0,len(cards),3)])
        fname=f"band2_{group}_12patches_RAW_B_candidate.png"
        save_png(fdir/fname,sheet)
    pd.DataFrame(rows).to_csv(fdir/"band2_candidate_raw_contrast_manual_review.csv",
                             encoding="utf-8-sig",index=False)
    overview={
       "stage":"CASE03K8B_BAND2_RAW_PATCH_REVIEW",
       "frame":frame,
       "all_band2_threshold_B_components":n-1,
       "candidate_top_area12_count":len(biggest),
       "candidate_small_area1to2_reviewed":len(selected_small),
       "selection_uses_no_manual_defect_labels":True,
       "RAW_contrast_not_gating_algorithm_only_audit":True,
       "patches_are_true_128px_RAW_local_crops_when_not_near_bounds":True,
       "mask_conversion_thickness_does_not_affect_candidate_size":True
    }
    (fdir/"summary.json").write_text(json.dumps(overview,indent=2),encoding="utf-8")
    print("K8B_BAND2_GALLERY_READY",frame,json.dumps(overview),flush=True)


if __name__=="__main__":
    for frame in (1,2):run_one(frame)
